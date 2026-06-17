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
connection per year.  Timestamps are at 06:00 UTC (seNorge convention for
meteorological days).

The source uses uppercase X/Y dims, a ``time`` dim, and 2D auxiliary
longitude/latitude coordinates; ``normalize_period`` handles all of that —
dropping the 2D helpers, renaming to the canonical x/y/t, and reprojecting the
WGS84 bbox onto the UTM33 grid for the spatial clip.
"""

from __future__ import annotations

import logging
from typing import Any

import xarray as xr

from open_climate_service.shared.time import daily_period_ids
from open_climate_service.streaming import BaseDatasetPlugin, normalize_period

logger = logging.getLogger(__name__)

THREDDS_BASE = "https://thredds.met.no/thredds/dodsC/senorge/seNorge_2018/Archive"

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
    The CRS alone cannot be inferred once the data is normalised, so it is
    declared via the ``crs`` class attribute — which also drives the bbox
    reprojection in ``normalize_period``.

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
        return daily_period_ids(clamped_start, end[:10])

    async def fetch_period(self, period_id: str, bbox: list[float], **_: Any) -> xr.Dataset:
        """Fetch one day from the annual THREDDS OPeNDAP file, clipped to bbox."""
        import rioxarray  # noqa: F401  # activates the .rio accessor for write_crs

        year = int(period_id[:4])
        if self._cache_year != year:
            url = f"{THREDDS_BASE}/seNorge2018_{year}.nc"
            logger.info("Opening seNorge annual file for %d: %s", year, url)
            self._cache_ds = xr.open_dataset(url, engine="netcdf4", chunks={})
            self._cache_year = year
        assert self._cache_ds is not None

        day = period_id[:10]
        logger.info("Fetching seNorge %s", day)
        ds = self._cache_ds[[self.variable]].sel(time=slice(day, day)).rio.write_crs(self.crs)
        return normalize_period(ds, variable=self.variable, bbox=bbox).load()
