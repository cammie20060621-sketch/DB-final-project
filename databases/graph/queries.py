"""
databases/graph/queries.py
--------------------------
All Neo4j query functions for the TransitFlow graph database.

Graph schema (matches seed_neo4j.py):
  Node labels  : MetroStation        {station_id, name, lines[], is_interchange_metro,
                                       is_interchange_national_rail}
                 NationalRailStation  {station_id, name, lines[], is_interchange_metro,
                                       is_interchange_national_rail}

  Relationships: METRO_LINK     {line, travel_time_min}   — metro adjacency
                 RAIL_LINK      {line, travel_time_min}   — national rail adjacency
                 INTERCHANGE_TO {walk_time_min, accessible}— cross-network walk

Connection pattern used by every function:
    with _driver() as driver:
        with driver.session() as session:
            result = session.run("MATCH ...", param=value)
            return [dict(record) for record in result]

Return contract:
  - Read functions return list[dict] or dict.
  - Never raise for "not found" — return [] or {"found": False, ...}.
"""

from __future__ import annotations
import os
from neo4j import GraphDatabase

# ---------------------------------------------------------------------------
# Config  (mirrors skeleton/config.py — change there, not here)
# ---------------------------------------------------------------------------
NEO4J_URI      = os.getenv("NEO4J_URI",      "bolt://localhost:7688")
NEO4J_USER     = os.getenv("NEO4J_USER",     "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "transitflow")


def _driver():
    """Return an authenticated Neo4j driver. Always use as a context manager."""
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


# ===========================================================================
# 1. query_line_stations
#    NEW — return all stations served by a specific line, ordered along the line.
# ===========================================================================

def query_line_stations(line_id: str) -> list[dict]:
    """
    Return all stations served by a given line, ordered by their sequence
    along the line (fewest hops from the first station encountered).

    Works for both metro lines (M1, M2, M3, M4) and national rail lines
    (NR1, NR2).  The line_id must match the 'line' property stored on
    METRO_LINK / RAIL_LINK relationships.

    Args:
        line_id: e.g. "M1", "M2", "NR1", "NR2"

    Returns:
        List of dicts, each with:
            station_id   (str)
            name         (str)
            label        (str  — "MetroStation" or "NationalRailStation")
            sequence     (int  — hop count from the first node, 0-based)
        Sorted by sequence ascending.
        Returns [] if no stations match the line.

    Example:
        query_line_stations("M1")
        # → [{station_id:"MS20", name:"Thornton",       sequence:0},
        #    {station_id:"MS05", name:"Westfield",       sequence:1},
        #    {station_id:"MS01", name:"Central Square",  sequence:2}, ...]
    """
    # Detect network from line prefix so we query only the relevant rel type
    if line_id.startswith("NR"):
        rel_type = "RAIL_LINK"
    else:
        rel_type = "METRO_LINK"

    cypher = f"""
    // Find one end-station of the line (degree 1 on this line = terminus)
    MATCH (terminus)-[r:{rel_type} {{line: $line_id}}]-()
    WITH terminus, count(r) AS degree
    ORDER BY degree ASC
    LIMIT 1

    // Walk the line from that terminus, collecting nodes in order
    MATCH path = (terminus)-[:{rel_type}* {{line: $line_id}}]-(other)
    WITH other, min(length(path)) AS sequence
    RETURN
        other.station_id    AS station_id,
        other.name          AS name,
        labels(other)[0]    AS label,
        sequence
    UNION
    // Also include the terminus itself (sequence 0)
    MATCH (terminus)-[r:{rel_type} {{line: $line_id}}]-()
    WITH terminus, count(r) AS degree
    ORDER BY degree ASC
    LIMIT 1
    RETURN
        terminus.station_id AS station_id,
        terminus.name       AS name,
        labels(terminus)[0] AS label,
        0                   AS sequence
    ORDER BY sequence ASC
    """

    with _driver() as driver:
        with driver.session() as session:
            result = session.run(cypher, line_id=line_id)
            rows = [dict(record) for record in result]

    # De-duplicate (UNION may return the terminus twice) and sort
    seen = {}
    for row in rows:
        sid = row["station_id"]
        if sid not in seen or row["sequence"] < seen[sid]["sequence"]:
            seen[sid] = row
    return sorted(seen.values(), key=lambda r: r["sequence"])


# ===========================================================================
# 2. query_shortest_route
#    Fastest path between any two stations (metro, rail, or cross-network).
# ===========================================================================

def query_shortest_route(
    origin_id: str,
    destination_id: str,
    network: str = "auto",
) -> dict:
    """
    Find the shortest (fastest) route between any two stations.

    Args:
        origin_id:      Station ID, e.g. "MS01" or "NR01".
        destination_id: Station ID, e.g. "MS14" or "NR05".
        network:        "metro"  — metro only (METRO_LINK)
                        "rail"   — national rail only (RAIL_LINK)
                        "auto"   — any link including interchanges (default)

    Returns:
        dict with keys:
            found      (bool)
            total_time (int, minutes — sum of travel_time_min / walk_time_min)
            path       (list of dicts: station_id, name, label)
        Returns {"found": False, "total_time": None, "path": []} if no route.
    """
    if network == "metro":
        rel_filter = "METRO_LINK"
    elif network == "rail":
        rel_filter = "RAIL_LINK"
    else:
        rel_filter = "METRO_LINK|RAIL_LINK|INTERCHANGE_TO"

    cypher = f"""
    MATCH (origin  WHERE origin.station_id  = $origin_id)
    MATCH (dest    WHERE dest.station_id    = $destination_id)
    MATCH p = shortestPath((origin)-[:{rel_filter}*]-(dest))
    WITH p,
         reduce(t = 0, r IN relationships(p) |
             t + coalesce(r.travel_time_min, r.walk_time_min, 0)
         ) AS total_time
    RETURN
        [node IN nodes(p) | {{
            station_id : node.station_id,
            name       : node.name,
            label      : labels(node)[0]
        }}] AS path,
        total_time
    ORDER BY total_time ASC
    LIMIT 1
    """

    with _driver() as driver:
        with driver.session() as session:
            result = session.run(
                cypher,
                origin_id=origin_id,
                destination_id=destination_id,
            )
            row = result.single()

    if row is None:
        return {"found": False, "total_time": None, "path": []}
    return {
        "found": True,
        "total_time": row["total_time"],
        "path": list(row["path"]),
    }


# ===========================================================================
# 3. query_cheapest_route
#    Route with lowest hop count (fewest stops → lower fare proxy).
# ===========================================================================

def query_cheapest_route(
    origin_id: str,
    destination_id: str,
    network: str = "auto",
    fare_class: str = "standard",
) -> dict:
    """
    Find the route with the fewest intermediate stops (cheapest fare proxy).

    Args:
        origin_id:      Station ID for journey start.
        destination_id: Station ID for journey end.
        network:        "metro", "rail", or "auto".
        fare_class:     Passed through for context only.

    Returns:
        dict with keys:
            found       (bool)
            stops       (int  — number of intermediate stations)
            total_time  (int  — total minutes)
            fare_class  (str)
            path        (list of dicts: station_id, name, label)
        Returns {"found": False} if no route exists.
    """
    if network == "metro":
        rel_filter = "METRO_LINK"
    elif network == "rail":
        rel_filter = "RAIL_LINK"
    else:
        rel_filter = "METRO_LINK|RAIL_LINK|INTERCHANGE_TO"

    cypher = f"""
    MATCH (origin WHERE origin.station_id = $origin_id)
    MATCH (dest   WHERE dest.station_id   = $destination_id)
    MATCH p = shortestPath((origin)-[:{rel_filter}*]-(dest))
    WITH p,
         length(p) - 1 AS stops,
         reduce(t = 0, r IN relationships(p) |
             t + coalesce(r.travel_time_min, r.walk_time_min, 0)
         ) AS total_time
    RETURN
        [node IN nodes(p) | {{
            station_id : node.station_id,
            name       : node.name,
            label      : labels(node)[0]
        }}] AS path,
        stops,
        total_time
    ORDER BY stops ASC, total_time ASC
    LIMIT 1
    """

    with _driver() as driver:
        with driver.session() as session:
            result = session.run(
                cypher,
                origin_id=origin_id,
                destination_id=destination_id,
            )
            row = result.single()

    if row is None:
        return {"found": False, "stops": None, "total_time": None, "path": []}
    return {
        "found": True,
        "stops": row["stops"],
        "total_time": row["total_time"],
        "fare_class": fare_class,
        "path": list(row["path"]),
    }


# ===========================================================================
# 4. query_alternative_routes
#    Paths that avoid a specific (closed/disrupted) station.
# ===========================================================================

def query_alternative_routes(
    origin_id: str,
    destination_id: str,
    avoid_station_id: str,
    network: str = "auto",
    max_routes: int = 3,
) -> list[list[dict]]:
    """
    Find alternative routes that exclude a specific station.

    Args:
        origin_id:        Journey start station ID.
        destination_id:   Journey end station ID.
        avoid_station_id: Station to exclude (e.g. "NR03" if Old Town Junction is closed).
        network:          "metro", "rail", or "auto".
        max_routes:       Maximum number of alternative routes to return.

    Returns:
        List of routes (each route is a list of dicts: station_id, name, label).
        Outer list is sorted fastest-first.
        Returns [] if no alternatives exist.
    """
    if network == "metro":
        rel_filter = "METRO_LINK"
    elif network == "rail":
        rel_filter = "RAIL_LINK"
    else:
        rel_filter = "METRO_LINK|RAIL_LINK|INTERCHANGE_TO"

    cypher = f"""
    MATCH (origin WHERE origin.station_id = $origin_id)
    MATCH (dest   WHERE dest.station_id   = $destination_id)
    MATCH p = (origin)-[:{rel_filter}*]-(dest)
    WHERE NONE(n IN nodes(p) WHERE n.station_id = $avoid_station_id)
    WITH p,
         reduce(t = 0, r IN relationships(p) |
             t + coalesce(r.travel_time_min, r.walk_time_min, 0)
         ) AS total_time
    RETURN
        [node IN nodes(p) | {{
            station_id : node.station_id,
            name       : node.name,
            label      : labels(node)[0]
        }}] AS path,
        total_time
    ORDER BY total_time ASC
    LIMIT $max_routes
    """

    with _driver() as driver:
        with driver.session() as session:
            result = session.run(
                cypher,
                origin_id=origin_id,
                destination_id=destination_id,
                avoid_station_id=avoid_station_id,
                max_routes=max_routes,
            )
            routes = []
            for row in result:
                path = list(row["path"])
                if path:
                    path[-1]["total_time"] = row["total_time"]
                routes.append(path)

    return routes


# ===========================================================================
# 5. query_interchange_path
#    Cross-network route (metro ↔ national rail via INTERCHANGE_TO).
# ===========================================================================

def query_interchange_path(
    origin_id: str,
    destination_id: str,
) -> dict:
    """
    Find the best path that crosses between the metro and national rail networks.
    Requires at least one INTERCHANGE_TO relationship in the path.

    Args:
        origin_id:      Starting station (any network).
        destination_id: Destination station (any network).

    Returns:
        dict with keys:
            found           (bool)
            total_time      (int, minutes)
            interchange_at  (list of str — station_ids where the network switch happens)
            path            (list of dicts: station_id, name, label)
        Returns {"found": False} if no cross-network path exists.
    """
    cypher = """
    MATCH (origin WHERE origin.station_id = $origin_id)
    MATCH (dest   WHERE dest.station_id   = $destination_id)
    MATCH p = shortestPath((origin)-[:METRO_LINK|RAIL_LINK|INTERCHANGE_TO*]-(dest))
    WHERE ANY(r IN relationships(p) WHERE type(r) = 'INTERCHANGE_TO')
    WITH p,
         reduce(t = 0, r IN relationships(p) |
             t + coalesce(r.travel_time_min, r.walk_time_min, 0)
         ) AS total_time
    RETURN
        [node IN nodes(p) | {
            station_id : node.station_id,
            name       : node.name,
            label      : labels(node)[0]
        }] AS path,
        total_time,
        [r IN relationships(p) WHERE type(r) = 'INTERCHANGE_TO' |
            startNode(r).station_id
        ] AS interchange_at
    ORDER BY total_time ASC
    LIMIT 1
    """

    with _driver() as driver:
        with driver.session() as session:
            result = session.run(
                cypher,
                origin_id=origin_id,
                destination_id=destination_id,
            )
            row = result.single()

    if row is None:
        return {"found": False, "total_time": None, "path": [], "interchange_at": []}
    return {
        "found": True,
        "total_time": row["total_time"],
        "interchange_at": list(row["interchange_at"]),
        "path": list(row["path"]),
    }


# ===========================================================================
# 6. query_delay_ripple
#    Stations affected by a closure/delay within N hops.
# ===========================================================================

def query_delay_ripple(
    delayed_station_id: str,
    hops: int = 2,
) -> list[dict]:
    """
    Find all stations reachable within N hops from a delayed/closed station.
    Used to communicate knock-on disruption to passengers.

    Args:
        delayed_station_id: The station experiencing the delay or closure.
        hops:               Search radius in hops (default 2).

    Returns:
        List of dicts, each with:
            station_id    (str)
            name          (str)
            label         (str)
            hop_distance  (int — 1 = direct neighbour, 2 = two hops away, etc.)
        Sorted by hop_distance ASC. Returns [] if station not found.
    """
    cypher = """
    MATCH (src WHERE src.station_id = $station_id)
    MATCH p = (src)-[:METRO_LINK|RAIL_LINK*1..$hops]-(affected)
    WHERE affected.station_id <> $station_id
    WITH affected, min(length(p)) AS hop_distance
    RETURN
        affected.station_id AS station_id,
        affected.name       AS name,
        labels(affected)[0] AS label,
        hop_distance
    ORDER BY hop_distance ASC, affected.station_id ASC
    """

    with _driver() as driver:
        with driver.session() as session:
            result = session.run(
                cypher,
                station_id=delayed_station_id,
                hops=hops,
            )
            return [dict(record) for record in result]


# ===========================================================================
# 7. query_station_connections
#    All direct neighbours of a station (one hop).
# ===========================================================================

def query_station_connections(station_id: str) -> list[dict]:
    """
    Return every station directly connected to the given station.

    Args:
        station_id: e.g. "MS01" or "NR01".

    Returns:
        List of dicts, each with:
            neighbour_id       (str)
            neighbour_name     (str)
            neighbour_label    (str)
            relationship_type  (str — "METRO_LINK", "RAIL_LINK", "INTERCHANGE_TO")
            line               (str or None — present on METRO_LINK / RAIL_LINK)
            travel_time_min    (int or None)
            walk_time_min      (int or None)
        Returns [] if station not found or has no connections.
    """
    cypher = """
    MATCH (src WHERE src.station_id = $station_id)
    MATCH (src)-[r:METRO_LINK|RAIL_LINK|INTERCHANGE_TO]->(neighbour)
    RETURN
        neighbour.station_id AS neighbour_id,
        neighbour.name       AS neighbour_name,
        labels(neighbour)[0] AS neighbour_label,
        type(r)              AS relationship_type,
        r.line               AS line,
        r.travel_time_min    AS travel_time_min,
        r.walk_time_min      AS walk_time_min
    ORDER BY relationship_type, r.line, neighbour.station_id
    """

    with _driver() as driver:
        with driver.session() as session:
            result = session.run(cypher, station_id=station_id)
            return [dict(record) for record in result]
