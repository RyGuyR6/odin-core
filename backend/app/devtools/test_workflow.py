from app.workflows.github import ModifyFileWorkflow

workflow = ModifyFileWorkflow()

result = workflow.run(
    owner="RyGuyR6",
    repo="odin-test",
    path="README.md",
    content="""# Odin Test

Modified through the Odin Workflow Engine.
""",
    commit_message="Workflow engine test",
    pr_title="Workflow Engine Test",
    pr_body="Generated automatically by Odin.",
)

print()
print("=" * 60)
print("WORKFLOW RESULT")
print("=" * 60)

print(result)
