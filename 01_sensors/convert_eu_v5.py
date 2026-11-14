"""Convert the EEA parquet downloads to our per-city/year CSV format,
Data/EU_v5/<City>_<year>.csv. Station list and coordinates come from the
v4 split; unknown stations are skipped so the network stays identical.
Timestamps are shifted from UTC+1 to UTC (TZ_OFF); an O3 diurnal-peak
check is printed so a wrong offset is easy to spot.
"""

import glob
import re
from pathlib import Path

import pandas as pd

BASE = Path.home()/"Desktop/Research/Neural Operators/Data"
RAW = BASE/"EU_raw_v5"
V4EU = BASE/"wno_split_v4/EU"
OUT = BASE/"EU_v5"
OUT.mkdir(exist_ok=True)

TZ_OFF = 1  # hours ahead of UTC in the raw files (EEA: UTC+1 fixed)
START, END = "2025-01-01", "2026-06-30 23:59"
POLL = {1: "so2", 5: "pm10", 7: "o3", 8: "no2", 10: "co", 6001: "pm25"}


def station_registry():
    """station -> (city, lat, lon) from the v4 tree"""
    reg = {}
    for citydir in sorted(V4EU.iterdir()):
        if not citydir.is_dir():
            continue
        for f in citydir.glob(f"{citydir.name}_20*.csv"):
            head = pd.read_csv(f, nrows=2000)
            cols = {c.lower(): c for c in head.columns}
            sid = cols.get("site_id") or list(head.columns)[0]
            la, lo = cols.get("latitude"), cols.get("longitude")
            for _, r in head.drop_duplicates(subset=[sid]).iterrows():
                code = str(r[sid]).strip()
                reg[code] = (citydir.name,
                             float(r[la]) if la else None,
                             float(r[lo]) if lo else None)
            break  # one year suffices for the registry
    print(f"Station registry from v4: {len(reg)} stations, "
          f"cities: {sorted(set(v[0] for v in reg.values()))}")
    return reg


def station_code(sp):
    """'DE/SPO.DE_DEBE062_NO2_dataGroup1' -> 'DEBE062'"""
    m = re.search(r"SPO\.[A-Z]{2}_([A-Z]{2}[A-Z0-9]+?)_", str(sp))
    return m.group(1) if m else None


def main():
    reg = station_registry()
    frames = []
    for stream, prio in (("E1a", 1), ("E2a", 2)):
        files = glob.glob(str(RAW/stream/"**/*.parquet"), recursive=True)
        print(f"{stream}: {len(files)} parquet files")
        kept = skipped_station = 0
        for fp in files:
            try:
                df = pd.read_parquet(
                    fp, columns=["Samplingpoint", "Pollutant", "Start",
                                 "Value", "Validity", "Verification"])
            except Exception as e:
                print(f"  !! {Path(fp).name}: {e}")
                continue
            if not len(df):
                continue
            pol = int(df["Pollutant"].iloc[0])
            if pol not in POLL:
                continue
            sp = str(df["Samplingpoint"].iloc[0]) + "|" + Path(fp).name
            code = station_code(sp)
            if code not in reg:
                code = next((c for c in sorted(reg, key=len, reverse=True)
                             if c in sp), None)
            if code is None:
                skipped_station += 1
                continue
            df = df[df["Validity"] == 1].copy()
            df["dt_utc"] = pd.to_datetime(df["Start"]) - pd.Timedelta(hours=TZ_OFF)
            df = df[(df["dt_utc"] >= START) & (df["dt_utc"] <= END)]
            if not len(df):
                continue
            city, la, lo = reg[code]
            frames.append(pd.DataFrame({
                "site_id": code, "city": city,
                "latitude": la, "longitude": lo,
                "datetime_utc": df["dt_utc"].dt.strftime("%Y-%m-%d %H:%M"),
                "param": POLL[pol],
                "value": pd.to_numeric(df["Value"], errors="coerce"),
                "verification": df["Verification"].astype("Int64"),
                "prio": prio}))
            kept += 1
        print(f"  kept {kept} files, skipped {skipped_station} unknown-station files")

    if not frames:
        print("[nothing to convert] check EU_raw_v5 contents / date window")
        return
    allrows = pd.concat(frames, ignore_index=True)
    # E1a over E2a per (station, hour, param)
    allrows.sort_values("prio", inplace=True)
    allrows = allrows.drop_duplicates(
        subset=["site_id", "datetime_utc", "param"], keep="first")

    wide = allrows.pivot_table(
        index=["site_id", "city", "latitude", "longitude", "datetime_utc"],
        columns="param", values="value", aggfunc="first").reset_index()
    ver = allrows.groupby(["site_id", "datetime_utc"])["verification"].max()
    wide = wide.merge(ver.rename("verification"),
                      on=["site_id", "datetime_utc"], how="left")
    wide["year"] = wide["datetime_utc"].str[:4]

    print("\n=== Coverage ===")
    for (city, year), g in wide.groupby(["city", "year"]):
        out = OUT/f"{city}_{year}.csv"
        g.drop(columns=["city", "year"]).to_csv(out, index=False)
        vshare = (g["verification"] == 1).mean()*100
        print(f"  {city} {year}: {len(g):>7} station-hours · "
              f"{g['site_id'].nunique()} stations · last {g['datetime_utc'].max()} "
              f"· verified {vshare:.0f}%")

    # --- diurnal sanity check (timezone verification) ---
    print("\n=== Timezone check (O3 diurnal peak, should be ~11-15 UTC) ===")
    chk = wide[wide.get("o3").notna()] if "o3" in wide else pd.DataFrame()
    if len(chk):
        chk = chk.copy()
        chk["hour"] = pd.to_datetime(chk["datetime_utc"]).dt.hour
        peak = chk.groupby("hour")["o3"].mean().idxmax()
        print(f"  mean O3 peaks at {peak}:00 UTC "
              f"{'✓ plausible' if 10 <= peak <= 16 else '!! suspicious: check TZ_OFF'}")
    else:
        print("  (no O3 rows in window for check)")
    print(f"\n-> {OUT}")


if __name__ == "__main__":
    main()
