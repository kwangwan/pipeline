from datetime import datetime, timedelta
import logging
import sys
import subprocess
import time
import trafilatura

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

def collect_news_content(**kwargs):
    pg_hook = PostgresHook(postgres_conn_id='postgres_default')
    conn = pg_hook.get_conn()
    cursor = conn.cursor()
    
    # Configuration
    BATCH_SIZE = 100
    
    while True:
        # 1. Lock articles to process
        # We look for PENDING articles OR PROCESSING articles that have been stuck for > 1 hour
        # Use explicit transaction for locking
        try:
            select_sql = """
                WITH locked_rows AS (
                    SELECT id
                    FROM naver_news_articles
                    WHERE collection_status = 'PENDING'
                       OR (collection_status = 'PROCESSING' AND locked_at < NOW() - INTERVAL '1 hour')
                    ORDER BY article_date DESC
                    LIMIT %s
                    FOR UPDATE SKIP LOCKED
                )
                UPDATE naver_news_articles
                SET collection_status = 'PROCESSING',
                    locked_at = NOW(),
                    fail_reason = NULL
                WHERE id IN (SELECT id FROM locked_rows)
                RETURNING id, naver_url;
            """
            
            cursor.execute(select_sql, (BATCH_SIZE,))
            rows = cursor.fetchall()
            conn.commit() # Commit the lock status so other workers don't see them
            
            if not rows:
                logger.info("No more articles found to collect. Finishing task.")
                break

            logger.info(f"Locked {len(rows)} articles for processing.")
            
        except Exception as e:
            logger.error(f"Error locking rows: {e}")
            conn.rollback()
            raise

        # 2. Process each article batch
        processed_count = 0
        
        for row in rows:
            article_id, url = row
            try:
                # Add delay to be polite
                time.sleep(0.5)
                
                downloaded = trafilatura.fetch_url(url)
                
                if downloaded:
                    # Use bare_extraction for metadata + content
                    data = trafilatura.bare_extraction(
                        downloaded,
                        include_comments=False,
                        include_tables=False,
                        no_fallback=False
                    )
                    
                    if data and data.text:
                        content = data.text
                        
                        update_sql = """
                            UPDATE naver_news_articles
                            SET content = %s,
                                collection_status = 'COMPLETED',
                                locked_at = NULL,
                                fail_reason = NULL
                            WHERE id = %s
                        """
                        cursor.execute(update_sql, (content, article_id))
                        conn.commit()
                        processed_count += 1
                    else:
                        raise Exception("Empty content extracted or no data returned")
                else:
                    raise Exception("Failed to download URL (fetch_url returned None)")
                    
            except Exception as e:
                logger.error(f"Error processing {article_id}: {e}")
                fail_reason = str(e)[:255] # Truncate error message
                
                try:
                    fail_sql = """
                        UPDATE naver_news_articles
                        SET collection_status = 'FAILED',
                            fail_reason = %s,
                            locked_at = NULL
                        WHERE id = %s
                    """
                    cursor.execute(fail_sql, (fail_reason, article_id))
                    conn.commit()
                except Exception as db_e:
                     logger.error(f"Failed to update failure status for {article_id}: {db_e}")
                     conn.rollback()

        logger.info(f"Batch processing complete. Successfully collected {processed_count}/{len(rows)} articles. Checking for more...")

    cursor.close()
    conn.close()

from airflow.operators.trigger_dagrun import TriggerDagRunOperator

with DAG(
    'naver_news_content_collector_dag',
    default_args=default_args,
    description='Collect article content using Trafilatura',
    schedule_interval='*/10 * * * *', # Run every 10 minutes
    catchup=False,
    max_active_runs=2, # Limit to 2 concurrent bots as requested
    tags=['news', 'naver', 'content'],
) as dag:

    collect_task = PythonOperator(
        task_id='collect_content_batch',
        python_callable=collect_news_content,
        provide_context=True,
    )

    trigger_summarizer = TriggerDagRunOperator(
        task_id='trigger_naver_news_summarizer',
        trigger_dag_id='naver_news_summarizer_dag',
        wait_for_completion=False,
    )

    collect_task >> trigger_summarizer
