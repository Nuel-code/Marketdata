import requests
import pandas as pd

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
BBOX = (53.20, -6.45, 53.45, -6.05)  # Dublin: south, west, north, east

TAGS = [
    ("shop", "electronics"),
    ("shop", "computer"),
    ("shop", "mobile_phone"),
    ("shop", "clothes"),
    ("shop", "shoes"),
]

def query(tag_key, tag_value, bbox=BBOX):
    s, w, n, e = bbox
    return f"""
    [out:json][timeout:60];
    (
      node["{tag_key}"="{tag_value}"]({s},{w},{n},{e});
      way["{tag_key}"="{tag_value}"]({s},{w},{n},{e});
      relation["{tag_key}"="{tag_value}"]({s},{w},{n},{e});
    );
    out center tags;
    """

def fetch_osm():
    rows = []
    for k, v in TAGS:
        r = requests.post(OVERPASS_URL, data=query(k, v).encode("utf-8"))
        r.raise_for_status()
        for el in r.json().get("elements", []):
            tags = el.get("tags", {})
            name = tags.get("name")
            if not name:
                continue

            if el["type"] == "node":
                lat, lon = el.get("lat"), el.get("lon")
            else:
                c = el.get("center") or {}
                lat, lon = c.get("lat"), c.get("lon")

            rows.append({
                "osm_type": el["type"],
                "osm_id": el["id"],
                "category": f"{k}={v}",
                "name": name,
                "website": tags.get("website") or tags.get("contact:website"),
                "phone": tags.get("phone") or tags.get("contact:phone"),
                "brand": tags.get("brand"),
                "addr": " ".join(filter(None, [
                    tags.get("addr:housenumber"),
                    tags.get("addr:street"),
                    tags.get("addr:city"),
                    tags.get("addr:postcode"),
                ])) or None,
                "lat": lat, "lon": lon,
            })

    df = pd.DataFrame(rows).drop_duplicates(subset=["osm_type", "osm_id"])
    return df

def main():
    df = fetch_osm()
    df.to_csv("stores_dublin.csv", index=False)
    df_web = df[df["website"].notna()].copy()
    df_web.to_csv("stores_with_websites.csv", index=False)

    print(f"All stores: {len(df)} | With websites: {len(df_web)}")

if __name__ == "__main__":
    main()
