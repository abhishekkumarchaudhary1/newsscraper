from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client
import os
from dotenv import load_dotenv

from scraper import run_scraper

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


@app.get("/")
def home():
    return {"message": "News API running"}


@app.get("/news")
def get_news():
    try:
        response = (
            supabase
            .table("articles")
            .select("*")
            .order("published_at", desc=True)
            .limit(20)
            .execute()
        )

        return response.data

    except Exception as e:
        return {"error": str(e)}

@app.get("/scrape")
def trigger_scrape():
    run_scraper()
    return {"message": "Scraping done"}