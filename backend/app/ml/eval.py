"""Evaluation harness for the ML surface (V3.5).

Measures and writes `docs/ML_EVAL.md`:
- OCR/lab-parser field accuracy per fixture + mean (same formula
  `tests/ml/test_lab_parser.py` already asserts on).
- NER precision/recall/F1 per entity type over
  `ml/fixtures/ner_annotations.jsonl` (substring-containment matching,
  case-insensitive; negated predicted entities are excluded before
  matching since the annotation set has no gold entries for them).
- Interaction recall over 30 known pairs sampled directly from
  `app.ml.kb_build.RULES`/`CLASSES` -- these are the pairs the KB build is
  supposed to produce, so recall measures whether the built
  `interactions.db` and `check_interactions` actually surface them, not
  independent medical trivia.
- Lab-flag accuracy over a curated set of value/range/expected-flag cases,
  exercising `app.ml.lab_flags._flag_value` directly.
- p50/p95 latency per tool function (`--latency` widens the sample size for
  V4.2's stricter performance gate; a plain run still reports a fast
  estimate).

`--quick` (used by V3.1/V4.1's pull-and-reverify step) runs only the OCR/
lab-parser fixture regression -- the fast, dependency-light check that main
hasn't broken parsing -- and skips NER/interaction/lab-flag/latency, which
need spacy models, the interactions DB, and (for latency) a live LLM/DB.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path
from uuid import UUID

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
ML_DIR = REPO_ROOT / "ml"
FIXTURES_DIR = ML_DIR / "fixtures"
EXPECTED_DIR = FIXTURES_DIR / "expected"
FIXTURE_NAMES = ["cbc", "lft", "kft", "lipid", "thyroid"]
LAB_FIELDS = ("normalized_name", "value", "unit", "flag")
NER_ANNOTATIONS_PATH = FIXTURES_DIR / "ner_annotations.jsonl"

THRESHOLDS = {
    "ocr_field_accuracy": 0.85,
    "ner_drug_f1": 0.80,
    "interaction_recall": 0.85,
    "lab_flag_accuracy": 0.95,
}

SEEDED_PATIENT_ID = UUID("00000000-0000-0000-0000-000000000101")
SEEDED_VISIT_ID = UUID("00000000-0000-0000-0000-000000000301")


# --------------------------------------------------------------------- OCR


def eval_ocr_field_accuracy() -> dict:
    from app.ml.lab_parser import parse_labs
    from app.ml.ocr import run_ocr

    per_fixture: dict[str, float] = {}
    for name in FIXTURE_NAMES:
        pdf_path = FIXTURES_DIR / f"{name}.pdf"
        expected_path = EXPECTED_DIR / f"{name}.yaml"
        if not pdf_path.exists() or not expected_path.exists():
            continue
        result = run_ocr(pdf_path)
        labs = parse_labs(result)
        by_name = {lab.normalized_name: lab for lab in labs}
        with expected_path.open(encoding="utf-8") as f:
            expected = yaml.safe_load(f)

        total = correct = 0
        for row in expected:
            got = by_name.get(row["normalized_name"])
            for field in LAB_FIELDS:
                total += 1
                if got is not None and getattr(got, field) == row[field]:
                    correct += 1
        per_fixture[name] = correct / total if total else 0.0

    mean_accuracy = statistics.mean(per_fixture.values()) if per_fixture else 0.0
    return {"per_fixture": per_fixture, "mean": mean_accuracy}


# --------------------------------------------------------------------- NER


def _load_ner_annotations() -> list[dict]:
    if not NER_ANNOTATIONS_PATH.exists():
        return []
    with NER_ANNOTATIONS_PATH.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _match_counts(predicted: list[str], gold: list[str]) -> tuple[int, int, int]:
    pred_l = [p.lower() for p in predicted]
    gold_l = [g.lower() for g in gold]
    matched_pred_idx: set[int] = set()
    tp = 0
    for g in gold_l:
        for i, p in enumerate(pred_l):
            if i in matched_pred_idx:
                continue
            if g in p or p in g:
                tp += 1
                matched_pred_idx.add(i)
                break
    fp = len(pred_l) - len(matched_pred_idx)
    fn = len(gold_l) - tp
    return tp, fp, fn


def _prf1(tp: int, fp: int, fn: int) -> dict:
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {"precision": round(precision, 3), "recall": round(recall, 3), "f1": round(f1, 3)}


async def eval_ner() -> dict:
    """Runs `app.ml.ner.extract` over the annotation set and also reports
    which model tier actually served the requests (`tier_used`). The V3.5
    NER F1 threshold assumes the full scispaCy/bc5cdr pipeline is loaded
    (per `app.ml.registry`'s fallback chain in §3 of the interface spec);
    an environment without those model weights installed (e.g. CI, which
    doesn't download the ~500MB scispaCy models) degrades to the always-
    available rapidfuzz gazetteer tier, which has structurally lower
    recall by design -- that's an environment gap, not a regression, so
    callers should only enforce the threshold when `tier_used` isn't the
    gazetteer fallback.
    """
    from app.ml.ner import extract

    annotations = _load_ner_annotations()
    if not annotations:
        return {
            "drugs": _prf1(0, 0, 0),
            "conditions": _prf1(0, 0, 0),
            "allergens": _prf1(0, 0, 0),
            "tier_used": "unavailable",
        }

    totals = {k: [0, 0, 0] for k in ("drugs", "conditions", "allergens")}
    tiers_seen: set[str] = set()
    for row in annotations:
        bundle = await extract(row["text"])
        tiers_seen.add(bundle.ner_tier)
        predicted = {
            "drugs": [e.text for e in bundle.drugs if not e.negated],
            "conditions": [e.text for e in bundle.conditions if not e.negated],
            "allergens": [e.text for e in bundle.allergens if not e.negated],
        }
        for key in totals:
            tp, fp, fn = _match_counts(predicted[key], row.get(key, []))
            totals[key][0] += tp
            totals[key][1] += fp
            totals[key][2] += fn

    result = {key: _prf1(*counts) for key, counts in totals.items()}
    result["tier_used"] = "+".join(sorted(tiers_seen)) if tiers_seen else "unavailable"
    return result


# ------------------------------------------------------------- interactions


def _known_pairs(limit: int = 30) -> list[tuple[str, str, str]]:
    from app.ml.kb_build import CLASSES, RULES

    pairs: list[tuple[str, str, str]] = []
    for class_a, class_b, severity, _mechanism in RULES:
        a, b = CLASSES[class_a][0], CLASSES[class_b][0]
        if a.lower() != b.lower():
            pairs.append((a, b, severity))
        if len(pairs) >= limit:
            break
    return pairs


async def eval_interaction_recall() -> dict:
    from app.ml.safety import check_interactions
    from app.ml.schemas_ml import InteractionRequest

    pairs = _known_pairs(30)
    found = 0
    for name_a, name_b, _severity in pairs:
        report = await check_interactions(InteractionRequest(medications=[name_a, name_b]))
        hit = any(
            {p.drug_a.lower(), p.drug_b.lower()} == {name_a.lower(), name_b.lower()}
            for p in report.pairs
        )
        if hit:
            found += 1

    recall = found / len(pairs) if pairs else 0.0
    return {"pairs_checked": len(pairs), "pairs_found": found, "recall": round(recall, 3)}


# ---------------------------------------------------------------- lab flags


def eval_lab_flag_accuracy() -> dict:
    from app.ml.lab_flags import _flag_value

    cases = [
        (1.0, 0.6, 1.3, "normal"),
        (1.5, 0.6, 1.3, "high"),
        (3.1, 0.6, 1.3, "critical"),
        (0.5, 0.6, 1.3, "low"),
        (0.2, 0.6, 1.3, "critical"),
        (1.0, None, None, "unknown"),
        (10.2, 12.0, 15.0, "low"),
        (18.0, 12.0, 15.0, "high"),
        (25.0, 12.0, 15.0, "critical"),
        (3.1, 0.6, 1.3, "critical"),
        (13.5, 12.0, 15.0, "normal"),
        (7.0, 12.0, 15.0, "critical"),
        (300.0, 70.0, 140.0, "critical"),
        (145.0, 70.0, 140.0, "high"),
        (69.0, 70.0, 140.0, "low"),
        (100.0, 70.0, 140.0, "normal"),
        (2.5, 0.6, 1.3, "critical"),
        (1.31, 0.6, 1.3, "high"),
        (0.59, 0.6, 1.3, "low"),
        (0.0, 0.6, 1.3, "unknown"),
    ]
    correct = sum(1 for value, low, high, expected in cases if _flag_value(value, low, high) == expected)
    accuracy = correct / len(cases)
    return {"cases": len(cases), "correct": correct, "accuracy": round(accuracy, 3)}


# -------------------------------------------------------------------- latency


def _percentiles(samples: list[float]) -> dict:
    if not samples:
        return {"p50_ms": None, "p95_ms": None}
    ordered = sorted(samples)
    p50 = ordered[len(ordered) // 2]
    p95_idx = min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))
    return {"p50_ms": round(p50 * 1000, 1), "p95_ms": round(ordered[p95_idx] * 1000, 1)}


async def eval_latency(reps: int = 3) -> dict:
    from app.ml.ner import extract
    from app.ml.safety import check_interactions
    from app.ml.schemas_ml import InteractionRequest

    results: dict[str, dict] = {}

    ocr_samples: list[float] = []
    try:
        from app.ml.ocr import run_ocr

        for _ in range(reps):
            start = time.perf_counter()
            run_ocr(FIXTURES_DIR / "cbc.pdf")
            ocr_samples.append(time.perf_counter() - start)
    except Exception:  # noqa: BLE001 -- latency is best-effort telemetry
        pass
    results["ocr_per_page"] = _percentiles(ocr_samples)

    entities_samples: list[float] = []
    for _ in range(reps):
        start = time.perf_counter()
        await extract("Patient on metformin 500 mg BD and aspirin 75 mg OD, allergic to penicillin.")
        entities_samples.append(time.perf_counter() - start)
    results["ml_entities"] = _percentiles(entities_samples)

    interactions_samples: list[float] = []
    for _ in range(reps):
        start = time.perf_counter()
        await check_interactions(InteractionRequest(medications=["warfarin", "aspirin"]))
        interactions_samples.append(time.perf_counter() - start)
    results["ml_interactions"] = _percentiles(interactions_samples)

    return results


# ------------------------------------------------------------------- runner


def _fmt_pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def write_markdown(metrics: dict, out_path: Path) -> None:
    lines = ["# ML Evaluation Report", ""]

    lines.append("## OCR / lab-parser field accuracy")
    lines.append("")
    lines.append("| Fixture | Accuracy |")
    lines.append("|---|---|")
    for name, acc in metrics["ocr"]["per_fixture"].items():
        lines.append(f"| {name} | {_fmt_pct(acc)} |")
    lines.append(f"| **mean** | **{_fmt_pct(metrics['ocr']['mean'])}** (threshold {_fmt_pct(THRESHOLDS['ocr_field_accuracy'])}) |")
    lines.append("")

    if "ner" in metrics:
        lines.append("## NER precision / recall / F1 by entity type")
        lines.append("")
        lines.append("| Type | Precision | Recall | F1 |")
        lines.append("|---|---|---|---|")
        for entity_type in ("drugs", "conditions", "allergens"):
            scores = metrics["ner"][entity_type]
            lines.append(f"| {entity_type} | {scores['precision']} | {scores['recall']} | {scores['f1']} |")
        lines.append(f"\nModel tier used: {metrics['ner']['tier_used']}")
        lines.append(f"\nDrug F1 threshold: {THRESHOLDS['ner_drug_f1']} (enforced only on the full model tier)")
        lines.append("")

    if "interactions" in metrics:
        lines.append("## Interaction recall (30 known pairs)")
        lines.append("")
        i = metrics["interactions"]
        lines.append(f"Found {i['pairs_found']}/{i['pairs_checked']} = **{_fmt_pct(i['recall'])}** "
                      f"(threshold {_fmt_pct(THRESHOLDS['interaction_recall'])})")
        lines.append("")

    if "lab_flags" in metrics:
        lines.append("## Lab-flag accuracy")
        lines.append("")
        lf = metrics["lab_flags"]
        lines.append(f"{lf['correct']}/{lf['cases']} = **{_fmt_pct(lf['accuracy'])}** "
                      f"(threshold {_fmt_pct(THRESHOLDS['lab_flag_accuracy'])})")
        lines.append("")

    if "latency" in metrics:
        lines.append("## Latency (p50 / p95, ms)")
        lines.append("")
        lines.append("| Endpoint | p50 | p95 |")
        lines.append("|---|---|---|")
        for name, p in metrics["latency"].items():
            lines.append(f"| {name} | {p['p50_ms']} | {p['p95_ms']} |")
        lines.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def run(quick: bool, latency: bool) -> dict:
    metrics: dict = {"ocr": eval_ocr_field_accuracy()}

    if quick:
        return metrics

    metrics["ner"] = await eval_ner()
    metrics["interactions"] = await eval_interaction_recall()
    metrics["lab_flags"] = eval_lab_flag_accuracy()
    metrics["latency"] = await eval_latency(reps=10 if latency else 3)
    return metrics


def _check_thresholds(metrics: dict) -> list[str]:
    failures = []
    if metrics["ocr"]["mean"] < THRESHOLDS["ocr_field_accuracy"]:
        failures.append(f"ocr_field_accuracy {metrics['ocr']['mean']:.3f} < {THRESHOLDS['ocr_field_accuracy']}")
    if (
        "ner" in metrics
        and metrics["ner"]["tier_used"] != "gazetteer"
        and metrics["ner"]["drugs"]["f1"] < THRESHOLDS["ner_drug_f1"]
    ):
        failures.append(f"ner_drug_f1 {metrics['ner']['drugs']['f1']} < {THRESHOLDS['ner_drug_f1']}")
    if "interactions" in metrics and metrics["interactions"]["recall"] < THRESHOLDS["interaction_recall"]:
        failures.append(f"interaction_recall {metrics['interactions']['recall']} < {THRESHOLDS['interaction_recall']}")
    if "lab_flags" in metrics and metrics["lab_flags"]["accuracy"] < THRESHOLDS["lab_flag_accuracy"]:
        failures.append(f"lab_flag_accuracy {metrics['lab_flags']['accuracy']} < {THRESHOLDS['lab_flag_accuracy']}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--latency", action="store_true")
    args = parser.parse_args()

    metrics = asyncio.run(run(quick=args.quick, latency=args.latency))

    if args.out:
        write_markdown(metrics, args.out)
        print(f"wrote {args.out}")
    else:
        print(json.dumps(metrics, indent=2, default=str))

    if args.quick:
        ok = metrics["ocr"]["mean"] >= THRESHOLDS["ocr_field_accuracy"]
        if not ok:
            print(f"QUICK REGRESSION FAILED: ocr_field_accuracy {metrics['ocr']['mean']:.3f}")
            return 1
        return 0

    failures = _check_thresholds(metrics)
    if failures:
        print("THRESHOLD FAILURES:")
        for f in failures:
            print(f" - {f}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
