"""
fig2_temporal.py — Paper Figure 2: temporal view of one event
==============================================================
Three nearest stations (with data) x three features, +-96 h around the
Juniper Fire (Arizona, 2025-07-02).

Writes  fig_temporal.pdf  and  fig_temporal.png (preview)
into    <OUT>  (default: ~/Desktop/GIT WNO DATA/figures).

Run:    python3 ~/Desktop/"GIT WNO DATA"/fig2_temporal.py
        (options: --base <folder with Data/>  --out <folder>)
Needs:  pandas, matplotlib, openpyxl
"""
import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

INK = "#1f2430"
SENSORS = ["#2a6fdb", "#d62728", "#2ca02c"]   # 3 highlighted sensors

EVENT = {"name": "Juniper Fire", "date": "2025-07-02"}
FEATS = ["pm25", "pm10", "wind_speed_10m"]
LABELS = {"pm25": "PM2.5 [µg/m³]", "pm10": "PM10 [µg/m³]",
          "wind_speed_10m": "wind speed [km/h]"}


def pick_sensors(d, lat, lon, feats, t0, window_h=96, n=3):
    """n nearest sensors that actually have data for the features."""
    st = d[["site_id", "latitude", "longitude"]].drop_duplicates("site_id")
    st["dist"] = np.sqrt(((st.latitude - lat) * 111) ** 2 +
                         ((st.longitude - lon) * 88) ** 2)
    st = st.sort_values("dist")
    lo, hi = (t0 - pd.Timedelta(hours=window_h),
              t0 + pd.Timedelta(hours=window_h))
    win = d[d.datetime_utc.between(lo, hi)]
    chosen = []
    for s in st.itertuples(index=False):
        g = win[win.site_id == s.site_id]
        if sum(g[f].notna().sum() >= 24 for f in feats) >= 2:
            chosen.append((s.site_id, s.dist))
        if len(chosen) == n:
            break
    return chosen, win


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base",
                    default=str(Path.home()/"Desktop/Research/Neural Operators"))
    ap.add_argument("--out",
                    default=str(Path.home()/"Desktop/GIT WNO DATA/figures"))
    a = ap.parse_args()
    base, out = Path(a.base), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    ev = pd.read_excel(base/"Data/events_v5_area.xlsx")
    ev["date"] = pd.to_datetime(ev["date"])
    erow = ev[(ev["name"] == EVENT["name"]) &
              (ev.date == EVENT["date"])].iloc[0]
    d = pd.read_csv(base/"Data/wno_split_v5/US/Arizona/Arizona_2025.csv",
                    parse_dates=["datetime_utc"])

    t0 = pd.to_datetime(erow["date"])
    chosen, win = pick_sensors(d, erow["lat"], erow["lon"], FEATS, t0)

    fig, axes = plt.subplots(3, 1, figsize=(3.5, 3.4), dpi=300, sharex=True)
    for ax, f in zip(axes, FEATS):
        for (sid, dist), c in zip(chosen, SENSORS):
            g = win[win.site_id == sid].sort_values("datetime_utc")
            ax.plot(g.datetime_utc, g[f],
                    lw=0.9 if f == "wind_speed_10m" else 1.3, color=c,
                    alpha=0.9 if f == "wind_speed_10m" else 1.0,
                    label=f"{dist:.0f} km")
        ax.axvline(t0, color="crimson", ls="--", lw=1.1)
        ax.set_ylabel(LABELS[f], fontsize=7)
        ax.tick_params(labelsize=6.5)
        ax.grid(alpha=0.18, lw=0.4)
        ax.margins(x=0.01)
    axes[0].annotate("registry\ndiscovery", xy=(t0, 1.0),
                     xycoords=("data", "axes fraction"),
                     xytext=(4, -2), textcoords="offset points",
                     fontsize=5.8, color="crimson", va="top")
    axes[0].set_title(f"{erow['name']} — {str(t0)[:10]}", fontsize=8.5,
                      color=INK, loc="left", pad=3)
    h, lab = axes[0].get_legend_handles_labels()
    fig.legend(h, lab, loc="upper right", bbox_to_anchor=(0.995, 1.002),
               ncol=3, fontsize=6.2, frameon=False,
               title="distance to event", title_fontsize=6.2,
               columnspacing=0.9, handlelength=1.3, handletextpad=0.4)
    fig.subplots_adjust(top=0.90)
    axes[-1].xaxis.set_major_locator(mdates.DayLocator(interval=2))
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    axes[-1].xaxis.set_minor_locator(mdates.DayLocator())
    for lbl in axes[-1].get_xticklabels():
        lbl.set_fontsize(6.5)
    fig.tight_layout(rect=(0, 0, 1, 0.925))
    fig.savefig(out/"fig_temporal.pdf", bbox_inches="tight",
                facecolor="white")
    fig.savefig(out/"fig_temporal.png", bbox_inches="tight",
                facecolor="white", dpi=450)
    plt.close(fig)
    print(f"-> {out/'fig_temporal.pdf'}")
    print(f"-> {out/'fig_temporal.png'}  (Vorschau)")
    print("   Sensoren:", ", ".join(f"{sid} ({dist:.0f} km)"
                                    for sid, dist in chosen))


if __name__ == "__main__":
    main()
