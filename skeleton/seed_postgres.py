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
        item.get("interchange_national_rail_lines"), # psycopg2 會自動轉為 PostgreSQL array
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
        item.get("first_train_time", "00:00"),
        item.get("last_train_time", "23:59"),
        item.get("frequency_min", 10),
        item.get("base_fare_usd", 0.00),
        item.get("per_stop_rate_usd", 0.00)
    ) for item in data]
    
    inserted_sched = insert_many(cur, table_sched, columns_sched, rows_sched)
    print(f"  -> Inserted {inserted_sched} rows into {table_sched}")

    # 2. 塞入中繼表 metro_schedule_stops (處理多個停靠站)
    table_stops = "metro_schedule_stops"
    columns_stops = ["schedule_id", "station_id", "stop_order"]
    
    rows_stops = []
    for item in data:
        # stops_in_order 是站點列表
        stops = item.get("stops_in_order", [])
        for idx, station_id in enumerate(stops, start=1):
            rows_stops.append((item["schedule_id"], station_id, idx))
            
    inserted_stops = insert_many(cur, table_stops, columns_stops, rows_stops)
    print(f"  -> Inserted {inserted_stops} rows into {table_stops}")


def seed_national_rail_schedules(cur):
    data = load("national_rail_schedules.json")
    
    # 1. 主表 national_rail_schedules (將 JSON 的 train_id 對應到 SQL 的 schedule_id)
    table_sched = "national_rail_schedules"
    columns_sched = ["schedule_id", "line", "service_type", "direction", "departure_time", "arrival_time", "base_fare_usd", "per_stop_fare_usd"]
    
    rows_sched = [(
        item["schedule_id"],
        item.get("line", "Unknown"),
        item.get("service_type", "normal"),
        item.get("direction", "Unknown"),
        item.get("first_train_time", "00:00"),
        item.get("last_train_time", "23:59"),
        item.get("fare_classes", {}).get("standard", {}).get("base_fare_usd", 0.00),
        item.get("fare_classes", {}).get("standard", {}).get("per_stop_rate_usd", 0.00)
    ) for item in data]
    
    inserted_sched = insert_many(cur, table_sched, columns_sched, rows_sched)
    print(f"  -> Inserted {inserted_sched} rows into {table_sched}")

    # 2. 中繼表 national_rail_schedule_stops
    table_stops = "national_rail_schedule_stops"
    columns_stops = ["schedule_id", "station_id", "stop_order"]
    
    rows_stops = []
    for item in data:
        stops = item.get("stops_in_order", [])
        # 根據 stops_in_order 的順序插入
        for idx, st_id in enumerate(stops, start=1):
            rows_stops.append((item["schedule_id"], st_id, idx))
            
    inserted_stops = insert_many(cur, table_stops, columns_stops, rows_stops)
    print(f"  -> Inserted {inserted_stops} rows into {table_stops}")
    
def seed_seat_layouts(cur):
    data = load("national_rail_seat_layouts.json")
    
    # 根據你的 schema.sql 分拆成三個表寫入
    # 1. national_rail_seat_layouts
    table_layouts = "national_rail_seat_layouts"
    columns_layouts = ["layout_id", "schedule_id"]
    
    rows_layouts = []
    rows_coaches = []
    rows_seats = []
    
    for layout_item in data:
        layout_id = layout_item["layout_id"]
        schedule_id = layout_item["schedule_id"]
        
        rows_layouts.append((layout_id, schedule_id))
        
        # 遍歷每個coach
        for coach_item in layout_item.get("coaches", []):
            coach = coach_item["coach"]
            fare_class = coach_item["fare_class"]
            
            rows_coaches.append((layout_id, coach, fare_class))
            
            # 遍歷每個座位
            for seat_item in coach_item.get("seats", []):
                seat_id = seat_item["seat_id"]
                seat_row = seat_item.get("row", 1)
                seat_col = seat_item.get("column", "A")
                
                rows_seats.append((seat_id, layout_id, coach, seat_row, seat_col))

    ins_layouts = insert_many(cur, table_layouts, columns_layouts, rows_layouts)
    ins_coaches = insert_many(cur, "national_rail_coaches", ["layout_id", "coach", "fare_class"], rows_coaches)
    ins_seats = insert_many(cur, "national_rail_seats", ["seat_id", "layout_id", "coach", "seat_row", "seat_column"], rows_seats)
    
    print(f"  -> Inserted {ins_layouts} layouts, {ins_coaches} coaches, {ins_seats} seats.")

def seed_ticket_types(cur):
    data = load("ticket_types.json")
    table = "ticket_types"
    columns = ["ticket_type", "display_name", "available_on", "description"]
    
    rows = [(
        item["ticket_type"],
        item.get("display_name", ""),
        item.get("available_on", []),  # psycopg2 會自動轉為 PostgreSQL array
        item.get("description", "")
    ) for item in data]
    
    inserted = insert_many(cur, table, columns, rows)
    print(f"  -> Inserted {inserted} rows into {table}")

def seed_ticket_type_rules(cur):
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
    import hashlib
    
    data = load("registered_users.json")
    table = "registered_users"
    columns = ["user_id", "name", "email", "password_hash", "phone_number", "year_of_birth", "secret_question", "secret_answer"]
    
    rows = []
    for item in data:
        user_id = item["user_id"]
        name = item.get("full_name", "")
        email = item["email"]
        # Hash the password for storage
        password = item.get("password", "")
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        phone_number = item.get("phone")
        
        # Extract year from date_of_birth (format: YYYY-MM-DD)
        dob = item.get("date_of_birth")
        year_of_birth = None
        if dob:
            try:
                year_of_birth = int(dob.split("-")[0])
            except (ValueError, IndexError):
                year_of_birth = None
        
        secret_question = item.get("secret_question")
        secret_answer = item.get("secret_answer")
        
        rows.append((user_id, name, email, password_hash, phone_number, year_of_birth, secret_question, secret_answer))
    
    inserted = insert_many(cur, table, columns, rows)
    print(f"  -> Inserted {inserted} rows into {table}")
    
    # 回傳 user_map 供後續表查詢關聯
    user_map = {item["user_id"]: item["user_id"] for item in data}
    return user_map

def seed_national_rail_bookings(cur, user_map):
    data = load("bookings.json")
    table = "bookings"
    columns = [
        "booking_id", "user_id", "schedule_id", "ticket_type", 
        "layout_id", "coach", "seat_id", "fare_class", 
        "amount_usd", "booking_date", "travel_date", "status"
    ]
    
    # 先載入layout信息以取得layout_id對應schedule_id的映射
    layout_data = load("national_rail_seat_layouts.json")
    schedule_to_layout = {}  # schedule_id -> layout_id
    for layout in layout_data:
        schedule_to_layout[layout["schedule_id"]] = layout["layout_id"]
    
    rows = []
    for item in data:
        u_id = item["user_id"]
        if u_id in user_map:
            schedule_id = item["schedule_id"]
            layout_id = schedule_to_layout.get(schedule_id, "SL01")  # Default fallback
            
            rows.append((
                item["booking_id"],
                u_id,
                schedule_id,
                item.get("ticket_type", "single"),
                layout_id,
                item.get("coach", "A"),
                item.get("seat_id", "A01"),
                item.get("fare_class", "standard"),
                item.get("amount_usd", 0.00),
                item.get("booked_at", None),
                item.get("travel_date", "2026-06-01"),
                item.get("status", "confirmed")
            ))
            
    inserted = insert_many(cur, table, columns, rows)
    print(f"  -> Inserted {inserted} rows into {table}")

def seed_metro_travels(cur, user_map):
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
            # 如果tap_in_time為null，使用travel_date作為默認值
            tap_in_time = item.get("purchased_at")
            if not tap_in_time:
                tap_in_time = f"{item.get('travel_date', '2026-06-01')}T00:00:00Z"
            
            rows.append((
                item["trip_id"],
                u_id,
                item.get("schedule_id"),
                item["origin_station_id"],
                item.get("destination_station_id"),
                item.get("ticket_type", "single"),
                item.get("travel_date", "2026-06-01"),
                tap_in_time,
                item.get("travelled_at"),
                item.get("amount_usd", 0.00),
                item.get("status", "completed")
            ))
            
    inserted = insert_many(cur, table, columns, rows)
    print(f"  -> Inserted {inserted} rows into {table}")

def seed_payments(cur):
    data = load("payments.json")
    table = "payments"
    columns = ["payment_id", "user_id", "booking_id", "trip_id", "amount_usd", "payment_method", "payment_date", "payment_status"]
    
    # 建立booking_id和trip_id到user_id的映射
    bookings_data = load("bookings.json")
    booking_to_user = {item["booking_id"]: item["user_id"] for item in bookings_data}
    
    travels_data = load("metro_travel_history.json")
    trip_to_user = {item["trip_id"]: item["user_id"] for item in travels_data}
    
    rows = []
    for item in data:
        payment_id = item["payment_id"]
        amount_usd = item.get("amount_usd", 0.00)
        payment_method = item.get("method", "unknown")
        payment_date = item.get("paid_at")
        payment_status = item.get("status", "pending")
        booking_id = item.get("booking_id")
        
        # 確定這是booking還是trip
        user_id = None
        trip_id = None
        
        if booking_id.startswith("BK"):
            # 這是booking
            user_id = booking_to_user.get(booking_id)
            trip_id = None
        elif booking_id.startswith("MT"):
            # 這是metro travel trip
            user_id = trip_to_user.get(booking_id)
            trip_id = booking_id
            booking_id = None
        
        if user_id:
            rows.append((payment_id, user_id, booking_id, trip_id, amount_usd, payment_method, payment_date, payment_status))
    
    inserted = insert_many(cur, table, columns, rows)
    print(f"  -> Inserted {inserted} rows into {table}")

def seed_feedback(cur, user_map):
    data = load("feedback.json")
    table = "feedback"
    columns = ["feedback_id", "user_id", "booking_id", "rating", "comments", "feedback_date"]
    
    rows = []
    for item in data:
        u_id = item["user_id"]
        booking_id = item.get("booking_id")
        
        # 只插入booking_id是BK開頭的反饋（因為schema的feedback表只支持booking_id）
        if u_id in user_map and booking_id and booking_id.startswith("BK"):
            rows.append((
                item["feedback_id"],
                u_id,
                booking_id,
                item.get("rating", 5),
                item.get("comment"),  # comments
                item.get("submitted_at")  # feedback_date
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
        seed_ticket_types(cur)
        seed_ticket_type_rules(cur)
        
        user_map = seed_users(cur)
        
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
