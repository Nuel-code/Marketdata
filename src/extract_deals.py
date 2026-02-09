import re
import time
import random
import requests
import pandas as pd
from bs4 import BeautifulSoup
from urllib.parse import urlparse

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123 Safari/537.36"

PRICE_RE = re.compile(r"(€|\£)\s?\d+(?:[\.,]\d{2})?")
PERCENT_RE = re.compile(r"\b(\d{1,2})\s?%")

def get(url, timeout=20):
    return requests.get(
        url,
        headers={"User-Agent": UA},
        timeout=timeout,
        allow_redirects=True,
    )

def clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()

def extract_prices(text: str):
    prices = PRICE_RE.findall(text)
    vals = []
    for p in prices:
        try:
            num = re.sub(r"[^\d\.]", "", p)
            vals.append(float(num))
        except Exception:
            pass
    return sorted(set(vals))

def extract_discount(text: str):
    m = PERCENT_RE.search(text)
    return int(m.group(1)) if m else None

def extract_title(soup: BeautifulSoup):
    for tag in ["h1", "h2", "title"]:
        el = soup.find(tag)
        if el and clean_text(el.get_text()):
            return clean_text(el.get_text())[:120]
    return None

def main():
    promos = pd.read_csv("promo_urls.csv")
    rows = []

    for i, row in promos.iterrows():
        store = row.get("store_name")
        category = row.get("category")
        website = row.get("website")
        promo_url = row.get("promo_url")

        print(f"[{i+1}/{len(promos)}] extracting {promo_url}", flush=True)

        try:
            r = get(promo_url)
            if r.status_code >= 400:
                continue

            soup = BeautifulSoup(r.text, "html.parser")
            text = clean_text(soup.get_text(" "))

            title = extract_title(soup)
            prices = extract_prices(text)
            discount = extract_discount(text)

            old_price = None
            new_price = None

            if len(prices) >= 2:
                old_price = max(prices)
                new_price = min(prices)
            elif len(prices) == 1:
                new_price = prices[0]

            rows.append({
                "store_name": store,
                "category": category,
                "deal_title": title,
                "old_price": old_price,
                "new_price": new_price,
                "discount_percent": discount,
                "source_url": promo_url,
                "website": website,
                "needs_review": True,
            })

            time.sleep(0.4 + random.random() * 0.4)

        except Exception as e:
            print(f"  ! failed: {e}", flush=True)

    df = pd.DataFrame(rows)

    if df.empty:
        print("No deals extracted.")
        df = pd.DataFrame(columns=[
            "store_name","category","deal_title","old_price",
            "new_price","discount_percent","source_url","website","needs_review"
        ])

    # Save CSV
    df.to_csv("deals.csv", index=False)

    # Save XLSX (clickable)
    with pd.ExcelWriter("deals.xlsx", engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="deals")
        ws = writer.sheets["deals"]
        ws.freeze_panes(1, 0)
        ws.autofilter(0, 0, len(df), len(df.columns) - 1)

        widths = {
            "store_name": 24,
            "category": 16,
            "deal_title": 40,
            "old_price": 12,
            "new_price": 12,
            "discount_percent": 12,
            "source_url": 50,
            "website": 35,
            "needs_review": 14,
        }
        for i, col in enumerate(df.columns):
            ws.set_column(i, i, widths.get(col, 18))

        link_fmt = writer.book.add_format({"font_color": "blue", "underline": 1})
        for i, url in enumerate(df["source_url"].tolist(), start=2):
            if isinstance(url, str) and url.startswith("http"):
                ws.write_url(i-1, df.columns.get_loc("source_url"), url, link_fmt, string="Open")

    print(f"Wrote deals.xlsx with {len(df)} rows")

if __name__ == "__main__":
    main()
