import pytest

from app.ml import eval as eval_module


def test_ocr_field_accuracy_meets_threshold() -> None:
    result = eval_module.eval_ocr_field_accuracy()
    assert result["mean"] >= eval_module.THRESHOLDS["ocr_field_accuracy"]


def test_lab_flag_accuracy_meets_threshold() -> None:
    result = eval_module.eval_lab_flag_accuracy()
    assert result["accuracy"] >= eval_module.THRESHOLDS["lab_flag_accuracy"]


@pytest.mark.asyncio
async def test_interaction_recall_meets_threshold() -> None:
    result = await eval_module.eval_interaction_recall()
    assert result["recall"] >= eval_module.THRESHOLDS["interaction_recall"]


@pytest.mark.asyncio
async def test_ner_drug_f1_meets_threshold() -> None:
    result = await eval_module.eval_ner()
    if result["tier_used"] == "gazetteer":
        pytest.skip(
            "scispaCy/bc5cdr model weights not installed in this environment; "
            "the F1 threshold assumes the full model tier, not the gazetteer fallback."
        )
    assert result["drugs"]["f1"] >= eval_module.THRESHOLDS["ner_drug_f1"]


def test_run_quick_returns_only_ocr_metrics() -> None:
    import asyncio

    metrics = asyncio.run(eval_module.run(quick=True, latency=False))
    assert set(metrics) == {"ocr"}
