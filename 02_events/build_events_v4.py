"""Assemble the master event table from the NIFC draft, the NOAA storm
pull, the EU events and the previous master. The manual decisions
(dropped fires, relabeled matches, dust episodes collapsed to one event
each) are encoded here so the build is repeatable.
"""

from pathlib import Path
import pandas as pd

DESK = Path.home() / "Desktop"
DL = Path.home() / "Downloads"
BK = Path.home() / ("Library/CloudStorage/OneDrive-OttawaUniversity/"
                    "Dateien von Anjum, Usman - New Project/Datasets/Combined/Events")

# County centroids for dust-zone coordinate assignment (approx, deg)
ZONE_CENTROIDS = {
    "EAST VALLEY": (33.39, -111.70), "SOUTH MOUNTAIN/AHWATUKEE": (33.34, -112.02),
    "SOUTHEAST VALLEY/QUEEN CREEK": (33.25, -111.63),
    "NORTHWEST DESERTS": (34.60, -114.00), "NORTHWEST VALLEY": (33.65, -112.35),
    "PARKER VALLEY": (34.00, -114.25), "TOHONO O ODHAM NATION": (32.00, -112.00),
    "TONOPAH DESERT": (33.50, -112.95),
    "APPLE AND LUCERNE VALLEYS": (34.47, -117.00), "BAKERSFIELD": (35.37, -119.02),
    "CHUCKWALLA VALLEY": (33.70, -115.30), "COACHELLA VALLEY": (33.70, -116.20),
    "DEATH VALLEY NATIONAL PARK": (36.50, -117.08),
    "EASTERN MOJAVE DESERT": (35.00, -115.50), "WESTERN MOJAVE DESERT": (34.80, -117.80),
    "MOJAVE DESERT": (34.90, -116.80),
    "CENTRAL TULAROSA BASIN": (32.90, -106.10),
    "MIDDLE RIO GRANDE VALLEY/ALBUQUERQUE METRO AREA": (35.08, -106.65),
    "NORTHWEST PLATEAU": (36.50, -108.20), "SANTA FE METRO AREA": (35.68, -105.94),
    "WEST CENTRAL PLATEAU": (34.80, -108.00),
    "SOUTHWEST DESERT/MIMBRES BASIN": (32.30, -107.90),
    "UNION COUNTY": (36.50, -103.50),
    "WESTERN NEVADA BASIN AND RANGE": (39.00, -118.50),
}

COUNTY_CENTROIDS = {
    # Arizona
    "MARICOPA": (33.35, -112.5), "PIMA": (32.1, -111.8), "PINAL": (32.9, -111.3),
    "YUMA": (32.8, -113.9), "LA PAZ": (33.7, -113.98), "COCHISE": (31.88, -109.75),
    "GRAHAM": (32.93, -109.89), "GREENLEE": (33.22, -109.24), "GILA": (33.8, -110.81),
    "SANTA CRUZ": (31.53, -110.85), "MOHAVE": (35.7, -113.76), "NAVAJO": (35.4, -110.32),
    "APACHE": (35.4, -109.49), "COCONINO": (35.84, -111.77), "YAVAPAI": (34.6, -112.55),
    # California
    "IMPERIAL": (33.04, -115.36), "RIVERSIDE": (33.74, -115.99),
    "SAN BERNARDINO": (34.84, -116.18), "KERN": (35.34, -118.73),
    "INYO": (36.51, -117.41), "LOS ANGELES": (34.2, -118.2), "FRESNO": (36.76, -119.65),
    "TULARE": (36.22, -118.8), "KINGS": (36.07, -119.82), "SAN DIEGO": (32.8, -116.7),
    "MONO": (37.94, -118.89), "LASSEN": (40.67, -120.59), "MODOC": (41.59, -120.72),
    "SAN JOAQUIN": (37.93, -121.27), "MERCED": (37.19, -120.72),
    # Nevada
    "CLARK": (36.21, -115.01), "NYE": (38.04, -116.47), "WASHOE": (40.66, -119.66),
    "CHURCHILL": (39.58, -118.34), "ESMERALDA": (37.78, -117.63),
    "LINCOLN": (37.64, -114.88), "MINERAL": (38.54, -118.44), "ELKO": (41.15, -115.36),
    "HUMBOLDT": (41.4, -118.11), "PERSHING": (40.44, -118.4), "LANDER": (39.93, -117.04),
    # New Mexico
    "DONA ANA": (32.35, -106.83), "LUNA": (32.18, -107.75), "HIDALGO": (31.91, -108.71),
    "GRANT": (32.74, -108.38), "SIERRA": (33.13, -107.19), "OTERO": (32.61, -105.74),
    "EDDY": (32.47, -104.3), "CHAVES": (33.36, -104.47), "LEA": (32.79, -103.41),
    "SOCORRO": (34.01, -106.94), "VALENCIA": (34.72, -106.81),
    "BERNALILLO": (35.05, -106.67), "CURRY": (34.57, -103.35),
    "ROOSEVELT": (34.02, -103.48), "QUAY": (35.1, -103.55),
    # Utah
    "MILLARD": (39.07, -113.1), "TOOELE": (40.45, -113.13), "JUAB": (39.7, -112.79),
    "IRON": (37.86, -113.29), "WASHINGTON": (37.28, -113.5), "BEAVER": (38.36, -113.24),
    "SALT LAKE": (40.67, -111.92), "UTAH": (40.12, -111.67), "SEVIER": (38.75, -111.8),
}

TZ_NOTE = {"MST-7": "MST", "PST-8": "PST", "MST": "MST", "PST": "PST"}


def zone_centroid(name):
    n = str(name).upper()
    for zone, ll in ZONE_CENTROIDS.items():
        if zone in n:
            return ll
    for county, ll in COUNTY_CENTROIDS.items():
        if county in n:
            return ll
    return None


def main():
    out_rows = []

    # ---------- 1. WILDFIRES ----------
    draft = pd.read_csv(DESK / "wildfires_v4_draft.csv")
    draft = draft[~draft["name"].str.contains("San Clemente", case=False, na=False)]

    # Contreras relabel: give the NIFC 'Contreras' 2022 AZ row our event_id
    mask = (draft["name"].str.contains("contreras", case=False, na=False)
            & (draft["state"] == "AZ")
            & draft["date"].astype(str).str.startswith("2022"))
    if mask.any():
        draft.loc[mask, "event_id"] = "WF-AZ-2022-Contreas"
        draft.loc[mask, "status"] = "upgraded"
        print(f"[contreras] relabeled {mask.sum()} NIFC row(s)")

    for _, f in draft.iterrows():
        out_rows.append({
            "event_id": f.get("event_id", "") or "",
            "name": f["name"], "type": "wildfire",
            "date": f["date"], "end_date": "",
            "location": f.get("location", ""), "lat": f["lat"], "lon": f["lon"],
            "region": "US", "area": f.get("state", ""),
            "tier": 1, "diffuse": False,
            "source": "NIFC WFIGS", "date_source": "NIFC",
            "source_url": "https://data-nifc.opendata.arcgis.com/",
            "notes": f"acres={f.get('acres','')}; status={f.get('status','')}",
        })

    # OURS_ONLY keeps (tier 2) — all except Contreras (fixed) & San Clemente (dropped)
    rep = pd.read_csv(DESK / "wildfire_match_report.csv")
    ours_only = rep[rep["result"] == "OURS_ONLY"]
    ev_us = pd.read_excel(DL / "events.xlsx")
    for _, r in ours_only.iterrows():
        if "Contreas" in str(r["event_id"]) or "SanClemente" in str(r["event_id"]):
            continue
        orig = ev_us[ev_us["event_id"] == r["event_id"]]
        if not len(orig):
            continue
        o = orig.iloc[0]
        out_rows.append({
            "event_id": o["event_id"], "name": o["name"], "type": "wildfire",
            "date": str(o["date"])[:10], "end_date": str(o.get("end_date", ""))[:10],
            "location": o.get("location", ""), "lat": o.get("lat"), "lon": o.get("lon"),
            "region": "US", "area": r["state"],
            "tier": 2, "diffuse": False,
            "source": "Wikipedia/CAL FIRE (below NIFC size cut)",
            "date_source": "year_only_placeholder",
            "source_url": o.get("source_url", ""),
            "notes": "small fire; real dates pending manual lookup",
        })

    # ---------- 2. NOAA DUST + HEAT (collapse episodes) ----------
    noaa = pd.read_csv(DESK / "noaa_storms_2022_2024.csv")

    for etype, tier, diffuse in [("dust_storm", 1, False), ("heatwave", 3, True)]:
        sub = noaa[noaa["type"] == etype].copy()
        grouped = sub.groupby("episode_id")
        n_ep = 0
        for ep_id, g in grouped:
            g = g.sort_values(["date", "begin_time_local"])
            first = g.iloc[0]
            # coords: first row with coords, else zone centroid lookup
            lat, lon, coord_src = None, None, "missing"
            with_coords = g[~g["coords_missing"]]
            if len(with_coords):
                lat, lon = with_coords.iloc[0]["lat"], with_coords.iloc[0]["lon"]
                coord_src = "noaa"
            else:
                for _, row in g.iterrows():
                    c = zone_centroid(row["location"])
                    if c:
                        lat, lon = c
                        coord_src = "county_centroid"
                        break
            zones = "; ".join(sorted(set(g["location"].astype(str))))[:150]
            eff_tier = tier if (lat is not None or tier == 3) else 2
            out_rows.append({
                "event_id": f"NOAA-{etype[:4].upper()}-{ep_id}",
                "name": f"{first['origin']} {first['date']} ({first['state']})",
                "type": etype,
                "date": first["date"], "end_date": g.iloc[-1]["end_date"],
                "location": zones,
                "lat": lat, "lon": lon,
                "region": "US", "area": {"Arizona":"AZ","California":"CA","New Mexico":"NM","Nevada":"NV","Utah":"UT"}.get(first["state"], first["state"]),
                "tier": eff_tier, "diffuse": diffuse,
                "source": "NOAA NCEI Storm Events", "date_source": "NOAA",
                "source_url": "https://www.ncdc.noaa.gov/stormevents/",
                "notes": (f"begin {first['begin_time_local']} {first['timezone']}; "
                          f"coords={coord_src}; zones={len(g)}"),
            })
            n_ep += 1
        print(f"[noaa] {etype}: {len(sub)} rows -> {n_ep} episodes")

    # old weather.gov dust: superseded by NOAA (same storms) — skip, note count
    old_dust = ev_us[ev_us["type"] == "dust_storm"]
    print(f"[dedup] old weather.gov dust events superseded by NOAA: {len(old_dust)}")

    # ---------- 3. old US atmospheric rivers + heat (tier 3) ----------
    for t in ["atmospheric_river", "heatwave"]:
        for _, o in ev_us[ev_us["type"] == t].iterrows():
            out_rows.append({
                "event_id": o["event_id"], "name": o["name"], "type": t,
                "date": str(o["date"])[:10], "end_date": str(o.get("end_date", ""))[:10],
                "location": o.get("location", ""), "lat": o.get("lat"),
                "lon": o.get("lon"), "region": "US",
                "area": "", "tier": 3, "diffuse": True,
                "source": "curated (Wikipedia/NASA)", "date_source": "manual",
                "source_url": o.get("source_url", ""), "notes": "diffuse regional event",
            })

    # ---------- 4. EU ----------
    eu = pd.read_csv(BK / "events_eu_v2.csv")
    eu["pdate"] = pd.to_datetime(eu["date"], errors="coerce")
    tiers_eu = {"fireworks": (1, False), "festival": (2, False),
                "oktoberfest": (2, False), "christmas_market": (2, False)}
    for _, o in eu.iterrows():
        t = o["type"]
        tier, diffuse = tiers_eu.get(t, (3, True))
        d = o["pdate"]
        out_rows.append({
            "event_id": o["event_id"], "name": o["name"], "type": t,
            "date": d.strftime("%Y-%m-%d") if pd.notna(d) else "",
            "end_date": "", "location": o.get("location", ""),
            "lat": o.get("lat"), "lon": o.get("lon"), "region": "EU",
            "area": "", "tier": tier, "diffuse": diffuse,
            "source": "curated (public records)", "date_source": "manual",
            "source_url": o.get("source_url", ""), "notes": str(o.get("notes", ""))[:150],
        })

    # ---------- 5. GLOBAL -> transport, tier 3 ----------
    gl = pd.read_csv(DL / "events_global.csv")
    for _, o in gl.iterrows():
        out_rows.append({
            "event_id": o["event_id"], "name": o["name"],
            "type": f"transport_{o['type']}",
            "date": str(o["date"])[:10], "end_date": str(o.get("end_date", ""))[:10],
            "location": o.get("location", ""), "lat": o.get("lat"),
            "lon": o.get("lon"), "region": "Global",
            "area": "", "tier": 3, "diffuse": True,
            "source": "curated (NASA/USGS/Copernicus)", "date_source": "manual",
            "source_url": o.get("source_url", ""),
            "notes": "source outside sensor network -> transport",
        })

    # ---------- write ----------
    v4 = pd.DataFrame(out_rows)
    out = DESK / "events_v4.xlsx"
    v4.to_excel(out, index=False)

    print(f"\n=== events_v4: {len(v4)} events -> {out} ===")
    print("\nBy tier:")
    print(v4["tier"].value_counts().sort_index().to_string())
    print("\nTier 1 by area × year (US):")
    t1 = v4[(v4.tier == 1) & (v4.region == "US")].copy()
    t1["year"] = t1["date"].astype(str).str[:4]
    print(pd.crosstab(t1["area"], t1["year"]).to_string())
    print("\nTier 1+2 EU by year:")
    eu12 = v4[(v4.region == "EU") & (v4.tier <= 2)].copy()
    eu12["year"] = eu12["date"].astype(str).str[:4]
    print(eu12.groupby("year").size().to_string())


if __name__ == "__main__":
    main()