"""Bulk seNorge download script — resumes from where the previous run stopped.

Skips existing monthly files (overwrite=False). After downloading, calls
POST /ingestions to build the zarr stores and register the artifacts.
"""

import logging
import sys
from pathlib import Path

# Make the plugins directory importable so 'import senorge' works.
sys.path.insert(0, str(Path(__file__).parent / "plugins"))

from senorge.daily import download  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

DOWNLOADS_DIR = Path(__file__).parent / "data" / "downloads"
BBOX = [3.0, 57.0, 32.0, 72.5]  # Norway WGS84
START = "1990-01-01"
END = "2026-05-11"

VARIABLES = [
    ("tg", "senorge_temperature_daily"),
    ("rr", "senorge_precipitation_daily"),
]

for variable, prefix in VARIABLES:
    logger.info("=== Downloading %s (%s to %s) ===", prefix, START, END)
    files = download(
        start=START,
        end=END,
        bbox=BBOX,
        dirname=DOWNLOADS_DIR,
        prefix=prefix,
        variable=variable,
        overwrite=False,
    )
    logger.info("Done: %d files present for %s", len(files), prefix)

logger.info("All downloads complete.")
