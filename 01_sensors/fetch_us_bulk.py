"""Download EPA AQS pre-generated hourly bulk files (2025 + 2026 H1),
filter to our five states and write Data/USA_GMT_v5/<Region>_2025_2026H1.csv.
The script prints the last datetime per region, which pins the v5 cutoff.
Run: python3 fetch_us_bulk.py            (or: fetch_us_bulk.py <param> <year>)
"""

import sys
import time
import urllib.request
from pathlib import Path

import pandas as pd

BASE = Path.home()/"Desktop/Research/Neural Operators/Data"
BULK = BASE/"US_bulk"; BULK.mkdir(exist_ok=True)
OUT = BASE/"USA_GMT_v5"; OUT.mkdir(exist_ok=True)

URL = "https://aqs.epa.gov/aqsweb/airdata/hourly_{p}_{y}.zip"
PARAMS = {"88101": "pm25", "81102": "pm10", "42602": "no2",
          "42401": "so2", "42101": "co", "44201": "o3"}
YEARS = [2025, 2026]
STATES = {"04": "Arizona", "06": "California", "32": "Nevada",
          "35": "NewMexico", "49": "Utah"}
CUTOFF = "2026-06-30"
USECOLS = ["State Code", "County Code", "Site Num", "Latitude", "Longitude",
           "Date GMT", "Time GMT", "Sample Measurement"]


def download(p, y):
    f = BULK/f"hourly_{p}_{y}.zip"
    if f.exists() and f.stat().st_size > 1_000_000:
        print(f"  [have] {f.name} ({f.stat().st_size//1_000_000} MB)")
        return f
    url = URL.format(p=p, y=y)
    print(f"  [get ] {url}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "wno-research"})
        with urllib.request.urlopen(req, timeout=300) as r, open(f, "wb") as o:
            done = 0
            while True:
                chunk = r.read(8_388_608)
                if not chunk:
                    break
                o.write(chunk); done += len(chunk)
                if done % 83_886_080 < 8_388_608:
                    print(f"      ...{done//1_000_000} MB", flush=True)
        print(f"  [ok  ] {f.name} ({f.stat().st_size//1_000_000} MB)")
        return f
    except Exception as e:
        print(f"  [fail] {url}: {e}")
        if f.exists():
            f.unlink()
        return None


def main():
    only_p = sys.argv[1] if len(sys.argv) > 2 else None
    only_y = int(sys.argv[2]) if len(sys.argv) > 2 else None
    frames = []
    for p, pname in PARAMS.items():
        if only_p and p != only_p:
            continue
        for y in YEARS:
            if only_y and y != only_y:
                continue
            f = download(p, y)
            if f is None:
                continue
            t0 = time.time()
            kept = 0
            for chunk in pd.read_csv(f, usecols=USECOLS, dtype=str,
                                     chunksize=500_000):
                chunk = chunk[chunk["State Code"].isin(STATES)]
                if not len(chunk):
                    continue
                kept += len(chunk)
                chunk = chunk.assign(
                    region=chunk["State Code"].map(STATES),
                    site_id=chunk["State Code"] + "-" + chunk["County Code"]
                            + "-" + chunk["Site Num"],
                    datetime_utc=chunk["Date GMT"] + " " + chunk["Time GMT"],
                    param=pname,
                    value=pd.to_numeric(chunk["Sample Measurement"],
                                        errors="coerce"))
                frames.append(chunk[["region", "site_id", "datetime_utc",
                                     "Latitude", "Longitude", "param", "value"]])
            print(f"  {pname} {y}: {kept} state-rows kept "
                  f"({time.time()-t0:.0f}s)", flush=True)

    if not frames:
        print("nothing extracted"); return
    allrows = pd.concat(frames, ignore_index=True)
    allrows = allrows[allrows["datetime_utc"] <= CUTOFF + " 23:59"]
    print(f"\ntotal rows (5 states, <= {CUTOFF}): {len(allrows)}")

    for region, g in allrows.groupby("region"):
        wide = g.pivot_table(index=["site_id", "datetime_utc",
                                    "Latitude", "Longitude"],
                             columns="param", values="value",
                             aggfunc="mean").reset_index()
        wide = wide.rename(columns={"Latitude": "latitude",
                                    "Longitude": "longitude"})
        out = OUT/f"{region}_2025_2026H1.csv"
        wide.to_csv(out, index=False)
        print(f"  {region}: {len(wide):>8} station-hours · "
              f"{wide['site_id'].nunique()} sites · "
              f"last datetime = {wide['datetime_utc'].max()}")
    print(f"\n-> {OUT}")
    print("CHECK the 'last datetime' lines: the minimum across regions is "
          "the true US cutoff for v5.")


if __name__ == "__main__":
    main()
