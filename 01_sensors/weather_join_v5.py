"""Join Open-Meteo (ERA5) weather to every station in the v5 data files,
US and EU trees alike. Only fetches stations whose weather is still
missing, paces requests and backs off when throttled, so it can be
re-run until every file reports ~100%.
Run: python3 weather_join_v5.py us|eu|all
"""

import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

BASE = Path.home()/"Desktop/Research/Neural Operators/Data"
DIRS = {"us": BASE/"USA_GMT_v5", "eu": BASE/"EU_v5"}
START, END = "2025-01-01", "2026-06-30"
WCOLS = ["temperature_2m", "surface_pressure", "precipitation",
         "wind_speed_10m", "wind_direction_10m"]


def fetch_weather(lat, lon):
    url = ("https://archive-api.open-meteo.com/v1/archive?" +
           urllib.parse.urlencode({
               "latitude": lat, "longitude": lon,
               "start_date": START, "end_date": END,
               "hourly": ",".join(WCOLS), "timezone": "UTC"}))
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                js = json.load(r)
            if "hourly" in js:
                w = pd.DataFrame(js["hourly"])
                w["dt_key"] = pd.to_datetime(w["time"]).dt.strftime("%Y-%m-%d %H:%M")
                return w.drop(columns=["time"])
            return None
        except Exception as e:
            wait = 60 if "429" in str(e) or attempt >= 1 else 10
            print(f"      retry in {wait}s ({e})", flush=True)
            time.sleep(wait)
    return None


def join_file(f):
    df = pd.read_csv(f, dtype={"site_id": str})
    df["dt_key"] = pd.to_datetime(df["datetime_utc"]).dt.strftime("%Y-%m-%d %H:%M")
    if "temperature_2m" not in df.columns:
        for c in WCOLS:
            df[c] = pd.NA
    # stations still missing weather
    miss = (df.groupby("site_id")["temperature_2m"]
              .apply(lambda s: s.isna().all()))
    pending = list(miss[miss].index)
    done_frac = 1 - df["temperature_2m"].isna().mean()
    if not pending:
        print(f"{f.name}: complete ({done_frac*100:.1f}%)")
        return
    print(f"{f.name}: {len(pending)} stations to fetch "
          f"(currently {done_frac*100:.1f}%)")
    coords = (df[df.site_id.isin(pending)]
              [["site_id", "latitude", "longitude"]].drop_duplicates("site_id"))
    ok = fail = 0
    for i, s in enumerate(coords.itertuples(index=False), 1):
        w = fetch_weather(s.latitude, s.longitude)
        if w is None:
            fail += 1
            print(f"   [{i}/{len(coords)}] {s.site_id} FAILED", flush=True)
            continue
        m = df["site_id"].eq(s.site_id)
        sub = df.loc[m, ["dt_key"]].merge(w, on="dt_key", how="left")
        for c in WCOLS:
            df.loc[m, c] = sub[c].values
        ok += 1
        if i % 10 == 0:
            print(f"   [{i}/{len(coords)}] ...", flush=True)
        time.sleep(1.5)
    df.drop(columns=["dt_key"]).to_csv(f, index=False)
    final = (1 - df["temperature_2m"].isna().mean())*100
    print(f"{f.name}: +{ok} stations, {fail} failed -> match {final:.1f}%")


def main():
    which = (sys.argv[1] if len(sys.argv) > 1 else "all").lower()
    targets = []
    if which in ("us", "all"):
        targets += sorted(DIRS["us"].glob("*_2025_2026H1.csv"))
    if which in ("eu", "all"):
        targets += sorted(DIRS["eu"].glob("*_20*.csv"))
    if not targets:
        print("no files found"); return
    for f in targets:
        join_file(f)
    print("\nRe-run the same command if any station FAILED — it resumes "
          "exactly where needed.")


if __name__ == "__main__":
    main()
