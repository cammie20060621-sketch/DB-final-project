"""
TransitFlow — Neo4j Seeder
Run once after starting Docker:
    python skeleton/seed_neo4j.py

Loads station and network data from train-mock-data/:
  - metro_stations.json         — city metro stations and adjacencies
  - national_rail_stations.json — national rail stations and adjacencies

Design your graph schema (node labels, relationship types, properties)
based on the data in these files, then implement the seed() function below.
"""

import json
import os
import sys

sys.path.insert(0, ".")

from neo4j import GraphDatabase
from skeleton.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

_DATA_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "train-mock-data")
)


def _load(filename):
    with open(os.path.join(_DATA_DIR, filename), encoding="utf-8") as f:
        return json.load(f)


def seed():
    metro_stations = _load("metro_stations.json")
    rail_stations  = _load("national_rail_stations.json")

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    with driver.session() as session:

        session.run("MATCH (n) DETACH DELETE n")
        print("  Cleared existing graph data")

        # TODO: Design your node labels and create metro station nodes.
        # Each station has: station_id, name, lines, and interchange info.
        # See metro_stations.json for the full data structure.
        print("  Creating metro station nodes...")
        for station in metro_stations:
            # 依規範使用 snake_case，將單一站點資料包成參數傳入
            session.run(
                """
                MERGE (s:MetroStation {station_id: $station_id})
                SET s.name = $name,
                    s.lines = $lines,
                    s.is_interchange_national_rail = $is_interchange
                """,
                station_id=station["station_id"],
                name=station["name"],
                lines=station["lines"],
                is_interchange=station["is_interchange_national_rail"]
            )
        
        # TODO: Design your node labels and create national rail station nodes.
        # See national_rail_stations.json for the full data structure.
        print("  Creating national rail station nodes...")
        for station in rail_stations:
            session.run(
                """
                MERGE (s:RailStation {station_id: $station_id})
                SET s.name = $name
                """,
                station_id=station["station_id"],
                name=station["name"]
            )

        # TODO: Design your relationship types and create metro links.
        # Each station lists its adjacent_stations with line and travel_time_min.
        # Consider what properties to store on the relationship.
        print("  Creating metro relationships...")
        for station in metro_stations:
            for adj in station.get("adjacent_stations", []):
                session.run(
                    """
                    MATCH (from:MetroStation {station_id: $from_id})
                    MATCH (to:MetroStation {station_id: $to_id})
                    MERGE (from)-[r:METRO_LINK {line: $line}]->(to)
                    SET r.travel_time_min = $time
                    """,
                    from_id=station["station_id"],
                    to_id=adj["station_id"],
                    line=adj["line"],
                    time=adj["travel_time_min"]
                )

        # TODO: Design your relationship types and create national rail links.
    
        print("  Creating national rail relationships...")
        for station in rail_stations:
            for adj in station.get("adjacent_stations", []):
                session.run(
                    """
                    MATCH (from:RailStation {station_id: $from_id})
                    MATCH (to:RailStation {station_id: $to_id})
                    MERGE (from)-[r:RAIL_LINK {line: $line}]->(to)
                    SET r.travel_time_min = $time
                    """,
                    from_id=station["station_id"],
                    to_id=adj["station_id"],
                    line=adj["line"],
                    time=adj["travel_time_min"]
                )

        # TODO: Create interchange relationships between metro and rail stations.
        # Interchange info is in the is_interchange_national_rail field
        # of metro_stations.json.
        print("  Creating interchange relationships...")
        for station in metro_stations:
            # 如果該地鐵站標記了可以轉乘國鐵
            if station.get("is_interchange_national_rail"):
                # 這裡假設對應的國鐵站 ID 記錄在 'national_rail_station_id' 欄位中
                # 請根據 train-mock-data/metro_stations.json 的實際欄位微調
                rail_id = station.get("national_rail_station_id")
                if rail_id:
                    session.run(
                        """
                        MATCH (m:MetroStation {station_id: $metro_id})
                        MATCH (r:RailStation {station_id: $rail_id})
                        MERGE (m)-[:INTERCHANGE]->(r)
                        MERGE (r)-[:INTERCHANGE]->(m)
                        """,
                        metro_id=station["station_id"],
                        rail_id=rail_id
                    )

    driver.close()
    print("\nNeo4j graph seeded successfully.")
    print("   Open http://localhost:7475 to explore the graph.")


if __name__ == "__main__":
    print("Connecting to Neo4j...")
    seed()
