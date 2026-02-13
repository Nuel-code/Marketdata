import os
import re
import time
import random
import requests
import pandas as pd
from urllib.parse import urljoin, urlparse

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123 Safari/537.36"

# ---------- Tunables (via workflow env) ----------
MAX_STORES = int(os.getenv("MAX_STORES", "60"))  # cap stores per run (prevents timeouts)
MAX_PROMO_URLS_PER_STORE = int(os.getenv("MAX_PROMO_URLS_PER_STORE", "25"))
SITEMAP_URL_CAP = int(os.getenv("SITEMAP_URL_CAP", "3000"))

REQ_TIMEOUT_GET = int(os.getenv("REQ_TIMEOUT_GET", "15"))
REQ_TIMEOUT_HEAD = int(os.getenv("REQ_TIMEOUT_HEAD", "10"))

SLEEP_MIN = float(os.getenv("SLEEP_MIN", "0.15"))
SLEEP_MAX = float(os.getenv("SLEEP_MAX", "0.35"))

# ---------- Heuristics ----------
COMMON_PATHS = [
    "/deals", "/deal", "/offers", "/offer", "/promotions", "/promotion",
    "/sale", "/sales", "/clearance", "/special-offers", "/specials",
    "/weekly", "/weekly-ad", "/catalogue", "/catalog", "/leaflet", "/outlet",
    "/offers-and-promotions", "/promos"
]

KEYWORDS = re.compile(r"(offer|deal|promo|promotion|sale|clearance|special|outlet|weekly|catalog|catalogue|leaflet|save)", re.I)

def normalize_base(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"

def same_domain(base: str, u: str) -> bool:
    try:
        return urlparse(base).netloc.lower() == urlparse(u).netloc.lower()
    except Exception:
        return False

def get(url: str, timeout=REQ_TIMEOUT_GET):
    return requests.get(url, timeout=timeout, headers={"User-Agent": UA}, allow_redirects=True)

def head(url: str, timeout=REQ_TIMEOUT_HEAD):
    return requests.head(url, timeout=timeout, headers={"User-Agent": UA}, allow_redirects=True)

def head_ok(url: str) -> bool:
    try:
        r = head(url)
        return r.status_code < 400
    except Exception:
        return False

def extract_sitemap_urls(xml_text: str):
    # crude but fast <loc> parsing
    urls = re.findall(r"<loc>(.*?)</loc>", xml_text)
    return [u.strip() for u in urls if u and isinstance(u, str)]

def fetch_sitemap_hits(base: str):
    hits = set()
    for sm in ["/sitemap.xml", "/sitemap_index.xml"]:
        sm_url = urljoin(base, sm)
        try:
            r = get(sm_url, timeout=REQ_TIMEOUT_GET)
            if r.status_code >= 400:
                continue
            urls = extract_sitemap_urls(r.text)[:SITEMAP_URL_CAP]
            for u in urls:
                if same_domain(base, u) and KEYWORDS.search(u):
                    hits.add(u.split("#")[0])
        except Exception:
            pass
    return hits

def fetch_homepage_hits(base: str):
    hits = set()
    try:
        r = get(base, timeout=REQ_TIMEOUT_GET)
        if r.status_code >= 400:
            return hits
        hrefs = re.findall(r'href=["\'](.*?)["\']', r.text, flags=re.I)
        # cap to avoid insane pages
        for h in hrefs[:1500]:
            if not h or h.startswith(("mailto:", "tel:", "javascript:")):
                continue
            u = urljoin(base, h).split("#")[0]
            if same_domain(base, u) and KEYWORDS.search(u):
                hits.add(u)
    except Exception:
        pass
    return hits

def discover_for_site(website: str):
    base = normalize_base(website)
    if not base:
        return []

    found = set()

    # 1) common promo paths (cheap)
    for path in COMMON_PATHS:
        u = urljoin(base, path)
        if head_ok(u):
            found.add(u)

    # 2) sitemap hits (good coverage, sometimes slow)
    found |= fetch_sitemap_hits(base)

    # 3) homepage link scan (nice extra, capped)
    found |= fetch_homepage_hits(base)

    # final cap per store
    found = sorted(found)[:MAX_PROMO_URLS_PER_STORE]
    return found

def priority_score(url: str) -> int:
    u = (url or "").lower()
    score = 0
    for kw, pts in [
        ("weekly", 6), ("leaflet", 6), ("catalogue", 6), ("catalog", 5),
        ("offers", 5), ("promotions", 5), ("deals", 5),
        ("sale", 3), ("clearance", 3), ("special", 2), ("outlet", 2)
    ]:
        if kw in u:
            score += pts
    return score

def write_xlsx(df: pd.DataFrame, path="promo_urls.xlsx"):
    with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="promo_urls")
        wb = writer.book
        ws = writer.sheets["promo_urls"]
        ws.freeze_panes(1, 0)
        ws.autofilter(0, 0, len(df), len(df.columns) - 1)

        widths = {"store_name": 28, "category": 16, "addr": 30, "website": 18, "promo_url": 55, "priority": 10}
        for c, col in enumerate(df.columns):
            ws.set_column(c, c, widths.get(col, 18))

        link_fmt = wb.add_format({"font_color": "blue", "underline": 1})

        # Make 'website' column a clean clickable label
        if "website" in df.columns:
            c = df.columns.get_loc("website")
            for r, url in enumerate(df["website"].tolist(), start=2):
                if isinstance(url, str) and url.startswith(("http://", "https://")):
                    ws.write_url(r - 1, c, url, link_fmt, string="Website")

        # Make promo_url clickable
        if "promo_url" in df.columns:
            c = df.columns.get_loc("promo_url")
            for r, url in enumerate(df["promo_url"].tolist(), start=2):
                if isinstance(url, str) and url.startswith(("http://", "https://")):
                    ws.write_url(r - 1, c, url, link_fmt, string=url)

def main():
    stores = pd.read_csv("stores_with_websites.csv")

    total = len(stores)
    n = min(MAX_STORES, total)

    # Deterministic selection: take the first N (already sorted from your store sheet)
    # Later you can randomize/rotate. For now: reliable.
    stores = stores.head(n).reset_index(drop=True)

    print(f"Using {n}/{total} stores (MAX_STORES={MAX_STORES})", flush=True)

    rows = []
    for i, row in stores.iterrows():
        name = row.get("name")
        website = row.get("website")
        category = row.get("category")
        addr = row.get("addr")

        print(f"[{i+1}/{n}] {name} | {website}", flush=True)

        promo_urls = discover_for_site(str(website))
        for u in promo_urls:
            rows.append({
                "store_name": name,
                "category": category,
                "addr": addr,
                "website": website,
                "promo_url": u,
                "priority": priority_score(u),
            })

        time.sleep(SLEEP_MIN + random.random() * (SLEEP_MAX - SLEEP_MIN))

    df = pd.DataFrame(rows)

    if df.empty:
        df = pd.DataFrame(columns=["store_name", "category", "addr", "website", "promo_url", "priority"])
    else:
        df = df.drop_duplicates(subset=["promo_url"])
        df = df.sort_values(["priority", "store_name"], ascending=[False, True], kind="stable").reset_index(drop=True)

    df.to_csv("promo_urls.csv", index=False)
    write_xlsx(df, "promo_urls.xlsx")

    print(f"Promo URLs: {len(df)}", flush=True)
    print("Wrote: promo_urls.xlsx (+ promo_urls.csv)", flush=True)

if __name__ == "__main__":
    main()
