"""
TransitFlow — PostgreSQL / Relational Database Layer
=====================================================
This module handles all queries to PostgreSQL.

TWO ROLES ARE SERVED HERE:
  1. Relational  → dual-network transit (metro + national rail),
                   availability, fares, bookings, seat selection
  2. Vector      → policy document similarity search (pgvector)

STUDENT TASK
------------
Design your schema in databases/relational/schema.sql, seed it with
skeleton/seed_postgres.py, then implement the query functions below.

Functions prefixed with `query_`  are read-only lookups called by the agent.
Functions prefixed with `execute_` are write operations (booking/cancellation).

The vector functions (query_policy_vector_search, store_policy_document)
are already implemented — do not modify them.
"""

from __future__ import annotations

import json
import random
import string
from datetime import datetime, timezone
from typing import Optional

import psycopg2
import psycopg2.extras

from skeleton.config import PG_DSN, VECTOR_TOP_K, VECTOR_SIMILARITY_THRESHOLD


def _connect():
    """Return a new psycopg2 connection with autocommit enabled."""
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = True
    return conn


def _gen_booking_id() -> str:
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"BK-{suffix}"


def _gen_payment_id() -> str:
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"PM-{suffix}"


# ── Example ───────────────────────────────────────────────────────────────────
# The block below shows the query pattern: open a cursor, run SQL, return rows.
# Use _connect() for read-only queries; for write operations use a manual
# connection with conn.commit() / conn.rollback() (see execute_booking below).

def example_query() -> dict:
    """Example: returns the name of the connected database."""
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT current_database() AS db;")
            return dict(cur.fetchone())

# TODO: Implement the query_ and execute_ functions below.
# ─────────────────────────────────────────────────────────────────────────────


# ── NATIONAL RAIL AVAILABILITY ────────────────────────────────────────────────

def query_national_rail_availability(
    origin_id: str,
    destination_id: str,
    travel_date: Optional[str] = None,
) -> list[dict]:
    """
    Return national rail schedules that serve both origin and destination stations
    in the correct order, along with seat occupancy for the requested travel date.

    Args:
        origin_id:       e.g. "NR01"
        destination_id:  e.g. "NR05"
        travel_date:     e.g. "2025-06-01" — used to count bookings; omit for general info
    """
    sql = """
        SELECT
            nrs.schedule_id,
            nrs.line,
            nrs.service_type,
            nrs.direction,
            nrs.departure_time,
            nrs.arrival_time,
            origin_stop.stop_order AS origin_stop_order,
            dest_stop.stop_order AS destination_stop_order,
            (dest_stop.stop_order - origin_stop.stop_order) AS stops_travelled,
            COUNT(DISTINCT seats.seat_id) AS total_seats,
            COUNT(DISTINCT b.booking_id) AS booked_seats,
            COUNT(DISTINCT seats.seat_id) - COUNT(DISTINCT b.booking_id) AS available_seats
        FROM national_rail_schedules nrs
        JOIN national_rail_schedule_stops origin_stop
            ON nrs.schedule_id = origin_stop.schedule_id
        JOIN national_rail_schedule_stops dest_stop
            ON nrs.schedule_id = dest_stop.schedule_id
        LEFT JOIN national_rail_seat_layouts layout
            ON nrs.schedule_id = layout.schedule_id
        LEFT JOIN national_rail_seats seats
            ON layout.layout_id = seats.layout_id
        LEFT JOIN bookings b
            ON b.schedule_id = nrs.schedule_id
           AND b.layout_id = seats.layout_id
           AND b.coach = seats.coach
           AND b.seat_id = seats.seat_id
           AND b.status != 'cancelled'
           AND (%s IS NULL OR b.travel_date = %s::date)
        WHERE origin_stop.station_id = %s
          AND dest_stop.station_id = %s
          AND origin_stop.stop_order < dest_stop.stop_order
        GROUP BY
            nrs.schedule_id,
            nrs.line,
            nrs.service_type,
            nrs.direction,
            nrs.departure_time,
            nrs.arrival_time,
            origin_stop.stop_order,
            dest_stop.stop_order
        ORDER BY nrs.departure_time;
    """

    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (travel_date, travel_date, origin_id, destination_id))
            return [dict(row) for row in cur.fetchall()]


def query_national_rail_fare(
    schedule_id: str,
    fare_class: str,
    stops_travelled: int,
) -> Optional[dict]:
    """
    Calculate the fare for a national rail journey.

    Args:
        schedule_id:     e.g. "NR_SCH01"
        fare_class:      "standard" or "first"
        stops_travelled: number of stops between origin and destination (inclusive)

    Returns:
        dict with fare_class, base_fare_usd, per_stop_rate_usd, total_fare_usd
    """
    sql = """
        SELECT
            schedule_id,
            base_fare_usd,
            per_stop_fare_usd
        FROM national_rail_schedules
        WHERE schedule_id = %s;
    """

    fare_class = fare_class.lower().strip()

    if fare_class not in ("standard", "first"):
        return None

    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (schedule_id,))
            row = cur.fetchone()

            if not row:
                return None

            base_fare = float(row["base_fare_usd"])
            per_stop_fare = float(row["per_stop_fare_usd"])

            # Simple assumption:
            # standard = normal price
            # first = 1.5x price
            multiplier = 1.5 if fare_class == "first" else 1.0

            total_fare = (base_fare + (stops_travelled * per_stop_fare)) * multiplier

            return {
                "schedule_id": row["schedule_id"],
                "fare_class": fare_class,
                "base_fare_usd": base_fare,
                "per_stop_rate_usd": per_stop_fare,
                "stops_travelled": stops_travelled,
                "fare_class_multiplier": multiplier,
                "total_fare_usd": round(total_fare, 2),
            }

# ── METRO SCHEDULES & FARE ────────────────────────────────────────────────────

def query_metro_schedules(origin_id: str, destination_id: str) -> list[dict]:
    """
    Return metro schedules that serve both origin and destination in the correct order.

    Args:
        origin_id:       e.g. "MS01"
        destination_id:  e.g. "MS09"
    """
    sql = """
        SELECT
            ms.schedule_id,
            ms.line,
            ms.direction,
            ms.departure_time,
            ms.arrival_time,
            ms.frequency_min,
            origin_stop.stop_order AS origin_stop_order,
            dest_stop.stop_order AS destination_stop_order,
            (dest_stop.stop_order - origin_stop.stop_order) AS stops_travelled
        FROM metro_schedules ms
        JOIN metro_schedule_stops origin_stop
            ON ms.schedule_id = origin_stop.schedule_id
        JOIN metro_schedule_stops dest_stop
            ON ms.schedule_id = dest_stop.schedule_id
        WHERE origin_stop.station_id = %s
          AND dest_stop.station_id = %s
          AND origin_stop.stop_order < dest_stop.stop_order
        ORDER BY ms.line, ms.departure_time;
    """

    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (origin_id, destination_id))
            return [dict(row) for row in cur.fetchall()]


def query_metro_fare(schedule_id: str, stops_travelled: int) -> Optional[dict]:
    """
    Calculate the metro fare for a single-ticket journey.

    Args:
        schedule_id:     e.g. "MS_SCH01"
        stops_travelled: number of stops between origin and destination

    Returns:
        dict with base_fare_usd, per_stop_rate_usd, total_fare_usd
    """
    sql = """
        SELECT
            schedule_id,
            base_fare_usd,
            per_stop_fare_usd
        FROM metro_schedules
        WHERE schedule_id = %s;
    """

    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (schedule_id,))
            row = cur.fetchone()

            if not row:
                return None

            base_fare = float(row["base_fare_usd"])
            per_stop_fare = float(row["per_stop_fare_usd"])
            total_fare = base_fare + (stops_travelled * per_stop_fare)

            return {
                "schedule_id": row["schedule_id"],
                "base_fare_usd": base_fare,
                "per_stop_rate_usd": per_stop_fare,
                "stops_travelled": stops_travelled,
                "total_fare_usd": round(total_fare, 2),
            }


# ── SEAT SELECTION ────────────────────────────────────────────────────────────

def query_available_seats(
    schedule_id: str,
    travel_date: str,
    fare_class: str,
) -> list[dict]:
    """
    Return available seats for a national rail journey on a given date.

    Args:
        schedule_id:  e.g. "NR_SCH01"
        travel_date:  e.g. "2025-06-01"
        fare_class:   "standard" or "first"

    Returns:
        List of dicts: {seat_id, coach, row, column}
    """
    fare_class = fare_class.lower().strip()
    sql = """
        SELECT
            seats.seat_id,
            seats.coach,
            seats.seat_row AS row,
            seats.seat_column AS column,
            layout.layout_id,
            coaches.fare_class
        FROM national_rail_seat_layouts layout
        JOIN national_rail_coaches coaches
            ON layout.layout_id = coaches.layout_id
        JOIN national_rail_seats seats
            ON seats.layout_id = coaches.layout_id
           AND seats.coach = coaches.coach
        LEFT JOIN bookings b
            ON b.layout_id = seats.layout_id
           AND b.coach = seats.coach
           AND b.seat_id = seats.seat_id
           AND b.schedule_id = layout.schedule_id
           AND b.travel_date = %s::date
           AND b.status != 'cancelled'
        WHERE layout.schedule_id = %s
          AND coaches.fare_class = %s
          AND b.booking_id IS NULL
        ORDER BY seats.coach, seats.seat_row, seats.seat_column;
    """

    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (travel_date, schedule_id, fare_class))
            return [dict(row) for row in cur.fetchall()]

def auto_select_adjacent_seats(available_seats: list[dict], count: int) -> list[str]:
    """
    Select `count` seats that are as close together as possible (same row preferred,
    then adjacent rows). Returns a list of seat_ids.

    Args:
        available_seats: output of query_available_seats()
        count:           number of seats needed
    """
    if not available_seats or count <= 0:
        return []
    if count >= len(available_seats):
        return [s["seat_id"] for s in available_seats[:count]]

    from collections import defaultdict
    rows: dict[int, list[dict]] = defaultdict(list)
    for seat in available_seats:
        rows[seat["row"]].append(seat)

    for row_seats in sorted(rows.values(), key=lambda s: s[0]["row"]):
        if len(row_seats) >= count:
            return [s["seat_id"] for s in row_seats[:count]]

    sorted_seats = sorted(available_seats, key=lambda s: (s["row"], s["column"]))
    return [s["seat_id"] for s in sorted_seats[:count]]


# ── USER & BOOKING QUERIES ────────────────────────────────────────────────────

def query_user_profile(user_email: str) -> Optional[dict]:
    """Return a user's profile by email."""
    sql = """
        SELECT
            user_id,
            name AS full_name,
            email,
            phone_number,
            year_of_birth,
            registered_at,
            is_active
        FROM registered_users
        WHERE email = %s;
    """

    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (user_email,))
            row = cur.fetchone()
            return dict(row) if row else None


def query_user_bookings(user_email: str) -> dict:
    """
    Return a user's combined booking history (national rail + metro).

    Returns:
        dict with keys 'national_rail' (list) and 'metro' (list)
    """
    sql_user = """
        SELECT user_id
        FROM registered_users
        WHERE email = %s;
    """

    sql_rail = """
        SELECT
            b.booking_id,
            b.schedule_id,
            nrs.line,
            nrs.service_type,
            nrs.departure_time,
            nrs.arrival_time,
            b.ticket_type,
            b.fare_class,
            b.layout_id,
            b.coach,
            b.seat_id,
            b.amount_usd,
            b.booking_date,
            b.travel_date,
            b.status
        FROM bookings b
        JOIN national_rail_schedules nrs
            ON b.schedule_id = nrs.schedule_id
        WHERE b.user_id = %s
        ORDER BY b.travel_date DESC, b.booking_date DESC;
    """

    sql_metro = """
        SELECT
            mt.trip_id,
            mt.schedule_id,
            ms.line,
            ms.direction,
            mt.entry_station_id,
            entry_station.name AS entry_station_name,
            mt.exit_station_id,
            exit_station.name AS exit_station_name,
            mt.ticket_type,
            mt.travel_date,
            mt.tap_in_time,
            mt.tap_out_time,
            mt.amount_usd,
            mt.status
        FROM metro_travel_history mt
        LEFT JOIN metro_schedules ms
            ON mt.schedule_id = ms.schedule_id
        JOIN metro_stations entry_station
            ON mt.entry_station_id = entry_station.station_id
        LEFT JOIN metro_stations exit_station
            ON mt.exit_station_id = exit_station.station_id
        WHERE mt.user_id = %s
        ORDER BY mt.travel_date DESC, mt.tap_in_time DESC;
    """

    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql_user, (user_email,))
            user = cur.fetchone()

            if not user:
                return {"national_rail": [], "metro": []}

            user_id = user["user_id"]

            cur.execute(sql_rail, (user_id,))
            national_rail = [dict(row) for row in cur.fetchall()]

            cur.execute(sql_metro, (user_id,))
            metro = [dict(row) for row in cur.fetchall()]

            return {
                "national_rail": national_rail,
                "metro": metro,
            }


def query_payment_info(booking_id: str) -> Optional[dict]:
    """Return payment record for a booking or metro trip."""
    sql = """
        SELECT
            payment_id,
            user_id,
            booking_id,
            trip_id,
            amount_usd,
            payment_method,
            payment_date,
            payment_status
        FROM payments
        WHERE booking_id = %s
           OR trip_id = %s
        ORDER BY payment_date DESC
        LIMIT 1;
    """

    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (booking_id, booking_id))
            row = cur.fetchone()
            return dict(row) if row else None


# ── TRANSACTIONAL OPERATIONS ──────────────────────────────────────────────────

def execute_booking(
    user_id: str,
    schedule_id: str,
    origin_station_id: str,
    destination_station_id: str,
    travel_date: str,
    fare_class: str,
    seat_id: str,
    ticket_type: str = "single",
) -> tuple[bool, dict | str]:
    """
    Create a national rail booking for a logged-in user.

    Args:
        user_id:                e.g. "RU01" — must match the logged-in user
        schedule_id:            e.g. "NR_SCH01"
        origin_station_id:      e.g. "NR01"
        destination_station_id: e.g. "NR05"
        travel_date:            e.g. "2025-06-01"
        fare_class:             "standard" or "first"
        seat_id:                e.g. "B05" (or "any" to auto-assign)
        ticket_type:            "single" (default) or "return"

    Returns:
        (True, booking_dict)   on success
        (False, error_message) on failure
    """
    fare_class = fare_class.lower().strip()
    ticket_type = ticket_type.lower().strip()
    seat_id = seat_id.strip()

    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = False

    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # 1. Check user exists
            cur.execute(
                """
                SELECT user_id
                FROM registered_users
                WHERE user_id = %s
                  AND is_active = TRUE;
                """,
                (user_id,),
            )
            if not cur.fetchone():
                conn.rollback()
                return False, "User not found or inactive."

            # 2. Check route order
            cur.execute(
                """
                SELECT
                    origin_stop.stop_order AS origin_stop_order,
                    dest_stop.stop_order AS destination_stop_order,
                    (dest_stop.stop_order - origin_stop.stop_order) AS stops_travelled
                FROM national_rail_schedule_stops origin_stop
                JOIN national_rail_schedule_stops dest_stop
                    ON origin_stop.schedule_id = dest_stop.schedule_id
                WHERE origin_stop.schedule_id = %s
                  AND origin_stop.station_id = %s
                  AND dest_stop.station_id = %s
                  AND origin_stop.stop_order < dest_stop.stop_order;
                """,
                (schedule_id, origin_station_id, destination_station_id),
            )
            route = cur.fetchone()

            if not route:
                conn.rollback()
                return False, "No valid route found for the selected origin and destination."

            stops_travelled = int(route["stops_travelled"])

            # 3. Determine seat
            available_seats = query_available_seats(schedule_id, travel_date, fare_class)

            if not available_seats:
                conn.rollback()
                return False, "No available seats for the selected schedule, date, and fare class."

            selected_seat = None

            if seat_id.lower() == "any":
                selected_seat = available_seats[0]
            else:
                for seat in available_seats:
                    if seat["seat_id"] == seat_id:
                        selected_seat = seat
                        break

            if not selected_seat:
                conn.rollback()
                return False, "Selected seat is not available."

            # 4. Calculate fare
            fare_info = query_national_rail_fare(schedule_id, fare_class, stops_travelled)
            if not fare_info:
                conn.rollback()
                return False, "Could not calculate fare."

            amount_usd = fare_info["total_fare_usd"]
            booking_id = _gen_booking_id()

            # 5. Insert booking
            cur.execute(
                """
                INSERT INTO bookings (
                    booking_id,
                    user_id,
                    schedule_id,
                    ticket_type,
                    layout_id,
                    coach,
                    seat_id,
                    fare_class,
                    amount_usd,
                    travel_date,
                    status
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::date, 'confirmed')
                RETURNING *;
                """,
                (
                    booking_id,
                    user_id,
                    schedule_id,
                    ticket_type,
                    selected_seat["layout_id"],
                    selected_seat["coach"],
                    selected_seat["seat_id"],
                    fare_class,
                    amount_usd,
                    travel_date,
                ),
            )

            booking = dict(cur.fetchone())

            # 6. Insert payment
            payment_id = _gen_payment_id()
            cur.execute(
                """
                INSERT INTO payments (
                    payment_id,
                    user_id,
                    booking_id,
                    trip_id,
                    amount_usd,
                    payment_method,
                    payment_status
                )
                VALUES (%s, %s, %s, NULL, %s, %s, 'paid')
                RETURNING *;
                """,
                (
                    payment_id,
                    user_id,
                    booking_id,
                    amount_usd,
                    "mock_payment",
                ),
            )

            payment = dict(cur.fetchone())

            conn.commit()

            booking["payment"] = payment
            booking["origin_station_id"] = origin_station_id
            booking["destination_station_id"] = destination_station_id
            booking["stops_travelled"] = stops_travelled

            return True, booking

    except Exception as e:
        conn.rollback()
        return False, str(e)

    finally:
        conn.close()


def execute_cancellation(booking_id: str, user_id: str) -> tuple[bool, dict | str]:
    """
    Cancel a national rail booking owned by the given user.

    Calculates the refund amount according to the booking's service type:
      - Normal service: RF001 windows (100% / 75% / 50% / 0%)
      - Express service: RF002 windows (100% / 50% / 0%)

    Args:
        booking_id: e.g. "BK001"
        user_id:    must match the booking's user_id

    Returns:
        (True, result_dict)  with refund_amount_usd and policy note
        (False, error_msg)
    """
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = False

    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    b.booking_id,
                    b.user_id,
                    b.schedule_id,
                    b.amount_usd,
                    b.travel_date,
                    b.status,
                    nrs.service_type,
                    nrs.departure_time
                FROM bookings b
                JOIN national_rail_schedules nrs
                    ON b.schedule_id = nrs.schedule_id
                WHERE b.booking_id = %s
                  AND b.user_id = %s;
                """,
                (booking_id, user_id),
            )

            booking = cur.fetchone()

            if not booking:
                conn.rollback()
                return False, "Booking not found or does not belong to this user."

            if booking["status"] == "cancelled":
                conn.rollback()
                return False, "Booking is already cancelled."

            # Build departure datetime
            travel_date_value = booking["travel_date"]
            departure_time_value = booking["departure_time"]

            departure_datetime = datetime.combine(
                travel_date_value,
                departure_time_value,
            )

            if departure_datetime.tzinfo is None:
                departure_datetime = departure_datetime.replace(tzinfo=timezone.utc)

            now = datetime.now(timezone.utc)
            hours_before_departure = (departure_datetime - now).total_seconds() / 3600

            service_type = booking["service_type"]

            # Simple mapping based on docstring:
            # normal/local => RF001
            # express => RF002
            if service_type == "express":
                refund_policy_id = "RF002"
            else:
                refund_policy_id = "RF001"

            cur.execute(
                """
                SELECT
                    window_id,
                    label,
                    hours_before_departure_min,
                    hours_before_departure_max,
                    refund_percentage,
                    admin_fee_usd
                FROM refund_policy_windows
                WHERE refund_policy_id = %s
                  AND (
                        hours_before_departure_min IS NULL
                        OR %s >= hours_before_departure_min
                  )
                  AND (
                        hours_before_departure_max IS NULL
                        OR %s < hours_before_departure_max
                  )
                ORDER BY hours_before_departure_min DESC NULLS LAST
                LIMIT 1;
                """,
                (
                    refund_policy_id,
                    hours_before_departure,
                    hours_before_departure,
                ),
            )

            window = cur.fetchone()

            if not window:
                refund_percentage = 0
                admin_fee = 0
                policy_note = "No matching refund window found."
            else:
                refund_percentage = float(window["refund_percentage"])
                admin_fee = float(window["admin_fee_usd"])
                policy_note = window["label"]

            original_amount = float(booking["amount_usd"])
            refund_amount = max(
                0,
                (original_amount * refund_percentage / 100) - admin_fee,
            )

            cur.execute(
                """
                UPDATE bookings
                SET status = 'cancelled'
                WHERE booking_id = %s
                RETURNING *;
                """,
                (booking_id,),
            )
            updated_booking = dict(cur.fetchone())

            cur.execute(
                """
                UPDATE payments
                SET payment_status = 'refunded'
                WHERE booking_id = %s;
                """,
                (booking_id,),
            )

            conn.commit()

            return True, {
                "booking": updated_booking,
                "original_amount_usd": round(original_amount, 2),
                "refund_amount_usd": round(refund_amount, 2),
                "refund_percentage": refund_percentage,
                "admin_fee_usd": admin_fee,
                "refund_policy_id": refund_policy_id,
                "policy_note": policy_note,
            }

    except Exception as e:
        conn.rollback()
        return False, str(e)

    finally:
        conn.close()


# ── AUTHENTICATION QUERIES ────────────────────────────────────────────────────

def register_user(
    email: str,
    first_name: str,
    surname: str,
    year_of_birth: int,
    password: str,
    secret_question: str,
    secret_answer: str,
) -> tuple[bool, str]:
    """
    Register a new user.
    Returns (True, user_id) on success or (False, error_message) on failure.

    NOTE: passwords are stored as plain text here intentionally for teaching
    purposes. In production, replace with a salted hash (e.g. bcrypt).
    """
    user_id = "RU-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    full_name = f"{first_name} {surname}".strip()

    sql = """
        INSERT INTO registered_users (
            user_id,
            name,
            email,
            password_hash,
            year_of_birth,
            secret_question,
            secret_answer,
            is_active
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE)
        RETURNING user_id;
    """

    try:
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    (
                        user_id,
                        full_name,
                        email,
                        password,
                        year_of_birth,
                        secret_question,
                        secret_answer,
                    ),
                )
                return True, cur.fetchone()[0]

    except psycopg2.IntegrityError as e:
        return False, f"Registration failed: {e}"
    except Exception as e:
        return False, str(e)


def login_user(email: str, password: str) -> Optional[dict]:
    """
    Verify credentials. Returns a user dict on success or None on failure.
    Dict keys: user_id, email, full_name, first_name, surname, phone, date_of_birth, is_active.
    """
    sql = """
        SELECT
            user_id,
            name AS full_name,
            email,
            phone_number AS phone,
            year_of_birth,
            is_active
        FROM registered_users
        WHERE email = %s
          AND password_hash = %s
          AND is_active = TRUE;
    """

    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (email, password))
            row = cur.fetchone()

            if not row:
                return None

            user = dict(row)

            name_parts = user["full_name"].split(" ", 1)
            user["first_name"] = name_parts[0]
            user["surname"] = name_parts[1] if len(name_parts) > 1 else ""
            user["date_of_birth"] = None

            return user


def get_user_secret_question(email: str) -> Optional[str]:
    """Return the secret question for a registered email, or None if not found."""
    sql = """
        SELECT secret_question
        FROM registered_users
        WHERE email = %s;
    """

    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (email,))
            row = cur.fetchone()
            return row[0] if row else None


def verify_secret_answer(email: str, answer: str) -> bool:
    """Return True if the provided answer matches the stored secret answer (case-insensitive)."""
    sql = """
        SELECT secret_answer
        FROM registered_users
        WHERE email = %s;
    """

    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (email,))
            row = cur.fetchone()

            if not row or row[0] is None:
                return False

            stored_answer = str(row[0]).strip().lower()
            provided_answer = str(answer).strip().lower()

            return stored_answer == provided_answer


def update_password(email: str, new_password: str) -> bool:
    """Update the password for a user. Returns True if the row was updated."""
    sql = """
        UPDATE registered_users
        SET password_hash = %s
        WHERE email = %s;
    """

    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (new_password, email))
            return cur.rowcount > 0


# ── VECTOR / RAG QUERIES — do not modify ─────────────────────────────────────

def query_policy_vector_search(embedding: list[float], top_k: int = VECTOR_TOP_K) -> list[dict]:
    """
    Find the most relevant policy documents for a given query embedding.

    Args:
        embedding: Query vector from llm.embed(user_question)
        top_k:     Number of results to return

    Returns:
        List of dicts with title, category, content, and similarity score
    """
    sql = """
        SELECT
            title,
            category,
            content,
            1 - (embedding <=> %s::vector) AS similarity
        FROM policy_documents
        WHERE 1 - (embedding <=> %s::vector) > %s
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """
    vec_str = "[" + ",".join(str(x) for x in embedding) + "]"
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (vec_str, vec_str, VECTOR_SIMILARITY_THRESHOLD, vec_str, top_k))
            return [dict(row) for row in cur.fetchall()]


def store_policy_document(
    title: str,
    category: str,
    content: str,
    embedding: list[float],
    source_file: str = "",
) -> int:
    """
    Insert a policy document with its embedding into the database.
    Used by skeleton/seed_vectors.py — students don't need to call this directly.

    Returns:
        The new document's id
    """
    sql = """
        INSERT INTO policy_documents (title, category, content, embedding, source_file)
        VALUES (%s, %s, %s, %s::vector, %s)
        RETURNING id
    """
    vec_str = "[" + ",".join(str(x) for x in embedding) + "]"
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (title, category, content, vec_str, source_file))
            return cur.fetchone()[0]
