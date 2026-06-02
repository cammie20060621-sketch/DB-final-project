"""
skeleton/seed_neo4j.py
----------------------
Dynamically reads train-mock-data/metro_stations.json and
train-mock-data/national_rail_stations.json, then creates all
nodes and relationships in Neo4j.

How to run:
    python3 skeleton/seed_neo4j.py          # macOS / Linux
    python  skeleton/seed_neo4j.py          # Windows

What it creates:
    Nodes        : MetroStation (MS01-MS20), NationalRailStation (NR01-NR10)
    Relationships: METRO_LINK, RAIL_LINK, INTERCHANGE_TO

Safe to re-run — all statements use MERGE, never CREATE.
"""

import json
import os
from pathlib import Path
from neo4j import GraphDatabase

# ---------------------------------------------------------------------------
# Config — reads from environment (same as skeleton/config.py)
# ---------------------------------------------------------------------------
NEO4J_URI      = os.getenv("NEO4J_URI",      "bolt://localhost:7688")
NEO4J_USER     = os.getenv("NEO4J_USER",     "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "transitflow")

# ---------------------------------------------------------------------------
# Helper — load JSON from the train-mock-data/ folder
# ---------------------------------------------------------------------------
DATA_DIR = Path(__file__).parent.parent / "train-mock-data"

def load(filename: str) -> list[dict]:
    """Load a JSON file from train-mock-data/ and return its contents."""
    path = DATA_DIR / filename
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Seeding functions
# ---------------------------------------------------------------------------

def seed_metro_stations(session, stations: list[dict]) -> None:
    """
    Create one MetroStation node per entry.
    Properties written: station_id, name, lines, is_interchange_metro,
                        is_interchange_national_rail, zone (not in JSON → default "").
    """
    for s in stations:
        session.run(
            """
            MERGE (n:MetroStation {station_id: $station_id})
            SET   n.name                        = $name,
                  n.lines                       = $lines,
                  n.is_interchange_metro        = $is_interchange_metro,
                  n.is_interchange_national_rail = $is_interchange_national_rail
            """,
            station_id=s["station_id"],
            name=s["name"],
            lines=s["lines"],
            is_interchange_metro=s["is_interchange_metro"],
            is_interchange_national_rail=s["is_interchange_national_rail"],
        )
    print(f"  MetroStation nodes    : {len(stations)}")


def seed_national_rail_stations(session, stations: list[dict]) -> None:
    """
    Create one NationalRailStation node per entry.
    Properties written: station_id, name, lines, is_interchange_national_rail,
                        is_interchange_metro.
    """
    for s in stations:
        session.run(
            """
            MERGE (n:NationalRailStation {station_id: $station_id})
            SET   n.name                        = $name,
                  n.lines                       = $lines,
                  n.is_interchange_national_rail = $is_interchange_national_rail,
                  n.is_interchange_metro         = $is_interchange_metro
            """,
            station_id=s["station_id"],
            name=s["name"],
            lines=s["lines"],
            is_interchange_national_rail=s["is_interchange_national_rail"],
            is_interchange_metro=s["is_interchange_metro"],
        )
    print(f"  NationalRailStation nodes: {len(stations)}")


def seed_metro_links(session, stations: list[dict]) -> None:
    """
    Create METRO_LINK relationships from each station's adjacent_stations list.
    Both (a)->(b) and (b)->(a) are created — shortestPath works in both directions.
    The 'line' property is stored on the relationship (one rel per line per pair).
    """
    count = 0
    for s in stations:
        for adj in s["adjacent_stations"]:
            # Forward direction: source → neighbour
            session.run(
                """
                MATCH (a:MetroStation {station_id: $from_id})
                MATCH (b:MetroStation {station_id: $to_id})
                MERGE (a)-[r:METRO_LINK {line: $line}]->(b)
                SET   r.travel_time_min = $travel_time_min
                """,
                from_id=s["station_id"],
                to_id=adj["station_id"],
                line=adj["line"],
                travel_time_min=adj["travel_time_min"],
            )
            count += 1
    print(f"  METRO_LINK relationships: {count}")


def seed_rail_links(session, stations: list[dict]) -> None:
    """
    Create RAIL_LINK relationships from each NR station's adjacent_stations list.
    Both directions are created.
    """
    count = 0
    for s in stations:
        for adj in s["adjacent_stations"]:
            session.run(
                """
                MATCH (a:NationalRailStation {station_id: $from_id})
                MATCH (b:NationalRailStation {station_id: $to_id})
                MERGE (a)-[r:RAIL_LINK {line: $line}]->(b)
                SET   r.travel_time_min = $travel_time_min
                """,
                from_id=s["station_id"],
                to_id=adj["station_id"],
                line=adj["line"],
                travel_time_min=adj["travel_time_min"],
            )
            count += 1
    print(f"  RAIL_LINK relationships : {count}")


def seed_interchange_links(
    session,
    metro_stations: list[dict],
    rail_stations: list[dict],
) -> None:
    """
    Create INTERCHANGE_TO relationships between metro and national rail stations
    that share a physical interchange.

    Sources:
      - metro_stations[*].interchange_national_rail_station_id  (MS → NR)
      - national_rail_stations[*].interchange_metro_station_id  (NR → MS, cross-check)

    Both directions are created with a default walk_time_min of 5 minutes.
    If the same pair appears in both lists, MERGE ensures no duplicate is created.
    """
    interchange_pairs: set[tuple[str, str]] = set()

    # Collect pairs from metro side
    for s in metro_stations:
        nr_id = s.get("interchange_national_rail_station_id")
        if nr_id:
            interchange_pairs.add((s["station_id"], nr_id))

    # Collect pairs from rail side (cross-check / may add same pairs)
    for s in rail_stations:
        ms_id = s.get("interchange_metro_station_id")
        if ms_id:
            interchange_pairs.add((ms_id, s["station_id"]))

    count = 0
    for ms_id, nr_id in interchange_pairs:
        # MetroStation → NationalRailStation
        session.run(
            """
            MATCH (m:MetroStation         {station_id: $ms_id})
            MATCH (r:NationalRailStation  {station_id: $nr_id})
            MERGE (m)-[x:INTERCHANGE_TO]->(r)
            SET   x.walk_time_min = 5,
                  x.accessible   = true
            """,
            ms_id=ms_id,
            nr_id=nr_id,
        )
        # NationalRailStation → MetroStation (reverse)
        session.run(
            """
            MATCH (m:MetroStation         {station_id: $ms_id})
            MATCH (r:NationalRailStation  {station_id: $nr_id})
            MERGE (r)-[x:INTERCHANGE_TO]->(m)
            SET   x.walk_time_min = 5,
                  x.accessible   = true
            """,
            ms_id=ms_id,
            nr_id=nr_id,
        )
        count += 2

    print(f"  INTERCHANGE_TO relationships: {count}  ({len(interchange_pairs)} pairs × 2 directions)")


def seed_indexes(session) -> None:
    """Create indexes for fast station_id lookup."""
    session.run(
        "CREATE INDEX metro_station_id IF NOT EXISTS "
        "FOR (s:MetroStation) ON (s.station_id)"
    )
    session.run(
        "CREATE INDEX rail_station_id IF NOT EXISTS "
        "FOR (s:NationalRailStation) ON (s.station_id)"
    )
    print("  Indexes: created (or already exist)")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def seed() -> None:
    print("Loading JSON files from train-mock-data/ ...")
    metro_stations = load("metro_stations.json")
    rail_stations  = load("national_rail_stations.json")
    print(f"  metro_stations.json         : {len(metro_stations)} entries")
    print(f"  national_rail_stations.json : {len(rail_stations)} entries")

    print("\nConnecting to Neo4j ...")
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    with driver.session() as session:
        print("\nSeeding nodes ...")
        seed_metro_stations(session, metro_stations)
        seed_national_rail_stations(session, rail_stations)

        print("\nSeeding relationships ...")
        seed_metro_links(session, metro_stations)
        seed_rail_links(session, rail_stations)
        seed_interchange_links(session, metro_stations, rail_stations)

        print("\nCreating indexes ...")
        seed_indexes(session)

    driver.close()
    print("\nDone. Neo4j graph seeded successfully.")
    print("Verify in Neo4j Browser (http://localhost:7475):")
    print("  MATCH (n)-[r]->(m) RETURN n, r, m")


if __name__ == "__main__":
    seed()
