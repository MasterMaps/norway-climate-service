"""SeNorge 2018 daily climate data downloader.

Downloads gridded daily temperature (tg) and precipitation (rr) from the
Norwegian Meteorological Institute's THREDDS OPeNDAP service and saves
monthly NetCDF files in the native UTM33 grid (EPSG:32633).

Source: https://thredds.met.no/thredds/catalog/senorge/seNorge_2018/Archive/
Coverage: Norway only, daily from 1957-01-01.
Native resolution: 1 km x 1 km on UTM33 grid.
"""

from __future__ import annotations

import logging
from calendar import monthrange
from datetime import date
from pathlib import Path

import pyproj
import xarray as xr

logger = logging.getLogger(__name__)

THREDDS_BASE = "https://thredds.met.no/thredds/dodsC/senorge/seNorge_2018/Archive"
SENORGE_CRS = "EPSG:32633"

# SeNorge data starts in 1957; earlier years do not exist.
DATA_START_YEAR = 1957


def download(
    start: str,
    end: str,
    bbox: list[float],
    dirname: str | Path,
    prefix: str,
    variable: str = "tg",
    overwrite: bool = False,
) -> list[Path]:
    """Download SeNorge 2018 daily data from THREDDS OPeNDAP.

    Saves one NetCDF file per month under ``dirname`` named
    ``{prefix}_{YYYY}-{MM}.nc``. Data is stored in the native UTM33 grid
    (EPSG:32633) with spatial dimensions named ``x`` and ``y``.

    Args:
        start: ISO date string for the first day to include (YYYY-MM-DD).
        end: ISO date string for the last day to include (YYYY-MM-DD).
        bbox: [xmin, ymin, xmax, ymax] in WGS84 degrees.
        dirname: Directory in which to write the output files.
        prefix: Filename prefix (dataset id).
        variable: SeNorge variable name — ``"tg"`` (temperature) or ``"rr"`` (precipitation).
        overwrite: If False, skip months whose output file already exists.

    Returns:
        Sorted list of output file paths that exist after the run.
    """
    dirname = Path(dirname)
    dirname.mkdir(parents=True, exist_ok=True)

    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)

    utm_bbox = _wgs84_bbox_to_utm33(bbox)
    files: list[Path] = []

    for year in range(start_date.year, end_date.year + 1):
        if year < DATA_START_YEAR:
            logger.warning("SeNorge data starts in %d, skipping year %d", DATA_START_YEAR, year)
            continue

        month_start = start_date.month if year == start_date.year else 1
        month_end = end_date.month if year == end_date.year else 12

        url = f"{THREDDS_BASE}/seNorge2018_{year}.nc"
        logger.info("Opening SeNorge %d from %s", year, url)

        try:
            ds_year = xr.open_dataset(url, engine="netcdf4", chunks=None)
        except OSError as exc:
            logger.error("Failed to open SeNorge %d: %s", year, exc)
            raise

        ds_year = _prepare(ds_year, utm_bbox, variable)

        for month in range(month_start, month_end + 1):
            save_path = dirname / f"{prefix}_{year}-{month:02d}.nc"
            files.append(save_path)

            if not overwrite and save_path.exists():
                logger.info("Already downloaded: %s", save_path.name)
                continue

            day_start = date(year, month, 1)
            day_end = date(year, month, monthrange(year, month)[1])
            if year == start_date.year and month == start_date.month:
                day_start = max(day_start, start_date)
            if year == end_date.year and month == end_date.month:
                day_end = min(day_end, end_date)

            time_slice = slice(day_start.isoformat(), day_end.isoformat())
            ds_month = ds_year.sel(time=time_slice)

            if ds_month.sizes.get("time", 0) == 0:
                logger.warning("No data for %d-%02d in SeNorge file, skipping", year, month)
                continue

            logger.info("Saving %d-%02d (%d days)", year, month, ds_month.sizes["time"])
            try:
                ds_month.to_netcdf(save_path)
            except Exception:
                save_path.unlink(missing_ok=True)
                raise
            logger.info("Saved %s", save_path.name)

        ds_year.close()

    return sorted(p for p in files if p.exists())


def _wgs84_bbox_to_utm33(bbox: list[float]) -> tuple[float, float, float, float]:
    """Convert a WGS84 [xmin, ymin, xmax, ymax] bbox to UTM33 coordinates."""
    transformer = pyproj.Transformer.from_crs("EPSG:4326", SENORGE_CRS, always_xy=True)
    corners_lon = [bbox[0], bbox[2], bbox[0], bbox[2]]
    corners_lat = [bbox[1], bbox[1], bbox[3], bbox[3]]
    xs, ys = transformer.transform(corners_lon, corners_lat)
    return float(min(xs)), float(min(ys)), float(max(xs)), float(max(ys))


def _prepare(ds: xr.Dataset, utm_bbox: tuple[float, float, float, float], variable: str) -> xr.Dataset:
    """Subset spatially, keep only the target variable, and normalise dimension names.

    The native SeNorge grid uses uppercase ``X``/``Y`` dimension names and
    includes 2D auxiliary ``longitude``/``latitude`` coordinate arrays.  The
    climate-api zarr builder expects lowercase ``x``/``y`` spatial dimensions
    and no 2D auxiliary coordinates (which would confuse dimension detection).
    """
    x_min, y_min, x_max, y_max = utm_bbox

    x_coord = ds["X"].values
    y_coord = ds["Y"].values
    x_ascending = x_coord[-1] > x_coord[0]
    y_ascending = y_coord[-1] > y_coord[0]
    x_slice = slice(x_min, x_max) if x_ascending else slice(x_max, x_min)
    y_slice = slice(y_min, y_max) if y_ascending else slice(y_max, y_min)
    ds = ds.sel(X=x_slice, Y=y_slice)

    ds = ds[[variable]]

    # Drop 2D auxiliary lat/lon arrays — they are not dimensions and would
    # cause get_lon_lat_dims to misidentify the spatial dimensions.
    drop_vars = [v for v in ds.coords if v in ("longitude", "latitude")]
    if drop_vars:
        ds = ds.drop_vars(drop_vars)

    # Rename X/Y → x/y so get_lon_lat_dims finds them via the ("x", "y") fallback.
    ds = ds.rename({"X": "x", "Y": "y"})

    # Ensure time coordinate encodes as datetime64 for CF compatibility.
    if "time" in ds.coords:
        ds["time"] = ds["time"].astype("datetime64[ns]")

    return ds
