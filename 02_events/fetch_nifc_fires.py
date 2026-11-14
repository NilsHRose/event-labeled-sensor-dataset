"""Query the NIFC WFIGS incident FeatureServer for 2022-2024 wildfires in
AZ/CA/NM/NV/UT above MIN_ACRES and write nifc_fires_2022_2024.csv in our
events schema.
Run: python3 fetch_nifc_fires.py
"""

import argparse
import csv
import datetime as dt
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services"
CANDIDATE_LAYERS = [
    "WFIGS_Incident_Locations_Full_History",
    "WFIGS_Wildland_Fire_Locations_Full_History",
    "WFIGS_Incident_Locations",
    "WFIGS_Incident_Locations_YearToDate",
]

STATES = ["US-AZ", "US-CA", "US-NM", "US-NV", "US-UT"]
STATE_NAMES = {"US-AZ": "Arizona", "US-CA": "California", "US-NM": "New Mexico",
               "US-NV": "Nevada", "US-UT": "Utah"}

WHERE = ("POOState IN ({states}) AND "
         "FireDiscoveryDateTime >= TIMESTAMP '2022-01-01 00:00:00' AND "
         "FireDiscoveryDateTime <  TIMESTAMP '2025-01-01 00:00:00'"
         ).format(states=",".join(f"'{s}'" for s in STATES))

ACRE_FIELDS = ["IncidentSize", "DailyAcres", "CalculatedAcres", "DiscoveryAcres"]


def http_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "wno-research/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def query_url(layer, params):
    return (f"{BASE}/{layer}/FeatureServer/0/query?"
            + urllib.parse.urlencode(params))


def pick_layer():
    for layer in CANDIDATE_LAYERS:
        try:
            data = http_json(query_url(layer, {
                "where": WHERE, "returnCountOnly": "true", "f": "json"}))
            count = data.get("count")
            if count is not None:
                print(f"[endpoint] {layer}: {count} matching incidents")
                if count > 0:
                    return layer, count
        except Exception as e:
            print(f"[endpoint] {layer}: not usable ({e})")
    print("[fatal] no endpoint answered with data")
    sys.exit(1)


def fetch_all(layer, total):
    feats, offset = [], 0
    while offset < total:
        data = http_json(query_url(layer, {
            "where": WHERE,
            "outFields": "*",
            "returnGeometry": "true",
            "resultOffset": offset,
            "resultRecordCount": 1000,
            "f": "json",
        }))
        batch = data.get("features", [])
        if not batch:
            break
        feats.extend(batch)
        offset += len(batch)
        print(f"  fetched {offset}/{total}", end="\r")
    print()
    return feats


def epoch_to_date(ms):
    if not ms:
        return ""
    try:
        return dt.datetime.utcfromtimestamp(ms / 1000).strftime("%Y-%m-%d")
    except Exception:
        return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-acres", type=float, default=500.0)
    args = ap.parse_args()

    layer, total = pick_layer()
    print(f"Fetching {total} incidents from {layer} ...")
    feats = fetch_all(layer, total)
    print(f"Got {len(feats)} features")

    rows = []
    for f in feats:
        a = f.get("attributes", {})
        geom = f.get("geometry") or {}

        acres = None
        for fld in ACRE_FIELDS:
            v = a.get(fld)
            if v is not None:
                acres = v
                break
        if acres is None or acres < args.min_acres:
            continue

        lat = a.get("InitialLatitude") or geom.get("y")
        lon = a.get("InitialLongitude") or geom.get("x")
        if lat is None or lon is None:
            continue

        state = STATE_NAMES.get(a.get("POOState", ""), a.get("POOState", ""))
        county = a.get("POOCounty", "") or ""
        name = a.get("IncidentName", "Unknown") or "Unknown"

        rows.append({
            "name": f"{name.strip().title()} Fire" if "fire" not in name.lower() else name.strip().title(),
            "type": "wildfire",
            "date": epoch_to_date(a.get("FireDiscoveryDateTime")),
            "end_date": epoch_to_date(a.get("ContainmentDateTime")
                                      or a.get("FireOutDateTime")),
            "location": f"{county} County, {state}" if county else state,
            "lat": round(float(lat), 5),
            "lon": round(float(lon), 5),
            "region": "US",
            "origin": "natural/human (see cause)",
            "source_url": "https://data-nifc.opendata.arcgis.com/",
            "notes": f"acres={acres}; cause={a.get('FireCause','')}",
            "acres": acres,
            "cause": a.get("FireCause", ""),
            "state": state,
        })

    rows.sort(key=lambda r: (r["state"], r["date"]))
    out = Path.home() / "Desktop" / "nifc_fires_2022_2024.csv"
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    print(f"\nWrote {len(rows)} fires >= {args.min_acres} acres to {out}")
    by_state = {}
    for r in rows:
        by_state[r["state"]] = by_state.get(r["state"], 0) + 1
    for s, n in sorted(by_state.items()):
        print(f"  {s}: {n}")


if __name__ == "__main__":
    main()