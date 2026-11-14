"""Plot the time series of the nearest sensors around any event in
events_v5_area.xlsx: one panel per feature, one line per sensor, event
time marked.
"""

import argparse
import math
import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

BASE = Path.home()/"Desktop/Research/Neural Operators"
SPLIT = BASE/"Data/wno_split_v5"
EVENTS = BASE/"Data/events_v5_area.xlsx"
OUTDIR = BASE/"Figures/event_plots"

US = ["Arizona", "California", "Nevada", "NewMexico", "Utah"]
EU = ["Berlin", "Munich", "Paris", "Rome", "Lisbon", "Stockholm"]

# feature name -> possible column spellings (v4 tree vs v5 files)
ALIASES = {
    "pm25": ["pm25", "PM2_5", "PM2.5"],
    "pm10": ["pm10", "PM10"],
    "no2": ["no2", "NO2"],
    "so2": ["so2", "SO2"],
    "co": ["co", "CO"],
    "o3": ["o3", "O3"],
    "temperature": ["temperature_2m", "temperature"],
    "pressure": ["surface_pressure", "pressure"],
    "precipitation": ["precipitation"],
    "wind_speed": ["wind_speed_10m", "wind_speed"],
    "wind_direction": ["wind_direction_10m", "wind_direction"],
}
UNITS = {"pm25": "µg/m³", "pm10": "µg/m³", "no2": "µg/m³ (EU) / ppb (US)",
         "so2": "µg/m³ / ppb", "co": "mg/m³ / ppm", "o3": "µg/m³ / ppb",
         "temperature": "°C", "pressure": "hPa", "precipitation": "mm",
         "wind_speed": "km/h", "wind_direction": "°"}


def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2-lat1), math.radians(lon2-lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*R*math.asin(math.sqrt(a))


def load_events():
    ev = pd.read_excel(EVENTS)
    ev["date"] = pd.to_datetime(ev["date"])
    return ev


def region_of_event(row):
    """Pick the split-tree region whose data file should hold the signal."""
    la, lo = float(row["lat"]), float(row["lon"])
    if row.get("region") == "US" or lo < -30:
        BBOX = {"Arizona": (31.3, 37.0, -114.9, -109.0),
                "NewMexico": (31.3, 37.0, -109.1, -103.0),
                "Utah": (37.0, 42.0, -114.1, -109.0),
                "Nevada": (35.0, 42.0, -120.0, -114.0),
                "California": (32.5, 42.0, -124.5, -114.1)}
        for rg, (s, n, w, e) in BBOX.items():
            if s <= la <= n and w <= lo <= e:
                return "US", rg
        return "US", None
    CITY = {"Berlin": (52.5, 13.4), "Munich": (48.14, 11.58),
            "Paris": (48.86, 2.35), "Rome": (41.9, 12.5),
            "Lisbon": (38.72, -9.14), "Stockholm": (59.33, 18.07)}
    best = min(CITY, key=lambda c: haversine(la, lo, *CITY[c]))
    return "EU", best


def find_col(df, feature):
    for c in ALIASES.get(feature, [feature]):
        if c in df.columns:
            return c
    return None


def load_region_year(group, region, year):
    f = SPLIT/group/region/f"{region}_{year}.csv"
    if not f.exists():
        raise FileNotFoundError(f"{f} fehlt (Jahr nicht im Datensatz?)")
    df = pd.read_csv(f)
    cols = {c.lower(): c for c in df.columns}
    sid = cols.get("site_id", list(df.columns)[0])
    la = cols.get("latitude"); lo = cols.get("longitude")
    tcol = cols.get("datetime_utc") or cols.get("timestamp")
    df = df.rename(columns={sid: "site_id", la: "latitude",
                            lo: "longitude", tcol: "datetime_utc"})
    df["datetime_utc"] = pd.to_datetime(df["datetime_utc"])
    return df


def plot_event(ev_row, features, window, top):
    group, region = region_of_event(ev_row)
    if region is None:
        print(f"!! Region fuer {ev_row['name']} nicht bestimmbar"); return
    t0 = ev_row["date"]
    year = t0.year
    df = load_region_year(group, region, year)
    lo_t, hi_t = t0 - pd.Timedelta(hours=window), t0 + pd.Timedelta(hours=window)
    win = df[(df.datetime_utc >= lo_t) & (df.datetime_utc <= hi_t)]
    if not len(win):
        print(f"!! keine Daten im Fenster fuer {ev_row['name']}"); return
    # nearest sensors
    st = win[["site_id", "latitude", "longitude"]].drop_duplicates("site_id")
    st["dist"] = st.apply(lambda s: haversine(
        ev_row["lat"], ev_row["lon"], s.latitude, s.longitude), axis=1)
    st = st.sort_values("dist")

    n = len(features)
    fig, axes = plt.subplots(n, 1, figsize=(11, 3.2*n), sharex=True, squeeze=False)
    slug = re.sub(r"[^A-Za-z0-9]+", "_", str(ev_row["name"]))[:40]
    for ax, feat in zip(axes[:, 0], features):
        col = find_col(win, feat)
        if col is None:
            ax.set_title(f"{feat}: Spalte nicht gefunden"); continue
        shown = 0
        for s in st.itertuples(index=False):
            g = win[win.site_id == s.site_id].sort_values("datetime_utc")
            if g[col].notna().sum() < 5:
                continue
            ax.plot(g.datetime_utc, g[col], lw=1.2,
                    label=f"{s.site_id} ({s.dist:.0f} km)")
            shown += 1
            if shown >= top:
                break
        ax.axvline(t0, color="crimson", ls="--", lw=1.5)
        ax.set_ylabel(f"{feat} [{UNITS.get(feat,'')}]")
        ax.legend(fontsize=7, ncol=2, loc="upper right")
        ax.grid(alpha=0.3)
    axes[0, 0].set_title(
        f"{ev_row['name']}  ·  {str(t0)[:10]}  ·  {region} ({group})  ·  "
        f"tier {ev_row.get('tier')}  ·  ±{window}h, {top} naechste Sensoren")
    axes[-1, 0].set_xlabel("UTC")
    fig.autofmt_xdate()
    fig.tight_layout()
    OUTDIR.mkdir(parents=True, exist_ok=True)
    out = OUTDIR/f"{slug}_{'_'.join(features)}.png"
    fig.savefig(out, dpi=140)
    plt.close(fig)
    print(f"-> {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--event", help="Event-Name (Teilstring reicht)")
    ap.add_argument("--region", help="State/City-Filter bei --list oder mehrdeutigem Event")
    ap.add_argument("--year", type=int)
    ap.add_argument("--type", help="Event-Typ-Filter (wildfire, dust_storm, ...)")
    ap.add_argument("--feature", default="pm25")
    ap.add_argument("--features", help="Komma-Liste fuer Grid-Plot")
    ap.add_argument("--window", type=int, default=72, help="Stunden vor/nach (default 72)")
    ap.add_argument("--top", type=int, default=6, help="n naechste Sensoren (default 6)")
    ap.add_argument("--list", action="store_true", help="Events anzeigen statt plotten")
    a = ap.parse_args()

    ev = load_events()
    if a.year:
        ev = ev[ev.date.dt.year == a.year]
    if a.type:
        ev = ev[ev["type"] == a.type]
    if a.region:
        gr = ev.apply(lambda r: region_of_event(r)[1] if pd.notna(r.get("lat")) else None, axis=1)
        ev = ev[gr == a.region]
    if a.list:
        print(ev[["name", "date", "type", "tier"]].to_string(max_rows=80))
        print(f"({len(ev)} Events)"); return
    if not a.event:
        print("--event NAME angeben (oder --list)"); return
    hit = ev[ev["name"].astype(str).str.contains(a.event, case=False, na=False)]
    if not len(hit):
        print(f"kein Event passt auf '{a.event}'"); return
    if len(hit) > 1:
        print(f"{len(hit)} Treffer — nehme den ersten:")
        print(hit[["name", "date", "type"]].head(5).to_string())
    feats = [f.strip() for f in (a.features.split(",") if a.features else [a.feature])]
    plot_event(hit.iloc[0], feats, a.window, a.top)


if __name__ == "__main__":
    main()
