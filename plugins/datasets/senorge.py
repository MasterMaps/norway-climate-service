"""SeNorge 2018 daily climate data — IngestionPlugin.

Downloads gridded daily temperature (tg) and precipitation (rr) from the
Norwegian Meteorological Institute's THREDDS OPeNDAP service.

Source: https://thredds.met.no/thredds/catalog/senorge/seNorge_2018/Archive/
Coverage: Norway only, daily from 1957-01-01.
Native resolution: 1 km x 1 km on UTM33 grid (EPSG:32633).

THREDDS serves annual NetCDF files over OPeNDAP.  The full Norway grid is
always returned — no bbox subsetting at the source.  One plugin period is one
calendar day; the annual file is opened once per year and cached on the plugin
instance so that fetching 365 consecutive days causes only one OPeNDAP
connection per year.  Dimension names are uppercase X/Y in the source; they
are renamed to lowercase x/y before writing.  Timestamps are at 06:00 UTC
(seNorge convention for meteorological days).
"""

from __future__ import annotations

import logging
import math
from datetime import date
from typing import Any

import pyproj
import xarray as xr

from climate_api.ingest.protocol import GridSpec, enumerate_periods

logger = logging.getLogger(__name__)

THREDDS_BASE = "https://thredds.met.no/thredds/dodsC/senorge/seNorge_2018/Archive"
SENORGE_CRS = "EPSG:32633"

# SeNorge data starts in 1957; earlier years do not exist.
DATA_START_YEAR = 1957
# Native grid resolution in metres (1 km × 1 km UTM33).
_SENORGE_RES_M = 1000.0

_NODATA = {"tg": -999.99, "rr": -9999.0}


class SeNorgePlugin:
    """IngestionPlugin for seNorge 2018 daily temperature and precipitation.

    Each period is one calendar day (YYYY-MM-DD).  The annual NetCDF file for
    a given year is opened once and cached on the instance so that fetching a
    full year causes only a single OPeNDAP connection.

    Args:
        variable: seNorge variable name — 'tg' (daily mean temperature, °C)
            or 'rr' (daily precipitation, mm).
    """

    max_concurrency = 1
    commit_batch_size = 30
    rechunk_time = 30

    def __init__(self, variable: str) -> None:
        if variable not in _NODATA:
            raise ValueError(f"variable must be 'tg' or 'rr', got {variable!r}")
        self.variable = variable
        self._cache_year: int | None = None
        self._cache_ds: xr.Dataset | None = None

    def probe(self, bbox: list[float], **_: Any) -> GridSpec:
        """Derive GridSpec from seNorge's known 1 km UTM33 resolution — no data transfer."""
        utm_bbox = _wgs84_bbox_to_utm33(bbox)
        xmin, ymin, xmax, ymax = utm_bbox
        nx = max(1, math.ceil((xmax - xmin) / _SENORGE_RES_M))
        ny = max(1, math.ceil((ymax - ymin) / _SENORGE_RES_M))
        return GridSpec(
            shape=(ny, nx),
            crs=32633,
            dtype="float32",
            nodata=_NODATA[self.variable],
        )

    def periods(self, start: str, end: str) -> list[str]:
        """Return daily period IDs clamped to seNorge availability (1957-01-01 onwards)."""
        clamped_start = max(start[:10], f"{DATA_START_YEAR}-01-01")
        return enumerate_periods(clamped_start, end, "daily")

    def fetch_period(self, period_id: str, bbox: list[float], **_: Any) -> xr.Dataset:
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
        return ds.sel(time=slice(day, day)).load()


def _wgs84_bbox_to_utm33(bbox: list[float]) -> tuple[float, float, float, float]:
    """Convert a WGS84 [xmin, ymin, xmax, ymax] bbox to UTM33 coordinates."""
    transformer = pyproj.Transformer.from_crs("EPSG:4326", SENORGE_CRS, always_xy=True)
    corners_lon = [bbox[0], bbox[2], bbox[0], bbox[2]]
    corners_lat = [bbox[1], bbox[1], bbox[3], bbox[3]]
    xs, ys = transformer.transform(corners_lon, corners_lat)
    return float(min(xs)), float(min(ys)), float(max(xs)), float(max(ys))


def _prepare(ds: xr.Dataset, utm_bbox: tuple[float, float, float, float], variable: str) -> xr.Dataset:
    """Subset spatially, keep only the target variable, and normalise dimension names.

    The native seNorge grid uses uppercase X/Y dimension names and includes
    2D auxiliary longitude/latitude coordinate arrays.  The orchestrator
    expects lowercase x/y spatial dimensions and no 2D auxiliary coordinates.
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

    ds = ds.rename({"X": "x", "Y": "y"})

    if "time" in ds.coords:
        ds["time"] = ds["time"].astype("datetime64[ns]")

    return ds
