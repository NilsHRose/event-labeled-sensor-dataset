"""Build the paper figures (fig_map, fig_temporal, fig_spatial) and the
region summary table from the released dataset tree.
Run: python3 make_paper_figures.py --base <folder with Data/ and Maps/>
     --out figs
"""
import argparse
import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.lines as mlines
import numpy as np
import pandas as pd

INK = "#1f2430"
C_FIRE = "#e6550d"
C_DUST = "#c7a13a"
C_OTH = "#8c564b"
C_SENS = "#9aa0a6"
SENSORS = ["#2a6fdb", "#d62728", "#2ca02c"]   # 3 highlighted sensors

US_REGIONS = {"Arizona", "California", "Nevada", "NewMexico", "Utah"}

EVENT = {"name": "Juniper Fire", "date": "2025-07-02",
         "lat": None, "lon": None}            # coords read from the table

try:
    from mpl_toolkits.basemap import Basemap
    HAVE_BM = True
except Exception:
    HAVE_BM = False


def base_map(ax, llr):
    if HAVE_BM:
        m = Basemap(projection="merc", llcrnrlon=llr[0], llcrnrlat=llr[1],
                    urcrnrlon=llr[2], urcrnrlat=llr[3], resolution="l", ax=ax)
        m.fillcontinents(color="#f2f0ea", lake_color="#ffffff", zorder=0)
        m.drawcoastlines(color="#c9c4b8", linewidth=0.5)
        m.drawcountries(color="#c9c4b8", linewidth=0.4)
        m.drawstates(color="#ddd8cc", linewidth=0.4)
        return m
    ax.set_xlim(llr[0], llr[2]); ax.set_ylim(llr[1], llr[3])
    ax.set_facecolor("#f7f6f2")
    return None


def proj(m, lons, lats):
    if m is None:
        return lons, lats
    return m(np.asarray(lons, float), np.asarray(lats, float))


def strip_axes(ax):
    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values():
        s.set_color("#d8d4c8"); s.set_linewidth(0.7)


def load_stations(base):
    """US stations from Maps/stations.csv, EU stations from the city files."""
    st = pd.read_csv(base/"Maps/stations.csv")[["site_id", "lat", "lon",
                                                "region"]]
    eu = []
    for f in sorted((base/"Data/wno_split_v5/EU").glob("*/*_2026.csv")):
        city = f.name.split("_")[0]
        g = pd.read_csv(f, usecols=["site_id", "latitude", "longitude"])
        g = g.drop_duplicates("site_id")
        eu.append(pd.DataFrame({"site_id": g.site_id, "lat": g.latitude,
                                "lon": g.longitude, "region": city}))
    if eu:
        st = pd.concat([st] + eu, ignore_index=True)
    return st


def fig_map(ev, st, out):
    fig, (ax_us, ax_eu) = plt.subplots(
        1, 2, figsize=(7.1, 2.55), dpi=300,
        gridspec_kw={"width_ratios": [1.35, 1], "wspace": 0.04})
    m = base_map(ax_us, (-125.5, 30.5, -101.5, 43.0))
    sus = st[st.region.isin(US_REGIONS)]
    x, y = proj(m, sus.lon, sus.lat)
    ax_us.scatter(x, y, s=3, c=C_SENS, lw=0, alpha=0.8, zorder=3)
    eus = ev[ev.region == "US"]
    for t, c in (("wildfire", C_FIRE), ("dust_storm", C_DUST)):
        g = eus[eus.type == t]
        x, y = proj(m, g.lon, g.lat)
        ax_us.scatter(x, y, s=7, c=c, lw=0, alpha=0.75, zorder=4)
    ax_us.set_title("US Southwest", fontsize=8.5, color=INK, loc="left", pad=3)

    m = base_map(ax_eu, (-12.0, 36.0, 22.0, 62.0))
    seu = st[~st.region.isin(US_REGIONS)]
    x, y = proj(m, seu.lon, seu.lat)
    ax_eu.scatter(x, y, s=4, c=C_SENS, lw=0, alpha=0.9, zorder=3)
    eeu = ev[ev.region == "EU"]
    for t, g in eeu.groupby("type"):
        c = {"wildfire": C_FIRE, "dust_storm": C_DUST}.get(t, C_OTH)
        x, y = proj(m, g.lon, g.lat)
        ax_eu.scatter(x, y, s=6, c=c, lw=0, alpha=0.6, zorder=4)
    ax_eu.set_title("Europe (6 city networks)", fontsize=8.5, color=INK,
                    loc="left", pad=3)

    for ax in (ax_us, ax_eu):
        strip_axes(ax)
    handles = [
        mlines.Line2D([], [], color=C_SENS, marker="o", ls="", ms=3.5,
                      label="sensor"),
        mlines.Line2D([], [], color=C_FIRE, marker="o", ls="", ms=4,
                      label="wildfire"),
        mlines.Line2D([], [], color=C_DUST, marker="o", ls="", ms=4,
                      label="dust storm"),
        mlines.Line2D([], [], color=C_OTH, marker="o", ls="", ms=4,
                      label="other event"),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=4, frameon=False,
               fontsize=7.5, bbox_to_anchor=(0.5, -0.04))
    fig.tight_layout()
    fig.savefig(out/"fig_map.pdf", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("fig_map.pdf")


def pick_sensors(d, lat, lon, feats, t0, window_h=96, n=3):
    """n nearest sensors that actually have data for the features."""
    st = d[["site_id", "latitude", "longitude"]].drop_duplicates("site_id")
    st["dist"] = np.sqrt(((st.latitude - lat) * 111) ** 2 +
                         ((st.longitude - lon) * 88) ** 2)
    st = st.sort_values("dist")
    lo, hi = t0 - pd.Timedelta(hours=window_h), t0 + pd.Timedelta(hours=window_h)
    win = d[d.datetime_utc.between(lo, hi)]
    chosen = []
    for s in st.itertuples(index=False):
        g = win[win.site_id == s.site_id]
        if sum(g[f].notna().sum() >= 24 for f in feats) >= 2:
            chosen.append((s.site_id, s.dist))
        if len(chosen) == n:
            break
    return chosen, win


def fig_temporal(d, erow, out):
    t0 = pd.to_datetime(erow["date"])
    feats = ["pm25", "pm10", "wind_speed_10m"]
    labels = {"pm25": "PM2.5 [µg/m³]", "pm10": "PM10 [µg/m³]",
              "wind_speed_10m": "wind speed [km/h]"}
    chosen, win = pick_sensors(d, erow["lat"], erow["lon"], feats, t0)
    fig, axes = plt.subplots(3, 1, figsize=(3.4, 2.95), dpi=300, sharex=True)
    for ax, f in zip(axes, feats):
        for (sid, dist), c in zip(chosen, SENSORS):
            g = win[win.site_id == sid].sort_values("datetime_utc")
            ax.plot(g.datetime_utc, g[f], lw=0.9, color=c,
                    label=f"{dist:.0f} km")
        ax.axvline(t0, color="crimson", ls="--", lw=1.0)
        ax.set_ylabel(labels[f], fontsize=7)
        ax.tick_params(labelsize=6.5)
        ax.grid(alpha=0.25, lw=0.4)
    axes[0].legend(fontsize=6, ncol=3, frameon=False, loc="upper left",
                   title="sensor distance to event", title_fontsize=6)
    axes[0].set_title(f"{erow['name']} — {str(t0)[:10]}", fontsize=8,
                      color=INK, loc="left")
    import matplotlib.dates as mdates
    loc = mdates.DayLocator()
    axes[-1].xaxis.set_major_locator(loc)
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    for lbl in axes[-1].get_xticklabels():
        lbl.set_fontsize(6.5)
        lbl.set_rotation(45)
        lbl.set_ha("right")
    fig.tight_layout()
    fig.savefig(out/"fig_temporal.pdf", bbox_inches="tight",
                facecolor="white")
    plt.close(fig)
    print("fig_temporal.pdf; sensors:", chosen)
    return [sid for sid, _ in chosen]


def fig_spatial(d, erow, out, highlight):
    t0 = pd.to_datetime(erow["date"])
    win = d[d.datetime_utc.between(t0, t0 + pd.Timedelta(hours=48))]
    agg = (win.groupby("site_id")
              .agg(lat=("latitude", "first"), lon=("longitude", "first"),
                   pm10=("pm10", "max")).reset_index())
    la, lo = erow["lat"], erow["lon"]
    box = 1.9
    sub = agg[agg.lat.between(la - box, la + box) &
              agg.lon.between(lo - box, lo + box)]
    fig, ax = plt.subplots(figsize=(3.3, 2.3), dpi=300)
    m = base_map(ax, (lo - box, la - box, lo + box, la + box))
    have = sub[sub.pm10.notna()]
    x, y = proj(m, have.lon, have.lat)
    sc = ax.scatter(x, y, c=have.pm10, s=26, cmap="YlOrRd",
                    vmin=0, vmax=max(200, np.nanpercentile(have.pm10, 95)),
                    edgecolors=INK, linewidths=0.3, zorder=4)
    none = sub[sub.pm10.isna()]
    x, y = proj(m, none.lon, none.lat)
    ax.scatter(x, y, s=10, c="#cccccc", lw=0, zorder=3)
    x, y = proj(m, [lo], [la])
    ax.scatter(x, y, marker="*", s=180, c="crimson", edgecolors="white",
               linewidths=0.6, zorder=5)
    cb = fig.colorbar(sc, ax=ax, shrink=0.85, pad=0.02)
    cb.set_label("max PM10 in first 48 h [µg/m³]", fontsize=7)
    cb.ax.tick_params(labelsize=6.5)
    strip_axes(ax)
    ax.set_title(f"{erow['name']} — spatial footprint", fontsize=8,
                 color=INK, loc="left")
    fig.tight_layout()
    fig.savefig(out/"fig_spatial.pdf", bbox_inches="tight",
                facecolor="white")
    plt.close(fig)
    print("fig_spatial.pdf")


BBOX = {"Arizona": (31.3, 37.0, -114.9, -109.0),
        "NewMexico": (31.3, 37.0, -109.1, -103.0),
        "Utah": (37.0, 42.0, -114.1, -109.0),
        "Nevada": (35.0, 42.0, -120.0, -114.0),
        "California": (32.5, 42.0, -124.5, -114.1)}


def us_state_of(lat, lon):
    """first-match state assignment — same order as the split pipeline"""
    for rg, (s, n, w, e) in BBOX.items():
        if s <= lat <= n and w <= lon <= e:
            return rg
    return None


def table_regions(ev, st, out):
    ev = ev.copy()
    ev["us_state"] = [us_state_of(a, b) if r == "US" else None
                    for a, b, r in zip(ev.lat, ev.lon, ev.region)]
    rows = []
    for rg, g in st.groupby("region"):
        is_us = rg in US_REGIONS
        if is_us:
            sel = ev[ev.us_state == rg]
        else:
            la, lo = g.lat.mean(), g.lon.mean()
            sel = ev[(ev.region == "EU") & ev.lat.between(la-1.5, la+1.5) &
                     ev.lon.between(lo-2.0, lo+2.0)]
        fires = int((sel.type == "wildfire").sum())
        dust = int((sel.type == "dust_storm").sum())
        other = int(len(sel) - fires - dust)
        rows.append((rg, "US" if is_us else "EU", len(g), fires, dust, other))
    df = pd.DataFrame(rows, columns=["region", "grp", "sensors", "fires",
                                     "dust", "other"])
    df = df.sort_values(["grp", "region"], ascending=[False, True])
    tot = ("Total", "", df.sensors.sum(), df.fires.sum(), df.dust.sum(),
           df.other.sum())
    lines = [f"{r.region.replace('NewMexico','New Mexico')} & {r.sensors} & "
             f"{r.fires} & {r.dust} & {r.other} \\\\"
             for r in df.itertuples(index=False)]
    lines.append("\\midrule")
    lines.append(f"\\textbf{{Total}} & \\textbf{{{tot[2]}}} & "
                 f"\\textbf{{{tot[3]}}} & \\textbf{{{tot[4]}}} & "
                 f"\\textbf{{{tot[5]}}} \\\\")
    (out/"table_regions.tex").write_text("\n".join(lines))
    print("table_regions.tex")
    print(df.to_string(index=False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=".", help="folder containing Data/")
    ap.add_argument("--out", default="figs")
    a = ap.parse_args()
    base = Path(a.base)
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)

    ev = pd.read_excel(base/"Data/events_v5_area.xlsx")
    ev["date"] = pd.to_datetime(ev["date"])
    ev = ev[ev.lat.notna()]
    st = load_stations(base)

    fig_map(ev, st, out)
    table_regions(ev, st, out)

    erow = ev[(ev["name"] == EVENT["name"]) &
              (ev.date == EVENT["date"])].iloc[0]
    d = pd.read_csv(base/"Data/wno_split_v5/US/Arizona/Arizona_2025.csv",
                    parse_dates=["datetime_utc"])
    highlight = fig_temporal(d, erow, out)
    fig_spatial(d, erow, out, highlight)


if __name__ == "__main__":
    main()
