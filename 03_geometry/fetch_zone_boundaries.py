"""Fetch the NWS Public Forecast Zone polygon for each zone-based NOAA
event (dust storms, heat), so area events carry their official boundary.
The zone identity (STATE + CZ_TYPE + CZ_FIPS) comes from the NOAA raw
pull.
"""

import json
import math
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

BASE = Path.home()/"Desktop/Research/Neural Operators/Data"
EV = BASE/"events_v5_area.xlsx"
RAW = BASE/"EventSources/noaa_storms_2022_2024.csv"
ZDIR = BASE/"Zones"; ZDIR.mkdir(exist_ok=True)

# NOAA IDP map service for public forecast zones (ArcGIS REST, like WFIGS)
ZONE_API = ("https://mapservices.weather.noaa.gov/static/rest/services/"
            "nws_reference_maps/nws_public_forecast_zones/MapServer/0/query")

STATE_ABBR = {"Arizona": "AZ", "California": "CA", "Nevada": "NV",
              "New Mexico": "NM", "NEW MEXICO": "NM", "Utah": "UT",
              "ARIZONA": "AZ", "CALIFORNIA": "CA", "NEVADA": "NV", "UTAH": "UT"}

ZONE_TYPES = {"dust_storm", "heatwave", "atmospheric_river"}


def q(params):
    url = ZONE_API + "?" + urllib.parse.urlencode(params)
    for a in range(3):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                return json.load(r)
        except Exception as e:
            print(f"   retry {a+1}: {e}")
            time.sleep(4)
    return None


def fetch_zone(state, fips):
    """one zone polygon by state + zone number"""
    zid = f"{state}Z{int(fips):03d}"
    f = ZDIR/f"{zid}.geojson"
    if f.exists():
        return f
    js = q({"where": f"STATE='{state}' AND ZONE='{int(fips):03d}'",
            "outFields": "STATE,ZONE,NAME",
            "returnGeometry": "true", "f": "geojson",
            "outSR": "4326"})
    feats = (js or {}).get("features", [])
    if not feats:
        return None
    f.write_text(json.dumps(feats[0]))
    return f


def main():
    ev = pd.read_excel(EV)
    raw = pd.read_csv(RAW, low_memory=False)
    raw.columns = [c.upper() for c in raw.columns]
    # keep zone-coded rows for our event kinds
    raw = raw[raw["CZ_TYPE"].astype(str).str.upper().eq("Z")].copy()
    raw["STATE2"] = raw["STATE"].map(lambda s: STATE_ABBR.get(str(s).strip(), None))
    raw = raw[raw["STATE2"].notna()]
    raw["BDATE"] = pd.to_datetime(raw["BEGIN_DATE_TIME"], errors="coerce").dt.date

    # unified boundary columns
    if "boundary_type" not in ev.columns:
        ev["boundary_type"] = None
        ev["boundary_file"] = None
    # carry fires over
    fire_mask = ev.get("has_perimeter") == True
    ev.loc[fire_mask, "boundary_type"] = "fire_perimeter"
    ev.loc[fire_mask, "boundary_file"] = ev.loc[fire_mask, "perimeter_file"]

    zev = ev[ev["type"].isin(ZONE_TYPES) & ev["lat"].notna()].copy()
    zev["edate"] = pd.to_datetime(zev["date"], errors="coerce").dt.date
    print(f"Zone-type events to bound: {len(zev)}")

    matched, fetched_fail = 0, 0
    for i, row in zev.iterrows():
        cands = raw[raw["BDATE"] == row["edate"]]
        if not len(cands):
            continue
        # nearest raw record by centroid distance
        d = ((cands["BEGIN_LAT"].astype(float) - row["lat"])**2 +
             (cands["BEGIN_LON"].astype(float) - row["lon"])**2)
        if not len(d.dropna()):
            # zone rows often lack begin lat/lon -> fall back to name overlap
            nm = str(row["name"]).lower()
            cands = cands[cands["CZ_NAME"].astype(str).str.lower()
                          .apply(lambda z: any(w in nm for w in z.split()[:2]))]
            if not len(cands):
                continue
            best = cands.iloc[0]
        else:
            best = cands.loc[d.idxmin()]
        zf = fetch_zone(best["STATE2"], best["CZ_FIPS"])
        if zf is None:
            fetched_fail += 1
            continue
        ev.at[i, "boundary_type"] = "nws_zone"
        ev.at[i, "boundary_file"] = f"Zones/{zf.name}"
        matched += 1
        time.sleep(0.3)

    ev.to_excel(EV, index=False)
    print(f"\nZone boundaries assigned: {matched} / {len(zev)}")
    if fetched_fail:
        print(f"Zone polygon fetch failures: {fetched_fail} (service/zone-id mismatches)")
    bt = ev["boundary_type"].value_counts(dropna=False)
    print("\nBoundary coverage now:")
    print(bt.to_string())
    print(f"\n-> events_v5_area.xlsx updated (boundary_type / boundary_file)")
    print(f"-> zone polygons in {ZDIR}")


if __name__ == "__main__":
    main()
