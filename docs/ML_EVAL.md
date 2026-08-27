# ML Evaluation Report

## OCR / lab-parser field accuracy

| Fixture | Accuracy |
|---|---|
| cbc | 100.0% |
| lft | 100.0% |
| kft | 100.0% |
| lipid | 100.0% |
| thyroid | 100.0% |
| **mean** | **100.0%** (threshold 85.0%) |

## NER precision / recall / F1 by entity type

| Type | Precision | Recall | F1 |
|---|---|---|---|
| drugs | 0.952 | 0.909 | 0.93 |
| conditions | 0.302 | 0.905 | 0.452 |
| allergens | 0.75 | 1.0 | 0.857 |

Drug F1 threshold: 0.8

## Interaction recall (30 known pairs)

Found 30/30 = **100.0%** (threshold 85.0%)

## Lab-flag accuracy

19/20 = **95.0%** (threshold 95.0%)

## Latency (p50 / p95, ms)

| Endpoint | p50 | p95 |
|---|---|---|
| ocr_per_page | 106.2 | 107.4 |
| ml_entities | 10.3 | 87.8 |
| ml_interactions | 0.9 | 1.2 |

