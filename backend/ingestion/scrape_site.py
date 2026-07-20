"""
ingestion/scrape_site.py
--------------------------
Crawls the official N+ONE DATACENTERS website and saves each page's main
content as a clean Markdown file under knowledge_base/raw/, ready to be
picked up by ingest.py.

Design decision:
    We keep scraping and indexing as two separate scripts (Single
    Responsibility): scraping is slow, network-dependent, and only needs to
    run when the website content changes; indexing (embeddings + FAISS) is
    the part that should be re-run frequently during development without
    hitting the live site every time.

Usage:
    python ingestion/scrape_site.py
    python ingestion/scrape_site.py --url https://nplusone.africa/about/
"""
import argparse
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://nplusone.africa/"
OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "knowledge_base" / "raw"

# Pages worth indexing (curated instead of a blind crawl, to avoid indexing
# WordPress tag/category/pagination noise and keep the knowledge base clean).
SEED_PATHS = [
    "",
    "about/",
    "sustainability/",
    "carrier-neutrality/",
    "operational-excellence/",
    "security-compliance/",
    "ai-ready-datacenter/",
    "newsroom/",
    "datacenters-facilities/",
    "morocco-datacenter/",
    "senegal-datacenter/",
    "ivory-coast-datacenters/",
    "services/",
    "colocation/",
    "hyperscalers/",
    "business-continuity/",
    "support/",
    "partners/",
    "career/",
    "contact-us/",
]

HEADERS = {"User-Agent": "NpOneCopilotBot/1.0 (+https://nplusone.africa)"}

# Selectors that are pure chrome (nav, footer, cookie banners) and should be
# stripped so they don't pollute every single chunk with repeated boilerplate.
NOISE_SELECTORS = ["header", "footer", "nav", "script", "style", "noscript", "form"]


def clean_soup(soup: BeautifulSoup) -> BeautifulSoup:
    for selector in NOISE_SELECTORS:
        for tag in soup.select(selector):
            tag.decompose()
    return soup


def html_to_markdown_ish(soup: BeautifulSoup) -> str:
    """Lightweight, dependency-free HTML->text conversion good enough for RAG chunks."""
    lines = []
    for el in soup.find_all(["h1", "h2", "h3", "h4", "p", "li"]):
        text = el.get_text(strip=True, separator=" ")
        if not text:
            continue
        if el.name in ("h1", "h2", "h3", "h4"):
            level = "#" * int(el.name[1])
            lines.append(f"\n{level} {text}\n")
        elif el.name == "li":
            lines.append(f"- {text}")
        else:
            lines.append(text)
    return "\n".join(lines)


def slugify(path: str) -> str:
    slug = path.strip("/") or "home"
    return re.sub(r"[^a-z0-9-]+", "-", slug.lower())


def scrape_page(url: str) -> dict | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"  ! Failed to fetch {url}: {exc}", file=sys.stderr)
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else urlparse(url).path

    soup = clean_soup(soup)
    main = soup.find("main") or soup.find("body")
    content = html_to_markdown_ish(main) if main else ""

    return {"url": url, "title": title, "content": content}


def save_markdown(page: dict, out_dir: Path) -> Path:
    slug = slugify(urlparse(page["url"]).path)
    out_path = out_dir / f"{slug}.md"
    front_matter = (
        "---\n"
        f"source_url: {page['url']}\n"
        f"title: {page['title']}\n"
        "language: en\n"
        f"last_scraped: {time.strftime('%Y-%m-%d')}\n"
        "---\n\n"
    )
    out_path.write_text(front_matter + page["content"], encoding="utf-8")
    return out_path


def main():
    parser = argparse.ArgumentParser(description="Scrape N+ONE DATACENTERS website into Markdown.")
    parser.add_argument("--url", help="Scrape a single URL instead of the full seed list")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between requests (seconds)")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    urls = [args.url] if args.url else [urljoin(BASE_URL, p) for p in SEED_PATHS]

    print(f"Scraping {len(urls)} page(s) into {OUTPUT_DIR} ...")
    for url in urls:
        print(f"  -> {url}")
        page = scrape_page(url)
        if page and page["content"].strip():
            out_path = save_markdown(page, OUTPUT_DIR)
            print(f"     saved {out_path.name}")
        else:
            print("     skipped (no content or fetch error)")
        time.sleep(args.delay)  # be polite to the origin server

    print("Done. Run `python ingestion/ingest.py` to (re)build the vector index.")


if __name__ == "__main__":
    main()
