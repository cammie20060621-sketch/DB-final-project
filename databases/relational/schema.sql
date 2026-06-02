
-- ============================================================
--  TransitFlow PostgreSQL Schema
--  Seed data is loaded separately by: python skeleton/seed_postgres.py
--
--  TWO ROLES:
--    1. Relational  → dual-network transit data you design below
--    2. Vector      → policy documents for RAG (provided — do not modify)
-- ============================================================
 
-- ============================================================
--  STUDENT TASK — Design and create your relational tables here
--
--  Start from the mock data in train-mock-data/:
--    metro_stations.json, national_rail_stations.json
--    metro_schedules.json, national_rail_schedules.json
--    national_rail_seat_layouts.json
--    registered_users.json
--    bookings.json, metro_travel_history.json
--    payments.json, feedback.json
--
--  Think about:
--    - What tables do you need?
--    - What columns and data types?
--    - Which fields are primary keys? Which are foreign keys?
--    - What constraints make sense?
--
--  Apply your schema with:
--    docker-compose down -v && docker-compose up -d
-- ============================================================
 
-- ============================================================
--Design choices:
--  1. Metro and national rail are modeled as separate tables.
--  2. Stops are normalized into separate tables (metro_schedule_stops and national_rail_schedule_stops) to maintain data integrity and avoid redundancy.
--  3. National rail seat layouts are normalized into:
--         national_rail_seat_layouts
--         national_rail_coaches
--         national_rail_seats
-- 4. Payments and feedback can belong to either:
--         a national rail booking
--         or a metro travel history record.
-- 5. metro_stations and national_rail_stations have a DEFERRABLE FK cycle
--    to allow both tables to be populated before the cross-reference is enforced.
-- ============================================================
 
DROP TABLE IF EXISTS feedback CASCADE;
DROP TABLE IF EXISTS payments CASCADE;
DROP TABLE IF EXISTS bookings CASCADE;
DROP TABLE IF EXISTS metro_travel_history CASCADE;
DROP TABLE IF EXISTS metro_schedule_stops CASCADE;
DROP TABLE IF EXISTS metro_schedules CASCADE;
DROP TABLE IF EXISTS national_rail_seats CASCADE;
DROP TABLE IF EXISTS national_rail_coaches CASCADE;
DROP TABLE IF EXISTS national_rail_seat_layouts CASCADE;
DROP TABLE IF EXISTS national_rail_schedule_stops CASCADE;
DROP TABLE IF EXISTS national_rail_schedules CASCADE;
DROP TABLE IF EXISTS national_rail_stations CASCADE;
DROP TABLE IF EXISTS metro_stations CASCADE;
DROP TABLE IF EXISTS registered_users CASCADE;
DROP TABLE IF EXISTS refund_policy_windows CASCADE;
DROP TABLE IF EXISTS refund_policy CASCADE;
DROP TABLE IF EXISTS booking_rules CASCADE;
DROP TABLE IF EXISTS travel_policies CASCADE;
DROP TABLE IF EXISTS ticket_type_rules CASCADE;
DROP TABLE IF EXISTS ticket_types CASCADE;
 
-- ============================================================
-- 1. REGISTERED USERS
--  source file: registered_users.json
--  Purpose: Store user information for both metro and national rail passengers.
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
 
 
-- =============================================================
-- 2. METRO STATIONS
--
-- FIX #1: Added semicolon at end of CREATE TABLE statement.
-- FIX #6: interchange_rail_station_id FK to national_rail_stations cannot be
--         declared inline here because national_rail_stations does not exist yet.
--         The FK is added below via ALTER TABLE after both tables are created,
--         using DEFERRABLE INITIALLY DEFERRED to handle the mutual reference.
-- =============================================================
CREATE TABLE metro_stations (
    station_id                   VARCHAR(10) PRIMARY KEY,
    name                         TEXT NOT NULL,
    is_interchange_metro         BOOLEAN NOT NULL,
    is_interchange_national_rail BOOLEAN NOT NULL,
    interchange_rail_station_id  VARCHAR(10)   -- FK added via ALTER TABLE below
);
 
-- =============================================================
-- 3. METRO SCHEDULES
-- =============================================================
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
 
-- ==============================================================
-- 4. METRO SCHEDULE STOPS
--  This table stores the order of stops for each metro_schedule.
--  Example:
--  schedule_id | station_id | stop_order
--    MSCH01     |  MS01     |    1
--    MSCH01     |  MS02     |    2
--    MSCH01     |  MS03     |    3
-- ==============================================================
 
CREATE TABLE metro_schedule_stops (
    schedule_id     VARCHAR(20) NOT NULL,
    station_id      VARCHAR(10) NOT NULL,
    stop_order      INTEGER NOT NULL,
 
    PRIMARY KEY (schedule_id, stop_order),
    UNIQUE (schedule_id, station_id),
 
    FOREIGN KEY (schedule_id) REFERENCES metro_schedules(schedule_id) ON DELETE CASCADE,
    FOREIGN KEY (station_id)  REFERENCES metro_stations(station_id)   ON DELETE CASCADE,
 
    CHECK (stop_order > 0)
);
 
-- ==============================================================
-- 5. METRO TRAVEL HISTORY
--  Source file: metro_travel_history.json
--
--  Metro does not have seat reservations;
--  we only store the tap-in and tap-out for each trip.
--
-- FIX #8: Added CHECK to ensure completed trips always have
--         tap_out_time and exit_station_id recorded.
-- ==============================================================
 
CREATE TABLE metro_travel_history (
    trip_id             VARCHAR(20) PRIMARY KEY,
    user_id             VARCHAR(20) NOT NULL,
    schedule_id         VARCHAR(20),
    entry_station_id    VARCHAR(10) NOT NULL,
    exit_station_id     VARCHAR(10),
    ticket_type         VARCHAR(20) NOT NULL,   -- 'single', 'day_pass', etc.
    travel_date         DATE NOT NULL,
    tap_in_time         TIMESTAMPTZ NOT NULL,
    tap_out_time        TIMESTAMPTZ,
    amount_usd          DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    status              VARCHAR(20) NOT NULL,   -- 'completed', 'in_progress', 'cancelled'
 
    FOREIGN KEY (user_id)           REFERENCES registered_users(user_id)      ON DELETE CASCADE,
    FOREIGN KEY (schedule_id)       REFERENCES metro_schedules(schedule_id)    ON DELETE CASCADE,
    FOREIGN KEY (entry_station_id)  REFERENCES metro_stations(station_id)      ON DELETE CASCADE,
    FOREIGN KEY (exit_station_id)   REFERENCES metro_stations(station_id)      ON DELETE CASCADE,
 
    CHECK (tap_out_time IS NULL OR tap_out_time > tap_in_time),
    CHECK (amount_usd >= 0),
    CHECK (status IN ('completed', 'in_progress', 'cancelled')),
    -- FIX #8: completed trips must have tap_out_time and exit_station_id
    CHECK (
        status != 'completed'
        OR (tap_out_time IS NOT NULL AND exit_station_id IS NOT NULL)
    )
);
 
-- ==============================================================
-- 6. NATIONAL RAIL STATIONS
-- ==============================================================
 
CREATE TABLE national_rail_stations (
    station_id                              VARCHAR(10) PRIMARY KEY,
    name                                    TEXT NOT NULL,
    city                                    VARCHAR(50),
    is_interchange_metro                    BOOLEAN NOT NULL,
    is_interchange_national_rail            BOOLEAN NOT NULL,
    interchange_national_rail_station_lines TEXT[],       -- e.g. ['NR Line 1', 'NR Line 2']
    interchange_metro_station_id            VARCHAR(10),  -- FK added via ALTER TABLE below
 
    CONSTRAINT chk_national_rail_interchange_lines
    CHECK (
        (
            is_interchange_national_rail = TRUE
            AND interchange_national_rail_station_lines IS NOT NULL
            AND array_length(interchange_national_rail_station_lines, 1) > 0
        )
        OR
        (
            is_interchange_national_rail = FALSE
            AND (
                interchange_national_rail_station_lines IS NULL
                OR array_length(interchange_national_rail_station_lines, 1) = 0
            )
        )
    )
);
 
-- FIX #6: Add cross-reference FKs after both station tables exist.
--         DEFERRABLE INITIALLY DEFERRED lets the seed script insert both sides
--         before the constraint is enforced at transaction commit.
ALTER TABLE metro_stations
    ADD CONSTRAINT fk_metro_interchange_rail
    FOREIGN KEY (interchange_rail_station_id)
    REFERENCES national_rail_stations(station_id)
    ON DELETE SET NULL
    DEFERRABLE INITIALLY DEFERRED;
 
ALTER TABLE national_rail_stations
    ADD CONSTRAINT fk_national_rail_interchange_metro
    FOREIGN KEY (interchange_metro_station_id)
    REFERENCES metro_stations(station_id)
    ON DELETE SET NULL
    DEFERRABLE INITIALLY DEFERRED;
 
-- ==============================================================
-- 7. NATIONAL RAIL SCHEDULES
-- ==============================================================
 
CREATE TABLE national_rail_schedules (
    schedule_id         VARCHAR(20) PRIMARY KEY,
    line                VARCHAR(20) NOT NULL,
    service_type        VARCHAR(50) NOT NULL,   -- 'express', 'local'
    direction           VARCHAR(50) NOT NULL,
    departure_time      TIME NOT NULL,
    arrival_time        TIME NOT NULL,
    base_fare_usd       DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    per_stop_fare_usd   DECIMAL(10,2) NOT NULL DEFAULT 0.00,
 
    CHECK (base_fare_usd >= 0 AND per_stop_fare_usd >= 0)
);
 
 
-- ==============================================================
-- 8. NATIONAL RAIL SCHEDULE STOPS
--  Similar to metro_schedule_stops but for national rail.
--
-- FIX #7: Aligned PK direction with metro_schedule_stops:
--         PRIMARY KEY (schedule_id, stop_order) + UNIQUE (schedule_id, station_id).
-- ==============================================================
 
CREATE TABLE national_rail_schedule_stops (
    schedule_id     VARCHAR(20) NOT NULL,
    station_id      VARCHAR(10) NOT NULL,
    stop_order      INTEGER NOT NULL,
 
    PRIMARY KEY (schedule_id, stop_order),   -- FIX #7: was (schedule_id, station_id)
    UNIQUE (schedule_id, station_id),
 
    FOREIGN KEY (schedule_id) REFERENCES national_rail_schedules(schedule_id) ON DELETE CASCADE,
    FOREIGN KEY (station_id)  REFERENCES national_rail_stations(station_id)   ON DELETE CASCADE,
 
    CHECK (stop_order > 0)
);
 
-- ==============================================================
-- 9. NATIONAL RAIL SEAT LAYOUTS
--  Source file: national_rail_seat_layouts.json
--
--  Stores the top-level seat layout for a national rail schedule.
--
--  JSON structure:  layout → coaches → seats
--
-- FIX #2: Removed the invalid CHECK that referenced non-existent columns
--         (seat_row, seat_column). Those checks belong in national_rail_seats.
-- ==============================================================
 
CREATE TABLE national_rail_seat_layouts (
    schedule_id     VARCHAR(20) NOT NULL,
    layout_id       VARCHAR(20) PRIMARY KEY,
 
    FOREIGN KEY (schedule_id)
        REFERENCES national_rail_schedules(schedule_id)
        ON DELETE CASCADE
);
 
-- ==============================================================
-- 10. NATIONAL RAIL COACHES
--  Source file: national_rail_seat_layouts.json
--
--  Stores coaches inside each seat layout.
--  Example: layout_id = SL01 | coach = A | fare_class = first
-- ==============================================================
 
CREATE TABLE national_rail_coaches (
    layout_id       VARCHAR(20) NOT NULL,
    coach           VARCHAR(10) NOT NULL,
    fare_class      VARCHAR(20) NOT NULL,   -- 'first', 'second'
 
    PRIMARY KEY (layout_id, coach),
 
    FOREIGN KEY (layout_id)
        REFERENCES national_rail_seat_layouts(layout_id)
        ON DELETE CASCADE
);
 
-- ==============================================================
-- 11. NATIONAL RAIL SEATS
--  Source file: national_rail_seat_layouts.json
--
--  Stores individual seats inside each coach.
--  Example: layout_id = SL01 | coach = A | seat_id = A01
--
-- FIX #3: Added missing comma before CHECK constraint.
-- ==============================================================
 
CREATE TABLE national_rail_seats (
    seat_id        VARCHAR(20) NOT NULL,
    layout_id      VARCHAR(20) NOT NULL,
    coach          VARCHAR(10) NOT NULL,
    seat_row       INTEGER NOT NULL,
    seat_column    CHAR(1) NOT NULL,
 
    PRIMARY KEY (layout_id, coach, seat_id),
 
    FOREIGN KEY (layout_id, coach)
        REFERENCES national_rail_coaches(layout_id, coach)
        ON DELETE CASCADE,   -- FIX #3: was missing comma here
 
    CHECK (seat_row > 0 AND seat_column ~ '^[A-Z]$')
);
 
-- ==============================================================
-- 12. TICKET TYPES
--  Source file: ticket_types.json
--  Purpose: Stores ticket type definitions and rules.
-- ==============================================================
 
CREATE TABLE ticket_types (
    ticket_type     VARCHAR(20) PRIMARY KEY,  -- 'single', 'return', 'day_pass', 'weekly_pass', etc.
    display_name    VARCHAR(50) NOT NULL,
    available_on    TEXT[] NOT NULL,          -- 'metro', 'national_rail', 'both'
    description     TEXT
);
 
-- ==============================================================
-- 13. TICKET TYPE NETWORK RULES
-- ==============================================================
 
CREATE TABLE ticket_type_rules (
    ticket_type             VARCHAR(20) NOT NULL,
    network                 VARCHAR(20) NOT NULL,  -- 'metro' or 'national_rail'
    pricing_model           VARCHAR(20) NOT NULL,  -- 'flat_rate', 'stops_based', etc.
    formula                 TEXT NOT NULL,
    fare_classes            TEXT[],                -- e.g. ['first', 'standard']
    seat_assignment         BOOLEAN NOT NULL DEFAULT FALSE,
    validity                TEXT,
    advance_purchase        BOOLEAN NOT NULL DEFAULT FALSE,
    advance_purchase_max_days INTEGER,
    changes_allowed         BOOLEAN NOT NULL DEFAULT FALSE,
    change_fee_usd          DECIMAL(10,2),
    change_deadline         TEXT,
    refundable              BOOLEAN NOT NULL DEFAULT FALSE,
    refund_rules            TEXT,
 
    PRIMARY KEY (ticket_type, network),
 
    FOREIGN KEY (ticket_type)
        REFERENCES ticket_types(ticket_type)
        ON DELETE CASCADE,
 
    CHECK (network IN ('metro', 'national_rail')),
    CHECK (
        advance_purchase = FALSE
        OR advance_purchase_max_days IS NULL
        OR advance_purchase_max_days > 0
    ),
    CHECK (
        changes_allowed = FALSE
        OR change_fee_usd IS NULL
        OR change_fee_usd >= 0
    )
);
 
-- ============================================================
-- 14. BOOKINGS
--  Source file: bookings.json
--  Purpose: Stores national rail advance bookings.
--
-- FIX #4: Added missing comma before CHECK constraint.
-- FIX #9: Added amount_usd to store the fare at time of booking.
-- ============================================================
 
CREATE TABLE bookings (
    booking_id      VARCHAR(20) PRIMARY KEY,
    user_id         VARCHAR(20) NOT NULL,
    schedule_id     VARCHAR(20) NOT NULL,
    ticket_type     VARCHAR(20) NOT NULL,
    layout_id       VARCHAR(20) NOT NULL,
    coach           VARCHAR(10) NOT NULL,
    seat_id         VARCHAR(20) NOT NULL,
    fare_class      VARCHAR(20) NOT NULL,   -- 'first', 'second'
    amount_usd      DECIMAL(10,2) NOT NULL DEFAULT 0.00,  -- FIX #9: fare at booking time
    booking_date    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    travel_date     DATE NOT NULL,
    status          VARCHAR(20) NOT NULL,   -- 'confirmed', 'cancelled', 'completed'
 
    FOREIGN KEY (user_id)
        REFERENCES registered_users(user_id)
        ON DELETE CASCADE,
    FOREIGN KEY (schedule_id)
        REFERENCES national_rail_schedules(schedule_id)
        ON DELETE CASCADE,
    FOREIGN KEY (ticket_type)
        REFERENCES ticket_types(ticket_type)
        ON DELETE CASCADE,
    FOREIGN KEY (layout_id, coach, seat_id)
        REFERENCES national_rail_seats(layout_id, coach, seat_id)
        ON DELETE CASCADE,   -- FIX #4: was missing comma here
 
    CHECK (amount_usd >= 0),
    CHECK (status IN ('confirmed', 'cancelled', 'completed'))
);
 
-- ============================================================
-- 15. PAYMENTS
--  Source file: payments.json
--  Purpose: Stores payment records for both metro and national rail.
--
--  A payment is linked to exactly one of:
--    - a national rail booking  (booking_id)
--    - a metro travel history   (trip_id)
--
-- FIX #11: Added CHECK constraint to enforce valid payment_status values.
-- ============================================================
 
CREATE TABLE payments (
    payment_id      VARCHAR(20) PRIMARY KEY,
    user_id         VARCHAR(20) NOT NULL,
    booking_id      VARCHAR(20),
    trip_id         VARCHAR(20),
    amount_usd      DECIMAL(10,2) NOT NULL,
    payment_method  VARCHAR(50) NOT NULL,   -- 'credit_card', 'ewallet', 'debit_card', etc.
    payment_date    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    payment_status  VARCHAR(20) NOT NULL,   -- 'paid', 'refunded', 'pending', 'failed'
 
    FOREIGN KEY (user_id)
        REFERENCES registered_users(user_id)
        ON DELETE CASCADE,
    FOREIGN KEY (booking_id)
        REFERENCES bookings(booking_id)
        ON DELETE CASCADE,
    FOREIGN KEY (trip_id)
        REFERENCES metro_travel_history(trip_id)
        ON DELETE CASCADE,
 
    CHECK (
        (booking_id IS NOT NULL AND trip_id IS NULL) OR
        (booking_id IS NULL AND trip_id IS NOT NULL)
    ),
    CHECK (amount_usd >= 0),
    CHECK (payment_status IN ('paid', 'refunded', 'pending', 'failed'))  -- FIX #11
);
 
-- ============================================================
-- 16. FEEDBACK
--  Source file: feedback.json
--  Purpose: Stores user feedback for national rail experiences.
--           A feedback record must be linked to a national rail booking.
-- ============================================================
 
CREATE TABLE feedback (
    feedback_id     VARCHAR(20) PRIMARY KEY,
    user_id         VARCHAR(20) NOT NULL,
    booking_id      VARCHAR(20) NOT NULL,
    rating          INTEGER CHECK (rating >= 1 AND rating <= 5),
    comments        TEXT,
    feedback_date   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 
    FOREIGN KEY (user_id)
        REFERENCES registered_users(user_id)
        ON DELETE CASCADE,
    FOREIGN KEY (booking_id)
        REFERENCES bookings(booking_id)
        ON DELETE CASCADE
);
 
-- ============================================================
-- 17. REFUND POLICY
--  Source file: refund_policy.json
--  Purpose: Stores structured refund eligibility rules.
--
-- FIX #10: Added FOREIGN KEY on ticket_type → ticket_types.
--          Added CHECK on service_type to enforce valid values.
-- ============================================================
 
CREATE TABLE refund_policy (
    refund_policy_id  VARCHAR(20) PRIMARY KEY,
    label             VARCHAR(50) NOT NULL,  -- e.g. 'full_refund_before_departure'
    network           VARCHAR(20) NOT NULL,  -- 'metro', 'national_rail', 'all'
    service_type      VARCHAR(20) NOT NULL,  -- 'express', 'local', 'normal', 'all'
    ticket_type       VARCHAR(20) NOT NULL,
    version           VARCHAR(10) NOT NULL,
 
    FOREIGN KEY (ticket_type)
        REFERENCES ticket_types(ticket_type),  -- FIX #10
 
    CHECK (network IN ('metro', 'national_rail', 'all')),
    CHECK (service_type IN ('express', 'local', 'normal', 'all'))  -- FIX #10
);
 
-- ============================================================
-- 18. REFUND POLICY WINDOWS
--  Source file: refund_policy.json
-- ============================================================
 
CREATE TABLE refund_policy_windows (
    window_id                    VARCHAR(30) PRIMARY KEY,
    refund_policy_id             VARCHAR(20) NOT NULL,
    label                        VARCHAR(50) NOT NULL,
    hours_before_departure_min   INTEGER,
    hours_before_departure_max   INTEGER,
    refund_percentage            DECIMAL(5,2) NOT NULL,
    admin_fee_usd                DECIMAL(10,2) NOT NULL DEFAULT 0.00,
 
    FOREIGN KEY (refund_policy_id)
        REFERENCES refund_policy(refund_policy_id)
        ON DELETE CASCADE,
 
    CHECK (hours_before_departure_min IS NULL OR hours_before_departure_min >= 0),
    CHECK (hours_before_departure_max IS NULL OR hours_before_departure_max >= 0),
    CHECK (refund_percentage BETWEEN 0 AND 100),
    CHECK (admin_fee_usd >= 0)
);
 
-- ============================================================
-- 19. BOOKING RULES
--  Source file: booking_rules.json
-- ============================================================
 
CREATE TABLE booking_rules (
    booking_rules_id  VARCHAR(20) PRIMARY KEY,
    version           VARCHAR(10) NOT NULL,
    network           VARCHAR(20) NOT NULL,  -- 'metro' or 'national_rail'
    last_updated      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    rule_category     VARCHAR(50) NOT NULL,
    rule_title        VARCHAR(100) NOT NULL,
    rule_details      TEXT NOT NULL,
    extra_details     JSONB,
 
    CHECK (network IN ('metro', 'national_rail'))
);
 
-- ============================================================
-- 20. TRAVEL POLICIES
--  Source file: travel_policies.json
-- ============================================================
 
CREATE TABLE travel_policies (
    travel_policy_id  VARCHAR(20) PRIMARY KEY,
    version           VARCHAR(10) NOT NULL,
    last_updated      DATE,
    network           VARCHAR(20) NOT NULL,  -- 'metro', 'national_rail', 'all'
    policy_category   VARCHAR(50) NOT NULL,
    policy_title      VARCHAR(100) NOT NULL,
    policy_details    TEXT NOT NULL,
    extra_details     JSONB,
 
    CHECK (network IN ('metro', 'national_rail', 'all'))
);

-- ============================================================
--  VECTOR SCHEMA  (RAG / Help Desk) — do not modify
-- ============================================================

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS policy_documents (
    id          SERIAL       PRIMARY KEY,
    title       VARCHAR(200) NOT NULL,
    category    VARCHAR(50)  NOT NULL,  -- 'refund', 'booking', 'conduct'
    content     TEXT         NOT NULL,
    -- 768-dim  → Ollama nomic-embed-text (default)
    -- 3072-dim → Gemini gemini-embedding-001
    -- If you switch LLM_PROVIDER to gemini, change to vector(3072) and reset the database.
    embedding   vector(768),
    source_file VARCHAR(200),
    created_at  TIMESTAMPTZ  DEFAULT NOW()
);

-- Index for fast cosine similarity search
CREATE INDEX IF NOT EXISTS ON policy_documents USING hnsw (embedding vector_cosine_ops);
