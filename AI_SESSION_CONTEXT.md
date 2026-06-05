# AI Session Context — TransitFlow

**How to use this file:**
At the start of every AI coding session, paste the full contents of this file as your first message to your AI assistant. This gives the AI the context it needs to produce code that fits your codebase and is consistent with your teammates' work.

**Who maintains this file:**
Whoever makes a schema change or architectural decision updates this file in the same commit. Treat it like a team contract.

---

## Project Overview

TransitFlow is a Python-based AI chat assistant for a fictional transit operator. It queries three databases — PostgreSQL (relational + vector), Neo4j (graph) — and uses an LLM to answer user questions. Our task as students is to design the database schema and implement the query functions in `databases/relational/queries.py` and `databases/graph/queries.py`.

## Tech Stack

- Language: Python 3.11+
- Relational DB: PostgreSQL via `psycopg2` with `RealDictCursor`
- Graph DB: Neo4j via the `neo4j` Python driver
- Vector search: `pgvector` extension (already implemented — do not modify)
- Web UI: Gradio
- LLM: Google Gemini or local Ollama (configured via `.env`)

> **Port & connection config:** Database ports and credentials are **not** hardcoded — copy `.env.example` to `.env` and fill in your values before running. Key variables include `POSTGRES_PORT` (default `5433`), `NEO4J_PORT` (default `7688`), and `NEO4J_URI` / `POSTGRES_*` credentials. Each team member must set up their own `.env` locally.

## Coding Conventions

- **Naming:** `snake_case` for all Python names and SQL identifiers
- **Docstrings:** All functions must have a docstring with `Args:` and `Returns:` sections
- **Return types:** Use type hints. Read-only functions return `list[dict]` or `Optional[dict]`
- **Empty results:** Return `[]` or `None` (as documented), never raise an exception for "not found"
- **SQL:** Use `%s` placeholders for all user inputs — never string-format into SQL
- **Relational pattern:** Use `_connect()` helper + `psycopg2.extras.RealDictCursor`:
  ```python
  with _connect() as conn:
      with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
          cur.execute("SELECT ...", (param,))
          return [dict(row) for row in cur.fetchall()]
  ```
- **Graph pattern:** Use `_driver()` helper + session:
  ```python
  with _driver() as driver:
      with driver.session() as session:
          result = session.run("MATCH ...", station_id=station_id)
          return [dict(record) for record in result]
  ```

## Agreed Relational Schema

<!-- ============================================================
  FILL THIS IN after your team completes the schema design workshop.
  Paste your final CREATE TABLE statements here.
  ============================================================ -->
### Key design decisions
1. Metro and national rail are modelled as **completely separate table families** — separate stations, schedules, stop lists, and travel records.
2. Stop ordering is normalised into `metro_schedule_stops` and `national_rail_schedule_stops` (join tables with a `stop_order` integer) rather than storing stops as arrays.
3. National rail seat layout is normalised into three levels: `national_rail_seat_layouts` → `national_rail_coaches` → `national_rail_seats`.
4. `payments` links to **either** a `bookings` row (national rail) **or** a `metro_travel_history` row — enforced by a `CHECK` that exactly one FK is non-null.
5. `metro_stations` and `national_rail_stations` have a mutual interchange FK. Both are declared with `DEFERRABLE INITIALLY DEFERRED` via `ALTER TABLE` so seed data can be loaded before the cross-reference is validated.
6. `bookings` stores `amount_usd` at the time of booking so the original fare is preserved even if pricing rules change later.
### Full schema
 
```sql
-- ============================================================
-- 1. REGISTERED USERS
-- ============================================================
CREATE TABLE registered_users (
    user_id           VARCHAR(20) PRIMARY KEY,
    name              TEXT NOT NULL,
    email             TEXT NOT NULL UNIQUE,
    password_hash     TEXT NOT NULL,
    phone_number      VARCHAR(20),
    year_of_birth     INTEGER,
    secret_question   TEXT,
    secret_answer     TEXT,
    registered_at     TIMESTAMPTZ DEFAULT NOW(),
    is_active         BOOLEAN DEFAULT TRUE
);
 
-- ============================================================
-- 2. METRO STATIONS
-- (cross-reference FK to national_rail_stations added via ALTER TABLE below)
-- ============================================================
CREATE TABLE metro_stations (
    station_id                   VARCHAR(10) PRIMARY KEY,
    name                         TEXT NOT NULL,
    is_interchange_metro         BOOLEAN NOT NULL,
    is_interchange_national_rail BOOLEAN NOT NULL,
    interchange_rail_station_id  VARCHAR(10)
);
 
-- ============================================================
-- 3. METRO SCHEDULES
-- ============================================================
CREATE TABLE metro_schedules (
    schedule_id         VARCHAR(20) PRIMARY KEY,
    line                VARCHAR(20) NOT NULL,
    direction           VARCHAR(50) NOT NULL,
    departure_time      TIME NOT NULL,
    arrival_time        TIME NOT NULL,
    frequency_min       INTEGER NOT NULL,
    base_fare_usd       DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    per_stop_fare_usd   DECIMAL(10,2) NOT NULL DEFAULT 0.00
);
 
-- ============================================================
-- 4. METRO SCHEDULE STOPS
-- PK = (schedule_id, stop_order); UNIQUE = (schedule_id, station_id)
-- ============================================================
CREATE TABLE metro_schedule_stops (
    schedule_id  VARCHAR(20) NOT NULL,
    station_id   VARCHAR(10) NOT NULL,
    stop_order   INTEGER NOT NULL,
    PRIMARY KEY (schedule_id, stop_order),
    UNIQUE (schedule_id, station_id),
    FOREIGN KEY (schedule_id) REFERENCES metro_schedules(schedule_id) ON DELETE CASCADE,
    FOREIGN KEY (station_id)  REFERENCES metro_stations(station_id)   ON DELETE CASCADE,
    CHECK (stop_order > 0)
);
 
-- ============================================================
-- 5. METRO TRAVEL HISTORY
-- tap_out_time / exit_station_id are NULL while trip is in_progress.
-- A completed trip must have both set (enforced by CHECK).
-- ============================================================
CREATE TABLE metro_travel_history (
    trip_id             VARCHAR(20) PRIMARY KEY,
    user_id             VARCHAR(20) NOT NULL,
    schedule_id         VARCHAR(20),
    entry_station_id    VARCHAR(10) NOT NULL,
    exit_station_id     VARCHAR(10),
    ticket_type         VARCHAR(20) NOT NULL,
    travel_date         DATE NOT NULL,
    tap_in_time         TIMESTAMPTZ NOT NULL,
    tap_out_time        TIMESTAMPTZ,
    amount_usd          DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    status              VARCHAR(20) NOT NULL,
    FOREIGN KEY (user_id)          REFERENCES registered_users(user_id)   ON DELETE CASCADE,
    FOREIGN KEY (schedule_id)      REFERENCES metro_schedules(schedule_id) ON DELETE CASCADE,
    FOREIGN KEY (entry_station_id) REFERENCES metro_stations(station_id)   ON DELETE CASCADE,
    FOREIGN KEY (exit_station_id)  REFERENCES metro_stations(station_id)   ON DELETE CASCADE,
    CHECK (tap_out_time IS NULL OR tap_out_time > tap_in_time),
    CHECK (amount_usd >= 0),
    CHECK (status IN ('completed', 'in_progress', 'cancelled')),
    CHECK (status != 'completed' OR (tap_out_time IS NOT NULL AND exit_station_id IS NOT NULL))
);
 
-- ============================================================
-- 6. NATIONAL RAIL STATIONS
-- (cross-reference FK to metro_stations added via ALTER TABLE below)
-- ============================================================
CREATE TABLE national_rail_stations (
    station_id                              VARCHAR(10) PRIMARY KEY,
    name                                    TEXT NOT NULL,
    city                                    VARCHAR(50),
    is_interchange_metro                    BOOLEAN NOT NULL,
    is_interchange_national_rail            BOOLEAN NOT NULL,
    interchange_national_rail_station_lines TEXT[],
    interchange_metro_station_id            VARCHAR(10),
    CONSTRAINT chk_national_rail_interchange_lines
    CHECK (
        (is_interchange_national_rail = TRUE
         AND interchange_national_rail_station_lines IS NOT NULL
         AND array_length(interchange_national_rail_station_lines, 1) > 0)
        OR
        (is_interchange_national_rail = FALSE
         AND (interchange_national_rail_station_lines IS NULL
              OR array_length(interchange_national_rail_station_lines, 1) = 0))
    )
);
 
-- Mutual interchange FKs (DEFERRABLE to allow seed inserts before validation)
ALTER TABLE metro_stations
    ADD CONSTRAINT fk_metro_interchange_rail
    FOREIGN KEY (interchange_rail_station_id)
    REFERENCES national_rail_stations(station_id)
    ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED;
 
ALTER TABLE national_rail_stations
    ADD CONSTRAINT fk_national_rail_interchange_metro
    FOREIGN KEY (interchange_metro_station_id)
    REFERENCES metro_stations(station_id)
    ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED;
 
-- ============================================================
-- 7. NATIONAL RAIL SCHEDULES
-- ============================================================
CREATE TABLE national_rail_schedules (
    schedule_id       VARCHAR(20) PRIMARY KEY,
    line              VARCHAR(20) NOT NULL,
    service_type      VARCHAR(50) NOT NULL,   -- 'express' | 'local'
    direction         VARCHAR(50) NOT NULL,
    departure_time    TIME NOT NULL,
    arrival_time      TIME NOT NULL,
    base_fare_usd     DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    per_stop_fare_usd DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    CHECK (base_fare_usd >= 0 AND per_stop_fare_usd >= 0)
);
 
-- ============================================================
-- 8. NATIONAL RAIL SCHEDULE STOPS
-- Same PK convention as metro_schedule_stops.
-- ============================================================
CREATE TABLE national_rail_schedule_stops (
    schedule_id  VARCHAR(20) NOT NULL,
    station_id   VARCHAR(10) NOT NULL,
    stop_order   INTEGER NOT NULL,
    PRIMARY KEY (schedule_id, stop_order),
    UNIQUE (schedule_id, station_id),
    FOREIGN KEY (schedule_id) REFERENCES national_rail_schedules(schedule_id) ON DELETE CASCADE,
    FOREIGN KEY (station_id)  REFERENCES national_rail_stations(station_id)   ON DELETE CASCADE,
    CHECK (stop_order > 0)
);
 
-- ============================================================
-- 9. NATIONAL RAIL SEAT LAYOUTS  (top level)
-- ============================================================
CREATE TABLE national_rail_seat_layouts (
    schedule_id  VARCHAR(20) NOT NULL,
    layout_id    VARCHAR(20) PRIMARY KEY,
    FOREIGN KEY (schedule_id) REFERENCES national_rail_schedules(schedule_id) ON DELETE CASCADE
);
 
-- ============================================================
-- 10. NATIONAL RAIL COACHES
-- ============================================================
CREATE TABLE national_rail_coaches (
    layout_id   VARCHAR(20) NOT NULL,
    coach       VARCHAR(10) NOT NULL,
    fare_class  VARCHAR(20) NOT NULL,   -- 'first' | 'second'
    PRIMARY KEY (layout_id, coach),
    FOREIGN KEY (layout_id) REFERENCES national_rail_seat_layouts(layout_id) ON DELETE CASCADE
);
 
-- ============================================================
-- 11. NATIONAL RAIL SEATS
-- ============================================================
CREATE TABLE national_rail_seats (
    seat_id     VARCHAR(20) NOT NULL,
    layout_id   VARCHAR(20) NOT NULL,
    coach       VARCHAR(10) NOT NULL,
    seat_row    INTEGER NOT NULL,
    seat_column CHAR(1) NOT NULL,
    PRIMARY KEY (layout_id, coach, seat_id),
    FOREIGN KEY (layout_id, coach) REFERENCES national_rail_coaches(layout_id, coach) ON DELETE CASCADE,
    CHECK (seat_row > 0 AND seat_column ~ '^[A-Z]$')
);
 
-- ============================================================
-- 12. TICKET TYPES
-- ============================================================
CREATE TABLE ticket_types (
    ticket_type  VARCHAR(20) PRIMARY KEY,
    display_name VARCHAR(50) NOT NULL,
    available_on TEXT[] NOT NULL,
    description  TEXT
);
 
-- ============================================================
-- 13. TICKET TYPE RULES
-- ============================================================
CREATE TABLE ticket_type_rules (
    ticket_type               VARCHAR(20) NOT NULL,
    network                   VARCHAR(20) NOT NULL,
    pricing_model             VARCHAR(20) NOT NULL,
    formula                   TEXT NOT NULL,
    fare_classes              TEXT[],
    seat_assignment           BOOLEAN NOT NULL DEFAULT FALSE,
    validity                  TEXT,
    advance_purchase          BOOLEAN NOT NULL DEFAULT FALSE,
    advance_purchase_max_days INTEGER,
    changes_allowed           BOOLEAN NOT NULL DEFAULT FALSE,
    change_fee_usd            DECIMAL(10,2),
    change_deadline           TEXT,
    refundable                BOOLEAN NOT NULL DEFAULT FALSE,
    refund_rules              TEXT,
    PRIMARY KEY (ticket_type, network),
    FOREIGN KEY (ticket_type) REFERENCES ticket_types(ticket_type) ON DELETE CASCADE,
    CHECK (network IN ('metro', 'national_rail')),
    CHECK (advance_purchase = FALSE OR advance_purchase_max_days IS NULL OR advance_purchase_max_days > 0),
    CHECK (changes_allowed = FALSE OR change_fee_usd IS NULL OR change_fee_usd >= 0)
);
 
-- ============================================================
-- 14. BOOKINGS  (national rail only)
-- amount_usd stores the fare at booking time.
-- ============================================================
CREATE TABLE bookings (
    booking_id    VARCHAR(20) PRIMARY KEY,
    user_id       VARCHAR(20) NOT NULL,
    schedule_id   VARCHAR(20) NOT NULL,
    ticket_type   VARCHAR(20) NOT NULL,
    layout_id     VARCHAR(20) NOT NULL,
    coach         VARCHAR(10) NOT NULL,
    seat_id       VARCHAR(20) NOT NULL,
    fare_class    VARCHAR(20) NOT NULL,
    amount_usd    DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    booking_date  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    travel_date   DATE NOT NULL,
    status        VARCHAR(20) NOT NULL,
    FOREIGN KEY (user_id)     REFERENCES registered_users(user_id)          ON DELETE CASCADE,
    FOREIGN KEY (schedule_id) REFERENCES national_rail_schedules(schedule_id) ON DELETE CASCADE,
    FOREIGN KEY (ticket_type) REFERENCES ticket_types(ticket_type)           ON DELETE CASCADE,
    FOREIGN KEY (layout_id, coach, seat_id)
        REFERENCES national_rail_seats(layout_id, coach, seat_id)            ON DELETE CASCADE,
    CHECK (amount_usd >= 0),
    CHECK (status IN ('confirmed', 'cancelled', 'completed'))
);
 
-- ============================================================
-- 15. PAYMENTS
-- Linked to exactly one of: bookings (national rail) or metro_travel_history.
-- ============================================================
CREATE TABLE payments (
    payment_id     VARCHAR(20) PRIMARY KEY,
    user_id        VARCHAR(20) NOT NULL,
    booking_id     VARCHAR(20),
    trip_id        VARCHAR(20),
    amount_usd     DECIMAL(10,2) NOT NULL,
    payment_method VARCHAR(50) NOT NULL,
    payment_date   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    payment_status VARCHAR(20) NOT NULL,
    FOREIGN KEY (user_id)    REFERENCES registered_users(user_id)        ON DELETE CASCADE,
    FOREIGN KEY (booking_id) REFERENCES bookings(booking_id)             ON DELETE CASCADE,
    FOREIGN KEY (trip_id)    REFERENCES metro_travel_history(trip_id)    ON DELETE CASCADE,
    CHECK ((booking_id IS NOT NULL AND trip_id IS NULL) OR (booking_id IS NULL AND trip_id IS NOT NULL)),
    CHECK (amount_usd >= 0),
    CHECK (payment_status IN ('paid', 'refunded', 'pending', 'failed'))
);
 
-- ============================================================
-- 16. FEEDBACK  (national rail bookings only)
-- ============================================================
CREATE TABLE feedback (
    feedback_id   VARCHAR(20) PRIMARY KEY,
    user_id       VARCHAR(20) NOT NULL,
    booking_id    VARCHAR(20) NOT NULL,
    rating        INTEGER CHECK (rating >= 1 AND rating <= 5),
    comments      TEXT,
    feedback_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (user_id)    REFERENCES registered_users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (booking_id) REFERENCES bookings(booking_id)      ON DELETE CASCADE
);
 
-- ============================================================
-- 17. REFUND POLICY
-- ============================================================
CREATE TABLE refund_policy (
    refund_policy_id VARCHAR(20) PRIMARY KEY,
    label            VARCHAR(50) NOT NULL,
    network          VARCHAR(20) NOT NULL,
    service_type     VARCHAR(20) NOT NULL,
    ticket_type      VARCHAR(20) NOT NULL,
    version          VARCHAR(10) NOT NULL,
    FOREIGN KEY (ticket_type) REFERENCES ticket_types(ticket_type),
    CHECK (network IN ('metro', 'national_rail', 'all')),
    CHECK (service_type IN ('express', 'local', 'normal', 'all'))
);
 
-- ============================================================
-- 18. REFUND POLICY WINDOWS
-- ============================================================
CREATE TABLE refund_policy_windows (
    window_id                  VARCHAR(30) PRIMARY KEY,
    refund_policy_id           VARCHAR(20) NOT NULL,
    label                      VARCHAR(50) NOT NULL,
    hours_before_departure_min INTEGER,
    hours_before_departure_max INTEGER,
    refund_percentage          DECIMAL(5,2) NOT NULL,
    admin_fee_usd              DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    FOREIGN KEY (refund_policy_id) REFERENCES refund_policy(refund_policy_id) ON DELETE CASCADE,
    CHECK (hours_before_departure_min IS NULL OR hours_before_departure_min >= 0),
    CHECK (hours_before_departure_max IS NULL OR hours_before_departure_max >= 0),
    CHECK (refund_percentage BETWEEN 0 AND 100),
    CHECK (admin_fee_usd >= 0)
);
 
-- ============================================================
-- 19. BOOKING RULES
-- ============================================================
CREATE TABLE booking_rules (
    booking_rules_id VARCHAR(20) PRIMARY KEY,
    version          VARCHAR(10) NOT NULL,
    network          VARCHAR(20) NOT NULL,
    last_updated     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    rule_category    VARCHAR(50) NOT NULL,
    rule_title       VARCHAR(100) NOT NULL,
    rule_details     TEXT NOT NULL,
    extra_details    JSONB,
    CHECK (network IN ('metro', 'national_rail'))
);
 
-- ============================================================
-- 20. TRAVEL POLICIES
-- ============================================================
CREATE TABLE travel_policies (
    travel_policy_id VARCHAR(20) PRIMARY KEY,
    version          VARCHAR(10) NOT NULL,
    last_updated     DATE,
    network          VARCHAR(20) NOT NULL,
    policy_category  VARCHAR(50) NOT NULL,
    policy_title     VARCHAR(100) NOT NULL,
    policy_details   TEXT NOT NULL,
    extra_details    JSONB,
    CHECK (network IN ('metro', 'national_rail', 'all'))
);
 
-- ============================================================
-- VECTOR SCHEMA (RAG / Help Desk) — do not modify
-- ============================================================
CREATE EXTENSION IF NOT EXISTS vector;
 
CREATE TABLE IF NOT EXISTS policy_documents (
    id          SERIAL PRIMARY KEY,
    title       VARCHAR(200) NOT NULL,
    category    VARCHAR(50)  NOT NULL,
    content     TEXT NOT NULL,
    embedding   vector(768),
    source_file VARCHAR(200),
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
 
CREATE INDEX IF NOT EXISTS idx_policy_documents_embedding
    ON policy_documents USING hnsw (embedding vector_cosine_ops);
```
 

## Agreed Graph Schema

### Node Labels

| Label | Station ID range | Description |
|---|---|---|
| `MetroStation` | MS01 – MS20 | Urban metro network stations |
| `NationalRailStation` | NR01 – NR10 | National rail network stations |

**`MetroStation` properties:**
| Property | Type | Example |
|---|---|---|
| `station_id` | `string` | `"MS01"` |
| `name` | `string` | `"Central Square"` |
| `lines` | `string[]` | `["M1", "M2"]` |
| `is_interchange_metro` | `boolean` | `true` |
| `is_interchange_national_rail` | `boolean` | `true` |

**`NationalRailStation` properties:**
| Property | Type | Example |
|---|---|---|
| `station_id` | `string` | `"NR01"` |
| `name` | `string` | `"Central Station"` |
| `lines` | `string[]` | `["NR1", "NR2"]` |
| `is_interchange_metro` | `boolean` | `true` |
| `is_interchange_national_rail` | `boolean` | `true` |

### Relationship Types

| Type | From → To | Direction | Description |
|---|---|---|---|
| `METRO_LINK` | `MetroStation` → `MetroStation` | Both directions seeded | Adjacent metro stations on a shared line |
| `RAIL_LINK` | `NationalRailStation` → `NationalRailStation` | Both directions seeded | Adjacent national rail stations on a shared line |
| `INTERCHANGE_TO` | `MetroStation` ↔ `NationalRailStation` | Both directions seeded | Physical walk between co-located metro and rail stations |

**`METRO_LINK` properties:**
| Property | Type | Example |
|---|---|---|
| `line` | `string` | `"M1"` |
| `travel_time_min` | `integer` | `3` |

**`RAIL_LINK` properties:**
| Property | Type | Example |
|---|---|---|
| `line` | `string` | `"NR1"` |
| `travel_time_min` | `integer` | `12` |

**`INTERCHANGE_TO` properties:**
| Property | Type | Default |
|---|---|---|
| `walk_time_min` | `integer` | `5` |
| `accessible` | `boolean` | `true` |

### Line IDs

- Metro lines: `M1`, `M2`, `M3`, `M4`
- National rail lines: `NR1`, `NR2`

### Key Design Decisions

1. **Bidirectional relationships:** `METRO_LINK` and `RAIL_LINK` are directed (`a→b`) but both directions are seeded for every pair, so `shortestPath` and undirected traversals work correctly.
2. **Interchange pairs:** `INTERCHANGE_TO` is seeded explicitly in both directions (MS→NR and NR→MS) with a fixed 5-minute walk time.
3. **Network separation:** Metro and national rail nodes use distinct labels so queries can filter by network (`METRO_LINK` only vs `RAIL_LINK` only vs all).
4. **`hops` in variable-length paths:** Cypher does not accept query parameters inside path-length bounds (`*1..N`). The `hops` value in `query_delay_ripple` is embedded directly via Python f-string interpolation — not passed as `$hops`.

```cypher
// Example: all stations on M1
MATCH (a:MetroStation)-[:METRO_LINK {line: "M1"}]->(b:MetroStation)
RETURN a.station_id, a.name, b.station_id, b.name

// Example: cross-network interchange
MATCH (m:MetroStation {station_id: "MS01"})-[:INTERCHANGE_TO]->(r:NationalRailStation)
RETURN m.name, r.name, r.station_id
```

## Function Signatures We Are Implementing

These are fixed contracts. AI-generated code must match these signatures exactly.

### Relational (`databases/relational/queries.py`)

```python
# Read-only
def query_national_rail_availability(origin_id: str, destination_id: str, travel_date: Optional[str] = None) -> list[dict]: ...
def query_national_rail_fare(schedule_id: str, fare_class: str, stops_travelled: int) -> Optional[dict]: ...
def query_metro_schedules(origin_id: str, destination_id: str) -> list[dict]: ...
def query_metro_fare(schedule_id: str, stops_travelled: int) -> Optional[dict]: ...
def query_available_seats(schedule_id: str, travel_date: str, fare_class: str) -> list[dict]: ...
def query_user_profile(user_email: str) -> Optional[dict]: ...
def query_user_bookings(user_email: str) -> dict: ...  # returns {"national_rail": [...], "metro": [...]}
def query_payment_info(booking_id: str) -> Optional[dict]: ...

# Write operations
def execute_booking(user_id, schedule_id, origin_station_id, destination_station_id, travel_date, fare_class, seat_id, ticket_type="single") -> tuple[bool, dict | str]: ...
def execute_cancellation(booking_id: str, user_id: str) -> tuple[bool, dict | str]: ...

# Auth
def register_user(email, first_name, surname, year_of_birth, password, secret_question, secret_answer) -> tuple[bool, str]: ...
def login_user(email: str, password: str) -> Optional[dict]: ...
def get_user_secret_question(email: str) -> Optional[str]: ...
def verify_secret_answer(email: str, answer: str) -> bool: ...
def update_password(email: str, new_password: str) -> bool: ...
```

### Graph (`databases/graph/queries.py`)

```python
def query_shortest_route(origin_id: str, destination_id: str, network: str = "auto") -> dict: ...
def query_cheapest_route(origin_id: str, destination_id: str, network: str = "auto", fare_class: str = "standard") -> dict: ...
def query_alternative_routes(origin_id, destination_id, avoid_station_id, network="auto", max_routes=3) -> list[list[dict]]: ...
def query_interchange_path(origin_id: str, destination_id: str) -> dict: ...
def query_delay_ripple(delayed_station_id: str, hops: int = 2) -> list[dict]: ...
def query_station_connections(station_id: str) -> list[dict]: ...
```

## Team Decisions Log

<!-- Add entries as you make decisions. Format: "Decision: X. Why: Y." -->

### Relational Schema
- [x] **Separate table families for metro and rail.** Metro and national rail are modelled as completely separate table families (stations, schedules, stop lists, travel records). Why: the two networks have different properties (e.g. rail has seat coaches and fare classes; metro does not), so a single unified table would need many nullable columns.
- [x] **Stop ordering as a join table, not an array.** `metro_schedule_stops` and `national_rail_schedule_stops` store a `stop_order` integer rather than a JSON/array column. Why: enables SQL `ORDER BY stop_order` and `WHERE stop_order BETWEEN` without needing `jsonb_array_elements`, which makes availability queries and stop-count calculations straightforward.
- [x] **Three-level seat layout normalisation.** National rail seat layout is split into `national_rail_seat_layouts` → `national_rail_coaches` → `national_rail_seats`. Why: matches the nested JSON source data structure and allows querying available seats by coach and fare class independently.
- [x] **Payments use a mutual-exclusion CHECK.** `payments` carries both `booking_id` and `trip_id` FKs, with a `CHECK` that exactly one is non-null. Why: a single payments table covers both national rail bookings and metro tap-in/tap-out trips, avoiding two separate payment tables with identical columns.
- [x] **Mutual interchange FK declared DEFERRABLE.** The cross-reference FKs between `metro_stations` and `national_rail_stations` are added via `ALTER TABLE … DEFERRABLE INITIALLY DEFERRED`. Why: the two tables reference each other, so normal FK constraints would reject inserts before both rows exist; deferring validation to commit time allows seed data to load in any order.
- [x] **`bookings.amount_usd` is a snapshot.** The fare is stored at booking time, not derived from current pricing tables. Why: pricing rules may change after booking; preserving the original amount_usd ensures historical records and refund calculations remain correct.

### Graph Schema
- [x] **Separate node labels for each network.** `MetroStation` and `NationalRailStation` are distinct labels rather than a generic `Station` label. Why: allows Cypher to filter by network using label syntax (`MATCH (n:MetroStation)`) without an extra `network` property, and keeps relationship types (`METRO_LINK` vs `RAIL_LINK`) cleanly scoped to each network.
- [x] **`travel_time_min` as edge weight on links.** `METRO_LINK` and `RAIL_LINK` both carry a `travel_time_min` integer property. Why: `shortestPath` in Cypher finds the minimum-hop path; total journey time is computed afterwards by summing `travel_time_min` across relationships with `reduce()`. This separates hop-count routing from time calculation.
- [x] **Both directions seeded for every link.** Each `METRO_LINK` and `RAIL_LINK` pair is seeded in both directions (a→b and b→a) by iterating each station's `adjacent_stations` list. Why: `shortestPath` and undirected `MATCH` patterns work correctly; no need for undirected relationship type workarounds.
- [x] **`INTERCHANGE_TO` seeded bidirectionally with fixed walk time.** Both MS→NR and NR→MS directions are created with `walk_time_min = 5` and `accessible = true`. Why: cross-network route queries need to traverse in either direction depending on journey origin; a fixed 5-minute walk is a reasonable uniform default for all interchange points.
- [x] **`hops` interpolated into Cypher, not passed as a parameter.** In `query_delay_ripple`, the hop count is embedded directly into the query string via f-string. Why: Cypher does not support query parameters inside variable-length path bounds (`*1..$hops`); passing `hops` as a parameter causes a runtime `SyntaxError`.

### Architecture
- [x] **Agent tool routing is LLM-driven.** `skeleton/agent.py` uses the LLM to decide which database tool to call based on the user's question. Why: no hard-coded keyword matching needed for the main path; the LLM reads the user message and selects the right tool (graph, relational, or vector) automatically.
- [x] **Vector search is pre-implemented and read-only.** `query_policy_vector_search` and `store_policy_document` in `databases/relational/queries.py` are already implemented. Students should not modify them; extend coverage by adding content to the JSON files in `train-mock-data/` and re-running `skeleton/seed_vectors.py`.

### Testing
- [x] **Graph query logic is covered by offline unit tests.** `test_graph_queries.py` uses `unittest.mock` to intercept the Neo4j driver, enabling schema consistency checks and edge-case validation (e.g. route-not-found handling) without a live database connection. All tests pass 100%.

---

## Prompts That Worked

### Schema design prompt
```
We are designing a PostgreSQL schema for a transit system with two networks:
City Metro (MS01–MS20, lines M1–M4) and National Rail (NR01–NR10, lines NR1–NR2).

Requirements:
- Query schedules between two stations in stop order
- Calculate fares (base fare + per-stop rate, with fare classes for rail)
- Book and cancel national rail seats (coach + seat_id)
- Track metro tap-in/tap-out travel history
- Store payments for both booking types in one table
- Some metro stations physically connect to rail stations (interchange)

The source data is in these JSON files: metro_stations.json, national_rail_stations.json,
metro_schedules.json, national_rail_schedules.json, national_rail_seat_layouts.json,
bookings.json, metro_travel_history.json, payments.json.

Design a normalised schema. Separate metro and rail into distinct table families.
Normalise stop ordering into a join table (not a JSON array). Output CREATE TABLE
statements with appropriate PRIMARY KEY, FOREIGN KEY, and CHECK constraints.
```

### Graph query implementation prompt
```
Implement a Neo4j Cypher query function in Python using the neo4j driver.

Graph schema:
- Nodes: MetroStation {station_id, name, lines[]}, NationalRailStation {station_id, name, lines[]}
- Relationships: METRO_LINK {line, travel_time_min}, RAIL_LINK {line, travel_time_min},
  INTERCHANGE_TO {walk_time_min, accessible} — all seeded bidirectionally

Connection pattern (always use this):
    with _driver() as driver:
        with driver.session() as session:
            result = session.run("MATCH ...", param=value)
            return [dict(record) for record in result]

Task: [describe the specific function here — e.g. "find the shortest route between
two stations, returning station_id, name, label for each stop and total travel time"]

Return [] or {"found": False} for not-found cases, never raise an exception.
```

### Relational query implementation prompt
```
Implement a PostgreSQL query function in Python using psycopg2.

Always use this connection pattern:
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT ...", (param,))
            return [dict(row) for row in cur.fetchall()]

Use %s placeholders for all parameters — never f-string or format() into SQL.

Schema: [paste the relevant CREATE TABLE statements from AI_SESSION_CONTEXT.md]

Task: [describe the specific function — e.g. "return all schedules that serve both
origin_id and destination_id in the correct stop order, including stop count"]

Return [] or None for not-found cases, never raise an exception.
```
