from fastapi import FastAPI, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

app = FastAPI(title="News Collection Dashboard API")

origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health_check():
    return {"status": "ok"}

def build_filter_clause(
    publisher: Optional[str] = None,
    section: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> (str, Dict[str, Any]):
    conditions = []
    params = {}

    if publisher:
        conditions.append("publisher = :publisher")
        params["publisher"] = publisher
    if section:
        conditions.append("section_id1 = :section")
        params["section"] = section
    if start_date:
        conditions.append("created_at >= :start_date")
        params["start_date"] = start_date
    if end_date:
        # Assuming end_date encompasses the whole day, add 1 day or use <= combined with time
        conditions.append("created_at <= :end_date")
        params["end_date"] = end_date

    clause = " AND ".join(conditions)
    if clause:
        clause = "WHERE " + clause
    else:
        # Default time window if no specific date range is provided to avoid querying everything
        if not start_date and not end_date:
             clause = "WHERE created_at >= NOW() - INTERVAL '30 days'"
        else:
             clause = "" # start or end provided, trust the user input
    
    return clause, params

@app.get("/stats/summary")
def get_summary(
    publisher: Optional[str] = None,
    section: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db)
):
    where_clause, params = build_filter_clause(publisher, section, start_date, end_date)
    
    # Total count
    # Success count (collection_status = 'COMPLETED' or similar, schema says 'PENDING' default. 
    # Let's assume 'COMPLETED' or fail_reason IS NULL as success for now, or check distinct statuses)
    # Checking schema: collection_status String? @default("PENDING")
    
    query = text(f"""
        SELECT 
            count(*) as total,
            count(*) FILTER (WHERE collection_status = 'COMPLETED') as success,
            count(*) FILTER (WHERE collection_status = 'FAILED' OR fail_reason IS NOT NULL) as failed
        FROM naver_news_articles
        {where_clause}
    """)
    
    result = db.execute(query, params).fetchone()
    return {
        "total": result[0],
        "success": result[1],
        "failed": result[2]
    }

@app.get("/stats/trend")
def get_trend(
    period: str = Query("daily", enum=["daily", "hourly"]), 
    publisher: Optional[str] = None,
    section: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db)
):
    where_clause, params = build_filter_clause(publisher, section, start_date, end_date)
    
    trunc_date = 'hour' if period == 'hourly' else 'day'
    
    query = text(f"""
        SELECT date_trunc(:trunc, created_at) as time, count(*) 
        FROM naver_news_articles 
        {where_clause}
        GROUP BY time 
        ORDER BY time ASC
    """)
    
    params["trunc"] = trunc_date
    result = db.execute(query, params).fetchall()
    return [{"time": str(row[0]), "count": row[1]} for row in result]

@app.get("/stats/publisher")
def get_publisher_stats(
    section: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db)
):
    where_clause, params = build_filter_clause(None, section, start_date, end_date)
    if where_clause:
        where_clause += " AND publisher IS NOT NULL"
    else:
        where_clause = "WHERE publisher IS NOT NULL"

    query = text(f"""
        SELECT publisher, count(*) as count
        FROM naver_news_articles
        {where_clause}
        GROUP BY publisher
        ORDER BY count DESC
        LIMIT 20
    """)
    result = db.execute(query, params).fetchall()
    return [{"publisher": row[0], "count": row[1]} for row in result]

@app.get("/stats/section")
def get_section_stats(
    publisher: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db)
):
    where_clause, params = build_filter_clause(publisher, None, start_date, end_date)
    if where_clause:
        where_clause += " AND section_id1 IS NOT NULL"
    else:
         where_clause = "WHERE section_id1 IS NOT NULL"

    query = text(f"""
        SELECT section_id1, count(*) as count
        FROM naver_news_articles
        {where_clause}
        GROUP BY section_id1
        ORDER BY count DESC
    """)
    result = db.execute(query, params).fetchall()
    return [{"section": row[0], "count": row[1]} for row in result]

@app.get("/filters")
def get_filters(db: Session = Depends(get_db)):
    pub_query = text("SELECT DISTINCT publisher FROM naver_news_articles WHERE publisher IS NOT NULL ORDER BY publisher")
    sec_query = text("SELECT DISTINCT section_id1 FROM naver_news_articles WHERE section_id1 IS NOT NULL ORDER BY section_id1")
    
    pubs = db.execute(pub_query).fetchall()
    secs = db.execute(sec_query).fetchall()
    
    return {
        "publishers": [row[0] for row in pubs],
        "sections": [row[0] for row in secs]
    }
