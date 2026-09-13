# Resto'U Paris - CROUS cafeterias availability map

A static web map showing the live open/closed status of CROUS student restaurants, cafeterias and self-service points in Paris. Status is computed client-side from opening hours scraped from the official open-data dataset of the French Ministry of Higher Education and Research (the same dataset powering etudiant.gouv.fr).

## Data source

- Dataset: `fr_crous_restauration_france_entiere` (MESR Opendatasoft platform).
- API: `https://mesr.opendatasoft.com/api/explore/v2.1/catalog/datasets/fr_crous_restauration_france_entiere/records`
- Filter: `zone like "Paris*"` (configurable in `scrape.py`).

Opening hours exist only as free text in the `infos` field. The scraper parses this into a structured weekly schedule.

## Repository layout

```text
.
├── .github/workflows/refresh-data.yml  # scheduled re-scrape (weekdays 05:00 UTC)
├── data/paris.json                     # generated snapshot
├── scripts/scrape.py                   # scraper and parser
├── index.html                          # map page (Leaflet)
├── app.js                              # status computation, markers, legend
├── style.css                           # layout, popups, mobile adjustments
└── README.md
```

## How it works

### Scraper (`scripts/scrape.py`)
1. Fetches records from the MESR API.
2. Extracts the "Horaires" section from the `infos` text.
3. Parses French day/time expressions into a weekly schedule of minute intervals.
4. Classifies access (`all`, `restricted`, `staff`, `unknown`) based on text heuristics.
5. Detects closures by cross-referencing textual notices ("fermé pour travaux") with the API's `closing` flag.
6. Writes `data/paris.json`.

### Map client (`app.js`)
- **Grouping:** Venues sharing coordinates (rounded to 5 decimals, ~1m) are grouped into a single marker. The popup lists all venues at that spot.
- **Status:** Recomputed every 60s in the `Europe/Paris` timezone via `Intl.DateTimeFormat`.
- **Colors:** Marker color reflects the best status among grouped venues.

| Colour | Hex | Meaning |
|---|---|---|
| Dark green | `#006400` | Open, closes in 2+ hours |
| Green | `#00a650` | Open, closes in 1-2 hours |
| Yellow | `#ffd400` | Open, closes in < 1 hour |
| Blue | `#1e88e5` | Closed, opens within 1 hour |
| Red | `#e53935` | Closed |
| Dark grey | `#424242` | Confirmed long-term closure |
| Grey | `#8d8d8d` | Hours unknown / unparseable |

## Configuration

Key constants can be adjusted directly in the source files:
- `app.js` -> `CONFIG`: Time thresholds (`darkGreenMin`, `greenMin`, `opensSoonMin`), refresh interval, map center/zoom, and coordinate grouping precision (`groupDecimals`).
- `scripts/scrape.py` -> `WHERE`: ODSQL filter for the API (set to `''` to scrape all ~750 venues in France).

## Attribution
- **Data:** MESR `fr_crous_restauration_france_entiere`, Licence Ouverte / Etalab.
- **Basemap:** OpenStreetMap contributors.
