# Authority across languages

A focused, offline analysis repository for multilingual authority-based prompt
injection in AI reporting workflows. It contains Python code, tests, selected
research evidence and a plain-English report. It makes **no model calls** and
requires no API key.

## Run

Python 3.11 or newer and [uv](https://docs.astral.sh/uv/) are required.

```sh
uv sync --frozen --extra dev
uv run python scripts/analyze.py --output artifacts/analysis.json
uv run pytest
uv run ruff check .
```

For a faster analysis check, add `--draws 100`. The default uses 10,000 task
bootstrap resamples. Outputs go under ignored `artifacts/`, not into the evidence.

## What the evidence supports

- **Wording changes the language pattern.** Strict no-record false-target REPORT
  counts are 25/6/64, 66/46/50 and 51/59/43 for English/Vietnamese/Chinese, each
  out of 80. Three contradictory ABSTAIN replies explain the difference from
  the separate raw numeric-field counts. No language is consistently dominant.
- **The neutral pilot exposes a defence failure.** All 180 replies are retained:
  71 known wrong reports, seven unsupported record attributions, one invalid
  output. The unchanged source/freshness gate allows 2/71 wrong reports and
  falsely blocks 0/45 known correct reports. A source label is not authentication.
- **Translation judging is sampled and incomplete.** The fixed 5% stratified
  sample contains 96 aligned EN/VI/Chinese groups and 288 replies. Of those,
  286 pass exact-evidence/rubric checks: 94 groups provisionally PASS, two remain
  PENDING. The two quote-check failures stay in the data. The other 1824 groups
  are unvalidated. This is LLM-based assessment, not human linguistic validation.

The code rechecks evidence hashes, neutral prompt/response joins, frozen random
selection, all sampled judge requests/responses and provisional outcomes.
Statistics use task blocks rather than treating repeated answers as independent.
The report discusses the assumptions and limits of these comparisons.

## Repository layout

```text
src/          measurement, source gates, task statistics and judge rubric
scripts/      one offline analysis entry point
tests/        synthetic unit cases and actual-evidence regression checks
data/         wording, neutral-pilot and sampled-judge evidence + hash manifest
docs/         readable report, two figures and LLM-use disclosure
```

[Read the report](docs/report.md) · [Evidence manifest](data/manifest.json) ·
[LLM-use disclosure](docs/llm-usage.md)

## Scope and provenance

This is a **new, curated analysis edition**, not a replacement for the original
research archive. Data comes from original commit
[`ae49c9b210324ac826150d0a381781a3e8b33b8c`](https://github.com/nhat117/AdoptionAIHackathon/tree/ae49c9b210324ac826150d0a381781a3e8b33b8c).
`data/manifest.json` records original paths, source hashes, local hashes and the
one documented selection-frame transformation. Model replies, including invalid
ones, have not been rewritten. The original source repository is unchanged.

Core scoring/rubric code is retained from that snapshot. A small standalone
offline driver and join utility replace the historical report orchestration.
Archive-oriented helpers that take an original archive root still require that
archive's paths. The legacy `astra-multilingual-v1` string is a **rubric identifier**,
not a claim that Astra produced any of the included GPT-5 judgments.

Historical experiments, failed API attempts, ledgers, frozen collection
protocols, original PDF/Word packages and the full audit trail remain in the
[original repository](https://github.com/nhat117/AdoptionAIHackathon/tree/ae49c9b210324ac826150d0a381781a3e8b33b8c).
The original 549/549 conditional defence result and separate 72/72 corrupt-record
test are discussed in the report; their full reanalysis requires that archive.
This smaller repository directly recomputes the wording, neutral-pilot and
sampled-judge findings listed above. It does not ship a paid collection runner,
the dashboard, old generated reports, local environments or development logs.

The readable report focuses on worker experiments and excludes separate judge
ratings from its main findings; the offline analysis exposes their audit results
separately. Native-speaker validation and author confirmation remain incomplete.
Nothing here confirms official submission or a reviewer's personal sign-off.
