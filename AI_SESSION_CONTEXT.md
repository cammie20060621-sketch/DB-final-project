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

<!-- ============================================================
  FILL THIS IN after your team agrees on Neo4j node labels and
  relationship types.
  ============================================================ -->

```
Node labels:
- TODO

Relationship types:
- TODO

Key properties:
- TODO
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

- [ ] Schema design: TODO — add your table/column decisions here
- [ ] Graph schema: TODO — add your node label and relationship type decisions here
- [ ] (example) Metro schedule stop ordering: using `jsonb_array_elements` approach — easier to debug than containment operators

## Prompts That Worked

<!-- Share prompts that produced good output so teammates can reuse them. -->

### Schema design prompt that worked:
```
TODO — add a prompt here after your schema design workshop
```

### Query implementation prompt that worked:
```
TODO — add after implementing your first function
```
