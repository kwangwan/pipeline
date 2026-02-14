from datetime import datetime, timedelta, timezone
import logging
import json
import requests
import os

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook

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

SEARCH_API_BASE = "https://api.proj.run"
SEARCH_API_KEY = os.getenv("SEARCH_API_KEY")
SEARCH_CATEGORY_ID = os.getenv("SEARCH_CATEGORY_ID")

def upload_summarized_articles(**kwargs):
    if not SEARCH_API_KEY or not SEARCH_CATEGORY_ID:
        logger.error("SEARCH_API_KEY or SEARCH_CATEGORY_ID not set in environment.")
        return

    pg_hook = PostgresHook(postgres_conn_id='postgres_default')
    conn = pg_hook.get_conn()
    cursor = conn.cursor()
    
    # Batch size for upload
    BATCH_SIZE = 10 
    
    headers = {
        "Authorization": f"Bearer {SEARCH_API_KEY}",
        "Content-Type": "application/json"
    }

    while True:
        try:
            # Select articles that have a summary but no doc_id
            select_sql = """
                WITH locked_rows AS (
                    SELECT id
                    FROM naver_news_articles
                    WHERE summary IS NOT NULL
                      AND doc_id IS NULL
                    ORDER BY article_date DESC NULLS LAST
                    LIMIT %s
                    FOR UPDATE SKIP LOCKED
                )
                SELECT a.id, a.summary, a.title, a.original_url, a.publisher, a.article_date
                FROM naver_news_articles a
                JOIN locked_rows lr ON a.id = lr.id;
            """
            
            cursor.execute(select_sql, (BATCH_SIZE,))
            rows = cursor.fetchall()
            
            if not rows:
                logger.info("No more articles to upload.")
                break

            logger.info(f"Retrieved {len(rows)} articles for upload.")
            
            for article_id, summary, title, original_url, publisher, article_date in rows:
                try:
                    # Prepare payload
                    # Content is limited to 2000 chars (summary is already limited in summarizer)
                    
                    # article_date is naive but represents KST. Add timezone info for correct API interpretation.
                    formatted_date = None
                    if article_date:
                        # Add KST timezone (+09:00) then convert to UTC
                        kst_date = article_date.replace(tzinfo=timezone(timedelta(hours=9)))
                        utc_date = kst_date.astimezone(timezone.utc)
                        formatted_date = utc_date.isoformat()

                    payload = {
                        "categoryId": SEARCH_CATEGORY_ID,
                        "content": summary,
                        "metadata": {
                            "id": article_id,
                            "title": title,
                            "original_url": original_url,
                            "publisher": publisher
                        },
                        "date": formatted_date
                    }

                    # Call Search API
                    response = requests.post(
                        f"{SEARCH_API_BASE}/documents",
                        json=payload,
                        headers=headers,
                        timeout=30
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        doc_id = result.get("docId")
                        
                        if doc_id:
                            update_sql = """
                                UPDATE naver_news_articles
                                SET doc_id = %s
                                WHERE id = %s
                            """
                            cursor.execute(update_sql, (doc_id, article_id))
                            conn.commit()
                            logger.info(f"Uploaded article {article_id} -> docId: {doc_id}")
                        else:
                            logger.error(f"Search API returned success but no docId for {article_id}")
                            conn.rollback()
                    else:
                        logger.error(f"Search API error for {article_id}: {response.status_code} - {response.text}")
                        conn.rollback()

                except Exception as e:
                    logger.error(f"Error uploading {article_id}: {e}")
                    conn.rollback()
                    
        except Exception as e:
            logger.error(f"Batch upload processing error: {e}")
            conn.rollback()
            break

    cursor.close()
    conn.close()

with DAG(
    'naver_news_uploader_dag',
    default_args=default_args,
    description='Upload summarized articles to Search API',
    schedule_interval='*/5 * * * *', 
    catchup=False,
    max_active_runs=1,
    tags=['news', 'search', 'upload'],
) as dag:

    upload_task = PythonOperator(
        task_id='upload_articles_batch',
        python_callable=upload_summarized_articles,
        provide_context=True,
    )
