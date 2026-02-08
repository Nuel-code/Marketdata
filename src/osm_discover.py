import time
import random
import requests
import pandas as pd
from urllib.parse import urlparse

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

def normalize_url(u):
    if not u or not isinstance(u, str):
        return None
    u = u.strip()
    if not u:
        return None
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    return u

def website_domain(u):
    if not u:
        return None
    try:
        netloc = urlparse(u).netloc.lower()
        return netloc.replace("www.", "", 1)
    except Exception:
        return None

def maps_url(lat, lon):
    if lat is None or lon is None:
        return None
    return f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"

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

            addr = " ".join(filter(None, [
                tags.get("addr:housenumber"),
                tags.get("addr:street"),
                tags.get("addr:city"),
                tags.get("addr:postcode"),
            ])) or None

            rows.append({
                "category": f"{k}={v}",
                "name": name,
                "addr": addr,
                "website": website,
                "website_domain": website_domain(website),
                "maps": maps_url(lat, lon),
                "phone": tags.get("phone") or tags.get("contact:phone"),
                "brand": tags.get("brand"),
                "lat": lat,
                "lon": lon,
                "osm_type": el["type"],
                "osm_id": el["id"],
            })

    df = pd.DataFrame(rows).drop_duplicates(subset=["osm_type", "osm_id"])
    # Clean + stable sort so it stays organised
    df["phone"] = df["phone"].astype("string")
    df = df.sort_values(["category", "name"], kind="stable").reset_index(drop=True)
    return df

def write_xlsx(df_all: pd.DataFrame, df_web: pd.DataFrame, path: str):
    # Requires XlsxWriter installed
    with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
        df_all.to_excel(writer, index=False, sheet_name="stores_all")
        df_web.to_excel(writer, index=False, sheet_name="stores_with_websites")

        wb = writer.book

        def style_sheet(sheet_name, df):
            ws = writer.sheets[sheet_name]
            ws.freeze_panes(1, 0)
            ws.autofilter(0, 0, len(df), len(df.columns) - 1)

            # Column widths (phone-friendly)
            widths = {
                "category": 16, "name": 30, "addr": 35,
                "website": 45, "website_domain": 22, "maps": 45,
                "phone": 16, "brand": 18, "lat": 10, "lon": 10,
                "osm_type": 10, "osm_id": 12,
            }
            for i, col in enumerate(df.columns):
                ws.set_column(i, i, widths.get(col, 18))

            # Turn website + maps into real hyperlinks
            link_fmt = wb.add_format({"font_color": "blue", "underline": 1})

            if "website" in df.columns:
                c = df.columns.get_loc("website")
                for r, url in enumerate(df["website"].tolist(), start=2):
                    if isinstance(url, str) and url.startswith(("http://", "https://")):
                        ws.write_url(r - 1, c, url, link_fmt, string=url)

            if "maps" in df.columns:
                c = df.columns.get_loc("maps")
                for r, url in enumerate(df["maps"].tolist(), start=2):
                    if isinstance(url, str) and url.startswith(("http://", "https://")):
                        ws.write_url(r - 1, c, url, link_fmt, string="Open in Maps")

        style_sheet("stores_all", df_all)
        style_sheet("stores_with_websites", df_web)

def main():
    df_all = fetch_osm()
    df_web = df_all[df_all["website"].notna()].copy()

    # Keep CSVs (source-of-truth + easy diffs)
    df_all.to_csv("stores_dublin.csv", index=False)
    df_web.to_csv("stores_with_websites.csv", index=False)

    # The spreadsheet you actually use
    write_xlsx(df_all, df_web, "dublin_stores.xlsx")

    print(f"All stores: {len(df_all)} | With websites: {len(df_web)}")
    print("Wrote: dublin_stores.xlsx (+ CSVs)")

if __name__ == "__main__":
    main()
