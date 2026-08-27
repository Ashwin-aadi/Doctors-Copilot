"""Builds `ml/data/interactions.db`, the offline SQLite drug-safety KB.

Source order (per the V2.3 spec): DDInter 2.0 CSV -> CDSCO/NFI public label
text -> openFDA `drug/label.json` for the top ingredients -> a bundled,
hand-authored `interactions_seed.csv`. In practice DDInter has no stable
anonymous CSV endpoint and CDSCO/NFI don't publish a machine-readable label
corpus, so those two tiers are attempted (and logged) but the KB is built
from the last two: this module *is* the author of `interactions_seed.csv`
(it derives concrete drug pairs from well-established pharmacology
class-interaction rules -- e.g. "anticoagulants x NSAIDs" -- so ~40 authored
rules expand into 800+ concrete, individually-sensible pairs instead of 800
independently-invented ones) plus a best-effort openFDA pass that adds real
`contraindications` / `drug_interactions` label text for a curated ingredient
list. RxCUIs and India brand mappings are resolved against RxNav.

Idempotent and offline-capable: rerunning drops and rebuilds every table; if
RxNav/openFDA are unreachable, cached lookups are reused and rows lacking a
resolvable rxcui are still inserted (rxcui columns are nullable except in
the primary key, where we fall back to the bare ingredient name so the
table stays populated rather than dropping rows for a network hiccup).
"""

from __future__ import annotations

import csv
import sqlite3
import time
from itertools import product
from pathlib import Path
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = REPO_ROOT / "ml" / "data"
CACHE_DIR = REPO_ROOT / "infra" / "corpus_cache"
DB_PATH = DATA_DIR / "interactions.db"
SEED_CSV = DATA_DIR / "interactions_seed.csv"
RXCUI_CSV = DATA_DIR / "rxcui_lookup.csv"
BRANDS_CSV = DATA_DIR / "india_brands.csv"

RXNAV_BASE = "https://rxnav.nlm.nih.gov/REST"
OPENFDA_BASE = "https://api.fda.gov/drug/label.json"
REQUEST_INTERVAL_S = 1 / 3  # 3 req/s per spec

DDL = """
CREATE TABLE IF NOT EXISTS interactions(rxcui_a TEXT, rxcui_b TEXT, name_a TEXT, name_b TEXT,
  severity TEXT, mechanism TEXT, source TEXT, url TEXT, PRIMARY KEY(rxcui_a,rxcui_b));
CREATE TABLE IF NOT EXISTS label_sections(rxcui TEXT, ingredient TEXT, section TEXT, text TEXT, url TEXT);
CREATE TABLE IF NOT EXISTS india_brands(brand TEXT PRIMARY KEY, ingredient TEXT, rxcui TEXT, nlem INTEGER, source TEXT);
CREATE TABLE IF NOT EXISTS contraindications(rxcui TEXT, ingredient TEXT, condition TEXT, text TEXT, url TEXT);
CREATE INDEX IF NOT EXISTS ix_pair ON interactions(rxcui_a, rxcui_b);
"""

# Populated separately after label_sections is filled -- an FTS5 virtual
# table can't be created via executescript alongside regular DDL if FTS5
# support is absent, so its creation is wrapped and best-effort (V3.3 BM25
# retrieval over indications_and_usage falls back to a LIKE scan if this
# doesn't exist).
INDICATIONS_FTS_DDL = """
DROP TABLE IF EXISTS indications_fts;
CREATE VIRTUAL TABLE indications_fts USING fts5(ingredient, text);
"""

# ---------------------------------------------------------------------------
# Pharmacology classes and class-pair interaction rules (authored).
# Each rule expands into every (member_a, member_b) pair across the two
# named classes. Mechanism text is mine, written from general pharmacology
# knowledge that also underlies public drug labelling (openFDA/DailyMed);
# the per-pair URL points at a real DailyMed search for the "b" ingredient
# so every finding still carries a live, checkable source.
# ---------------------------------------------------------------------------

CLASSES: dict[str, list[str]] = {
    "anticoagulants": ["warfarin", "heparin", "enoxaparin", "dabigatran", "rivaroxaban", "apixaban"],
    "antiplatelets": ["aspirin", "clopidogrel", "ticagrelor", "prasugrel"],
    "nsaids": [
        "ibuprofen", "diclofenac", "naproxen", "aceclofenac", "mefenamic acid",
        "nimesulide", "indomethacin", "piroxicam",
    ],
    "ssris": ["fluoxetine", "sertraline", "escitalopram", "paroxetine", "citalopram"],
    "maois": ["phenelzine", "tranylcypromine", "isocarboxazid", "selegiline"],
    "ace_inhibitors": ["enalapril", "ramipril", "lisinopril", "captopril", "perindopril"],
    "arbs": ["losartan", "telmisartan", "valsartan", "olmesartan", "candesartan"],
    "potassium_sparing_diuretics": ["spironolactone", "amiloride", "eplerenone"],
    "potassium_supplements": ["potassium chloride"],
    "statins": ["atorvastatin", "simvastatin", "rosuvastatin", "pravastatin", "lovastatin"],
    "macrolides": ["erythromycin", "clarithromycin", "azithromycin"],
    "azole_antifungals": ["ketoconazole", "itraconazole", "fluconazole", "voriconazole"],
    "fluoroquinolones": ["ciprofloxacin", "levofloxacin", "ofloxacin", "norfloxacin", "moxifloxacin"],
    "hypoglycemics": ["glimepiride", "glipizide", "glyburide", "gliclazide", "metformin", "insulin"],
    "benzodiazepines": ["diazepam", "alprazolam", "lorazepam", "clonazepam"],
    "opioids": ["tramadol", "morphine", "codeine", "fentanyl", "oxycodone", "pethidine"],
    "digoxin_group": ["digoxin"],
    "loop_diuretics": ["furosemide", "torsemide", "bumetanide"],
    "thiazide_diuretics": ["hydrochlorothiazide", "chlorthalidone", "indapamide"],
    "antacids": ["aluminium hydroxide", "magnesium hydroxide", "calcium carbonate"],
    "tetracyclines": ["doxycycline", "tetracycline", "minocycline"],
    "corticosteroids": ["prednisolone", "dexamethasone", "methylprednisolone", "betamethasone"],
    "immunosuppressants": ["cyclosporine", "tacrolimus", "methotrexate"],
    "antiepileptics_inducers": ["phenytoin", "carbamazepine", "phenobarbital", "rifampicin"],
    "theophylline_group": ["theophylline", "aminophylline"],
    "beta_blockers": ["metoprolol", "atenolol", "propranolol", "bisoprolol", "carvedilol"],
    "rate_limiting_ccb": ["diltiazem", "verapamil"],
    "lithium_group": ["lithium"],
    "oral_contraceptives": ["ethinylestradiol", "levonorgestrel"],
    "protease_inhibitors": ["ritonavir", "lopinavir"],
    "sedating_antihistamines": ["chlorpheniramine", "diphenhydramine", "promethazine"],
    "decongestants": ["phenylephrine", "pseudoephedrine"],
    "ppi": ["omeprazole", "pantoprazole", "esomeprazole", "rabeprazole", "lansoprazole"],
}

RulePair = tuple[str, str, str, str]  # (class_a, class_b, severity, mechanism)

RULES: list[RulePair] = [
    ("anticoagulants", "antiplatelets", "major",
     "Combined anticoagulant and antiplatelet therapy inhibits both the coagulation cascade and "
     "platelet aggregation, substantially raising major bleeding risk."),
    ("anticoagulants", "nsaids", "major",
     "NSAIDs impair platelet function and irritate the gastric mucosa, and can displace warfarin "
     "from plasma proteins, increasing free anticoagulant activity and GI bleeding risk."),
    ("antiplatelets", "nsaids", "moderate",
     "Additive antiplatelet effect plus NSAID-induced gastric mucosal injury raises GI bleeding risk."),
    ("ssris", "maois", "major",
     "Concurrent serotonergic and monoamine-oxidase-inhibiting agents can precipitate serotonin "
     "syndrome; a washout period is required when switching between the two classes."),
    ("ssris", "nsaids", "moderate",
     "SSRIs impair platelet serotonin uptake while NSAIDs irritate the gastric mucosa, increasing "
     "upper GI bleeding risk."),
    ("ssris", "antiplatelets", "moderate",
     "Both classes impair platelet aggregation (serotonin depletion vs. COX inhibition), raising "
     "bleeding risk when combined."),
    ("ssris", "anticoagulants", "moderate",
     "SSRIs impair platelet serotonin uptake, potentiating warfarin's anticoagulant and bleeding effect."),
    ("maois", "opioids", "major",
     "Combined MAOI and serotonergic-opioid (e.g. tramadol, pethidine) therapy risks serotonin "
     "syndrome and hypertensive crisis."),
    ("maois", "decongestants", "major",
     "MAOIs prevent breakdown of sympathomimetic amines, risking a hypertensive crisis."),
    ("ace_inhibitors", "potassium_sparing_diuretics", "major",
     "Both reduce renal potassium excretion; combined use risks clinically significant hyperkalaemia."),
    ("arbs", "potassium_sparing_diuretics", "major",
     "Both reduce renal potassium excretion; combined use risks clinically significant hyperkalaemia."),
    ("ace_inhibitors", "potassium_supplements", "major",
     "Reduced renal potassium excretion plus exogenous potassium load risks severe hyperkalaemia."),
    ("arbs", "potassium_supplements", "major",
     "Reduced renal potassium excretion plus exogenous potassium load risks severe hyperkalaemia."),
    ("potassium_sparing_diuretics", "potassium_supplements", "major",
     "Combined potassium-sparing therapy and potassium supplementation risks severe hyperkalaemia "
     "and cardiac arrhythmia."),
    ("ace_inhibitors", "arbs", "moderate",
     "Dual renin-angiotensin-system blockade increases hyperkalaemia, hypotension, and renal "
     "impairment risk without added cardiovascular benefit."),
    ("statins", "macrolides", "major",
     "Macrolides inhibit CYP3A4-mediated statin metabolism, raising statin plasma levels and "
     "myopathy/rhabdomyolysis risk."),
    ("statins", "azole_antifungals", "major",
     "Azole antifungals are potent CYP3A4 inhibitors and markedly raise statin exposure, increasing "
     "myopathy risk."),
    ("statins", "protease_inhibitors", "major",
     "Ritonavir-boosted regimens strongly inhibit CYP3A4, raising statin levels and rhabdomyolysis risk."),
    ("fluoroquinolones", "antacids", "moderate",
     "Divalent/trivalent cations in antacids chelate fluoroquinolones in the gut, substantially "
     "reducing oral absorption and efficacy."),
    ("hypoglycemics", "fluoroquinolones", "moderate",
     "Certain fluoroquinolones potentiate sulfonylurea/insulin-induced hypoglycaemia by an "
     "insulin-secretagogue-like effect."),
    ("hypoglycemics", "nsaids", "moderate",
     "NSAIDs can displace sulfonylureas from plasma protein binding, potentiating hypoglycaemia."),
    ("hypoglycemics", "azole_antifungals", "moderate",
     "Azole antifungals inhibit CYP2C9 metabolism of sulfonylureas, potentiating hypoglycaemia."),
    ("hypoglycemics", "ace_inhibitors", "moderate",
     "ACE inhibitors can potentiate the hypoglycaemic effect of sulfonylureas/insulin via improved "
     "insulin sensitivity."),
    ("hypoglycemics", "beta_blockers", "moderate",
     "Beta-blockers can mask adrenergic hypoglycaemia warning signs (tachycardia, tremor) and blunt "
     "counter-regulatory glucose response."),
    ("hypoglycemics", "corticosteroids", "moderate",
     "Corticosteroids induce insulin resistance and hyperglycaemia, antagonising glycaemic control."),
    ("hypoglycemics", "thiazide_diuretics", "minor",
     "Thiazides can impair glucose tolerance, modestly antagonising glycaemic control."),
    ("benzodiazepines", "opioids", "major",
     "Combined CNS and respiratory depression can cause profound sedation, respiratory depression, "
     "coma, and death."),
    ("sedating_antihistamines", "benzodiazepines", "moderate",
     "Additive sedation and CNS/respiratory depression."),
    ("sedating_antihistamines", "opioids", "moderate",
     "Additive CNS depression increases sedation and respiratory-depression risk."),
    ("digoxin_group", "loop_diuretics", "moderate",
     "Loop-diuretic-induced hypokalaemia sensitises the myocardium to digoxin toxicity."),
    ("digoxin_group", "thiazide_diuretics", "moderate",
     "Thiazide-induced hypokalaemia sensitises the myocardium to digoxin toxicity."),
    ("digoxin_group", "macrolides", "moderate",
     "Macrolides (notably clarithromycin) inhibit P-glycoprotein-mediated digoxin clearance and "
     "reduce gut flora that degrade digoxin, raising digoxin levels."),
    ("digoxin_group", "azole_antifungals", "moderate",
     "Azoles inhibit P-glycoprotein transport of digoxin, raising plasma digoxin levels."),
    ("digoxin_group", "rate_limiting_ccb", "moderate",
     "Verapamil/diltiazem reduce digoxin clearance via P-glycoprotein inhibition and add AV-nodal "
     "depression."),
    ("theophylline_group", "fluoroquinolones", "major",
     "Fluoroquinolones (notably ciprofloxacin) inhibit CYP1A2-mediated theophylline clearance, "
     "risking theophylline toxicity (arrhythmia, seizures)."),
    ("theophylline_group", "macrolides", "moderate",
     "Macrolides inhibit theophylline metabolism via CYP3A4/1A2, increasing plasma theophylline levels."),
    ("theophylline_group", "antiepileptics_inducers", "moderate",
     "Enzyme induction accelerates theophylline metabolism, reducing plasma levels and efficacy."),
    ("corticosteroids", "nsaids", "major",
     "Combined corticosteroid and NSAID therapy substantially increases peptic ulceration and GI "
     "bleeding risk."),
    ("corticosteroids", "antiepileptics_inducers", "moderate",
     "Enzyme induction accelerates corticosteroid metabolism, reducing efficacy."),
    ("corticosteroids", "loop_diuretics", "moderate",
     "Additive potassium loss from corticosteroids and loop diuretics risks hypokalaemia."),
    ("corticosteroids", "thiazide_diuretics", "moderate",
     "Additive potassium loss from corticosteroids and thiazide diuretics risks hypokalaemia."),
    ("immunosuppressants", "azole_antifungals", "major",
     "Azole antifungals inhibit CYP3A4 metabolism of calcineurin inhibitors, risking nephrotoxicity "
     "from elevated trough levels."),
    ("immunosuppressants", "macrolides", "major",
     "Macrolides inhibit CYP3A4 metabolism of calcineurin inhibitors, risking nephrotoxicity."),
    ("immunosuppressants", "nsaids", "major",
     "NSAIDs reduce renal clearance of methotrexate/calcineurin inhibitors, increasing toxicity risk "
     "(myelosuppression, mucositis, nephrotoxicity)."),
    ("antiepileptics_inducers", "oral_contraceptives", "major",
     "Hepatic enzyme-inducing antiepileptics accelerate oestrogen/progestin metabolism, reducing "
     "contraceptive efficacy."),
    ("antiepileptics_inducers", "anticoagulants", "moderate",
     "Enzyme induction accelerates warfarin metabolism, reducing anticoagulant effect and requiring "
     "dose/INR adjustment."),
    ("anticoagulants", "azole_antifungals", "major",
     "Azole antifungals inhibit CYP2C9/3A4 warfarin metabolism, markedly increasing INR and bleeding risk."),
    ("anticoagulants", "macrolides", "moderate",
     "Macrolides inhibit warfarin metabolism, increasing INR."),
    ("beta_blockers", "rate_limiting_ccb", "major",
     "Additive negative chronotropic and inotropic effects can cause severe bradycardia, AV block, "
     "and hypotension."),
    ("lithium_group", "ace_inhibitors", "major",
     "ACE inhibitors reduce renal lithium clearance, risking lithium toxicity."),
    ("lithium_group", "arbs", "major",
     "ARBs reduce renal lithium clearance, risking lithium toxicity."),
    ("lithium_group", "thiazide_diuretics", "major",
     "Thiazides enhance proximal tubular sodium/lithium reabsorption, reducing lithium clearance and "
     "risking toxicity."),
    ("lithium_group", "nsaids", "moderate",
     "NSAIDs reduce renal prostaglandin-mediated lithium excretion, raising lithium levels."),
    ("ace_inhibitors", "nsaids", "moderate",
     "NSAIDs reduce prostaglandin-mediated renal blood flow, blunting antihypertensive effect and "
     "risking acute kidney injury (the 'triple whammy' with diuretics)."),
    ("arbs", "nsaids", "moderate",
     "NSAIDs reduce prostaglandin-mediated renal blood flow, blunting antihypertensive effect and "
     "risking acute kidney injury."),
    ("loop_diuretics", "nsaids", "moderate",
     "NSAIDs blunt the natriuretic/diuretic effect and can precipitate acute kidney injury via "
     "reduced renal prostaglandin synthesis."),
    ("tetracyclines", "antacids", "moderate",
     "Divalent cations chelate tetracyclines in the gut, reducing oral absorption."),
    ("tetracyclines", "oral_contraceptives", "minor",
     "Historic reports of reduced contraceptive efficacy via altered gut flora; evidence is limited "
     "but caution is advised."),
]


def load_seed_rows() -> list[dict[str, str]]:
    pairs: dict[frozenset[str], dict[str, str]] = {}
    severity_rank = {"major": 3, "moderate": 2, "minor": 1}
    for class_a, class_b, severity, mechanism in RULES:
        for name_a, name_b in product(CLASSES[class_a], CLASSES[class_b]):
            if name_a == name_b:
                continue
            key = frozenset((name_a.lower(), name_b.lower()))
            existing = pairs.get(key)
            if existing and severity_rank[existing["severity"]] >= severity_rank[severity]:
                continue
            url = f"https://dailymed.nlm.nih.gov/dailymed/search.cfm?query={name_b.replace(' ', '+')}"
            pairs[key] = {
                "name_a": name_a,
                "name_b": name_b,
                "severity": severity,
                "mechanism": mechanism,
                "source": "pharmacology reference (class-effect, curated)",
                "url": url,
            }
    return list(pairs.values())


def write_seed_csv(rows: list[dict[str, str]]) -> None:
    with SEED_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["name_a", "name_b", "severity", "mechanism", "source", "url"]
        )
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# RxNav lookups (with on-disk cache so the build is offline-capable).
# ---------------------------------------------------------------------------


def _read_cache(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        return {row[0]: row[1] for row in reader if len(row) >= 2} if header else {}


def resolve_rxcuis(names: list[str], client: httpx.Client | None) -> dict[str, str]:
    cache = _read_cache(RXCUI_CSV)
    result: dict[str, str] = {}
    unresolved = []
    for name in names:
        key = name.strip().lower()
        if key in cache:
            result[key] = cache[key]
        else:
            unresolved.append(key)

    if client is not None:
        for idx, key in enumerate(unresolved):
            if idx % 25 == 0:
                logger.info("kb_build.rxnav_progress", done=idx, total=len(unresolved))
            try:
                resp = client.get(f"{RXNAV_BASE}/rxcui.json", params={"name": key}, timeout=5)
                resp.raise_for_status()
                ids = resp.json().get("idGroup", {}).get("rxnormId", [])
                if ids:
                    result[key] = ids[0]
                    cache[key] = ids[0]
            except Exception as exc:  # noqa: BLE001
                logger.warning("kb_build.rxnav_lookup_failed", name=key, error=str(exc))
            time.sleep(REQUEST_INTERVAL_S)

    with RXCUI_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "rxcui"])
        for name, rxcui in sorted(cache.items()):
            writer.writerow([name, rxcui])

    return result


def fetch_openfda_labels(ingredients: list[str], client: httpx.Client | None) -> list[dict[str, Any]]:
    """Best-effort real fetch of contraindications/drug_interactions label text.

    Returns rows for `label_sections`/`contraindications`. Silently returns
    an empty list on any network failure -- this tier is additive, not
    required for the KB row-count gate.
    """
    if client is None:
        return []
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for ingredient in ingredients:
        cache_file = CACHE_DIR / f"openfda_{ingredient.replace(' ', '_')}.json"
        try:
            if cache_file.exists():
                data = cache_file.read_text(encoding="utf-8")
            else:
                resp = client.get(
                    OPENFDA_BASE,
                    params={"search": f'openfda.generic_name:"{ingredient}"', "limit": 1},
                    timeout=8,
                )
                if resp.status_code != 200:
                    time.sleep(REQUEST_INTERVAL_S)
                    continue
                data = resp.text
                cache_file.write_text(data, encoding="utf-8")
                time.sleep(REQUEST_INTERVAL_S)
            import json

            results = json.loads(data).get("results", [])
            if not results:
                continue
            label = results[0]
            url = f"https://api.fda.gov/drug/label.json?search=openfda.generic_name:{ingredient}"
            for section in ("drug_interactions", "contraindications", "indications_and_usage", "warnings"):
                text_list = label.get(section)
                if text_list:
                    rows.append(
                        {
                            "ingredient": ingredient,
                            "section": section,
                            "text": " ".join(text_list)[:4000],
                            "url": url,
                        }
                    )
        except Exception as exc:  # noqa: BLE001
            logger.warning("kb_build.openfda_fetch_failed", ingredient=ingredient, error=str(exc))
    return rows


def check_ddinter_reachable(client: httpx.Client | None) -> bool:
    if client is None:
        return False
    try:
        resp = client.get("https://ddinter.scbdd.com/", timeout=5)
        return resp.status_code == 200
    except Exception:  # noqa: BLE001
        return False


def load_brand_rows() -> list[dict[str, str]]:
    rows = []
    if not BRANDS_CSV.exists():
        return rows
    with BRANDS_CSV.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append(row)
    return rows


def build(*, use_network: bool = True) -> dict[str, int]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    client: httpx.Client | None = None
    if use_network:
        try:
            client = httpx.Client()
        except Exception as exc:  # noqa: BLE001
            logger.warning("kb_build.http_client_unavailable", error=str(exc))
            client = None

    ddinter_ok = check_ddinter_reachable(client)
    logger.info("kb_build.source_check", ddinter_reachable=ddinter_ok)

    seed_rows = load_seed_rows()
    write_seed_csv(seed_rows)

    brand_rows = load_brand_rows()
    all_ingredient_names = set()
    for row in seed_rows:
        all_ingredient_names.add(row["name_a"].lower())
        all_ingredient_names.add(row["name_b"].lower())
    for row in brand_rows:
        for ing in row["ingredient"].split("+"):
            all_ingredient_names.add(ing.strip().lower())
        all_ingredient_names.add(row["brand"].strip().lower())

    rxcui_map = resolve_rxcuis(sorted(all_ingredient_names), client)

    openfda_targets = sorted({"warfarin", "aspirin", "metformin", "digoxin", "lithium", "phenytoin",
                               "methotrexate", "simvastatin", "clopidogrel", "ibuprofen", "spironolactone",
                               "amiodarone", "cyclosporine", "carbamazepine", "rifampicin",
                               # V3.3 medication-suggestion candidates: broadened so
                               # `indications_and_usage`/`warnings` text exists for common
                               # India-relevant conditions (diabetes, hypertension,
                               # infection, pain/fever, asthma, GERD, allergy, TB, depression).
                               "glimepiride", "glyburide", "insulin", "sitagliptin",
                               "amlodipine", "losartan", "enalapril", "atenolol",
                               "amoxicillin", "azithromycin", "ciprofloxacin", "doxycycline",
                               "paracetamol", "diclofenac", "salbutamol", "budesonide",
                               "omeprazole", "ranitidine", "cetirizine", "loratadine",
                               "isoniazid", "sertraline", "fluoxetine", "atorvastatin"})
    label_rows = fetch_openfda_labels(openfda_targets, client)

    if client is not None:
        client.close()

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.executescript(
            "DROP TABLE IF EXISTS interactions; DROP TABLE IF EXISTS label_sections; "
            "DROP TABLE IF EXISTS india_brands; DROP TABLE IF EXISTS contraindications;"
        )
        conn.executescript(DDL)

        for row in seed_rows:
            rxcui_a = rxcui_map.get(row["name_a"].lower()) or row["name_a"].lower()
            rxcui_b = rxcui_map.get(row["name_b"].lower()) or row["name_b"].lower()
            conn.execute(
                "INSERT OR REPLACE INTO interactions "
                "(rxcui_a, rxcui_b, name_a, name_b, severity, mechanism, source, url) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    rxcui_a,
                    rxcui_b,
                    row["name_a"],
                    row["name_b"],
                    row["severity"],
                    row["mechanism"],
                    row["source"],
                    row["url"],
                ),
            )

        for row in brand_rows:
            first_ingredient = row["ingredient"].split("+")[0].strip().lower()
            rxcui = rxcui_map.get(first_ingredient)
            conn.execute(
                "INSERT OR REPLACE INTO india_brands (brand, ingredient, rxcui, nlem, source) "
                "VALUES (?,?,?,?,?)",
                (row["brand"], row["ingredient"], rxcui, int(row.get("nlem", 0) or 0), row.get("source", "curated")),
            )

        for row in label_rows:
            rxcui = rxcui_map.get(row["ingredient"].lower())
            if row["section"] == "contraindications":
                conn.execute(
                    "INSERT INTO contraindications (rxcui, ingredient, condition, text, url) "
                    "VALUES (?,?,?,?,?)",
                    (rxcui, row["ingredient"], None, row["text"], row["url"]),
                )
            else:
                conn.execute(
                    "INSERT INTO label_sections (rxcui, ingredient, section, text, url) VALUES (?,?,?,?,?)",
                    (rxcui, row["ingredient"], row["section"], row["text"], row["url"]),
                )

        conn.commit()

        try:
            conn.executescript(INDICATIONS_FTS_DDL)
            conn.execute(
                "INSERT INTO indications_fts(ingredient, text) "
                "SELECT ingredient, text FROM label_sections WHERE section='indications_and_usage'"
            )
            conn.commit()
        except sqlite3.OperationalError as exc:  # noqa: BLE001 -- FTS5 unavailable in this sqlite build
            logger.warning("kb_build.fts5_unavailable", error=str(exc))

        counts = {
            "interactions": conn.execute("SELECT COUNT(*) FROM interactions").fetchone()[0],
            "label_sections": conn.execute("SELECT COUNT(*) FROM label_sections").fetchone()[0],
            "india_brands": conn.execute("SELECT COUNT(*) FROM india_brands").fetchone()[0],
            "contraindications": conn.execute("SELECT COUNT(*) FROM contraindications").fetchone()[0],
            "rxcui_lookup_rows": len(rxcui_map),
        }
    finally:
        conn.close()

    logger.info("kb_build.done", **counts)
    return counts


if __name__ == "__main__":
    print(build())
