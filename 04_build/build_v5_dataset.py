"""Build the wno_split_v5/ release tree (per-region per-year CSVs plus
boundary GeoJSONs) from the v5 data files and the master event table.
Run: python3 build_v5_dataset.py --stage split   (stages: us, weather,
eu, split; see STAGES below)
"""

import argparse
import gzip
import io
import json
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

import pandas as pd

BASE = Path.home()/"Desktop/Research/Neural Operators/Data"
EV = BASE/"events_v5_area.xlsx"
USA = BASE/"USA_GMT"                       # existing per-state wide CSVs (2022-24)
NEW = BASE/"USA_GMT_v5"                    # extended per-state data land here
SPLIT = Path.home()/"Desktop/Research/Neural Operators/Data/wno_split_v5"
CUTOFF = "2026-06-30"
YEARS_NEW = [(2025, "2025-01-01", "2025-12-31"), (2026, "2026-01-01", CUTOFF)]

US_REGIONS = {"Arizona": "04", "California": "06", "Nevada": "32",
              "NewMexico": "35", "Utah": "49"}
EU_CITIES = ["Berlin", "Munich", "Paris", "Rome", "Lisbon", "Stockholm"]
AQS_PARAMS = {"88101": "pm25", "81102": "pm10", "42602": "no2",
              "42401": "so2", "42101": "co", "44201": "o3"}

NIFC_API = ("https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/"
            "WFIGS_Incident_Locations_YearToDate/FeatureServer/0/query")
NIFC_HIST = ("https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/"
             "WFIGS_Incident_Locations/FeatureServer/0/query")
NOAA_BULK = "https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/"


def fetch_json(url, tries=3):
    for a in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=180) as r:
                return json.load(r)
        except Exception as e:
            print(f"   retry {a+1}: {e}"); time.sleep(5)
    return None


def load_events():
    return pd.read_excel(EV)


def save_events(ev):
    ev.to_excel(EV, index=False)


# ============================= STAGE: fires =============================
def stage_fires():
    ev = load_events()
    have = set(zip(ev["name"].astype(str), ev["date"].astype(str).str[:10]))
    added = 0
    for endpoint in (NIFC_HIST, NIFC_API):
        for ystart, yend in [("2025-01-01", "2025-12-31"), ("2026-01-01", CUTOFF)]:
            where = (f"FireDiscoveryDateTime >= DATE '{ystart}' AND "
                     f"FireDiscoveryDateTime <= DATE '{yend}' AND "
                     f"IncidentSize >= 500 AND "
                     f"POOState IN ('US-AZ','US-CA','US-NV','US-NM','US-UT')")
            offset = 0
            while True:
                url = endpoint + "?" + urllib.parse.urlencode({
                    "where": where,
                    "outFields": "IncidentName,FireDiscoveryDateTime,"
                                 "InitialLatitude,InitialLongitude,IncidentSize,POOState",
                    "returnGeometry": "false", "f": "json",
                    "resultOffset": offset, "resultRecordCount": 1000})
                js = fetch_json(url)
                feats = (js or {}).get("features", [])
                for f in feats:
                    a = f["attributes"]
                    nm = f"{a.get('IncidentName','?')} Fire"
                    dt = pd.to_datetime(a.get("FireDiscoveryDateTime"), unit="ms")
                    key = (nm, str(dt)[:10])
                    lat, lon = a.get("InitialLatitude"), a.get("InitialLongitude")
                    if key in have or lat is None or lon is None:
                        continue
                    ev.loc[len(ev)] = {**{c: None for c in ev.columns},
                        "name": nm, "date": str(dt)[:10], "type": "wildfire",
                        "tier": 1, "region": "US",
                        "lat": float(lat), "lon": float(lon),
                        "source": "NIFC WFIGS",
                        "notes": f"acres={a.get('IncidentSize')}; state={a.get('POOState')}; v5ext"}
                    have.add(key); added += 1
                if len(feats) < 1000:
                    break
                offset += 1000
        if added:
            break  # historical layer covered it; skip YTD duplicate pass
    save_events(ev)
    print(f"fires: +{added} new wildfire events (2025 - {CUTOFF})")
    print("NEXT: rerun fetch_fire_perimeters.py (then pass-2 + audit) for the new fires")


# ============================= STAGE: dust =============================
def stage_dust():
    ev = load_events()
    have = set(zip(ev["name"].astype(str), ev["date"].astype(str).str[:10]))
    # NCEI bulk files are named ...d2025_c<creation>.csv.gz — find via index
    idx = None
    try:
        with urllib.request.urlopen(NOAA_BULK, timeout=120) as r:
            idx = r.read().decode("utf-8", "ignore")
    except Exception as e:
        print(f"[fail] cannot list NCEI bulk dir: {e}"); return
    added = 0
    for year in (2025, 2026):
        import re
        m = re.findall(rf'(StormEvents_details-ftp_v1\.0_d{year}_c\d+\.csv\.gz)', idx)
        if not m:
            print(f"dust {year}: no bulk file yet"); continue
        fname = sorted(m)[-1]
        print(f"dust {year}: downloading {fname}")
        with urllib.request.urlopen(NOAA_BULK + fname, timeout=600) as r:
            raw = pd.read_csv(io.BytesIO(gzip.decompress(r.read())), low_memory=False)
        raw = raw[raw["EVENT_TYPE"].isin(["Dust Storm", "Dust Devil"]) &
                  raw["STATE"].isin(["ARIZONA", "CALIFORNIA", "NEVADA",
                                     "NEW MEXICO", "UTAH"])]
        raw["BD"] = pd.to_datetime(raw["BEGIN_DATE_TIME"], errors="coerce")
        raw = raw[raw["BD"] <= pd.Timestamp(CUTOFF) + pd.Timedelta(days=1)]
        for _, r2 in raw.iterrows():
            if r2["EVENT_TYPE"] != "Dust Storm":
                continue
            nm = f"Dust storm {r2['CZ_NAME']} {str(r2['BD'])[:10]}"
            key = (nm, str(r2["BD"])[:10])
            if key in have:
                continue
            lat = r2.get("BEGIN_LAT"); lon = r2.get("BEGIN_LON")
            ev.loc[len(ev)] = {**{c: None for c in ev.columns},
                "name": nm, "date": str(r2["BD"])[:10], "type": "dust_storm",
                "tier": 1 if pd.notna(lat) else 2, "region": "US",
                "lat": lat, "lon": lon, "source": "NOAA Storm Events",
                "notes": f"zone={r2.get('CZ_NAME')}; episode={r2.get('EPISODE_ID')}; v5ext"}
            have.add(key); added += 1
    save_events(ev)
    print(f"dust: +{added} new dust events")
    print("NOTE: zone-centroid coords may be missing for Z-type rows -> "
          "fetch_zone_boundaries gives them area geometry later")


# ============================= STAGE: us_data =============================
def aqs_key():
    f = Path.home()/".aqs_key"
    if not f.exists():
        print("[need key] run:  curl 'https://aqs.epa.gov/data/api/signup?email=YOUR@EMAIL'")
        print("then:            echo 'YOUR@EMAIL|YOURKEY' > ~/.aqs_key")
        return None, None
    email, key = f.read_text().strip().split("|")
    return email, key


def stage_us_data():
    email, key = aqs_key()
    if not key:
        return
    NEW.mkdir(parents=True, exist_ok=True)
    for region, fips in US_REGIONS.items():
        frames = []
        for year, bdate, edate in YEARS_NEW:
            for half in ((bdate.replace("-", ""), f"{year}0630"),
                         (f"{year}0701", edate.replace("-", ""))):
                if half[0] > CUTOFF.replace("-", ""):
                    continue
                for param, pname in AQS_PARAMS.items():
                    url = ("https://aqs.epa.gov/data/api/sampleData/byState?" +
                           urllib.parse.urlencode({"email": email, "key": key,
                               "param": param, "bdate": half[0],
                               "edate": min(half[1], CUTOFF.replace("-", "")),
                               "state": fips}))
                    js = fetch_json(url)
                    rows = (js or {}).get("Data", [])
                    print(f"  {region} {pname} {half[0]}-{half[1]}: {len(rows)} rows")
                    for r in rows:
                        frames.append({
                            "site_id": f"{r['state_code']}-{r['county_code']}-{r['site_number']}",
                            "datetime_utc": f"{r['date_gmt']} {r['time_gmt']}",
                            "latitude": r["latitude"], "longitude": r["longitude"],
                            "param": pname, "value": r["sample_measurement"]})
                    time.sleep(6)  # AQS rate limit politeness
        if not frames:
            print(f"{region}: no new data returned"); continue
        df = pd.DataFrame(frames)
        wide = df.pivot_table(index=["site_id", "datetime_utc",
                                     "latitude", "longitude"],
                              columns="param", values="value",
                              aggfunc="first").reset_index()
        out = NEW/f"{region}_2025_2026H1.csv"
        wide.to_csv(out, index=False)
        print(f"{region}: -> {out} ({len(wide)} station-hours)")
        # report true last validated day
        print(f"{region}: last datetime in data = {wide['datetime_utc'].max()}")
    print("\nCHECK the 'last datetime' lines — the minimum across states is the "
          "true v5 cutoff. The release is pinned to that date.")


# ============================= STAGE: weather =============================
def stage_weather():
    NEW.mkdir(exist_ok=True)
    files = list(NEW.glob("*_2025_2026H1.csv"))
    if not files:
        print("run us_data first"); return
    for f in files:
        df = pd.read_csv(f)
        if "temperature_2m" in df.columns:
            print(f"{f.name}: weather already joined"); continue
        stations = df[["site_id", "latitude", "longitude"]].drop_duplicates()
        wmap = {}
        for _, s in stations.iterrows():
            url = ("https://archive-api.open-meteo.com/v1/archive?" +
                   urllib.parse.urlencode({
                       "latitude": s.latitude, "longitude": s.longitude,
                       "start_date": "2025-01-01", "end_date": CUTOFF,
                       "hourly": "temperature_2m,surface_pressure,precipitation,"
                                 "wind_speed_10m,wind_direction_10m",
                       "timezone": "UTC"}))
            js = fetch_json(url)
            if not js or "hourly" not in js:
                print(f"   weather fail {s.site_id}"); continue
            h = js["hourly"]
            wdf = pd.DataFrame(h)
            wdf["datetime_utc"] = pd.to_datetime(wdf["time"]).dt.strftime("%Y-%m-%d %H:%M")
            wmap[s.site_id] = wdf.drop(columns=["time"])
            time.sleep(0.4)
        parts = []
        df["dt_key"] = pd.to_datetime(df["datetime_utc"]).dt.strftime("%Y-%m-%d %H:%M")
        for sid, g in df.groupby("site_id"):
            w = wmap.get(sid)
            if w is None:
                parts.append(g); continue
            parts.append(g.merge(w, left_on="dt_key", right_on="datetime_utc",
                                 how="left", suffixes=("", "_w")))
        out = pd.concat(parts, ignore_index=True).drop(
            columns=[c for c in ("dt_key", "datetime_utc_w") if c in parts[0].columns],
            errors="ignore")
        match = out["temperature_2m"].notna().mean()*100 if "temperature_2m" in out else 0
        out.to_csv(f, index=False)
        print(f"{f.name}: weather joined, match {match:.1f}%")


# ============================= STAGE: eu_data =============================
def stage_eu_data():
    print("EU pollutant data 2025-2026H1:")
    print("  The EEA download service changes frequently; the reliable path is")
    print("  the EEA Air Quality Download interface (Parquet/CSV) in the browser:")
    print("  https://eeadmz1-downloads-webapp.azurewebsites.net/")
    print("  -> select country (DE/FR/IT/PT/SE), pollutants (PM2.5 PM10 NO2 SO2 CO O3),")
    print("     timeframe 2025-01-01 .. 2026-06-30, E1a+UTD")
    print("  -> download, unzip into:  Data/EU_raw_v5/<City>/")
    print("Then rerun this stage: it converts whatever sits in EU_raw_v5/ to our format.")
    src = BASE/"EU_raw_v5"
    if not src.exists():
        print("\n(no EU_raw_v5/ yet — nothing to convert)"); return
    print("\nFound EU_raw_v5 — conversion depends on the delivered schema; "
          "check the delivered schema before converting.")


# ============================= STAGE: split =============================
def stage_split():
    import shutil
    ev = load_events()
    SPLIT.mkdir(parents=True, exist_ok=True)
    # 1. copy v4 tree as the base (2022-24 data unchanged)
    v4 = BASE/"wno_split_v4"
    for p in v4.rglob("*.csv"):
        rel = p.relative_to(v4)
        tgt = SPLIT/rel
        tgt.parent.mkdir(parents=True, exist_ok=True)
        if not tgt.exists():
            shutil.copy(p, tgt)
    # 2. slice new US data per year
    for f in NEW.glob("*_2025_2026H1.csv"):
        region = f.name.split("_")[0]
        df = pd.read_csv(f)
        df["year"] = pd.to_datetime(df["datetime_utc"]).dt.year
        for year, g in df.groupby("year"):
            out = SPLIT/"US"/region/f"{region}_{year}.csv"
            out.parent.mkdir(parents=True, exist_ok=True)
            g.drop(columns=["year"]).to_csv(out, index=False)
            print(f"  {out.relative_to(SPLIT)}: {len(g)} rows")
    # 2b. EU city files
    eudir = BASE/"EU_v5"
    if eudir.exists():
        for f in sorted(eudir.glob("*_20*.csv")):
            city = f.name.split("_")[0]
            out = SPLIT/"EU"/city/f.name
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(f, out)
            print(f"  EU/{city}/{f.name}")
    # 3. events per region-year, with boundary columns
    ev["year"] = ev["date"].astype(str).str[:4]
    bcols = [c for c in ("has_perimeter", "gis_acres", "perimeter_file",
                         "boundary_type", "boundary_file", "perimeter_audit")
             if c in ev.columns]
    for grp, regions in (("US", list(US_REGIONS)), ("EU", EU_CITIES)):
        sub = ev[ev.region.eq(grp)]
        for region in regions:
            for year in ("2022", "2023", "2024", "2025", "2026"):
                # assignment to region by proximity is already encoded in v4
                # events files; for new rows use state in notes / nearest city
                pass
    # simple route: write ALL events of the group per year to each region file
    # is wrong; keep v4 assignment for old rows and assign new rows by state tag
    newev = ev[ev["notes"].astype(str).str.contains("v5ext", na=False)].copy()
    state_map = {"US-AZ": "Arizona", "US-CA": "California", "US-NV": "Nevada",
                 "US-NM": "NewMexico", "US-UT": "Utah"}
    import re as _re
    BBOX = {"Arizona": (31.3, 37.0, -114.9, -109.0),
            "NewMexico": (31.3, 37.0, -109.1, -103.0),
            "Utah": (37.0, 42.0, -114.1, -109.0),
            "Nevada": (35.0, 42.0, -120.0, -114.0),
            "California": (32.5, 42.0, -124.5, -114.1)}
    def region_of(row):
        m = _re.search(r"state=(US-\w\w)", str(row.get("notes")))
        if m:
            return state_map.get(m.group(1))
        try:
            la, lo = float(row["lat"]), float(row["lon"])
        except Exception:
            return None
        for rg, (s, n, w, e) in BBOX.items():
            if s <= la <= n and w <= lo <= e:
                return rg
        return None
    newev["sregion"] = newev.apply(region_of, axis=1)
    for (region, year), g in newev.groupby(["sregion", "year"]):
        if region is None:
            continue
        out = SPLIT/"US"/region/f"{region}_events_{year}.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        cols = ["name", "date", "type", "tier", "region", "lat", "lon",
                "source", "notes"] + bcols
        mode_df = g[cols]
        if out.exists():
            old = pd.read_csv(out)
            mode_df = pd.concat([old, mode_df], ignore_index=True)\
                        .drop_duplicates(subset=["name", "date"])
        mode_df.to_csv(out, index=False)
        print(f"  {out.relative_to(SPLIT)}: {len(mode_df)} events")
    # 4. ship boundaries
    bdir = SPLIT/"_boundaries"
    for sub in ("Perimeters", "Zones"):
        s = BASE/sub
        if s.exists():
            t = bdir/sub; t.mkdir(parents=True, exist_ok=True)
            for gj in s.glob("*.geojson"):
                if not (t/gj.name).exists():
                    shutil.copy(gj, t/gj.name)
    n = sum(1 for _ in SPLIT.rglob("*.csv"))
    nb = sum(1 for _ in (SPLIT/"_boundaries").rglob("*.geojson")) if (SPLIT/"_boundaries").exists() else 0
    print(f"\nwno_split_v5: {n} CSVs, {nb} boundary GeoJSONs -> {SPLIT}")
    print("NOTE: dust 2025+ rows without a state tag and EU events/data need "
          "their stages before this tree is complete; rerun split anytime.")


# ============================= STAGE: status =============================
def stage_status():
    ev = load_events() if EV.exists() else None
    print(f"events_v5_area: {len(ev) if ev is not None else 'MISSING'} rows")
    if ev is not None:
        print(f"  v5ext rows: {ev['notes'].astype(str).str.contains('v5ext', na=False).sum()}")
        print(f"  with boundary_file: {(ev.get('boundary_file').notna().sum() if 'boundary_file' in ev else 0)}")
        print(f"  latest event date: {ev['date'].astype(str).max()[:10]}")
    print(f"USA_GMT_v5 files: {[f.name for f in NEW.glob('*.csv')] if NEW.exists() else 'none'}")
    print(f"wno_split_v5 CSVs: {sum(1 for _ in SPLIT.rglob('*.csv')) if SPLIT.exists() else 0}")


STAGES = {"fires": stage_fires, "dust": stage_dust, "us_data": stage_us_data,
          "weather": stage_weather, "eu_data": stage_eu_data,
          "split": stage_split, "status": stage_status}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True, choices=list(STAGES))
    STAGES[ap.parse_args().stage]()
