"""Small evidence-join utility; full historical report generation is archived."""


def join(inputs, rows, complete=True):
    expected = {row["trial_id"]: row for row in inputs}
    ids = [row["trial_id"] for row in rows]
    if len(expected) != len(inputs) or len(ids) != len(set(ids)):
        raise ValueError("duplicate_trial_ids")
    if not set(ids) <= set(expected) or (complete and set(ids) != set(expected)):
        raise ValueError("missing_or_unassigned_trials")
    for row in rows:
        if any(row.get(key) != value for key, value in expected[row["trial_id"]].items()):
            raise ValueError("prompt_or_metadata_mismatch: " + row["trial_id"])
