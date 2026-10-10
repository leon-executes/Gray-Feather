"""Corruption/regression tests; synthetic strings are not translation golds."""
import hashlib
import unittest
from unittest.mock import patch
from reinforcement import Candidate, LANGUAGE_CODES, critical_checks, reinforce, route_order

def calendar_fixture():
    values = {
        "en": "January February March April May June July August September October November December".split(),
        "om": "Amajjii Guraandhala Bitootessa Eebila Caamsaa Waxabajjii Adoolessa Hagayya Fulbaana Onkoloolessa Sadaasa Mudde".split(),
        "fr": "janvier février mars avril mai juin juillet août septembre octobre novembre décembre".split()}
    days = {"en": "Sunday Monday Tuesday Wednesday Thursday Friday Saturday".split(), "om": "Dilbata Wiixata Kibxata Roobii Kamisa Jimaata Sanbata".split(), "fr": "dimanche lundi mardi mercredi jeudi vendredi samedi".split()}
    return {code: {"complete": True, "calendar": "gregorian", "months": {str(i): {"format": word, "stand-alone": word} for i, word in enumerate(words, 1)}, "days": {identity: {"format": word} for identity, word in zip("sun mon tue wed thu fri sat".split(), days[code])}} for code, words in values.items()}

class ReinforcementTests(unittest.TestCase):
    def test_observed_oromo_month_is_repaired_without_other_changes(self):
        source = "The appointment is on Tuesday, 13 October 2026, at 09:30, not Thursday at 19:30."
        original = "Beellamni kun Kibxata, Waxabajjii 13, 2026, sa’aatii 09:30tti malee Kamisa sa’aatii 19:30tti miti."
        with patch("reinforcement._calendar_data", return_value=calendar_fixture()):
            decision = reinforce(source, "en", "om", Candidate(original, "mymemory"))
        self.assertEqual(decision.method, "calendar_repair")
        self.assertEqual(decision.text, original.replace("Waxabajjii", "Onkoloolessa"))
        self.assertEqual(decision.original_primary.text, original)
        self.assertEqual(decision.audit[0]["edit"]["anchor"], (13, 2026))

    def test_heldout_calendar_contexts_all_twelve(self):
        data = calendar_fixture()
        with patch("reinforcement._calendar_data", return_value=data):
            for month in range(1, 13):
                with self.subTest(month=month):
                    source_name = data["en"]["months"][str(month)]["format"]
                    wrong = str(month % 12 + 1)
                    bad_name = data["om"]["months"][wrong]["format"]
                    source = "Archive opens on 7 " + source_name + " 2028. Ticket AB-1234."
                    output = "X " + bad_name + " 7, 2028. AB-1234."
                    decision = reinforce(source, "en", "om", Candidate(output, "mymemory"))
                    self.assertEqual(decision.text, output.replace(bad_name, data["om"]["months"][str(month)]["format"]))

    def test_calendar_prefers_complete_correct_candidate(self):
        with patch("reinforcement._calendar_data", return_value=calendar_fixture()):
            decision = reinforce("Meet on 8 October 2028.", "en", "fr", Candidate("Rendez-vous le 8 juin 2028.", "bing_web"), [Candidate("Rendez-vous le 8 octobre 2028.", "google_web")])
        self.assertEqual(decision.method, "whole_candidate")
        self.assertEqual(decision.provider, "google_web")

    def test_calendar_refuses_multiple_or_ambiguous_dates(self):
        fixtures = [
            ("Meet on 8 October 2028 or 9 November 2028.", "X 8 Waxabajjii 2028 Y 9 Sadaasa 2028."),
            ("October is busy in 2028.", "Waxabajjii 2028."),
            ("Meet on 8 October 2028.", "X 9 Waxabajjii 2028."),
            ("Convert the date 8 October 2028 to the Ethiopian calendar.", "X 8 Waxabajjii 2028."),
            ('Keep "8 October 2028" exactly.', "X 8 Waxabajjii 2028."),
            ("Meet on 31 January 2028.", "X 31 Waxabajjii 2028."),
            ("We may meet in 2028.", "X Waxabajjii 2028.")]
        with patch("reinforcement._calendar_data", return_value=calendar_fixture()):
            for source, target in fixtures:
                with self.subTest(source=source):
                    self.assertFalse(reinforce(source, "en", "om", Candidate(target, "mymemory")).changed)

    def test_calendar_refuses_other_fact_damage(self):
        with patch("reinforcement._calendar_data", return_value=calendar_fixture()):
            decision = reinforce("Meet on 8 October 2028. AB-1234.", "en", "om", Candidate("X 8 Waxabajjii 2028. AB-9999.", "mymemory"))
        self.assertFalse(decision.changed)

    def test_missing_lexicon_never_invents_month(self):
        with patch("reinforcement._calendar_data", return_value={}):
            self.assertFalse(reinforce("8 October 2028", "en", "om", Candidate("8 Waxabajjii 2028", "mymemory")).changed)

    def test_explicit_polarity_recovery_selects_whole_result(self):
        source = "Temperature is minus 5, not plus 5. Bring 2, not 3."
        primary = Candidate("X 5 Y 5. 2 3.", "bing_web")
        better = Candidate("X -5 Y +5. 2 3.", "google_web")
        decision = reinforce(source, "en", "ti", primary, [better])
        self.assertEqual(decision.text, better.text)
        self.assertIn("explicit_signed_polarity_recovery", decision.reasons)
        self.assertEqual(decision.original_primary.text, primary.text)

    def test_sign_swap_and_other_quantity_regression_rejected(self):
        source = "Temperature -5, not +5. Bring 2."
        decision = reinforce(source, "en", "ti", Candidate("X +5 +5. 2.", "bing_web"), [Candidate("X -5 +5. 20.", "google_web")])
        self.assertFalse(decision.changed)

    def test_no_numeric_order_or_role_guess(self):
        # Equal fact multisets do not establish who receives which amount.
        decision = reinforce("Give Alice 2 and Bob 3.", "en", "fr", Candidate("Bob 2 Alice 3.", "bing_web"), [Candidate("Alice 2 Bob 3.", "google_web")])
        self.assertFalse(decision.changed)

    def test_actual_amharic_contrast_reversal_rejected_and_correct_whole_selected(self):
        source = "The label says 0.5 mg, not 5 mg."
        primary = Candidate("መለያው 0.5 mg ሳይሆን 5 mg ይላል.", "bing_web")
        correct = Candidate("መለያው 5 mg ሳይሆን 0.5 mg ይላል.", "google_web")
        self.assertIn("numeric_contrast", critical_checks(source, primary.text, "en", "am")["violations"])
        decision = reinforce(source, "en", "am", primary, [correct])
        self.assertEqual(decision.text, correct.text)
        self.assertEqual(decision.method, "whole_candidate")

    def test_amharic_unknown_contrast_not_claimed_as_repair(self):
        decision = reinforce("0.5 mg, not 5 mg.", "en", "am", Candidate("0.5 mg ሳይሆን 5 mg.", "bing_web"), [Candidate("X 0.5 mg Y 5 mg.", "gemma_local")])
        self.assertFalse(decision.changed)

    def test_multiple_numeric_contrasts_no_role_parser(self):
        check = critical_checks("0.5 mg, not 5 mg. 2 mg, not 3 mg.", "0.5 mg ሳይሆን 5 mg. 2 mg ሳይሆን 3 mg.", "en", "am")
        self.assertNotIn("numeric_contrast", check["violations"])

    def test_model_repair_requires_explicit_policy_and_both_bindings(self):
        source, original = "Call it a day. AB-1234.", "X AB-1234."
        meta = {"operation": "repair", "source_sha256": hashlib.sha256(source.encode()).hexdigest(), "candidate_sha256": hashlib.sha256(original.encode()).hexdigest(), "direction_approved": True, "evidence_id": "synthetic explicit approval fixture; not production evidence"}
        primary = Candidate(original, "bing_web")
        model = Candidate("Y AB-1234.", "hy_mt_local", metadata=meta)
        self.assertFalse(reinforce(source, "en", "fr", primary, [model]).changed)
        self.assertEqual(reinforce(source, "en", "fr", primary, [model], policy="source_anchored_model").method, "model_repair")
        bad = Candidate(model.text, model.provider, metadata={**meta, "source_sha256": "stale"})
        self.assertFalse(reinforce(source, "en", "fr", primary, [bad], policy="source_anchored_model").changed)
        unmeasured = Candidate(model.text, model.provider, metadata={**meta, "direction_approved": False})
        self.assertFalse(reinforce(source, "en", "fr", primary, [unmeasured], policy="source_anchored_model").changed)

    def test_glossary_context_and_incomplete_candidate_cannot_be_rewritten(self):
        source, primary, alternative = "Mail a@example.org.", Candidate("X b@example.org.", "bing_web"), Candidate("X a@example.org.", "google_web")
        self.assertFalse(reinforce(source, "en", "fr", primary, [alternative], context=True).changed)
        self.assertFalse(reinforce(source, "en", "fr", primary, [alternative], glossary=True).changed)
        decision = reinforce(source, "en", "fr", primary, [Candidate(alternative.text, alternative.provider, complete=False)])
        self.assertEqual(decision.method, "opaque_literal_repair")
        self.assertEqual(decision.text, "X a@example.org.")
        self.assertEqual(decision.provider, primary.provider)
        self.assertEqual(decision.original_primary, primary)

    def test_routes_configured_exact_before_approximate_and_unsupported_removed(self):
        self.assertEqual(route_order("en", "prs", ["google_web", "mymemory", "bing_web"]), ("bing_web", "google_web", "mymemory"))
        self.assertEqual(route_order("prs", "en", ["mymemory", "bing_web"]), ("bing_web", "mymemory"))
        self.assertEqual(route_order("en", "om", ["bing_web", "google_web", "mymemory", "hy_mt_local"]), ("google_web", "mymemory"))
        self.assertEqual(route_order("en", "fr", ["mymemory", "google_web"]), ("mymemory", "google_web"))
        self.assertEqual(route_order("en", "am", ["hy_mt_local"]), ())
        self.assertEqual(route_order("en", "fa", ["google_web", "bing_web", "mymemory"]), ("bing_web", "google_web", "mymemory"))
        self.assertEqual(route_order("fa", "en", ["google_web", "bing_web"]), ("bing_web", "google_web"))
        self.assertEqual(route_order("om", "en", ["index_web", "bing_web", "google_web", "mymemory"]), ("google_web", "mymemory"))
        self.assertIn("index_web", route_order("en", "om", ["index_web", "google_web"]))

    def test_actual_multilingual_sign_renderings_request_consultation_without_guessed_repair(self):
        source = "Bring 2 copies, not 3. The temperature is minus 5 degrees Celsius, not plus 5."
        outputs = {
            "ti": "3 ዘይኰነስ 2 ቅዳሓት ኣምጽእ። እቲ ሙቐት ትሕቲ 5 ዲግሪ ሰልሲየስ ደኣ እምበር 5 ኣይኰነን።",
            "am": "2 ቅጂዎችን አምጡ, 3 አይደለም. የሙቀት መጠኑ ከ 5 ዲግሪ ሴንቲ ግሬድ ሲቀነስ ነው, ሲደመር 5 አይደለም.",
            "so": "Keel laba nuqul, ma ahan saddex. Heerkulku waa shan darajo hoose, ma ahan shan darajo sare.",
            "kmr": "2 kopî bînin, ne 3. Germahî kêm 5 derece Celsius e, ne plus 5."}
        for code, text in outputs.items():
            with self.subTest(language=code):
                check = critical_checks(source, text, "en", code)
                self.assertTrue(check["needs_consultation"])
                self.assertIn("signed_numbers", check["consultation_reasons"])
                self.assertFalse(reinforce(source, "en", code, Candidate(text, "bing_web")).changed)

    def test_real_cldr_data_has_all34_explicit_coverage(self):
        from reinforcement import _calendar_data
        data = _calendar_data()
        self.assertEqual(set(data), set(LANGUAGE_CODES))
        self.assertTrue(all(record["complete"] and len(record["months"]) == 12 for record in data.values()))
        self.assertEqual(data["om"]["months"]["10"]["format"], "Onkoloolessa")
        self.assertEqual(data["om"]["months"]["6"]["format"], "Waxabajjii")

    def test_observed_index_unknown_oromo_weekdays_are_unresolved_not_blindly_replaced(self):
        source = "The appointment is on Tuesday, 13 October 2026, at 09:30, not Thursday at 19:30."
        output = "Yeroo murtaa’e Waaqii, 13 Onkololeessa 2026, sa’aatii 09:30 ti; Waa’essa sa’aatii 19:30 miti."
        check = critical_checks(source, output, "en", "om")
        self.assertEqual(check["calendar_weekdays"]["status"], "unresolved")
        self.assertFalse(check["literal_complete"])
        self.assertFalse(reinforce(source, "en", "om", Candidate(output, "index_web")).changed)

    def test_calendar_glossary_native_anchored_names_and_refusals(self):
        from reinforcement import calendar_glossary
        source = "Meet on Tuesday, 13 October 2026, not Thursday."
        self.assertEqual(calendar_glossary(source, "en", "om"), {"October": "Onkoloolessa", "Tuesday": "Kibxata", "Thursday": "Kamisa"})
        self.assertFalse(calendar_glossary("We may meet Tuesday.", "en", "om"))
        self.assertFalse(calendar_glossary('Keep "13 October 2026" exactly.', "en", "om"))
        self.assertFalse(calendar_glossary("13 October 2026 or14November2026", "en", "om"))

    def test_unknown_month_alternative_cannot_claim_to_resolve_known_calendar_damage(self):
        with patch("reinforcement._calendar_data", return_value=calendar_fixture()):
            decision = reinforce("Meet on 8 October 2028.", "en", "om", Candidate("X 8 Waxabajjii 2028.", "mymemory"), [Candidate("X 8 Imaginarymonth 2028.", "index_web")])
        self.assertEqual(decision.method, "calendar_repair")
        self.assertNotIn("Imaginarymonth", decision.text)

    def test_actual_index_amharic_candidate_repairs_actual_bing_reversal(self):
        source = "The label says 0.5 mg, not 5 mg. The patient has not taken it today. Ask the pharmacist to check the label."
        bad = "መለያው 0.5 mg ሳይሆን 5 mg ይላል. በሽተኛው ዛሬ አልወሰደም. መለያውን እንዲፈትሽ ፋርማሲስቱ ይጠይቁ።"
        actual = "በመለያው ላይ 5 mg ሳይሆን 0.5 mg ተብሎ ጽፏል። ታካሚው ዛሬ አልወሰደውም። ከፋርማሲስቱ መለያውን እንዲፈትሽ ጠይቁ።"
        decision = reinforce(source, "en", "am", Candidate(bad, "bing_web"), [Candidate(actual, "index_web")])
        self.assertEqual(decision.text, actual)
        self.assertEqual(decision.provider, "index_web")
        self.assertEqual(decision.original_primary.text, bad)

    def test_arabic_dual_copies_is_narrow_quantity_equivalence(self):
        for form in ("نسختين", "نسختان"):
            check = critical_checks("Bring only 2 copies.", "أحضر " + form + " فقط.", "en", "ar")
            self.assertTrue(check["literal_complete"])
            self.assertEqual(check["number_equivalences"][0]["value"], "2")
        for source, target in (("Bring 2 copies and 2 envelopes.", "أحضر نسختين."), ("Bring 3 copies.", "أحضر نسختين."), ("Bring 2 copies.", "أحضر نسختين ونسختين."), ("Pay £2 and bring copies.", "أحضر نسختين."), ("Bring 2 copies.", "أحضر نسختين و3 مظاريف.")):
            with self.subTest(source=source, target=target):
                check = critical_checks(source, target, "en", "ar")
                self.assertFalse(check["number_equivalences"])
                self.assertFalse(check["literal_complete"])
        check = critical_checks("Bring 2 copies.", "أحضر نسختين.", "en", "fa")
        self.assertFalse(check["number_equivalences"])

    def test_signed_quantity_prompt_constraints_exclude_arithmetic_ids_and_unsigned_ranges(self):
        from reinforcement import source_signed_quantities
        source = "The temperature is minus 5 degrees Celsius, not plus 5. The label is negative 0.5 mg."
        values = source_signed_quantities(source, "en")
        self.assertEqual([item["signed_number"] for item in values], ["-5", "+5", "-0.5"])
        for source in ("Compute 10 minus 5 mg.", "Compute 10 - 5°C.", "Reference AB-5 mg.", "Keep between 5 and 10°C.", "The range is 5-10°C.", "Order minus 5 copies."):
            with self.subTest(source=source):
                self.assertFalse(source_signed_quantities(source, "en"))
        self.assertEqual([item["signed_number"] for item in source_signed_quantities("Keep at -5°C to +5°C.", "en")], ["-5", "+5"])
        self.assertFalse(source_signed_quantities("minus 5 mg", "fa"))

    def test_arithmetic_minus_is_not_a_unary_signed_quantity(self):
        source = "Calculate 10 minus 5 mg. Do not treat the result as negative 5 mg."
        translated = "10 ካብ 5 mg ኣውጽእ። ነቲ ውጽኢት ከም -5 mg ኣይትውሰዶ።"
        check = critical_checks(source, translated, "en", "ti")
        self.assertEqual(check["signed_numbers"]["source"], ("-5",))
        self.assertEqual(check["signed_numbers"]["status"], "preserved")
        self.assertTrue(check["literal_complete"])
        check = critical_checks("Calculate 10 - 5 mg.", "Calculate 10 - 5 mg.", "en", "en")
        self.assertEqual(check["signed_numbers"]["status"], "not_applicable")

    def test_two_character_native_month_is_recognized(self):
        check = critical_checks("Meet on 22 May 2026.", "22 ሜይ 2026", "en", "am")
        self.assertEqual(check["calendar"]["status"], "preserved")

    def test_all39_historical_critical_outputs_never_receive_guessed_semantic_rewrites(self):
        import json
        from pathlib import Path
        cases = json.loads((Path(__file__).parent / "verification/historical-critical-regressions.json").read_text(encoding="utf-8"))["cases"]
        self.assertEqual(len(cases), 39)
        for case in cases:
            with self.subTest(case=case["id"]):
                primary = Candidate(case["text"], case["provider"])
                decision = reinforce(case["source"], case["source_code"], case["target_code"], primary)
                self.assertEqual(decision.original_primary, primary)
                self.assertIn(decision.method, ("unchanged", "calendar_repair", "negative_promise_repair"))
                self.assertEqual(decision.audit[0]["original_sha256"], case["historical_text_sha256"])
                if decision.changed:
                    self.assertIn(decision.method, ("calendar_repair", "negative_promise_repair"))
                    self.assertTrue(critical_checks(case["source"], decision.text, case["source_code"], case["target_code"])["literal_complete"])

    def test_written_english_temperature_unit_matches_exact_symbol_without_hiding_wrong_unit(self):
        source = "The temperature is minus 5 degrees Celsius, not plus 5 degrees Celsius."
        check = critical_checks(source, "-5°C, +5°C", "en", "ti")
        self.assertTrue(check["literal_complete"])
        self.assertEqual(check["unit_equivalences"][0]["unit"], "°C")
        bad = critical_checks(source, "-5°F, +5°F", "en", "ti")
        self.assertIn("units", bad["violations"])
        self.assertFalse(bad["literal_complete"])
        source = "Keep at minus 5 degrees Celsius, not plus 5."
        good = Candidate("-5°C, +5°C", "index_web")
        decision = reinforce(source, "en", "ti", Candidate("5 ዲግሪ ሴልስየስ, 5", "bing_web"), [good])
        self.assertEqual(decision.text, good.text)

    def test_actual_amharic_money_amount_swap_selects_whole_source_preserving_candidate(self):
        source = "Pay each of the 4 people £7.25. Do not pay £7.25 as the total for all 4 people."
        bad = "ለእያንዳንዳቸው 4 ሰዎች £7.25 ይክፈሉ። ለሁሉም 7.25 ሰዎች በአጠቃላይ £4 አይክፈሉ።"
        good = "ከ4ቱ ሰዎች እያንዳንዱን £7.25 ክፈሉ። ለ4ቱ ሰዎች በአጠቃላይ £7.25 አትክፈሉ።"
        self.assertTrue(all(critical_checks(source, bad, "en", "am")["facts_equal"].values()))
        self.assertIn("currency_amounts", critical_checks(source, bad, "en", "am")["violations"])
        decision = reinforce(source, "en", "am", Candidate(bad, "bing_web"), [Candidate(good, "index_web")])
        self.assertEqual(decision.text, good)
        self.assertEqual(decision.method, "whole_candidate")
        self.assertEqual(decision.original_primary.text, bad)

    def test_currency_amount_pair_controls_localization_ambiguity_and_missing_markers(self):
        source = "Pay £7.25 to each of 4 people."
        for text in ("Pay 7,25 GBP to each of 4 people.", "Pay GBP 7.25 to each of 4 people.", "Pay £7.2500 to each of 4 people."):
            self.assertEqual(critical_checks(source, text, "en", "fr")["currency_amounts"]["status"], "preserved")
        for text in ("Pay 7.25 pounds to each of 4 people.", "Pay to each of 4 people."):
            self.assertNotIn("currency_amounts", critical_checks(source, text, "en", "fr")["violations"])
        check = critical_checks("Pay £1.234 and £7.25.", "Pay £1234 and £7.25.", "en", "fr")
        self.assertNotIn("currency_amounts", check["violations"])
        self.assertEqual(check["currency_amounts"]["status"], "unresolved")
        check = critical_checks("Pay £50 and £50 later.", "Pay £50 once.", "en", "fr")
        self.assertNotIn("currency_amounts", check["violations"])

    def test_dutch_negative_promise_recovery_is_complete_clause_and_quote_safe(self):
        source = 'The child said, "He called me a bastard." Record the child’s exact words. Do not promise to keep abuse secret.'
        bad = 'Het kind zei: "Hij noemde me een bastaard." Noteer de exacte woorden van het kind. Bel niet dat je het misbruik geheim zult houden.'
        actual = 'Het kind zei: "Hij noemde me een bastaard." Noteer de precieze woorden van het kind. Beloof niet dat u misbruik geheim zult houden.'
        decision = reinforce(source, "en", "nl", Candidate(bad, "bing_web"), [Candidate(actual, "index_web")])
        self.assertEqual(decision.text, actual)
        self.assertIn("negative_promise", decision.reasons)
        fixed = reinforce(source, "en", "nl", Candidate(bad, "bing_web"))
        self.assertEqual(fixed.method, "negative_promise_repair")
        self.assertEqual(fixed.text, bad.replace("Bel niet dat", "Beloof niet dat"))
        self.assertEqual(fixed.audit[0]["edit"]["before"], "Bel niet dat je het misbruik geheim zult houden.")
        altered_quote = Candidate(actual.replace("bastaard", "vriend"), "index_web")
        protected = reinforce(source, "en", "nl", Candidate(bad, "bing_web"), [altered_quote])
        self.assertEqual(protected.method, "negative_promise_repair")
        self.assertIn('"Hij noemde me een bastaard."', protected.text)

    def test_dutch_negative_promise_refusals_and_fresh_context(self):
        pairs = [("Say: \"Do not promise to keep it secret.\"", "Bel niet dat je het geheim zult houden."), ("Do not promise to keep it secret.", 'Hij zei: "Bel niet dat je het geheim zult houden."'), ("Do not promise to keep it secret. Do not call the office.", "Bel niet dat je het geheim zult houden. Bel het kantoor niet."), ("Do not promise to keep it secret. Do not promise to reply.", "Bel niet dat je het geheim zult houden."), ("Do not call the office.", "Bel het kantoor niet."), ("Do not promise to reply tonight.", "Bel niet dat restaurant."), ("Do not promise to reply tonight.", 'Bel niet dat je vannacht antwoordt. "unfinished')]
        for source, text in pairs:
            with self.subTest(source=source, text=text):
                self.assertFalse(reinforce(source, "en", "nl", Candidate(text, "bing_web")).changed)
        source = "Do not promise to reply tonight. Keep reference AB-1234."
        text = "Bel niet dat je vanavond antwoordt. Bewaar referentie AB-1234."
        fixed = reinforce(source, "en", "nl", Candidate(text, "bing_web"))
        self.assertEqual(fixed.text, "Beloof niet dat je vanavond antwoordt. Bewaar referentie AB-1234.")
        self.assertFalse(reinforce(source, "en", "nl", Candidate(text, "bing_web"), context=True).changed)

    def test_actual_dutch_reward_instead_of_promise_is_bounded_and_reward_source_refused(self):
        source = 'The child said, "He called me a bastard." Record the child’s exact words. Do not promise to keep abuse secret.'
        bad = 'Het kind zei: "Hij noemde me een bastaard." Noteer de exacte woorden van het kind. Beloon niet om misbruik geheim te houden.'
        decision = reinforce(source, "en", "nl", Candidate(bad, "bing_web"))
        self.assertEqual(decision.method, "negative_promise_repair")
        self.assertEqual(decision.text, bad.replace("Beloon niet om", "Beloof niet om"))
        good = Candidate(bad.replace("Beloon niet om", "Beloof niet om"), "index_web")
        self.assertEqual(reinforce(source, "en", "nl", Candidate(bad, "bing_web"), [good]).method, "whole_candidate")
        for source in ("Do not reward anyone to keep abuse secret.", "Do not reward anyone. Do not promise to keep abuse secret.", "Do not promise to reward anyone."):
            self.assertFalse(reinforce(source, "en", "nl", Candidate("Beloon niet om misbruik geheim te houden.", "bing_web")).changed)

    def test_actual_oromo_unique_corrupted_email_restored_without_touching_prose(self):
        source = "Email help@example.org about case REF-5678. Open https://example.org/help?id=24 and keep the code X_024 unchanged."
        bad = "Dhimma REF-5678 ilaalchisee email@example.org irratti iyyata ergaa. https://example.org/help?id=24 bantee, koodii X_024 osoo hin jijjiirin tursiisi."
        decision = reinforce(source, "en", "om", Candidate(bad, "index_web"))
        self.assertEqual(decision.method, "opaque_literal_repair")
        self.assertEqual(decision.text, bad.replace("email@example.org", "help@example.org"))
        self.assertEqual(decision.original_primary.text, bad)
        self.assertEqual(decision.audit[0]["edit"]["kind"], "email")

    def test_unique_opaque_url_and_reference_recovery_preserves_boundary_punctuation(self):
        cases = [("Open https://example.org/a?x=24.", "ክፈት https://example.net/a?x=24.", "https://example.net/a?x=24", "https://example.org/a?x=24"), ("Keep reference AB-1234.", "X AB-1235!", "AB-1235", "AB-1234")]
        for source, bad, before, after in cases:
            with self.subTest(source=source):
                decision = reinforce(source, "en", "ti", Candidate(bad, "index_web"))
                self.assertEqual(decision.method, "opaque_literal_repair")
                self.assertEqual(decision.text, bad.replace(before, after))

    def test_opaque_literal_repair_refuses_ambiguous_missing_extra_or_other_changed_facts(self):
        cases = [("Mail a@example.org and b@example.org.", "Mail c@example.org and b@example.org."), ("Mail a@example.org.", "Mail someone."), ("Mail a@example.org.", "Mail b@example.org and c@example.org."), ("Mail a@example.org twice.", "Mail b@example.org b@example.org."), ("Mail a@example.org and pay£50.", "Mail b@example.org and pay£500."), ("Mail a@example.org. Keep AB-1234.", "Mail b@example.org. Keep AB-1235."), ("Keep AB-1234 and CD-5678.", "Keep AB-1235 and CD-5678."), ("Mail a@example.org.", "Mail https://example.org/b@example.org."), ("Keep AB-1234.", "Keep xAB-1235y."), ("Mail a@example.org.", "Mail b@example.org. Mention prefixb@example.orgsuffix.")]
        for source, text in cases:
            with self.subTest(source=source, text=text):
                self.assertFalse(reinforce(source, "en", "om", Candidate(text, "index_web")).changed)
        source, text = "Mail a@example.org.", "Mail b@example.org."
        self.assertFalse(reinforce(source, "en", "om", Candidate(text, "index_web"), glossary=True).changed)
        self.assertFalse(reinforce(source, "en", "om", Candidate(text, "index_web"), context=True).changed)

def corruption_test(code):
    def test(self):
        source = "Reference AB-1234. Contact test@example.com. Dose 2 mg, £50."
        primary = Candidate("AB-1235. test@example.net. 20 mg, €50.", "bing_web")
        correct = Candidate("AB-1234. test@example.com. 2 mg, £50.", "google_web")
        decision = reinforce(source, "en", code, primary, [correct])
        self.assertTrue(decision.changed)
        self.assertEqual(decision.text, correct.text)
        self.assertEqual(decision.original_primary.text, primary.text)
        damaged = Candidate("AB-1234. test@example.com. 2 mg, £500.", "google_web")
        self.assertFalse(reinforce(source, "en", code, primary, [damaged]).changed)
    return test

for code in LANGUAGE_CODES:
    setattr(ReinforcementTests, "test_literal_corruption_" + code, corruption_test(code))

if __name__ == "__main__":
    unittest.main()
