"""
Seed PostgreSQL with all TransitFlow mock data from train-mock-data/.

Usage:
    python skeleton/seed_postgres.py

Run AFTER docker-compose up -d.
You must first design and create your tables in databases/relational/schema.sql.
Safe to re-run: implement your inserts with ON CONFLICT DO NOTHING.
"""

import json
import os
import sys

import psycopg2
from psycopg2.extras import execute_values
from tomlkit import item

# ── resolve paths ────────────────────────────────────────────────────────────
SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
DATA_DIR    = os.path.join(PROJECT_DIR, "train-mock-data")

sys.path.insert(0, PROJECT_DIR)
from skeleton import config as cfg


def load(filename):
    with open(os.path.join(DATA_DIR, filename), encoding="utf-8") as f:
        return json.load(f)


def connect():
    return psycopg2.connect(
        host=cfg.PG_HOST,
        port=cfg.PG_PORT,
        dbname=cfg.PG_DB,
        user=cfg.PG_USER,
        password=cfg.PG_PASSWORD,
    )


def insert_many(cur, table, columns, rows):
    """Bulk insert with ON CONFLICT DO NOTHING. Returns row count inserted."""
    if not rows:
        return 0
    sql = (
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES %s "
        f"ON CONFLICT DO NOTHING"
    )
    execute_values(cur, sql, rows)
    return cur.rowcount


# ── seeders ──────────────────────────────────────────────────────────────────

def seed_metro_stations(cur):
    # Load metro station data and insert into metro_stations table.
    # Includes zone info and interchange flags for metro/national rail connections.
    data = load("metro_stations.json")
    table = "metro_stations"
    columns = ["station_id", "name", "zone", "is_interchange_metro", "is_interchange_national_rail", "interchange_rail_station_id"]
    
    rows = [(
        item["station_id"],
        item["name"],
        item.get("zone"),
        item.get("is_interchange_metro", False),
        item.get("is_interchange_national_rail", False),
        item.get("interchange_rail_station_id")
    ) for item in data]
    
    inserted = insert_many(cur, table, columns, rows)
    print(f"  -> Inserted {inserted} rows into {table}")


def seed_national_rail_stations(cur):
    # Load national rail station data and insert into national_rail_stations table.
    # Includes city, interchange flags, and linked metro station references.
    data = load("national_rail_stations.json")
    table = "national_rail_stations"
    columns = [
        "station_id", "name", "city", "is_interchange_metro", 
        "is_interchange_national_rail", "interchange_national_rail_station_lines", 
        "interchange_metro_station_id"
    ]
    
    rows = [(
        item["station_id"],
        item["name"],
        item.get("city"),
        item.get("is_interchange_metro", False),
        item.get("is_interchange_national_rail", False),
        item.get("interchange_national_rail_station_lines") or [],
        item.get("interchange_metro_station_id")
    ) for item in data]
    
    inserted = insert_many(cur, table, columns, rows)
    print(f"  -> Inserted {inserted} rows into {table}")

def seed_metro_schedules(cur):
    # Load metro schedule data and insert into metro_schedules and metro_schedule_stops.
    # Each schedule contains ordered stops which are extracted into a separate table.
    data = load("metro_schedules.json")

    schedule_table = "metro_schedules"
    schedule_columns = [
        "schedule_id",
        "line",
        "direction",
        "departure_time",
        "arrival_time",
        "frequency_min",
        "base_fare_usd",
        "per_stop_fare_usd",
    ]

    schedule_rows = []
    stop_rows = []

    for item in data:
        # Build one row per schedule
        schedule_rows.append(
            (
                item["schedule_id"],
                item["line"],
                item["direction"],
                item["first_train_time"],
                item["last_train_time"],
                item["frequency_min"],
                item["base_fare_usd"],
                item["per_stop_rate_usd"],
            )
        )
        # Build one row per stop, preserving stop order (1-indexed)
        for index, station_id in enumerate(item["stops_in_order"], start=1):
            stop_rows.append(
                (
                    item["schedule_id"],
                    station_id,
                    index,
                )
            )

    inserted = insert_many(cur, schedule_table, schedule_columns, schedule_rows)
    print(f"  -> Inserted {inserted} rows into {schedule_table}")

    inserted_stops = insert_many(
        cur,
        "metro_schedule_stops",
        ["schedule_id", "station_id", "stop_order"],
        stop_rows,
    )
    print(f"  -> Inserted {inserted_stops} rows into metro_schedule_stops")


def seed_national_rail_schedules(cur):
    # Load national rail schedule data and insert into three related tables:
    # national_rail_schedules, national_rail_schedule_stops, and national_rail_fare_classes.
    # Standard fare is stored directly on the schedule; all fare classes go into the fare class table.
    data = load("national_rail_schedules.json")

    schedule_table = "national_rail_schedules"
    schedule_columns = [
        "schedule_id",
        "line",
        "service_type",
        "direction",
        "departure_time",
        "arrival_time",
        "base_fare_usd",
        "per_stop_fare_usd",
    ]

    schedule_rows = []
    stop_rows = []
    fare_class_rows = []

    for item in data:
        # 1. Insert basic schedule data.
        # Because the real fare by class is stored in national_rail_fare_classes,
        # we store the standard fare here as the default fare.
        fare_classes = item.get("fare_classes", {})
        standard_fare = fare_classes.get("standard", {})

        # 1. Insert basic schedule data
        # Because the real fare by class is stored in national_rail_fare_classes,
        # we store the standard fare here as the default fare.
        schedule_rows.append(
            (
                item["schedule_id"],
                item["line"],
                item["service_type"],
                item["direction"],
                item["first_train_time"],
                item["last_train_time"],
                standard_fare.get("base_fare_usd", 0.00),
                standard_fare.get("per_stop_rate_usd", 0.00),
            )
        )

        # 2. Insert ordered stops
        for index, station_id in enumerate(item["stops_in_order"], start=1):
            stop_rows.append(
                (
                    item["schedule_id"],
                    station_id,
                    index,
                )
            )

        # 3. Insert fare class rows
        for fare_class, fare_info in fare_classes.items():
            fare_class_rows.append(
                (
                    item["schedule_id"],
                    fare_class,
                    fare_info.get("base_fare_usd", 0.00),
                    fare_info.get("per_stop_rate_usd", 0.00),
                )
            )

    inserted = insert_many(cur, schedule_table, schedule_columns, schedule_rows)
    print(f"  -> Inserted {inserted} rows into {schedule_table}")

    inserted_stops = insert_many(
        cur,
        "national_rail_schedule_stops",
        ["schedule_id", "station_id", "stop_order"],
        stop_rows,
    )
    print(f"  -> Inserted {inserted_stops} rows into national_rail_schedule_stops")

    inserted_fares = insert_many(
        cur,
        "national_rail_fare_classes",
        ["schedule_id", "fare_class", "base_fare_usd", "per_stop_fare_usd"],
        fare_class_rows,
    )
    print(f"  -> Inserted {inserted_fares} rows into national_rail_fare_classes")
    
def seed_seat_layouts(cur):
    # Load seat layout data and insert into three related tables:
    # national_rail_seat_layouts (top-level), national_rail_coaches (per coach),
    # and national_rail_seats (individual seats within each coach).
    data = load("national_rail_seat_layouts.json")

    layout_rows = []
    coach_rows = []
    seat_rows = []

    for item in data:
        layout_id = item["layout_id"]
        schedule_id = item["schedule_id"]

        # 1. national_rail_seat_layouts
        layout_rows.append(
            (
                layout_id,
                schedule_id,
            )
        )

        # 2. national_rail_coaches
        for coach_item in item.get("coaches", []):
            coach = coach_item["coach"]
            fare_class = coach_item["fare_class"]

            coach_rows.append(
                (
                    layout_id,
                    coach,
                    fare_class,
                )
            )

            # 3. national_rail_seats
            for seat in coach_item.get("seats", []):
                seat_rows.append(
                    (
                        seat["seat_id"],
                        layout_id,
                        coach,
                        seat["row"],
                        seat["column"],
                    )
                )

    inserted_layouts = insert_many(
        cur,
        "national_rail_seat_layouts",
        ["layout_id", "schedule_id"],
        layout_rows,
    )
    print(f"  -> Inserted {inserted_layouts} rows into national_rail_seat_layouts")

    inserted_coaches = insert_many(
        cur,
        "national_rail_coaches",
        ["layout_id", "coach", "fare_class"],
        coach_rows,
    )
    print(f"  -> Inserted {inserted_coaches} rows into national_rail_coaches")

    inserted_seats = insert_many(
        cur,
        "national_rail_seats",
        ["seat_id", "layout_id", "coach", "seat_row", "seat_column"],
        seat_rows,
    )
    print(f"  -> Inserted {inserted_seats} rows into national_rail_seats")

def seed_ticket_types(cur):
    data = load("ticket_types.json")

    ticket_rows = []
    rule_rows = []

    for item in data:
        ticket_rows.append(
            (
                item["ticket_type"],
                item["display_name"],
                item["available_on"],
                item.get("description"),
            )
        )

        for network in item.get("available_on", []):
            rule = item.get(network)
            if not rule:
                continue

            rule_rows.append(
                (
                    item["ticket_type"],
                    network,
                    rule.get("pricing_model", "unknown"),
                    rule.get("formula", ""),
                    rule.get("fare_classes"),
                    rule.get("seat_assignment", False),
                    rule.get("validity"),
                    rule.get("advance_purchase", False),
                    rule.get("advance_purchase_max_days"),
                    rule.get("changes_allowed", False),
                    rule.get("change_fee_usd"),
                    rule.get("change_deadline"),
                    rule.get("refundable", False),
                    rule.get("refund_rule"),
                )
            )

    inserted_tickets = insert_many(
        cur,
        "ticket_types",
        ["ticket_type", "display_name", "available_on", "description"],
        ticket_rows,
    )
    print(f"  -> Inserted {inserted_tickets} rows into ticket_types")

    inserted_rules = insert_many(
        cur,
        "ticket_type_rules",
        [
            "ticket_type",
            "network",
            "pricing_model",
            "formula",
            "fare_classes",
            "seat_assignment",
            "validity",
            "advance_purchase",
            "advance_purchase_max_days",
            "changes_allowed",
            "change_fee_usd",
            "change_deadline",
            "refundable",
            "refund_rules",
        ],
        rule_rows,
    )
    print(f"  -> Inserted {inserted_rules} rows into ticket_type_rules")

def seed_ticket_types(cur):
    # Load ticket type definitions and insert display name, available networks, and description.
    data = load("ticket_types.json")
    table = "ticket_types"
    columns = ["ticket_type", "display_name", "available_on", "description"]
    
    rows = [(
        item["ticket_type"],
        item.get("display_name", ""),
        item.get("available_on", []),
        item.get("description", "")
    ) for item in data]
    
    inserted = insert_many(cur, table, columns, rows)
    print(f"  -> Inserted {inserted} rows into {table}")

def seed_ticket_type_rules(cur):
    # Load ticket type rules and insert one row per (ticket_type, network) combination.
    # Handles both metro and national_rail rules separately from the same source file.
    data = load("ticket_types.json")
    table = "ticket_type_rules"
    columns = [
        "ticket_type", "network", "pricing_model", "formula", "fare_classes",
        "seat_assignment", "validity", "advance_purchase", "advance_purchase_max_days",
        "changes_allowed", "change_fee_usd", "change_deadline", "refundable", "refund_rules"
    ]
    
    rows = []
    for item in data:
        ticket_type = item["ticket_type"]
        
        # Process metro rules if available
        metro_rules = item.get("metro")
        if metro_rules:
            rows.append((
                ticket_type,
                "metro",
                metro_rules.get("pricing_model", ""),
                metro_rules.get("formula", ""),
                metro_rules.get("fare_classes", []),
                metro_rules.get("seat_assignment", False),
                metro_rules.get("validity", ""),
                metro_rules.get("advance_purchase", False),
                metro_rules.get("advance_purchase_max_days"),
                metro_rules.get("changes_allowed", False),
                metro_rules.get("change_fee_usd"),
                metro_rules.get("change_deadline"),
                metro_rules.get("refundable", False),
                metro_rules.get("refund_rule", "")
            ))
        
        # Process national_rail rules if available
        rail_rules = item.get("national_rail")
        if rail_rules:
            rows.append((
                ticket_type,
                "national_rail",
                rail_rules.get("pricing_model", ""),
                rail_rules.get("formula", ""),
                rail_rules.get("fare_classes", []),
                rail_rules.get("seat_assignment", False),
                rail_rules.get("validity", ""),
                rail_rules.get("advance_purchase", False),
                rail_rules.get("advance_purchase_max_days"),
                rail_rules.get("changes_allowed", False),
                rail_rules.get("change_fee_usd"),
                rail_rules.get("change_deadline"),
                rail_rules.get("refundable", False),
                rail_rules.get("refund_rule", "")
            ))
    
    inserted = insert_many(cur, table, columns, rows)
    print(f"  -> Inserted {inserted} rows into {table}")

def seed_users(cur):
    # Load registered user data and insert into registered_users table.
    # Handles variations in name fields (name vs first_name + surname).
    # Falls back to a default password if no password field is found.
    import hashlib
    
    data = load("registered_users.json")

    table = "registered_users"
    columns = [
        "user_id",
        "name",
        "email",
        "password_hash",
        "phone_number",
        "year_of_birth",
        "secret_question",
        "secret_answer",
        "is_active",
    ]

    rows = []

    for item in data:
        # Normalise name: prefer "name", fall back to "first_name" + "surname"
        name = item.get("name")

        if not name:
            first_name = item.get("first_name", "")
            surname = item.get("surname", "")
            name = f"{first_name} {surname}".strip()
        # Accept any password field variant; default if none found
        password_value = (
            item.get("password_hash")
            or item.get("password")
            or item.get("plain_password")
            or "password123"
        )

        rows.append(
            (
                item["user_id"],
                name,
                item["email"],
                password_value,
                item.get("phone_number"),
                item.get("year_of_birth"),
                item.get("secret_question"),
                item.get("secret_answer"),
                item.get("is_active", True),
            )
        )

    inserted = insert_many(cur, table, columns, rows)
    print(f"  -> Inserted {inserted} rows into {table}")
    #Return a user_id -> user_id identity map for use by dependent seeders
    return {item["user_id"]: item["user_id"] for item in data}

def seed_national_rail_bookings(cur, user_map):
    # Load booking data and insert into the bookings table.
    # Resolves layout_id from the schedule if not already present in the booking record.
    data = load("bookings.json")

    # schedule_id -> layout_id
    # Example: NR_SCH01 -> SL01
    cur.execute("""
        SELECT schedule_id, layout_id
        FROM national_rail_seat_layouts;
    """)
    schedule_layout_map = {
        schedule_id: layout_id
        for schedule_id, layout_id in cur.fetchall()
    }

    table = "bookings"
    columns = [
        "booking_id",
        "user_id",
        "schedule_id",
        "ticket_type",
        "layout_id",
        "coach",
        "seat_id",
        "fare_class",
        "amount_usd",
        "booking_date",
        "travel_date",
        "status",
    ]
    rows = []

    for item in data:
        user_id = user_map.get(item["user_id"], item["user_id"])
        schedule_id = item["schedule_id"]
        
        # Use layout_id from the record, or fall back to the schedule lookup
        layout_id = item.get("layout_id") or schedule_layout_map.get(schedule_id)

        if not layout_id:
            print(f"  !! Skipping booking {item['booking_id']}: no layout found for {schedule_id}")
            continue

        rows.append(
            (
                item["booking_id"],
                user_id,
                schedule_id,
                item.get("ticket_type", "single"),
                layout_id,
                item["coach"],
                item["seat_id"],
                item.get("fare_class", "standard"),
                item.get("amount_usd", 0.00),
                item.get("booked_at"),
                item["travel_date"],
                item.get("status", "confirmed"),
            )
        )

    inserted = insert_many(cur, table, columns, rows)
    print(f"  -> Inserted {inserted} rows into {table}")

def seed_metro_travels(cur, user_map):
    # Load metro travel history and insert into metro_travel_history table.
    # Maps purchased_at -> tap_in_time and travelled_at -> tap_out_time.
    # tap_out_time is only set for completed trips.
    data = load("metro_travel_history.json")

    table = "metro_travel_history"
    columns = [
        "trip_id",
        "user_id",
        "schedule_id",
        "entry_station_id",
        "exit_station_id",
        "ticket_type",
        "travel_date",
        "tap_in_time",
        "tap_out_time",
        "amount_usd",
        "status",
    ]

    rows = []

    for item in data:
        user_id = user_map.get(item["user_id"], item["user_id"])
        status = item.get("status", "completed")

        travelled_at = item.get("travelled_at")
        purchased_at = item.get("purchased_at")

        # tap_in_time is NOT NULL in schema.
        # Use purchased_at as the start time, and travelled_at as the end time.
        tap_in_time = purchased_at or travelled_at

        # For completed trips, schema requires tap_out_time and exit_station_id.
        tap_out_time = travelled_at if status == "completed" else None

        rows.append(
            (
                item["trip_id"],
                user_id,
                item.get("schedule_id"),
                item["origin_station_id"],
                item.get("destination_station_id"),
                item.get("ticket_type", "single"),
                item["travel_date"],
                tap_in_time,
                tap_out_time,
                item.get("amount_usd", 0.00),
                status,
            )
        )

    inserted = insert_many(cur, table, columns, rows)
    print(f"  -> Inserted {inserted} rows into {table}")

def seed_payments(cur):
    # Load payment data and insert into the payments table.
    # Resolves user_id by looking up the linked booking or metro trip.
    # Determines whether the source is a booking (BK prefix) or metro trip (MT prefix).
    data = load("payments.json")

    # booking_id -> user_id
    cur.execute("""
        SELECT booking_id, user_id
        FROM bookings;
    """)
    booking_user_map = {
        booking_id: user_id
        for booking_id, user_id in cur.fetchall()
    }

    # trip_id -> user_id
    cur.execute("""
        SELECT trip_id, user_id
        FROM metro_travel_history;
    """)
    trip_user_map = {
        trip_id: user_id
        for trip_id, user_id in cur.fetchall()
    }

    table = "payments"
    columns = [
        "payment_id",
        "user_id",
        "booking_id",
        "trip_id",
        "amount_usd",
        "payment_method",
        "payment_date",
        "payment_status",
    ]

    rows = []

    for item in data:
        source_id = item["booking_id"]

        # Route to bookings or metro trips based on ID prefix
        if source_id.startswith("BK"):
            booking_id = source_id
            trip_id = None
            user_id = booking_user_map.get(booking_id)
        elif source_id.startswith("MT"):
            booking_id = None
            trip_id = source_id
            user_id = trip_user_map.get(trip_id)
        else:
            print(f"  !! Skipping payment {item['payment_id']}: unknown source id {source_id}")
            continue

        if not user_id:
            print(f"  !! Skipping payment {item['payment_id']}: cannot determine user_id")
            continue

        rows.append(
            (
                item["payment_id"],
                user_id,
                booking_id,
                trip_id,
                item["amount_usd"],
                item.get("method", "unknown"),
                item.get("paid_at"),
                item.get("status", "paid"),
            )
        )

    inserted = insert_many(cur, table, columns, rows)
    print(f"  -> Inserted {inserted} rows into {table}")

def seed_feedback(cur, user_map):
    # Load feedback data and insert into the feedback table.
    # Resolves user_id from the linked booking or metro trip if not directly provided.
    # Handles both "comments" and "comment" field name variants.
    data = load("feedback.json")

    # booking_id -> user_id
    cur.execute("""
        SELECT booking_id, user_id
        FROM bookings;
    """)
    booking_user_map = {
        booking_id: user_id
        for booking_id, user_id in cur.fetchall()
    }

    # trip_id -> user_id
    cur.execute("""
        SELECT trip_id, user_id
        FROM metro_travel_history;
    """)
    trip_user_map = {
        trip_id: user_id
        for trip_id, user_id in cur.fetchall()
    }

    table = "feedback"
    columns = [
        "feedback_id",
        "user_id",
        "booking_id",
        "trip_id",
        "rating",
        "comments",
        "feedback_date",
    ]

    rows = []

    for item in data:
        source_id = item.get("booking_id") or item.get("trip_id")

        # Route to bookings or metro trips based on ID prefix
        if source_id.startswith("BK"):
            booking_id = source_id
            trip_id = None
            user_id = item.get("user_id") or booking_user_map.get(booking_id)

        elif source_id.startswith("MT"):
            booking_id = None
            trip_id = source_id
            user_id = item.get("user_id") or trip_user_map.get(trip_id)

        else:
            print(f"  !! Skipping feedback {item.get('feedback_id')}: unknown source id {source_id}")
            continue

        if not user_id:
            print(f"  !! Skipping feedback {item.get('feedback_id')}: cannot determine user_id")
            continue

        rows.append(
            (
                item["feedback_id"],
                user_map.get(user_id, user_id),
                booking_id,
                trip_id,
                item["rating"],
                item.get("comments") or item.get("comment"),
                item.get("feedback_date") or item.get("submitted_at") or item.get("created_at"),
            )
        )

    inserted = insert_many(cur, table, columns, rows)
    print(f"  -> Inserted {inserted} rows into {table}")

# ── main ─────────────────────────────────────────────────────────────────────

def main():
    print("Connecting to PostgreSQL...")
    conn = connect()
    conn.autocommit = False # Use explicit transaction so we can rollback on error
    cur = conn.cursor()

    try:
        print("Seeding tables (dependency order):")

        # Defer FK constraint checks so tables can be seeded in any order within the transaction
        cur.execute("SET CONSTRAINTS ALL DEFERRED;")
        # Seed reference/lookup tables first (no foreign key dependencies)
        seed_metro_stations(cur)
        seed_national_rail_stations(cur)
        seed_metro_schedules(cur)
        seed_national_rail_schedules(cur)
        seed_seat_layouts(cur)
        seed_ticket_types(cur)
        seed_ticket_type_rules(cur)
        
        # Seed users and capture the user_id map for dependent tables
        user_map =seed_users(cur)
        seed_ticket_types(cur)
        
        # Seed transactional tables that depend on users, schedules, and seats
        seed_national_rail_bookings(cur, user_map)
        seed_metro_travels(cur, user_map)

        # Seed payments after bookings and trips exist (for user_id resolution)
        seed_payments(cur)

        # Seed feedback last as it references both bookings and metro trips
        seed_feedback(cur, user_map)
        
        conn.commit()
        print("\nAll done. Database seeded successfully.")
    except Exception as e:
        # Roll back the entire transaction on any failure to keep the DB clean
        conn.rollback()
        print(f"\nError: {e}")
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
