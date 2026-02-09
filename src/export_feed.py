import json
import os
from datetime import datetime, timezone

import pandas as pd


INPUT_XLSX = os.getenv("DEALS_XLSX", "deals.xlsx")
OUTPUT_JSON = os.getenv("OUTPUT_JSON", "published_deals.json")


# Map messy spreadsheet columns → stable API fields
COLUMN_MAP = {
    "store_name": ["store_name", "store", "merchant", "shop"],
    "category": ["category", "store_category"],
    "deal_title": ["deal_title", "title", "name", "product", "deal"],
    "old_price": ["old_price", "was_price", "price_old", "previous_price"],
    "new_price": ["new_price", "now_price", "price_new", "current_price", "price"],
    "discount_percent": ["discount_percent", "discount", "percent_off", "%off"],
    "start_date": ["start_date", "valid_from", "from"],
    "end_date": ["end_date", "valid_to", "to", "expires"],
    "in_store_confidence": ["in_store_confidence", "in_store", "instore_confidence"],
    "source_url": ["source_url", "url", "promo_url", "link"],
    "addr": ["addr", "address", "location"],
    "lat": ["lat", "latitude"],
    "lon": ["lon", "lng", "longitude"],
    "publish": ["publish", "approved", "is_published"],
    "needs_review": ["needs_review", "review", "flagged"],
    "captured_at": ["captured_at", "captured", "scraped_at", "timestamp"],
}

def pick_col(df: pd.DataFrame, keys: list[str]) -> str | None:
    cols = {c.lower(): c for c in df.columns}
    for k in keys:
        if k.lower() in cols:
            return cols[k.lower()]
    return None

def as_bool(x) -> bool | None:
    if pd.isna(x):
        return None
    if isinstance(x, bool):
        return x
    s = str(x).strip().lower()
    if s in ("true", "1", "yes", "y", "approved", "publish"):
        return True
    if s in ("false", "0", "no", "n", "reject", "rejected"):
        return False
    return None

def as_float(x) -> float | None:
    if pd.isna(x):
        return None
    try:
        # strip currency symbols/commas
        s = str(x).replace(",", "").strip()
        s = "".join(ch for ch in s if (ch.isdigit() or ch in ".-"))
        return float(s) if s else None
    except Exception:
        return None

def main():
    df = pd.read_excel(INPUT_XLSX)

    # Build column lookup once
    col = {k: pick_col(df, v) for k, v in COLUMN_MAP.items()}

    rows = []
    now_iso = datetime.now(timezone.utc).isoformat()

    for _, r in df.iterrows():
        item = {
            "store_name": r.get(col["store_name"]) if col["store_name"] else None,
            "category": r.get(col["category"]) if col["category"] else None,
            "title": r.get(col["deal_title"]) if col["deal_title"] else None,
            "old_price": as_float(r.get(col["old_price"])) if col["old_price"] else None,
            "new_price": as_float(r.get(col["new_price"])) if col["new_price"] else None,
            "discount_percent": as_float(r.get(col["discount_percent"])) if col["discount_percent"] else None,
            "start_date": r.get(col["start_date"]) if col["start_date"] else None,
            "end_date": r.get(col["end_date"]) if col["end_date"] else None,
            "in_store_confidence": r.get(col["in_store_confidence"]) if col["in_store_confidence"] else None,
            "source_url": r.get(col["source_url"]) if col["source_url"] else None,
            "addr": r.get(col["addr"]) if col["addr"] else None,
            "lat": as_float(r.get(col["lat"])) if col["lat"] else None,
            "lon": as_float(r.get(col["lon"])) if col["lon"] else None,
            "captured_at": r.get(col["captured_at"]) if col["captured_at"] else now_iso,
        }

        publish_val = as_bool(r.get(col["publish"])) if col["publish"] else None
        needs_review_val = as_bool(r.get(col["needs_review"])) if col["needs_review"] else None

        # Default behavior:
        # - If publish column exists, only export published ones
        # - Else export all, but mark needs_review true
        if col["publish"]:
            if publish_val is not True:
                continue
            item["publish"] = True
        else:
            item["publish"] = True  # for MVP feed
            item["needs_review"] = True if needs_review_val is None else needs_review_val

        # Minimal sanity: must have title + source_url
        if not item["title"] or not item["source_url"]:
            continue

        rows.append(item)

    out = {
        "generated_at": now_iso,
        "count": len(rows),
        "items": rows,
    }

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)

    print(f"Wrote {OUTPUT_JSON} with {len(rows)} items")

if __name__ == "__main__":
    main()
