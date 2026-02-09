import os
import subprocess
import sys

def run(cmd):
    print(">", " ".join(cmd), flush=True)
    subprocess.check_call(cmd)

def main():
    # If we already have the store lists, don't hit Overpass again.
    if os.path.exists("stores_with_websites.csv") and os.path.exists("dublin_stores.xlsx"):
        print("> Skipping osm_discover.py (cached store outputs found)", flush=True)
    else:
        run([sys.executable, "src/osm_discover.py"])

    run([sys.executable, "src/promo_discover.py"])
    run([sys.executable, "src/extract_deals.py"])

if __name__ == "__main__":
    main()
