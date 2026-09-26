# Demo samples

Small inputs (6 MB in total) used by [docs/DEMO.md](../docs/DEMO.md) and `manifest.json`. These are
the only raster files committed to the repo.

| File | What | Bands (use as band roles) | Source / licence |
|---|---|---|---|
| `rsvqa_lr_232.tif` | RSVQA-LR test image 232, 256 x 256, 3-band RGB | auto (RGB) | RSVQA-LR (Lobry et al., 2020), [Zenodo 6344334](https://zenodo.org/records/6344334), CC-BY-4.0 |
| `bellandur_s2_2024q1.tif` | Sentinel-2 L2A median, Jan-Mar 2024, Bellandur, Bengaluru, 10 m, EPSG:32643 | `blue,green,red,nir,swir1` | Contains modified Copernicus Sentinel data 2024 (via Google Earth Engine) |
| `bellandur_s1_2024q1.tif` | Sentinel-1 GRD IW median (dB), same period and grid | `vv,vh` | Contains modified Copernicus Sentinel data 2024 |
| `sarjapur_s2_2019q1.tif` | Sentinel-2 L2A median, Jan-Mar 2019, Sarjapur Road, Bengaluru | `blue,green,red,nir,swir1,swir2` | Contains modified Copernicus Sentinel data 2019 |
| `sarjapur_s2_2021q1.tif` | same area, Jan-Mar 2021 | `blue,green,red,nir,swir1,swir2` | Contains modified Copernicus Sentinel data 2021 |
| `sarjapur_s2_2025q1.tif` | same area, Jan-Mar 2025 | `blue,green,red,nir,swir1,swir2` | Contains modified Copernicus Sentinel data 2025 |

Earth Engine exports drop band names, so give the band roles above in the upload form
(Advanced) or in `manifest.json`.
