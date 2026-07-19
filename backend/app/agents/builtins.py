from __future__ import annotations

from datetime import datetime, timezone

from .models import (
    AgentDefinition,
    AgentPermissions,
    RetryPolicy,
    WorkflowDefinition,
    WorkflowStep,
)


def now():
    return datetime.now(timezone.utc)


def builtin_agents() -> list[AgentDefinition]:
    timestamp = now()
    common = AgentPermissions(
        allow_llm=True,
        allow_tools=False,
        allow_memory_read=True,
        allow_memory_write=False,
        allow_conversations=True,
    )
    return [
        AgentDefinition(
            id="builtin-planner",
            name="planner",
            description="Creates dependency-aware implementation plans.",
            prompt_template="planner",
            temperature=0.2,
            retry_policy=RetryPolicy(max_attempts=2),
            permissions=common,
            metadata={"category": "planning"},
            enabled=True,
            built_in=True,
            created_at=timestamp,
            updated_at=timestamp,
        ),
        AgentDefinition(
            id="builtin-coder",
            name="coder",
            description="Produces implementation guidance and code changes.",
            prompt_template="coder",
            temperature=0.1,
            retry_policy=RetryPolicy(max_attempts=2),
            permissions=common,
            metadata={"category": "engineering"},
            enabled=True,
            built_in=True,
            created_at=timestamp,
            updated_at=timestamp,
        ),
        AgentDefinition(
            id="builtin-reviewer",
            name="reviewer",
            description="Reviews changes for correctness, security, and regressions.",
            prompt_template="reviewer",
            temperature=0.1,
            retry_policy=RetryPolicy(max_attempts=2),
            permissions=common,
            metadata={"category": "quality"},
            enabled=True,
            built_in=True,
            created_at=timestamp,
            updated_at=timestamp,
        ),
        AgentDefinition(
            id="builtin-debugger",
            name="debugger",
            description="Diagnoses failures and proposes safe fixes.",
            prompt_template="debug",
            temperature=0.1,
            retry_policy=RetryPolicy(max_attempts=2),
            permissions=common,
            metadata={"category": "debugging"},
            enabled=True,
            built_in=True,
            created_at=timestamp,
            updated_at=timestamp,
        ),
        AgentDefinition(
            id="builtin-researcher",
            name="researcher",
            description="Explains and researches technical subjects using supplied context.",
            prompt_template="explain",
            temperature=0.3,
            retry_policy=RetryPolicy(max_attempts=2),
            permissions=common,
            metadata={"category": "research"},
            enabled=True,
            built_in=True,
            created_at=timestamp,
            updated_at=timestamp,
        ),
    ]


def builtin_workflows() -> list[WorkflowDefinition]:
    timestamp = now()
    return [
        WorkflowDefinition(
            id="builtin-software-delivery",
            name="software-delivery",
            description="Plan, implement, and review a software change.",
            mode="sequential",
            steps=[
                WorkflowStep(
                    id="plan",
                    agent="planner",
                    input={
                        "goal": "{{ workflow.input.goal }}",
                        "repository": "{{ workflow.context.repository }}",
                        "constraints": "{{ workflow.context.constraints }}",
                    },
                ),
                WorkflowStep(
                    id="code",
                    agent="coder",
                    depends_on=["plan"],
                    input={
                        "task": "{{ workflow.input.goal }}",
                        "plan": "{{ steps.plan.output.content }}",
                        "repository": "{{ workflow.context.repository }}",
                        "constraints": "{{ workflow.context.constraints }}",
                    },
                ),
                WorkflowStep(
                    id="review",
                    agent="reviewer",
                    depends_on=["code"],
                    input={
                        "requirements": "{{ workflow.input.goal }}",
                        "repository": "{{ workflow.context.repository }}",
                        "changes": "{{ steps.code.output.content }}",
                    },
                ),
            ],
            metadata={"category": "engineering"},
            built_in=True,
            created_at=timestamp,
            updated_at=timestamp,
        ),
        WorkflowDefinition(
            id="builtin-debug-cycle",
            name="debug-cycle",
            description="Diagnose a failure and review the proposed fix.",
            mode="sequential",
            steps=[
                WorkflowStep(
                    id="diagnose",
                    agent="debugger",
                    input={
                        "error": "{{ workflow.input.error }}",
                        "logs": "{{ workflow.context.logs }}",
                        "code": "{{ workflow.context.code }}",
                        "environment": "{{ workflow.context.environment }}",
                    },
                ),
                WorkflowStep(
                    id="review",
                    agent="reviewer",
                    depends_on=["diagnose"],
                    input={
                        "requirements": "Resolve the reported failure safely.",
                        "repository": "{{ workflow.context.repository }}",
                        "changes": "{{ steps.diagnose.output.content }}",
                    },
                ),
            ],
            metadata={"category": "debugging"},
            built_in=True,
            created_at=timestamp,
            updated_at=timestamp,
        ),
    ]
