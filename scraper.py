import re
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


def absolute_url(href: str) -> str:
    href = href.strip()
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        return BASE_URL + href
    return f"{BASE_URL}/{href}"


def clean_trending_title(text: str) -> str:
    """Strip TOI section labels glued to the headline (e.g. 'Trending', 'IPL Top Stories')."""
    s = text.strip()
    changed = True
    while changed:
        changed = False
        for prefix in ("Trending", "IPL Top Stories", "Top Stories"):
            if s.startswith(prefix):
                s = s[len(prefix) :].strip()
                changed = True
                break
    s = re.sub(r"\s+", " ", s)
    return s


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


def collect_trending_skeletons():
    """Homepage carousel labeled 'Trending' (ul.hozxP containing the Trending badge)."""
    res = requests.get(BASE_URL + "/", headers=HEADERS, timeout=10)
    soup = BeautifulSoup(res.text, "html.parser")

    trending_ul = None
    for ul in soup.select("ul.hozxP"):
        if ul.find("div", string="Trending"):
            trending_ul = ul
            break

    out = []
    if not trending_ul:
        return out

    for li in trending_ul.find_all("li", recursive=False):
        a = li.find("a", href=True)
        if not a:
            continue
        title = clean_trending_title(a.get_text(strip=True))
        if not title:
            continue
        url = absolute_url(a["href"])
        if "indiatimes.com" not in url:
            continue
        out.append({"title": title, "url": url, "feed_section": "trending"})
    return out


def collect_headline_skeletons():
    url = f"{BASE_URL}/home/headlines"
    res = requests.get(url, headers=HEADERS, timeout=10)
    soup = BeautifulSoup(res.text, "html.parser")

    articles = soup.select("div.top-newslist li")
    out = []

    for block in articles:
        link_tag = block.find("a")
        if not link_tag or not link_tag.get("href"):
            continue

        title = link_tag.get_text(strip=True)
        full_link = absolute_url(link_tag["href"])
        out.append({"title": title, "url": full_link, "feed_section": "headlines"})

    return out


def merge_skeletons(trending, headlines):
    """Trending first; skip headline rows whose URL already appeared in trending."""
    seen = set()
    merged = []
    for row in trending:
        u = row["url"]
        if u not in seen:
            seen.add(u)
            merged.append(row)
    for row in headlines:
        u = row["url"]
        if u not in seen:
            seen.add(u)
            merged.append(row)
    return merged


def scrape_toi():
    try:
        trending = collect_trending_skeletons()
        headlines = collect_headline_skeletons()
        merged = merge_skeletons(trending, headlines)

        rows = []
        for order, sk in enumerate(merged):
            content, description, image_url = get_article_content(sk["url"])
            rows.append(
                {
                    "title": sk["title"],
                    "description": description,
                    "content": content,
                    "url": sk["url"],
                    "image_url": image_url,
                    "source": "Times of India",
                    "published_at": datetime.now(IST).isoformat(),
                    "feed_section": sk["feed_section"],
                    "scrape_order": order,
                }
            )

        supabase.table("articles").delete().not_.is_("id", None).execute()

        if rows:
            supabase.table("articles").insert(rows).execute()
            for r in rows:
                print(f"[{r['feed_section']}] {r['title']}")
        else:
            print("No articles found; table cleared.")

    except Exception as e:
        print(f"Scraping failed: {e}")


def run_scraper():
    scrape_toi()


if __name__ == "__main__":
    run_scraper()
