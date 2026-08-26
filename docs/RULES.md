# RULES.md -- deterministic rule packs (Niyati's scope)

First draft, written at CP2 (section 8 N2.5). Every weight, threshold and
rule id below lives in a YAML file under `backend/app/services/rules/packs/`
and `backend/app/services/queueing/pq.py`'s pack -- nothing is a magic number
inside a `.py` file (that's the CP4 N4.5 gate; this draft documents what CP1
and CP2 already externalised, and gets extended each checkpoint after).

No LLM anywhere in this project's rule evaluation. Every table below is a
plain lookup or threshold comparison, which is what makes `reasons[]` always
renderable in plain English/Hindi instead of a model's paraphrase.

## `packs/triage_india.yaml` -- MoHFW/NELS triage tiers

`severity_esi` (Ashwin's frozen field, 1-5) carries India's three-colour
casualty scheme in this project, not the US Emergency Severity Index.

| Tier | Colour | Label (en/hi) | Target | Source |
|---|---|---|---|---|
| 1 | red | Resuscitation / पुनर्जीवन | 0 min | MoHFW/AIIMS casualty triage protocol |
| 2 | red | Emergency / आपातकाल | 10 min | MoHFW/AIIMS casualty triage protocol |
| 3 | yellow | Urgent / अत्यावश्यक | 60 min | MoHFW/AIIMS casualty triage protocol |
| 4 | green | Less urgent / कम अत्यावश्यक | 120 min | MoHFW/AIIMS casualty triage protocol |
| 5 | green | Non-urgent / सामान्य | 240 min | MoHFW/AIIMS casualty triage protocol |

Statutory priority groups (bounded bonus, `priority_group_max_bonus: 1`,
never enough to outrank RED -- see `pq.py::_sort_key`, a same-tier tie-break
rather than a numeric severity reduction): pregnant (3rd trimester, ANC
norms), infant under 1, senior citizen 60+, divyangjan. Order in the pack is
the deterministic tie-break when a patient qualifies for more than one.

## `packs/optimizer.yaml` -- doctor ranking

| Parameter | Value | Meaning | Tuning effect | Source |
|---|---|---|---|---|
| `weights.specialty` | 0.30 | exact vs related specialty match | raising it favours specialist-exactness over convenience | project design (SIH scope doc) |
| `weights.availability` | 0.20 | sooner next slot scores higher | raising it prioritises speed over other factors | OPD throughput priority |
| `weights.distance` | 0.13 | closer clinic scores higher | raising it favours proximity, relevant given patient travel cost | rural access requirement |
| `weights.queue` | 0.13 | shorter queue scores higher | raising it spreads load across doctors | fairness / anti-bottleneck |
| `weights.language` | 0.10 | doctor speaks patient's language | raising it prioritises communication access | language-access requirement (project design) |
| `weights.scheme` | 0.09 | clinic empanelled for patient's scheme | raising it favours free/covered care | PM-JAY/CGHS/ESIC affordability |
| `weights.rating` | 0.03 | doctor rating (0-5) | minor tie-break signal | secondary quality signal |
| `weights.fee` | 0.02 | penalises consultation fee | raising it favours cheaper care | affordability, capped low so it never overrides specialty/availability |
| `min_facility_type` | per specialty | a case needing a specialist is never routed to a PHC | e.g. cardiology floor = DH | PHC->CHC->SDH->DH->Medical College referral ladder |
| `free_facility_types` | phc, chc, sdh, dh | fee penalty forced to 0 at public facilities | keeps public OPD's `fee=0` from ever inflating a doctor's rank on a technicality | public-OPD-is-free reality |
| `max_distance_km` | 40 | urban hard cutoff | tightening excludes distant urban clinics | urban travel-time reality |
| `max_distance_km_rural` | 60 | rural hard cutoff (used as the single CP1 cutoff; N3.3 splits urban/rural bands) | rural patients travel further by necessity | rural access requirement |
| `horizon_days` | 7 | how far ahead slots are searched | shorter horizon speeds ranking, may miss later availability | OPD booking-window convention |

## `packs/queue.yaml` -- priority queue

| Parameter | Value | Meaning | Tuning effect | Source |
|---|---|---|---|---|
| `holidays` | 4 gazetted national holidays | non-emergency facilities close | add state-specific holidays to extend closures | Republic Day / Holi / Independence Day / Gandhi Jayanti |
| `inter_clinic_travel_minutes` | 30 | gap enforced between a doctor's sessions at two clinics same day | raising it is more conservative about double-booking a commuting doctor | realistic India dual-practice pattern (govt AM + private PM) |
| `aging_minutes` | 45 | wait time before effective severity improves by 1 tier | lowering it moves long-waiters up faster (anti-starvation) | OPD fairness requirement |
| `aging_max_bonus` | 2 | cap on aging-driven tier improvement | prevents aging alone from ever reaching RED | RED must stay reserved for real emergencies |
| `avg_consult_minutes` | 6 | used for `estimated_wait_minutes = position * avg_consult_minutes` | raising it inflates displayed wait estimates | Indian OPD reality (4-8 min/patient, not the 12 min a US clinic assumes) |
| `emergency_severity_max` | 2 | tiers 1-2 are RED / auto-emergency | -- | MoHFW/NELS red tier definition |
| `grace_minutes` | 15 | no-show grace window (used from N3.2 onward) | -- | OPD no-show convention |
| `token_prefix_by_facility` | P/C/S/D/K/H | printable token prefix per facility type | matches what staff announce on paper/board | Indian OPD token-board convention |
| `opd_sessions_ist` | 09:00-13:00, 17:00-20:00 | split morning/evening OPD | -- | Indian OPD hours convention |

## `packs/lab_panels.yaml` -- lab-order recommendation rules

36 rules (35 real conditions + 1 `general_baseline` fallback), each mapping
`symptoms_any`/`symptoms_all`/`conditions_any`/`severity_max`/`season`/
`region`/`age_max`/`pregnant` to a deduped set of `SuggestedLab`s, tagged with
CGHS/PM-JAY coverage codes where a mapping exists. Weighted to India's actual
OPD disease burden rather than a generic differential list:

| Rule id | Clinical source |
|---|---|
| `acute_febrile_illness_monsoon`, `dengue_chikungunya_suspected` | NVBDCP dengue/chikungunya case-management guidelines |
| `malaria_suspected` | NVBDCP malaria diagnosis protocol |
| `enteric_fever_typhoid` | MoHFW Standard Treatment Guidelines (STG), fever |
| `pulmonary_tb_suspected`, `tb_contact_household_screening` | NTEP (National TB Elimination Programme) diagnostic algorithm |
| `anaemia_screening`, `anaemia_pregnancy` | Anaemia Mukt Bharat |
| `diabetes_screening_npcdcs`, `diabetes_known_followup`, `hypertension_screening_npcdcs` | NPCDCS (non-communicable disease programme) |
| `thyroid_dysfunction` | MoHFW STG, endocrine |
| `anc_first_visit_panel` | MoHFW ANC guidelines (first-visit test panel) |
| `leptospirosis_suspected`, `scrub_typhus_suspected` | NCDC monsoon-season zoonotic disease advisories |
| `hepatitis_a_e_suspected` | MoHFW STG, water-borne hepatitis |
| `snakebite_envenomation` | NVBDCP/state snakebite management protocol |
| `organophosphate_poisoning` | MoHFW STG, poisoning management |
| `heat_stroke_summer` | NCDC heat-wave action plan |
| `acute_diarrhoeal_disease_cholera` | MoHFW STG, diarrhoeal disease |
| `copd_biomass_exposure` | MoHFW STG, respiratory (biomass-fuel COPD burden) |
| `rheumatic_heart_disease` | MoHFW STG, cardiology (RHD screening) |
| `ckd_screening` | NPCDCS CKD screening extension |
| `stroke_suspected_fast`, `acs_chest_pain` | MoHFW STG, emergency cardiology/neurology |
| `acute_severe_asthma` | MoHFW STG, respiratory emergency |
| `urinary_tract_infection`, `pneumonia_lower_respiratory`, `jaundice_hepatobiliary_workup`, `seizure_disorder` | MoHFW STG, general OPD |
| `severe_acute_malnutrition_child` | NRC/CMAM SAM management protocol |
| `neonatal_sepsis_screen` | FBNC (Facility-Based Newborn Care) protocol |
| `rabies_category3_animal_bite` | National Rabies Control Programme |
| `covid_ili_screen` | ICMR ILI/SARI testing strategy |
| `dermatology_fungal_infection` | MoHFW STG, dermatology |
| `general_baseline` | fallback only -- CBC/RBS/urine routine, used when no other rule matches |

`merge_with_rag` unions the rule-engine output with whatever a retrieval/LLM
path (Ashwin's triage RAG) separately suggested: present in both -> `"both"`
(rule's own reason wins, since it is the reproducible side); rule-only ->
`"rule"`; RAG-only -> `"rag"`. Sort order `both < rule < rag` so the
strongest-evidence items lead the list.

## `packs/emergency.yaml` -- red flags and referral floor

93 red-flag phrase entries across 24 categories (chest pain/ACS, stroke FAST
signs, anaphylaxis, haemorrhage, GCS drop, hypoxia, snakebite, poisoning,
polytrauma, PPH, eclampsia, obstructed labour, neonatal emergency, SAM with
complications, heat stroke, massive haemoptysis, DKA, severe asthma, rabies
category III, drowning, electrocution, severe burns, acute abdomen, status
epilepticus, severe paediatric dehydration). Each carries a `min_facility_type`
-- the lowest rung of the PHC->CHC->SDH->DH->Medical College ladder that can
actually manage it, sourced from NRHM First Referral Unit (FRU) criteria for
obstetric emergencies and MoHFW STG emergency chapters elsewhere.

`should_escalate`: `severity_esi <= 2` (RED) **or** any red-flag phrase match
-- `emergency_severity_max` (2) is read from `queue.yaml`, one source of
truth shared with the queue's own RED definition.

Referral-ladder check (`escalation.py::escalate_with_referral`): if the
assigned clinic is not `is_emergency_capable`, or its facility rank is below
the matched red flag's `min_facility_type`, the nearest clinic meeting the
floor (within `max_distance_km_rural`, borrowed from `optimizer.yaml`) is
looked up directly via `repo.all_clinics()` -- **not** by re-running
`rank_doctors`, because the optimizer is doctor-availability-driven and would
wrongly suppress a valid transfer suggestion for a capable-but-understaffed
facility (a facility-capability problem, not a doctor-availability one). The
suggestion is appended to `reasons`/`reasons_hi` as facility name, type,
distance and "Call 108 for transfer" -- the system never dispatches an
ambulance itself.

## `mapping/data/india_drugs.csv` -- brand -> generic (offline-first)

332 rows across 173 molecules/combinations, covering the brands actually
written on Indian OPD prescriptions (paracetamol, NSAID combinations,
antibiotics, PPIs, antidiabetics, antihypertensives, statins, thyroid,
antihistamines, respiratory inhalers, vitamins/haematinics, GI, ENT,
ophthalmology, dermatology, anti-TB/ART national-programme FDCs, obstetric
emergency drugs, anti-snake-venom, anti-rabies biologicals). 275 rows are
NLEM 2022-listed; 262 carry a Jan Aushadhi (PMBJP) product code.
`normalize_brand()` strips strength tokens and common marketing suffixes
(`-SR`/`-DS`/`-XL`/`Plus`/dosage-form words) case-fold, so `"Dolo 650"`,
`"Dolo-650"` and `"Dolo"` all resolve to the same catalogue entry.

`nppa_ceiling.csv` (184 rows): a deliberately conservative, deterministic
model of DPCO-notified ceiling prices -- `round(0.72 * min(branded MRP for
that ingredient+strength), 2)` -- restricted to NLEM-listed, historically
DPCO-scheduled molecules (excludes lifestyle/non-scheduled brands). This
gives the right *shape* for the ₹-savings story (a real generic typically
prices near or below the NPPA ceiling); the literal rupee figures are
illustrative rather than a verbatim mirror of a live NPPA notification --
flagged here rather than presented as sourced data it isn't.

`GenericProduct.price_inr`: NPPA ceiling when one is on file; otherwise, for
a Jan Aushadhi-stocked item with no notified ceiling, `0.4 * mrp_inr` (a
fixed, deterministic, documented approximation of typical PMBJP savings).
`savings_pct = round(100 * (mrp - price) / mrp, 1)`, exactly the section 4.2
formula.

RxNav enrichment (`rxnorm.py`) only fires on a local-table miss, and never
attaches an Indian MRP/Jan Aushadhi code to an RxNav-sourced product --
`GenericProduct.mrp_inr`/`price_inr`/`jan_aushadhi_code` stay `None` on those
rows, so an international RxNorm catalogue entry is never mistaken for
something stocked at a Jan Aushadhi Kendra. Two-layer cache: in-process
`cachetools.TTLCache` (1h) backed by Redis (`rxnorm:{key}`, 7 days).

## Weight-sweep record

Not yet run -- section 8 N5.2 (CP5) sweeps `optimizer.yaml`'s weight vector
against the full clinic simulation and records the before/after table here.
This draft only documents the CP1/CP2 defaults above.
