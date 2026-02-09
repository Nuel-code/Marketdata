import os
import subprocess
import sys

def run(cmd):
    print(">", " ".join(cmd), flush=True)
    subprocess.check_call(cmd)

def main():
    if not (os.path.exists("stores_with_websites.csv") and os.path.exists("dublin_stores.xlsx")):
        run([sys.executable, "src/osm_discover.py"])
    else:
        print("> Skipping osm_discover.py (cached outputs found)", flush=True)

    run([sys.executable, "src/promo_discover.py"])
    run([sys.executable, "src/extract_deals.py"])     # assuming you already have this
    run([sys.executable, "src/export_feed.py"])       # ✅ clean export

if __name__ == "__main__":
    main()
