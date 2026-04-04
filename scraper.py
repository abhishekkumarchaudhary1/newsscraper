import requests
from bs4 import BeautifulSoup
from supabase import create_client
import os
from dotenv import load_dotenv
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "en-US,en;q=0.9"
}


BASE_URL = "https://timesofindia.indiatimes.com"


def get_article_content(url):
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")

        meta_desc = soup.find("meta", attrs={"name": "description"})
        description = meta_desc["content"].strip() if meta_desc and meta_desc.get("content") else None

        og_image = soup.find("meta", property="og:image")
        image_url = og_image["content"].strip() if og_image and og_image.get("content") else None

        paragraphs = soup.select("div._s30J.clearfix p")
        content = " ".join([p.get_text(strip=True) for p in paragraphs])

        if not description and content:
            description = content[:200]

        return content if content else None, description, image_url

    except Exception as e:
        print(f"Error fetching content: {e}")
        return None, None, None


def scrape_toi():
    try:
        url = f"{BASE_URL}/home/headlines"
        res = requests.get(url, headers=HEADERS, timeout=10)

        soup = BeautifulSoup(res.text, "html.parser")

        articles = soup.select("div.top-newslist li")
        rows = []

        for a in articles:
            link_tag = a.find("a")

            if not link_tag or not link_tag.get("href"):
                continue

            title = link_tag.get_text(strip=True)
            relative_link = link_tag["href"]
            full_link = BASE_URL + relative_link

            content, description, image_url = get_article_content(full_link)

            rows.append({
                "title": title,
                "description": description,
                "content": content,
                "url": full_link,
                "image_url": image_url,
                "source": "Times of India",
                "published_at": datetime.now(IST).isoformat()
            })

        # Replace entire table with this run's headlines (PostgREST requires a filter on delete)
        supabase.table("articles").delete().not_.is_("id", None).execute()

        if rows:
            supabase.table("articles").insert(rows).execute()
            for r in rows:
                print(f"Inserted: {r['title']}")
        else:
            print("No articles found; table cleared.")

    except Exception as e:
        print(f"Scraping failed: {e}")


def run_scraper():
    scrape_toi()


if __name__ == "__main__":
    run_scraper()