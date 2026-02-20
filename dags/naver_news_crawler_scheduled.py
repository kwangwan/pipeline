from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.timezone import make_aware

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '../plugins'))

try:
    from naver_news_crawler_utils import crawl_all_sections_for_date
except ImportError:
    from plugins.naver_news_crawler_utils import crawl_all_sections_for_date
import logging
import pytz

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

def crawl_scheduled(**kwargs):
    # Determine execution date (logical date)
    # dag_run = kwargs.get('dag_run')
    # execution_date = kwargs.get('execution_date') # Deprecated in newer Airflow, use logical_date or data_interval_start
    
    # We want "Today" and "Yesterday" based on KST relative to when this runs
    # If run at 2026-02-14 10:00 KST, we want 20260214 and 20260213
    
    kst = pytz.timezone('Asia/Seoul')
    now_kst = datetime.now(kst)
    
    today_str = now_kst.strftime('%Y%m%d')
    yesterday_str = (now_kst - timedelta(days=1)).strftime('%Y%m%d')
    
    logger.info(f"Scheduled crawl for {today_str} (Today) and {yesterday_str} (Yesterday)")
    
    # Crawl Today
    crawl_all_sections_for_date(today_str)
    
    # Crawl Yesterday
    crawl_all_sections_for_date(yesterday_str)

with DAG(
    'naver_news_crawler_scheduled',
    default_args=default_args,
    description='Crawl Naver News articles for Today and Yesterday',
    schedule_interval='0 12 * * *', # At 12:00 PM daily
    catchup=False,
    max_active_runs=1,
    tags=['news', 'naver', 'crawler', 'scheduled'],
) as dag:

    crawl_task = PythonOperator(
        task_id='crawl_today_and_yesterday',
        python_callable=crawl_scheduled,
        provide_context=True,
    )
