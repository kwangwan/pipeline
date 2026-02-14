from datetime import datetime, timedelta
import logging
import sys
import subprocess
import time

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

def install_trafilatura():
    """Dynamically install trafilatura if not present."""
    try:
        import trafilatura
        logger.info("trafilatura is already installed.")
    except ImportError:
        logger.info("trafilatura not found. Installing...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "trafilatura"])
            logger.info("trafilatura installed successfully.")
        except Exception as e:
            logger.error(f"Failed to install trafilatura: {e}")
            raise

def collect_news_content(**kwargs):
    # Ensure dependencies are installed
    install_trafilatura()
    import trafilatura
    
    pg_hook = PostgresHook(postgres_conn_id='postgres_default')
    conn = pg_hook.get_conn()
    cursor = conn.cursor()
    
    # Configuration
    BATCH_SIZE = 100
    
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
            logger.info("No articles found to collect.")
            return

        logger.info(f"Locked {len(rows)} articles for processing.")
        
    except Exception as e:
        logger.error(f"Error locking rows: {e}")
        conn.rollback()
        raise

    # 2. Process each article
    # We process in a loop. Since we already marked them as PROCESSING and committed, 
    # we can take our time. If we crash, they stay PROCESSING until timeout.
    
    processed_count = 0
    
    try:
        for row in rows:
            article_id, url = row
            # logger.info(f"Processing article {article_id}: {url}")
            
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
                    
                    if data and data.get('text'):
                        content = data.get('text')
                        title_extracted = data.get('title')
                        reporter_name = data.get('author')
                        
                        update_sql = """
                            UPDATE naver_news_articles
                            SET content = %s,
                                title_extracted = %s,
                                reporter_name = %s,
                                collection_status = 'COMPLETED',
                                locked_at = NULL,
                                fail_reason = NULL
                            WHERE id = %s
                        """
                        cursor.execute(update_sql, (content, title_extracted, reporter_name, article_id))
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

        logger.info(f"Batch processing complete. Successfully collected {processed_count}/{len(rows)} articles.")
        
    finally:
        cursor.close()
        conn.close()

with DAG(
    'naver_news_content_collector_dag',
    default_args=default_args,
    description='Collect article content using Trafilatura',
    schedule_interval='*/10 * * * *', # Run every 10 minutes
    catchup=False,
    max_active_runs=3, # Allow multiple concurrent runs since we have locking
    tags=['news', 'naver', 'content'],
) as dag:

    collect_task = PythonOperator(
        task_id='collect_content_batch',
        python_callable=collect_news_content,
        provide_context=True,
    )
