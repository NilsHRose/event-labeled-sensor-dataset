# Multi-Region Event-Labeled Sensor-Network Dataset - Collection Pipeline

Code for building the multi-region, event-labeled sensor-network dataset
described in our IEEE BigData 2026 poster paper (in `paper/`): hourly
air-quality + weather measurements from 516 stations (five US Southwest
states, six European cities, 2022 – June 2026), paired with ~1,700
wildfire and dust-storm events from authoritative sources, with quality
tiers, official area geometries, and fire ignition records.

**Data sources (all official, all public):** US EPA AQS (air quality) ·
EEA e-Reporting (EU air quality) · Open-Meteo/ERA5 (weather) · NIFC WFIGS
(US fires, perimeters, ignition records) · NOAA Storm Events (dust
storms) · NASA FIRMS/VIIRS (EU fire detections).

## Pipeline

Run stages in order; each script prints verification counts when done.

| Stage | Folder | What it does |
| --- | --- | --- |
| 1 | `01_sensors/` | Download EPA bulk hourly files (`fetch_us_bulk.py`); download + convert EEA parquet data (`download_eu_parquets.py`, `convert_eu_v5.py`); join ERA5 weather to every station (`weather_join_v5.py` — resumable, rate-limit aware) |
| 2 | `02_events/` | Pull events from NIFC (`fetch_nifc_fires.py`), NOAA Storm Events (`fetch_noaa_storms.py`), NASA FIRMS (`fetch_firms_eu_fires.py`); match and assemble the master event table (`match_nifc_events.py`, `build_events_v4.py`) |
| 3 | `03_geometry/` | Fetch official fire perimeters (`fetch_fire_perimeters.py`) and NWS zone polygons (`fetch_zone_boundaries.py`); audit point-in-polygon + reported-vs-GIS acreage (`audit_perimeters.py`); join ignition point + discovery size per fire (`fetch_discovery_acres.py`) |
| 4 | `04_build/` | Build the per-region, per-year release tree `wno_split_v5/` (`build_v5_dataset.py --stage split`); propagate ignition columns into the event CSVs (`update_event_startpoints.py`) |
| 5 | `05_figures/` | Paper figures (`fig1_map.py`, `fig2_temporal.py`, `fig3_spatial.py`; `make_paper_figures.py` is the earlier all-in-one version), per-event signal plots (`plot_event_signals.py`), interactive Leaflet map (`gen_event_map_v5.py`) |

## Reproducing the paper figures

```bash
pip install -r requirements.txt
python 05_figures/make_paper_figures.py --base <folder containing Data/ and Maps/> --out paper/figs
```

`--base` must point at a folder holding `Data/events_v5_area.xlsx`,
`Data/wno_split_v5/`, and `Maps/stations.csv` (the released dataset tree).

## Data layout (release)

```
wno_split_v5/
  US/<State>/<State>_<year>.csv          hourly sensor data
  US/<State>/<State>_events_<year>.csv   events incl. ignition columns
  EU/<City>/<City>_<year>.csv
  _boundaries/Perimeters/*.geojson       official fire perimeters
  _boundaries/Zones/*.geojson            NWS forecast zones
events_v5_area.xlsx                      master event table
```

## Notes

- API keys are **not** stored in this repository. The optional AQS API
  route reads a key from `~/.aqs_key`; the bulk-file route used for the
  release needs no key.
- Several fetch scripts are resumable: re-run them until the printed
  coverage is complete.
- Known limitations are documented in the paper and encoded in the data
  (tiers, audit flags, source columns).
