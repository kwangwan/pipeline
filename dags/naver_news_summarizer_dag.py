from datetime import datetime, timedelta
import logging
import json
import requests
import time
import os

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.models import Variable

logger = logging.getLogger(__name__)

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': datetime(2026, 2, 14),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://ollama:11434")
SUMMARIZATION_MODEL = os.getenv("SUMMARIZATION_MODEL", "gemma3:4b")

def summarize_articles(**kwargs):
    pg_hook = PostgresHook(postgres_conn_id='postgres_default')
    conn = pg_hook.get_conn()
    cursor = conn.cursor()
    
    BATCH_SIZE = int(os.getenv("SUMMARIZER_BATCH_SIZE", 3))
    
    while True:
        # Lock articles that are COMPLETED (content exists) but not yet summarized
        try:
            select_sql = """
                WITH locked_rows AS (
                    SELECT id
                    FROM naver_news_articles
                    WHERE (collection_status = 'COMPLETED' OR collection_status = 'SUMM_FAILED')
                      AND summary IS NULL
                      AND content IS NOT NULL
                    ORDER BY article_date DESC NULLS LAST
                    LIMIT %s
                    FOR UPDATE SKIP LOCKED
                )
                SELECT a.id, a.content, a.title
                FROM naver_news_articles a
                JOIN locked_rows lr ON a.id = lr.id;
            """
            
            cursor.execute(select_sql, (BATCH_SIZE,))
            rows = cursor.fetchall()
            
            if not rows:
                logger.info("No more articles to summarize.")
                break

            logger.info(f"Retrieved {len(rows)} articles for summarization.")
            
            for article_id, content, title in rows:
                try:
                    # 1. Context length check & truncation
                    # Gemma 3: 4B has a limited context window. 
                    # We'll truncate the content to a safe length (e.g., 4000 characters) to avoid overflow
                    MAX_INPUT_CHAR = 4000
                    safe_content = (content[:MAX_INPUT_CHAR] + "..") if len(content) > MAX_INPUT_CHAR else content

                    # 2. Refined prompt for copyright protection and language matching
                    prompt = f"""You are a news curator. Summarize the following news article within 2000 characters.

CRITICAL INSTRUCTIONS:
1. DO NOT copy-paste sentences directly from the source. Paraphrase everything in your own words to avoid copyright issues.
2. The summary MUST be in the same language as the original text (e.g., if Article is Korean, Summary MUST be Korean).
3. Do not include any meta-comments or headers, just provide the summary text.
4. Keep the summary concise and professional.

Article Title: {title}
Article Content:
{safe_content}

Summary:"""

                    # Call Ollama API
                    response = requests.post(
                        f"{OLLAMA_HOST}/api/generate",
                        json={
                            "model": SUMMARIZATION_MODEL,
                            "prompt": prompt,
                            "stream": False,
                            "options": {
                                "num_predict": 1000, # Max output tokens
                                "temperature": 0.7
                            }
                        },
                        timeout=90
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        summary_text = result.get("response", "").strip()[:2000] # Hard character limit
                        
                        update_sql = """
                            UPDATE naver_news_articles
                            SET summary = %s,
                                summary_model = %s,
                                collection_status = 'COMPLETED'
                            WHERE id = %s
                        """
                        cursor.execute(update_sql, (summary_text, f"ollama/{SUMMARIZATION_MODEL}", article_id))
                        conn.commit()
                        logger.info(f"Summarized article {article_id}")
                    else:
                        error_msg = f"Ollama API error: {response.text}"
                        logger.error(f"{error_msg} for {article_id}")
                        
                        # Update status to failed so we don't retry immediately/indefinitely
                        fail_sql = """
                            UPDATE naver_news_articles
                            SET collection_status = 'SUMM_FAILED',
                                fail_reason = %s
                            WHERE id = %s
                        """
                        cursor.execute(fail_sql, (error_msg[:255], article_id)) # Truncate error message if needed
                        conn.commit()

                except Exception as e:
                    logger.error(f"Error summarizing {article_id}: {e}")
                    try:
                        # Attempt to record the exception
                        fail_sql = """
                            UPDATE naver_news_articles
                            SET collection_status = 'SUMM_FAILED',
                                fail_reason = %s
                            WHERE id = %s
                        """
                        cursor.execute(fail_sql, (str(e)[:255], article_id))
                        conn.commit()
                    except Exception as inner_e:
                         logger.error(f"Failed to update fail status for {article_id}: {inner_e}")
                         conn.rollback()
                    
        except Exception as e:
            logger.error(f"Batch processing error: {e}")
            conn.rollback()
            break

    cursor.close()
    conn.close()

with DAG(
    'naver_news_summarizer_dag',
    default_args=default_args,
    description='Summarize collected articles using Ollama/Gemma',
    schedule_interval='*/5 * * * *', # Shortened to 5 minutes, also triggered by collector
    catchup=False,
    max_active_runs=1,
    tags=['news', 'ai', 'summarize'],
) as dag:

    summarize_task = PythonOperator(
        task_id='summarize_articles_batch',
        python_callable=summarize_articles,
        provide_context=True,
    )
