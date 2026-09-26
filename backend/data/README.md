# backend/data

`india_locations.json` is the only data file the backend ships with. It lists all 36 states and union
territories of India (28 states + 8 UTs) and 734 districts. For each one it stores the name, a centroid
(lat/lon), a bounding box `[west, south, east, north]` and a map zoom level. Each state also has a short
`major_cities` list (the capital, when it is a district of that state, then the biggest cities; each
entry points at a district in the list) and `aliases` for old or source spellings (e.g. `Bangalore` ->
`Bengaluru Urban`, `Mangaluru` -> `Dakshina Kannada`). No boundary polygons are stored.

It is generated once by [`scripts/build_india_locations.py`](../../scripts/build_india_locations.py) and
read from disk at runtime, so the app does not need Earth Engine or internet to show the list.

## Source, version, licence

| | ADM1 (states / UTs) | ADM2 (districts) |
|---|---|---|
| Dataset | geoBoundaries gbOpen `IND-ADM1-1811400` | geoBoundaries gbOpen `IND-ADM2-76128533` |
| Represents | 2011 boundaries with the 2019-2020 UT changes (Ladakh; Dadra and Nagar Haveli and Daman and Diu) | 2021 district list |
| Original source | DataMeet India community, Election Commission of India | Pathways Data Pvt. Ltd., lgdirectory.gov.in |
| Licence | CC BY 2.5 IN | ODbL 1.0 |

geoBoundaries release commit `9469f09` (built 12 Dec 2023), simplified geometries. Citation: Runfola, D.
et al. (2020) *geoBoundaries: A global database of political administrative boundaries.* PLoS ONE 15(4):
e0231866. https://www.geoboundaries.org. The same boundaries are in the Earth Engine catalog
(`WM/geoLab/geoBoundaries/600/ADM1`, `.../ADM2`).

Because the districts are ODbL, this derived file is also shared under **ODbL 1.0**
(attribution: geoBoundaries / Pathways Data / lgdirectory.gov.in; DataMeet for the states).

## How it was built

- Districts carry no state in the source, so each is assigned to the state it overlaps most. Yanam (an
  enclave of Puducherry inside Andhra Pradesh) is set explicitly; a placeholder polygon named
  "DATA NOT AVAILABLE" (Ladakh) is dropped.
- Typos and Census transliterations are replaced by current official / common names (e.g. `Hydrabad` ->
  `Hyderabad`, `Haora` -> `Howrah`, `Gurgaon` -> `Gurugram`, `Allahabad` -> `Prayagraj`); every source
  name that changes is kept as an alias. The full table is in the script.
- Centroid: the polygon centroid, or a point guaranteed inside the district when the centroid falls
  outside (odd shapes). Zoom: the level at which the bounding box fits a ~500 px map, clamped to 5-12.

## Known limits

- The district list is from **2021**. Later changes are not in it, e.g. Andhra Pradesh's 2022
  reorganisation (13 -> 26 districts; the file has the 13 old ones), Rajasthan's 2023 new districts,
  and other new districts created since 2021. They will appear when geoBoundaries publishes a newer list
  and the script is re-run.
- Bounding boxes come from simplified boundaries, so they are slightly approximate.

## Rebuild

```powershell
.\.venv\Scripts\python.exe -m pip install shapely   # only needed for the build script
.\.venv\Scripts\python.exe scripts\build_india_locations.py
```
