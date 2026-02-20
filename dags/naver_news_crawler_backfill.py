from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.models.param import Param
import pytz
import time
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

def wait_if_outside_window():
    """
    Check if the current time is within 10:00 AM - 10:00 PM KST.
    If not, sleep until the next 10:00 AM KST.
    """
    kst = pytz.timezone('Asia/Seoul')
    
    while True:
        now_kst = datetime.now(kst)
        hour = now_kst.hour
        
        # Window: 10:00:00 to 21:59:59 (10 AM to 10 PM)
        if 10 <= hour < 22:
            logger.info(f"Current time {now_kst.strftime('%Y-%m-%d %H:%M:%S')} is within the window. Proceeding.")
            break
        
        # Calculate when the next 10:00 AM is
        if hour >= 22:
            # Tomorrow 10 AM
            next_start = (now_kst + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
        else:
            # Today 10 AM
            next_start = now_kst.replace(hour=10, minute=0, second=0, microsecond=0)
            
        wait_seconds = (next_start - now_kst).total_seconds()
        logger.info(f"Current time {now_kst.strftime('%Y-%m-%d %H:%M:%S')} is OUTSIDE the window (10:00-22:00 KST).")
        logger.info(f"Pausing execution. Will resume at {next_start.strftime('%Y-%m-%d %H:%M:%S')} (in {wait_seconds/3600:.2f} hours).")
        
        # Sleep in chunks or at once. For long waits, sleep in 10-minute chunks to stay responsive to Airflow if needed.
        # But for simplicity, we sleep the whole duration.
        time.sleep(wait_seconds + 5) # Buffer 5 seconds

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
        # Check time window before each date
        wait_if_outside_window()
        
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
