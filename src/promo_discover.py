import re
import time
import random
import requests
import pandas as pd
from urllib.parse import urlparse, urljoin

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123 Safari/537.36"

COMMON_PATHS = [
    "/deals", "/deal", "/offers", "/offer", "/promotions", "/promotion",
    "/sale", "/sales", "/clearance", "/special-offers", "/specials",
    "/weekly", "/weekly-ad", "/catalogue", "/catalog", "/leaflet", "/outlet",
    "/store/offers", "/offers-and-promotions", "/promos"
]

KEYWORDS = re.compile(r"(offer|deal|promo|promotion|sale|clearance|special|outlet|weekly|catalog|catalogue|leaflet|save)", re.I)

def normalize_base(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    if not url.startswith(("http://","https://")):
        url = "https://" + url
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"

def same_domain(a: str, b: str) -> bool:
    try:
        return urlparse(a).netloc.lower() == urlparse(b).netloc.lower()
    except Exception:
        return False

def get(url: str, timeout=20):
    return requests.get(url, timeout=timeout, headers={"User-Agent": UA}, allow_redirects=True)

def head(url: str, timeout=15):
    return requests.head(url, timeout=timeout, headers={"User-Agent": UA}, allow_redirects=True)

def safe_head_ok(url: str) -> bool:
    try:
        r = head(url)
        return r.status_code < 400
    except Exception:
        return False

def fetch_sitemap_urls(base: str):
    urls = set()
    for sm in ["/sitemap.xml", "/sitemap_index.xml"]:
        sm_url = urljoin(base, sm)
        try:
            r = get(sm_url, timeout=25)
            if r.status_code >= 400:
                continue
            # Extract <loc> URLs (good enough)
            found = re.findall(r"<loc>(.*?)</loc>", r.text)
            for u in found[:10000]:
                u = u.strip()
                if u and same_domain(base, u) and KEYWORDS.search(u):
                    urls.add(u)
        except Exception:
            pass
    return urls

def discover_for_site(website: str):
    base = normalize_base(website)
    if not base:
        return []

    found = set()

    # 1) common promo paths
    for path in COMMON_PATHS:
        u = urljoin(base, path)
        if safe_head_ok(u):
            found.add(u)

    # 2) sitemap keyword hits
    found |= fetch_sitemap_urls(base)

    # 3) light homepage scan for promo-ish links (optional but useful)
    try:
        r = get(base, timeout=25)
        if r.status_code < 400:
            hrefs = re.findall(r'href=["\'](.*?)["\']', r.text, flags=re.I)
            for h in hrefs[:3000]:
                if not h or h.startswith(("mailto:", "tel:", "javascript:")):
                    continue
                u = urljoin(base, h)
                if same_domain(base, u) and KEYWORDS.search(u):
                    found.add(u.split("#")[0])
    except Exception:
        pass

    # cap to avoid spam
    return sorted(list(found))[:40]

def priority_score(url: str) -> int:
    u = url.lower()
    score = 0
    for kw, pts in [
        ("weekly", 5), ("leaflet", 5), ("catalogue", 5), ("catalog", 4),
        ("offers", 4), ("promotions", 4), ("deals", 4),
        ("sale", 3), ("clearance", 3), ("special", 2), ("outlet", 2)
    ]:
        if kw in u:
            score += pts
    return score

def main():
    stores = pd.read_csv("stores_with_websites.csv")
    rows = []

    for i, row in stores.iterrows():
        name = row.get("name")
        website = row.get("website")
        category = row.get("category")
        addr = row.get("addr")

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

        # be nice to websites
        time.sleep(0.3 + random.random() * 0.4)

        if (i + 1) % 25 == 0:
            print(f"Processed {i+1}/{len(stores)} stores...")

    df = pd.DataFrame(rows)
    if df.empty:
        print("No promo URLs found.")
        df = pd.DataFrame(columns=["store_name","category","addr","website","promo_url","priority"])
    else:
        df = df.sort_values(["priority","store_name"], ascending=[False, True], kind="stable").reset_index(drop=True)
        df = df.drop_duplicates(subset=["promo_url"])

    # Write XLSX with clickable links
    with pd.ExcelWriter("promo_urls.xlsx", engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="promo_urls")
        wb = writer.book
        ws = writer.sheets["promo_urls"]
        ws.freeze_panes(1, 0)
        ws.autofilter(0, 0, len(df), len(df.columns) - 1)

        widths = {"store_name": 28, "category": 16, "addr": 30, "website": 40, "promo_url": 55, "priority": 10}
        for c, col in enumerate(df.columns):
            ws.set_column(c, c, widths.get(col, 18))

        link_fmt = wb.add_format({"font_color": "blue", "underline": 1})
        # website link
        if "website" in df.columns:
            c = df.columns.get_loc("website")
            for r, url in enumerate(df["website"].tolist(), start=2):
                if isinstance(url, str) and url.startswith(("http://","https://")):
                    ws.write_url(r-1, c, url, link_fmt, string="Website")
        # promo link
        if "promo_url" in df.columns:
            c = df.columns.get_loc("promo_url")
            for r, url in enumerate(df["promo_url"].tolist(), start=2):
                if isinstance(url, str) and url.startswith(("http://","https://")):
                    ws.write_url(r-1, c, url, link_fmt, string=url)

    # also save csv for versioning
    df.to_csv("promo_urls.csv", index=False)

    print(f"Promo URLs: {len(df)}")
    print("Wrote: promo_urls.xlsx (+ promo_urls.csv)")

if __name__ == "__main__":
    main()
