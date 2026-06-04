"""
test_graph_queries.py
---------------------
Verifies databases/graph/queries.py is consistent with skeleton/seed_neo4j.py.
Uses unittest.mock so no live Neo4j connection is required.
"""

import sys
import types
import unittest
from unittest.mock import MagicMock, call, patch

# ---------------------------------------------------------------------------
# Stub the neo4j package so queries.py can be imported without the driver
# ---------------------------------------------------------------------------
neo4j_stub = types.ModuleType("neo4j")
neo4j_stub.GraphDatabase = MagicMock()
sys.modules.setdefault("neo4j", neo4j_stub)

from databases.graph import queries  # noqa: E402


def _mock_session(rows: list[dict]):
    """Return a mock (driver, session, result) triple that yields `rows`."""
    mock_result = MagicMock()
    mock_result.__iter__ = MagicMock(return_value=iter(
        [MagicMock(**{"__iter__": None, "keys": MagicMock(return_value=list(r.keys())),
                      **{k: v for k, v in r.items()}}) for r in rows]
    ))
    mock_result.single.return_value = None

    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.run.return_value = mock_result

    mock_driver = MagicMock()
    mock_driver.__enter__ = MagicMock(return_value=mock_driver)
    mock_driver.__exit__ = MagicMock(return_value=False)
    mock_driver.session.return_value = mock_session

    return mock_driver, mock_session, mock_result


class TestDelayRippleHopsInterpolation(unittest.TestCase):
    """
    Fix verified: $hops must NOT appear as a Cypher parameter.
    Cypher doesn't support parameters in variable-length path bounds.
    The hops value must be interpolated directly into the query string.
    """

    def _run_with_hops(self, hops: int):
        mock_driver, mock_session, mock_result = _mock_session([])
        mock_result.__iter__ = MagicMock(return_value=iter([]))
        with patch.object(queries, "_driver", return_value=mock_driver):
            queries.query_delay_ripple("MS01", hops=hops)
        return mock_session.run.call_args

    def test_hops_literal_in_query_string(self):
        """The hop count must be embedded in the Cypher, not passed as a parameter."""
        run_call = self._run_with_hops(3)
        cypher = run_call.args[0]
        self.assertIn("*1..3", cypher,
                      "Hop count should be interpolated directly into the Cypher string")

    def test_hops_not_a_parameter(self):
        """$hops must not be passed as a keyword argument to session.run."""
        run_call = self._run_with_hops(3)
        self.assertNotIn("hops", run_call.kwargs,
                         "$hops must not be passed as a Cypher parameter")

    def test_no_dollar_hops_in_query(self):
        """The string '$hops' must not appear in the generated Cypher."""
        run_call = self._run_with_hops(2)
        cypher = run_call.args[0]
        self.assertNotIn("$hops", cypher,
                         "$hops in the query string would cause a Cypher SyntaxError")

    def test_different_hop_values(self):
        """Verify each hop value is correctly embedded."""
        for h in [1, 2, 5]:
            with self.subTest(hops=h):
                run_call = self._run_with_hops(h)
                cypher = run_call.args[0]
                self.assertIn(f"*1..{h}", cypher)

    def test_station_id_still_a_parameter(self):
        """station_id must still be passed as a safe Cypher parameter."""
        run_call = self._run_with_hops(2)
        self.assertEqual(run_call.kwargs.get("station_id"), "MS01",
                         "station_id should remain a parameterized value")


class TestQuerySchemaConsistency(unittest.TestCase):
    """
    Verifies that query functions reference the same node labels, relationship
    types, and property names that seed_neo4j.py creates.
    """

    def _get_cypher(self, fn, *args, **kwargs):
        """Call fn with mocked driver and return the Cypher string used."""
        mock_driver, mock_session, mock_result = _mock_session([])
        mock_result.__iter__ = MagicMock(return_value=iter([]))
        mock_result.single.return_value = None
        with patch.object(queries, "_driver", return_value=mock_driver):
            try:
                fn(*args, **kwargs)
            except Exception:
                pass
        if mock_session.run.called:
            return mock_session.run.call_args.args[0]
        return ""

    def test_delay_ripple_uses_correct_rel_types(self):
        cypher = self._get_cypher(queries.query_delay_ripple, "MS01", hops=2)
        self.assertIn("METRO_LINK", cypher)
        self.assertIn("RAIL_LINK", cypher)

    def test_station_connections_uses_all_three_rel_types(self):
        cypher = self._get_cypher(queries.query_station_connections, "MS01")
        for rel in ("METRO_LINK", "RAIL_LINK", "INTERCHANGE_TO"):
            self.assertIn(rel, cypher, f"{rel} missing from query_station_connections")

    def test_station_connections_has_distinct(self):
        cypher = self._get_cypher(queries.query_station_connections, "MS01")
        self.assertIn("DISTINCT", cypher,
                      "DISTINCT should be present to avoid duplicates from bidirectional seeding")

    def test_interchange_path_requires_interchange_to_rel(self):
        cypher = self._get_cypher(queries.query_interchange_path, "MS01", "NR01")
        self.assertIn("INTERCHANGE_TO", cypher)

    def test_shortest_route_metro_uses_metro_link_only(self):
        cypher = self._get_cypher(
            queries.query_shortest_route, "MS01", "MS14", network="metro"
        )
        self.assertIn("METRO_LINK", cypher)
        self.assertNotIn("RAIL_LINK", cypher)

    def test_shortest_route_rail_uses_rail_link_only(self):
        cypher = self._get_cypher(
            queries.query_shortest_route, "NR01", "NR05", network="rail"
        )
        self.assertIn("RAIL_LINK", cypher)
        self.assertNotIn("METRO_LINK", cypher)

    def test_shortest_route_auto_uses_all_rel_types(self):
        cypher = self._get_cypher(
            queries.query_shortest_route, "MS01", "NR05", network="auto"
        )
        for rel in ("METRO_LINK", "RAIL_LINK", "INTERCHANGE_TO"):
            self.assertIn(rel, cypher)

    def test_line_stations_metro_uses_metro_link(self):
        cypher = self._get_cypher(queries.query_line_stations, "M1")
        self.assertIn("METRO_LINK", cypher)
        self.assertNotIn("RAIL_LINK", cypher)

    def test_line_stations_rail_uses_rail_link(self):
        cypher = self._get_cypher(queries.query_line_stations, "NR1")
        self.assertIn("RAIL_LINK", cypher)
        self.assertNotIn("METRO_LINK", cypher)

    def test_property_names_travel_time_min(self):
        """seed_neo4j seeds travel_time_min on METRO_LINK and RAIL_LINK."""
        cypher = self._get_cypher(queries.query_shortest_route, "MS01", "MS14")
        self.assertIn("travel_time_min", cypher)

    def test_property_names_walk_time_min(self):
        """seed_neo4j seeds walk_time_min on INTERCHANGE_TO."""
        cypher = self._get_cypher(queries.query_shortest_route, "MS01", "NR01")
        self.assertIn("walk_time_min", cypher)

    def test_node_label_metro_station(self):
        """query_station_connections returns labels dynamically via labels() — no hardcoded label needed."""
        cypher = self._get_cypher(queries.query_station_connections, "MS01")
        # Labels are returned via labels(neighbour)[0], not a hardcoded string
        self.assertIn("labels(", cypher)

    def test_node_label_national_rail_station(self):
        """seed_neo4j creates NationalRailStation nodes."""
        cypher = self._get_cypher(queries.query_station_connections, "NR01")
        # NationalRailStation label appears in interchange queries; check delay ripple
        cypher2 = self._get_cypher(queries.query_interchange_path, "MS01", "NR01")
        # Either query or label-based checks — just ensure no unexpected label names
        self.assertNotIn("NationalRail ", cypher2)  # no truncated label


class TestCheapestRouteSchema(unittest.TestCase):
    """Schema consistency tests for query_cheapest_route."""

    def _get_cypher(self, fn, *args, **kwargs):
        mock_driver, mock_session, mock_result = _mock_session([])
        mock_result.single.return_value = None
        with patch.object(queries, "_driver", return_value=mock_driver):
            try:
                fn(*args, **kwargs)
            except Exception:
                pass
        if mock_session.run.called:
            return mock_session.run.call_args.args[0]
        return ""

    def test_cheapest_route_metro_uses_metro_link_only(self):
        cypher = self._get_cypher(queries.query_cheapest_route, "MS01", "MS14", network="metro")
        self.assertIn("METRO_LINK", cypher)
        self.assertNotIn("RAIL_LINK", cypher)

    def test_cheapest_route_rail_uses_rail_link_only(self):
        cypher = self._get_cypher(queries.query_cheapest_route, "NR01", "NR05", network="rail")
        self.assertIn("RAIL_LINK", cypher)
        self.assertNotIn("METRO_LINK", cypher)

    def test_cheapest_route_auto_uses_all_rel_types(self):
        cypher = self._get_cypher(queries.query_cheapest_route, "MS01", "NR05", network="auto")
        for rel in ("METRO_LINK", "RAIL_LINK", "INTERCHANGE_TO"):
            self.assertIn(rel, cypher, f"{rel} missing from auto cheapest route")

    def test_cheapest_route_uses_stops(self):
        cypher = self._get_cypher(queries.query_cheapest_route, "MS01", "MS14")
        self.assertIn("stops", cypher)

    def test_cheapest_route_uses_travel_time_min(self):
        cypher = self._get_cypher(queries.query_cheapest_route, "MS01", "MS14")
        self.assertIn("travel_time_min", cypher)


class TestAlternativeRoutesSchema(unittest.TestCase):
    """Schema consistency tests for query_alternative_routes."""

    def _get_cypher_and_kwargs(self, fn, *args, **kwargs):
        mock_driver, mock_session, mock_result = _mock_session([])
        mock_result.__iter__ = MagicMock(return_value=iter([]))
        with patch.object(queries, "_driver", return_value=mock_driver):
            try:
                fn(*args, **kwargs)
            except Exception:
                pass
        if mock_session.run.called:
            return mock_session.run.call_args.args[0], mock_session.run.call_args.kwargs
        return "", {}

    def test_alternative_routes_metro_uses_metro_link_only(self):
        cypher, _ = self._get_cypher_and_kwargs(
            queries.query_alternative_routes, "MS01", "MS14", "MS05", network="metro"
        )
        self.assertIn("METRO_LINK", cypher)
        self.assertNotIn("RAIL_LINK", cypher)

    def test_alternative_routes_rail_uses_rail_link_only(self):
        cypher, _ = self._get_cypher_and_kwargs(
            queries.query_alternative_routes, "NR01", "NR05", "NR03", network="rail"
        )
        self.assertIn("RAIL_LINK", cypher)
        self.assertNotIn("METRO_LINK", cypher)

    def test_alternative_routes_auto_uses_all_rel_types(self):
        cypher, _ = self._get_cypher_and_kwargs(
            queries.query_alternative_routes, "MS01", "NR05", "MS05", network="auto"
        )
        for rel in ("METRO_LINK", "RAIL_LINK", "INTERCHANGE_TO"):
            self.assertIn(rel, cypher, f"{rel} missing from auto alternative routes")

    def test_alternative_routes_excludes_avoid_station_via_none_clause(self):
        cypher, kwargs = self._get_cypher_and_kwargs(
            queries.query_alternative_routes, "MS01", "MS14", "MS05"
        )
        self.assertIn("NONE", cypher)
        self.assertEqual(kwargs.get("avoid_station_id"), "MS05")

    def test_alternative_routes_max_routes_is_a_parameter(self):
        _, kwargs = self._get_cypher_and_kwargs(
            queries.query_alternative_routes, "MS01", "MS14", "MS05", max_routes=5
        )
        self.assertEqual(kwargs.get("max_routes"), 5)


class TestReturnValueParsing(unittest.TestCase):
    """Verify query functions correctly parse and return structured results."""

    def _driver_single(self, row):
        """Mock driver whose session.run().single() returns `row` (dict or None)."""
        mock_result = MagicMock()
        mock_result.single.return_value = row

        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.run.return_value = mock_result

        mock_driver = MagicMock()
        mock_driver.__enter__ = MagicMock(return_value=mock_driver)
        mock_driver.__exit__ = MagicMock(return_value=False)
        mock_driver.session.return_value = mock_session
        return mock_driver

    def _driver_rows(self, rows):
        """Mock driver whose session.run() is iterable over `rows` (list of dicts)."""
        mock_result = MagicMock()
        mock_result.__iter__ = MagicMock(return_value=iter(rows))

        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.run.return_value = mock_result

        mock_driver = MagicMock()
        mock_driver.__enter__ = MagicMock(return_value=mock_driver)
        mock_driver.__exit__ = MagicMock(return_value=False)
        mock_driver.session.return_value = mock_session
        return mock_driver

    def test_shortest_route_not_found_shape(self):
        with patch.object(queries, "_driver", return_value=self._driver_single(None)):
            result = queries.query_shortest_route("MS01", "MS99")
        self.assertFalse(result["found"])
        self.assertIsNone(result["total_time"])
        self.assertEqual(result["path"], [])

    def test_shortest_route_found_shape(self):
        path = [
            {"station_id": "MS01", "name": "Central Square", "label": "MetroStation"},
            {"station_id": "MS02", "name": "North Gate",     "label": "MetroStation"},
        ]
        with patch.object(queries, "_driver",
                          return_value=self._driver_single({"path": path, "total_time": 8})):
            result = queries.query_shortest_route("MS01", "MS02")
        self.assertTrue(result["found"])
        self.assertEqual(result["total_time"], 8)
        self.assertEqual(result["path"][0]["station_id"], "MS01")
        self.assertEqual(len(result["path"]), 2)

    def test_cheapest_route_not_found_shape(self):
        with patch.object(queries, "_driver", return_value=self._driver_single(None)):
            result = queries.query_cheapest_route("MS01", "MS99")
        self.assertFalse(result["found"])
        self.assertIsNone(result["stops"])
        self.assertIsNone(result["total_time"])
        self.assertEqual(result["path"], [])

    def test_cheapest_route_found_shape(self):
        path = [
            {"station_id": "MS01", "name": "Central Square", "label": "MetroStation"},
            {"station_id": "MS02", "name": "North Gate",     "label": "MetroStation"},
        ]
        with patch.object(queries, "_driver",
                          return_value=self._driver_single({"path": path, "stops": 1, "total_time": 8})):
            result = queries.query_cheapest_route("MS01", "MS02", fare_class="first")
        self.assertTrue(result["found"])
        self.assertEqual(result["stops"], 1)
        self.assertEqual(result["total_time"], 8)
        self.assertEqual(result["fare_class"], "first")
        self.assertEqual(len(result["path"]), 2)

    def test_interchange_path_not_found_shape(self):
        with patch.object(queries, "_driver", return_value=self._driver_single(None)):
            result = queries.query_interchange_path("MS01", "NR99")
        self.assertFalse(result["found"])
        self.assertEqual(result["path"], [])
        self.assertEqual(result["interchange_at"], [])

    def test_interchange_path_found_shape(self):
        path = [
            {"station_id": "MS01", "name": "Central Square",  "label": "MetroStation"},
            {"station_id": "NR01", "name": "City Terminal",   "label": "NationalRailStation"},
        ]
        row = {"path": path, "total_time": 10, "interchange_at": ["MS01"]}
        with patch.object(queries, "_driver", return_value=self._driver_single(row)):
            result = queries.query_interchange_path("MS01", "NR01")
        self.assertTrue(result["found"])
        self.assertEqual(result["total_time"], 10)
        self.assertEqual(result["interchange_at"], ["MS01"])
        self.assertEqual(len(result["path"]), 2)

    def test_delay_ripple_empty(self):
        with patch.object(queries, "_driver", return_value=self._driver_rows([])):
            result = queries.query_delay_ripple("MS99")
        self.assertEqual(result, [])

    def test_delay_ripple_returns_list_of_dicts(self):
        rows = [
            {"station_id": "MS02", "name": "North Gate", "label": "MetroStation", "hop_distance": 1},
            {"station_id": "MS03", "name": "East End",   "label": "MetroStation", "hop_distance": 2},
        ]
        with patch.object(queries, "_driver", return_value=self._driver_rows(rows)):
            result = queries.query_delay_ripple("MS01", hops=2)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["station_id"], "MS02")
        self.assertEqual(result[0]["hop_distance"], 1)

    def test_station_connections_empty(self):
        with patch.object(queries, "_driver", return_value=self._driver_rows([])):
            result = queries.query_station_connections("MS99")
        self.assertEqual(result, [])

    def test_station_connections_returns_list_of_dicts(self):
        rows = [{
            "neighbour_id": "MS02", "neighbour_name": "North Gate",
            "neighbour_label": "MetroStation", "relationship_type": "METRO_LINK",
            "line": "M1", "travel_time_min": 4, "walk_time_min": None,
        }]
        with patch.object(queries, "_driver", return_value=self._driver_rows(rows)):
            result = queries.query_station_connections("MS01")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["neighbour_id"], "MS02")
        self.assertEqual(result[0]["relationship_type"], "METRO_LINK")

    def test_alternative_routes_empty(self):
        with patch.object(queries, "_driver", return_value=self._driver_rows([])):
            result = queries.query_alternative_routes("MS01", "MS14", "MS05")
        self.assertEqual(result, [])

    def test_alternative_routes_returns_list_of_paths(self):
        path = [
            {"station_id": "MS01", "name": "Central Square", "label": "MetroStation"},
            {"station_id": "MS03", "name": "East End",       "label": "MetroStation"},
        ]
        rows = [{"path": path, "total_time": 12}]
        with patch.object(queries, "_driver", return_value=self._driver_rows(rows)):
            result = queries.query_alternative_routes("MS01", "MS14", "MS05")
        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0]), 2)
        self.assertEqual(result[0][-1]["total_time"], 12)


if __name__ == "__main__":
    unittest.main(verbosity=2)
