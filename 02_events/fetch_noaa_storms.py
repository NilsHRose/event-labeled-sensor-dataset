"""Download the NCEI Storm Events yearly CSVs and extract dust storms and
heat events for our five states into noaa_storms_2022_2024.csv.
Zone-based rows without coordinates are flagged coords_missing.
Run: python3 fetch_noaa_storms.py
"""

import csv
import gzip
import io
import re
import urllib.request
from pathlib import Path

import pandas as pd

BASE = "https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/"
YEARS = ["2022", "2023", "2024"]
STATES = ["ARIZONA", "CALIFORNIA", "NEW MEXICO", "NEVADA", "UTAH"]

TIER1_TYPES = ["Dust Storm", "Blowing Dust"]
TIER3_TYPES = ["Excessive Heat", "Heat"]
KEEP_TYPES = TIER1_TYPES + TIER3_TYPES


def http_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "wno-research/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def find_files():
    listing = http_get(BASE).decode("utf-8", "ignore")
    files = {}
    for y in YEARS:
        pat = rf'StormEvents_details-ftp_v1\.0_d{y}_c\d+\.csv\.gz'
        hits = sorted(set(re.findall(pat, listing)))
        if hits:
            files[y] = hits[-1]  # latest revision
            print(f"  {y}: {hits[-1]}")
        else:
            print(f"  {y}: NOT FOUND in directory listing")
    return files


def main():
    print("Locating yearly files ...")
    files = find_files()
    rows = []

    for y, fname in files.items():
        print(f"\nDownloading {fname} ...")
        raw = http_get(BASE + fname)
        with gzip.open(io.BytesIO(raw)) as gz:
            df = pd.read_csv(gz, low_memory=False)
        print(f"  {len(df):,} events nationwide")

        sel = df[df["STATE"].isin(STATES) & df["EVENT_TYPE"].isin(KEEP_TYPES)]
        print(f"  kept {len(sel)} in our states/types")

        for _, e in sel.iterrows():
            etype = e["EVENT_TYPE"]
            tier = 1 if etype in TIER1_TYPES else 3
            lat = e.get("BEGIN_LAT")
            lon = e.get("BEGIN_LON")
            missing = pd.isna(lat) or pd.isna(lon)

            byd = str(int(e["BEGIN_YEARMONTH"])) + f"{int(e['BEGIN_DAY']):02d}"
            date = f"{byd[:4]}-{byd[4:6]}-{byd[6:8]}"
            btime = f"{int(e['BEGIN_TIME']):04d}"
            begin_hhmm = f"{btime[:2]}:{btime[2:]}"

            eyd = str(int(e["END_YEARMONTH"])) + f"{int(e['END_DAY']):02d}"
            end_date = f"{eyd[:4]}-{eyd[4:6]}-{eyd[6:8]}"

            rows.append({
                "name": f"{etype} — {e.get('CZ_NAME','')}, {e['STATE'].title()} {date}",
                "type": "dust_storm" if tier == 1 else "heatwave",
                "date": date,
                "begin_time_local": begin_hhmm,
                "timezone": e.get("CZ_TIMEZONE", ""),
                "end_date": end_date,
                "location": f"{e.get('CZ_NAME','')}, {e['STATE'].title()}",
                "lat": None if missing else round(float(lat), 5),
                "lon": None if missing else round(float(lon), 5),
                "coords_missing": bool(missing),
                "region": "US",
                "state": e["STATE"].title(),
                "origin": etype,
                "source": "NOAA NCEI Storm Events",
                "source_url": "https://www.ncdc.noaa.gov/stormevents/",
                "episode_id": e.get("EPISODE_ID", ""),
                "event_id_noaa": e.get("EVENT_ID", ""),
                "tier": tier,
                "diffuse": tier == 3,
                "notes": str(e.get("EVENT_NARRATIVE", ""))[:200],
            })

    out = Path.home() / "Desktop" / "noaa_storms_2022_2024.csv"
    df = pd.DataFrame(rows)
    df.to_csv(out, index=False)

    print(f"\nWrote {len(df)} events to {out}")
    if len(df):
        print("\nBy type:")
        print(df["type"].value_counts().to_string())
        print("\nTier 1 (dust) by state × year:")
        t1 = df[df["tier"] == 1].copy()
        t1["year"] = t1["date"].str[:4]
        print(pd.crosstab(t1["state"], t1["year"]).to_string())
        print(f"\nDust events missing coords: {t1['coords_missing'].sum()} "
              f"(get county centroids at merge)")


if __name__ == "__main__":
    main()