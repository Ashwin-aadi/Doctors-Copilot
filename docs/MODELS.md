# Model registry

Every pretrained model, dataset, and knowledge source used by the ML/OCR/NLP
pipeline in `backend/app/ml/`. Nothing here is trained — everything is
downloaded, wrapped, and served, per the [autonomy contract](../CLAUDE.md).

`ml/download_models.py` bootstraps this list and writes measured size/load
time into `ml/.cache/manifest.json` on every run (idempotent — safe to
re-run). Run it after `pip install -r backend/requirements.txt`:

```bash
python ml/download_models.py
```

Fallback tiers are documented per-capability below; `backend/app/ml/registry.py`
implements the same chain and exposes `Registry.available()` for a live view.

> Outputs of this pipeline are decision support, not diagnosis, and require
> doctor review before acting. Data handling follows India's **DPDP Act
> 2023** and the **ABDM / EHR Standards for India 2016**.

---

## OCR

| Tier | Model | Task | License | Source |
|---|---|---|---|---|
| 1 (primary) | PaddleOCR `en` + `devanagari` (`use_angle_cls=True`) | Scene/document text detection + recognition, English and Devanagari | Apache-2.0 | https://github.com/PaddlePaddle/PaddleOCR |
| 2 (fallback) | Tesseract via `pytesseract` (`--psm 6 --oem 3 -l eng+hin`) | OCR, English + Hindi | Apache-2.0 | https://github.com/tesseract-ocr/tesseract |
| 3 (fallback) | PyMuPDF embedded-text layer | Extract existing text layer from digitally-produced PDFs (no OCR needed) | AGPL-3.0 / commercial (PyMuPDF dual license — used read-only, no redistribution) | https://pymupdf.readthedocs.io |

Layout/tables: PaddleOCR PP-Structure (tier 1) -> y-centroid row clustering (tier 2, no model) -> regex line parser (tier 3, no model).

## Biomedical / clinical NER

| Tier | Model | Task | License | Source |
|---|---|---|---|---|
| 1 (primary) | scispaCy `en_core_sci_sm` | General biomedical NER + tokenization | MIT | https://allenai.github.io/scispacy/ |
| 1 (primary) | scispaCy `en_ner_bc5cdr_md` | Chemical/disease NER (BC5CDR) | MIT | https://allenai.github.io/scispacy/ |
| 2 (fallback) | HF `d4data/biomedical-ner-all` | Biomedical NER (drugs, conditions, dosage) | Apache-2.0 | https://huggingface.co/d4data/biomedical-ner-all |
| 3 (fallback) | Gazetteer + `rapidfuzz` over RxNorm generics + Indian brand names | Fuzzy dictionary match | project data (`ml/data/india_brands.csv`, `ml/data/ner_gazetteer_seed.yaml`) | n/a |

## Negation

| Tier | Model | Task | License | Source |
|---|---|---|---|---|
| 1 (primary) | `negspacy` | Negation/uncertainty detection over spaCy spans | MIT | https://github.com/jenojp/negspacy |
| 2 (fallback) | Rule list `ml/data/negation_cues.yaml` | Cue-window negation | project data | n/a |

## Drug interactions

| Tier | Source | Task | License | URL |
|---|---|---|---|---|
| 1 (primary) | DDInter 2.0 CSV | Pairwise drug-drug interaction severity + mechanism | free for research/academic use | http://ddinter.scbdd.com/ |
| 2 (fallback) | CDSCO / National Formulary of India (NFI) label text | Interactions/contraindications for NLEM ingredients | Government of India public domain | https://cdsco.gov.in |
| 2 (fallback) | openFDA `drug/label.json` (`drug_interactions` section) | US label text, used as a secondary corroborating source | public domain (US Gov) | https://open.fda.gov/apis/drug/label/ |
| 3 (fallback) | Bundled `ml/data/interactions_seed.csv` (>=800 pairs, built in V2.3) | Authored fallback pairs, sourced from public labelling | project data | n/a |

## Summary / ranking LLM

| Model | Task | License | Source |
|---|---|---|---|
| `app.llm.gateway` (Ashwin's gateway; Groq `llama-3.3-70b-versatile` primary, Ollama `llama3.1:8b` fallback) | SOAP summary generation, structured JSON completion | see `docs/DECISIONS.md` / Ashwin's model card | n/a — imported, never instantiated separately |

---

## Measured footprint

Populated by `ml/download_models.py` on each run; see `ml/.cache/manifest.json`
for the machine-readable version (`status: ok|unavailable`, `size_bytes`,
`elapsed_s`). RAM figures below are steady-state process RSS estimates from
upstream documentation, pending an on-box measurement in V4.2/V5.3.

| Model | Size (approx, on disk) | RAM (approx) | Load time (this box) |
|---|---|---|---|
| PaddleOCR `en` | ~15 MB (det+rec+cls) | ~500 MB | see manifest.json |
| PaddleOCR `devanagari` | ~15 MB | ~500 MB | see manifest.json |
| Tesseract (system binary, not pip-managed) | ~30 MB per language pack | ~150 MB | n/a (system install, not bootstrapped by this script) |
| scispaCy `en_core_sci_sm` | ~15 MB | ~300 MB | see manifest.json |
| scispaCy `en_ner_bc5cdr_md` | ~50 MB | ~400 MB | see manifest.json |
| HF `d4data/biomedical-ner-all` | ~420 MB (safetensors) | ~1.2 GB | see manifest.json |
| `negspacy` | <1 MB (rule package, no weights) | negligible | see manifest.json |

**Known limitations (initial pass, expanded in V5.3):**
- PaddleOCR `devanagari` is tuned for printed Devanagari; handwritten
  prescription shorthand (OD/BD/TDS mixed with Devanagari) is handled by the
  V4.5 fixture but expect lower confidence — surfaced via `confidence` for
  doctor review, never silently accepted.
- `d4data/biomedical-ner-all` is trained on US/European clinical text; Indian
  brand names are resolved via the gazetteer/`india_brands.csv` tier *before*
  falling through to this model, not by relying on this model to know them.
- This dev machine has no system Tesseract binary and no MSVC C++ Build
  Tools; local verification therefore exercises the PyMuPDF OCR fallback
  tier and skips `chromadb`-dependent installs. See `docs/DECISIONS.md`.
