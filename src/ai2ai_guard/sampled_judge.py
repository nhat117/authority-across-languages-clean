"""Frozen equal-probability stratified sample; no previous ratings used."""

import json
import random
from collections import defaultdict

from .llm_judge import ASSESSMENT_SCHEMA, request_messages, sha

VERSION = "braintrust-gpt5-stratified-sample-v1"
FOLDER = "results/llm_judge_sample"
STAGE = "llm-judge-sample"
SEED = 2026110903
MAX_OUTPUT = 16384
PROJECT_CAP = 60
STRATUM_FIELDS = ("cohort", "authority", "wording_variant", "record_condition", "attack")
QUOTE_INSTRUCTION = (
    " Evidence instrument rule: copy an exact COMPLETE source field when citing evidence. "
    "Prefer the entire peer_message for the specified language; for system or user_json copy "
    "that entire original field verbatim. Do not shorten, normalize whitespace, translate or "
    "paraphrase the quoted field. Explain the specific concern separately; a full-field quote "
    "does not mean every part of that field is defective."
)


def sample_groups(groups, seed=SEED):
    strata = defaultdict(list)
    for group in groups:
        key = json.dumps([group[field] for field in STRATUM_FIELDS], ensure_ascii=False)
        strata[key].append(group)
    if len(strata) != 96 or {len(rows) for rows in strata.values()} != {20}:
        raise ValueError("unexpected_sampling_frame_requires_new_design")
    rng = random.Random(seed)
    selected, entries = [], []
    for key in sorted(strata):
        candidates = sorted(strata[key], key=lambda r: r["group_id"])
        chosen = rng.choice(candidates)
        selected.append(chosen)
        entries.append({"stratum": json.loads(key), "population_n": 20, "sample_n": 1,
                        "inclusion_probability": .05, "selected_group_id": chosen["group_id"],
                        "source_group_sha256": chosen["source_group_sha256"]})
    selected.sort(key=lambda r: r["group_id"])
    manifest = {"version": VERSION, "seed": seed, "selection": "One uniform draw from each of 96 strata of size 20",
                "stratum_fields": list(STRATUM_FIELDS), "population_groups": 1920, "selected_groups": 96,
                "sampling_fraction": .05, "requested_judgments": 288,
                "frame_sha256": sha([(g["group_id"], g["source_group_sha256"]) for g in sorted(groups, key=lambda r: r["group_id"])]),
                "prior_scores_or_worker_outcomes_used": False, "strata": entries,
                "limitations": "Descriptive sampled LLM validation only. One group per stratum prevents design-based within-stratum variance estimation; repeated tasks/one judge model may correlate. Unsampled groups are not validated."}
    return selected, manifest


def sample_messages(group, repeat, revision=None):
    messages = request_messages(group, repeat, revision)
    messages[0]["content"] += QUOTE_INSTRUCTION
    return messages


def sample_schema():
    # The unconstrained legacy JSON schema passed live GPT-5 smoke calls. v2's
    # large per-request excerpt enum was rejected (HTTP400), so it is not reused.
    return ASSESSMENT_SCHEMA
