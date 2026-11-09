"""Recompute published evidence offline; no API client or paid inference."""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from ai2ai_guard.llm_judge import aggregate, agreement, sha, validate_assessment
from ai2ai_guard.review_analysis import join
from ai2ai_guard.round3_analysis import wording_language
from ai2ai_guard.round3_neutral import metrics, score
from ai2ai_guard.sampled_judge import (
    VERSION,
    sample_groups,
    sample_messages,
    sample_schema,
)

ROOT = Path(__file__).resolve().parents[1]


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def verify_data(root):
    manifest = json.loads((root / "data/manifest.json").read_text())
    for name, record in manifest["files"].items():
        path = (root / name).resolve()
        if not path.is_relative_to((root / "data").resolve()):
            raise ValueError("manifest_path_outside_data")
        if hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]:
            raise ValueError("evidence_changed: " + name)
    return manifest


def neutral_analysis(root):
    inputs = read_jsonl(root / "data/neutral/inputs.jsonl")
    rows = read_jsonl(root / "data/neutral/workers.jsonl")
    join(inputs, rows, complete=True)
    if len(inputs) != 180:
        raise ValueError("neutral_design_not_complete")
    scores = [score(row) for row in rows]
    for row, outcome in zip(rows, scores):
        if row["measurement"] != outcome:
            raise ValueError("saved_neutral_measurement_mismatch")
    return metrics(rows, scores, assigned=180)


def judge_analysis(root):
    folder = root / "data/judge"
    frame = json.loads((folder / "frame.json").read_text())
    selected, manifest = sample_groups(frame)
    if manifest != json.loads((folder / "selection.json").read_text()):
        raise ValueError("sample_selection_changed")
    groups = read_jsonl(folder / "groups.jsonl")
    by_id = {group["group_id"]: group for group in groups}
    expected = {group["group_id"]: group for group in selected}
    if len(by_id) != 96 or set(by_id) != set(expected):
        raise ValueError("sample_group_coverage_mismatch")
    for gid, group in by_id.items():
        if any(group[key] != value for key, value in expected[gid].items()):
            raise ValueError("sample_group_metadata_changed")
        original = {key: value for key, value in group.items()
                    if key != "source_group_sha256"}
        if sha(original) != group["source_group_sha256"]:
            raise ValueError("sample_group_source_hash_changed")
    rows = read_jsonl(folder / "judgments.jsonl")
    raw = read_jsonl(folder / "raw_responses.jsonl")
    raw_by_id = {row["raw_response"]["id"]: row for row in raw}
    if len(raw_by_id) != len(raw) or len(raw) != 288 or len(rows) != 288:
        raise ValueError("missing_or_duplicate_sample_response")
    seen, used, buckets = set(), set(), {gid: [] for gid in by_id}
    invalid = []
    for row in rows:
        gid, repeat, key = row["group_id"], row["repeat"], row["request_key"]
        if (gid not in by_id or repeat not in (0, 1, 2)
                or row["phase"] != "original"
                or key != f"original:{gid}:{repeat}" or key in seen):
            raise ValueError("unassigned_or_duplicate_sample_judgment")
        seen.add(key)
        group = by_id[gid]
        record = raw_by_id[row["response_id"]]
        response = record["raw_response"]
        if row["response_id"] in used:
            raise ValueError("sample_response_reused")
        used.add(row["response_id"])
        messages = sample_messages(group, repeat)
        order = [p["language"] for p in json.loads(messages[1]["content"])
                 ["prompts_in_randomized_order"]]
        if (record["profile"] != VERSION or record["request_key"] != key
                or record["messages"] != messages
                or record["messages_sha256"] != sha(messages)
                or record["schema_sha256"] != sha(sample_schema())
                or record["reasoning_effort"] != "high"
                or record["max_output_tokens"] != 16384
                or response["model"] != "gpt-5-2025-08-07"
                or row["returned_model"] != response["model"]
                or row["source_group_sha256"] != group["source_group_sha256"]
                or row["language_order"] != order):
            raise ValueError("sample_actual_input_or_model_mismatch")
        choices = response.get("choices", [])
        if len(choices) != 1 or choices[0]["finish_reason"] != "stop":
            raise ValueError("incomplete_sample_response")
        text = choices[0]["message"]["content"]
        try:
            assessment = validate_assessment(text, group)
        except (ValueError, TypeError) as error:
            if row["status"] != "INVALID" or row["instrument_error"] != str(error):
                raise ValueError("invalid_sample_status_mismatch") from error
            invalid.append({"request_key": key, "instrument_error": str(error)})
        else:
            if row["status"] != "VALID" or assessment != row["assessment"]:
                raise ValueError("saved_sample_assessment_mismatch")
        buckets[gid].append(row)
    outcomes = [aggregate(group, buckets[gid]) for gid, group in by_id.items()]
    return {
        "scope": "5_PERCENT_STRATIFIED_SAMPLE_LLM_BASED_NOT_HUMAN",
        "population_groups": 1920, "sample_groups": 96,
        "unsampled_groups_not_validated": 1824,
        "saved_judgments": len(rows),
        "valid_judgments": sum(row["status"] == "VALID" for row in rows),
        "group_outcomes": dict(Counter(row["outcome"] for row in outcomes)),
        "instrument_failures": invalid,
        "completed_sample_validation": not invalid,
        "completed_full_corpus_validation": False,
        "agreement": agreement(rows),
    }


def analyze(root=ROOT, draws=10000):
    provenance = verify_data(root)
    wording = wording_language(read_jsonl(root / "data/wording/workers.jsonl"), draws)
    return {
        "source_commit": provenance["source_commit"],
        "wording_language": wording,
        "neutral": neutral_analysis(root),
        "sampled_judge": judge_analysis(root),
        "paid_calls": 0,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draws", type=int, default=10000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 1 <= args.draws <= 100000:
        parser.error("--draws must be 1-100000")
    result = analyze(draws=args.draws)
    if args.output:
        if args.output.resolve().is_relative_to((ROOT / "data").resolve()):
            parser.error("Output must not overwrite the evidence directory")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({
        "wording_answers": 4320,
        "neutral_cases": result["neutral"]["returned"],
        "neutral_wrong_reports": result["neutral"]["known_wrong_reports"],
        "sampled_judge": {key: value for key, value in result["sampled_judge"].items()
                          if key not in ("agreement", "instrument_failures")},
        "paid_calls": 0,
    }, indent=2))


if __name__ == "__main__":
    main()
