"""
fig3_spatial.py — Paper Figure 3: spatial footprint of one event
=================================================================
Per-station maximum PM10 in the first 48 h after the Juniper Fire
(Arizona, 2025-07-02); star = event location. Optionally on real
satellite / street / light map tiles (contextily).

Writes  fig_spatial.pdf  and  fig_spatial.png (preview)
into    <OUT>  (default: ~/Desktop/GIT WNO DATA/figures).

Run:    python3 ~/Desktop/"GIT WNO DATA"/fig3_spatial.py
Options:
    --tiles satellite|streets|light|none   (default: satellite)
    --base <folder with Data/>  --out <folder>
Caption credit when satellite is used:
    "Basemap imagery: Esri World Imagery."
"""
import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

INK = "#1f2430"
EVENT = {"name": "Juniper Fire", "date": "2025-07-02"}
R = 6378137.0


def wm(lon, lat):
    lon = np.asarray(lon, float)
    lat = np.clip(np.asarray(lat, float), -85.05, 85.05)
    return (R*np.radians(lon),
            R*np.log(np.tan(np.pi/4 + np.radians(lat)/2)))


try:
    import contextily as ctx
    import requests as _rq
    _orig_get = _rq.get

    def _get_with_timeout(*args, **kw):
        kw.setdefault("timeout", 15)
        return _orig_get(*args, **kw)

    _rq.get = _get_with_timeout
    HAVE_CTX = True
except Exception:
    HAVE_CTX = False

try:
    from mpl_toolkits.basemap import Basemap
    HAVE_BM = True
except Exception:
    HAVE_BM = False


def tile_source(kind):
    return {"satellite": ctx.providers.Esri.WorldImagery,
            "streets": ctx.providers.OpenStreetMap.Mapnik,
            "light": ctx.providers.CartoDB.Positron}[kind]


def tiles_reachable(kind):
    try:
        src = tile_source(kind)
        url = src.build_url(x=12, y=25, z=6)
        r = _rq.get(url, timeout=8,
                    headers={"user-agent": "wno-dataset-figure"})
        return r.status_code == 200 and len(r.content) > 500
    except Exception:
        return False


def setup_panel(ax, llr, tiles, zoom):
    x0, y0 = wm(llr[0], llr[1])
    x1, y1 = wm(llr[2], llr[3])
    ax.set_xlim(x0, x1); ax.set_ylim(y0, y1)
    ax.set_aspect("equal")
    if tiles != "none" and HAVE_CTX:
        try:
            ctx.add_basemap(ax, source=tile_source(tiles), zoom=zoom,
                            attribution=False, interpolation="bilinear")
            return tiles == "satellite"
        except Exception as e:
            print(f"note: tiles failed ({str(e)[:60]}) -> fallback")
    if HAVE_BM:
        m = Basemap(projection="cyl", llcrnrlon=llr[0], llcrnrlat=llr[1],
                    urcrnrlon=llr[2], urcrnrlat=llr[3], resolution="i",
                    fix_aspect=False)
        ax.set_facecolor("#f2f0ea")
        for seg in getattr(m, "coastsegs", []):
            a = np.asarray(seg)
            if len(a):
                x, y = wm(a[:, 0], a[:, 1])
                ax.plot(x, y, color="#c9c4b8", lw=0.45, zorder=1)
    else:
        ax.set_facecolor("#f7f6f2")
    return False


def scale_bar(ax, llr, km, dark):
    lat0 = llr[1] + 0.07*(llr[3]-llr[1])
    lon0 = llr[0] + 0.07*(llr[2]-llr[0])
    dlon = km / (111.32*np.cos(np.radians(lat0)))
    x, y = wm([lon0, lon0+dlon], [lat0, lat0])
    c = "#ffffff" if dark else INK
    halo = "black" if dark else "white"
    ax.plot(x, y, color=c, lw=1.6, solid_capstyle="butt", zorder=7,
            path_effects=[pe.withStroke(linewidth=3, foreground=halo)])
    ax.text(0.5*(x[0]+x[1]), y[0] + 0.015*(ax.get_ylim()[1]-ax.get_ylim()[0]),
            f"{km} km", ha="center", va="bottom", fontsize=6, color=c,
            zorder=7, path_effects=[pe.withStroke(linewidth=1.8,
                                                  foreground=halo)])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base",
                    default=str(Path.home()/"Desktop/Research/Neural Operators"))
    ap.add_argument("--out",
                    default=str(Path.home()/"Desktop/GIT WNO DATA/figures"))
    ap.add_argument("--tiles", default="satellite",
                    choices=["satellite", "streets", "light", "none"])
    a = ap.parse_args()
    base, out = Path(a.base), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if a.tiles != "none" and not HAVE_CTX:
        print("note: contextily not installed -> no map tiles")
    if a.tiles != "none" and HAVE_CTX:
        print(f"checking tile server ({a.tiles}) ...", flush=True)
        if not tiles_reachable(a.tiles):
            print(f"note: {a.tiles} tile server NOT reachable "
                  "-> drawing without tiles")
            a.tiles = "none"
        else:
            print("tile server OK")

    ev = pd.read_excel(base/"Data/events_v5_area.xlsx")
    ev["date"] = pd.to_datetime(ev["date"])
    erow = ev[(ev["name"] == EVENT["name"]) &
              (ev.date == EVENT["date"])].iloc[0]
    d = pd.read_csv(base/"Data/wno_split_v5/US/Arizona/Arizona_2025.csv",
                    parse_dates=["datetime_utc"])

    t0 = pd.to_datetime(erow["date"])
    win = d[d.datetime_utc.between(t0, t0 + pd.Timedelta(hours=48))]
    agg = (win.groupby("site_id")
              .agg(lat=("latitude", "first"), lon=("longitude", "first"),
                   pm10=("pm10", "max")).reset_index())
    la, lo = erow["lat"], erow["lon"]
    box = 1.9
    llr = (lo - box, la - box, lo + box, la + box)
    sub = agg[agg.lat.between(la - box, la + box) &
              agg.lon.between(lo - box, lo + box)]

    fig, ax = plt.subplots(figsize=(3.3, 2.5), dpi=300)
    dark = setup_panel(ax, llr, a.tiles, zoom=9)
    edge = "white" if dark else INK
    have = sub[sub.pm10.notna()]
    x, y = wm(have.lon, have.lat)
    sc = ax.scatter(x, y, c=have.pm10, s=30, cmap="YlOrRd",
                    vmin=0, vmax=max(200, np.nanpercentile(have.pm10, 95)),
                    edgecolors=edge, linewidths=0.4, zorder=4)
    none = sub[sub.pm10.isna()]
    x, y = wm(none.lon, none.lat)
    ax.scatter(x, y, s=10, c="#cccccc",
               lw=0.3 if dark else 0,
               edgecolors="black" if dark else "none", zorder=3)
    x, y = wm([lo], [la])
    ax.scatter(x, y, marker="*", s=200, c="crimson", edgecolors="white",
               linewidths=0.8, zorder=5)
    scale_bar(ax, llr, 50, dark)
    cb = fig.colorbar(sc, ax=ax, shrink=0.85, pad=0.02)
    cb.set_label("max PM10 in first 48 h [µg/m³]", fontsize=7)
    cb.ax.tick_params(labelsize=6.5)
    ax.set_xticks([]); ax.set_yticks([])
    for s_ in ax.spines.values():
        s_.set_color("#b9b4a8"); s_.set_linewidth(0.7)
    ax.set_title(f"{erow['name']} — spatial footprint", fontsize=8,
                 color=INK, loc="left")
    fig.tight_layout()
    fig.savefig(out/"fig_spatial.pdf", bbox_inches="tight",
                facecolor="white")
    fig.savefig(out/"fig_spatial.png", bbox_inches="tight",
                facecolor="white", dpi=450)
    plt.close(fig)
    print(f"-> {out/'fig_spatial.pdf'}")
    print(f"-> {out/'fig_spatial.png'}  (Vorschau)")
    print(f"   tiles={a.tiles} · {len(have)} Stationen mit PM10, "
          f"{len(none)} ohne")


if __name__ == "__main__":
    main()
