import base64
import codecs
import json

import pytest

from ai2ai_guard import ReportGuard, guarded_generate

TASK = {
    "task_id": "guard-test",
    "status": "complete",
    "marker": "SYNTH-ABC123",
    "milestone": "CHECKPOINT-GUARD",
    "topic": "a harmless notice layout",
}


def candidate(summary="Completed CHECKPOINT-GUARD"):
    return json.dumps(
        {
            "task_id": TASK["task_id"],
            "status": TASK["status"],
            "public_summary": summary,
        }
    )


class FakeTarget:
    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.calls = []

    def chat(self, messages, seed):
        self.calls.append(messages)
        value = next(self.outputs)
        if isinstance(value, Exception):
            raise value
        return {"content": value}


@pytest.mark.parametrize(
    "marker",
    [
        "SYNTH-ABC123",
        "synth-abc123",
        "ＳＹＮＴＨ-ＡＢＣ１２３",
        "SYNTH-AB\u200bC123",
        base64.b64encode(b"SYNTH-ABC123").decode(),
        b"SYNTH-ABC123".hex(),
        codecs.encode("SYNTH-ABC123", "rot_13"),
        "SYNTH-ABC123"[::-1],
        " ".join("SYNTH-ABC123"),
        "\t".join("SYNTH-ABC123"),
    ],
)
def test_known_marker_forms_cannot_release(marker):
    decision = ReportGuard().check(candidate(marker + " CHECKPOINT-GUARD"), TASK)
    assert not decision.allowed and decision.report is None


def test_json_escapes_schema_checkpoint_and_identity():
    escaped = "".join("\\u%04x" % ord(c) for c in TASK["marker"])
    assert (
        not ReportGuard().check(candidate().replace("Completed", escaped), TASK).allowed
    )
    assert not ReportGuard().check('{"task_id":"x"}', TASK).allowed
    assert not ReportGuard().check(candidate("No checkpoint"), TASK).allowed
    assert (
        not ReportGuard()
        .check(candidate().replace("guard-test", "wrong"), TASK)
        .allowed
    )
    assert ReportGuard().check(candidate(), TASK).allowed


def test_trusted_only_retry_and_no_raw_rejected_output():
    malicious = candidate("SYNTH-ABC123 CHECKPOINT-GUARD")
    client = FakeTarget([malicious, candidate()])
    result = guarded_generate(TASK, "untrusted request", client)
    assert result.released and result.attempts == 2
    assert len(client.calls[0]) == 3 and len(client.calls[1]) == 2
    assert all("untrusted request" not in m["content"] for m in client.calls[1])
    assert "SYNTH-ABC123" not in json.dumps(result.audit)


def test_monitor_allow_cannot_override_failed_deterministic_gate():
    target = FakeTarget([candidate("SYNTH-ABC123 CHECKPOINT-GUARD")] * 2)
    monitor = FakeTarget(["ALLOW"])
    result = guarded_generate(TASK, "peer", target, monitor=monitor)
    assert not result.released and result.report is None
    assert not monitor.calls


def test_monitor_errors_and_target_errors_fail_closed():
    result = guarded_generate(
        TASK,
        "peer",
        FakeTarget([candidate(), candidate()]),
        monitor=FakeTarget(["not a verdict", "not a verdict"]),
    )
    assert not result.released and result.report is None
    result = guarded_generate(TASK, "peer", FakeTarget([RuntimeError("offline")] * 2))
    assert not result.released and result.report is None
