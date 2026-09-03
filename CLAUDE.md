# Project rules

Note: this captures my design decisions for this project. The full reasoning
lives in DESIGN.md — read it before writing any code; this file is the short
operating manual. Some specifics (exact response shapes, cache TTL values,
batch sizes) may be refined during implementation. The layering and
principles below are what I intend to hold.

## What this is

A read-only FastAPI service with one endpoint that, for a set of hotels and a
month, returns each hotel's current lowest price per arrival date and the
difference vs the same date X years ago ("pre-corona"). Pricing lives in a
Bigtable-style key-value store, NOT a relational database. Managed with uv,
Makefile for common commands.

`GET /pricing/pre_corona_difference/` — params: month (YYYY-MM), currency
(3-letter), hotels (array of ints, <= 10), years_ago (int 1-5), cancellable
(bool, default true). Returns one row per hotel per arrival date; the
`difference` field is nullable.

## Architecture

- Layered: app/api (thin HTTP handlers) -> app/services (logic) ->
  app/adapters (store, cache). Keep routes thin — no business logic in the API
  layer.
- Two ports in app/services/ports.py (Protocols the services depend on):
  - `PricingStore` — a batch `get_latest_readings(pairs)` that hides the
    index-then-get resolution and returns the newest reading per (hotel,
    arrival).
  - `Cache` — `get(key)`, `set(key, value, ttl)`.
- Services depend only on these Protocols, never on concrete infrastructure.
- Adapters: `InMemoryPricingStore` (seeded fake — readings + latest-extract
  index) and `InMemoryCache` (dict + TTL). Real Bigtable/Redis adapters are
  drop-in replacements — described in DESIGN.md, not built here.
- Config from environment via app/config.py. No hardcoded values or secrets.

## No relational database

This build does NOT use Postgres, SQLAlchemy, Alembic, or docker-compose. The
system of record is the external KV store, which we model with an in-memory
fake. Do not scaffold a database, migrations, or a DB container unless a
concrete need emerges and I approve it first.

## Data model (the KV store — non-negotiable)

- Key = (hotel_id, extract_date, arrival_date), dates as days-since-epoch.
  extract_date = the day the price was scraped; arrival_date = the guest stay.
- Value = bytes -> deserialise -> dict with a `prices` list of rate options
  (price_value, currency, is_cancellable, room_name, ...). One reading is a
  single currency.
- The same (hotel, arrival) has many entries — one per scrape day. "Current"
  = the entry with the newest extract_date.
- Assumption: the acquisition team maintains a latest-extract side-index
  (hotel_id, arrival_date) -> newest extract_date. We only READ it. We do not
  write the store or the index.

## Behaviour rules (the locked decisions)

- Newest-extract resolution is O(1), never a scan. Current = the known
  last-scrape-day -> direct key. Historic = look up the side-index -> get.
- Currency is a FILTER, not a conversion. Only use readings already in the
  requested currency. FX conversion is future scope, not built.
- Historic date = same month/day, year - years_ago. Missing historic (data
  gap, or a non-existent Feb 29) -> return the current price with
  `difference: null`. Missing current -> OMIT that row.
- "Lowest price" = min(price_value) within the newest reading, AFTER filtering
  its prices by currency + cancellable. Filter before min so a wrong-currency
  or wrong-cancellable option can never win.
- Graceful degradation: per-row problems degrade (null / omit) and the request
  returns 200 with partial results. A missing key is expected (degrade); a
  store outage is a failure (error).

## Performance

- One request fans out to up to ~620 reads. Batch all needed keys into a few
  multi-gets; the handler is async (the work is I/O-bound).
- In-memory cache behind the Cache port: historic prices are immutable ->
  cache indefinitely; current prices change once a day -> TTL until the next
  scrape. Redis is the production drop-in (same port).
- structlog middleware logs duration_ms per request (the deck's "log the time
  each request took"); optional X-Response-Time-ms header.

## Error handling

Deliberate and scoped to this problem. Typed domain errors, mapped in one
place. Keep the error format simple — one consistent JSON error shape, not a
heavyweight envelope:
- Input validation -> 422 (FastAPI/pydantic + a single handler, one error shape).
- StoreUnavailableError (outage/timeout) -> 502.
- Per-item missing data is not an error — it degrades (null / omit).

## Conventions

- Python 3.12, full type hints, pydantic schemas, structlog for logging.
  uv for dependencies, ruff for lint/format, Makefile for commands.
- Every module has a top-of-file docstring stating its purpose. Every public
  function, method, and class has a docstring describing what it does —
  including tests. Keep docstrings short and useful, not verbose.
- Logging: use `structlog.get_logger(__name__)` with key-value kwargs — not
  `logging.getLogger` + `extra` (its fields do not render under the current
  config).

## Testing

- pytest. Unit tests are the default and must be deterministic and offline.
- Unit-test services against the fake PricingStore and fake Cache — no network.
  Cover: lowest-price selection, currency filter, cancellable filter, historic
  mapping, missing-historic -> null, missing-current -> omit, Feb 29, batching
  correctness, cache hit/miss + TTL.
- Integration tests drive the endpoint through FastAPI's TestClient, injecting
  a seeded in-memory store/cache via dependency_overrides. Assert the response
  shape matches the OpenAPI contract and the degradation rules.

## Ways of working

- Build one phase at a time, then stop for review. A passing test and a commit
  per phase. Explain non-trivial choices in the commit message.
