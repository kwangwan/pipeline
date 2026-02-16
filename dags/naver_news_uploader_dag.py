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

def chunk_content(content, max_length=2000):
    """
    Splits content into chunks of max_length.
    Preserves line breaks where possible.
    If a single line exceeds max_length, it is split rigidly.
    """
    if not content:
        return []

    chunks = []
    current_chunk = ""
    lines = content.split('\n')

    for line in lines:
        # +1 for the newline character that would be added
        if len(current_chunk) + len(line) + 1 > max_length:
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = ""
            
            # If the line itself is longer than max_length, split it hard
            if len(line) > max_length:
                for i in range(0, len(line), max_length):
                    chunks.append(line[i:i+max_length])
            else:
                current_chunk = line
        else:
            if current_chunk:
                current_chunk += "\n" + line
            else:
                current_chunk = line
    
    if current_chunk:
        chunks.append(current_chunk)
    
    return chunks


def upload_articles(**kwargs):
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
            # Select articles that are COMPLETED (content exists) but no doc_id
            select_sql = """
                WITH locked_rows AS (
                    SELECT id
                    FROM naver_news_articles
                    WHERE collection_status = 'COMPLETED'
                      AND doc_id IS NULL
                      AND content IS NOT NULL
                    ORDER BY article_date DESC NULLS LAST
                    LIMIT %s
                    FOR UPDATE SKIP LOCKED
                )
                SELECT a.id, a.content, a.title, a.original_url, a.publisher, a.article_date
                FROM naver_news_articles a
                JOIN locked_rows lr ON a.id = lr.id;
            """
            
            cursor.execute(select_sql, (BATCH_SIZE,))
            rows = cursor.fetchall()
            
            if not rows:
                logger.info("No more articles to upload.")
                break

            logger.info(f"Retrieved {len(rows)} articles for upload.")
            
            for article_id, content, title, original_url, publisher, article_date in rows:
                try:
                    chunks = chunk_content(content, max_length=2000)
                    first_doc_id = None
                    all_chunks_uploaded = True

                    logger.info(f"Uploading article {article_id} in {len(chunks)} chunks.")

                    for i, chunk in enumerate(chunks):
                        # article_date is naive but represents KST. Add timezone info for correct API interpretation.
                        formatted_date = None
                        if article_date:
                            # Add KST timezone (+09:00) then convert to UTC
                            kst_date = article_date.replace(tzinfo=timezone(timedelta(hours=9)))
                            utc_date = kst_date.astimezone(timezone.utc)
                            formatted_date = utc_date.isoformat()

                        payload = {
                            "categoryId": SEARCH_CATEGORY_ID,
                            "content": chunk,
                            "title": title,
                            "url": original_url,
                            "metadata": {
                                "id": article_id,
                                "publisher": publisher,
                                "chunk_index": i,
                                "total_chunks": len(chunks)
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
                            uploaded_doc_id = result.get("docId") or result.get("id") # Handle potential API response variation
                            
                            if i == 0:
                                first_doc_id = uploaded_doc_id
                            
                            logger.info(f"Uploaded chunk {i+1}/{len(chunks)} for article {article_id}")
                        else:
                            logger.error(f"Search API error for {article_id} chunk {i}: {response.status_code} - {response.text}")
                            all_chunks_uploaded = False
                            break # Stop uploading remaining chunks if one fails
                    
                    if all_chunks_uploaded and first_doc_id:
                        update_sql = """
                            UPDATE naver_news_articles
                            SET doc_id = %s
                            WHERE id = %s
                        """
                        cursor.execute(update_sql, (first_doc_id, article_id))
                        # Commit is handled at the end of logic or could be here? 
                        # Original code committed per article. Let's stick to that pattern but maybe batch commits are better?
                        # For safety, per article commit is fine for this scale.
                        conn.commit()
                        logger.info(f"Successfully uploaded all chunks for article {article_id}. Set doc_id to {first_doc_id}")
                    else:
                        logger.error(f"Failed to upload all chunks for article {article_id}. Rolled back.")
                        conn.rollback() # Rollback DB transaction (though passed API calls can't be rolled back)

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
    description='Upload full articles to Search API',
    schedule_interval='*/5 * * * *', 
    catchup=False,
    max_active_runs=1,
    tags=['news', 'search', 'upload'],
) as dag:

    upload_task = PythonOperator(
        task_id='upload_articles_batch',
        python_callable=upload_articles,
        provide_context=True,
    )
