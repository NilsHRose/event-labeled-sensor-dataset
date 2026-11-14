"""Pull the official burn perimeter polygon for each matched wildfire from
NIFC WFIGS Interagency Fire Perimeters and save it as
Data/Perimeters/<Fire>_<year>.geojson.
"""

import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

BASE = Path.home()/"Desktop/Research/Neural Operators/Data"
EVENTS = BASE/"events_v5_area.xlsx"
OUTDIR = BASE/"Perimeters"
OUTDIR.mkdir(parents=True, exist_ok=True)

API = ("https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/"
       "WFIGS_Interagency_Perimeters/FeatureServer/0/query")

STATES = {"Arizona": "US-AZ", "California": "US-CA", "Nevada": "US-NV",
          "NewMexico": "US-NM", "Utah": "US-UT"}


def norm(name):
    """normalize an incident name for matching"""
    n = str(name).lower()
    n = re.sub(r"\b(fire|complex|incident)\b", "", n)
    n = re.sub(r"[^a-z0-9]", "", n)
    return n


def query(params):
    url = API + "?" + urllib.parse.urlencode(params)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                return json.load(r)
        except Exception as e:
            print(f"    retry {attempt+1}: {e}")
            time.sleep(5)
    return None


def fetch_state_year(state_code, year):
    """all perimeters for one state+year (paginated)"""
    feats, offset = [], 0
    where = (f"attr_POOState='{state_code}' AND "
             f"attr_FireDiscoveryDateTime >= DATE '{year}-01-01' AND "
             f"attr_FireDiscoveryDateTime < DATE '{year+1}-01-01'")
    while True:
        js = query({
            "where": where,
            "outFields": "poly_IncidentName,attr_FireDiscoveryDateTime,"
                         "poly_GISAcres,attr_IncidentSize",
            "returnGeometry": "true",
            "f": "geojson",
            "resultOffset": offset,
            "resultRecordCount": 500,
        })
        if not js or "features" not in js:
            break
        feats += js["features"]
        if len(js["features"]) < 500:
            break
        offset += 500
    return feats


def main():
    ev = pd.read_excel(EVENTS)
    fires = ev[(ev["type"] == "wildfire") &
               (ev["source"].astype(str).str.contains("NIFC", case=False, na=False))].copy()
    fires["year"] = fires["date"].astype(str).str[:4].astype(int)
    fires["nname"] = fires["name"].apply(norm)
    print(f"Wildfire events to match: {len(fires)}")

    ev["has_perimeter"] = False
    ev["gis_acres"] = None
    ev["perimeter_file"] = None
    report = []

    for region, code in STATES.items():
        for year in sorted(fires[fires.region.eq("US")]["year"].unique()):
            sub = fires[(fires["year"] == year)]
            # only fires plausibly in this state (name-independent; we match by name)
            feats = fetch_state_year(code, int(year))
            print(f"{region} {year}: {len(feats)} perimeters in WFIGS")
            index = {}
            for f in feats:
                p = f.get("properties", {})
                index.setdefault(norm(p.get("poly_IncidentName", "")), []).append(f)
            for i, row in sub.iterrows():
                if ev.at[i, "has_perimeter"]:
                    continue
                cands = index.get(row["nname"], [])
                if not cands:
                    continue
                # largest polygon wins if several share the name
                best = max(cands, key=lambda f: (f["properties"].get("poly_GISAcres") or 0))
                acres = best["properties"].get("poly_GISAcres")
                safe = re.sub(r"[^A-Za-z0-9_-]", "_", str(row["name"]))[:60]
                fname = OUTDIR/f"{safe}_{year}.geojson"
                fname.write_text(json.dumps(best))
                ev.at[i, "has_perimeter"] = True
                ev.at[i, "gis_acres"] = acres
                ev.at[i, "perimeter_file"] = f"Perimeters/{fname.name}"
                report.append({"name": row["name"], "year": year, "region": region,
                               "gis_acres": acres})
            time.sleep(1)

    matched = int(ev["has_perimeter"].sum())
    print(f"\nMatched perimeters: {matched} / {len(fires)} wildfire events")
    pd.DataFrame(report).to_csv(BASE/"perimeter_match_report.csv", index=False)
    ev.to_excel(EVENTS, index=False)
    print(f"-> {BASE/'perimeter_match_report.csv'}")
    print(f"-> {BASE/'events_v5_area.xlsx'}  (updated in place)")
    print(f"-> {matched} GeoJSON files in {OUTDIR}")


if __name__ == "__main__":
    main()
