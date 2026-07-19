from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.workflows.github.modify_file import ModifyFileWorkflow


router = APIRouter(
    prefix="/github/workflow",
    tags=["GitHub Workflow"],
)


class ModifyFileBody(BaseModel):
    owner: str = Field(..., description="GitHub repository owner")
    repo: str = Field(..., description="Repository name")
    path: str = Field(..., description="Repository file path")
    content: str = Field(..., description="New file contents")
    commit_message: str = Field(..., min_length=1)
    pr_title: str = Field(..., min_length=1)
    pr_body: str = ""


@router.post("/modify-file")
def modify_file(body: ModifyFileBody):
    workflow = ModifyFileWorkflow()

    try:
        return workflow.run(
            owner=body.owner,
            repo=body.repo,
            path=body.path,
            content=body.content,
            commit_message=body.commit_message,
            pr_title=body.pr_title,
            pr_body=body.pr_body,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc