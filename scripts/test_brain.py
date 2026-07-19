from odin_mcp.core.brain import OdinBrain

brain = OdinBrain()

ctx = brain.create_context(
    "Implement JWT authentication"
)

print(ctx)
print()
print(ctx.decision_graph)
