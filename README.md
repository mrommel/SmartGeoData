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

Geocoding requires a running **omlx** server with an OpenAI-compatible chat completions endpoint. Set `OMLX_MODEL` in `.env` to a model served by omlx. Set `OMLX_API_KEY` if your server requires Bearer authentication. `OMLX_BASE_URL` defaults to `http://127.0.0.1:8000/v1` (override it if your server uses another host or port); `OMLX_TIMEOUT` defaults to 15 seconds. The server extracts street, house number, city, county, state, country, and postal code as JSON; only names found by the local street/city tokenizers and matching database records produce results. The house number does not affect coordinates (which remain city coordinates).

## Geocoding API

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

The `street` key appears only for street matches. Results contain city coordinates (not a street address's precise location) and are limited to 10. An unmatched query returns `{"results": []}`; missing, blank, or overlong `text` returns HTTP 400 with an `error` message. If omlx is unavailable, unconfigured, or returns invalid JSON, the endpoint returns HTTP 503. The endpoint accepts GET only.

## Tests

```sh
make venv
./.venv/bin/python manage.py test geo
```

The test suite uses an in-memory SQLite database.

To exercise the **real omlx server** and tokenizer/database matching end to end, start omlx, set `OMLX_MODEL` to a served model (and `OMLX_BASE_URL` if not using the default), then run `make test_e2e` (equivalent to):

```sh
RUN_OMLX_E2E=1 ./.venv/bin/python manage.py test geo.test_e2e --tag=e2e
```

The live test seeds real-world Berlin, Paris, and New York addresses in a temporary SQLite test database, sends actual requests to omlx, and checks complete API responses. It allows 120 seconds per inference (for local model startup). It does not read or modify your PostgreSQL database. Live tests are skipped by default when running `manage.py test geo`; with `RUN_OMLX_E2E=1`, an unreachable or incorrectly configured model fails the test rather than silently skipping it. Model extraction can vary between models; use an instruction-following model capable of returning JSON.

## Deployment note

The checked-in Django settings enable `DEBUG` and leave `ALLOWED_HOSTS` empty. Configure production-safe settings before deploying; do not commit `.env` or reuse its local secrets in production. The provided Compose file starts PostgreSQL only, not Django.
