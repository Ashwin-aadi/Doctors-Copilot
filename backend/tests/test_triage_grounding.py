"""Regression tests for pre-assessment grounding, consistency and retrieval bias.

These are deliberately free of database and network dependencies: everything
tested here is the deterministic spine of the triage pipeline, which is exactly
the part that must never regress. The LLM is only ever allowed to influence
prose and ranking, so nothing below needs it.

Each test class maps to one of the failure modes observed in testing:
inferred symptoms, unsupported red flags, contradictory triage, common-disease
bias, and silence about what was never asked.
"""

import pytest

from app.rag import triage_rag, triage_rules
from app.rag.negation import polarity_at, split_clauses
from app.rag.patient_state import PatientState, extract_deterministic
from app.rag.query_builder import build_queries, candidate_conditions
from app.rag.retriever import _diversify, rescore_with_evidence
from app.rag.store import Hit
from app.rag.triage_rag import _asserted_text, _regex_red_flag


def _convo(*pairs: str) -> list[dict]:
    """Build a transcript from alternating assistant/user strings."""
    roles = ("assistant", "user")
    return [{"role": roles[i % 2], "content": text} for i, text in enumerate(pairs)]


LEPTO_CASE = _convo(
    "How can we help you today?",
    "I have had high fever for about 5 days with severe muscle pain, especially in my calves. "
    "I also have a headache and feel nauseous.",
    "Have you vomited, or noticed any rash?",
    "Yes I vomited twice and there is a mild reddish rash. My urine has been noticeably dark "
    "and I have mild abdominal discomfort.",
    "Do you have any shortness of breath, chest pain or difficulty breathing?",
    "No shortness of breath, no chest pain and no difficulty breathing.",
    "Any blood in your vomit, urine or stool?",
    "No blood in vomit, urine, or stool.",
    "Any recent exposure to flood or stagnant water?",
    "Yes, I waded through stagnant water outside my house last week after the flooding.",
    "Do you have any long-term conditions or take any regular medicines?",
    "No chronic conditions and no regular medicines.",
)


@pytest.fixture
def lepto_state() -> PatientState:
    return extract_deterministic(LEPTO_CASE)


# ------------------------------------------------ positive vs negative symptoms


class TestPositiveAndNegativeSymptoms:
    def test_asserted_symptoms_are_present(self, lepto_state):
        for name in ("fever", "calf_myalgia", "dark_urine", "rash", "stagnant_water_exposure"):
            assert lepto_state.is_present(name), f"{name} should be PRESENT"

    def test_denied_symptoms_are_absent_not_present(self, lepto_state):
        for name in ("dyspnoea", "chest_pain", "haematemesis"):
            assert lepto_state.is_absent(name), f"{name} should be ABSENT"
            assert not lepto_state.is_present(name)

    def test_denied_symptom_never_appears_as_a_present_finding(self, lepto_state):
        present_names = {f.name for f in lepto_state.present}
        assert present_names.isdisjoint({"dyspnoea", "chest_pain", "haematemesis"})

    @pytest.mark.parametrize(
        ("utterance", "feature", "expected"),
        [
            ("I have been coughing for three days", "cough", "present"),
            ("no cough at all", "cough", "absent"),
            ("no fever but I do have a bad cough", "cough", "present"),
            ("no fever but I do have a bad cough", "fever", "absent"),
            ("I deny any chest pain", "chest_pain", "absent"),
            ("chest pain nahi hai", "chest_pain", "absent"),
            ("there is no doubt I have chest pain", "chest_pain", "present"),
        ],
    )
    def test_negation_scope_across_phrasings(self, utterance, feature, expected):
        state = extract_deterministic(_convo("What brings you in?", utterance))
        assert state.status(feature) == expected

    def test_bare_no_answers_the_question_that_was_asked(self):
        state = extract_deterministic(
            _convo("Do you have any difficulty breathing?", "No.")
        )
        assert state.is_absent("dyspnoea")

    def test_bare_yes_answers_the_question_that_was_asked(self):
        state = extract_deterministic(_convo("Do you have a fever?", "Yes"))
        assert state.is_present("fever")

    def test_question_text_alone_never_creates_a_finding(self):
        state = extract_deterministic(
            _convo("Do you have chest pain or difficulty breathing?", "My knee hurts.")
        )
        assert state.status("chest_pain") == "unknown"
        assert state.status("dyspnoea") == "unknown"

    def test_nested_phrase_does_not_negate_the_broader_symptom(self):
        """"No blood in vomit" must not erase an earlier "I vomited"."""
        state = extract_deterministic(
            _convo(
                "What is wrong?",
                "I vomited three times today.",
                "Any blood in the vomit?",
                "No blood in vomit, urine, or stool.",
            )
        )
        assert state.is_present("vomiting")
        assert state.is_absent("haematemesis")


# ------------------------------------------------------------ unknown symptoms


class TestUnknownSymptoms:
    def test_unmentioned_symptom_is_unknown_not_present(self, lepto_state):
        assert lepto_state.status("jaundice") == "unknown"
        assert lepto_state.status("neck_stiffness") == "unknown"

    def test_hedged_answer_is_unknown(self):
        state = extract_deterministic(
            _convo("Any rash?", "Maybe a rash, I am not sure.")
        )
        assert state.status("rash") == "unknown"

    def test_dont_know_answer_is_unknown(self):
        state = extract_deterministic(_convo("Do you have a fever?", "I don't know"))
        assert state.status("fever") == "unknown"

    def test_state_prompt_block_labels_the_three_statuses_distinctly(self, lepto_state):
        block = lepto_state.as_prompt_block()
        assert "PRESENT: fever" in block
        assert "EXPLICITLY DENIED: shortness of breath" in block


# --------------------------------------------------- contradictory responses


class TestContradictoryResponses:
    def test_later_correction_wins(self):
        state = extract_deterministic(
            _convo(
                "Any vomiting?",
                "No vomiting.",
                "Are you sure? Nothing came up at all?",
                "Actually yes, I vomited once this morning.",
            )
        )
        assert state.is_present("vomiting")

    def test_a_definite_answer_beats_an_earlier_hedge(self):
        state = extract_deterministic(
            _convo(
                "Any rash?",
                "Maybe, not sure.",
                "Have another look — is there a rash?",
                "Yes there is a rash on my chest.",
            )
        )
        assert state.is_present("rash")

    def test_evidence_is_retained_for_every_finding(self, lepto_state):
        for finding in lepto_state.present:
            assert finding.evidence, f"{finding.name} carries no evidence span"


# ------------------------------------------- hallucinated / inferred symptoms


class TestHallucinatedFindings:
    def test_ungrounded_quote_is_rejected(self):
        from app.rag.patient_state import _quote_is_grounded

        words = "I have fever and calf pain"
        assert _quote_is_grounded("calf pain", words)
        assert not _quote_is_grounded("shortness of breath", words)
        assert not _quote_is_grounded("bleeding gums", words)

    def test_quote_grounding_ignores_punctuation_and_case(self):
        from app.rag.patient_state import _quote_is_grounded

        assert _quote_is_grounded("Calf, pain!", "i have fever and calf pain")

    def test_rationale_asserting_a_denied_finding_is_stripped(self, lepto_state):
        text = (
            "The patient has difficulty breathing. "
            "There is a five day fever with calf pain."
        )
        cleaned = triage_rules.strip_denied_findings(text, lepto_state)
        assert "difficulty breathing" not in cleaned.lower()
        assert "calf pain" in cleaned.lower()

    def test_rationale_may_still_report_a_denial(self, lepto_state):
        text = "The patient denies difficulty breathing, which is reassuring."
        cleaned = triage_rules.strip_denied_findings(text, lepto_state)
        assert "denies difficulty breathing" in cleaned.lower()


# --------------------------------------------------------- unsupported red flags


class TestRedFlagSupport:
    def test_denied_breathlessness_raises_no_red_flag(self, lepto_state):
        """The exact defect seen in testing: a denied symptom became a red flag."""
        flags = triage_rules.detect_red_flags(lepto_state)
        assert not any("breath" in f.text.lower() for f in flags)

    def test_no_red_flags_at_all_for_this_presentation(self, lepto_state):
        assert triage_rules.detect_red_flags(lepto_state) == []

    def test_legacy_phrase_screen_respects_negation(self):
        assert _regex_red_flag("no difficulty breathing") is None
        assert _regex_red_flag("I have difficulty breathing") is not None
        assert _regex_red_flag("no chest pain, no coughing up blood") is None

    def test_asserted_text_drops_pure_denial_clauses(self):
        kept = _asserted_text("No shortness of breath, no chest pain, but I have a fever")
        assert "fever" in kept.lower()
        assert "shortness of breath" not in kept.lower()

    def test_genuine_red_flag_still_fires_with_evidence(self):
        state = extract_deterministic(
            _convo(
                "What is wrong?",
                "I have crushing chest pain radiating to my left arm and I am sweating.",
            )
        )
        flags = triage_rules.detect_red_flags(state)
        assert flags
        assert all(f.evidence for f in flags)
        assert triage_rules.decide_severity(state).esi <= 2

    def test_red_flag_requires_every_feature_to_be_present(self):
        """Fever alone must not fire the fever-plus-neck-stiffness rule."""
        state = extract_deterministic(_convo("What is wrong?", "I have a fever."))
        assert not any(f.id == "rf_meningism" for f in triage_rules.detect_red_flags(state))


# ------------------------------------------- contradictory triage and rationale


class TestTriageConsistency:
    def test_no_red_flag_means_no_emergency_level(self, lepto_state):
        decision = triage_rules.decide_severity(lepto_state)
        assert decision.red_flags == []
        assert decision.esi >= 3, "cannot be an emergency without a red flag"

    def test_model_cannot_escalate_past_the_rule_ceiling(self, lepto_state):
        """Even if the model insists on ESI 1, no red flag means no red triage."""
        decision = triage_rules.decide_severity(lepto_state, llm_esi=1)
        assert decision.esi >= 3

    def test_model_cannot_de_escalate_below_a_fired_red_flag(self):
        state = extract_deterministic(
            _convo("What is wrong?", "I am coughing up blood since this morning.")
        )
        assert triage_rules.decide_severity(state, llm_esi=5).esi <= 2

    def test_emergency_language_removed_when_no_red_flag_fired(self, lepto_state):
        rationale = (
            "This is a critical, immediately life-threatening presentation. "
            "The fever has lasted five days."
        )
        fixed, issues = triage_rules.check_consistency(
            esi=3, red_flags=[], rationale=rationale, state=lepto_state
        )
        assert "critical" not in fixed.lower()
        assert "five days" in fixed
        assert issues

    def test_reassurance_removed_when_a_red_flag_is_active(self, lepto_state):
        rationale = (
            "There are no immediate life-threatening signs and ESI 2 is not indicated. "
            "The patient should be reviewed."
        )
        fixed, issues = triage_rules.check_consistency(
            esi=2,
            red_flags=["coughing up blood"],
            rationale=rationale,
            state=lepto_state,
        )
        assert "not indicated" not in fixed.lower()
        assert "coughing up blood" in fixed.lower()
        assert issues

    def test_the_exact_observed_contradiction_is_repaired(self, lepto_state):
        """ESI 2 + "critical" + "no life-threatening signs", all in one note."""
        decision = triage_rules.decide_severity(lepto_state)
        rationale = (
            "Critical presentation requiring immediate emergency care. "
            "The patient has difficulty breathing. "
            "There are no immediate life-threatening signs, so ESI 2 is not indicated."
        )
        fixed, issues = triage_rules.check_consistency(
            esi=decision.esi,
            red_flags=[f.render() for f in decision.red_flags],
            rationale=rationale,
            state=lepto_state,
        )
        assert decision.esi >= 3
        assert "critical" not in fixed.lower()
        assert "difficulty breathing" not in fixed.lower()
        assert len(issues) >= 2

    def test_no_red_flag_note_is_stated_explicitly(self, lepto_state):
        fixed, _ = triage_rules.check_consistency(
            esi=3, red_flags=[], rationale="Fever for five days.", state=lepto_state
        )
        assert "no emergency red flags" in fixed.lower()


# ------------------------------------------------------------ common-disease bias


class TestCommonDiseaseBias:
    def test_dengue_is_demoted_without_a_discriminating_feature(self, lepto_state):
        ranked = ["dengue fever", "leptospirosis", "scrub typhus"]
        reordered = triage_rules.suppress_common_bias(ranked, lepto_state)
        assert reordered.index("leptospirosis") < reordered.index("dengue fever")

    def test_dengue_keeps_its_place_when_its_own_discriminator_is_present(self):
        state = extract_deterministic(
            _convo(
                "What is wrong?",
                "Fever for three days with severe pain behind my eyes and bleeding gums.",
            )
        )
        ranked = ["dengue fever", "scrub typhus"]
        assert triage_rules.suppress_common_bias(ranked, state)[0] == "dengue fever"

    def test_no_demotion_when_the_patient_has_no_discriminators_at_all(self):
        state = extract_deterministic(_convo("What is wrong?", "Fever and body ache."))
        ranked = ["dengue fever", "viral fever"]
        assert triage_rules.suppress_common_bias(ranked, state) == ranked

    def test_discriminating_features_drive_candidate_conditions(self, lepto_state):
        candidates = [c.lower() for c in candidate_conditions(lepto_state)]
        assert "leptospirosis" in candidates
        assert candidates.index("leptospirosis") < len(candidates) / 2

    def test_generic_features_alone_raise_no_candidate_conditions(self):
        state = extract_deterministic(
            _convo("What is wrong?", "I have fever, body ache and vomiting.")
        )
        assert candidate_conditions(state) == []


# ------------------------------------------------- discriminating features in RAG


class TestRetrievalWeighting:
    def test_query_fan_out_includes_each_discriminator(self, lepto_state):
        texts = " | ".join(q.text.lower() for q in build_queries(lepto_state))
        assert "calf" in texts
        assert "stagnant" in texts or "flood" in texts
        assert "dark" in texts

    def test_query_fan_out_probes_candidate_conditions_by_name(self, lepto_state):
        kinds = {q.kind for q in build_queries(lepto_state)}
        assert "condition" in kinds
        texts = " | ".join(q.text.lower() for q in build_queries(lepto_state))
        assert "leptospirosis" in texts

    def test_denied_findings_never_enter_query_text(self, lepto_state):
        texts = " | ".join(q.text.lower() for q in build_queries(lepto_state))
        for denied in ("shortness of breath", "chest pain"):
            assert denied not in texts

    def test_combination_query_outweighs_single_feature_queries(self, lepto_state):
        queries = build_queries(lepto_state)
        combination = next(q for q in queries if q.kind == "combination")
        discriminator = next(q for q in queries if q.kind == "discriminator")
        assert combination.weight > discriminator.weight

    def test_duration_is_carried_into_the_query(self, lepto_state):
        presentation = next(q for q in build_queries(lepto_state) if q.kind == "presentation")
        assert "5 days" in presentation.text or "prolonged" in presentation.text

    def test_rescoring_promotes_a_chunk_matching_a_discriminator(self):
        hits = [
            Hit(id="dengue", text="Dengue fever causes fever, rash and vomiting.", score=1.0,
                metadata={"title": "Dengue"}),
            Hit(id="lepto", text="Fever with severe calf muscle pain and dark urine after "
                "contact with stagnant water suggests leptospirosis.", score=0.8,
                metadata={"title": "Leptospirosis"}),
        ]
        rescored = rescore_with_evidence(
            hits,
            discriminator_terms=["calf muscle pain", "dark", "stagnant water"],
            denied_terms=[],
        )
        assert rescored[0].id == "lepto"

    def test_rescoring_penalises_a_chunk_resting_on_a_denied_feature(self):
        hits = [
            Hit(id="a", text="Presents with shortness of breath and chest pain.", score=1.0,
                metadata={"title": "A"}),
            Hit(id="b", text="Presents with fever and calf pain.", score=0.9,
                metadata={"title": "B"}),
        ]
        rescored = rescore_with_evidence(
            hits,
            discriminator_terms=["calf pain"],
            denied_terms=["shortness of breath", "chest pain"],
        )
        assert rescored[0].id == "b"

    def test_diversity_cap_prevents_one_document_dominating_context(self):
        hits = [
            Hit(id=f"d{i}", text="dengue", score=1.0 - i / 100, metadata={"title": "Dengue"})
            for i in range(6)
        ] + [
            Hit(id="l1", text="lepto", score=0.5, metadata={"title": "Leptospirosis"}),
            Hit(id="s1", text="scrub", score=0.4, metadata={"title": "Scrub typhus"}),
        ]
        top = _diversify(hits, k=4, max_per_source=2)
        titles = [h.metadata["title"] for h in top]
        assert titles.count("Dengue") <= 2
        assert "Leptospirosis" in titles


# ----------------------------------------------- incomplete patient information


class TestIncompleteInformation:
    def test_empty_conversation_yields_no_findings_and_no_emergency(self):
        state = extract_deterministic(_convo("How can we help you today?"))
        assert state.present == []
        decision = triage_rules.decide_severity(state)
        assert decision.red_flags == []
        assert decision.basis == "insufficient information"
        assert decision.esi >= 3

    def test_sparse_history_is_reported_as_uncertain(self):
        from app.rag.triage_rag import _uncertainty_notes

        state = extract_deterministic(_convo("What is wrong?", "I feel unwell."))
        notes = " ".join(_uncertainty_notes(state, [], []))
        assert "provisional" in notes or "duration" in notes.lower()

    def test_missing_duration_is_flagged(self):
        from app.rag.triage_rag import _uncertainty_notes

        state = extract_deterministic(_convo("What is wrong?", "I have a fever and a rash."))
        assert state.duration_days is None
        assert any("duration" in n.lower() for n in _uncertainty_notes(state, [], []))

    def test_non_specific_presentation_is_flagged_as_unnarrowable(self):
        from app.rag.triage_rag import _uncertainty_notes

        state = extract_deterministic(
            _convo("What is wrong?", "Fever and body ache for two days.")
        )
        assert state.discriminators == []
        assert any("discriminating" in n for n in _uncertainty_notes(state, [], []))

    def test_coverage_gaps_are_reported_for_a_partial_history(self, lepto_state):
        from app.rag.triage_rag import _coverage_gaps

        gaps = _coverage_gaps(lepto_state)
        # Jaundice was never asked about, and it separates the leading candidates.
        assert "hepatic" in gaps


# -------------------------------------------------- negation engine unit tests


class TestNegationEngine:
    @pytest.mark.parametrize(
        ("text", "concept", "expected"),
        [
            ("no shortness of breath", "shortness of breath", "absent"),
            ("denies fever", "fever", "absent"),
            ("without any vomiting", "vomiting", "absent"),
            ("fever is absent", "fever", "absent"),
            ("no fever, but severe headache", "headache", "present"),
            ("headache since morning", "headache", "present"),
            ("maybe a headache", "headache", "unknown"),
            ("no doubt about the headache", "headache", "present"),
            ("bukhar nahi hai", "bukhar", "absent"),
        ],
    )
    def test_polarity(self, text, concept, expected):
        index = text.index(concept)
        assert polarity_at(text, (index, index + len(concept))) == expected

    def test_scope_does_not_leak_across_clauses(self):
        text = "no chest pain. I have a severe headache"
        index = text.index("severe headache")
        assert polarity_at(text, (index, index + len("severe headache"))) == "present"

    def test_clause_offsets_are_absolute(self):
        clauses = split_clauses("no fever. severe headache")
        assert all(text[c.start : c.end] == c.text for text, c in [("no fever. severe headache", c) for c in clauses])


# ------------------------------------------------- knowledge-base ingestion


class TestCorpusQuality:
    """The corpus is a pipeline stage too.

    Leptospirosis was present in the vector store as three chunks of scraped
    JavaScript, so no query could retrieve it however well it was built. These
    guard the cleaning and quality gate that fixed that.
    """

    def test_script_and_style_bodies_are_removed(self):
        from app.rag.ingest_guidelines import _clean_html

        cleaned = _clean_html(
            "<html><head><style>a{color:red}</style></head>"
            "<body><script>var x=1;</script><p>Dengue &amp; fever</p></body></html>"
        )
        assert cleaned == "Dengue & fever"

    def test_html_comments_are_removed(self):
        from app.rag.ingest_guidelines import _clean_html

        assert "tracker" not in _clean_html("<p>Fever</p><!-- tracker snippet -->")

    def test_javascript_is_not_accepted_as_prose(self):
        from app.rag.ingest_guidelines import is_prose

        js = (
            "(function (w, d, s, n, a) { if (!w[n]) { var l = "
            "'call,catch,on,once,set,then,track'.split(','), i, o = function (n) "
            "{ return 'function' == typeof n ? o.l.push([arguments]) && o : "
            "function () { return o.l.push([n, arguments]) && o } }; } })"
        )
        assert not is_prose(js)

    def test_navigation_link_soup_is_not_accepted_as_prose(self):
        from app.rag.ingest_guidelines import is_prose

        assert not is_prose(" ".join(["Home About Contact Newsroom Data Reports"] * 8))

    def test_clinical_prose_is_accepted(self):
        from app.rag.ingest_guidelines import is_prose

        assert is_prose(
            "Fever with severe calf muscle pain, red eyes, headache and jaundice, in "
            "someone exposed to flood water, waterlogged fields or sewage, suggests "
            "leptospirosis. Reduced urine output, breathlessness or bleeding indicates "
            "severe disease that requires admission and close monitoring in hospital."
        )

    def test_curated_corpus_covers_the_uncommon_indian_differential(self):
        from app.rag.ingest_guidelines import _symptom_corpus_chunks

        titles = " | ".join(c.metadata["title"].lower() for c in _symptom_corpus_chunks())
        for condition in ("leptospirosis", "scrub typhus", "organophosphate", "heat"):
            assert condition in titles, f"curated corpus lacks {condition}"


# ------------------------------------- unseen presentations, end to end (rules)


class TestUnseenPresentations:
    """Cases the pipeline was not tuned on, checked for state and triage sanity."""

    @pytest.mark.parametrize(
        ("utterances", "expect_present", "expect_candidate", "min_esi", "max_esi"),
        [
            (
                [
                    "Fever for 8 days with bad headache. I found a painless black scab on my thigh.",
                    "The glands in my neck are swollen and I work in the fields near scrub.",
                ],
                ["eschar", "lymphadenopathy", "scrub_exposure"],
                "scrub typhus",
                3, 4,
            ),
            (
                [
                    "Fever for 10 days, it keeps going up each day. I eat roadside food daily.",
                    "Abdominal pain and my pulse is slow.",
                ],
                ["stepladder_fever", "relative_bradycardia", "fever"],
                "enteric fever",
                3, 4,
            ),
            (
                [
                    "Fever with shaking chills every alternate day for a week.",
                    "Lots of mosquitoes at home.",
                ],
                ["periodic_fever", "fever"],
                "malaria",
                3, 4,
            ),
            (
                [
                    "Cough for three weeks with drenching night sweats and I am losing weight.",
                    "No coughing up blood.",
                ],
                ["chronic_cough", "night_sweats", "weight_loss"],
                "tuberculosis",
                3, 4,
            ),
            (
                [
                    "Fever for 6 days, my eyes have gone yellow and urine is dark brown.",
                    "I drink well water at work.",
                ],
                ["jaundice", "dark_urine"],
                "viral hepatitis",
                3, 4,
            ),
        ],
    )
    def test_state_and_triage_on_unseen_cases(
        self, utterances, expect_present, expect_candidate, min_esi, max_esi
    ):
        pairs: list[str] = []
        for utterance in utterances:
            pairs.extend(["What else can you tell me?", utterance])
        state = extract_deterministic(_convo(*pairs))

        for name in expect_present:
            assert state.is_present(name), f"{name} missing from state"
        candidates = [c.lower() for c in candidate_conditions(state)]
        assert expect_candidate in candidates
        assert candidates[0] == expect_candidate, f"expected {expect_candidate} to lead {candidates}"

        decision = triage_rules.decide_severity(state)
        assert min_esi <= decision.esi <= max_esi
        assert decision.red_flags == [], "no emergency sign was reported in these cases"

    @pytest.mark.parametrize(
        ("utterance", "expected_esi"),
        [
            ("My brother drank pesticide an hour ago and he is drowsy.", 1),
            ("I was bitten by a snake in the field.", 1),
            ("High fever since yesterday with a very stiff neck and I feel confused.", 2),
            ("I am coughing up blood.", 2),
            ("I have a mild cold and runny nose for two days.", 4),
        ],
    )
    def test_emergency_and_benign_presentations_are_separated(self, utterance, expected_esi):
        state = extract_deterministic(_convo("What brings you in?", utterance))
        assert triage_rules.decide_severity(state).esi == expected_esi

    def test_denial_heavy_history_does_not_manufacture_urgency(self):
        state = extract_deterministic(
            _convo(
                "What brings you in?",
                "Mild headache since yesterday.",
                "Any chest pain, difficulty breathing or confusion?",
                "No chest pain, no difficulty breathing, no confusion, no bleeding.",
                "Any vomiting blood or black stools?",
                "No vomiting blood and no black stools.",
            )
        )
        decision = triage_rules.decide_severity(state)
        assert decision.red_flags == []
        assert decision.esi >= 4


# --------------------------------------------- model output shape robustness


class TestModelOutputHandling:
    """The reasoning stages must survive the response shapes models actually emit.

    A schema mismatch used to discard the entire note and fall back to an empty
    result: safe, but it threw away correct reasoning over a key name.
    """

    def test_differential_accepts_a_bare_list(self):
        from app.rag.triage_rag import _RawDifferential

        parsed = _RawDifferential.model_validate(
            [{"condition": "leptospirosis", "citation_numbers": [1]}]
        )
        assert parsed.differentials[0].condition == "leptospirosis"

    def test_labs_keyed_on_test_are_accepted(self):
        from app.rag.triage_rag import _RawTriage

        parsed = _RawTriage.model_validate(
            {"suggested_labs": [{"test": "Leptospira IgM ELISA", "reason": "calf pain"}]}
        )
        assert parsed.suggested_labs[0].name == "Leptospira IgM ELISA"

    def test_word_confidence_is_coerced(self):
        from app.rag.triage_rag import _RawTriage

        assert _RawTriage.model_validate({"confidence": "moderate"}).confidence == 0.5
        assert _RawTriage.model_validate({"confidence": "nonsense"}).confidence == 0.0

    def test_citations_accept_numbers_and_objects(self):
        from app.rag.triage_rag import _RawTriage

        assert _RawTriage.model_validate({"citations": [1, 4]}).citations == [1, 4]
        assert _RawTriage.model_validate(
            {"citations": [{"n": 2, "title": "made up"}]}
        ).citations == [2]


class TestCitationResolution:
    def _hits(self):
        return [
            Hit(id="h1", text="Leptospirosis text.", score=1.0,
                metadata={"title": "Leptospirosis", "source": "symptom_corpus",
                          "url": "internal://a", "published": "2024"}),
            Hit(id="h2", text="Dengue text.", score=0.9,
                metadata={"title": "Dengue", "source": "who", "url": "https://x",
                          "published": "2023"}),
        ]

    def test_citations_are_rebuilt_from_hits_not_from_model_text(self):
        from app.rag.triage_rag import _resolve_citations

        text, citations = _resolve_citations("Calf pain fits leptospirosis [1].", [1], self._hits())
        assert citations[0].title == "Leptospirosis"
        assert citations[0].source == "symptom_corpus"
        assert text == "Calf pain fits leptospirosis [1]."

    def test_out_of_range_markers_are_dropped_from_prose_and_list(self):
        from app.rag.triage_rag import _resolve_citations

        text, citations = _resolve_citations("Supported [9]. Also this [2].", [9, 2], self._hits())
        assert "[9]" not in text
        assert [c.n for c in citations] == [1]
        assert citations[0].title == "Dengue"

    def test_markers_are_renumbered_consistently_with_the_list(self):
        from app.rag.triage_rag import _resolve_citations

        text, citations = _resolve_citations("First [2]. Second [1].", [], self._hits())
        assert [c.n for c in citations] == [1, 2]
        assert citations[0].title == "Dengue"
        assert text == "First [1]. Second [2]."


class TestUncertaintyHonesty:
    def test_answered_category_is_not_reported_as_unassessed(self, lepto_state):
        from app.rag.triage_rag import _coverage_gaps

        assert "exposure" not in _coverage_gaps(lepto_state)

    def test_unavailable_differential_is_distinguished_from_an_empty_one(self, lepto_state):
        from app.rag.triage_rag import _uncertainty_notes

        unavailable = " ".join(
            _uncertainty_notes(lepto_state, [], [], differential_available=False)
        )
        empty = " ".join(_uncertainty_notes(lepto_state, [], [], differential_available=True))
        assert "unavailable" in unavailable
        assert "unavailable" not in empty
        assert "No condition could be supported" in empty

    def test_against_claims_from_unassessed_findings_are_recognised(self, lepto_state):
        from app.rag.triage_rag import _rests_on_unassessed

        # Rigors and eschar were never asked about in this history.
        assert _rests_on_unassessed("no reported chills or rigors", lepto_state)
        assert _rests_on_unassessed("no eschar noted", lepto_state)
        # Breathlessness WAS asked and denied, so arguing from it is legitimate.
        assert not _rests_on_unassessed("shortness of breath was denied", lepto_state)
        # A positive statement is not an argument from absence at all.
        assert not _rests_on_unassessed("calf pain is typical", lepto_state)

    def test_differential_citations_are_renumbered_with_the_rationale(self):
        from app.rag.triage_rag import _resolve_citations
        from app.schemas.triage import DifferentialItem

        hits = [
            Hit(id=f"h{i}", text=f"text {i}", score=1.0,
                metadata={"title": f"T{i}", "source": "s", "url": "u", "published": "2024"})
            for i in range(1, 7)
        ]
        differentials = [
            DifferentialItem(condition="lepto", citation_numbers=[6]),
            DifferentialItem(condition="dengue", citation_numbers=[4, 99]),
        ]
        text, citations = _resolve_citations("Driven by exposure [1].", [], hits, differentials)
        titles = {c.n: c.title for c in citations}
        assert titles[differentials[0].citation_numbers[0]] == "T6"
        assert titles[differentials[1].citation_numbers[0]] == "T4"
        assert 99 not in differentials[1].citation_numbers
        assert text == "Driven by exposure [1]."


class TestSpecialtyRouting:
    """The scheduler matches Doctor.specialties exactly, so triage must emit a
    bookable slug rather than whatever prose the model produced. Regression for
    the demo journey, where `Infectious Diseases` routed to no doctor at all and
    every booking made from a triage session 404'd.
    """

    def test_canonical_slugs_pass_through(self):
        for slug in triage_rag.CANONICAL_SPECIALTIES:
            assert triage_rag.normalise_specialty(slug) == slug

    def test_prose_is_slugified_and_aliased(self):
        assert triage_rag.normalise_specialty("Infectious Diseases") == "general_medicine"
        assert triage_rag.normalise_specialty("Obstetrics & Gynaecology") == "obstetrics_gynaecology"
        assert triage_rag.normalise_specialty("Paediatrics") == "pediatrics"
        assert triage_rag.normalise_specialty("Hepatology") == "gastroenterology"

    def test_keyword_fallback_routes_subspecialties(self):
        assert triage_rag.normalise_specialty("Interventional Cardiology") == "cardiology"
        assert triage_rag.normalise_specialty("paediatric neurology") == "neurology"

    def test_unknown_and_empty_degrade_to_general_medicine(self):
        for value in (None, "", "   ", "!!!", "astrology"):
            assert triage_rag.normalise_specialty(value) == "general_medicine"

    def test_output_is_always_bookable(self):
        samples = [
            "Emergency Medicine", "Tropical Medicine", "Nephrology / Renal",
            "chest medicine", "ENT", "Mental Health", "General Surgery",
            "Diabetology", "skin and venereology", None, "",
        ]
        for s in samples:
            assert triage_rag.normalise_specialty(s) in triage_rag.CANONICAL_SPECIALTIES
