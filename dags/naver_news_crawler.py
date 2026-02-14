from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.models.param import Param
from naver_news_crawler_utils import (
    fetch_article_list, 
    parse_article_list_html, 
    fetch_article_detail, 
    get_article_id,
    parse_naver_date
)
import time
import random
import logging

logger = logging.getLogger(__name__)

# Target Sections from the user request
SECTIONS = {
    "100": ["264", "265", "268", "266", "267", "269"],
    "101": ["259", "258", "261", "771", "260", "262", "310", "263"],
    "102": ["249", "250", "251", "254", "252", "59b", "255", "256", "276", "257"],
    "103": ["241", "239", "240", "237", "238", "376", "242", "243", "244", "248", "245"],
    "105": ["731", "226", "227", "230", "732", "283", "229", "228"],
    "104": ["231", "232", "233", "234", "322"]
}

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': datetime(2026, 2, 14),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

def crawl_naver_news_by_date(**kwargs):
    # Get date from dag_run parameters or use execution_date
    conf = kwargs.get('dag_run').conf
    target_date = conf.get('date', datetime.now().strftime('%Y%m%d'))
    
    pg_hook = PostgresHook(postgres_conn_id='postgres_default')
    
    for sid1, sid2_list in SECTIONS.items():
        for sid2 in sid2_list:
            logger.info(f"Starting crawl for section {sid1}/{sid2} on {target_date}")
            
            next_cursor = None
            page_no = 1
            total_added = 0
            
            while True:
                response_json = fetch_article_list(sid1, sid2, target_date, next_cursor, page_no)
                if not response_json or not response_json.get('renderedComponent'):
                    break
                
                html_content = response_json['renderedComponent'].get('SECTION_ARTICLE_LIST_FOR_LATEST')
                if not html_content:
                    break
                    
                articles = parse_article_list_html(html_content)
                if not articles:
                    break
                
                for article in articles:
                    naver_url = article['naver_url']
                    title = article['title']
                    article_id = get_article_id(naver_url)
                    
                    # Fetch Detail
                    detail = fetch_article_detail(naver_url)
                    if not detail:
                        continue
                        
                    # Insert into DB
                    sql = """
                    INSERT INTO naver_news_articles (
                        id, naver_url, original_url, title, publisher, article_date, section_id1, section_id2
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO NOTHING;
                    """
                    
                    parsed_date = parse_naver_date(detail['article_date'])
                    
                    pg_hook.run(sql, parameters=(
                        article_id,
                        naver_url,
                        detail['original_url'],
                        title,
                        detail['publisher'],
                        parsed_date,
                        sid1,
                        sid2
                    ))
                    total_added += 1
                
                # Check for next cursor
                next_cursor = response_json.get('next')
                if not next_cursor:
                    break
                
                page_no += 1
                # Respectful delay
                time.sleep(random.uniform(2, 4))
                
            logger.info(f"Finished section {sid1}/{sid2}. Added {total_added} articles.")


with DAG(
    'naver_news_crawler',
    default_args=default_args,
    description='Crawl Naver News articles by date and section',
    schedule_interval=None, # Manual trigger for specific dates
    catchup=False,
    tags=['news', 'naver', 'crawler'],
    params={
        "date": Param(
            default=datetime.now().strftime('%Y%m%d'),
            type="string",
            description="수집할 날짜 (YYYYMMDD 형식)"
        )
    },
) as dag:

    crawl_task = PythonOperator(
        task_id='crawl_task',
        python_callable=crawl_naver_news_by_date,
        provide_context=True,
    )
