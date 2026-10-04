"""Human approval for change plans, and a dry-run-only executor with a hash-chained audit log.

Rules enforced in code:
  * an approval is bound to the plan's content hash: editing the plan voids it;
  * the requester (the agent) can never approve its own plan;
  * the approver must hold an allowed role; commitment purchases need the ``finance`` role;
  * plans with an irreversible step (delete, purchase) need two distinct approvers;
  * approvals expire after ``APPROVAL_TTL_HOURS`` on the caller-supplied logical clock;
  * the executor only ever produces a dry run. Live execution is not implemented on purpose.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from finops.agent.plan import ChangePlan

APPROVER_ROLES = {"finops-approver", "resource-owner", "finance"}
APPROVAL_TTL_HOURS = 72


class ApprovalError(Exception):
    pass


@dataclass(frozen=True)
class Approval:
    plan_id: str
    plan_digest: str
    approver: str
    role: str
    issued_at_hour: int


@dataclass
class AuditLog:
    entries: list[dict] = field(default_factory=list)

    def append(self, event: str, **data) -> dict:
        prev = self.entries[-1]["hash"] if self.entries else "0" * 64
        body = {"event": event, "data": data, "prev": prev}
        body["hash"] = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        self.entries.append(body)
        return body

    def verify(self) -> bool:
        prev = "0" * 64
        for e in self.entries:
            body = {"event": e["event"], "data": e["data"], "prev": e["prev"]}
            if e["prev"] != prev or hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest() != e["hash"]:
                return False
            prev = e["hash"]
        return True


def approve(plan: ChangePlan, approver: str, role: str, now_hour: int, audit: AuditLog | None = None) -> Approval:
    if approver == plan.requested_by:
        raise ApprovalError("the requester cannot approve its own plan")
    if role not in APPROVER_ROLES:
        raise ApprovalError(f"role {role!r} cannot approve changes")
    a = Approval(plan.plan_id, plan.digest, approver, role, now_hour)
    if audit:
        audit.append("approved", plan=plan.plan_id, digest=plan.digest, approver=approver, role=role)
    return a


def required_approvals(plan: ChangePlan) -> int:
    return 2 if plan.irreversible else 1


def check(plan: ChangePlan, approvals: list[Approval], now_hour: int) -> list[str]:
    """Return the list of problems (empty means the plan may be dry-run executed)."""
    problems = []
    valid = []
    for a in approvals:
        if a.plan_id != plan.plan_id or a.plan_digest != plan.digest:
            problems.append(f"approval by {a.approver} is for different plan content")
        elif now_hour - a.issued_at_hour > APPROVAL_TTL_HOURS:
            problems.append(f"approval by {a.approver} expired")
        else:
            valid.append(a)
    people = {a.approver for a in valid}
    if len(people) < required_approvals(plan):
        problems.append(f"needs {required_approvals(plan)} distinct approver(s), has {len(people)}")
    if any("purchase" in s.command for s in plan.steps) and not any(a.role == "finance" for a in valid):
        problems.append("commitment purchase needs a finance approver")
    return problems


def execute(plan: ChangePlan, approvals: list[Approval], now_hour: int, audit: AuditLog | None = None, dry_run: bool = True) -> list[str]:
    if not dry_run:
        raise NotImplementedError("live execution is deliberately not implemented; run the approved commands through change management")
    problems = check(plan, approvals, now_hour)
    if problems:
        if audit:
            audit.append("execution-refused", plan=plan.plan_id, problems=problems)
        raise ApprovalError("; ".join(problems))
    out = [f"[DRY-RUN] {s.command}" for s in plan.steps]
    plan.status = "dry-run-complete"
    plan.log = out
    if audit:
        audit.append("dry-run", plan=plan.plan_id, digest=plan.digest, steps=len(out))
    return out
