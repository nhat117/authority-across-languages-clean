"""Post-review, task-blocked exploratory inference (not randomized causal tests)."""

import math
import random
from collections import Counter
from fractions import Fraction

SEED = 20261111


def percentile(values, p):
    return sorted(values)[min(len(values) - 1, int(p * len(values)))]


def bootstrap(values, draws=10000, seed=SEED):
    rng = random.Random(seed)
    means = [round(math.fsum(rng.choices(values, k=len(values))) / len(values), 12) for _ in range(draws)]
    return [percentile(means, .025), percentile(means, .975)]


def sign_flip_p(differences):
    """Exact task-level Rademacher test, conditional on sign-symmetry assumption."""
    fractions = [Fraction(x) for x in differences]
    scale = math.lcm(*(x.denominator for x in fractions))
    weights = [abs(int(x * scale)) for x in fractions if x]
    if not weights:
        return 1.0
    distribution = Counter({0: 1})
    for weight in weights:
        updated = Counter()
        for total, count in distribution.items():
            updated[total + weight] += count
            updated[total - weight] += count
        distribution = updated
    observed = abs(sum(int(x * scale) for x in fractions))
    return sum(n for k, n in distribution.items() if abs(k) >= observed) / 2 ** len(weights)


def holm(p_values):
    result = [None] * len(p_values)
    running = 0.0
    for rank, index in enumerate(sorted(range(len(p_values)), key=p_values.__getitem__)):
        running = max(running, min(1, p_values[index] * (len(p_values) - rank)))
        result[index] = running
    return result


def analyze(rows, outcomes, draws=10000):
    tasks = sorted({r["cluster"] for r in rows})
    if len(tasks) < 2:
        raise ValueError("need_multiple_tasks")
    paired = list(zip(rows, outcomes))

    def rate(task, record, field=None, level=None):
        subset = [(r, o) for r, o in paired if r["cluster"] == task and r["attack"]
                  and r["record_access"] == record and (field is None or r[field] == level)]
        if not subset:
            raise ValueError("missing_paired_cell")
        return Fraction(sum(o["target_relay"] is True for _, o in subset), len(subset))

    rates = []
    for record in ("absent", "stale", "correct"):
        for field, levels in (("language", ("en", "vi", "zh")), ("authority", (0, 1, 2, 3))):
            for level in levels:
                subset = [(r, o) for r, o in paired if r["attack"]
                          and r["record_access"] == record and r[field] == level]
                values = [float(rate(t, record, field, level)) for t in tasks]
                k = sum(o["target_relay"] is True for _, o in subset)
                invalid = sum(not o["format_valid"] for _, o in subset)
                rates.append(dict(record=record, factor=field, level=level, n=len(subset),
                                  k=k, rate=k / len(subset), invalid=invalid,
                                  identification_bounds=[k / len(subset), (k + invalid) / len(subset)],
                                  task_bootstrap_95=bootstrap(values, draws)))
    contrasts = []
    specs = [("language", a, b) for a, b in (("vi", "en"), ("zh", "en"), ("zh", "vi"))]
    specs += [("authority", a, 0) for a in (1, 2, 3)]
    for record in ("absent", "stale", "correct"):
        for field, a, b in specs:
            diffs = [rate(t, record, field, a) - rate(t, record, field, b) for t in tasks]
            contrasts.append(effect(diffs, draws, kind=field, record=record,
                                    level=a, reference=b))
    for record in ("absent", "stale"):
        for field, a, b in specs:
            diffs = [rate(t, record, field, a) - rate(t, record, field, b)
                     - rate(t, "correct", field, a) + rate(t, "correct", field, b) for t in tasks]
            contrasts.append(effect(diffs, draws, kind=field + "_by_record",
                                    record=record, record_reference="correct", level=a, reference=b))
        diffs = [rate(t, record) - rate(t, "correct") for t in tasks]
        contrasts.append(effect(diffs, draws, kind="record", record=record, reference="correct"))
    adjusted = holm([r["p_exact_sign_flip"] for r in contrasts])
    for row, p in zip(contrasts, adjusted):
        row.update(p_holm=p, family_size=len(contrasts),
                   exploratory_evidence_under_assumptions=p < .05)
    return {"rates": rates, "contrasts": contrasts, "tasks": tasks, "draws": draws,
            "seed": SEED, "registration": "post-review exploratory analysis",
            "test_assumption": "Task differences independent across tasks and sign-symmetric under null; not a randomization-based causal claim",
            "invalids": "Confirmed-relay lower indicator; unresolved-format bounds separate from bootstrap intervals",
            "constant_outcomes": "Zero-width empirical bootstrap intervals do not establish equivalence or a population safety bound"}


def effect(differences, draws, **labels):
    values = list(map(float, differences))
    return dict(labels, tasks=len(values), difference=float(sum(differences) / len(values)),
                task_bootstrap_95=bootstrap(values, draws),
                p_exact_sign_flip=sign_flip_p(differences),
                positive_tasks=sum(x > 0 for x in differences),
                negative_tasks=sum(x < 0 for x in differences),
                zero_tasks=sum(x == 0 for x in differences))
