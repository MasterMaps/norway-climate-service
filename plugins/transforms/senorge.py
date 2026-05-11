"""Custom transforms for seNorge datasets."""

from typing import Any

import xarray as xr


def celsius_to_kelvin(ds: xr.Dataset, dataset: dict[str, Any]) -> xr.Dataset:
    """Convert temperature from degrees Celsius to Kelvin."""
    varname = dataset["variable"]
    ds[varname] = ds[varname] + 273.15
    ds[varname].attrs["units"] = "K"
    return ds
