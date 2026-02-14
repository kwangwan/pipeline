import requests
from bs4 import BeautifulSoup
import hashlib
import time
import random
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Constants
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
AJAX_URL = "https://news.naver.com/section/template/SECTION_ARTICLE_LIST_FOR_LATEST"

# Target Sections
SECTIONS = {
    "100": ["264", "265", "268", "266", "267", "269"],
    "101": ["259", "258", "261", "771", "260", "262", "310", "263"],
    "102": ["249", "250", "251", "254", "252", "59b", "255", "256", "276", "257"],
    "103": ["241", "239", "240", "237", "238", "376", "242", "243", "244", "248", "245"],
    "105": ["731", "226", "227", "230", "732", "283", "229", "228"],
    "104": ["231", "232", "233", "234", "322"]
}

def get_headers():
    return {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://news.naver.com/",
    }

def get_article_id(url):
    return hashlib.sha256(url.encode('utf-8')).hexdigest()

def fetch_article_list(sid, sid2, date, next_cursor=None, page_no=1):
    params = {
        "sid": sid,
        "sid2": sid2,
        "cluid": "",
        "pageNo": page_no,
        "date": date,
        "next": next_cursor if next_cursor else "",
        "_": int(time.time() * 1000)
    }
    
    try:
        response = requests.get(AJAX_URL, params=params, headers=get_headers(), timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Error fetching article list for {sid}/{sid2} on {date}: {e}")
        return None

def parse_article_list_html(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    articles = []
    
    # Each article is in a list item or div with class 'sa_item' or similar
    # Based on research, sa_item_inner contains the title and link
    items = soup.select('.sa_item')
    for item in items:
        title_tag = item.select_one('.sa_text_title')
        if not title_tag:
            continue
            
        naver_url = title_tag['href']
        title = title_tag.get_text(strip=True)
        
        articles.append({
            "naver_url": naver_url,
            "title": title
        })
        
    return articles

def fetch_article_detail(url):
    try:
        # Avoid too frequent requests
        time.sleep(random.uniform(1, 2))
        
        response = requests.get(url, headers=get_headers(), timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 1. Original Article URL
        original_url_tag = soup.select_one('.media_end_head_origin_link')
        original_url = original_url_tag['href'] if original_url_tag else None
        
        # 2. Article Date
        # Many patterns exist, common one is media_end_head_info_datestamp_time
        date_tag = soup.select_one('.media_end_head_info_datestamp_time')
        date_str = date_tag.get_text(strip=True) if date_tag else None
        # Format: 2024.02.14. 오후 2:16 (example) - parsing varies
        
        # 3. Publisher
        publisher_tag = soup.select_one('.media_end_head_top_logo img')
        publisher = publisher_tag['title'] if publisher_tag else None
        if not publisher:
            publisher_tag = soup.select_one('.media_end_head_top_logo p')
            publisher = publisher_tag.get_text(strip=True) if publisher_tag else None

        return {
            "original_url": original_url,
            "article_date": date_str,
            "publisher": publisher
        }
    except Exception as e:
        logger.error(f"Error fetching article detail for {url}: {e}")
        return None

def parse_naver_date(date_str):
    if not date_str:
        return None
    try:
        # Example: 2024.02.14. 오후 2:16
        # Or: 2024-02-14 14:16:11
        
        # Clean up the string
        clean_date = date_str.replace('.', '-')
        if "오후" in clean_date:
            clean_date = clean_date.replace("오후", "PM")
        elif "오전" in clean_date:
            clean_date = clean_date.replace("오전", "AM")
            
        # Try multiple formats
        formats = [
            "%Y-%m-%d- %p %I:%M", 
            "%Y-%m-%d %p %I:%M", 
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M"
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(clean_date.strip(), fmt)
            except:
                continue
        
        # If no format matches, try to just parse the date part if it looks like ISO
        try:
            return datetime.fromisoformat(clean_date.strip())
        except:
            pass
            
        return None
    except:
        return None

from airflow.providers.postgres.hooks.postgres import PostgresHook

def crawl_all_sections_for_date(target_date, postgres_conn_id='postgres_default'):
    pg_hook = PostgresHook(postgres_conn_id=postgres_conn_id)
    
    total_added_all = 0
    
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
                    
                    # Fallback to target_date if parsing failed or date is missing
                    if not parsed_date:
                        try:
                            # target_date is in YYYYMMDD format
                            parsed_date = datetime.strptime(target_date, '%Y%m%d')
                            logger.info(f"Falling back to target_date {target_date} for article: {naver_url}")
                        except Exception as e:
                            logger.error(f"Failed to create fallback date from {target_date}: {e}")
                            parsed_date = None

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
            total_added_all += total_added
            
    return total_added_all
