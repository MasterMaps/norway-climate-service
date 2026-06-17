"""SeNorge 2018 daily climate data — BaseDatasetPlugin.

Downloads gridded daily temperature (tg) and precipitation (rr) from the
Norwegian Meteorological Institute's THREDDS OPeNDAP service.

Source: https://thredds.met.no/thredds/catalog/senorge/seNorge_2018/Archive/
Coverage: Norway only, daily from 1957-01-01.
Native resolution: 1 km x 1 km on UTM33 grid (EPSG:32633).

THREDDS serves annual NetCDF files over OPeNDAP.  The full Norway grid is
always returned — no bbox subsetting at the source.  One plugin period is one
calendar day; the annual file is opened once per year and cached on the plugin
instance so that fetching 365 consecutive days causes only one OPeNDAP
connection per year.  Dimension names are uppercase X/Y and ``time`` in the
source; they are renamed to lowercase x/y and the canonical ``t`` before
writing.  Timestamps are at 06:00 UTC (seNorge convention for meteorological
days).
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

import pyproj
import xarray as xr

from open_climate_service.streaming import BaseDatasetPlugin

logger = logging.getLogger(__name__)

THREDDS_BASE = "https://thredds.met.no/thredds/dodsC/senorge/seNorge_2018/Archive"
SENORGE_CRS = "EPSG:32633"

# SeNorge data starts in 1957; earlier years do not exist.
DATA_START_YEAR = 1957

_VARIABLES = ("tg", "rr")


class SeNorgePlugin(BaseDatasetPlugin):
    """BaseDatasetPlugin for seNorge 2018 daily temperature and precipitation.

    Each period is one calendar day (YYYY-MM-DD).  The annual NetCDF file for
    a given year is opened once and cached on the instance so that fetching a
    full year causes only a single OPeNDAP connection.

    No ``probe`` is declared: the orchestrator infers the grid (shape, dtype,
    and nodata from the source ``_FillValue``) from the first fetched period.
    Only the CRS cannot be inferred from the fetched data — seNorge is on a
    projected UTM33 grid and the data carries no CRS once the auxiliary
    longitude/latitude coordinates are dropped — so it is declared via the
    ``crs`` class attribute.

    Args:
        variable: seNorge variable name — 'tg' (daily mean temperature, °C)
            or 'rr' (daily precipitation, mm).
    """

    max_concurrency = 1
    commit_batch_size = 30
    crs = 32633

    def __init__(self, variable: str, **_: Any) -> None:
        if variable not in _VARIABLES:
            raise ValueError(f"variable must be 'tg' or 'rr', got {variable!r}")
        self.variable = variable
        self._cache_year: int | None = None
        self._cache_ds: xr.Dataset | None = None

    async def periods(self, start: str, end: str) -> list[str]:
        """Return daily period IDs clamped to seNorge availability (1957-01-01 onwards)."""
        clamped_start = max(start[:10], f"{DATA_START_YEAR}-01-01")
        return _daily_dates(clamped_start, end[:10])

    async def fetch_period(self, period_id: str, bbox: list[float], **_: Any) -> xr.Dataset:
        """Fetch one day from the annual THREDDS OPeNDAP file, clip to bbox."""
        year = int(period_id[:4])
        utm_bbox = _wgs84_bbox_to_utm33(bbox)
        if self._cache_year != year:
            url = f"{THREDDS_BASE}/seNorge2018_{year}.nc"
            logger.info("Opening seNorge annual file for %d: %s", year, url)
            self._cache_ds = xr.open_dataset(url, engine="netcdf4", chunks={})
            self._cache_year = year
        assert self._cache_ds is not None
        ds = _prepare(self._cache_ds, utm_bbox, self.variable)
        day = period_id[:10]
        logger.info("Fetching seNorge %s", day)
        return ds.sel(t=slice(day, day)).load()


def _daily_dates(start: str, end: str) -> list[str]:
    """Return ISO date strings for every day in [start, end]."""
    d_start = date.fromisoformat(start)
    d_end = date.fromisoformat(end)
    results = []
    current = d_start
    while current <= d_end:
        results.append(current.isoformat())
        current += timedelta(days=1)
    return results


def _wgs84_bbox_to_utm33(bbox: list[float]) -> tuple[float, float, float, float]:
    """Convert a WGS84 [xmin, ymin, xmax, ymax] bbox to UTM33 coordinates."""
    transformer = pyproj.Transformer.from_crs("EPSG:4326", SENORGE_CRS, always_xy=True)
    corners_lon = [bbox[0], bbox[2], bbox[0], bbox[2]]
    corners_lat = [bbox[1], bbox[1], bbox[3], bbox[3]]
    xs, ys = transformer.transform(corners_lon, corners_lat)
    return float(min(xs)), float(min(ys)), float(max(xs)), float(max(ys))


def _prepare(ds: xr.Dataset, utm_bbox: tuple[float, float, float, float], variable: str) -> xr.Dataset:
    """Subset spatially, keep only the target variable, and normalise dimension names.

    The native seNorge grid uses uppercase X/Y dimension names, a ``time``
    dimension, and 2D auxiliary longitude/latitude coordinate arrays.  The
    orchestrator and the rest of the stack expect lowercase x/y spatial
    dimensions, the canonical ``t`` time dimension, and no 2D auxiliary
    coordinates.
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

    drop_vars = [v for v in ds.coords if v in ("longitude", "latitude")]
    if drop_vars:
        ds = ds.drop_vars(drop_vars)

    ds = ds.rename({"X": "x", "Y": "y", "time": "t"})

    if "t" in ds.coords:
        ds["t"] = ds["t"].astype("datetime64[ns]")

    return ds
