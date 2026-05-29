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
    data = load("metro_stations.json")
    # TODO: Design your table schema, then implement the INSERT logic here.
    # Each item in `data` is a dict — inspect the JSON to see available fields.
    data = load("metro_stations.json")
    table = "metro_stations"
    # 欄位名稱一律使用 snake_case，並與 schema.sql 保持一致
    columns = ["station_id", "name", "line", "latitude", "longitude"]
    rows = [
        (item["station_id"], item["name"], item["line"], item["latitude"], item["longitude"])
        for item in data
    ]
    
    inserted = insert_many(cur, table, columns, rows)
    print(f"  -> Inserted {inserted} rows into {table}")
    pass


def seed_national_rail_stations(cur):
    data = load("national_rail_stations.json")
    # TODO: Design your table schema, then implement the INSERT logic here.
    data = load("national_rail_stations.json")
    table = "national_rail_stations"
    columns = ["station_id", "name", "latitude", "longitude"]
    rows = [
        (item["station_id"], item["name"], item["latitude"], item["longitude"])
        for item in data
    ]
    
    inserted = insert_many(cur, table, columns, rows)
    print(f"  -> Inserted {inserted} rows into {table}")
    pass


def seed_metro_schedules(cur):
    data = load("metro_schedules.json")
    # TODO: Design your table schema, then implement the INSERT logic here.
    table = "metro_schedules"
    columns = ["schedule_id", "line", "station_id", "arrival_time", "departure_time"]

    rows = [
        (item["schedule_id"], item["line"], item["station_id"], item["arrival_time"], item["departure_time"])
        for item in data
    ]

    inserted = insert_many(cur, table, columns, rows)
    print(f"  -> Inserted {inserted} rows into {table}")
    pass


def seed_national_rail_schedules(cur):
    data = load("national_rail_schedules.json")
    # TODO: Design your table schema, then implement the INSERT logic here.
    table = "national_rail_schedules"
    columns = ["train_id", "route_id", "station_id", "arrival_time", "departure_time", "sequence_number"]

    rows = [
        (
            item["train_id"], 
            item["route_id"], 
            item["station_id"], 
            item["arrival_time"], 
            item["departure_time"], 
            item["sequence_number"]
        )
        for item in data
    ]

    inserted = insert_many(cur, table, columns, rows)
    print(f"  -> Inserted {inserted} rows into {table}")
    pass


def seed_seat_layouts(cur):
    data = load("national_rail_seat_layouts.json")
    # TODO: Design your table schema, then implement the INSERT logic here.
    table = "seat_layouts"
    columns = ["train_id", "carriage_number", "seat_number", "class_type", "is_window"]

    rows = [
        (item["train_id"], item["carriage_number"], item["seat_number"], item["class_type"], item["is_window"])
        for item in data
    ]

    inserted = insert_many(cur, table, columns, rows)
    print(f"  -> Inserted {inserted} rows into {table}")
    pass


def seed_users(cur):
    data = load("registered_users.json")
    # TODO: Design your table schema, then implement the INSERT logic here.
    table = "users"
    columns = ["email", "first_name", "surname", "year_of_birth", "password_hash"]
    rows = [
        (
            item["email"], 
            item["first_name"], 
            item["surname"], 
            item["year_of_birth"], 
            item["password_hash"]
        )
        for item in data
    ]
    inserted = insert_many(cur, table, columns, rows)
    print(f"  -> Inserted {inserted} rows into {table}")
    pass


def seed_national_rail_bookings(cur):
    data = load("bookings.json")
    # TODO: Design your table schema, then implement the INSERT logic here.

    table = "bookings"
    columns = ["booking_id", "user_id", "train_id", "origin_station", "destination_station", "seat_number", "fare", "booking_time", "status"]
    rows = [
        (
            item["booking_id"], 
            item["user_id"], 
            item["train_id"], 
            item["origin_station"], 
            item["destination_station"], 
            item["seat_number"], 
            item["fare"], 
            item["booking_time"], 
            item["status"]
        )
        for item in data
    ]

    inserted = insert_many(cur, table, columns, rows)
    print(f"  -> Inserted {inserted} rows into {table}")
    pass


def seed_metro_travels(cur):
    data = load("metro_travel_history.json")
    # TODO: Design your table schema, then implement the INSERT logic here.

    table = "metro_travels"
    columns = ["travel_id", "user_id", "tap_in_station", "tap_out_station", "tap_in_time", "tap_out_time", "fare"]

    rows = [
        (
            item["travel_id"], 
            item["user_id"], 
            item["tap_in_station"], 
            item["tap_out_station"], 
            item["tap_in_time"], 
            item["tap_out_time"], 
            item["fare"]
        )
        for item in data
    ]

    inserted = insert_many(cur, table, columns, rows)
    print(f"  -> Inserted {inserted} rows into {table}")
    pass


def seed_payments(cur):
    data = load("payments.json")
    # TODO: Design your table schema, then implement the INSERT logic here.
    table = "payments"
    columns = ["payment_id", "booking_id", "amount", "payment_method", "payment_time", "status"]

    rows = [
        (
            item["payment_id"], 
            item["booking_id"], 
            item["amount"], 
            item["payment_method"], 
            item["payment_time"], 
            item["status"]
        )
        for item in data
    ]

    inserted = insert_many(cur, table, columns, rows)
    print(f"  -> Inserted {inserted} rows into {table}")
    pass


def seed_feedback(cur):
    data = load("feedback.json")
    # TODO: Design your table schema, then implement the INSERT logic here.

    table = "feedback"
    columns = ["feedback_id", "user_id", "rating", "comment", "submitted_at"]

    rows = [
        (item["feedback_id"], item["user_id"], item["rating"], item["comment"], item["submitted_at"])
        for item in data
    ]

    inserted = insert_many(cur, table, columns, rows)
    print(f"  -> Inserted {inserted} rows into {table}")
    pass


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    print("Connecting to PostgreSQL...")
    conn = connect()
    conn.autocommit = False
    cur = conn.cursor()

    try:
        print("Seeding tables (dependency order):")
        seed_metro_stations(cur)
        seed_national_rail_stations(cur)
        seed_metro_schedules(cur)
        seed_national_rail_schedules(cur)
        seed_seat_layouts(cur)
        seed_users(cur)
        seed_national_rail_bookings(cur)
        seed_metro_travels(cur)
        seed_payments(cur)
        seed_feedback(cur)
        conn.commit()
        print("\nAll done. Database seeded successfully.")
    except Exception as e:
        conn.rollback()
        print(f"\nError: {e}")
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
