"""Copy the ignition/discovery columns from events_v5_area.xlsx into the
per-region event CSVs of wno_split_v5 (matched on name + date), and into
the upload copy if present.
"""

from pathlib import Path

import pandas as pd

BASE = Path.home()/"Desktop/Research/Neural Operators/Data"
EV = BASE/"events_v5_area.xlsx"
TREES = [BASE/"wno_split_v5",
         Path.home()/"Desktop/WNO_v5_Upload/wno_split_v5"]

NEWCOLS = ["ignition_lat", "ignition_lon", "ignition_offset_km",
           "ignition_in_polygon", "discovery_acres", "discovery_match"]


def key(df):
    return (df["name"].astype(str).str.strip() + "|" +
            df["date"].astype(str).str[:10])


def main():
    ev = pd.read_excel(EV)
    cols = [c for c in NEWCOLS if c in ev.columns]
    if not cols:
        print("events_v5_area.xlsx hat die neuen Spalten noch nicht — "
              "erst fetch_discovery_acres.py laufen lassen.")
        return
    ev = ev.drop_duplicates(subset=["name", "date"]).copy()
    ev["_k"] = key(ev)
    lut = ev.set_index("_k")[cols]
    print(f"master: {len(ev)} events, {lut[cols[0]].notna().sum()} "
          f"mit Startpunkt-Daten")

    total_files = total_rows = 0
    for tree in TREES:
        if not tree.exists():
            print(f"(übersprungen, fehlt: {tree})")
            continue
        for f in sorted(tree.glob("US/*/*_events_*.csv")):
            df = pd.read_csv(f)
            df["_k"] = key(df)
            df = df.drop(columns=[c for c in cols if c in df.columns])
            df = df.merge(lut, left_on="_k", right_index=True, how="left")
            df = df.drop(columns=["_k"])
            df.to_csv(f, index=False)
            n = df[cols[0]].notna().sum() if cols[0] in df.columns else 0
            total_files += 1
            total_rows += int(n)
            print(f"  {f.relative_to(tree.parent)}: {len(df)} events, "
                  f"{n} mit Startpunkt")
    print(f"\n{total_files} Event-CSVs aktualisiert, "
          f"{total_rows} Zeilen mit Startpunkt-Daten insgesamt")


if __name__ == "__main__":
    main()
