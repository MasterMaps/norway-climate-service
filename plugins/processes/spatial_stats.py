"""Custom spatial statistics process for the Norway Climate API instance."""

from typing import Any


def execute_spatial_mean(
    dataset_id: str,
    statistic: str = "mean",
) -> dict[str, Any]:
    """Compute the spatial mean (or min/max) of a dataset over its full extent.

    Args:
        dataset_id: The managed dataset identifier (e.g. ``worldpop_population_yearly_nor``).
        statistic: One of ``"mean"``, ``"min"``, or ``"max"``.

    Returns:
        A dict with the dataset_id, statistic name, and the computed value per time step.
    """
    from climate_api.data_accessor.services.accessor import open_zarr_dataset
    from climate_api.ingestions.services import group_datasets

    if statistic not in ("mean", "min", "max"):
        raise ValueError(f"statistic must be one of 'mean', 'min', 'max', got {statistic!r}")

    groups = group_datasets()
    artifacts = [a for a in groups.get(dataset_id, []) if a.format.value == "zarr" and a.path]
    if not artifacts:
        raise ValueError(f"No zarr artifact found for dataset_id={dataset_id!r}")

    artifact = max(artifacts, key=lambda a: a.created_at)
    ds = open_zarr_dataset(artifact.path)
    variable = next(iter(ds.data_vars))
    da = ds[variable]

    spatial_dims = [d for d in da.dims if d != "time"]
    if statistic == "mean":
        result = da.mean(dim=spatial_dims)
    elif statistic == "min":
        result = da.min(dim=spatial_dims)
    else:
        result = da.max(dim=spatial_dims)

    values = result.values.tolist()
    times = da.time.values.astype(str).tolist() if "time" in da.dims else []

    return {
        "dataset_id": dataset_id,
        "variable": variable,
        "statistic": statistic,
        "values": values if isinstance(values, list) else [values],
        "times": times,
    }
