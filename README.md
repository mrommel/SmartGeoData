# SmartGeoData

SmartGeoData is a Django project for storing geographic names and resolving city or street queries to a city's coordinates. It models countries, states, counties, cities, streets, and alternative names, and exposes a JSON geocoding endpoint.

## Run locally

Requires Python 3.12 or newer, `make`, and Docker Compose. Copy `.env.example` to `.env` and replace both placeholder values. The `.env` file is ignored by Git; Django loads it via `python-dotenv`, while Docker Compose reads it automatically for variable substitution. If you already have a `.env`, add `DJANGO_SECRET_KEY` and `POSTGRES_PASSWORD` instead of overwriting it.

Start PostgreSQL before migrating or running Django:

```sh
docker compose up -d
```

The app connects to the PostgreSQL container on localhost port 5435. If you have an existing PostgreSQL volume initialized with a different password or `trust` authentication, changing `.env` alone will not change the database user's password; update that user's password or recreate the volume if its data is disposable.

```sh
make venv
make migrate
make run
```

Run the django-tasks database worker in another terminal (after migrating):

```sh
./.venv/bin/python manage.py db_worker
```

Starting the web app queues city and street tokenizer population only if no task has been queued for that tokenizer yet. The worker builds persistent snapshots; web processes load the completed snapshots when needed. Server restarts reuse existing tasks instead of repeatedly rebuilding them. After changing geographic names, or to retry a failed task, run `./.venv/bin/python manage.py refresh_tokenizers` to queue a new pair. Without a worker, population remains pending and geocoding returns HTTP 503.

The development server runs on port 9112. A fresh database has no geographic records, so searches return no results until data is entered. The geographic models are not currently registered in Django admin; use the Django shell to add records. For example, in a second terminal after running `make venv` and `make migrate`:

```sh
./.venv/bin/python manage.py shell <<'PY'
from geo.models import City, Country, State, StreetName

country, _ = Country.objects.get_or_create(name='Germany')
state, _ = State.objects.get_or_create(name='Berlin', defaults={'country': country})
city, _ = City.objects.update_or_create(
    name='Berlin',
    defaults={'country': country, 'state': state, 'zip_code': '10115,10117',
              'lat': 52.52, 'lng': 13.405},
)
street, _ = StreetName.objects.get_or_create(name='Unter den Linden')
street.cities.add(city)
PY
```

Cities need `lat` and `lng` to appear in geocoding results. Street queries require a street-to-city association; alternative city and street names can be added for matching.

Open `http://127.0.0.1:9112/` in a browser to geocode one address using the web form. It displays matches and their city coordinates via the same API described below. JavaScript must be enabled.

Geocoding requires a running **omlx** server with an OpenAI-compatible chat completions endpoint. Set `OMLX_MODEL` in `.env` to a model served by omlx. Set `OMLX_API_KEY` if your server requires Bearer authentication. `OMLX_BASE_URL` defaults to `http://127.0.0.1:8000/v1` (override it if your server uses another host or port); `OMLX_TIMEOUT` defaults to 15 seconds. The server extracts street, house number, city, county, state, country, and postal code as JSON; only names found by the local street/city tokenizers and matching database records produce results. The house number does not affect coordinates (which remain city coordinates).

## Geocoding API

Interactive documentation for `/api/geocode/`, `/api/tokenizer-status/`, and `/api/health/` is at `http://127.0.0.1:9112/swagger/`. The OpenAPI 3 schema is available at `/api/openapi.json`. Swagger UI loads its JavaScript and CSS from a version-pinned jsDelivr CDN, so the interactive page needs an internet connection; the schema itself does not.

Send a GET request to `/api/geocode/` with a `text` query parameter (1–255 characters):

```sh
curl --get 'http://127.0.0.1:9112/api/geocode/' \
  --data-urlencode 'text=Unter den Linden 12, 10115 Berlin, Germany'
```

If matching data has been entered, the response has this shape:

```json
{
  "results": [
    {
      "street": "Unter den Linden",
      "city": "Berlin",
      "county": null,
      "state": "Berlin",
      "country": "Germany",
      "zip_code": "10115,10117",
      "lat": 52.52,
      "lng": 13.405
    }
  ]
}
```

The `street` key appears only for street matches. Results contain city coordinates (not a street address's precise location) and are limited to 10. An unmatched query returns `{"results": []}`; missing, blank, or overlong `text` returns HTTP 400 with an `error` message. If omlx is unavailable, unconfigured, returns invalid JSON, or tokenizer population has not completed, the endpoint returns HTTP 503. The endpoint accepts GET only.

GET `/api/tokenizer-status/` reports both tasks and the overall population state:

```json
{"status": "running", "tokenizers": {"city": "running", "street": "pending"}}
```

States are `pending`, `running`, `completed`, and `failed`. A failed tokenizer makes the overall status `failed`; run `./.venv/bin/python manage.py refresh_tokenizers` after fixing the underlying data to enqueue fresh tasks.

GET `/api/health/` checks **geocoding readiness** (including database access to the tokenizer tasks). It returns HTTP 200 with `{"status":"ready","tokenizers":{"city":"completed","street":"completed"}}` when both tokenizers are ready, or HTTP 503 with `status: "unavailable"` and their current states while they are not ready. If the database status check fails, it returns HTTP 503 with `{"status":"unavailable"}`. It does not check whether omlx is reachable or whether an address will match. For example:

```sh
curl -i http://127.0.0.1:9112/api/health/
```

## MCP tools for LLM clients

An MCP (Model Context Protocol) server exposes `geocode_address(text)` and `geocoding_health()` as tools. `geocode_address` uses the same `/api/geocode/` endpoint and returns its `{"results": [...]}` response, including up to 10 **city-level** coordinates; `geocoding_health` returns the `/api/health/` JSON even when the endpoint reports 503. Unavailable web/omlx services or invalid geocode input produce a tool error.

First run `make migrate`, `make run`, and the background worker as described above; configure omlx and add geographic data for nonempty results. Start the MCP HTTP server in a **separate terminal**:

```sh
make run_mcp
```

It listens at `http://127.0.0.1:9113/mcp` using Streamable HTTP. Before connecting a client, check **both** processes from another terminal:

```sh
curl -fsS http://127.0.0.1:9113/health        # MCP process: {"status":"ok"}
curl -i http://127.0.0.1:9112/api/health/    # Django: HTTP 200 ready, or 503 until tokenizers finish
```

The MCP `/health` endpoint checks only that its process is running; Django's `/api/health/` checks tokenizer/database readiness, not omlx. If either process is not running, curl will fail to connect. Configure an MCP client that supports Streamable HTTP with URL `http://127.0.0.1:9113/mcp` (the MCP endpoint is not a browser page). Alternatively, clients that start their own servers can still use **stdio** and absolute paths for your checkout (replace `/path/to/SmartGeoData`):

```json
{
  "mcpServers": {
    "smartgeodata": {
      "command": "/path/to/SmartGeoData/.venv/bin/python",
      "args": ["/path/to/SmartGeoData/geo/mcp_server.py"],
      "env": {
        "SMARTGEODATA_API_URL": "http://127.0.0.1:9112"
      }
    }
  }
}
```

`SMARTGEODATA_API_URL` defaults to `http://127.0.0.1:9112` if omitted and applies to both transports. `SMARTGEODATA_MCP_HOST` and `SMARTGEODATA_MCP_PORT` can override the HTTP bind address and port (defaults: `127.0.0.1` and `9113`). The MCP process must be able to reach Django; for remote instances, set the Django base URL and secure access appropriately. Neither transport starts Django, the worker, or omlx. Keep the HTTP server bound to localhost unless you add authentication and transport security. Consult your MCP client's documentation for the exact configuration file/location.

## Tests

```sh
make venv
./.venv/bin/python manage.py test geo
```

Tests live in the `geo/tests/` package and use an in-memory SQLite database. `manage.py test geo` discovers all test modules there.

To exercise the **real omlx server** and tokenizer/database matching end to end, start omlx, set `OMLX_MODEL` to a served model (and `OMLX_BASE_URL` if not using the default), then run `make test_e2e` (equivalent to):

```sh
RUN_OMLX_E2E=1 ./.venv/bin/python manage.py test geo.tests.test_e2e --tag=e2e
```

The live test seeds real-world Berlin, Paris, and New York addresses in a temporary SQLite test database, sends actual requests to omlx, and checks complete API responses. It allows 120 seconds per inference (for local model startup). It does not read or modify your PostgreSQL database. Live tests are skipped by default when running `manage.py test geo`; with `RUN_OMLX_E2E=1`, an unreachable or incorrectly configured model fails the test rather than silently skipping it. Model extraction can vary between models; use an instruction-following model capable of returning JSON.

## Deployment note

The checked-in Django settings enable `DEBUG` and leave `ALLOWED_HOSTS` empty. Configure production-safe settings before deploying; do not commit `.env` or reuse its local secrets in production. The provided Compose file starts PostgreSQL only, not Django.
