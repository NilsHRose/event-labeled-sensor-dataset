"""Generate event_map_v5.html from events_v5_area.xlsx + stations.csv,
reusing the UI shell of the existing event_map.html."""
import json
import re
import sys
from pathlib import Path

import pandas as pd

SRC = str(Path.home() / "Desktop/Research/Neural Operators")
OLD = f"{SRC}/Maps/event_map.html"
OUT = str(Path.home() / "Desktop/Research/Neural Operators/Maps/event_map_v5.html")

US = {"Arizona", "California", "Nevada", "NewMexico", "Utah", "Colorado",
      "New Mexico"}

TG = {}
def tg_of(t):
    t = str(t)
    if t.startswith("football") or t == "olympics_football":
        return "football"
    if t in ("festival", "oktoberfest", "christmas_market"):
        return "festival/market"
    if t.endswith("holiday"):
        return "holiday"
    if t.startswith("transport"):
        return "transport"
    return t


def main():
    ev = pd.read_excel(f"{SRC}/Data/events_v5_area.xlsx")
    st = pd.read_csv(f"{SRC}/Maps/stations.csv")
    h = open(OLD, encoding="utf-8").read()

    ev = ev[ev["lat"].notna() & ev["lon"].notna()].copy()
    ev["date"] = pd.to_datetime(ev["date"], errors="coerce")
    ev = ev[ev["date"].notna()]
    has_ign = "ignition_lat" in ev.columns

    events = []
    for _, r in ev.iterrows():
        mag = r.get("gis_acres")
        if pd.isna(mag):
            m = re.search(r"acres=([\d.]+)", str(r.get("notes")))
            mag = float(m.group(1)) if m else 0.0
        mag = float(mag) if pd.notna(mag) else 0.0
        label = f"{r['name']} · {r['date'].date()}"
        if mag:
            label += f" · {mag:,.0f} acres"
        da = r.get("discovery_acres")
        if pd.notna(da):
            label += f" · at discovery: {float(da):g} acres"
        e = {"lat": round(float(r["lat"]), 5), "lon": round(float(r["lon"]), 5),
             "name": str(r["name"]), "type": str(r["type"]),
             "tg": tg_of(r["type"]), "year": str(r["date"].year),
             "tier": int(r["tier"]) if pd.notna(r.get("tier")) else 3,
             "region": str(r.get("region") or "US"),
             "date": str(r["date"].date()), "src": str(r.get("source") or ""),
             "label": label, "mag": mag, "major": bool(mag >= 20000)}
        if has_ign and pd.notna(r.get("ignition_lat")):
            e["ign"] = [round(float(r["ignition_lat"]), 5),
                        round(float(r["ignition_lon"]), 5)]
        events.append(e)

    stations = [{"id": str(s.site_id), "lat": float(s.lat), "lon": float(s.lon),
                 "region": str(s.region),
                 "grp": "US" if str(s.region) in US else "EU"}
                for s in st.itertuples(index=False)]

    years = sorted({e["year"] for e in events})
    tgs = sorted({e["tg"] for e in events})
    regions = sorted({e["region"] for e in events})

    i_ev = h.index("const EVENTS = ")
    i_st = h.index("const STATIONS = ")
    i_col = h.index("const COLORS = ")
    head, tail = h[:i_ev], h[i_col:]

    # panel: add ignition toggle + retitle
    head = head.replace("WNO Sensors &amp; Events", "WNO Sensors &amp; Events — v5")
    head = head.replace("WNO Sensors & Events", "WNO Sensors & Events — v5")
    head = head.replace(
        '<label><input type="checkbox" id="showMajor"> Label major events</label>',
        '<label><input type="checkbox" id="showMajor"> Label major events</label>\n'
        '  <label><input type="checkbox" id="showIgn"> Ignition points (WFIGS)</label>')

    tail = re.sub(r"mkCheck\('fyear', \[[^\]]*\]",
                  "mkCheck('fyear', " + json.dumps(years), tail)
    tail = re.sub(r"mkCheck\('ftype', \[[^\]]*\]",
                  "mkCheck('ftype', " + json.dumps(tgs), tail)
    tail = re.sub(r"mkCheck\('fregion', \[[^\]]*\]",
                  "mkCheck('fregion', " + json.dumps(regions), tail)

    # ignition drawing inside redraw()
    tail = tail.replace(
        "    m.addTo(evLayer);",
        """    m.addTo(evLayer);
    if(e.ign && document.getElementById('showIgn').checked){
      L.polyline([[e.lat,e.lon],e.ign],{color:col,weight:1,dashArray:'3,3',opacity:.7}).addTo(evLayer);
      L.circleMarker(e.ign,{radius:3,color:'#111',weight:1.5,fillColor:'#fff',fillOpacity:1})
       .bindPopup(`<b>${e.name}</b><br>official ignition point (WFIGS)`).addTo(evLayer);
    }""")

    html = (head + "const EVENTS = " + json.dumps(events) +
            ";\n\nconst STATIONS = " + json.dumps(stations) + ";\n\n" + tail)
    open(OUT, "w", encoding="utf-8").write(html)
    print(f"{OUT}: {len(events)} events ({sum(1 for e in events if 'ign' in e)} "
          f"with ignition), {len(stations)} stations, years {years}")


if __name__ == "__main__":
    main()
