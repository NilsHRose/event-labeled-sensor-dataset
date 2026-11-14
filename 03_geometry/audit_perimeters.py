"""Check every matched wildfire polygon: is the ignition point inside (or
within 5 km of) the perimeter, is gis_acres within 0.3x-4x of the
reported acres, and is the perimeter date within +-3 days of ours.
Verdicts are written back per event.
"""

import json
import math
import re
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

BASE = Path.home()/"Desktop/Research/Neural Operators/Data"
EV = BASE/"events_v5_area.xlsx"


# ---------- geometry helpers (stdlib only) ----------
def point_in_ring(lon, lat, ring):
    """ray casting"""
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[(i+1) % n][0], ring[(i+1) % n][1]
        if (y1 > lat) != (y2 > lat):
            xint = (x2-x1) * (lat-y1) / (y2-y1 + 1e-12) + x1
            if lon < xint:
                inside = not inside
    return inside


def point_in_geom(lon, lat, geom):
    t = geom.get("type")
    if t == "Polygon":
        rings = geom["coordinates"]
        if not rings: return False
        if not point_in_ring(lon, lat, rings[0]): return False
        return not any(point_in_ring(lon, lat, h) for h in rings[1:])
    if t == "MultiPolygon":
        return any(point_in_geom(lon, lat, {"type": "Polygon", "coordinates": p})
                   for p in geom["coordinates"])
    return False


def min_dist_km(lon, lat, geom):
    """rough min distance from point to any polygon vertex (upper bound)"""
    best = float("inf")
    def rings_of(g):
        if g["type"] == "Polygon":
            for r in g["coordinates"]: yield r
        elif g["type"] == "MultiPolygon":
            for p in g["coordinates"]:
                for r in p: yield r
    for ring in rings_of(geom):
        for x, y in ring[::max(1, len(ring)//200)]:  # subsample long rings
            d = math.hypot((x-lon)*111.32*math.cos(math.radians(lat)),
                           (y-lat)*110.57)
            if d < best: best = d
    return best


def main():
    ev = pd.read_excel(EV)
    m = ev[ev.get("has_perimeter") == True].copy()
    print(f"Auditing {len(m)} matched perimeters...")

    results = []
    ev["perimeter_audit"] = None
    for i, row in m.iterrows():
        flags = []
        try:
            gj = json.loads((BASE/row["perimeter_file"]).read_text())
        except Exception as e:
            ev.at[i, "perimeter_audit"] = "ERROR: file"
            results.append({"name": row["name"], "audit": "ERROR: file"})
            continue
        geom = gj.get("geometry") or {}
        props = gj.get("properties", {})

        # 1. point-in-polygon (or near)
        inside = point_in_geom(row["lon"], row["lat"], geom)
        dist = 0.0 if inside else min_dist_km(row["lon"], row["lat"], geom)
        if not inside and dist > 5.0:
            flags.append(f"point_outside({dist:.1f}km)")

        # 2. size ratio
        rep = None
        mm = re.search(r"acres=([\d.]+)", str(row.get("notes")))
        if mm: rep = float(mm.group(1))
        ga = row.get("gis_acres")
        ratio = None
        if rep and ga and rep > 0:
            ratio = ga/rep
            if not (0.3 <= ratio <= 4.0):
                flags.append(f"size_ratio({ratio:.2f})")

        # 3. date match
        pd_ms = props.get("attr_FireDiscoveryDateTime")
        ddays = None
        if pd_ms:
            try:
                pdate = datetime.utcfromtimestamp(pd_ms/1000)
                edate = pd.to_datetime(row["date"])
                ddays = abs((pdate - edate.to_pydatetime()).days)
                if ddays > 3:
                    flags.append(f"date_off({ddays}d)")
            except Exception:
                pass

        verdict = "pass" if not flags else "; ".join(flags)
        ev.at[i, "perimeter_audit"] = verdict
        results.append({"name": row["name"], "date": str(row["date"])[:10],
                        "region": row.get("region"),
                        "inside": inside, "dist_km": round(dist, 1),
                        "size_ratio": round(ratio, 2) if ratio else None,
                        "date_diff_days": ddays, "audit": verdict})

    rep = pd.DataFrame(results)
    rep.to_csv(BASE/"perimeter_audit.csv", index=False)
    ev.to_excel(EV, index=False)

    npass = (rep["audit"] == "pass").sum()
    print(f"\n=== AUDIT RESULT ===")
    print(f"pass: {npass} / {len(rep)}  ({100*npass/max(1,len(rep)):.1f}%)")
    print("\nFlag breakdown:")
    flagged = rep[rep["audit"] != "pass"]
    for kind in ["point_outside", "size_ratio", "date_off", "ERROR"]:
        n = flagged["audit"].astype(str).str.contains(kind).sum()
        if n: print(f"  {kind}: {n}")
    if len(flagged):
        print("\nWorst offenders (first 10):")
        print(flagged.head(10).to_string(index=False))
    print(f"\n-> {BASE/'perimeter_audit.csv'}")
    print("-> events_v5_area.xlsx updated with 'perimeter_audit' column")


if __name__ == "__main__":
    main()
