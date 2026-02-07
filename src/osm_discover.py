import time
import random
import requests
import pandas as pd

BBOX = (53.20, -6.45, 53.45, -6.05)  # Dublin

TAGS = [
    ("shop", "electronics"),
    ("shop", "computer"),
    ("shop", "mobile_phone"),
    ("shop", "clothes"),
    ("shop", "shoes"),
]

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.nchc.org.tw/api/interpreter",
]

def query(tag_key, tag_value, bbox=BBOX):
    s, w, n, e = bbox
    return f"""
    [out:json][timeout:180];
    (
      node["{tag_key}"="{tag_value}"]({s},{w},{n},{e});
      way["{tag_key}"="{tag_value}"]({s},{w},{n},{e});
      relation["{tag_key}"="{tag_value}"]({s},{w},{n},{e});
    );
    out center tags;
    """

def overpass_post(q: str, timeout=180, tries=6):
    last_err = None
    for attempt in range(tries):
        url = random.choice(OVERPASS_ENDPOINTS)
        try:
            r = requests.post(url, data=q.encode("utf-8"), timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last_err = e
            sleep_s = (2 ** attempt) + random.random()
            print(f"[warn] Overpass fail ({url}) attempt {attempt+1}/{tries}: {e} | sleeping {sleep_s:.1f}s")
            time.sleep(sleep_s)
    raise last_err

def normalize_url(u: str | None) -> str | None:
    if not u or not isinstance(u, str):
        return None
    u = u.strip()
    if not u:
        return None
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    return u

def fetch_osm():
    rows = []
    for k, v in TAGS:
        data = overpass_post(query(k, v))
        for el in data.get("elements", []):
            tags = el.get("tags", {})
            name = tags.get("name")
            if not name:
                continue

            if el["type"] == "node":
                lat, lon = el.get("lat"), el.get("lon")
            else:
                c = el.get("center") or {}
                lat, lon = c.get("lat"), c.get("lon")

            website = normalize_url(tags.get("website") or tags.get("contact:website"))

            rows.append({
                "name": name,
                "category": f"{k}={v}",
                "website": website,
                "addr": " ".join(filter(None, [
                    tags.get("addr:housenumber"),
                    tags.get("addr:street"),
                    tags.get("addr:city"),
                    tags.get("addr:postcode"),
                ])) or None,
                "phone": tags.get("phone") or tags.get("contact:phone"),
                "brand": tags.get("brand"),
                "lat": lat,
                "lon": lon,
                "osm_type": el["type"],
                "osm_id": el["id"],
            })

    df = pd.DataFrame(rows).drop_duplicates(subset=["osm_type", "osm_id"])
    # Make it look sane
    df = df.sort_values(["category", "name"], kind="stable").reset_index(drop=True)
    return df

def to_xlsx_with_hyperlinks(df: pd.DataFrame, path: str):
    # Write with xlsxwriter so links become clickable
    with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="stores")
        wb = writer.book
        ws = writer.sheets["stores"]

        # Freeze header row
        ws.freeze_panes(1, 0)

        # Set column widths
        col_widths = {
            "name": 30, "category": 18, "website": 45, "addr": 35,
            "phone": 18, "brand": 18, "lat": 10, "lon": 10,
            "osm_type": 10, "osm_id": 12
        }
        for i, col in enumerate(df.columns):
            ws.set_column(i, i, col_widths.get(col, 18))

        # Convert website cells to real hyperlinks
        if "website" in df.columns:
            link_fmt = wb.add_format({"font_color": "blue", "underline": 1})
            website_col_idx = df.columns.get_loc("website")
            for row_idx, url in enumerate(df["website"].tolist(), start=2):  # Excel rows start at 1, header is row 1
                if isinstance(url, str) and url.startswith(("http://", "https://")):
                    ws.write_url(row_idx - 1, website_col_idx, url, link_fmt, string=url)

def main():
    df = fetch_osm()

    # CSV (plain text)
    df.to_csv("stores_dublin.csv", index=False)

    df_web = df[df["website"].notna()].copy()
    df_web.to_csv("stores_with_websites.csv", index=False)

    # XLSX (clickable links)
    to_xlsx_with_hyperlinks(df, "stores_dublin.xlsx")
    to_xlsx_with_hyperlinks(df_web, "stores_with_websites.xlsx")

    print(f"All stores: {len(df)} | With websites: {len(df_web)}")
    print("Wrote: stores_dublin.xlsx, stores_with_websites.xlsx")

if __name__ == "__main__":
    main()
