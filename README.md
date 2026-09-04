# Pre-Corona Pricing API

A read-only FastAPI service with a single endpoint: for a set of hotels and a month, it
returns each hotel's current lowest price per arrival date alongside the difference against
the same date a few years ago, the "pre-corona" comparison. Pricing is read from a
Bigtable-style key-value store, not a relational database; this build models that store with
an in-memory fake so the whole service runs offline.

## The endpoint

```
GET /pricing/pre_corona_difference/
```

| Parameter | Type | Notes |
| --- | --- | --- |
| `month` | `YYYY-MM` | Required. The arrival month. |
| `currency` | 3-letter code | Required, uppercase (e.g. `SGD`). A filter, not a conversion. |
| `hotels` | list of ints | Required, 1–10 hotel ids. Repeat the parameter per hotel. |
| `years_ago` | int | Required, 1–5. How far back the comparison reaches. |
| `cancellable` | bool | Optional, defaults to `true`. |

The response is one row per hotel per arrival date, with a nullable `difference`:

```json
{
  "prices": [
    {
      "hotel": 3173269,
      "price": 261.0,
      "currency": "SGD",
      "difference": 70.0,
      "arrival_date": "2026-10-01"
    }
  ]
}
```

Invalid input returns `422`; an outage of the underlying store returns `502`. Every response
carries an `X-Response-Time-ms` header, and each request is logged with its `duration_ms`.

The full contract lives in [`openapi.yaml`](openapi.yaml) at the repo root, and the running
service serves interactive docs at <http://127.0.0.1:8000/docs>.

## Quickstart

The only prerequisite is [uv](https://docs.astral.sh/uv/); it manages Python 3.12 and every
dependency. There is no Docker and no database to start.

```bash
make install    # uv sync
make run        # uvicorn with reload, on http://127.0.0.1:8000
make test       # pytest
make lint       # ruff check
make fmt        # ruff format
make fmt-check  # ruff format --check
make typecheck  # mypy, strict
```

With the service running, the seeded demo dataset covers October 2026 for hotels `3173269`
and `3173270`. Pipe any call to [`jq`](https://jqlang.github.io/jq/) for readable output; it
is optional, the JSON prints fine without it.

**Request timing and caching** — every response carries an `X-Response-Time-ms` header. Run
this call twice: the first is cold and reads the store; the second is served from the warm
cache and is markedly faster. Run it before the happy path below (or restart the service) so
the first call is genuinely cold.

```bash
curl -s -D - -o /dev/null "http://127.0.0.1:8000/pricing/pre_corona_difference/?month=2026-10&currency=SGD&hotels=3173269&hotels=3173270&years_ago=5" | grep -i x-response-time
```

**Happy path** — one row per hotel per arrival date:

```bash
curl -s "http://127.0.0.1:8000/pricing/pre_corona_difference/?month=2026-10&currency=SGD&hotels=3173269&hotels=3173270&years_ago=5" | jq
```

The seeded data deliberately contains gaps, so this response shows both degradation rules:
arrival day 7 is **omitted** (no current price), and days 14 and 15 come back with
`difference: null` (no historic price).

**A rejected request** — a month outside `01`–`12` fails validation with `422` before the
store is touched. The `-w` flag prints the status code after the body:

```bash
curl -s -w "\nHTTP %{http_code}\n" "http://127.0.0.1:8000/pricing/pre_corona_difference/?month=2026-13&currency=SGD&hotels=3173269&years_ago=5"
```

The body names the failing field and the reason (`value_error`, "Month must be between 01 and
12."), and the trailing line shows `HTTP 422`.

For the full parameter set, and to try requests interactively, open the docs at
<http://127.0.0.1:8000/docs>.

## Project layout

The code is layered, with dependencies pointing inward: HTTP handlers depend on services,
services depend on ports, and adapters implement those ports.

| Path | What lives there |
| --- | --- |
| `app/api/` | Thin FastAPI routers, validation, mapping, error registration. No business logic. |
| `app/services/` | `ports.py` defines the `PricingStore` and `Cache` Protocols; `pricing_service.py` is the pipeline. |
| `app/adapters/` | `InMemoryPricingStore` and `InMemoryCache`, plus the demo dataset that seeds them. |
| `app/domain/` | Framework-free models and pure calculations (date maths, lowest-price selection). |
| `app/schemas/` | Pydantic request/response shapes, the wire contract, kept out of the domain. |

The domain imports nothing but the standard library, and the service depends only on the two
Protocols, never on a concrete adapter. Swapping the fakes for Bigtable and Redis is a change
to `app/adapters/` and `app/dependencies.py` alone.

## Design and decisions

The service resolves the newest price for a hotel and arrival date in constant time rather
than scanning: a latest-extract side-index maps each `(hotel, arrival)` pair to its newest scrape, so both
current and historic prices resolve with an O(1) index lookup and then a get. (For a current
arrival the newest scrape is simply the last-scrape day — a direct-key shortcut we note but
don't build, since the index is simpler and robust to a hotel that missed a scrape.) The
acquisition pipeline maintains the index; this service only reads it.
A single request fans out to hundreds of reads, so the pipeline expands the whole work set up
front, checks the cache before the store, and batches every remaining lookup into one
multi-get. Historic prices are immutable and cached indefinitely; current prices carry a TTL.

The reasoning behind that ordering, along with the risks, the rejected alternatives and the
future scope (FX conversion, competitor comparison, precomputed differences), is written up
in [DESIGN.md](DESIGN.md), which is the document to read before changing behaviour.

## Assumptions

Currency is a **filter, not a conversion**: only readings already stored in the requested
currency are considered, which keeps `difference` an honest same-currency subtraction. FX is
future scope.

Money is carried as `float`. That is a deliberate simplification for a comparison API whose
output is a difference between two scraped prices, not a billing system; `Decimal` would be
the right call the moment these numbers are charged to anyone.

`cancellable=true` narrows the rate options to cancellable ones. `cancellable=false` applies
**no** cancellability filter at all, it means "any rate", not "non-cancellable only", so it
can return either.

Missing data degrades rather than failing the request. A missing **historic** price, a genuine
data gap, or a 29 February with no counterpart in the target year, returns the current price
with `difference: null`. A missing **current** price omits that row entirely. Both cases still
return `200` with partial results; only bad input (`422`) and a store outage (`502`) are hard
failures.

## Testing

```bash
make test                 # everything
uv run pytest tests/domain tests/services   # unit only
uv run pytest tests/api                     # integration only
```

Unit tests cover the domain calculations and drive the pricing service against the in-memory
store and cache through the ports, asserting the batching, caching and degradation rules
directly. Integration tests drive the endpoint through FastAPI's `TestClient`, injecting a
seeded stack via `dependency_overrides` to assert the response shape, the validation failures
and the `502` mapping. Everything is deterministic and offline, TTL expiry is driven by an
injected fake clock rather than by sleeping.

The in-memory adapters are both the production stand-in and the test double. They exist so the
service can be tested without a Bigtable or Redis instance; in production they are replaced by
real adapters implementing the same two Protocols.
