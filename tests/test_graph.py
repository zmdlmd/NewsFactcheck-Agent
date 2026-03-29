import unittest

from app.agent.graph import build_graph, route_after_con_search, route_from_supervisor


class BuildGraphTests(unittest.TestCase):
    def test_graph_contains_expected_nodes(self):
        graph = build_graph().get_graph()
        self.assertEqual(
            set(graph.nodes.keys()),
            {
                "__start__",
                "__end__",
                "extract_claims",
                "supervisor",
                "pro_planner",
                "con_planner",
                "pro_search",
                "con_search",
                "fetch_key_pages",
                "judge",
                "write_report",
            },
        )

    def test_supervisor_route_mapping(self):
        self.assertEqual(route_from_supervisor({"supervisor_plan": {"next_step": "search"}}), "pro_planner")
        self.assertEqual(route_from_supervisor({"supervisor_plan": {"next_step": "next_claim"}}), "supervisor")
        self.assertEqual(route_from_supervisor({"supervisor_plan": {"next_step": "finish"}}), "write_report")

    def test_fetch_route_mapping(self):
        self.assertEqual(
            route_after_con_search(
                {
                    "enable_fetch": True,
                    "fetch_budget_remaining": 1,
                    "supervisor_plan": {"use_fetch": True},
                }
            ),
            "fetch_key_pages",
        )
        self.assertEqual(
            route_after_con_search(
                {
                    "enable_fetch": False,
                    "fetch_budget_remaining": 1,
                    "supervisor_plan": {"use_fetch": True},
                }
            ),
            "judge",
        )


if __name__ == "__main__":
    unittest.main()
