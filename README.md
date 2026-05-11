# Norway Climate Service

This project is based on the [Open Climate Service](https://dhis2.github.io/climate-api/) and is intended solely as an example of how Open Climate Service can be adapted for a national context (here, Norwegian climate data). It is not a production service, but a demonstration of adaptation and integration principles.

This repository provides tools and scripts for downloading, processing, and serving Norwegian climate data, including daily temperature and precipitation from the SeNorge dataset.

## Installation

1. **Clone the repository:**
   ```sh
   git clone https://github.com/MasterMaps/norway-climate-service.git
   cd norway-climate-service
   ```
2. **Install dependencies:**
   It is recommended to use [uv](https://github.com/astral-sh/uv) for dependency management.

   ```sh
   uv sync
   ```

   This will create a `.venv` and install all dependencies as specified in `pyproject.toml` and `uv.lock`. If you use `make install`, it will also run `uv sync` for you.

## Usage

### Running the Instance

You can run this instance following the official Open Climate Service pattern:

1. **Install dependencies:**

   ```sh
   make install
   ```

2. **Start the API/service:**
   ```sh
   make run
   ```

This will start the API (by default at http://localhost:8000). Visit `/extent` to confirm the API is running and returning your configured bounding box. The OpenAPI/Swagger UI is typically available at `/docs`.

#### Ingest Data via the API

Once the service is running, you can ingest data by making a POST request to the ingestion endpoint (e.g., `/ingestions`).

Example using `curl`:

```sh
curl -X POST http://localhost:8000/ingestions \
  -H "Content-Type: application/json" \
  -d '{
        "dataset": "senorge_temperature_daily",
        "source": "data/downloads/senorge_temperature_daily_1990-01.nc"
      }'
```
