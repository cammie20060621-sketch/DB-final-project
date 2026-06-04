
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

DROP TABLE IF EXISTS refund_policy_windows CASCADE;
DROP TABLE IF EXISTS refund_policy CASCADE;
DROP TABLE IF EXISTS booking_rules CASCADE;
DROP TABLE IF EXISTS travel_policies CASCADE;
DROP TABLE IF EXISTS ticket_type_rules CASCADE;
DROP TABLE IF EXISTS ticket_types CASCADE;

DROP TABLE IF EXISTS registered_users CASCADE;

-- Recreate vector table too, so schema can be fully reset.
DROP TABLE IF EXISTS policy_documents CASCADE;


-- ============================================================
-- 1. REGISTERED USERS
-- Source file: registered_users.json
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
    is_active         BOOLEAN DEFAULT TRUE,

    CHECK (year_of_birth IS NULL OR year_of_birth BETWEEN 1900 AND 2100)
);


-- ============================================================
-- 2. METRO STATIONS
-- Source file: metro_stations.json
-- ============================================================

CREATE TABLE metro_stations (
    station_id                   VARCHAR(10) PRIMARY KEY,
    name                         TEXT NOT NULL,
    zone                         INTEGER,
    is_interchange_metro         BOOLEAN NOT NULL DEFAULT FALSE,
    is_interchange_national_rail BOOLEAN NOT NULL DEFAULT FALSE,
    interchange_rail_station_id  VARCHAR(10),

    CHECK (zone IS NULL OR zone > 0)
);


-- ============================================================
-- 3. NATIONAL RAIL STATIONS
-- Source file: national_rail_stations.json
-- ============================================================

CREATE TABLE national_rail_stations (
    station_id                              VARCHAR(10) PRIMARY KEY,
    name                                    TEXT NOT NULL,
    city                                    VARCHAR(50),
    is_interchange_metro                    BOOLEAN NOT NULL DEFAULT FALSE,
    is_interchange_national_rail            BOOLEAN NOT NULL DEFAULT FALSE,
    interchange_national_rail_station_lines TEXT[],
    interchange_metro_station_id            VARCHAR(10),
);



-- ============================================================
-- 4. CROSS-REFERENCE FOREIGN KEYS
-- Add after both station tables exist.
-- DEFERRABLE allows mutual references during seeding.
-- ============================================================

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


-- ============================================================
-- 5. METRO SCHEDULES
-- Source file: metro_schedules.json
-- ============================================================

CREATE TABLE metro_schedules (
    schedule_id         VARCHAR(20) PRIMARY KEY,
    line                VARCHAR(20) NOT NULL,
    direction           VARCHAR(50) NOT NULL,
    departure_time      TIME NOT NULL,
    arrival_time        TIME NOT NULL,
    frequency_min       INTEGER NOT NULL,
    base_fare_usd       DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    per_stop_fare_usd   DECIMAL(10,2) NOT NULL DEFAULT 0.00,

    CHECK (frequency_min > 0),
    CHECK (base_fare_usd >= 0),
    CHECK (per_stop_fare_usd >= 0)
);


-- ============================================================
-- 6. METRO SCHEDULE STOPS
-- Normalized stop order for each metro schedule.
-- ============================================================

CREATE TABLE metro_schedule_stops (
    schedule_id     VARCHAR(20) NOT NULL,
    station_id      VARCHAR(10) NOT NULL,
    stop_order      INTEGER NOT NULL,

    PRIMARY KEY (schedule_id, stop_order),
    UNIQUE (schedule_id, station_id),

    FOREIGN KEY (schedule_id)
        REFERENCES metro_schedules(schedule_id)
        ON DELETE CASCADE,

    FOREIGN KEY (station_id)
        REFERENCES metro_stations(station_id)
        ON DELETE CASCADE,

    CHECK (stop_order > 0)
);


-- ============================================================
-- 7. NATIONAL RAIL SCHEDULES
-- Source file: national_rail_schedules.json
-- ============================================================

CREATE TABLE national_rail_schedules (
    schedule_id         VARCHAR(20) PRIMARY KEY,
    line                VARCHAR(20) NOT NULL,
    service_type        VARCHAR(50) NOT NULL,
    direction           VARCHAR(50) NOT NULL,
    departure_time      TIME NOT NULL,
    arrival_time        TIME NOT NULL,
    base_fare_usd       DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    per_stop_fare_usd   DECIMAL(10,2) NOT NULL DEFAULT 0.00,

    CHECK (base_fare_usd >= 0),
    CHECK (per_stop_fare_usd >= 0),
    CHECK (service_type IN ('express', 'local', 'normal'))
);


-- ============================================================
-- 8. NATIONAL RAIL SCHEDULE STOPS
-- ============================================================

CREATE TABLE national_rail_schedule_stops (
    schedule_id     VARCHAR(20) NOT NULL,
    station_id      VARCHAR(10) NOT NULL,
    stop_order      INTEGER NOT NULL,

    PRIMARY KEY (schedule_id, stop_order),
    UNIQUE (schedule_id, station_id),

    FOREIGN KEY (schedule_id)
        REFERENCES national_rail_schedules(schedule_id)
        ON DELETE CASCADE,

    FOREIGN KEY (station_id)
        REFERENCES national_rail_stations(station_id)
        ON DELETE CASCADE,

    CHECK (stop_order > 0)
);


-- ============================================================
-- 9. NATIONAL RAIL SEAT LAYOUTS
-- Source file: national_rail_seat_layouts.json
-- ============================================================

CREATE TABLE national_rail_seat_layouts (
    layout_id       VARCHAR(20) PRIMARY KEY,
    schedule_id     VARCHAR(20) NOT NULL,

    FOREIGN KEY (schedule_id)
        REFERENCES national_rail_schedules(schedule_id)
        ON DELETE CASCADE
);


-- ============================================================
-- 10. NATIONAL RAIL COACHES
-- ============================================================

CREATE TABLE national_rail_coaches (
    layout_id       VARCHAR(20) NOT NULL,
    coach           VARCHAR(10) NOT NULL,
    fare_class      VARCHAR(20) NOT NULL,

    PRIMARY KEY (layout_id, coach),

    FOREIGN KEY (layout_id)
        REFERENCES national_rail_seat_layouts(layout_id)
        ON DELETE CASCADE,

    CHECK (fare_class IN ('first', 'standard'))
);


-- ============================================================
-- 11. NATIONAL RAIL SEATS
-- ============================================================

CREATE TABLE national_rail_seats (
    seat_id        VARCHAR(20) NOT NULL,
    layout_id      VARCHAR(20) NOT NULL,
    coach          VARCHAR(10) NOT NULL,
    seat_row       INTEGER NOT NULL,
    seat_column    CHAR(1) NOT NULL,

    PRIMARY KEY (layout_id, coach, seat_id),

    FOREIGN KEY (layout_id, coach)
        REFERENCES national_rail_coaches(layout_id, coach)
        ON DELETE CASCADE,

    CHECK (seat_row > 0),
    CHECK (seat_column ~ '^[A-Z]$')
);


-- ============================================================
-- 12. TICKET TYPES
-- Source file: ticket_types.json
-- ============================================================

CREATE TABLE ticket_types (
    ticket_type     VARCHAR(20) PRIMARY KEY,
    display_name    VARCHAR(50) NOT NULL,
    available_on    TEXT[] NOT NULL,
    description     TEXT,

    CHECK (array_length(available_on, 1) > 0)
);


-- ============================================================
-- 13. TICKET TYPE RULES
-- Source file: ticket_types.json
-- ============================================================

CREATE TABLE ticket_type_rules (
    ticket_type                VARCHAR(20) NOT NULL,
    network                    VARCHAR(20) NOT NULL,
    pricing_model              VARCHAR(30) NOT NULL,
    formula                    TEXT NOT NULL,
    fare_classes               TEXT[],
    seat_assignment            BOOLEAN NOT NULL DEFAULT FALSE,
    validity                   TEXT,
    advance_purchase           BOOLEAN NOT NULL DEFAULT FALSE,
    advance_purchase_max_days  INTEGER,
    changes_allowed            BOOLEAN NOT NULL DEFAULT FALSE,
    change_fee_usd             DECIMAL(10,2),
    change_deadline            TEXT,
    refundable                 BOOLEAN NOT NULL DEFAULT FALSE,
    refund_rules               TEXT,

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
-- 14. METRO TRAVEL HISTORY
-- Source file: metro_travel_history.json
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

    FOREIGN KEY (user_id)
        REFERENCES registered_users(user_id)
        ON DELETE CASCADE,

    FOREIGN KEY (schedule_id)
        REFERENCES metro_schedules(schedule_id)
        ON DELETE SET NULL,

    FOREIGN KEY (entry_station_id)
        REFERENCES metro_stations(station_id)
        ON DELETE CASCADE,

    FOREIGN KEY (exit_station_id)
        REFERENCES metro_stations(station_id)
        ON DELETE SET NULL,

    FOREIGN KEY (ticket_type)
        REFERENCES ticket_types(ticket_type)
        ON DELETE CASCADE,

    CHECK (tap_out_time IS NULL OR tap_out_time > tap_in_time),
    CHECK (amount_usd >= 0),
    CHECK (status IN ('completed', 'in_progress', 'cancelled')),
    CHECK (
        status != 'completed'
        OR (tap_out_time IS NOT NULL AND exit_station_id IS NOT NULL)
    )
);


-- ============================================================
-- 15. BOOKINGS
-- Source file: bookings.json
-- Purpose: National rail advance bookings.
-- ============================================================

CREATE TABLE bookings (
    booking_id      VARCHAR(20) PRIMARY KEY,
    user_id         VARCHAR(20) NOT NULL,
    schedule_id     VARCHAR(20) NOT NULL,
    ticket_type     VARCHAR(20) NOT NULL,
    layout_id       VARCHAR(20) NOT NULL,
    coach           VARCHAR(10) NOT NULL,
    seat_id         VARCHAR(20) NOT NULL,
    fare_class      VARCHAR(20) NOT NULL,
    amount_usd      DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    booking_date    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    travel_date     DATE NOT NULL,
    status          VARCHAR(20) NOT NULL,

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
        ON DELETE CASCADE,

    CHECK (amount_usd >= 0),
    CHECK (fare_class IN ('first', 'standard')),
    CHECK (status IN ('confirmed', 'cancelled', 'completed'))
);


-- ============================================================
-- 16. PAYMENTS
-- Source file: payments.json
-- Payment can belong to either a booking or a metro trip.
-- ============================================================

CREATE TABLE payments (
    payment_id      VARCHAR(20) PRIMARY KEY,
    user_id         VARCHAR(20) NOT NULL,
    booking_id      VARCHAR(20),
    trip_id         VARCHAR(20),
    amount_usd      DECIMAL(10,2) NOT NULL,
    payment_method  VARCHAR(50) NOT NULL,
    payment_date    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    payment_status  VARCHAR(20) NOT NULL,

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
        (booking_id IS NOT NULL AND trip_id IS NULL)
        OR
        (booking_id IS NULL AND trip_id IS NOT NULL)
    ),
    CHECK (amount_usd >= 0),
    CHECK (payment_status IN ('paid', 'refunded', 'pending', 'failed'))
);


-- ============================================================
-- 17. FEEDBACK
-- Source file: feedback.json
-- ============================================================

CREATE TABLE feedback (
    feedback_id     VARCHAR(20) PRIMARY KEY,
    user_id         VARCHAR(20) NOT NULL,
    booking_id      VARCHAR(20) NOT NULL,
    rating          INTEGER NOT NULL,
    comments        TEXT,
    feedback_date   TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    FOREIGN KEY (user_id)
        REFERENCES registered_users(user_id)
        ON DELETE CASCADE,

    FOREIGN KEY (booking_id)
        REFERENCES bookings(booking_id)
        ON DELETE CASCADE,

    CHECK (rating BETWEEN 1 AND 5)
);


-- ============================================================
-- 18. REFUND POLICY
-- Source file: refund_policy.json
-- ============================================================

CREATE TABLE refund_policy (
    refund_policy_id  VARCHAR(20) PRIMARY KEY,
    label             VARCHAR(50) NOT NULL,
    network           VARCHAR(20) NOT NULL,
    service_type      VARCHAR(20) NOT NULL,
    ticket_type       VARCHAR(20) NOT NULL,
    version           VARCHAR(10) NOT NULL,

    FOREIGN KEY (ticket_type)
        REFERENCES ticket_types(ticket_type)
        ON DELETE CASCADE,

    CHECK (network IN ('metro', 'national_rail', 'all')),
    CHECK (service_type IN ('express', 'local', 'normal', 'all'))
);


-- ============================================================
-- 19. REFUND POLICY WINDOWS
-- Source file: refund_policy.json
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
    CHECK (
        hours_before_departure_min IS NULL
        OR hours_before_departure_max IS NULL
        OR hours_before_departure_max >= hours_before_departure_min
    ),
    CHECK (refund_percentage BETWEEN 0 AND 100),
    CHECK (admin_fee_usd >= 0)
);


-- ============================================================
-- 20. BOOKING RULES
-- Source file: booking_rules.json
-- ============================================================

CREATE TABLE booking_rules (
    booking_rules_id  VARCHAR(20) PRIMARY KEY,
    version           VARCHAR(10) NOT NULL,
    network           VARCHAR(20) NOT NULL,
    last_updated      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    rule_category     VARCHAR(50) NOT NULL,
    rule_title        VARCHAR(100) NOT NULL,
    rule_details      TEXT NOT NULL,
    extra_details     JSONB,

    CHECK (network IN ('metro', 'national_rail', 'all'))
);


-- ============================================================
-- 21. TRAVEL POLICIES
-- Source file: travel_policies.json
-- ============================================================

CREATE TABLE travel_policies (
    travel_policy_id  VARCHAR(20) PRIMARY KEY,
    version           VARCHAR(10) NOT NULL,
    last_updated      DATE,
    network           VARCHAR(20) NOT NULL,
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

CREATE INDEX IF NOT EXISTS idx_policy_documents_embedding 
ON policy_documents 
USING hnsw (embedding vector_cosine_ops);

-- ============================================================
-- 23. PERFORMANCE INDEXES
-- These help common queries run faster.
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_registered_users_email
ON registered_users(email);

CREATE INDEX IF NOT EXISTS idx_metro_schedule_stops_station
ON metro_schedule_stops(station_id);

CREATE INDEX IF NOT EXISTS idx_metro_schedule_stops_schedule_order
ON metro_schedule_stops(schedule_id, stop_order);

CREATE INDEX IF NOT EXISTS idx_national_rail_schedule_stops_station
ON national_rail_schedule_stops(station_id);

CREATE INDEX IF NOT EXISTS idx_national_rail_schedule_stops_schedule_order
ON national_rail_schedule_stops(schedule_id, stop_order);

CREATE INDEX IF NOT EXISTS idx_bookings_user_id
ON bookings(user_id);

CREATE INDEX IF NOT EXISTS idx_bookings_schedule_date
ON bookings(schedule_id, travel_date);

CREATE INDEX IF NOT EXISTS idx_bookings_status
ON bookings(status);

CREATE INDEX IF NOT EXISTS idx_metro_travel_history_user_id
ON metro_travel_history(user_id);

CREATE INDEX IF NOT EXISTS idx_metro_travel_history_travel_date
ON metro_travel_history(travel_date);

CREATE INDEX IF NOT EXISTS idx_payments_user_id
ON payments(user_id);

CREATE INDEX IF NOT EXISTS idx_payments_booking_id
ON payments(booking_id);

CREATE INDEX IF NOT EXISTS idx_payments_trip_id
ON payments(trip_id);

CREATE INDEX IF NOT EXISTS idx_feedback_booking_id
ON feedback(booking_id);

CREATE INDEX IF NOT EXISTS idx_policy_documents_category
ON policy_documents(category);
