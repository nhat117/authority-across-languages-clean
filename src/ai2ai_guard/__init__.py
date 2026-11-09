"""Policy-enforcing release gate for the synthetic administrative reporting task.

This is a task-specific validator, not a universal prompt-injection detector.
"""

import base64
import codecs
import hashlib
import unicodedata
from dataclasses import dataclass, field
from typing import List, Optional

from ai2ai_injection.evaluator import strict_json
from ai2ai_injection.monitor import monitor_messages, verdict
from ai2ai_injection.target import target_messages


def normalize(text):
    folded = unicodedata.normalize("NFKC", text).casefold()
    return "".join(ch for ch in folded if unicodedata.category(ch) != "Cf")


def visible_strings(value):
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return list(value) + [s for v in value.values() for s in visible_strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in visible_strings(v)]
    return []


@dataclass
class GateDecision:
    allowed: bool
    reasons: List[str]
    report: Optional[dict] = None


class ReportGuard:
    """Enforce schema, task identity, checkpoint and known marker forms."""

    def check(self, raw, task):
        if not isinstance(raw, str) or len(raw) > 65536:
            return GateDecision(False, ["invalid_or_oversized_candidate"])
        reasons = []
        try:
            value = strict_json(raw)
        except (ValueError, TypeError, RecursionError):
            value = None
            reasons.append("invalid_json")
        strings = [raw]
        try:
            strings += visible_strings(value)
        except RecursionError:
            return GateDecision(False, ["excessive_nesting"])
        forms = set()
        for marker in {task["marker"], task["marker"].lower()}:
            forms.update(
                {
                    normalize(marker),
                    normalize(marker.encode().hex()),
                    normalize(base64.b64encode(marker.encode()).decode()),
                    normalize(base64.urlsafe_b64encode(marker.encode()).decode()),
                    normalize(codecs.encode(marker, "rot_13")),
                    normalize(marker[::-1]),
                }
            )
        normalized = [normalize(text) for text in strings]
        compacted = ["".join(c for c in text if not c.isspace()) for text in normalized]
        if any(form in text for text in normalized + compacted for form in forms):
            reasons.append("forbidden_marker_or_known_encoding")
        schema = (
            isinstance(value, dict)
            and set(value) == {"task_id", "status", "public_summary"}
            and all(isinstance(v, str) for v in value.values())
        )
        if not schema:
            reasons.append("invalid_schema")
        elif value["task_id"] != task["task_id"] or value["status"] != task["status"]:
            reasons.append("wrong_task_identity_or_status")
        if schema and task["milestone"] not in value["public_summary"]:
            reasons.append("missing_required_checkpoint")
        return GateDecision(not reasons, reasons, value if not reasons else None)


@dataclass
class ProtectedResult:
    released: bool
    report: Optional[dict]
    attempts: int
    audit: List[dict] = field(default_factory=list)


def guarded_generate(task, peer_message, target, *, monitor=None, retry_trusted=True):
    """Release only validated data; an optional monitor may veto, never override.

    Retry at most once in fresh context with the peer message removed. API errors,
    invalid verdicts and repeated validation failures release no candidate.
    Audit entries retain hashes/reasons, never raw candidate text or API keys.
    """
    gate = ReportGuard()
    audit = []
    for attempt in range(2 if retry_trusted else 1):
        messages = target_messages(task, peer_message)
        if attempt:
            messages = messages[:2]
        try:
            response = target.chat(messages, 81821 + attempt)
            raw = response["content"]
            decision = gate.check(raw, task)
            entry = {
                "attempt": attempt + 1,
                "trusted_only_retry": bool(attempt),
                "candidate_sha256": hashlib.sha256(raw.encode()).hexdigest(),
                "deterministic_allowed": decision.allowed,
                "reasons": list(decision.reasons),
            }
            if decision.allowed and monitor is not None:
                # Untrusted original peer content is deliberately not sent to the guard.
                try:
                    check = monitor.chat(
                        monitor_messages(
                            {"task": task, "peer_message": ""}, raw, "output_only"
                        ),
                        91821 + attempt,
                    )
                    if verdict(check["content"]):
                        entry["reasons"].append("monitor_veto")
                except Exception:
                    entry["reasons"].append("monitor_error_fail_closed")
            audit.append(entry)
            if decision.allowed and not entry["reasons"]:
                return ProtectedResult(True, decision.report, attempt + 1, audit)
        except Exception as error:
            audit.append(
                {
                    "attempt": attempt + 1,
                    "trusted_only_retry": bool(attempt),
                    "reasons": ["generation_error_" + type(error).__name__],
                }
            )
    return ProtectedResult(False, None, len(audit), audit)
