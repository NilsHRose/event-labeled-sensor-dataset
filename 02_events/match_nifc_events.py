"""Deduplicate the NIFC fire pull against our existing wildfire events by
name, year and coordinates. Writes wildfires_v4_draft.csv and a match
report for manual review.
"""

import math
import re
from pathlib import Path
import pandas as pd

DESK = Path.home() / "Desktop"
NIFC_CSV = DESK / "nifc_fires_2022_2024.csv"
EVENTS_XLSX = Path.home() / "Downloads" / "events.xlsx"

STATE_MAP = {"Arizona": "AZ", "California": "CA", "New Mexico": "NM",
             "Nevada": "NV", "Utah": "UT"}


def norm_name(s):
    s = str(s).lower()
    s = re.sub(r"\b(fire|complex|wildfire)\b", "", s)
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s.strip()


def state_of(loc):
    loc = str(loc).lower()
    for full, ab in [("arizona", "AZ"), ("california", "CA"), ("new mexico", "NM"),
                     ("nevada", "NV"), ("utah", "UT"), ("colorado", "CO")]:
        if full in loc:
            return ab
    return "?"


def haversine_km(a, b, c, d):
    r = 6371.0
    p1, p2 = math.radians(a), math.radians(c)
    dp = math.radians(c - a)
    dl = math.radians(d - b)
    x = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * r * math.asin(math.sqrt(x))


def main():
    nifc = pd.read_csv(NIFC_CSV)
    ev = pd.read_excel(EVENTS_XLSX)

    ours = ev[ev["type"] == "wildfire"].copy()
    print(f"Our wildfires: {len(ours)} | NIFC fires: {len(nifc)}")

    ours["nname"] = ours["name"].apply(norm_name)
    ours["state"] = ours["location"].apply(state_of)
    ours["year"] = pd.to_datetime(ours["date"], errors="coerce").dt.year

    nifc["nname"] = nifc["name"].apply(norm_name)
    nifc["st"] = nifc["state"].map(STATE_MAP).fillna("?")
    nifc["year"] = pd.to_datetime(nifc["date"], errors="coerce").dt.year

    nifc_used = set()
    report = []

    for i, o in ours.iterrows():
        cand = nifc[(nifc["st"] == o["state"]) & (nifc["year"] == o["year"])]
        match_idx, how, dist = None, "", None

        # 1. name match
        exact = cand[cand["nname"] == o["nname"]]
        if len(exact):
            match_idx, how = exact.index[0], "name"
        else:
            # partial name containment
            part = cand[cand["nname"].apply(
                lambda n: bool(n) and (n in o["nname"] or o["nname"] in n))]
            if len(part):
                match_idx, how = part.index[0], "name_partial"

        # 2. coordinate match
        if match_idx is None and pd.notna(o.get("lat")) and pd.notna(o.get("lon")):
            best, bestd = None, 1e9
            for j, n in cand.iterrows():
                d = haversine_km(o["lat"], o["lon"], n["lat"], n["lon"])
                if d < bestd:
                    best, bestd = j, d
            if best is not None and bestd <= 30:
                match_idx, how, dist = best, "coords", round(bestd, 1)

        if match_idx is not None:
            nifc_used.add(match_idx)
            n = nifc.loc[match_idx]
            report.append({
                "event_id": o.get("event_id", ""), "our_name": o["name"],
                "state": o["state"], "year": o["year"],
                "result": "MATCHED", "how": how, "dist_km": dist,
                "nifc_name": n["name"], "nifc_date": n["date"],
                "nifc_lat": n["lat"], "nifc_lon": n["lon"],
                "acres": n.get("acres", ""),
            })
        else:
            report.append({
                "event_id": o.get("event_id", ""), "our_name": o["name"],
                "state": o["state"], "year": o["year"],
                "result": "OURS_ONLY", "how": "", "dist_km": None,
                "nifc_name": "", "nifc_date": "", "nifc_lat": "",
                "nifc_lon": "", "acres": "",
            })

    rep = pd.DataFrame(report)
    rep.to_csv(DESK / "wildfire_match_report.csv", index=False)

    matched = rep[rep.result == "MATCHED"]
    print(f"\nMATCHED: {len(matched)} / {len(ours)}")
    print(matched["how"].value_counts().to_string())
    print(f"OURS_ONLY (review): {len(rep) - len(matched)}")

    nifc_new = nifc[~nifc.index.isin(nifc_used)].copy()
    print(f"NIFC_NEW (addition candidates): {len(nifc_new)}")
    print(nifc_new.groupby("st").size().to_string())

    # Build the v4 wildfire draft
    rows = []
    for _, r in matched.iterrows():
        rows.append({
            "event_id": r["event_id"], "name": r["our_name"], "type": "wildfire",
            "date": r["nifc_date"], "location": "", "lat": r["nifc_lat"],
            "lon": r["nifc_lon"], "region": "US", "state": r["state"],
            "source": "NIFC WFIGS", "tier": 1, "date_source": "NIFC",
            "acres": r["acres"], "status": "upgraded",
        })
    for _, n in nifc_new.iterrows():
        rows.append({
            "event_id": "", "name": n["name"], "type": "wildfire",
            "date": n["date"], "location": n["location"], "lat": n["lat"],
            "lon": n["lon"], "region": "US", "state": n["st"],
            "source": "NIFC WFIGS", "tier": 1, "date_source": "NIFC",
            "acres": n.get("acres", ""), "status": "new",
        })
    draft = pd.DataFrame(rows)
    draft.to_csv(DESK / "wildfires_v4_draft.csv", index=False)

    print(f"\nWrote wildfire_match_report.csv + wildfires_v4_draft.csv "
          f"({len(draft)} fires) to Desktop")
    print("\nPer state × year in the draft:")
    draft["year"] = pd.to_datetime(draft["date"], errors="coerce").dt.year
    print(pd.crosstab(draft["state"], draft["year"]).to_string())


if __name__ == "__main__":
    main()