# Pre-Corona Pricing Difference API — Design

> The design doc for the Lighthouse technical case. It pins the architecture and
> the decisions before any code. It doubles as the presentation backbone.
> Python 3.12 · FastAPI · uv · ports & adapters · structlog.

## What this is

A **read-only** FastAPI service with one endpoint that, for a set of hotels and a
month, returns each hotel's **current lowest price per arrival date** and the
**difference vs the same date `X` years ago** ("pre-corona"). Pricing lives in a
**key-value store** (Bigtable-style), not a relational DB.

`GET /pricing/pre_corona_difference/`
- `month` — `YYYY-MM` (required)
- `currency` — 3-letter code (required)
- `hotels` — array of ints, ≤ 10 (required)
- `years_ago` — int 1–5 (required)
- `cancellable` — bool, default `true`

Response: `{ "prices": [ { hotel, price, currency, difference, arrival_date } ] }`
— one row per hotel per arrival date in the month. `difference` is **nullable**.

## Architecture

- **Layered:** `app/api` (thin HTTP handlers) → `app/services` (logic) →
  `app/adapters` (store, cache). Routes stay thin.
- **Ports** (`app/services/ports.py`, Protocols the services depend on):
  - `PricingStore` — `get_latest_readings(pairs) -> dict[(hotel, arrival), Reading]`
    (batch), hiding the index-then-get resolution.
  - `Cache` — `get(key)`, `set(key, value, ttl)`.
- **Adapters:**
  - `InMemoryPricingStore` — seeded fake (readings + latest-extract index).
  - `InMemoryCache` — dict + TTL (`cachetools`-style).
  - Real `Bigtable`/`Redis` adapters are drop-in replacements — described, not built.
- **Config** from env (`app/config.py`). No hardcoded values.

## Data model (the KV store — NON-NEGOTIABLE)

- **Key** = `(hotel_id, extract_date, arrival_date)`, dates as **days-since-epoch**.
  - `extract_date` = the day the price was scraped. `arrival_date` = the guest's stay.
- **Value** = **bytes** → deserialise → dict with a `prices` list of rate options
  (`price_value`, `currency`, `is_cancellable`, `room_name`, …). One reading is a
  single currency.
- The **same `(hotel, arrival)` has many entries** — one per scrape day. "Current"
  = the entry with the **newest `extract_date`**.
- **Assumption:** the acquisition team maintains a **latest-extract side-index**
  `(hotel_id, arrival_date) → newest extract_date` (most naturally another keyspace
  in the same KV store, updated on each scrape). We only **read** it.

## Locked decisions

1. **"Newest extract" resolution.** A KV `get` needs the whole key, but the request
   only gives hotel + arrival — the newest `extract_date` is unknown. Resolve it O(1)
   via a **side-index** `(hotel, arrival) → newest extract_date`, then `get` by the
   full key. Never scan.
   - The store port is **uniform**: it resolves the newest reading for any
     `(hotel, arrival)` pair the same way, for **both** current and historic — so the
     read path doesn't distinguish them.
   - *Optional optimisation (not built):* for a **current** arrival the newest scrape
     is the **last scrape day**, so the index lookup could be skipped with a direct
     key. We keep the index for both because it's simpler and **more robust** — the
     last-scrape-day shortcut assumes every hotel was scraped that day and silently
     misses any whose latest scrape was earlier, whereas the index always points at
     the true newest.
   (If we owned the key we'd order it `(hotel, arrival, extract)` for a native range
   query; the key is fixed, so an index is the pragmatic answer.)
2. **Currency = filter, not convert.** Only use readings already in the requested
   currency; keeps `difference` a clean same-currency subtraction. **FX conversion**
   (and the historical-rate methodology) is **future scope**.
3. **Historic date** = same month/day, `year − years_ago`. Missing historic (data
   gap, or a non-existent Feb 29) → return the current price with **`difference: null`**.
   Missing **current** → **omit** that row.
4. **"Lowest price"** = `min(price_value)` within the newest reading, **after**
   filtering its `prices` by currency + `cancellable`. The `cancellable` flag is a
   toggle (**assumption**): `true` (default) keeps only cancellable options; `false`
   applies no cancellability filter.
5. **Graceful degradation.** Per-row problems degrade (null / omit); the request
   returns **`200` with partial results**. Hard stops only for **bad input → `422`**
   and **store unavailable → `5xx`**. A missing key is *expected* (degrade); a store
   outage is a *failure* (error).
6. **Performance / fan-out.** One request ≈ up to 620 reads.
   - **Build:** **batch** all needed keys into a few multi-gets. The handler is a
     **sync `def`** — FastAPI runs it in a threadpool, so a blocking store call gives
     cross-request concurrency without stalling the event loop. An **async store
     adapter** (awaited) is the future step for event-loop concurrency.
   - **Build:** **in-memory cache** behind the `Cache` port — *historic cached
     indefinitely (immutable), current with a TTL until the next scrape.* Redis is
     the production drop-in (same port; in-memory is single-process, lost on restart).
   - **Request timing:** structlog **middleware** logs `duration_ms` per request
     (+ optional `X-Response-Time-ms` header).

## The operations pipeline — and why this order (graded deliverable)

**Why this order.** Two principles drive the sequence: *(1) do the cheapest,
most-eliminating work first*, and *(2) each step sets up the next.* So we reject
bad input before touching anything; gather **all** keys up front because you can
only batch reads you've enumerated; hit the **cheap cache before the expensive
store**; **batch** the store for just the misses; and leave the light in-memory
decode/transform to the end, on only the data we actually fetched. In short:
**reject cheaply → gather keys so you can batch → cache before store → batch the
store → transform in memory last.** The goal throughout is to minimise expensive
I/O (store round-trips) and make each step possible.

1. **Validate & parse params.** *First — cheapest to reject; never touch the store
   for a bad request.* → `422` on failure.
2. **Expand the work set.** For each hotel × each arrival date in the month, compute
   the current lookup and the `historic_arrival = year − years_ago`. *Compute all
   keys up front so the reads can be batched.*
3. **Cache first.** Look up each needed value in the cache; collect the misses.
   *The cache is the cheapest source, and immutable-historic + daily-current give a
   high hit rate.*
4. **Batch-read the store for the misses.** Index batch (historic) + value batch(es),
   using the known last-scrape-day for current. *Minimise round-trips across the fan-out.*
5. **Decode → filter → pick lowest.** Deserialise each reading, filter `prices` by
   currency + `cancellable`, take `min(price_value)`. *Cheap in-memory work on only
   what we fetched; filter before min so a wrong-currency/cancellable price can't win.*
6. **Compute the difference** = `current − historic` (`null` if historic missing);
   **write results to the cache.**
7. **Assemble the response** (omit no-current rows); **log request duration.**

*One-line motivation:* reject-cheap-first → compute keys so you can batch → cache
before store → batch the store → transform/aggregate in memory last.

## Error handling

Deliberate and scoped to this problem. Typed domain errors, mapped in one
place — one consistent JSON error shape, kept deliberately simple:
- Input validation → `422` (FastAPI/pydantic + a single handler for one error shape).
- `StoreUnavailableError` (outage/timeout) → `502`.
- **Per-item missing data is not an error** — it degrades (null / omit).

## Conventions

- Python 3.12, full type hints, pydantic schemas, structlog. uv + ruff.
- **Money as `float`** to match the OpenAPI `number` type and the source data; a
  single same-currency subtraction of display prices makes float acceptable here.
  A real pricing system should use **integer minor units + currency code** with
  integer arithmetic and float only at the display edge (the model we run in
  production) — which also makes cross-currency operations an explicit error.
- Module-level docstring on every file; short docstring on every public
  function/class, **including tests**. Docstrings state *what* a function does and
  its contract (args / returns / edge behaviour) — design **rationale** lives in
  this doc, not in docstrings. No `ai-usage/` folder.

## Testing

- **Unit** (offline, deterministic): services against a fake `PricingStore` + fake
  `Cache`. Cover: lowest-price selection, currency filter, cancellable filter,
  historic mapping, missing-historic → null, missing-current → omit, Feb 29,
  batching correctness, cache hit/miss + TTL.
- **Integration:** endpoint via FastAPI `TestClient` with `dependency_overrides`
  injecting a seeded in-memory store/cache. Assert the response shape matches the
  OpenAPI contract and the degradation rules.

## Risks (graded)

- **KV fan-out / latency** at 10k users → batching + caching are the mitigations.
- **Cache invalidation** on each new daily scrape (current TTL); in-memory cache
  isn't shared across replicas → Redis in production.
- **Gappy historic data** (COVID, pre-dataset) → null differences; surface clearly.
- **Currency coverage** — no FX, so limited to the stored currency.
- **"Newest extract" depends on** side-index correctness / scrape reliability.
- **Deserialisation CPU cost** (GIL-bound) if it ever dominates → faster codec /
  worker processes.
- **Hot keys / thundering herd** on popular hotels-months → cache + request coalescing.

## Future scope (graded)

- **FX conversion** with an explicit historical-rate methodology.
- **Competitor comparison** (the deck mock-up): own vs a competitor set.
- More filters (room type, length-of-stay, meal, occupancy); pagination.
- **Precomputed/materialised differences**; streaming updates on new scrapes.
- Shared **Redis** cache; response-level caching; CDN edge caching.
- **Negative caching** of permanent historic gaps — cache a "no data" marker for
  historic misses (they never change) so known gaps aren't re-read every request.
- Observability: metrics, tracing, SLOs on the per-request timing.
