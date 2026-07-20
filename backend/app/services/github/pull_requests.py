from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from .client import GitHubClient
from .safety import (
    GitHubWriteSafetyError,
    require_confirmation,
    validate_branch_name,
    validate_repository_part,
)


class MergeMethod(str, Enum):
    MERGE = "merge"
    SQUASH = "squash"
    REBASE = "rebase"


@dataclass(frozen=True)
class ReviewGateResult:
    passed: bool
    mergeable: bool
    draft: bool
    approvals: int
    required_approvals: int
    changes_requested: int
    checks_state: str
    required_checks_passed: bool
    reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "mergeable": self.mergeable,
            "draft": self.draft,
            "approvals": self.approvals,
            "required_approvals": self.required_approvals,
            "changes_requested": self.changes_requested,
            "checks_state": self.checks_state,
            "required_checks_passed": self.required_checks_passed,
            "reasons": list(self.reasons),
        }


class PullRequestService:
    def __init__(self, client: GitHubClient):
        self.client = client

    def create_pull_request(
        self,
        owner,
        repo,
        title,
        head,
        base,
        body="",
        *,
        draft: bool = False,
        confirmed: bool = False,
        dry_run: bool = True,
    ):
        owner = validate_repository_part(owner, "owner")
        repo = validate_repository_part(repo, "repository")
        head = validate_branch_name(head)
        base = validate_branch_name(base)
        title = title.strip()
        if not title:
            raise GitHubWriteSafetyError("Pull request title is required")
        if head == base:
            raise GitHubWriteSafetyError("Pull request head and base branches must differ")

        plan = {
            "operation": "create_pull_request",
            "repository": f"{owner}/{repo}",
            "title": title,
            "head": head,
            "base": base,
            "body": body,
            "draft": draft,
            "requires_confirmation": True,
            "dry_run": dry_run,
        }
        if dry_run:
            return {"executed": False, "plan": plan}

        require_confirmation(confirmed=confirmed, dry_run=dry_run)
        result = self.client.post(
            f"/repos/{owner}/{repo}/pulls",
            {
                "title": title,
                "head": head,
                "base": base,
                "body": body,
                "draft": draft,
            },
        )
        return {"executed": True, "plan": plan, "result": result}

    def get_pull_request(self, owner, repo, number):
        return self.client.get(f"/repos/{owner}/{repo}/pulls/{int(number)}")

    def list_files(self, owner, repo, number):
        return self.client.get(f"/repos/{owner}/{repo}/pulls/{int(number)}/files")

    def list_reviews(self, owner, repo, number):
        return self.client.get(f"/repos/{owner}/{repo}/pulls/{int(number)}/reviews")

    def get_combined_status(self, owner, repo, ref):
        return self.client.get(f"/repos/{owner}/{repo}/commits/{ref}/status")

    def evaluate_review_gates(
        self,
        owner,
        repo,
        number,
        *,
        required_approvals: int = 1,
        require_checks: bool = True,
    ) -> ReviewGateResult:
        pr = self.get_pull_request(owner, repo, number)
        reviews = self.list_reviews(owner, repo, number) or []

        latest_by_user = {}
        for review in reviews:
            user = (review.get("user") or {}).get("login")
            if user:
                latest_by_user[user] = review.get("state", "").upper()

        approvals = sum(state == "APPROVED" for state in latest_by_user.values())
        changes_requested = sum(
            state == "CHANGES_REQUESTED" for state in latest_by_user.values()
        )

        head_sha = ((pr.get("head") or {}).get("sha") or "").strip()
        status = self.get_combined_status(owner, repo, head_sha) if head_sha else {}
        checks_state = (status or {}).get("state", "pending")
        required_checks_passed = (not require_checks) or checks_state == "success"

        reasons = []
        if pr.get("draft", False):
            reasons.append("pull request is still a draft")
        if pr.get("mergeable") is False:
            reasons.append("pull request is not mergeable")
        if approvals < required_approvals:
            reasons.append(
                f"requires {required_approvals} approval(s), found {approvals}"
            )
        if changes_requested:
            reasons.append(f"{changes_requested} review(s) requested changes")
        if not required_checks_passed:
            reasons.append(f"required checks are {checks_state}")

        mergeable = pr.get("mergeable") is not False
        passed = (
            not pr.get("draft", False)
            and mergeable
            and approvals >= required_approvals
            and changes_requested == 0
            and required_checks_passed
        )
        return ReviewGateResult(
            passed=passed,
            mergeable=mergeable,
            draft=bool(pr.get("draft", False)),
            approvals=approvals,
            required_approvals=required_approvals,
            changes_requested=changes_requested,
            checks_state=checks_state,
            required_checks_passed=required_checks_passed,
            reasons=tuple(reasons),
        )

    def merge_pull_request(
        self,
        owner,
        repo,
        number,
        *,
        method: str = "squash",
        commit_title: str | None = None,
        commit_message: str | None = None,
        required_approvals: int = 1,
        require_checks: bool = True,
        confirmed: bool = False,
        dry_run: bool = True,
    ):
        try:
            merge_method = MergeMethod(method)
        except ValueError as exc:
            raise GitHubWriteSafetyError(
                "merge method must be one of: merge, squash, rebase"
            ) from exc

        gates = self.evaluate_review_gates(
            owner,
            repo,
            number,
            required_approvals=required_approvals,
            require_checks=require_checks,
        )
        plan = {
            "operation": "merge_pull_request",
            "repository": f"{owner}/{repo}",
            "pull_request": int(number),
            "merge_method": merge_method.value,
            "commit_title": commit_title,
            "commit_message": commit_message,
            "gates": gates.as_dict(),
            "requires_confirmation": True,
            "dry_run": dry_run,
        }

        if dry_run:
            return {"executed": False, "plan": plan}
        if not gates.passed:
            raise GitHubWriteSafetyError(
                "Pull request review gates failed: " + "; ".join(gates.reasons)
            )
        require_confirmation(confirmed=confirmed, dry_run=dry_run)

        payload = {"merge_method": merge_method.value}
        if commit_title:
            payload["commit_title"] = commit_title
        if commit_message:
            payload["commit_message"] = commit_message

        result = self.client.put(
            f"/repos/{owner}/{repo}/pulls/{int(number)}/merge",
            payload,
        )
        return {"executed": True, "plan": plan, "result": result}
