import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup
from tqdm.auto import tqdm
import json
import hashlib
from config import settings


BASE_URL = "https://elibrary.judiciary.gov.ph"
# page that shows all years & months (screenshot 1)
DECISIONS_INDEX_URL = f"{BASE_URL}/"   # change if the real path is e.g. "/decisions/"

REQUEST_DELAY = 1.0      # polite delay between requests
MAX_DECISIONS_PER_MONTH: Optional[int] = None   # e.g. 5 for testing, None for all
OUTPUT_JSONL = "sc_elibrary_decisions_text.jsonl"

MONTH_ABBRS = {"Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"}


CACHE_DIR = Path("cache")
CACHE_DIR.mkdir(exist_ok=True)

CHECKPOINT_FILE = Path("checkpoint_done.txt")
if CHECKPOINT_FILE.exists():
    done_urls = set(CHECKPOINT_FILE.read_text().splitlines())
else:
    done_urls = set()

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; research-bot; +https://example.com)"
})

def fetch(url: str, retries: int = 3, timeout: float = 20.0) -> requests.Response:
    last_err = None
    for attempt in range(retries):
        try:
            r = session.get(url, timeout=timeout)
            r.raise_for_status()
            time.sleep(REQUEST_DELAY)
            return r
        except requests.RequestException as e:
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    raise last_err

def get_soup(url: str) -> BeautifulSoup:
    return BeautifulSoup(fetch(url).text, "lxml")

def urljoin(href: str) -> str:
    return requests.compat.urljoin(BASE_URL, href)

def url_to_key(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()

def save_decision_cache(url: str, data: dict):
    key = url_to_key(url)
    cache_path = CACHE_DIR / f"{key}.json"

    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

    # mark checkpoint
    with open(CHECKPOINT_FILE, "a", encoding="utf-8") as f:
        f.write(url + "\n")

    done_urls.add(url)

def load_decision_cache(url: str):
    key = url_to_key(url)
    cache_path = CACHE_DIR / f"{key}.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text())
    return None

def find_month_links(index_url: str) -> Dict[str, str]:
    """
    Returns mapping like:
        { '1996-Jan': 'https://.../docmonth/Jan/1996/1', ... }

    Strategy:
      1) Try to read the year from the href itself ( .../1996/... ).
      2) Otherwise, use the most recent "year heading" encountered in
         the document (a tag whose text is exactly 4 digits).
    """
    soup = get_soup(index_url)

    container = soup.find(id="content") or soup.body or soup
    month_links: Dict[str, str] = {}

    current_year: Optional[str] = None

    # iterate through descendants in document order
    for el in container.descendants:
        if not hasattr(el, "name"):
            continue

        # 1) Detect year headings like <strong>1996</strong>, <h3>2008</h3>, etc.
        if el.name in ("strong", "b", "span", "h1", "h2", "h3", "h4", "h5", "h6"):
            text = (el.get_text(strip=True) or "")
            if re.fullmatch(r"(19|20)\d{2}", text):
                current_year = text

        # 2) Pick up month links
        if el.name == "a" and el.get("href"):
            label = (el.get_text(strip=True) or "")
            if label not in MONTH_ABBRS:
                continue

            href = urljoin(el["href"])

            # Prefer year from href if present: .../docmonth/Jan/1996/1
            m = re.search(r"/((?:19|20)\d{2})/", href)
            if m:
                year = m.group(1)
            elif current_year:
                year = current_year
            else:
                year = "unknown"

            key = f"{year}-{label}"
            month_links[key] = href

    return month_links

CASE_NO_RE = re.compile(
    r"\b(?:[A-Z]\.[A-Z]\.\s*No\.\s*\d+|[A-Z]{1,5}(?:-\d+)+)\b",
    re.I
)

def find_decision_links(month_url: str) -> List[str]:
    """
    From a month page (screenshot 2), return links to each decision.
    Heuristics:
      - only inside the main content container
      - anchor text looks like 'G.R. No. 275832', 'A.C. No. 7941', etc.
    """
    soup = get_soup(month_url)

    # try to narrow to main content; fall back to whole soup
    content = (soup.find(id="content") or
               soup.find("div", class_="content") or
               soup.find("div", class_="inner") or
               soup.body or soup)
    
    links = []
    for a in content.find_all("a", href=True):
        text = a.get_text(" ", strip=True)
        href = a["href"]

        # ignore printer-friendly or navigation links
        if not text:
            continue
        if text in MONTH_ABBRS:
            continue
        if "printer" in href.lower():
            continue

        # decision titles: 'G.R. No. 275832', 'A.C. No. 7941', etc.
        if CASE_NO_RE.search(text):
            full = urljoin(href)
            links.append(full)

    # dedupe while preserving order
    seen = set()
    uniq = []
    for u in links:
        if u not in seen:
            seen.add(u)
            uniq.append(u)

    return uniq


def extract_text_from_html_page(html: str) -> Tuple[str, str]:
    soup = BeautifulSoup(html, "lxml")

    # title
    title = soup.title.string.strip() if soup.title and soup.title.string else ""

    # focus on main content
    main = (soup.find(id="content") or
            soup.find("div", class_="content") or
            soup.find("article") or
            soup.body or soup)

    # drop obviously non-content elements
    for tag in main.find_all(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()

    text = main.get_text("\n", strip=True)
    text = re.sub(r"\n{2,}", "\n\n", text)

    return title, text


def extract_text_from_decision_url(url: str) -> Tuple[str, str]:
    r = fetch(url)
    ctype = r.headers.get("Content-Type", "").lower()

    return extract_text_from_html_page(r.text)

def crawl_decisions():
    month_links = find_month_links(DECISIONS_INDEX_URL)
    print(f"Found {len(month_links)} month links")
    
    rows = []
    for key, month_url in month_links.items():
        year, month_abbr = key.split("-")
        print(f"\n=== {year} {month_abbr} ===")
        print(month_url)

        decision_links = find_decision_links(month_url)
        if MAX_DECISIONS_PER_MONTH:
            decision_links = decision_links[:MAX_DECISIONS_PER_MONTH]

        print(f"  candidate decisions: {len(decision_links)}")

        for url in tqdm(decision_links, desc=f"{year}-{month_abbr}", leave=False):

            # 1) Skip if already processed (resume support)
            if url in done_urls:
                continue

            # 2) Try load from local cache
            cached = load_decision_cache(url)
            if cached is not None:
                rows.append(cached)
                continue

            # 3) Fresh extraction
            try:
                title, text = extract_text_from_decision_url(url)
            except Exception as e:
                print(f"[ERROR] {url}: {e}")
                continue

            data = {
                "year": year,
                "month": month_abbr,
                "title": title,
                "url": url,
                "text": text,
            }

            # 4) Save to cache + mark as completed
            save_decision_cache(url, data)

            # 5) Add to output rows
            rows.append(data)


    # write JSONL
    with open(OUTPUT_JSONL, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"\nSaved {len(rows)} decisions to {OUTPUT_JSONL}")

def main():
    crawl_decisions()

if __name__ == "__main__":
    main()