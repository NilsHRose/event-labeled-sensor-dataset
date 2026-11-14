"""Download NASA FIRMS VIIRS country CSVs (DE/FR/IT/PT/SE, 2022-2024),
keep detections within RADIUS_KM of our six cities and cluster them into
fire events (same or consecutive days within ~5 km, >= MIN_DETECTIONS).
Writes firms_eu_fires_2022_2024.csv.
Run: python3 fetch_firms_eu_fires.py
"""

import argparse
import csv
import io
import math
import urllib.request
from pathlib import Path

import pandas as pd

CITIES = {
    "Berlin": (52.52, 13.405), "Munich": (48.137, 11.575),
    "Paris": (48.857, 2.352), "Rome": (41.902, 12.496),
    "Lisbon": (38.722, -9.139), "Stockholm": (59.329, 18.069),
}
CITY_COUNTRY = {"Berlin": "Germany", "Munich": "Germany", "Paris": "France",
                "Rome": "Italy", "Lisbon": "Portugal", "Stockholm": "Sweden"}
COUNTRIES = sorted(set(CITY_COUNTRY.values()))
YEARS = ["2022", "2023", "2024"]

URL_PATTERNS = [
    "https://firms.modaps.eosdis.nasa.gov/data/country/viirs-snpp/{y}/viirs-snpp_{y}_{c}.csv",
    "https://firms.modaps.eosdis.nasa.gov/data/country/zips/viirs-snpp_{y}_{c}.csv",
    "https://firms2.modaps.eosdis.nasa.gov/data/country/viirs-snpp/{y}/viirs-snpp_{y}_{c}.csv",
    "https://firms.modaps.eosdis.nasa.gov/data/country/modis/{y}/modis_{y}_{c}.csv",
]


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * r * math.asin(math.sqrt(a))


def fetch_country_year(country, year):
    for pat in URL_PATTERNS:
        url = pat.format(y=year, c=country)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "wno-research/1.0"})
            with urllib.request.urlopen(req, timeout=120) as r:
                raw = r.read()
            df = pd.read_csv(io.BytesIO(raw))
            if "latitude" in df.columns:
                print(f"  {country} {year}: {len(df):,} detections  [{url.split('/data/')[1][:40]}...]")
                return df
        except Exception:
            continue
    print(f"  {country} {year}: NO WORKING URL")
    return None


def cluster_events(det, city, args):
    """det: detections near one city. Returns list of event dicts."""
    if not len(det):
        return []
    det = det.sort_values("acq_date").reset_index(drop=True)
    det["cluster"] = -1
    cid = 0
    events = []

    # simple spatio-temporal single-link: same cluster if within 5 km and <= 2 days
    for i in det.index:
        if det.at[i, "cluster"] >= 0:
            continue
        det.at[i, "cluster"] = cid
        members = [i]
        queue = [i]
        while queue:
            j = queue.pop()
            dj = det.loc[j]
            for k in det.index:
                if det.at[k, "cluster"] >= 0:
                    continue
                dk = det.loc[k]
                days = abs((pd.Timestamp(dk["acq_date"]) - pd.Timestamp(dj["acq_date"])).days)
                if days > 2:
                    continue
                if haversine_km(dj["latitude"], dj["longitude"],
                                dk["latitude"], dk["longitude"]) <= 5:
                    det.at[k, "cluster"] = cid
                    members.append(k)
                    queue.append(k)
        g = det.loc[members]
        if len(g) >= args.min_detections:
            lat, lon = g["latitude"].mean(), g["longitude"].mean()
            clat, clon = CITIES[city]
            events.append({
                "name": f"Fire near {city} {g['acq_date'].min()}",
                "type": "wildfire",
                "date": g["acq_date"].min(),
                "end_date": g["acq_date"].max(),
                "location": f"near {city}",
                "lat": round(lat, 5), "lon": round(lon, 5),
                "region": "EU", "area": city,
                "tier": 1, "diffuse": False,
                "source": "NASA FIRMS (VIIRS S-NPP)",
                "date_source": "FIRMS",
                "source_url": "https://firms.modaps.eosdis.nasa.gov/",
                "notes": (f"n_detections={len(g)}; frp_sum="
                          f"{round(g.get('frp', pd.Series(dtype=float)).sum(),1)}; "
                          f"dist_km={round(haversine_km(lat, lon, clat, clon),1)}"),
                "n_detections": len(g),
                "city": city,
            })
        cid += 1
    return events


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--radius", type=float, default=50.0)
    ap.add_argument("--min-detections", type=int, default=3)
    args = ap.parse_args()

    all_events = []
    for country in COUNTRIES:
        cities = [c for c, co in CITY_COUNTRY.items() if co == country]
        for year in YEARS:
            df = fetch_country_year(country, year)
            if df is None:
                continue
            df = df[df["acq_date"].astype(str).str.startswith(tuple(YEARS))]
            for city in cities:
                clat, clon = CITIES[city]
                near = df[
                    (df["latitude"].between(clat - 1, clat + 1)) &
                    (df["longitude"].between(clon - 1.5, clon + 1.5))
                ].copy()
                if len(near):
                    near["dist"] = near.apply(
                        lambda r: haversine_km(r["latitude"], r["longitude"], clat, clon), axis=1)
                    near = near[near["dist"] <= args.radius]
                evs = cluster_events(near, city, args)
                if evs:
                    print(f"    -> {city}: {len(near)} detections -> {len(evs)} events")
                all_events.extend(evs)

    out = Path.home() / "Desktop" / "firms_eu_fires_2022_2024.csv"
    if all_events:
        df = pd.DataFrame(all_events).sort_values(["city", "date"])
        df.to_csv(out, index=False)
        print(f"\nWrote {len(df)} EU fire events to {out}")
        print(df.groupby("city").size().to_string())
    else:
        print("\nNo qualifying fire events found near the cities "
              "(in-network criterion is strict; this is a valid result).")


if __name__ == "__main__":
    main()