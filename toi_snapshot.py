"""
Scrape TOI weather, AQI, gold, and silver for configured cities (Delhi, Mumbai).
HTML/CSS on TOI changes often — this module may need selector updates.

Supabase (run once in SQL editor):

  create table if not exists toi_snapshot (
    id smallint primary key default 1,
    snapshot jsonb not null,
    updated_at text
  );
"""

from __future__ import annotations

import re
from datetime import datetime, timezone, timedelta
from typing import Any

import requests
from bs4 import BeautifulSoup

IST = timezone(timedelta(hours=5, minutes=30))

BASE = "https://timesofindia.indiatimes.com"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# Paths are TOI-specific IDs in the URL — if links break, update from the live site.
CITIES: list[dict[str, str]] = [
    {
        "key": "delhi",
        "label": "New Delhi",
        "weather_path": "/weather/new-delhi-weather-forecast-today/3291",
        "aqi_path": "/weather/new-delhi-aqi-level-air-quality-index-today/3291",
        "gold_slug": "gold-price-in-delhi",
        "silver_slug": "silver-price-in-delhi",
    },
    {
        "key": "mumbai",
        "label": "Mumbai",
        "weather_path": "/weather/mumbai-weather-forecast-today/3258",
        "aqi_path": "/weather/mumbai-aqi-level-air-quality-index-today/3258",
        "gold_slug": "gold-price-in-mumbai",
        "silver_slug": "silver-price-in-mumbai",
    },
]


def _get(path: str) -> str:
    url = path if path.startswith("http") else BASE + path
    r = requests.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    return r.text


def _parse_num(s: str) -> float | None:
    s = s.replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def parse_weather_temps(html: str) -> dict[str, float | None]:
    soup = BeautifulSoup(html, "html.parser")
    sec = soup.find("section", class_="jolbV")
    if not sec:
        return {"temp_max_c": None, "temp_min_c": None}
    t = sec.get_text(" | ", strip=True)
    mx = re.search(r"Max\.?\s*Temp\.?\s*\|\s*([\d.]+)", t)
    mn = re.search(r"Min\.?\s*Temp\.?\s*\|\s*([\d.]+)", t)
    return {
        "temp_max_c": float(mx.group(1)) if mx else None,
        "temp_min_c": float(mn.group(1)) if mn else None,
    }


def parse_aqi_bundle(html: str) -> dict[str, int | None]:
    """First hourly componentMap on the AQI page (embedded JSON in HTML)."""
    aqi_us = re.search(r'"aqi":\{"sensorName":"aqi","sensorData":(\d+)', html)
    aqi_in = re.search(r'"AQI-IN":\{"sensorName":"AQI-IN","sensorData":(\d+)', html)
    pm25 = re.search(r'"pm25":\{"sensorName":"pm25","sensorData":(\d+)', html)
    temp = re.search(r'"t":\{"sensorName":"t","sensorData":(\d+)', html)
    return {
        "aqi_us": int(aqi_us.group(1)) if aqi_us else None,
        "aqi_in": int(aqi_in.group(1)) if aqi_in else None,
        "pm25_ug_m3": int(pm25.group(1)) if pm25 else None,
        "aqi_page_temp_c": int(temp.group(1)) if temp else None,
    }


def parse_gold_city_page(html: str) -> dict[str, str | float | None]:
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("div.fCMra")
    header_idx = None
    for i, row in enumerate(rows):
        txt = row.get_text(" | ", strip=True)
        if "Date" in txt and "22K" in txt and "24K" in txt:
            header_idx = i
            break
    if header_idx is None or header_idx + 1 >= len(rows):
        return {"gold_22k_per_gm": None, "gold_24k_per_gm": None}
    data = rows[header_idx + 1].get_text(" | ", strip=True)
    parts = [p.strip() for p in data.split("|")]
    # e.g. 4th Apr 2026 | 13,851 | ₹ 1 | 15,109 | ₹ 1
    if len(parts) < 4:
        return {"gold_22k_per_gm": None, "gold_24k_per_gm": None}
    v22 = _parse_num(parts[1])
    v24 = _parse_num(parts[3])
    return {
        "gold_22k_per_gm": v22,
        "gold_24k_per_gm": v24,
    }


def parse_silver_city_page(html: str) -> dict[str, float | None]:
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("div.fCMra")
    silver_gm: float | None = None
    silver_10g: float | None = None

    for row in rows:
        txt = row.get_text(" | ", strip=True)
        parts = [p.strip() for p in txt.split("|")]
        if not parts:
            continue
        head = parts[0]
        if "Rate" in head and any(m in head for m in ("Apr", "Mar", "Feb", "Jan", "May", "Jun")):
            if len(parts) >= 3:
                # Multiple rows (e.g. 1st April vs 4th April) — last row is usually the latest rate
                silver_gm = _parse_num(parts[1])
                silver_10g = _parse_num(parts[2])

    if silver_gm is None:
        for i, row in enumerate(rows):
            txt = row.get_text(" | ", strip=True)
            if "Date" in txt and "Price/100gm" in txt and i + 1 < len(rows):
                parts = [p.strip() for p in rows[i + 1].get_text(" | ", strip=True).split("|")]
                if len(parts) >= 2:
                    p100 = _parse_num(parts[1])
                    if p100 is not None:
                        silver_gm = round(p100 / 100.0, 2)
                break

    return {"silver_per_gm": silver_gm, "silver_per_10gm": silver_10g}


def build_city_snapshot(cfg: dict[str, str]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "key": cfg["key"],
        "label": cfg["label"],
    }
    try:
        whtml = _get(cfg["weather_path"])
        out.update(parse_weather_temps(whtml))
    except Exception as e:
        out["weather_error"] = str(e)

    try:
        ahtml = _get(cfg["aqi_path"])
        out.update(parse_aqi_bundle(ahtml))
    except Exception as e:
        out["aqi_error"] = str(e)

    try:
        ghtml = _get(f"/business/gold-rates-today/{cfg['gold_slug']}")
        out.update(parse_gold_city_page(ghtml))
    except Exception as e:
        out["gold_error"] = str(e)

    try:
        shtml = _get(f"/business/silver-rates-today/{cfg['silver_slug']}")
        out.update(parse_silver_city_page(shtml))
    except Exception as e:
        out["silver_error"] = str(e)

    return out


def fetch_snapshot() -> dict[str, Any]:
    cities = []
    for cfg in CITIES:
        cities.append(build_city_snapshot(cfg))
    return {
        "updated_at": datetime.now(IST).isoformat(),
        "source": "Times of India (scraped)",
        "cities": cities,
    }


def persist_snapshot(supabase) -> dict[str, Any] | None:
    """Store latest snapshot in table `toi_snapshot` (id=1). Returns payload or None on failure."""
    data = fetch_snapshot()
    try:
        supabase.table("toi_snapshot").upsert(
            {
                "id": 1,
                "snapshot": data,
                "updated_at": data["updated_at"],
            }
        ).execute()
        return data
    except Exception as e:
        print(f"toi_snapshot persist failed (create table toi_snapshot?): {e}")
        return None
