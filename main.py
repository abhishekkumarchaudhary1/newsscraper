from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client
import os
from dotenv import load_dotenv

from scraper import run_scraper

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SCRAPER_API_KEY = os.getenv("SCRAPER_API_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

app = FastAPI(
    title="News Scraper API",
    description="API that scrapes and serves latest news from Times of India",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def home():
    return {
        "status": "success",
        "message": "News Scraper API is running",
        "endpoints": {
            "/news": "GET — articles (trending first, then headlines; ordered by scrape)",
            "/scrape": "GET — trigger scraper (requires API key)",
            "/docs": "GET — interactive API documentation",
        }
    }


@app.get("/news")
def get_news():
    try:
        response = (
            supabase
            .table("articles")
            .select("*")
            .order("scrape_order")
            .limit(100)
            .execute()
        )

        return {
            "status": "success",
            "count": len(response.data),
            "data": response.data
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/scrape")
def trigger_scrape(api_key: str = Query(None), x_api_key: str = Header(None)):
    key = x_api_key or api_key
    if key != SCRAPER_API_KEY:
        raise HTTPException(status_code=403, detail="Forbidden — invalid or missing API key")

    run_scraper()
    return {"status": "success", "message": "Scraping complete"}