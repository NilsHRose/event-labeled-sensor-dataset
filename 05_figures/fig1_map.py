"""
fig1_map.py — Paper Figure 1 (2x2): overview + zoom maps on real basemaps
==========================================================================
Top row:    US Southwest overview | Europe overview   (zoom boxes marked)
Bottom row: Arizona zoom with official fire perimeters | Paris city network

Background:  satellite / street / light-gray web-map tiles (contextily),
             falling back to basemap coastlines, then to a plain canvas.

Writes  fig_map.pdf (for LaTeX)  and  fig_map.png (preview)
into    <OUT>  (default: ~/Desktop/GIT WNO DATA/figures).

Run on the Mac:
    pip3 install contextily
    python3 ~/Desktop/"GIT WNO DATA"/fig1_map.py
Options:
    --tiles satellite|streets|light|none   (default: satellite)
    --base <folder with Data/ and Maps/>   --out <output folder>

If --tiles satellite is used, add to the figure caption:
    "Basemap imagery: Esri World Imagery."
"""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.lines as mlines
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
import numpy as np
import pandas as pd

INK = "#1f2430"
C_FIRE = "#ff5a1f"
C_DUST = "#e6c229"
C_OTH = "#b07aa1"
C_SENS = "#35b8e0"
C_PERIM = "#e832c8"   # magenta — clearly distinct from wildfire orange
US_REGIONS = {"Arizona", "California", "Nevada", "NewMexico", "Utah"}

# panel extents (lon_min, lat_min, lon_max, lat_max)
EXT_US = (-125.5, 30.5, -101.5, 43.0)
EXT_EU = (-12.0, 36.0, 22.0, 62.0)
EXT_AZ = (-115.0, 31.2, -108.9, 37.1)
EXT_PAR = (1.68, 48.40, 3.02, 49.24)

R = 6378137.0


def wm(lon, lat):
    """Lon/lat (deg) -> Web-Mercator meters (EPSG:3857)."""
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

    _rq.get = _get_with_timeout          # force a timeout on tile fetches
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
    """Fetch ONE test tile with a short timeout; False = server blocked."""
    try:
        src = tile_source(kind)
        url = src.build_url(x=12, y=25, z=6)
        r = _rq.get(url, timeout=8,
                    headers={"user-agent": "wno-dataset-figure"})
        return r.status_code == 200 and len(r.content) > 500
    except Exception:
        return False


TILES_DRAWN = []


def setup_panel(ax, llr, tiles, zoom):
    """Set extent in Web Mercator; draw tile / coastline background.
    Returns True if a tile background was drawn (dark imagery)."""
    x0, y0 = wm(llr[0], llr[1])
    x1, y1 = wm(llr[2], llr[3])
    ax.set_xlim(x0, x1); ax.set_ylim(y0, y1)
    ax.set_aspect("equal")
    if tiles != "none" and HAVE_CTX:
        try:
            ctx.add_basemap(ax, source=tile_source(tiles), zoom=zoom,
                            attribution=False, interpolation="bilinear")
            TILES_DRAWN.append(tiles)
            return tiles == "satellite"
        except Exception as e:
            print(f"note: tiles failed ({str(e)[:60]}) -> fallback")
    if HAVE_BM:
        # coastlines in lon/lat (cyl projection), re-projected to mercator
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


def zoom_box(ax, llr, dark, panel_llr=None, min_frac=0.14):
    """Dashed rectangle marking a zoom region; enforced minimum display
    size so small regions (Paris) stay visible in the overview."""
    lon0, lat0, lon1, lat1 = llr
    if panel_llr is not None:
        pw = panel_llr[2] - panel_llr[0]
        ph = panel_llr[3] - panel_llr[1]
        cx, cy = 0.5*(lon0+lon1), 0.5*(lat0+lat1)
        w = max(lon1-lon0, min_frac*pw)
        h = max(lat1-lat0, min_frac*ph)
        lon0, lon1 = cx - w/2, cx + w/2
        lat0, lat1 = cy - h/2, cy + h/2
    lons = [lon0, lon1, lon1, lon0, lon0]
    lats = [lat0, lat0, lat1, lat1, lat0]
    x, y = wm(lons, lats)
    c = "#ffffff" if dark else INK
    ax.plot(x, y, color=c, lw=1.4, ls=(0, (3, 1.5)), zorder=6,
            path_effects=[pe.withStroke(linewidth=2.8,
                                        foreground="black" if dark
                                        else "white")])


def scale_bar(ax, llr, km, dark):
    lat0 = llr[1] + 0.06*(llr[3]-llr[1])
    lon0 = llr[0] + 0.06*(llr[2]-llr[0])
    dlon = km / (111.32*np.cos(np.radians(lat0)))
    x, y = wm([lon0, lon0+dlon], [lat0, lat0])
    c = "#ffffff" if dark else INK
    halo = "black" if dark else "white"
    ax.plot(x, y, color=c, lw=1.6, solid_capstyle="butt", zorder=7,
            path_effects=[pe.withStroke(linewidth=3, foreground=halo)])
    ax.text(0.5*(x[0]+x[1]), y[0] + 0.013*(ax.get_ylim()[1]-ax.get_ylim()[0]),
            f"{km} km", ha="center", va="bottom", fontsize=6, color=c,
            zorder=7, path_effects=[pe.withStroke(linewidth=1.8,
                                                  foreground=halo)])


def geojson_polys(path):
    try:
        gj = json.loads(Path(path).read_text())
    except Exception:
        return
    feats = gj.get("features", [gj] if gj.get("geometry") else [])
    for ft in feats:
        geom = ft.get("geometry") or {}
        t, c = geom.get("type"), geom.get("coordinates")
        polys = [c] if t == "Polygon" else (c if t == "MultiPolygon" else [])
        for poly in polys:
            for ring in poly[:1]:
                a = np.asarray(ring, float)
                if len(a) >= 3:
                    yield a[:, 0], a[:, 1]


def load_stations(base):
    st = pd.read_csv(base/"Maps/stations.csv")[["site_id", "lat", "lon",
                                                "region"]]
    eu = []
    for f in sorted((base/"Data/wno_split_v5/EU").glob("*/*_2026.csv")):
        g = pd.read_csv(f, usecols=["site_id", "latitude", "longitude"])
        g = g.drop_duplicates("site_id")
        eu.append(pd.DataFrame({"site_id": g.site_id, "lat": g.latitude,
                                "lon": g.longitude,
                                "region": f.name.split("_")[0]}))
    if eu:
        st = pd.concat([st] + eu, ignore_index=True)
    return st


def unstack(ev, radius_deg=0.014):
    """Spread events sharing identical coordinates on a small ring so
    stacked recurring events stay countable (display only)."""
    ev = ev.copy()
    key = ev.lat.round(3).astype(str) + "/" + ev.lon.round(3).astype(str)
    for _, idx in ev.groupby(key).groups.items():
        n = len(idx)
        if n > 1:
            ang = np.linspace(0, 2*np.pi, n, endpoint=False)
            ev.loc[idx, "lon"] = ev.loc[idx, "lon"] + radius_deg*np.cos(ang)
            ev.loc[idx, "lat"] = ev.loc[idx, "lat"] + radius_deg*np.sin(ang)
    return ev


def scatter_events(ax, ev, s=7, alpha=0.8, dark=False):
    edge = {"lw": 0.25, "edgecolors": "black"} if dark else {"lw": 0}
    for t, g in ev.groupby("type"):
        c = {"wildfire": C_FIRE, "dust_storm": C_DUST}.get(t, C_OTH)
        x, y = wm(g.lon, g.lat)
        ax.scatter(x, y, s=s, c=c, alpha=alpha, zorder=4, **edge)


def scatter_sensors(ax, st, s=4, dark=False):
    x, y = wm(st.lon, st.lat)
    if dark:
        ax.scatter(x, y, s=s, c=C_SENS, lw=0.25, edgecolors="black",
                   alpha=0.95, zorder=3)
    else:
        ax.scatter(x, y, s=s, c="#5b6472", lw=0, alpha=0.8, zorder=3)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--base",
                   default=str(Path.home()/"Desktop/Research/Neural Operators"))
    p.add_argument("--out",
                   default=str(Path.home()/"Desktop/GIT WNO DATA/figures"))
    p.add_argument("--tiles", default="satellite",
                   choices=["satellite", "streets", "light", "none"])
    a = p.parse_args()
    base, out = Path(a.base), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if a.tiles != "none" and not HAVE_CTX:
        print("note: contextily not installed -> no map tiles "
              "(pip3 install contextily)")
    if a.tiles != "none" and HAVE_CTX:
        print(f"checking tile server ({a.tiles}) ...", flush=True)
        if not tiles_reachable(a.tiles):
            print(f"note: {a.tiles} tile server NOT reachable from this "
                  "network -> drawing without tiles.\n"
                  "      try --tiles streets or --tiles light, or another "
                  "network (phone hotspot).")
            a.tiles = "none"
        else:
            print("tile server OK")

    ev = pd.read_excel(base/"Data/events_v5_area.xlsx")
    ev = ev[ev.lat.notna()]
    st = load_stations(base)
    sus = st[st.region.isin(US_REGIONS)]
    seu = st[~st.region.isin(US_REGIONS)]
    eus = ev[ev.region == "US"]
    eeu = ev[ev.region == "EU"]
    in_az = ((ev.lat >= EXT_AZ[1]) & (ev.lat <= EXT_AZ[3]) &
             (ev.lon >= EXT_AZ[0]) & (ev.lon <= EXT_AZ[2]))
    eaz = ev[in_az]
    perims = (eaz.perimeter_file.dropna().unique()
              if "perimeter_file" in ev.columns else [])

    fig, axs = plt.subplots(
        2, 2, figsize=(7.1, 5.6), dpi=300,
        gridspec_kw={"wspace": 0.05, "hspace": 0.14,
                     "width_ratios": [1.12, 1]})
    (ax_us, ax_eu), (ax_az, ax_pa) = axs

    # (a) US overview
    dark = setup_panel(ax_us, EXT_US, a.tiles, zoom=7)
    scatter_sensors(ax_us, sus, s=3, dark=dark)
    scatter_events(ax_us, eus, s=5, alpha=0.65, dark=dark)
    zoom_box(ax_us, EXT_AZ, dark, panel_llr=EXT_US)
    ax_us.set_title("(a) US Southwest — 5 states", fontsize=8,
                    color=INK, loc="left", pad=3)

    # (b) EU overview
    dark = setup_panel(ax_eu, EXT_EU, a.tiles, zoom=6)
    scatter_sensors(ax_eu, seu, s=4, dark=dark)
    scatter_events(ax_eu, eeu, s=5, alpha=0.6, dark=dark)
    zoom_box(ax_eu, EXT_PAR, dark, panel_llr=EXT_EU)
    ax_eu.set_title("(b) Europe — 6 city networks", fontsize=8,
                    color=INK, loc="left", pad=3)

    # (c) Arizona zoom with perimeters
    dark = setup_panel(ax_az, EXT_AZ, a.tiles, zoom=9)
    saz = sus[(sus.lat >= EXT_AZ[1]) & (sus.lat <= EXT_AZ[3]) &
              (sus.lon >= EXT_AZ[0]) & (sus.lon <= EXT_AZ[2])]
    scatter_sensors(ax_az, saz, s=5, dark=dark)
    scatter_events(ax_az, eaz, s=3, alpha=0.5, dark=dark)
    n_drawn = 0
    for pf in perims:
        fp = base/"Data"/pf
        if not fp.exists():
            continue
        for lons, lats in geojson_polys(fp):
            x, y = wm(lons, lats)
            ax_az.fill(x, y, fc=C_PERIM, ec=C_PERIM, lw=0.6,
                       alpha=0.5 if dark else 0.45, zorder=5)
        n_drawn += 1
    scale_bar(ax_az, EXT_AZ, 100, dark)
    ax_az.set_title(f"(c) Arizona — {n_drawn} official fire perimeters",
                    fontsize=8, color=INK, loc="left", pad=3)

    # (d) Paris zoom
    dark = setup_panel(ax_pa, EXT_PAR, a.tiles, zoom=11)
    spa = seu[seu.region == "Paris"]
    scatter_sensors(ax_pa, spa, s=18, dark=dark)
    in_pa = ((eeu.lat >= EXT_PAR[1]) & (eeu.lat <= EXT_PAR[3]) &
             (eeu.lon >= EXT_PAR[0]) & (eeu.lon <= EXT_PAR[2]))
    scatter_events(ax_pa, unstack(eeu[in_pa]), s=20, alpha=0.9, dark=dark)
    scale_bar(ax_pa, EXT_PAR, 10, dark)
    ax_pa.set_title(f"(d) Paris — {len(spa)}-station city network",
                    fontsize=8, color=INK, loc="left", pad=3)

    for ax in axs.ravel():
        ax.set_xticks([]); ax.set_yticks([])
        for s_ in ax.spines.values():
            s_.set_color("#b9b4a8"); s_.set_linewidth(0.7)

    sens_leg = C_SENS if "satellite" in TILES_DRAWN else "#5b6472"
    handles = [
        mlines.Line2D([], [], color=sens_leg, marker="o", ls="", ms=3.5,
                      label="sensor"),
        mlines.Line2D([], [], color=C_FIRE, marker="o", ls="", ms=4,
                      label="wildfire"),
        mlines.Line2D([], [], color=C_DUST, marker="o", ls="", ms=4,
                      label="dust storm"),
        mlines.Line2D([], [], color=C_OTH, marker="o", ls="", ms=4,
                      label="other event"),
        mlines.Line2D([], [], color=C_PERIM, marker="s", ls="", ms=5,
                      alpha=0.45, label="fire perimeter"),
        mlines.Line2D([], [], color=INK, ls=(0, (3, 1.5)), lw=1,
                      label="zoom extent"),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=6, frameon=False,
               fontsize=7, bbox_to_anchor=(0.5, -0.012), columnspacing=1.2,
               handletextpad=0.4)
    fig.savefig(out/"fig_map.pdf", bbox_inches="tight", facecolor="white")
    fig.savefig(out/"fig_map.png", bbox_inches="tight", facecolor="white",
                dpi=450)
    plt.close(fig)
    print(f"-> {out/'fig_map.pdf'}")
    print(f"-> {out/'fig_map.png'}  (Vorschau)")
    print(f"   tiles={a.tiles} (contextily {'ja' if HAVE_CTX else 'NEIN'}) · "
          f"{len(sus)} US + {len(seu)} EU Sensoren · "
          f"{len(eus)} US + {len(eeu)} EU Events · "
          f"{n_drawn} AZ-Perimeter · {len(spa)} Paris-Stationen")


if __name__ == "__main__":
    main()
