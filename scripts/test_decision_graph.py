from odin_mcp.models.decision_graph import DecisionGraph

graph = DecisionGraph()

graph.add_node(
    "goal",
    "Add JWT Authentication",
    "goal",
)

graph.add_node(
    "analysis",
    "Repository Analysis",
    "analysis",
)

graph.add_node(
    "plan",
    "Engineering Plan",
    "plan",
)

graph.connect(
    "goal",
    "analysis",
    "analyzed_by",
)

graph.connect(
    "analysis",
    "plan",
    "produced",
)

print(graph)
