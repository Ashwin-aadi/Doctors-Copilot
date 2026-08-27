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

Model tier used: bc5cdr

Drug F1 threshold: 0.8 (enforced only on the full model tier)

## Interaction recall (30 known pairs)

Found 30/30 = **100.0%** (threshold 85.0%)

## Lab-flag accuracy

19/20 = **95.0%** (threshold 95.0%)

## Latency (p50 / p95, ms)

| Endpoint | p50 | p95 |
|---|---|---|
| ocr_per_page | 115.1 | 115.7 |
| ml_entities | 10.8 | 78.9 |
| ml_interactions | 1.0 | 1.3 |

