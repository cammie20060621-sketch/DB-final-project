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
        item.get("interchange_national_rail_station_lines"), # psycopg2 會自動轉為 PostgreSQL array
        item.get("interchange_metro_station_id")
    ) for item in data]
    
    inserted = insert_many(cur, table, columns, rows)
    print(f"  -> Inserted {inserted} rows into {table}")

def seed_metro_schedules(cur):
    data = load("metro_schedules.json")
    
    # 1. 塞入主表 metro_schedules
    table_sched = "metro_schedules"
    columns_sched = ["schedule_id", "line", "direction", "departure_time", "arrival_time", "frequency_min", "base_fare_usd", "per_stop_fare_usd"]
    
    # 這裡假設你的 JSON 資料中含有 direction, frequency_min 等欄位，若無則給 default
    rows_sched = [(
        item["schedule_id"],
        item["line"],
        item.get("direction", "Unknown"),
        item["departure_time"],
        item["arrival_time"],
        item.get("frequency_min", 10),
        item.get("base_fare_usd", 0.00),
        item.get("per_stop_fare_usd", 0.00)
    ) for item in data]
    
    inserted_sched = insert_many(cur, table_sched, columns_sched, rows_sched)
    print(f"  -> Inserted {inserted_sched} rows into {table_sched}")

    # 2. 塞入中繼表 metro_schedule_stops (處理多個停靠站)
    table_stops = "metro_schedule_stops"
    columns_stops = ["schedule_id", "station_id", "stop_order"]
    
    rows_stops = []
    for item in data:
        # 如果 JSON 裡的 station_id 是一個陣列/清單則拆開，若是單一值則給 order 1
        stations = item["station_id"] if isinstance(item["station_id"], list) else [item["station_id"]]
        for idx, st_id in enumerate(stations, start=1):
            rows_stops.append((item["schedule_id"], st_id, idx))
            
    inserted_stops = insert_many(cur, table_stops, columns_stops, rows_stops)
    print(f"  -> Inserted {inserted_stops} rows into {table_stops}")


def seed_national_rail_schedules(cur):
    data = load("national_rail_schedules.json")
    
    # 1. 主表 national_rail_schedules (將 JSON 的 train_id 對應到 SQL 的 schedule_id)
    table_sched = "national_rail_schedules"
    columns_sched = ["schedule_id", "line", "service_type", "direction", "departure_time", "arrival_time", "base_fare_usd", "per_stop_fare_usd"]
    
    rows_sched = [(
        item["train_id"], # JSON 的 train_id 映射為 schedule_id
        item.get("line", item.get("route_id", "Unknown")),
        item.get("service_type", "normal"),
        item.get("direction", "Unknown"),
        item["departure_time"],
        item["arrival_time"],
        item.get("base_fare_usd", 0.00),
        item.get("per_stop_fare_usd", 0.00)
    ) for item in data]
    
    inserted_sched = insert_many(cur, table_sched, columns_sched, rows_sched)
    print(f"  -> Inserted {inserted_sched} rows into {table_sched}")

    # 2. 中繼表 national_rail_schedule_stops
    table_stops = "national_rail_schedule_stops"
    columns_stops = ["schedule_id", "station_id", "stop_order"]
    
    rows_stops = []
    for item in data:
        stations = item["station_id"] if isinstance(item["station_id"], list) else [item["station_id"]]
        # 如果 JSON 本身有 sequence_number 就用它，沒有就用 enumerate 產出
        for idx, st_id in enumerate(stations, start=1):
            seq = item.get("sequence_number", idx)
            rows_stops.append((item["train_id"], st_id, seq))
            
    inserted_stops = insert_many(cur, table_stops, columns_stops, rows_stops)
    print(f"  -> Inserted {inserted_stops} rows into {table_stops}")
    
def seed_seat_layouts(cur):
    data = load("national_rail_seat_layouts.json")
    
    # 根據你的 schema.sql 分拆成三個表寫入
    # 1. national_rail_seat_layouts
    table_layouts = "national_rail_seat_layouts"
    columns_layouts = ["layout_id", "schedule_id"]
    
    # 建立 layout_id（JSON內通常若無個別ID，可以複合或用 layout_ 拼接，這裡假設 JSON 欄位或拿 train_id 當 layout_id）
    rows_layouts = []
    rows_coaches = []
    rows_seats = []
    
    # 用於防重
    seen_layouts = set()
    seen_coaches = set()

    for item in data:
        # 配合 schema 的 FK 串接邏輯
        layout_id = item.get("layout_id", f"layout_{item['train_id']}")
        sched_id = item["train_id"] # 對應到 national_rail_schedules 的主鍵
        coach_id = item["carriage_number"]
        fare_class = item["class_type"]
        seat_id = item["seat_number"]
        
        # 解析座位 Row 和 Column (例如 "12A" -> row=12, col='A')
        seat_row = int(''.join(filter(str.isdigit, seat_id)))
        seat_col = ''.join(filter(str.isalpha, seat_id)).upper()

        if layout_id not in seen_layouts:
            rows_layouts.append((layout_id, sched_id))
            seen_layouts.add(layout_id)
            
        if (layout_id, coach_id) not in seen_coaches:
            rows_coaches.append((layout_id, coach_id, fare_class))
            seen_coaches.add((layout_id, coach_id))
            
        rows_seats.append((seat_id, layout_id, coach_id, seat_row, seat_col))

    ins_layouts = insert_many(cur, table_layouts, columns_layouts, rows_layouts)
    ins_coaches = insert_many(cur, "national_rail_coaches", ["layout_id", "coach", "fare_class"], rows_coaches)
    ins_seats = insert_many(cur, "national_rail_seats", ["seat_id", "layout_id", "coach", "seat_row", "seat_column"], rows_seats)
    
    print(f"  -> Inserted {ins_layouts} layouts, {ins_coaches} coaches, {ins_seats} seats.")

def seed_users(cur):
    data = load("registered_users.json")
    table = "registered_users"
    columns = ["user_id", "name", "email", "password_hash", "phone_number", "year_of_birth", "secret_question", "secret_answer"]
    
    rows = [(
        item["user_id"],
        item.get("name", f"{item.get('first_name', '')} {item.get('surname', '')}".strip()),
        item["email"],
        item["password_hash"],
        item.get("phone_number"),
        item.get("year_of_birth"),
        item.get("secret_question"),
        item.get("secret_answer")
    ) for item in data]
    
    inserted = insert_many(cur, table, columns, rows)
    print(f"  -> Inserted {inserted} rows into {table}")
    
    # 回傳 user_map 供後續表查詢關聯
    user_map = {item["user_id"]: item["user_id"] for item in data}
    return user_map

def seed_national_rail_bookings(cur,user_map):
    data = load("bookings.json")
    table = "bookings"
    columns = [
        "booking_id", "user_id", "schedule_id", "ticket_type", 
        "layout_id", "coach", "seat_id", "fare_class", 
        "amount_usd", "booking_date", "travel_date", "status"
    ]
    
    rows = []
    for item in data:
        u_id = item["user_id"]
        if u_id in user_map:
            # 配合 seat_layouts 的邏輯建立複合欄位預期
            layout_id = item.get("layout_id", f"layout_{item['train_id']}")
            rows.append((
                item["booking_id"],
                u_id,
                item["train_id"], # schedule_id
                item.get("ticket_type", "Advance Standard"),
                layout_id,
                item.get("carriage_number", "A"),
                item["seat_number"], # seat_id
                item.get("fare_class", "standard"),
                item.get("fare", 0.00), # amount_usd
                item.get("booking_time"), # booking_date
                item.get("travel_date", "2026-06-01"),
                item["status"]
            ))
            
    inserted = insert_many(cur, table, columns, rows)
    print(f"  -> Inserted {inserted} rows into {table}")

def seed_metro_travels(cur,user_map):
    data = load("metro_travel_history.json")
    table = "metro_travel_history"
    columns = [
        "trip_id", "user_id", "schedule_id", "entry_station_id", 
        "exit_station_id", "ticket_type", "travel_date", 
        "tap_in_time", "tap_out_time", "amount_usd", "status"
    ]
    
    rows = []
    for item in data:
        u_id = item["user_id"]
        if u_id in user_map:
            rows.append((
                item["travel_id"], # trip_id
                u_id,
                item.get("schedule_id"),
                item["tap_in_station"], # entry_station_id
                item.get("tap_out_station"), # exit_station_id
                item.get("ticket_type", "Pay As You Go"),
                item.get("travel_date", "2026-06-01"),
                item["tap_in_time"],
                item.get("tap_out_time"),
                item.get("fare", 0.00), # amount_usd
                item.get("status", "completed")
            ))
            
    inserted = insert_many(cur, table, columns, rows)
    print(f"  -> Inserted {inserted} rows into {table}")

def seed_payments(cur):
    data = load("payments.json")
    table = "payments"
    columns = ["payment_id", "user_id", "booking_id", "trip_id", "amount_usd", "payment_method", "payment_date", "payment_status"]
    
    rows = [(
        item["payment_id"],
        item["user_id"],
        item.get("booking_id"),
        item.get("travel_id"), # 對應到 schema.sql 的 trip_id
        item["amount"], # amount_usd
        item["payment_method"],
        item["payment_time"], # payment_date
        item.get("status", "paid") # payment_status
    ) for item in data]
    
    inserted = insert_many(cur, table, columns, rows)
    print(f"  -> Inserted {inserted} rows into {table}")

def seed_feedback(cur,user_map):
    data = load("feedback.json")
    table = "feedback"
    columns = ["feedback_id", "user_id", "booking_id", "rating", "comments", "feedback_date"]
    
    rows = []
    for item in data:
        u_id = item["user_id"]
        if u_id in user_map:
            rows.append((
                item["feedback_id"],
                u_id,
                item["booking_id"],
                item["rating"],
                item.get("comment"), # comments
                item.get("submitted_at") # feedback_date
            ))
            
    inserted = insert_many(cur, table, columns, rows)
    print(f"  -> Inserted {inserted} rows into {table}")

# ── main ─────────────────────────────────────────────────────────────────────

def main():
    print("Connecting to PostgreSQL...")
    conn = connect()
    conn.autocommit = False
    cur = conn.cursor()

    try:
        print("Seeding tables (dependency order):")
        cur.execute("SET CONSTRAINTS ALL DEFERRED;")
        seed_metro_stations(cur)
        seed_national_rail_stations(cur)
        seed_metro_schedules(cur)
        seed_national_rail_schedules(cur)
        seed_seat_layouts(cur)
        
        user_map =seed_users(cur)
        
        seed_national_rail_bookings(cur, user_map)
        seed_metro_travels(cur, user_map)
        seed_payments(cur)
        seed_feedback(cur, user_map)
        
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
