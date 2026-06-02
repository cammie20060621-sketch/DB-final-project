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
-- ============================================================

DROP TABLE IF EXISTS metro_stations CASCADE;
DROP TABLE IF EXISTS metro_schedules CASCADE;
DROP TABLE IF EXISTS metro_schedule_stops CASCADE;
DROP TABLE IF EXISTS metro_travel_history CASCADE;

DROP TABLE IF EXISTS national_rail_stations CASCADE;
DROP TABLE IF EXISTS national_rail_schedules CASCADE; 
DROP TABLE IF EXISTS national_rail_schedule_stops CASCADE;  
DROP TABLE IF EXISTS national_rail_seat_layouts CASCADE;

DROP TABLE IF EXISTS registered_users CASCADE;

DROP TABLE IF EXISTS bookings CASCADE;
DROP TABLE IF EXISTS payments CASCADE;
DROP TABLE IF EXISTS feedback CASCADE;

DROP TABLE IF EXISTS refund_policy CASCADE;
DROP TABLE IF EXISTS booking_rules CASCADE;
DROP TABLE IF EXISTS travel_policies CASCADE;
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


--=============================================================
-- 2. METRO STATIONS
--=============================================================
CREATE TABLE metro_stations (
    station_id                   VARCHAR(10) PRIMARY KEY,
    name                         TEXT NOT NULL,
    is_interchange_metro         BOOLEAN NOT NULL,
    is_interchange_national_rail BOOLEAN NOT NULL,
    interchange_rail_station_id  VARCHAR(10)
)

--=============================================================
-- 3. METRO SCHEDULES
--=============================================================
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
--  This is a table stores the order of stops for each metro_schedule.
--  Example:
--  schedule_id | station_id | stop_order
--    MSCH01     |  MS01     |    1
--    MSCH01     |  MS02     |    2
--    MSCH01     |  MS03     |    3
-- ==============================================================

CREATE TABLE metro_schedule_stops (
    schedule_id     VARCHAR(20) NOT NULL,
    station_id      VARCHAR(10) NOT NULL,
    stop_order        INTEGER NOT NULL,

    PRIMARY KEY (schedule_id, stop_order),
    UNIQUE (schedule_id, station_id),

    FOREIGN KEY (schedule_id) REFERENCES metro_schedules(schedule_id) ON DELETE CASCADE,
    FOREIGN KEY (station_id) REFERENCES metro_stations(station_id) ON DELETE CASCADE,

    CHECK (stop_order > 0)
);

-- ==============================================================
-- 5. METRO TRAVEL HISTORY
--  Source file: metro_travel_history.json
--
-- Metro does not have seat reservations
-- so we only store the tap-in and tap-out for each trip.
-- ==============================================================

CREATE TABLE metro_travel_history (
    trip_id             VARCHAR(20) PRIMARY KEY,
    user_id             VARCHAR(20) NOT NULL,
    schedule_id         VARCHAR(20),
    entry_station_id    VARCHAR(10) NOT NULL,
    exit_station_id     VARCHAR(10),
    ticket_type         VARCHAR(20) NOT NULL,  -- 'single', 'day_pass', etc.
    travel_date         DATE NOT NULL,
    tap_in_time         TIMESTAMPTZ NOT NULL,
    tap_out_time        TIMESTAMPTZ ,
    amount_usd     DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    status              VARCHAR(20) NOT NULL ,  -- 'completed', 'in_progress', 'cancelled'

    FOREIGN KEY (user_id) REFERENCES registered_users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (schedule_id) REFERENCES metro_schedules(schedule_id) ON DELETE CASCADE,
    FOREIGN KEY (entry_station_id) REFERENCES metro_stations(station_id) ON DELETE CASCADE,
    FOREIGN KEY (exit_station_id) REFERENCES metro_stations(station_id) ON DELETE CASCADE,

    CHECK (tap_out_time > tap_in_time),
    CHECK (amount_usd >= 0),
    CHECK(status IN ('completed', 'in_progress', 'cancelled'))
);

-- ==============================================================
-- 6. NATIONAL RAIL STATIONS
-- ==============================================================

CREATE TABLE national_rail_stations (
    station_id                   VARCHAR(10) PRIMARY KEY,
    name                         TEXT NOT NULL,
    city                         VARCHAR(50),
    is_interchange_metro         BOOLEAN NOT NULL,
    is_interchange_national_rail BOOLEAN NOT NULL,
    interchange_national_rail_station_lines TEXT[],  -- e.g. ['NR Line 1', 'NR Line 2']
    interchange_metro_station_id VARCHAR(10),

    FOREIGN KEY (interchange_metro_station_id) 
    REFERENCES metro_stations(station_id) 
    ON DELETE SET NULL,

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

-- ==============================================================
-- 7. NATIONAL RAIL SCHEDULES
-- ==============================================================

CREATE TABLE national_rail_schedules (
    schedule_id         VARCHAR(20) PRIMARY KEY,
    line                VARCHAR(20) NOT NULL,
    service_type         VARCHAR(50) NOT NULL,  -- 'express', 'local'
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
-- ==============================================================

CREATE TABLE national_rail_schedule_stops (
    schedule_id     VARCHAR(20) NOT NULL,
    station_id      VARCHAR(10) NOT NULL,
    stop_order      INTEGER NOT NULL,

    PRIMARY KEY (schedule_id, station_id),
    UNIQUE (schedule_id, stop_order),

    FOREIGN KEY (schedule_id) REFERENCES national_rail_schedules(schedule_id) ON DELETE CASCADE,
    FOREIGN KEY (station_id) REFERENCES national_rail_stations(station_id) ON DELETE CASCADE,

    CHECK (stop_order > 0)
);

-- ==============================================================
-- 9. NATIONAL RAIL SEAT LAYOUTS
--  Source file:
--    national_rail_seat_layouts.json
--
--  Purpose:
--    Stores the top-level seat layout for a national rail schedule.
--
--  JSON structure:
--    layout
--      → coaches
--          → seats
--
--  This table represents the layout level.
-- ==============================================================

CREATE TABLE national_rail_seat_layouts (
    schedule_id     VARCHAR(20) NOT NULL,
    layout_id       VARCHAR(20) PRIMARY KEY,
 
    FOREIGN KEY (schedule_id) 
        REFERENCES national_rail_schedules(schedule_id) 
        ON DELETE CASCADE,
    CHECK (seat_row > 0 AND seat_column ~ '^[A-Z]$')
);

-- ==============================================================
-- 10. NATIONAL RAIL COACHES
--  Source file:
--    national_rail_seat_layouts.json
--
--  Purpose:
--    Stores coaches inside each seat layout.
--
--  Example:
--    layout_id = SL01
--    coach = A
--    fare_class = first
-- ==============================================================

CREATE TABLE national_rail_coaches (
    layout_id       VARCHAR(20) NOT NULL,
    coach           VARCHAR(10) NOT NULL,
    fare_class      VARCHAR(20) NOT NULL,  -- 'first', 'second'

    PRIMARY KEY (layout_id, coach),

     FOREIGN KEY (layout_id) 
        REFERENCES national_rail_seat_layouts(layout_id) 
        ON DELETE CASCADE

);

-- ==============================================================
-- 11. NATIONAL RAIL SEATS
--  Source file:
--    national_rail_seat_layouts.json
--
--  Purpose:
--    Stores individual seats inside each coach.
--
--  Example:
--    layout_id = SL01
--    coach = A
--    seat_id = A01
--    seat_row = 1
--    seat_column = A
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
        ON DELETE CASCADE
    
    CHECK (seat_row > 0 AND seat_column ~ '^[A-Z]$')
);

-- ==============================================================
-- 12. TICKET TYPES
--
--  Source file:
--    ticket_types.json
--
--  Purpose:
--    Stores ticket type definitions and rules.
-- ==============================================================

CREATE TABLE ticket_types (
    ticket_type        VARCHAR(20) PRIMARY KEY, --'single', 'return', 'day_pass', 'weekly_pass', etc.
    display_name       VARCHAR(50) NOT NULL,
    available_on       TEXT[] NOT NULL,  -- 'metro', 'national_rail', 'both'
    description        TEXT
);

-- ==============================================================
-- 13. TICKET TYPE NETWORK RULES
-- ==============================================================

CREATE TABLE ticket_type_rules (
    ticket_type        VARCHAR(20) NOT NULL,
    network            VARCHAR(20) NOT NULL, -- 'metro' or 'national_rail'
    pricing_model      VARCHAR(20) NOT NULL, -- 'flat_rate', 'stops_based', 'stops_based_with_fare_class','stops_based_per_leg'
    formula            TEXT NOT NULL, -- e.g. '5.00', '2.00 + 0.50 * stops', 'base_fare + per_stop_fare * stops * fare_class_multiplier', 'base_fare + per_stop_fare * stops * fare_class_multiplier + leg_fee'
    
    fare_classes        TEXT[], -- e.g. ['first', 'standard'], only applicable if pricing_model involves fare_class
    seat_assignment     BOOLEAN NOT NULL DEFAULT FALSE, -- whether this ticket type requires seat assignment (only for national rail)
    validity           TEXT, -- e.g. '1 day from purchase', 'valid on specific date', 'valid for 7 days', etc.
    
    advance_purchase   BOOLEAN NOT NULL DEFAULT FALSE, -- whether this ticket type requires advance purchase
    advance_purchase_max_days INTEGER, -- how many days in advance the ticket must be purchased, only applicable if advance_purchase is true

    changes_allowed       BOOLEAN NOT NULL DEFAULT FALSE, -- whether ticket changes are allowed
    change_fee_usd       DECIMAL(10,2), -- fee for changing the ticket, only applicable if changes_allowed is true
    change_deadline      TEXT, -- how many hours before departure the change is allowed, only applicable if changes_allowed is true

    refundable            BOOLEAN NOT NULL DEFAULT FALSE, -- whether this ticket type is refundable
    refund_rules          TEXT, -- e.g. 'full_refund_before_departure', 'partial_refund_before_departure', 'no_refund', etc.

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
--  14. BOOKINGS
--
--  Source file:
--    bookings.json
--
--  Purpose:
--    Stores national rail advance bookings.
--
--  National rail supports:
--    - advance booking
--    - fare class
--    - seat assignment
--
--  Seat design:
--    layout_id + coach + seat_id points to national_rail_seats.
-- ============================================================

CREATE TABLE bookings (
    booking_id         VARCHAR(20) PRIMARY KEY,
    user_id            VARCHAR(20) NOT NULL,
    schedule_id        VARCHAR(20) NOT NULL,
    ticket_type        VARCHAR(20) NOT NULL,
    layout_id          VARCHAR(20) NOT NULL,
    coach              VARCHAR(10) NOT NULL,
    seat_id            VARCHAR(20) NOT NULL,
    fare_class         VARCHAR(20) NOT NULL,  -- 'first', 'second'
    booking_date       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    travel_date        DATE NOT NULL,
    status             VARCHAR(20) NOT NULL,  -- 'confirmed', 'cancelled', 'completed'

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
    ON DELETE CASCADE
    CHECK(status IN ('confirmed', 'cancelled', 'completed'))
);

-- ============================================================
-- 15. PAYMENTS
--  Source file:
--    payments.json
--  Purpose:
--    Stores payment records for both metro and national rail transactions.
--  A payment can be linked to either:
--    - a national rail booking (booking_id)
--    - or a metro travel history record (trip_id)
--  Constraint:
--    Exactly one of booking_id or travel_id should be filled.
-- ============================================================

CREATE TABLE payments (
    payment_id         VARCHAR(20) PRIMARY KEY,
    user_id            VARCHAR(20) NOT NULL,
    booking_id         VARCHAR(20),
    trip_id            VARCHAR(20),
    amount_usd         DECIMAL(10,2) NOT NULL,
    payment_method     VARCHAR(50) NOT NULL,  -- 'credit_card', 'ewallet', 'debit_card', etc.
    payment_date       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    payment_status     VARCHAR(20) NOT NULL,  -- 'paid', 'refunded'
    

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
    CHECK (amount_usd >= 0)
);

-- ============================================================
-- 16. FEEDBACK
--  Source file:
--    feedback.json
--  Purpose:
--    Stores user feedback for  national rail experiences.
--  A feedback record only can be linked to:
--    - a national rail booking (booking_id)
-- ============================================================

CREATE TABLE feedback (
    feedback_id        VARCHAR(20) PRIMARY KEY,
    user_id            VARCHAR(20) NOT NULL,
    booking_id         VARCHAR(20),
    rating             INTEGER CHECK (rating >= 1 AND rating <= 5),
    comments           TEXT,
    feedback_date      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    FOREIGN KEY (user_id) 
        REFERENCES registered_users(user_id) 
        ON DELETE CASCADE,
    FOREIGN KEY (booking_id) 
        REFERENCES bookings(booking_id) 
        ON DELETE CASCADE,

    CHECK (booking_id IS NOT NULL)
);

-- ============================================================
-- 17. REFUND POLICY
--  Source file:
--    refund_policy.json
--  Purpose:
--    Stores structured refund eligibility rules.
--
--  Note:
--    This is different from policy_documents.
--    refund_policy is structured SQL data.
--    policy_documents is vector/RAG text data.
-- ============================================================

CREATE TABLE refund_policy (
    refund_policy_id   VARCHAR(20) PRIMARY KEY,
    label                VARCHAR(50) NOT NULL,  -- e.g. 'full_refund_before_departure', 'partial_refund_before_departure', 'no_refund'
    network              VARCHAR(20) NOT NULL,  -- 'metro', 'national_rail', 'all'
    service_type         VARCHAR(20) NOT NULL,  -- 'express', 'local', 'normal'
    ticket_type          VARCHAR(20) NOT NULL,  -- 'single', 'return', 'day_pass', etc.
    version              VARCHAR(10) NOT NULL,  -- links to the version of the refund policy

   CHECK (network IN ('metro', 'national_rail', 'all') )
);

-- ============================================================
-- 18. REFUND POLICY WINDOWS
--  Source file:
--    refund_policy.json
--  Purpose:
--    Stores the time windows for refund eligibility.
-- Example:
-- policy_id | hours_before_departure_min | hours_before_departure_max
--  RP01      | 24                         | 12
-- This means:
-- - Full refund if cancelled more than 24 hours before departure
-- - Partial refund if cancelled between 12 and 24 hours before departure
-- - No refund if cancelled less than 12 hours before departure
-- ============================================================

CREATE TABLE refund_policy_windows (
    window_id          VARCHAR(30) PRIMARY KEY,
    refund_policy_id   VARCHAR(20) NOT NULL,
    label              VARCHAR(50) NOT NULL,  -- e.g. 'full_refund', 'partial_refund', 'no_refund'
    hours_before_departure_min INTEGER,  -- hours before departure when refund eligibility starts
    hours_before_departure_max   INTEGER,  -- hours before departure when refund eligibility ends
    refund_percentage  DECIMAL(5,2) NOT NULL,  -- e.g. 100.00 for full refund, 50.00 for partial refund, 0.00 for no refund
    admin_fee_usd      DECIMAL(10,2) NOT NULL DEFAULT 0.00,  -- administrative fee deducted from refund amount

    FOREIGN KEY (refund_policy_id) 
        REFERENCES refund_policy(refund_policy_id) 
        ON DELETE CASCADE,

    CHECK (
        hours_before_departure_min IS NULL
        OR hours_before_departure_min >= 0
    ),

    CHECK (
        hours_before_departure_max IS NULL
        OR hours_before_departure_max >= 0
    ),

    CHECK (refund_percentage BETWEEN 0 AND 100),
    CHECK (admin_fee_usd >= 0)
);

-- ============================================================
-- 19. BOOKING RULES
--  Source file:
--    booking_rules.json
--  Purpose:
--    Stores structured booking rules for different ticket types and networks.
-- ============================================================

CREATE TABLE booking_rules (
    booking_rules_id            VARCHAR(20) PRIMARY KEY,
    version            VARCHAR(10) NOT NULL,
    network            VARCHAR(20) NOT NULL,  -- 'metro' or 'national_rail'
    last_updated       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    rule_category      VARCHAR(50) NOT NULL,  -- 'advance_purchase', 'cancellation', 'changes', etc.
    rule_title         VARCHAR(100) NOT NULL,
    rule_details       TEXT NOT NULL,
    extra_details      JSONB,  -- for any additional structured data related to the rule
    
    CHECK (network IN ('metro', 'national_rail') )
);

-- ============================================================
-- 20. TRAVEL POLICIES
--  Source file:
--    travel_policies.json
--  Purpose:
--    Stores structured travel policies that may impact booking and refunds.
-- ============================================================

CREATE TABLE travel_policies (
    travel_policy_id          VARCHAR(20) PRIMARY KEY,
    version            VARCHAR(10) NOT NULL,
    last_updated     DATE,
    network          VARCHAR(20) NOT NULL,  -- 'metro', 'national_rail', 'all'
    policy_category    VARCHAR(50) NOT NULL,  -- 'covid', 'weather', 'security', etc.
    policy_title       VARCHAR(100) NOT NULL,
    policy_details     TEXT NOT NULL,
    extra_details      JSONB,  -- for any additional structured data related to the policy
    
    CHECK (network IN ('metro', 'national_rail', 'all') )
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
