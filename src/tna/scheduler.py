"""Production scheduling"""
import asyncio
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler

async def schedule_jobs(store: SQLiteStore):
    """Daily cron jobs"""
    scheduler = AsyncIOScheduler()
    
    # Daily: 9:55am ET - Pre-decision news ingest
    scheduler.add_job(
        ingest_news_cron, 
        'cron', hour=9, minute=55, timezone='America/New_York',
        args=(store,)
    )
    
    # Daily: 4:05pm ET - EOD price ingest + reporting
    scheduler.add_job(
        eod_pipeline, 
        'cron', hour=16, minute=5, timezone='America/New_York',
        args=(store,)
    )
    
    scheduler.start()
    print("⏰ Scheduler started")

async def ingest_news_cron(store):
    """Fresh news before 10am decision"""
    print("📰 Cron: News ingest")
    # Call your news ingest

async def eod_pipeline(store):
    """End-of-day pipeline"""
    print("📈 Cron: EOD pipeline")
    # Ingest prices, generate features, retrain model monthly
