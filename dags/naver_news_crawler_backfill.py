from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.models.param import Param
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '../plugins'))

try:
    from naver_news_crawler_utils import crawl_all_sections_for_date
except ImportError:
    from plugins.naver_news_crawler_utils import crawl_all_sections_for_date
import logging

logger = logging.getLogger(__name__)

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': datetime(2026, 2, 14),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 0,
}

def crawl_backfill(**kwargs):
    params = kwargs.get('params', {})
    start_date_str = params.get('start_date')
    end_date_str = params.get('end_date')
    
    if not start_date_str or not end_date_str:
        raise ValueError("Both start_date and end_date must be provided.")
        
    start_date = datetime.strptime(start_date_str, '%Y%m%d')
    end_date = datetime.strptime(end_date_str, '%Y%m%d')
    
    if start_date > end_date:
        raise ValueError(f"start_date ({start_date_str}) cannot be after end_date ({end_date_str})")
        
    # Generate list of dates from end_date down to start_date
    current_date = end_date
    while current_date >= start_date:
        target_date_str = current_date.strftime('%Y%m%d')
        logger.info(f"Backfill crawl for {target_date_str}")
        
        crawl_all_sections_for_date(target_date_str)
        
        current_date -= timedelta(days=1)

with DAG(
    'naver_news_crawler_backfill',
    default_args=default_args,
    description='Crawl Naver News articles for a specific date range (Backfill)',
    schedule_interval=None,
    catchup=False,
    tags=['news', 'naver', 'crawler', 'backfill'],
    params={
        "start_date": Param(
            default=(datetime.now() - timedelta(days=7)).strftime('%Y%m%d'),
            type="string",
            description="Start Date (YYYYMMDD) - Earliest date to crawl"
        ),
        "end_date": Param(
            default=datetime.now().strftime('%Y%m%d'),
            type="string",
            description="End Date (YYYYMMDD) - Latest date to crawl"
        )
    },
) as dag:

    crawl_task = PythonOperator(
        task_id='crawl_range',
        python_callable=crawl_backfill,
        provide_context=True,
    )
