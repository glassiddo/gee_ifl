# Annual loss of intact forest landscapes

[Read the case study (PDF)](docs/ifl-case-study.pdf) 

Google Earth Engine code for estimating annual IFL loss from satellite forest-loss data and spatial criteria. Developed for Houngbedji, Isman, Plakhtieva and Wren-Lewis (2026), *What are the Limits to Voluntary Certification? Evidence from an Attempt to Protect Biodiversity* (working paper).

## Repository contents

| File | Purpose |
| --- | --- |
| `code/ifl_maps_by_year.py` | Two-stage annual processing and task orchestration in the Earth Engine Python API |
| `code/regions_ifl.py` | Manually drawn processing regions, designed to avoid cutting through IFL patches |
| `code/combine_regions.js` | GEE Code Editor helper for mosaicking regional outputs |
| `code/create_shapefile_from_assets.js` | Export helper for the earlier 2001-2020 assets and naming conventions |
| `docs/` | Case-study PDF |

## Method in the current code

1. **Start from a reference map.** Each configured interval starts from its official IFL baseline. A preliminary step applies the spatial filters to the baseline before annual updates.
2. **Find annual disturbance.** Select Hansen forest-loss pixels inside the previous year's remaining IFL, with at least 30% tree cover in 2000. Exclude mapped fire loss where the fire dataset covers the year.
3. **Group disturbance.** Keep groups of at least three connected pixels, including diagonal neighbours. Buffer by 1km, merge overlapping areas through vectorisation at 100m, and retain buffered groups with a loss-mask sum of at least 30 evaluated at 100m. This threshold is not a count of 30 native 30m pixels and should not be converted directly into a hectare threshold.
4. **Filter narrow parts.** Erode the remaining IFL by 1km, regrow by 1.5km, and intersect with the area before this operation. This approximates the 2km corridor/appendage criterion while limiting regrowth to the original area. The 10km broadest-width test was not applied because it changed little and was expensive.
5. **Filter small patches.** Save the intermediate at 30m, then vectorise at 200m to identify patches smaller than 500km². Buffer the small-patch mask by 100m before removing it from the detailed raster.
6. **Constrain and repeat.** Restore baseline areas outside the official interval-loss mask, save the final 30m output, and use it for the following year. For 2021-2024, the interval-loss mask comes from the 2020 and 2025 IFL snapshots.

The script stores remaining-IFL maps as intermediate/final assets. Annual loss estimates are obtained from changes between successive outputs. These are estimates of loss timing, not exact annual ground truth.

### Data

- Hansen global forest change: `UMD/hansen/global_forest_change_2024_v1_12`.
- Fire-related forest loss: `users/sashatyu/2001-2023_fire_forest_loss_annual`. This does not cover 2024.
- IFL snapshots: 2000, 2013, 2016, 2020 and 2025. The script references project-specific Earth Engine copies.

## References

- Hansen et al. (2013). *High-resolution global maps of 21st-century forest cover change*. Science, 342, 850-853. https://doi.org/10.1126/science.1244693
- Potapov et al. (2017). *The last frontiers of wilderness: Tracking loss of intact forest landscapes from 2000 to 2013*. Science Advances, 3, e1600821. https://doi.org/10.1126/sciadv.1600821
- Tyukavina et al. (2022). *Global trends of forest loss due to fire from 2001 to 2019*. Frontiers in Remote Sensing, 3, 825190. https://doi.org/10.3389/frsen.2022.825190
- IFL Mapping Team (2025). *Intact Forest Landscapes Extent and Change, 2000-2025*. https://zenodo.org/records/18011599

