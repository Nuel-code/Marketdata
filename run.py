import subprocess, sys

def run(cmd):
    print(">", " ".join(cmd))
    subprocess.check_call(cmd)

def main():
    run([sys.executable, "src/osm_discover.py"])
    run([sys.executable, "src/promo_discover.py"])

if __name__ == "__main__":
    main()
