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
    end_date: Optional[str] = None,
    date_field: str = "created_at",
    timezone: str = "UTC"
) -> (str, Dict[str, Any], str):
    conditions = []
    params = {"tz": timezone}

    # Define how to access the localized version of the date field
    if date_field == "created_at":
        # created_at is stored in UTC
        localized_field = f"({date_field} AT TIME ZONE 'UTC' AT TIME ZONE :tz)"
    else:
        # article_date is naive but represents KST (Asia/Seoul)
        localized_field = f"({date_field} AT TIME ZONE 'Asia/Seoul' AT TIME ZONE :tz)"

    if publisher:
        conditions.append("publisher = :publisher")
        params["publisher"] = publisher
    if section:
        conditions.append("section_id1 = :section")
        params["section"] = section
    if start_date:
        conditions.append(f"{localized_field}::date >= :start_date")
        params["start_date"] = start_date
    if end_date:
        conditions.append(f"{localized_field}::date <= :end_date")
        params["end_date"] = end_date

    clause = " AND ".join(conditions)
    if clause:
        clause = "WHERE " + clause
    else:
        # Default time window if no specific date range is provided to avoid querying everything
        if not start_date and not end_date and date_field == "created_at":
             clause = f"WHERE {localized_field} >= (NOW() AT TIME ZONE :tz) - INTERVAL '30 days'"
        else:
             clause = ""
    
    return clause, params, localized_field

@app.get("/stats/summary")
def get_summary(
    publisher: Optional[str] = None,
    section: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    timezone: str = Query("UTC"),
    db: Session = Depends(get_db)
):
    where_clause, params, _ = build_filter_clause(publisher, section, start_date, end_date, timezone=timezone)
    
    query = text(f"""
        SELECT 
            count(*) as total,
            count(*) FILTER (WHERE collection_status = 'COMPLETED') as success,
            count(*) FILTER (WHERE collection_status = 'FAILED' OR fail_reason IS NOT NULL) as failed,
            count(*) FILTER (WHERE collection_status = 'COMPLETED') as collected,
            count(*) FILTER (WHERE doc_id IS NOT NULL) as uploaded
        FROM naver_news_articles
        {where_clause}
    """)
    
    result = db.execute(query, params).fetchone()
    return {
        "total": result[0],
        "success": result[1],
        "failed": result[2],
        "collected": result[3],
        "uploaded": result[4]
    }

@app.get("/stats/trend")
def get_trend(
    period: str = Query("daily", enum=["daily", "hourly"]), 
    date_field: str = Query("created_at", enum=["created_at", "article_date"]),
    publisher: Optional[str] = None,
    section: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    timezone: str = Query("UTC"),
    db: Session = Depends(get_db)
):
    where_clause, params, localized_field = build_filter_clause(publisher, section, start_date, end_date, date_field, timezone)
    
    trunc_date = 'hour' if period == 'hourly' else 'day'
    
    query = text(f"""
        SELECT date_trunc(:trunc, {localized_field}) as time, count(*) 
        FROM naver_news_articles 
        {where_clause}
        {"AND" if where_clause else "WHERE"} {date_field} IS NOT NULL
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
    timezone: str = Query("UTC"),
    db: Session = Depends(get_db)
):
    where_clause, params, _ = build_filter_clause(None, section, start_date, end_date, timezone=timezone)
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
    timezone: str = Query("UTC"),
    db: Session = Depends(get_db)
):
    where_clause, params, _ = build_filter_clause(publisher, None, start_date, end_date, timezone=timezone)
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
@app.post("/articles/reset-failed")
def reset_failed_articles(db: Session = Depends(get_db)):
    try:
        query = text("UPDATE naver_news_articles SET collection_status = 'PENDING', fail_reason = NULL WHERE collection_status = 'FAILED' OR fail_reason IS NOT NULL")
        db.execute(query)
        db.commit()
        return {"status": "success", "message": "Failed articles have been reset to PENDING"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
