"""For each fire event, pull the official ignition point
(InitialLatitude/InitialLongitude) and DiscoveryAcres from NIFC WFIGS,
and compare the ignition point against our perimeter and event
coordinates. Resumable; writes back into events_v5_area.xlsx.
"""

import json
import math
import re
import time
import urllib.parse
import urllib.request

from pathlib import Path

import pandas as pd

BASE = Path.home()/"Desktop/Research/Neural Operators/Data"
EV = BASE/"events_v5_area.xlsx"

SERVICES = [
    ("https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/"
     "WFIGS_Incident_Locations/FeatureServer/0/query"),
    ("https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/"
     "WFIGS_Incident_Locations_YearToDate/FeatureServer/0/query"),
]


def q(base, params, tries=3):
    url = base + "?" + urllib.parse.urlencode(params)
    for a in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                js = json.load(r)
            if "error" in js:
                return js
            return js
        except Exception as e:
            print(f"   retry {a+1}: {e}", flush=True)
            time.sleep(8)
    return None


def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*R*math.asin(math.sqrt(a))


def polygon_rings(geom):
    """all rings of a GeoJSON Polygon/MultiPolygon as [[lon,lat],...] lists"""
    t = geom.get("type")
    if t == "Polygon":
        return list(geom["coordinates"])
    if t == "MultiPolygon":
        return [r for poly in geom["coordinates"] for r in poly]
    return []


def point_in_rings(lon, lat, rings):
    """even-odd ray casting over all rings (handles holes)"""
    inside = False
    for ring in rings:
        j = len(ring) - 1
        for k in range(len(ring)):
            x1, y1 = ring[k][0], ring[k][1]
            x2, y2 = ring[j][0], ring[j][1]
            if (y1 > lat) != (y2 > lat) and \
               lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
                inside = not inside
            j = k
    return inside


def clean_name(n):
    n = str(n).strip()
    n = re.sub(r"\s+(RX\s+)?Fire$", "", n, flags=re.I)
    n = re.sub(r"\s+Rx$", "", n, flags=re.I)
    return n.replace("'", "''")


def pick_service():
    """first service that answers a trivial query"""
    for s in SERVICES:
        js = q(s, {"where": "1=1", "returnCountOnly": "true", "f": "json"},
               tries=1)
        if js and "count" in js:
            print(f"service OK: {s.split('/services/')[1].split('/')[0]} "
                  f"({js['count']:,} incidents)")
            return s
    raise RuntimeError("no WFIGS service reachable")


def main():
    ev = pd.read_excel(EV)
    fires = ev[(ev["type"] == "wildfire") & ev["lat"].notna()].copy()
    fires["year"] = pd.to_datetime(fires["date"]).dt.year
    print(f"fire events to match: {len(fires)}")

    svc = pick_service()

    for c in ("discovery_acres", "discovery_match", "ignition_lat",
              "ignition_lon", "ignition_offset_km", "ignition_in_polygon"):
        if c not in ev.columns:
            ev[c] = pd.NA

    hit = miss = 0
    for i, row in fires.iterrows():
        if pd.notna(ev.at[i, "discovery_acres"]):
            hit += 1
            continue                      # resumable
        nm = clean_name(row["name"])
        la, lo = float(row["lat"]), float(row["lon"])
        y = int(row["year"])
        where = (f"UPPER(IncidentName) LIKE UPPER('%{nm}%') AND "
                 f"FireDiscoveryDateTime >= DATE '{y}-01-01' AND "
                 f"FireDiscoveryDateTime <= DATE '{y}-12-31' AND "
                 f"InitialLatitude >= {la-0.4} AND InitialLatitude <= {la+0.4} AND "
                 f"InitialLongitude >= {lo-0.4} AND InitialLongitude <= {lo+0.4}")
        js = q(svc, {"where": where, "outFields": "*",
                     "returnGeometry": "false", "f": "json"})
        feats = (js or {}).get("features", [])
        if not feats:
            miss += 1
            continue
        # nearest candidate
        def dist(f):
            at = f["attributes"]
            try:
                return ((at.get("InitialLatitude") - la)**2 +
                        (at.get("InitialLongitude") - lo)**2)
            except Exception:
                return 9e9
        at = min(feats, key=dist)["attributes"]
        ev.at[i, "discovery_acres"] = at.get("DiscoveryAcres")
        ev.at[i, "discovery_match"] = at.get("IncidentName")
        ila, ilo = at.get("InitialLatitude"), at.get("InitialLongitude")
        if ila is not None and ilo is not None:
            ev.at[i, "ignition_lat"] = ila
            ev.at[i, "ignition_lon"] = ilo
            ev.at[i, "ignition_offset_km"] = round(
                haversine(la, lo, float(ila), float(ilo)), 2)
        hit += 1
        if (hit + miss) % 25 == 0:
            print(f"   [{hit+miss}/{len(fires)}] matched {hit}", flush=True)
        time.sleep(0.4)

    # --- polygon check: WFIGS ignition point vs our perimeter ---
    pcol = "perimeter_file" if "perimeter_file" in ev.columns else None
    checked = inside = 0
    if pcol:
        for i, row in ev[ev["ignition_lat"].notna() &
                         ev[pcol].notna()].iterrows():
            pf = BASE/str(row[pcol])
            if not pf.exists():
                continue
            try:
                gj = json.loads(pf.read_text())
            except Exception:
                continue
            geom = gj.get("geometry") or (gj.get("features") or
                                          [{}])[0].get("geometry")
            if not geom:
                continue
            rings = polygon_rings(geom)
            if not rings:
                continue
            ev.at[i, "ignition_in_polygon"] = point_in_rings(
                float(row["ignition_lon"]), float(row["ignition_lat"]), rings)
            checked += 1
            if ev.at[i, "ignition_in_polygon"]:
                inside += 1

    bak = EV.with_name("events_v5_area_pre_discoveryacres.xlsx")
    if not bak.exists():
        pd.read_excel(EV).to_excel(bak, index=False)
    ev.to_excel(EV, index=False)

    da = pd.to_numeric(ev["discovery_acres"], errors="coerce").dropna()
    print(f"\nmatched {hit} / {len(fires)} fires (no WFIGS match: {miss})")
    if len(da):
        print(f"DiscoveryAcres  n={len(da)}")
        print(f"  median: {da.median():.2f} acres")
        print(f"  p90:    {da.quantile(0.9):.1f} acres")
        print(f"  share < 1 acre:  {(da < 1).mean()*100:.0f}%")
        print(f"  share < 10 acres: {(da < 10).mean()*100:.0f}%")
        print(f"  max: {da.max():.0f} acres")
    off = pd.to_numeric(ev["ignition_offset_km"], errors="coerce").dropna()
    if len(off):
        print(f"\nour event point vs WFIGS ignition point (n={len(off)}):")
        print(f"  median offset: {off.median():.2f} km · "
              f"p90: {off.quantile(0.9):.1f} km")
    if checked:
        print(f"\nignition point inside our perimeter polygon: "
              f"{inside}/{checked} ({inside/checked*100:.0f}%)")
    print(f"\n-> {EV.name} updated (+backup {bak.name})")


if __name__ == "__main__":
    main()
