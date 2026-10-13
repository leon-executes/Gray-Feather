"""Deterministic safety/contract tests; no live API key or provider calls."""
import csv
import io
import json
import random
import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from engine import (Cancelled, HTTPTransport, LANGUAGES, ProviderConfig,
                    RevisionConflict, StorageError, Store, TranslationError,
                    Translator, check_translation, extract_facts, provider_language,
                    provider_supports, split_text, validate_text)
from engine import source_review_aids

class FakeTransport:
    def __init__(self, response=None, fail=None):
        self.calls, self.response, self.fail = [], response, fail
    def request_json(self, provider, url, payload, headers, deadline, cancel):
        self.calls.append({"provider": provider, "url": url, "payload": payload, "headers": headers})
        if self.fail:
            raise self.fail
        if self.response is not None:
            return self.response(provider, payload) if callable(self.response) else self.response
        if provider == "azure":
            from urllib.parse import parse_qs, urlsplit
            target = parse_qs(urlsplit(url).query)["to"][0]
            return [{"translations": [{"to": target, "text": payload[0]["Text"]}]}]
        if provider == "google":
            return {"data": {"translations": [{"translatedText": payload["q"][0]}]}}
        if provider == "index_web":
            raise TranslationError('service','This fixture has no Index response.')
        return {"translations": [{"text": payload["text"][0]}]}

def warning_codes(source, target, source_code="en", target_code="fr"):
    return {warning.code for warning in check_translation(source, target, source_code, target_code)}

class LanguageCorpusTests(unittest.TestCase):
    def test_all_registered_languages_have_nontrivial_styles_and_explicit_meaning_criteria(self):
        from collections import Counter
        from tests.language_corpus_check import cases
        values=cases()
        self.assertEqual(len(values),204)
        self.assertEqual(Counter(v['target_code'] for v in values),Counter({l.code:6 for l in LANGUAGES}))
        self.assertEqual(len({v['category'] for v in values}),6)
        self.assertTrue(all(v['source_code']!=v['target_code'] for v in values))
        self.assertTrue(all(len(v['critical_semantic_predicates'])>=3 for v in values))
        self.assertTrue(all('not a certified' in v['review_validation'] for v in values))
    def test_lexicon_and_registry_do_not_invent_unmeasured_dictionary_certainty(self):
        root=Path(__file__).resolve().parents[1]/'resources'/'test'
        lexicon=json.loads((root/'translation-lexicon.json').read_text(encoding='utf8'))
        registry=json.loads((root/'translation-provider-quality-registry.json').read_text(encoding='utf8'))
        self.assertEqual({l['code'] for l in lexicon['languages']},{l.code for l in LANGUAGES})
        self.assertEqual({l['language'] for l in registry['languages']},{l.code for l in LANGUAGES})
        self.assertEqual(len(lexicon['entries']),8)
        self.assertTrue(all('To be recorded' in l['target_samples_status'] for l in lexicon['languages']))
        for lang in registry['languages']:
            for route in lang['translation_routes']:
                if not route['observed_target_or_source_cases'] and route['app_mapping_supported']:
                    self.assertEqual(route['live_observation_status'],'Unmeasured in this bound report')
                self.assertIn('No broad quality',route['quality_status'])
        self.assertIn('mixed',registry['independence_rules']['mymemory'].lower())
        self.assertIn('correlated',registry['independence_rules']['lingva'].lower())
    def test_fact_corruption_protection_across_all_language_identities_and_digit_scripts(self):
        # These are fact-token fixtures, not simulated fluent translations or
        # language golds. Language-independent literal checks are the subject.
        source='Amount £50. Time 09:30. Measure 2 mg. Reference GF-4821. Mail person@example.com. Link https://example.org/a?x=50.'
        alphabets={
            'ar':'٠١٢٣٤٥٦٧٨٩','fa':'۰۱۲۳۴۵۶۷۸۹','prs':'۰۱۲۳۴۵۶۷۸۹',
            'bn':'০১২৩৪৫৬৭৮৯','hi':'०१२३४५६७८९','pa':'੦੧੨੩੪੫੬੭੮੯'}
        plain='50 GBP · 09h30 · 2 mg · GF-4821 · person@example.com · https://example.org/a?x=50'
        hard={'numbers','currencies','units','references','identifiers'}
        for lang in LANGUAGES:
            with self.subTest(language=lang.code):
                target=plain
                digits=alphabets.get(lang.code)
                if digits:
                    # Keep immutable reference/link characters exact; localize
                    # only independent displayed amount/clock/measurement.
                    target=plain.replace('50 GBP',''.join(digits[int(c)] for c in '50')+' GBP')
                    target=target.replace('09h30',''.join(digits[int(c)] if c.isdigit() else c for c in '09h30'))
                    target=target.replace('2 mg',digits[2]+' mg')
                self.assertFalse(hard & warning_codes(source,target,'en',lang.code))
                variants={
                  'numbers':target.replace('09h30','09h31') if not digits else target.replace(digits[3]+digits[0],digits[3]+digits[1],1),
                  'currencies':target.replace('GBP','EUR'),
                  'units':target.replace(' mg',' g'),
                  'references':target.replace('GF-4821','GF-4822'),
                  'identifiers':target.replace('person@example.com','other@example.com')}
                for code,corrupt in variants.items():
                    self.assertIn(code,warning_codes(source,corrupt,'en',lang.code),f'{lang.code}: {code}')
                self.assertIn('numbers',warning_codes('Pay 50 now and 50 later.','Pay 50 now.','en',lang.code))
    def test_live_corpus_runner_refuses_paid_profile_before_any_translation(self):
        from tests.language_corpus_check import run
        class Profile:
            calls=0
            def settings(self):return {'providers':{'azure':{'key':'synthetic-account'}}}
            def translate(self,*args,**kwargs):self.calls+=1;raise AssertionError('Paid profile called')
        profile=Profile()
        with self.assertRaises(ValueError):run(profile,languages=['fr'])
        self.assertEqual(profile.calls,0)

class FactTests(unittest.TestCase):
    def test_clock_h_format_is_value_preserving_only_when_exact_and_valid(self):
        self.assertNotIn('numbers', warning_codes('Deadline 17:00 on 12 March 2027.', 'Prazo 17h00 em 12 de março de 2027.', 'en', 'pt'))
        self.assertNotIn('numbers', warning_codes('Call 09:30. Join 10 minutes early.', 'Appel 09h30. Rejoindre 10 minutes avant.', 'en', 'fr'))
        for text in ('09h300', '09h30word', '25h00', '17h90', '17hello'):
            self.assertNotEqual(extract_facts(text)['numbers'], ('09:30',))
        self.assertNotIn('17:00', extract_facts('17hours')['numbers'])
    def test_underscore_error_identifier_is_an_exact_reference(self):
        facts = extract_facts('Keep error E_CONN_204 visible.')
        self.assertEqual(facts['references'], ('E_CONN_204',))
        self.assertEqual(facts['numbers'], ())
        self.assertIn('references', warning_codes('Error E_CONN_204.', '错误 E_CONN_240。', 'en', 'zh'))
    def test_source_idiom_advisory_explains_risk_without_rewriting(self):
        source = "Let's call it a day. We can pick this up tomorrow."
        warnings = source_review_aids(source, 'en')
        self.assertEqual([w.code for w in warnings], ['idiom'])
        self.assertIn('finish work for today', warnings[0].message)
        self.assertIn('resume the task tomorrow', warnings[0].message)
        self.assertIn('both engines', warnings[0].message)
        self.assertEqual(source_review_aids(source, 'fr'), ())
        self.assertEqual(source_review_aids('Bring 2 copies tomorrow.', 'en'), ())
    def test_embedded_instruction_advisory_is_general_source_wording(self):
        for source in ('Translate this sentence from a draft: "The tenant may leave."', 'The draft clause says: "Keep the window open."', 'Keep this text exactly: config_key=user_id'):
            self.assertIn('embedded_instruction', {w.code for w in source_review_aids(source, 'en')})
        self.assertEqual(source_review_aids('Please bring 2 copies.', 'en'), ())
    def test_registered_languages_and_identity(self):
        self.assertEqual(len(LANGUAGES), 34)
        self.assertEqual(len({l.code for l in LANGUAGES}), 34)
        self.assertEqual(provider_language("azure", "prs"), "prs")
        self.assertEqual(provider_language("azure", "ckb"), "ku")
        self.assertEqual(provider_language("azure", "kmr"), "kmr")
        self.assertEqual(provider_language("google", "kmr"), "ku")
        self.assertEqual(provider_language("google", "ckb"), "ckb")
        self.assertEqual(provider_language("azure", "pt", True), "pt-pt")
        self.assertEqual(provider_language("google", "pt", True), "pt-PT")
        self.assertEqual(provider_language("deepl", "pt", True), "PT-PT")
        self.assertFalse(provider_supports("google", "prs", "en"))
        self.assertFalse(provider_supports("azure", "om", "en"))
        with self.assertRaises(TranslationError):
            provider_language("azure", "missing")
    def test_number_and_reference_corruption(self):
        source = "Pay £50 by 14:30. Reference AB-1234."
        correct = "Payez £50 avant 14:30. Référence AB-1234."
        self.assertEqual(warning_codes(source, correct), set())
        for damaged in (correct.replace("£50", "£500"), correct.replace("14:30", "14:03")):
            self.assertIn("numbers", warning_codes(source, damaged))
        self.assertIn("references", warning_codes(source, correct.replace("AB-1234", "AB-1235")))
    def test_unicode_digits_decimal(self):
        source = "The temperature is 38.5°C and the dose is 2 mg."
        correct = "درجة الحرارة ٣٨.٥°C والجرعة ٢ mg."
        self.assertNotIn("numbers", warning_codes(source, correct, "en", "ar"))
        self.assertIn("numbers", warning_codes(source, correct.replace("٣٨.٥", "٣٨.٦"), "en", "ar"))
        self.assertIn("numbers", warning_codes(source, correct.replace("٢ mg", "٢٠ mg"), "en", "ar"))
    def test_link_identity(self):
        source = "Email test@example.com or open https://example.org/a?x=50."
        correct = "Écrivez à test@example.com ou ouvrez https://example.org/a?x=50."
        self.assertEqual(warning_codes(source, correct), set())
        self.assertIn("identifiers", warning_codes(source, correct.replace("example.org/a", "example.org/b")))
        self.assertIn("identifiers", warning_codes(source, correct.replace("test@example.com", "test@example. com")))
    def test_repeated_facts_are_multiset(self):
        self.assertIn("numbers", warning_codes("Pay 50 now and 50 later.", "Payez 50 maintenant."))
    def test_cjk_adjacent_digits_references_and_unit_markers(self):
        self.assertEqual(extract_facts("请携带2份。")['numbers'], ('2',))
        for text in ("予約番号はGF-4821です。", "예약 번호는 GF-4821입니다."):
            facts = extract_facts(text)
            self.assertEqual(facts['references'], ('GF-4821',))
            self.assertEqual(facts['numbers'], ())
        self.assertEqual(extract_facts("温度38.5℃です。")['units'], ('38.5 °C',))
        self.assertEqual(extract_facts("価格50 GBPです。")['currencies'], ('GBP',))
        self.assertIn('references', warning_codes('Reference GF-4821.', '예약 번호는 GF-4822입니다.', 'en', 'ko'))
        self.assertIn('numbers', warning_codes('Bring 2 copies.', '请携带3份。', 'en', 'zh'))
    def test_currency_and_unit_changes(self):
        self.assertIn("currencies", warning_codes("Pay £50.", "Payez $50."))
        self.assertNotIn("currencies", warning_codes("Pay £50.", "Payez 50 GBP."))
        self.assertIn("units", warning_codes("Dose: 2 mg.", "Dose : 2 g."))
        self.assertIn("units", warning_codes("Temperature 38.5°C.", "Température 38.5°F."))
        self.assertNotIn("units", warning_codes("Dose: 2 mcg.", "الجرعة ٢ µg.", "en", "ar"))
        self.assertNotIn("units", warning_codes("Temperature 38.5°C.", "温度 38.5℃.", "en", "zh"))
    def test_accented_currency_words_are_not_measurement_units(self):
        for text in ('50 lîre nedin.', '50 līre', '50 Lîre'):
            self.assertEqual(extract_facts(text)['units'], ())
        self.assertNotIn('units', warning_codes('Do not pay £50.', '50 lîre nedin.', 'en', 'kmr'))
        for text in ('温度38.5℃です。', '온도38.5℃입니다.', '温度38.5°C。'):
            self.assertEqual(extract_facts(text)['units'], ('38.5 °C',))
    def test_inserted_reference(self):
        self.assertIn("references", warning_codes("I have no reference number.", "Référence AB-1234."))
    def test_negation_is_advisory_even_when_correct(self):
        source = "Do not pay £50 today."
        for target in ("Ne payez pas £50 aujourd’hui.", "Payez £50 aujourd’hui."):
            self.assertIn("negation", warning_codes(source, target))
            self.assertNotIn("numbers", warning_codes(source, target))
        self.assertNotIn("confidence", check_translation(source, target)[0].to_dict())
    def test_no_mutating_preprocessing(self):
        source = "38.5 14:30 test@example.com\n\n  Keep spaces\t🙂"
        self.assertEqual(validate_text(source), source)
        self.assertEqual("".join(split_text(source, max_chars=10, max_bytes=30)), source)
    def test_invalid_unicode_and_no_silent_truncation(self):
        for text in ("x\x00y", "\ud800", "x" * 200001):
            with self.assertRaises(TranslationError):
                validate_text(text)
    def test_lossless_chunk_fuzz(self):
        randomizer = random.Random(1501)
        alphabet = "abc £,.！？\n\t🙂 عربى १२ é e\u0301"
        for _ in range(100):
            source = "".join(randomizer.choice(alphabet) for _ in range(randomizer.randint(1, 1000)))
            chars, byte_limit = randomizer.randint(4, 50), randomizer.randint(8, 80)
            chunks = split_text(source, max_chars=chars, max_bytes=byte_limit)
            self.assertEqual("".join(chunks), source)
            self.assertTrue(all(len(c) <= chars and len(c.encode()) <= byte_limit for c in chunks))

class ProviderTests(unittest.TestCase):
    def make(self, *names, transport=None, **kwargs):
        return Translator([ProviderConfig(name, "test:fx" if name == "deepl" else "test") for name in names or ("azure",)], transport=transport or FakeTransport(), **kwargs)
    def test_azure_schema_and_exact_dialect(self):
        fake = FakeTransport()
        translator = self.make(transport=fake)
        result = translator.translate("مرحبا", "prs", "ckb")
        call = fake.calls[0]
        self.assertIn("from=prs", call["url"])
        self.assertIn("to=ku", call["url"])
        self.assertEqual(call["payload"], [{"Text": "مرحبا"}])
        self.assertEqual(result.source_code, "prs")
        self.assertEqual(result.target_code, "ckb")
    def test_google_schema_and_escaped_response(self):
        fake = FakeTransport({"data": {"translations": [{"translatedText": "L&#39;été &amp; café"}]}})
        result = self.make("google", transport=fake).translate("Summer & café", "en", "fr")
        self.assertEqual(result.text, "L'été & café")
        self.assertEqual(fake.calls[0]["payload"]["format"], "text")
    def test_deepl_context_and_glossary(self):
        fake = FakeTransport()
        self.make("deepl", transport=fake).translate("Bank", "en", "fr", context="Financial account", glossary="glossary-1")
        call = fake.calls[0]
        self.assertEqual(call["url"], "https://api-free.deepl.com/v2/translate")
        self.assertEqual(call["payload"]["context"], "Financial account")
        self.assertEqual(call["payload"]["glossary_id"], "glossary-1")
        self.assertEqual(call["headers"]["Authorization"], "DeepL-Auth-Key test:fx")
    def test_context_not_silently_ignored(self):
        fake = FakeTransport()
        with self.assertRaises(TranslationError) as raised:
            self.make(transport=fake).translate("Bank", "en", "fr", context="Account")
        self.assertEqual(raised.exception.kind, "unsupported")
        self.assertFalse(fake.calls)
    def test_no_silent_fallback(self):
        fake = FakeTransport(fail=TranslationError("credentials", "Rejected"))
        with self.assertRaises(TranslationError):
            self.make("azure", "google", transport=fake, allow_fallback=False).translate("Hello", "en", "fr")
        self.assertEqual([c["provider"] for c in fake.calls], ["azure"])
    def test_automatic_selects_supported_pair_before_any_request(self):
        fake = FakeTransport()
        result = self.make("azure", "google", transport=fake).translate("Hello", "en", "om")
        self.assertEqual(result.provider, "google")
        self.assertEqual([call["provider"] for call in fake.calls], ["google"])
    def test_explicit_fallback_all_chunks_single_provider(self):
        class Route(FakeTransport):
            def request_json(self, provider, *args):
                if provider == "azure":
                    self.calls.append({"provider": "azure"})
                    raise TranslationError("credentials", "Rejected")
                return super().request_json(provider, *args)
        fake = Route()
        result = self.make("azure", "google", transport=fake, allow_fallback=True).translate("word " * 2200, "en", "fr")
        self.assertEqual(result.provider, "google")
        self.assertIn("fallback", {w.code for w in result.warnings})
        self.assertEqual(result.text, "word " * 2200)
    def test_partial_chunks_never_success(self):
        class Partial(FakeTransport):
            def request_json(self, provider, *args):
                if self.calls:
                    raise TranslationError("response", "Missing later chunk")
                return super().request_json(provider, *args)
        with self.assertRaises(TranslationError):
            self.make("google", transport=Partial()).translate("word " * 1200, "en", "fr")
    def test_cache_exact_identity_and_context(self):
        fake = FakeTransport()
        translator = self.make(transport=fake)
        translator.translate("سلام", "fa", "en")
        self.assertTrue(translator.translate("سلام", "fa", "en").cached)
        self.assertFalse(translator.translate("سلام", "prs", "en").cached)
        self.assertEqual(len(fake.calls), 2)
        fake2 = FakeTransport()
        deepl = self.make("deepl", transport=fake2)
        for context in ("One", "Two"):
            deepl.translate("Bank", "en", "fr", context=context)
        self.assertEqual(len(fake2.calls), 2)
    def test_cache_bounded(self):
        translator = self.make(cache_size=2)
        for source in ("A", "B", "C"):
            translator.translate(source, "en", "fr")
        self.assertEqual(len(translator._cache), 2)
    def test_independent_engine_and_backtranslation_label(self):
        fake = FakeTransport()
        result = self.make("azure", "google", transport=fake).translate("Hello", "en", "fr", independent_review=True, backtranslate=True)
        self.assertEqual(result.review_provider, "google")
        self.assertEqual(result.backtranslation_provider, "google")
        self.assertEqual([c["provider"] for c in fake.calls], ["azure", "google", "google"])
        result2 = self.make().translate("Hello", "en", "fr", backtranslate=True)
        self.assertTrue(any("correlated" in w.message for w in result2.warnings))
    def test_same_language_no_network(self):
        fake = FakeTransport()
        result = self.make(transport=fake).translate("38.5", "en", "en")
        self.assertEqual(result.text, "38.5")
        self.assertEqual(result.provider, "original")
        self.assertFalse(fake.calls)
    def test_cancel_before_any_call(self):
        cancel = threading.Event()
        cancel.set()
        fake = FakeTransport()
        with self.assertRaises(Cancelled):
            self.make(transport=fake).translate("Hello", "en", "fr", cancel=cancel)
        self.assertFalse(fake.calls)
    def test_malformed_and_wrong_target_rejected(self):
        for response in ({}, [], [{"translations": []}], [{"translations": [{"to": "de", "text": "Text"}]}], [{"translations": [{"to": "fr", "text": ""}]}]):
            with self.subTest(response=response), self.assertRaises(TranslationError):
                self.make(transport=FakeTransport(response)).translate("Hello", "en", "fr")
    def test_endpoint_prevents_credentials_redirect(self):
        for endpoint in ("http://api.deepl.com", "https://evil.test", "https://api.deepl.com@evil.test", "https://api.deepl.com:444", "https://api.deepl.com/?x=1"):
            transport = FakeTransport()
            translator = Translator([ProviderConfig("deepl", "secret", endpoint=endpoint)], transport=transport)
            with self.assertRaises(TranslationError):
                translator.translate("Hello", "en", "fr", provider="deepl")
            self.assertFalse(transport.calls)
        self.assertNotIn("secret", repr(ProviderConfig("azure", "secret")))
    def test_unused_bad_endpoint_and_timeout_do_not_block_selected_provider(self):
        transport = FakeTransport()
        translator = Translator([ProviderConfig("azure", "secret", endpoint="https://invalid.example", timeout=float("nan")), ProviderConfig("google", "synthetic")], transport=transport)
        result = translator.translate("Hello", "en", "fr", provider="google")
        self.assertEqual(result.provider, "google")
        self.assertEqual([call["provider"] for call in transport.calls], ["google"])
    def test_selected_invalid_timeout_never_sends_credentials(self):
        for timeout in (float("nan"), float("inf"), 0, 121, "15", True):
            transport = FakeTransport()
            translator = Translator([ProviderConfig("azure", "secret", timeout=timeout)], transport=transport)
            with self.subTest(timeout=timeout), self.assertRaises(TranslationError) as raised:
                translator.translate("Hello", "en", "fr")
            self.assertEqual(raised.exception.kind, "settings")
            self.assertFalse(transport.calls)
    def test_broken_independent_review_retains_complete_primary(self):
        transport = FakeTransport()
        translator = Translator([ProviderConfig("azure", "secret", endpoint="https://invalid.example"), ProviderConfig("google", "synthetic")], transport=transport)
        result = translator.translate("Hello", "en", "fr", provider="google", independent_review=True)
        self.assertEqual(result.provider, "google")
        self.assertEqual(result.text, "Hello")
        self.assertEqual(result.review_text, "")
        self.assertIn("review_failed", {warning.code for warning in result.warnings})
        self.assertEqual([call["provider"] for call in transport.calls], ["google"])
    def test_provider_identity_still_validated_before_use(self):
        with self.assertRaises(TranslationError):
            Translator([ProviderConfig("unknown", "secret")])

class FreeTransport(FakeTransport):
    """Synthetic public-service session; no live endpoint or real token."""
    PAGE = '<html><script>var params_AbusePreventionHelper = [1700000000000,"synthetic",3600000]; var a={IG:"ABCDEF1234567890"};</script><div data-iid="translator.1"></div></html>'
    def __init__(self, handler=None, page=None):
        super().__init__()
        self.handler, self.page, self.page_calls = handler, self.PAGE if page is None else page, 0
    def request_text(self, provider, url, headers, deadline, cancel):
        self.page_calls += 1
        return self.page
    def request_json(self, provider, url, payload, headers, deadline, cancel):
        from urllib.parse import parse_qs, unquote, urlsplit
        query = parse_qs(urlsplit(url).query)
        self.calls.append({"provider": provider, "url": url, "payload": payload, "headers": headers})
        if self.handler:
            result = self.handler(provider, url, payload, len(self.calls))
            if result is not None:
                return result
        if provider == "google_web":
            source = query["q"][0]
            return [[[source, source, None, None]], None, query["sl"][0]]
        if provider == "bing_web":
            data = parse_qs(payload.decode())
            return [{"translations": [{"text": data["text"][0], "to": data["to"][0]}]}]
        if provider == "mymemory":
            return {"responseStatus": 200, "quotaFinished": False, "responseData": {"translatedText": query["q"][0]}}
        if provider == "lingva":
            return {"translation": unquote(urlsplit(url).path.rsplit("/", 1)[1])}
        if provider == "libretranslate":
            return {"translatedText": payload["q"]}
        # Preserve the official adapters' existing fixture schemas.
        self.calls.pop()
        return super().request_json(provider, url, payload, headers, deadline, cancel)

class FreeProviderTests(unittest.TestCase):
    def test_english_persian_auto_prefers_bing_in_both_directions(self):
        for source, target in (("en", "fa"), ("fa", "en")):
            transport = FreeTransport()
            result = Translator(transport=transport).translate("Synthetic source", source, target, independent_review=True)
            self.assertEqual((result.provider, result.review_provider), ("bing_web", "google_web"))
        self.assertEqual(Translator(transport=FreeTransport()).translate("Hello", "en", "fr").provider, "google_web")
    def test_persian_preference_preserves_explicit_choice_and_disabled_fallback(self):
        transport = FreeTransport()
        result = Translator(transport=transport).translate("Hello", "en", "fa", provider="google_web")
        self.assertEqual(result.provider, "google_web")
        transport = FreeTransport(page="<html>Unavailable</html>")
        result = Translator(transport=transport).translate("Hello", "en", "fa")
        self.assertEqual(result.provider, "google_web")
        self.assertIn("fallback", {w.code for w in result.warnings})
        with self.assertRaises(TranslationError):
            Translator(transport=FreeTransport(page="<html>Unavailable</html>"), allow_fallback=False).translate("Hello", "en", "fa")
    def test_persian_preference_never_adds_a_disabled_provider(self):
        translator = Translator([ProviderConfig("google_web")], transport=FreeTransport())
        self.assertEqual(translator.translate("Hello", "en", "fa").provider, "google_web")
    def test_reverse_outage_falls_back_to_complete_same_engine_without_primary_mutation(self):
        from urllib.parse import parse_qs
        source='Save 2 copies. Reference GF-4821.'
        primary='Enregistrez 2 copies. Référence GF-4821.'
        def handler(provider,url,payload,*args):
            if provider=='google_web':raise TranslationError('quota','HTTP 429',status_code=429)
            if provider=='bing_web':
                form=parse_qs(payload.decode());text=primary if form['to'][0]=='fr' else source
                return [{'translations':[{'text':text,'to':form['to'][0]}]}]
        transport=FreeTransport(handler)
        result=Translator(transport=transport).translate(source,'en','fr',provider='bing_web',independent_review=True,backtranslate=True)
        self.assertEqual((result.provider,result.text),('bing_web',primary))
        self.assertEqual((result.backtranslation_provider,result.backtranslation),('bing_web',source))
        self.assertEqual((result.review_provider,result.review_text),('',''))
        self.assertEqual(sum(c['provider']=='google_web' for c in transport.calls),1)
        reverse_call=transport.calls[-1]
        self.assertEqual(parse_qs(reverse_call['payload'].decode())['text'][0],primary)
        self.assertTrue(any(w.code=='backtranslation' and 'correlated' in w.message for w in result.warnings))
        self.assertNotIn('backtranslation_failed',{w.code for w in result.warnings})
        self.assertTrue(any(t.get('phase')=='backtranslation' and t['provider']=='google_web' for t in result.trace))
    def test_reverse_fallback_respects_disabled_fallback_and_no_false_independence(self):
        def handler(provider,*args):
            if provider=='google_web':raise TranslationError('network','Unavailable')
        transport=FreeTransport(handler)
        result=Translator(transport=transport,allow_fallback=False).translate('Bonjour.','fr','en',provider='bing_web',backtranslate=True)
        self.assertEqual(result.provider,'bing_web')
        self.assertEqual(result.backtranslation,'')
        self.assertEqual([c['provider'] for c in transport.calls],['bing_web','google_web'])
        self.assertIn('backtranslation_failed',{w.code for w in result.warnings})
        self.assertFalse(any(w.code=='backtranslation' for w in result.warnings))
    def test_free_reverse_fallback_does_not_call_a_paid_configured_engine(self):
        def handler(provider,*args):
            if provider=='google_web':raise TranslationError('network','Unavailable')
        transport=FreeTransport(handler)
        configs=[ProviderConfig(p) for p in ('bing_web','google_web')]+[ProviderConfig('azure','synthetic-secret')]
        result=Translator(configs,transport=transport).translate('Hello.','en','fr',provider='bing_web',backtranslate=True)
        self.assertEqual(result.backtranslation_provider,'bing_web')
        self.assertEqual([c['provider'] for c in transport.calls],['bing_web','google_web','bing_web'])
    def test_reverse_fallback_cancel_propagates_without_another_request(self):
        stop=threading.Event()
        def handler(provider,*args):
            if provider=='google_web':
                stop.set();raise TranslationError('network','Unavailable')
        transport=FreeTransport(handler)
        with self.assertRaises(Cancelled):Translator(transport=transport).translate('Hello.','en','fr',provider='bing_web',backtranslate=True,cancel=stop)
        self.assertEqual([c['provider'] for c in transport.calls],['bing_web','google_web'])
    def test_reverse_outage_cannot_start_fallback_after_total_deadline(self):
        def handler(provider,*args):
            if provider=='google_web':
                time.sleep(.11);raise TranslationError('timeout','Timed out')
        transport=FreeTransport(handler)
        result=Translator(transport=transport).translate('Hello.','en','fr',provider='bing_web',backtranslate=True,deadline_seconds=.1)
        self.assertEqual(result.provider,'bing_web')
        self.assertEqual(result.backtranslation,'')
        self.assertEqual([c['provider'] for c in transport.calls],['bing_web','google_web'])
        self.assertIn('backtranslation_failed',{w.code for w in result.warnings})
    def test_independent_reverse_success_never_adds_a_correlated_request(self):
        transport=FreeTransport()
        result=Translator(transport=transport).translate('Hello.','en','fr',provider='bing_web',backtranslate=True)
        self.assertEqual(result.backtranslation_provider,'google_web')
        self.assertEqual([c['provider'] for c in transport.calls],['bing_web','google_web'])
        self.assertTrue(any(w.code=='backtranslation' and 'separate translation engine' in w.message for w in result.warnings))
    def test_observed_429_pauses_only_route_and_avoids_repeated_review_requests(self):
        def handler(provider,*args):
            if provider=='google_web':
                raise TranslationError('quota','HTTP 429',status_code=429)
        transport=FreeTransport(handler); translator=Translator(transport=transport)
        first=translator.translate('First turn.','en','fr',independent_review=True,backtranslate=True)
        second=translator.translate('Second turn.','en','fr',independent_review=True,backtranslate=True)
        self.assertEqual((first.provider,second.provider),('bing_web','bing_web'))
        self.assertEqual(sum(c['provider']=='google_web' for c in transport.calls),1)
        self.assertTrue(any(s['status']=='temporarily_paused' and s['reason']=='observed_429' for s in second.trace))
        self.assertIn('review_failed',{w.code for w in second.warnings})
        self.assertTrue(all(c['provider'] in ('google_web','bing_web') for c in transport.calls))
    def test_429_pause_expires_and_successful_exact_cache_remains_usable(self):
        state={'limited':False}
        def handler(provider,*args):
            if provider=='google_web' and state['limited']:
                raise TranslationError('quota','HTTP 429',status_code=429,retry_after_seconds=10)
        transport=FreeTransport(handler); translator=Translator(transport=transport)
        with patch('engine.time.monotonic',return_value=1000):
            translator.translate('Cached turn.','en','fr')
            state['limited']=True
            translator.translate('Limited turn.','en','fr')
            cached=translator.translate('Cached turn.','en','fr')
            self.assertTrue(cached.cached)
            self.assertEqual(cached.provider,'google_web')
        state['limited']=False
        with patch('engine.time.monotonic',return_value=1011):
            restored=translator.translate('Restored turn.','en','fr')
            self.assertEqual(restored.provider,'google_web')
            self.assertNotIn('google_web',translator._quota_until)
    def test_generic_quota_network_and_unsupported_failures_do_not_create_429_pause(self):
        for kind in ('quota','network','request','response'):
            transport=FreeTransport(lambda p,*args: (_ for _ in ()).throw(TranslationError(kind,'Synthetic failure')) if p=='google_web' else None)
            translator=Translator(transport=transport)
            with self.subTest(kind=kind):
                translator.translate('A.','en','fr');translator.translate('B.','en','fr')
                self.assertEqual(sum(c['provider']=='google_web' for c in transport.calls),2)
                self.assertFalse(translator._quota_until)
    def test_paused_opinion_availability_is_observed_not_health_speculation(self):
        def handler(provider,*args):
            if provider=='google_web':raise TranslationError('quota','HTTP 429',status_code=429)
        transport=FreeTransport(handler);translator=Translator(transport=transport)
        translator.translate('Original.','en','fr')
        calls=len(transport.calls)
        routes=translator.available_opinion_providers('en','fr',['bing_web'])
        self.assertEqual(routes[0]['availability'],'temporarily_paused')
        self.assertGreater(routes[0]['retry_in_seconds'],0)
        self.assertEqual(len(transport.calls),calls)
        opinion=translator.additional_opinion('Original.','en','fr',used_providers=['bing_web'])
        self.assertEqual(opinion.provider,'mymemory')
        self.assertTrue(any(s['status']=='temporarily_paused' for s in opinion.trace))
        self.assertEqual(sum(c['provider']=='google_web' for c in transport.calls),1)
    def test_json_429_pauses_bing_but_mymemory_daily_403_does_not_pause(self):
        for provider,status in (('bing_web',429),('mymemory',403)):
            def handler(p,*args):
                if p==provider:return {'statusCode':status} if p=='bing_web' else {'responseStatus':status,'quotaFinished':True}
            translator=Translator([ProviderConfig(provider)],transport=FreeTransport(handler))
            with self.subTest(provider=provider),self.assertRaises(TranslationError):translator.translate('Hello.','en','fr')
            self.assertEqual(bool(translator._quota_until),status==429)
    def test_actual_http_429_carries_bounded_retry_metadata_without_response_body(self):
        from urllib.error import HTTPError
        from engine import _quota_pause_seconds
        class Opener:
            def open(self,*args,**kwargs):raise HTTPError('https://private.test',429,'Secret response',{'Retry-After':'600'},None)
        with patch('engine.build_opener',return_value=Opener()),self.assertRaises(TranslationError) as raised:
            HTTPTransport(1).request_json('google_web','https://private.test',None,{},time.monotonic()+2,None)
        self.assertEqual((raised.exception.status_code,raised.exception.retry_after_seconds),(429,120))
        self.assertNotIn('Secret',str(raised.exception))
        for value,expected in ((None,60),('garbage',60),('inf',60),('-3',1),('10',10)):
            with self.subTest(value=value):self.assertEqual(_quota_pause_seconds(value),expected)
    def test_explicit_paused_route_without_fallback_returns_before_network(self):
        transport=FreeTransport(lambda p,*args: (_ for _ in ()).throw(TranslationError('quota','HTTP 429',status_code=429)))
        translator=Translator([ProviderConfig('google_web')],allow_fallback=False,transport=transport)
        for source in ('One.','Two.'):
            with self.assertRaises(TranslationError) as error:translator.translate(source,'en','fr',provider='google_web')
            self.assertEqual(error.exception.kind,'quota')
        self.assertEqual(len(transport.calls),1)
    def test_additional_registry_prioritizes_distinct_engine_without_live_health_claim(self):
        translator = Translator(transport=FreeTransport())
        routes = translator.available_opinion_providers('en','fr',['google_web'])
        self.assertEqual([r['provider'] for r in routes], ['bing_web','mymemory'])
        self.assertTrue(routes[0]['independent_of_used'])
        self.assertEqual(routes[0]['provenance'],'separate_engine')
        self.assertFalse(routes[1]['independent_of_used'])
        self.assertEqual(routes[1]['provenance'],'mixed_unverified')
        self.assertTrue(all(r['availability']=='configured_not_probed' for r in routes))
        self.assertFalse(translator.transport.calls)
    def test_third_default_opinion_is_mixed_and_fourth_is_unavailable(self):
        transport=FreeTransport(); translator=Translator(transport=transport)
        source='Bring 2 copies. Do not delete GF-4821.'
        result=translator.additional_opinion(source,'en','fr',used_providers=['google_web','bing_web'])
        self.assertEqual(result.provider,'mymemory')
        self.assertEqual(result.text,source)
        self.assertTrue(any(w.code=='opinion_provenance' and 'mixed' in w.message for w in result.warnings))
        self.assertEqual([c['provider'] for c in transport.calls],['mymemory'])
        self.assertEqual(result.trace[-1]['provenance'],'mixed_unverified')
        self.assertFalse(result.trace[-1]['independent_of_used'])
        with self.assertRaises(TranslationError) as error:
            translator.additional_opinion(source,'en','fr',used_providers=['google_web','bing_web','mymemory'])
        self.assertEqual(error.exception.kind,'opinion_unavailable')
        self.assertEqual(len(transport.calls),1)
    def test_additional_routes_never_spend_keyed_account_or_assume_custom_independence(self):
        configs=[ProviderConfig(p) for p in ('google_web','bing_web','mymemory')]
        configs.extend([ProviderConfig('azure','secret'),ProviderConfig('lingva',endpoint='https://lingva.example/api/v1'),ProviderConfig('libretranslate',endpoint='https://libre.example/translate')])
        translator=Translator(configs,transport=FreeTransport())
        routes={r['provider']:r for r in translator.available_opinion_providers('en','fr',['google_web','bing_web'])}
        self.assertNotIn('azure',routes)
        self.assertEqual(routes['lingva']['provenance'],'correlated_engine')
        self.assertEqual(routes['libretranslate']['provenance'],'server_model_unverified')
        self.assertFalse(any(r['independent_of_used'] for r in routes.values()))
        explicit_keyed=Translator([ProviderConfig('libretranslate','account-secret',endpoint='https://libre.example/translate')],transport=FreeTransport())
        self.assertEqual(explicit_keyed.available_opinion_providers('en','fr'),())
    def test_opinion_rejects_bad_identity_collection_and_invalid_pair_before_transport(self):
        transport=FreeTransport(); translator=Translator(transport=transport)
        for used in ('google_web',None,['typo-provider'],[object()]):
            with self.subTest(used=used), self.assertRaises(TranslationError):
                translator.additional_opinion('Hello','en','fr',used_providers=used)
        with self.assertRaises(TranslationError):translator.additional_opinion('Hello','en','missing')
        with self.assertRaises(TranslationError) as error:translator.additional_opinion('Hello','en','en')
        self.assertEqual(error.exception.kind,'opinion_unavailable')
        self.assertFalse(transport.calls)
    def test_opinion_preserves_dari_identity_and_approximation_label(self):
        translator=Translator(transport=FreeTransport())
        routes=translator.available_opinion_providers('en','prs',['google_web'])
        self.assertEqual(routes[0]['provider'],'bing_web')
        self.assertFalse(routes[0]['language_approximation'])
        result=translator.additional_opinion('Hello','en','prs',used_providers=['google_web','bing_web'])
        self.assertEqual(result.target_code,'prs')
        self.assertIn('language_approximation',{w.code for w in result.warnings})
        self.assertFalse(any(r['provider']=='bing_web' for r in translator.available_opinion_providers('en','om')))
    def test_partial_additional_route_is_discarded_before_complete_fallback(self):
        source=('Alpha beta gamma delta. '*32)+'\nReference GF-4821.'
        count=[0]
        def handler(provider,*args):
            if provider=='mymemory':
                count[0]+=1
                return {'responseStatus':200,'responseData':{'translatedText':'PARTIAL'}} if count[0]==1 else {'responseStatus':429,'quotaFinished':True}
        transport=FreeTransport(handler)
        configs=[ProviderConfig(p) for p in ('google_web','bing_web','mymemory')]+[ProviderConfig('libretranslate',endpoint='https://libre.example/translate')]
        result=Translator(configs,transport=transport).additional_opinion(source,'en','fr',used_providers=['google_web','bing_web'])
        self.assertEqual(result.provider,'libretranslate')
        self.assertEqual(result.text,source)
        self.assertNotIn('PARTIAL',result.text)
        self.assertTrue(any(step.get('phase')=='additional_opinion' and step.get('status')=='quota' for step in result.trace))
        self.assertTrue(any(w.code=='opinion_provenance' and 'unverified' in w.message for w in result.warnings))
        self.assertEqual(next(c['payload']['q'] for c in transport.calls if c['provider']=='libretranslate'),source)
    def test_additional_opinion_warns_corruption_without_rewriting_existing_result(self):
        source='Pay £50. Reference GF-4821.'
        transport=FreeTransport(lambda provider,*args: {'responseStatus':200,'responseData':{'translatedText':'Pay £500. Reference GF-4822.'}} if provider=='mymemory' else None)
        translator=Translator(transport=transport)
        original=translator.translate(source,'en','fr',provider='google_web')
        opinion=translator.additional_opinion(source,'en','fr',used_providers=['google_web','bing_web'])
        self.assertEqual(original.text,source)
        self.assertEqual(opinion.text,'Pay £500. Reference GF-4822.')
        self.assertTrue({'numbers','references'}<={w.code for w in opinion.warnings})
        self.assertNotIn('quality_selection',{w.code for w in opinion.warnings})
    def test_additional_opinion_observes_cancel_and_total_deadline(self):
        stop=threading.Event();stop.set();transport=FreeTransport()
        with self.assertRaises(Cancelled):Translator(transport=transport).additional_opinion('Hello','en','fr',cancel=stop)
        self.assertFalse(transport.calls)
        stop.clear()
        def cancel_after(*args):stop.set()
        with self.assertRaises(Cancelled):Translator(transport=FreeTransport(cancel_after)).additional_opinion('Hello','en','fr',cancel=stop)
        def late(*args):time.sleep(.12)
        with self.assertRaises(TranslationError) as error:
            Translator(transport=FreeTransport(late)).additional_opinion('Hello','en','fr',deadline_seconds=.1)
        self.assertEqual(error.exception.kind,'timeout')
        for timeout in (True,'30',float('nan'),0,181):
            with self.subTest(timeout=timeout),self.assertRaises(TranslationError):
                Translator(transport=transport).additional_opinion('Hello','en','fr',deadline_seconds=timeout)
    def test_invalid_unused_configuration_is_not_advertised_or_called(self):
        transport=FreeTransport()
        configs=[ProviderConfig('lingva',endpoint='http://lingva.example/api/v1'),ProviderConfig('mymemory',timeout=float('nan'))]
        translator=Translator(configs,transport=transport)
        self.assertEqual(translator.available_opinion_providers('en','fr'),())
        with self.assertRaises(TranslationError) as error:translator.additional_opinion('Hello','en','fr')
        self.assertEqual(error.exception.kind,'opinion_unavailable')
        self.assertFalse(transport.calls)
    def test_disabled_fallback_applies_to_an_additional_opinion_too(self):
        def handler(provider,*args):
            if provider=='mymemory':return {'responseStatus':429,'quotaFinished':True}
        transport=FreeTransport(handler)
        configs=[ProviderConfig('mymemory'),ProviderConfig('libretranslate',endpoint='https://libre.example/translate')]
        with self.assertRaises(TranslationError) as error:
            Translator(configs,transport=transport,allow_fallback=False).additional_opinion('Hello','en','fr')
        self.assertEqual(error.exception.kind,'opinion_unavailable')
        self.assertEqual([call['provider'] for call in transport.calls],['mymemory'])
    def test_corrupted_email_selects_entire_fact_preserving_alternative(self):
        source='Reference GF-4821. Send 2 copies to review@example.com.'
        wrong='Referans GF-4821. 2 kopyayı inceleme@example.com adresine gönderin.'
        correct='Referans GF-4821. 2 kopyayı review@example.com adresine gönderin.'
        def handler(provider, *args):
            return [[[wrong, source]]] if provider=='google_web' else [{'translations':[{'text':correct,'to':'tr'}]}]
        result=Translator(transport=FreeTransport(handler)).translate(source,'en','tr',independent_review=True)
        self.assertEqual((result.provider,result.text),('bing_web',correct))
        self.assertEqual((result.review_provider,result.review_text),('google_web',wrong))
        self.assertEqual(result.trace[-1]['reason'],'address_identity')
        codes={w.code for w in result.warnings}
        self.assertIn('quality_selection',codes)
        self.assertIn('review_identifiers',codes)
        self.assertNotIn('identifiers',codes)
    def test_corrupted_web_address_and_reference_use_complete_alternative(self):
        pairs=[('Open https://example.org/a.','Ouvrez https://example.org/b.','Ouvrez https://example.org/a.','address_identity'),
               ('Reference E_CONN_204.','Référence E_CONN_240.','Référence E_CONN_204.','reference_identity')]
        for source,wrong,correct,reason in pairs:
            def handler(provider,*args):
                return [[[wrong,source]]] if provider=='google_web' else [{'translations':[{'text':correct,'to':'fr'}]}]
            with self.subTest(reason=reason):
                result=Translator(transport=FreeTransport(handler)).translate(source,'en','fr',independent_review=True)
                self.assertEqual(result.provider,'bing_web')
                self.assertEqual(result.text,correct)
                self.assertEqual(result.trace[-1]['reason'],reason)
    def test_address_selection_requires_all_fact_atoms_preserved(self):
        source='Send 2 copies. Reference GF-4821. Pay £50. Email review@example.com.'
        wrong=source.replace('review@example.com','wrong@example.com')
        candidates=[source.replace('2 copies','two copies'),source.replace('£50','€50'),source.replace('GF-4821','GF-4822'),source+' Also 10.',source+' Visit https://extra.example.']
        for alternative in candidates:
            def handler(provider,*args):
                return [[[wrong,source]]] if provider=='google_web' else [{'translations':[{'text':alternative,'to':'fr'}]}]
            with self.subTest(alternative=alternative):
                result=Translator(transport=FreeTransport(handler)).translate(source,'en','fr',independent_review=True)
                self.assertEqual(result.provider,'google_web')
                self.assertNotIn('quality_selection',{w.code for w in result.warnings})
    def test_corrupted_address_without_review_is_flagged_not_rewritten(self):
        source='Email review@example.com.'
        wrong='Email wrong@example.com.'
        result=Translator(transport=FreeTransport(lambda provider,*args: [[[wrong,source]]] if provider=='google_web' else None)).translate(source,'en','fr')
        self.assertEqual(result.text,wrong)
        self.assertEqual(result.provider,'google_web')
        self.assertIn('identifiers',{w.code for w in result.warnings})
        self.assertNotIn('quality_selection',{w.code for w in result.warnings})
    def test_source_semantic_advisories_do_not_vote_or_rewrite_outputs(self):
        source="Let's call it a day."
        literal="Disons que c'est un jour."
        result=Translator(transport=FreeTransport(lambda provider,*args: [[[literal,source]]] if provider=='google_web' else None)).translate(source,'en','fr',independent_review=True)
        self.assertEqual(result.text,literal)
        self.assertEqual(result.provider,'google_web')
        self.assertIn('idiom',{w.code for w in result.warnings})
        self.assertNotIn('quality_selection',{w.code for w in result.warnings})
    def test_bing_translation_plus_transliteration_metadata_is_valid(self):
        fixture = [{"translations": [{"to": "en", "text": "Do not cancel."}]}, {"inputTransliteration": "la tulghi", "script": "Latn"}]
        transport = FreeTransport(lambda provider, *args: fixture if provider == 'bing_web' else None)
        result = Translator([ProviderConfig('bing_web')], transport=transport).translate('لا تلغ', 'ar', 'en')
        self.assertEqual(result.provider, 'bing_web')
        self.assertEqual(result.text, 'Do not cancel.')
    def test_bing_extra_translation_or_unknown_metadata_is_rejected(self):
        first = {"translations": [{"to": "en", "text": "Do not cancel."}]}
        for extra in (first, {'unrecognised': 'extra'}, {'script': ['Latn']}, {}):
            transport = FreeTransport(lambda provider, *args: [first, extra] if provider == 'bing_web' else None)
            with self.subTest(extra=extra):
                result = Translator(transport=transport).translate('لا تلغ', 'ar', 'en', provider='bing_web')
                self.assertEqual(result.provider, 'google_web')
                self.assertTrue(any(t.get('provider') == 'bing_web' and t.get('phase') == 'parse' for t in result.trace))
    def test_currency_swap_selects_entire_fact_preserving_independent_result(self):
        original = 'Please bring 2 copies. Reference GF-4821. Do not pay £50.'
        wrong = 'Breng 2 kopieën. Referentie GF-4821. Betaal geen €50.'
        corrected = 'Neem 2 kopieën mee. Referentie GF-4821. Betaal geen £50.'
        def handler(provider, *args):
            return [[[wrong, original]]] if provider == 'google_web' else [{'translations': [{'text': corrected, 'to': 'nl'}]}]
        result = Translator(transport=FreeTransport(handler)).translate(original, 'en', 'nl', independent_review=True)
        self.assertEqual(result.text, corrected)
        self.assertEqual(result.provider, 'bing_web')
        self.assertEqual(result.review_text, wrong)
        self.assertEqual(result.review_provider, 'google_web')
        codes = {w.code for w in result.warnings}
        self.assertIn('quality_selection', codes)
        self.assertNotIn('currencies', codes)
        self.assertIn('review_currencies', codes)
        self.assertEqual(result.trace[-1]['status'], 'quality_selected')
    def test_currency_word_localisation_does_not_trigger_selection(self):
        original, primary, alternative = 'Pay £50.', 'Payez 50 livres sterling.', 'Payez £50.'
        def handler(provider, *args):
            return [[[primary, original]]] if provider == 'google_web' else [{'translations': [{'text': alternative, 'to': 'fr'}]}]
        result = Translator(transport=FreeTransport(handler)).translate(original, 'en', 'fr', independent_review=True)
        self.assertEqual(result.provider, 'google_web')
        self.assertEqual(result.text, primary)
        self.assertNotIn('quality_selection', {w.code for w in result.warnings})
        self.assertIn('currencies', {w.code for w in result.warnings})
    def test_official_context_or_glossary_route_is_not_automatically_replaced(self):
        source = 'Pay £50.'
        def handler(provider, *args):
            if provider == 'deepl':
                return {'translations': [{'text': 'Payez €50.'}]}
            return [[['Payez £50.', source]]]
        result = Translator([ProviderConfig('deepl', 'synthetic:fx'), ProviderConfig('google_web')], transport=FreeTransport(handler)).translate(source, 'en', 'fr', context='Billing instructions', glossary='billing-1', independent_review=True)
        self.assertEqual(result.provider, 'deepl')
        self.assertEqual(result.review_provider, 'google_web')
        self.assertNotIn('quality_selection', {w.code for w in result.warnings})
    def test_currency_selection_requires_preserved_references_and_no_added_numeric_facts(self):
        original, wrong = 'Reference GF-4821. Pay £50.', 'Referentie GF-4821. Betaal €50.'
        for alternative in ('Referentie GF-4822. Betaal £50.', 'Referentie GF-4821. Betaal £500.', 'Referentie GF-4821. Betaal £50 en 10.'):
            def handler(provider, *args):
                return [[[wrong, original]]] if provider == 'google_web' else [{'translations': [{'text': alternative, 'to': 'nl'}]}]
            with self.subTest(alternative=alternative):
                result = Translator(transport=FreeTransport(handler)).translate(original, 'en', 'nl', independent_review=True)
                self.assertEqual(result.provider, 'google_web')
                self.assertNotIn('quality_selection', {w.code for w in result.warnings})
    def test_dari_approximation_label_identifies_only_the_alternative(self):
        result = Translator(transport=FreeTransport()).translate('Hello', 'en', 'prs', independent_review=True)
        self.assertEqual(result.provider, 'bing_web')
        self.assertEqual(result.review_provider, 'google_web')
        warning = next(w for w in result.warnings if w.code == 'language_approximation')
        self.assertTrue(warning.message.startswith('Alternative translation:'))
    def test_new_default_is_free_without_credentials(self):
        transport = FreeTransport()
        translator = Translator(transport=transport)
        self.assertEqual(translator.enabled_order, ("google_web", "bing_web", "mymemory"))
        self.assertTrue(translator.allow_fallback)
        result = translator.translate("Hello", "en", "fr")
        self.assertEqual(result.provider, "google_web")
        self.assertEqual(result.text, "Hello")
        self.assertIsNone(transport.calls[0]["payload"])
        self.assertFalse(any("key=" in c["url"] for c in transport.calls))
    def test_explicit_free_route_falls_back_when_enabled(self):
        def fail_google(provider, *args):
            if provider == "google_web":
                raise TranslationError("quota", "Rate limit")
        transport = FreeTransport(fail_google)
        result = Translator(transport=transport).translate("Hello", "en", "fr", provider="google_web")
        self.assertEqual(result.provider, "bing_web")
        self.assertIn("fallback", {w.code for w in result.warnings})
        self.assertEqual([c["provider"] for c in transport.calls], ["google_web", "bing_web"])
        self.assertEqual(transport.page_calls, 1)
    def test_google_partial_and_malformed_segments_use_complete_fallback(self):
        for damaged in ([[["Bonjour", "Hell"]]], [[["Bonjour", "Hello"], [None, "there"]]], {"data": "wrong"}, [[]]):
            def handle(provider, *args):
                if provider == "google_web":
                    return damaged
            with self.subTest(response=damaged):
                result = Translator(transport=FreeTransport(handle)).translate("Hello there", "en", "fr")
                self.assertEqual(result.provider, "bing_web")
                self.assertEqual(result.text, "Hello there")
    def test_late_chunk_failure_restarts_whole_turn_on_one_provider(self):
        def handle(provider, url, payload, count):
            if provider == "google_web" and count == 1:
                from urllib.parse import parse_qs, urlsplit
                content = parse_qs(urlsplit(url).query)["q"][0]
                return [[["PARTIAL-GOOGLE", content]]]
            if provider == "google_web":
                raise TranslationError("quota", "Rate limit")
        source = "Word 38.5 AB-1234. " * 420 + "🙂"
        transport = FreeTransport(handle)
        translator = Translator(transport=transport)
        result = translator.translate(source, "en", "fr")
        self.assertEqual(result.provider, "bing_web")
        self.assertEqual(result.text, source)
        self.assertNotIn("PARTIAL-GOOGLE", result.text)
        self.assertFalse(any(key[3] == "google_web" for key in translator._cache))
    def test_google_full_multi_segment_source_coverage(self):
        transport = FreeTransport(lambda provider, *args: [[["Bonjour. ", "Hello. "], ["Comment ça va?", "How are you?"]]] if provider == "google_web" else None)
        result = Translator(transport=transport).translate("Hello. How are you?", "en", "fr")
        self.assertEqual(result.text, "Bonjour. Comment ça va?")
        self.assertEqual(result.provider, "google_web")
    def test_free_review_uses_separate_engine_without_a_key(self):
        transport = FreeTransport()
        result = Translator(transport=transport).translate("£50 at 14:30", "en", "fr", independent_review=True)
        self.assertEqual(result.provider, "google_web")
        self.assertEqual(result.review_provider, "bing_web")
        self.assertEqual(result.review_text, "£50 at 14:30")
        self.assertIn("independent_review", {w.code for w in result.warnings})
        self.assertEqual([c["provider"] for c in transport.calls], ["google_web", "bing_web"])
        self.assertTrue(all(c["headers"].get("Authorization") is None for c in transport.calls))
    def test_google_mirror_and_unknown_memory_are_not_independent(self):
        transport = FreeTransport()
        translator = Translator([ProviderConfig("google_web"), ProviderConfig("lingva", endpoint="https://lingva.example"), ProviderConfig("google", "synthetic"), ProviderConfig("mymemory")], transport=transport)
        result = translator.translate("Hello", "en", "fr", independent_review=True)
        self.assertEqual(result.review_text, "")
        self.assertIn("review_unavailable", {w.code for w in result.warnings})
        self.assertEqual(len(transport.calls), 1)
    def test_microsoft_frontends_are_not_independent(self):
        transport = FreeTransport()
        result = Translator([ProviderConfig("bing_web"), ProviderConfig("azure", "synthetic")], transport=transport).translate("Hello", "en", "fr", independent_review=True)
        self.assertEqual(result.review_text, "")
        self.assertEqual(len(transport.calls), 1)
    def test_review_checks_also_reveal_corrupted_numbers(self):
        def handle(provider, url, payload, *args):
            if provider == "bing_web":
                return [{"translations": [{"text": "Pay £500", "to": "fr"}]}]
        result = Translator(transport=FreeTransport(handle)).translate("Pay £50", "en", "fr", independent_review=True)
        self.assertIn("review_numbers", {w.code for w in result.warnings})
        self.assertEqual(result.text, "Pay £50")
    def test_failed_public_session_review_retains_primary(self):
        result = Translator(transport=FreeTransport(page="<html>Challenge</html>")).translate("Hello", "en", "fr", independent_review=True)
        self.assertEqual(result.provider, "google_web")
        self.assertEqual(result.text, "Hello")
        self.assertEqual(result.review_text, "")
        self.assertIn("review_failed", {w.code for w in result.warnings})
    def test_bing_session_reused_and_sensitive_nonce_not_in_trace(self):
        transport = FreeTransport()
        translator = Translator([ProviderConfig("bing_web")], transport=transport)
        first = translator.translate("Word " * 1200, "en", "fr")
        translator.translate("Different source", "en", "fr")
        self.assertEqual(transport.page_calls, 1)
        self.assertEqual(first.text, "Word " * 1200)
        self.assertNotIn("synthetic", json.dumps(first.to_dict()))
        self.assertNotIn("1700000000000", json.dumps(first.to_dict()))
        translator._bing_until = 0
        translator.translate("New source", "en", "fr")
        self.assertEqual(transport.page_calls, 2)
    def test_bing_rejected_session_refresh_once(self):
        def handle(provider, url, payload, count):
            if provider == "bing_web" and count == 1:
                return {"statusCode": 403}
        transport = FreeTransport(handle)
        result = Translator([ProviderConfig("bing_web")], transport=transport).translate("Hello", "en", "fr")
        self.assertEqual(result.text, "Hello")
        self.assertEqual(transport.page_calls, 2)
        self.assertEqual(len(transport.calls), 2)
    def test_bing_challenge_falls_back_without_bypass(self):
        transport = FreeTransport(page="<html>Please complete a CAPTCHA</html>")
        result = Translator(transport=transport).translate("Hello", "en", "fr", provider="bing_web")
        self.assertEqual(result.provider, "google_web")
        self.assertEqual(transport.page_calls, 1)
        self.assertEqual([c["provider"] for c in transport.calls], ["google_web"])
    def test_dari_uses_exact_microsoft_then_labelled_persian_fallback(self):
        transport = FreeTransport()
        result = Translator(transport=transport).translate("Hello", "en", "prs")
        self.assertEqual(result.provider, "bing_web")
        from urllib.parse import parse_qs
        self.assertEqual(parse_qs(transport.calls[0]["payload"].decode())["to"], ["prs"])
        self.assertNotIn("language_approximation", {w.code for w in result.warnings})
        result2 = Translator(transport=FreeTransport(page="<html>Unavailable</html>")).translate("Hello", "en", "prs")
        self.assertEqual(result2.provider, "google_web")
        self.assertEqual(result2.target_code, "prs")
        self.assertIn("language_approximation", {w.code for w in result2.warnings})
    def test_exact_portuguese_and_kurdish_mappings(self):
        for provider in ("google_web", "mymemory", "lingva"):
            self.assertEqual(provider_language(provider, "pt", True), "pt-PT")
            self.assertEqual(provider_language(provider, "kmr"), "ku")
            self.assertEqual(provider_language(provider, "ckb"), "ckb")
        self.assertEqual(provider_language("bing_web", "ckb"), "ku")
        self.assertEqual(provider_language("bing_web", "kmr"), "kmr")
        self.assertFalse(provider_supports("bing_web", "om", "en"))
    def test_mymemory_request_limits_are_utf8_bytes(self):
        from urllib.parse import parse_qs, urlsplit
        transport = FreeTransport()
        source = "🙂 العربية abc. " * 80
        result = Translator([ProviderConfig("mymemory")], transport=transport).translate(source, "ar", "en")
        self.assertEqual(result.text, source)
        self.assertGreater(len(transport.calls), 1)
        self.assertTrue(all(len(parse_qs(urlsplit(c["url"]).query)["q"][0].encode()) <= 500 for c in transport.calls))
    def test_mymemory_quota_error_and_malformed_data_are_never_translation(self):
        cases = [[], {}, {"responseStatus": 403, "responseData": {"translatedText": "Quota exceeded"}}, {"responseStatus": 200, "quotaFinished": True, "responseData": {"translatedText": "Quota exceeded"}}, {"responseStatus": 200, "responseData": {"translatedText": "MYMEMORY WARNING: YOU USED ALL AVAILABLE FREE TRANSLATIONS"}}, {"responseStatus": 200, "responseData": {"translatedText": 123}}]
        for damaged in cases:
            def handle(provider, *args):
                return damaged if provider == "mymemory" else None
            with self.subTest(response=damaged):
                result = Translator(transport=FreeTransport(handle)).translate("Hello", "en", "fr", provider="mymemory")
                self.assertEqual(result.provider, "google_web")
                self.assertEqual(result.text, "Hello")
    def test_optional_server_endpoint_validation_before_any_source_leaves(self):
        for provider in ("lingva", "libretranslate"):
            for endpoint in ("", "http://external.example", "https://name:secret@external.example", "https://external.example/?q=bad"):
                transport = FreeTransport()
                translator = Translator([ProviderConfig(provider, endpoint=endpoint)], transport=transport)
                with self.subTest(provider=provider, endpoint=endpoint), self.assertRaises(TranslationError):
                    translator.translate("Hello", "en", "fr")
                self.assertFalse(transport.calls)
    def test_optional_server_schemas_and_url_quoting(self):
        for provider, endpoint in (("lingva", "https://lingva.example"), ("libretranslate", "http://127.0.0.1:5000")):
            transport = FreeTransport()
            source = "Hello / ? # & café"
            result = Translator([ProviderConfig(provider, endpoint=endpoint)], transport=transport).translate(source, "en", "fr")
            self.assertEqual(result.text, source)
            if provider == "lingva":
                self.assertIn("%2F", transport.calls[0]["url"])
                self.assertIn("%3F", transport.calls[0]["url"])
            else:
                self.assertEqual(transport.calls[0]["url"], "http://127.0.0.1:5000/translate")
                self.assertNotIn("api_key", transport.calls[0]["payload"])
    def test_same_language_and_cancel_use_no_public_session(self):
        transport = FreeTransport()
        translator = Translator(transport=transport)
        self.assertEqual(translator.translate("Hello", "en", "en").text, "Hello")
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(Cancelled):
            translator.translate("Hello", "en", "fr", cancel=cancel)
        self.assertFalse(transport.calls)
        self.assertEqual(transport.page_calls, 0)

class ServiceProviderIsolationTests(unittest.TestCase):
    def test_explicit_google_works_when_inactive_azure_endpoint_is_invalid(self):
        from app import Service
        with tempfile.TemporaryDirectory(prefix="engine-service-", dir=tempfile.tempdir or Path(__file__).parents[1]) as directory:
            service = Service(directory)
            # Synthetic credentials in memory only; do not access a real account.
            service._settings._data["providers"]["azure"].update(key="synthetic-azure", endpoint="https://invalid.example")
            service._settings._data["providers"]["google"].update(key="synthetic-google")
            transport = FakeTransport()
            with patch("engine.HTTPTransport", return_value=transport):
                result = service.translate("Hello", "en", "fr", provider="google")
            self.assertEqual(result["provider"], "google")
            # The invalid independent Azure configuration remains isolated;
            # optional reverse review can now use the selected official route.
            called = [call['provider'] for call in transport.calls]
            self.assertEqual(called.count('google'), 2)
            self.assertNotIn('azure', called)
            self.assertTrue(set(called) <= {'google','index_web'})
            self.assertEqual(result["backtranslation_provider"], "google")

class TransportTests(unittest.TestCase):
    def test_get_text_get_json_and_form_post_share_bounded_transport(self):
        requests, openers = [], []
        class Opener:
            def open(self, request, **kwargs):
                requests.append(request)
                body = b'public page' if request.full_url.endswith('/translator') else b'{"value": "ok"}'
                return io.BytesIO(body)
        def build(*handlers):
            openers.append(handlers)
            return Opener()
        transport = HTTPTransport(1)
        with patch("engine.build_opener", side_effect=build):
            limit = time.monotonic() + 2
            self.assertEqual(transport.request_text("bing_web", "https://www.bing.com/translator", {}, limit, None), "public page")
            self.assertEqual(transport.request_json("google_web", "https://example.test/translate?q=hello", None, {}, limit, None), {"value": "ok"})
            self.assertEqual(transport.request_json("bing_web", "https://example.test/translate", b"text=hello", {"Content-Type": "application/x-www-form-urlencoded"}, limit, None), {"value": "ok"})
        self.assertEqual([request.get_method() for request in requests], ["GET", "GET", "POST"])
        self.assertEqual(requests[-1].data, b"text=hello")
        self.assertTrue(all(handlers[1].cookiejar is transport._cookies for handlers in openers))
    def test_public_403_message_does_not_ask_for_a_paid_key_or_leak_url(self):
        from urllib.error import HTTPError
        class Opener:
            def open(self, *args, **kwargs):
                raise HTTPError("https://example.test/?q=private-source", 403, "Secret response", {}, None)
        with patch("engine.build_opener", return_value=Opener()), self.assertRaises(TranslationError) as raised:
            HTTPTransport(1).request_json("google_web", "https://example.test", None, {}, time.monotonic() + 2, None)
        self.assertEqual(raised.exception.kind, "credentials")
        self.assertIn("public-service session", str(raised.exception))
        self.assertNotIn("key", str(raised.exception))
        self.assertNotIn("private", str(raised.exception))
    def test_default_worker_slots_survive_translator_replacement(self):
        self.assertIs(HTTPTransport()._slots, HTTPTransport()._slots)
        self.assertIsNot(HTTPTransport(1)._slots, HTTPTransport(1)._slots)
    def test_hard_deadline_even_with_stalled_open(self):
        release = threading.Event()
        class Stalled:
            def open(self, *args, **kwargs):
                release.wait(3)
                raise OSError("Secret contents must not escape")
        transport = HTTPTransport(1)
        try:
            with patch("engine.build_opener", return_value=Stalled()):
                before = time.monotonic()
                with self.assertRaises(TranslationError) as raised:
                    transport.request_json("azure", "https://example.test", {}, {}, before + .15, None)
                self.assertEqual(raised.exception.kind, "timeout")
                self.assertLess(time.monotonic() - before, .7)
                with self.assertRaises(TranslationError) as busy:
                    transport.request_json("azure", "https://example.test", {}, {}, time.monotonic() + 1, None)
                self.assertEqual(busy.exception.kind, "busy")
        finally:
            release.set()
    def test_cancellation_during_stalled_open(self):
        release, cancel = threading.Event(), threading.Event()
        class Stalled:
            def open(self, *args, **kwargs):
                release.wait(3)
                raise OSError("Secret")
        timer = threading.Timer(.1, cancel.set)
        timer.start()
        try:
            with patch("engine.build_opener", return_value=Stalled()):
                before = time.monotonic()
                with self.assertRaises(Cancelled):
                    HTTPTransport().request_json("azure", "https://example.test", {}, {}, before + 2, cancel)
                self.assertLess(time.monotonic() - before, .7)
        finally:
            release.set()
            timer.join()

class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="engine-test-", dir=tempfile.tempdir or Path(__file__).parents[1])
        self.path = Path(self.temporary.name) / "history.sqlite3"
        self.store = Store(self.path)
        self.conversation = self.store.new_conversation("Meeting العربية")
    def tearDown(self):
        self.temporary.cleanup()
    def save(self, text="38.5 14:30 test@example.com", **kwargs):
        return self.store.save_turn(self.conversation["id"], "en", "ar", text, "٣٨.٥ ١٤:٣٠", "azure", **kwargs)
    def test_unicode_original_and_revisions(self):
        raw = "38.5 14:30 test@example.com\n🙂 العربية"
        turn = self.save(raw)
        edited = self.store.save_turn(self.conversation["id"], "en", "ar", raw, "New output", "azure", reviewed_source="Corrected source", turn_id=turn["id"], expected_revision=1)
        self.assertEqual(edited["raw_source"], raw)
        self.assertEqual(edited["revision"], 2)
        revisions = self.store.get_revisions(turn["id"])
        self.assertEqual(len(revisions), 2)
        self.assertEqual(revisions[0]["reviewed_source"], raw)
        self.assertEqual(revisions[1]["reviewed_source"], "Corrected source")
        with self.assertRaises(StorageError):
            self.store.save_turn(self.conversation["id"], "en", "ar", "Overwritten", turn_id=turn["id"])
    def test_revision_conflict(self):
        turn = self.save()
        with self.assertRaises(RevisionConflict):
            self.save(turn_id=turn["id"], expected_revision=0)
        self.assertEqual(len(self.store.get_revisions(turn["id"])), 1)
    def test_turn_order_and_speakers(self):
        for speaker in ("1", "2", "1"):
            self.save(speaker=speaker)
        turns = self.store.get_conversation(self.conversation["id"])["turns"]
        self.assertEqual([t["seq"] for t in turns], [1, 2, 3])
        self.assertEqual([t["speaker"] for t in turns], ["1", "2", "1"])
        self.assertEqual(len({t["id"] for t in turns}), 3)
    def test_whole_snapshot_drafts_and_noop(self):
        data = self.store.get_conversation(self.conversation["id"])
        data["drafts"] = {"1": "Unsaved typing 🙂", "2": "العربية"}
        data["turns"] = [{"id": "gui-id-1", "seq": 1, "speaker": "1", "source_lang": "en", "target_lang": "ar", "raw_source": "Hello", "reviewed_source": "Hello", "translated_text": "مرحبا", "provider": "azure", "warnings": []}]
        saved = self.store.save_conversation(data)
        self.assertEqual(saved["turns"][0]["id"], "gui-id-1")
        self.assertEqual(saved["drafts"], data["drafts"])
        second = self.store.save_conversation(saved)
        self.assertEqual(second["revision"], saved["revision"])
        self.assertEqual(len(self.store.get_revisions("gui-id-1")), 1)
        reopened = Store(self.path).get_conversation(saved["id"])
        self.assertEqual(reopened["drafts"], data["drafts"])
    def test_whole_snapshot_rollback(self):
        turn = self.save()
        data = self.store.get_conversation(self.conversation["id"])
        data["turns"][0]["translated_text"] = "Should roll back"
        data["turns"].append({"source_lang": "unknown", "target_lang": "ar", "raw_source": "bad"})
        with self.assertRaises(StorageError):
            self.store.save_conversation(data)
        self.assertNotEqual(self.store.get_conversation(self.conversation["id"])["turns"][0]["translated_text"], "Should roll back")
        self.assertEqual(len(self.store.get_revisions(turn["id"])), 1)
    def test_gui_new_uuid_conversation_atomic(self):
        data = {"id": "new-gui-conversation", "title": "New GUI", "revision": 0, "drafts": {"1": "Draft", "2": ""}, "turns": []}
        created = self.store.save_conversation(data)
        self.assertEqual(created["id"], data["id"])
        self.assertEqual(created["drafts"]["1"], "Draft")
        missing = {"id": "must-not-resurrect", "revision": 8, "turns": []}
        with self.assertRaises(RevisionConflict):
            self.store.save_conversation(missing)
    def test_explicit_delete_tombstone_and_restore(self):
        turn = self.save("Immutable original")
        data = self.store.get_conversation(self.conversation["id"])
        data["turns"], data["deleted_turn_ids"] = [], [turn["id"]]
        removed = self.store.save_conversation(data)
        self.assertFalse(removed["turns"])
        revisions = self.store.get_revisions(turn["id"])
        self.assertEqual(revisions[-1]["deleted"], 1)
        self.assertEqual(revisions[-1]["raw_source"], "Immutable original")
        restored_turn = dict(turn)
        restored_turn["revision"] = revisions[-1]["revision"]
        removed["turns"] = [restored_turn]
        restored = self.store.save_conversation(removed)
        self.assertEqual(restored["turns"][0]["raw_source"], "Immutable original")
        self.assertEqual(len(self.store.get_revisions(turn["id"])), 3)
    def test_multistore_concurrent_appends(self):
        second = Store(self.path)
        errors = []
        def save(store, index):
            try:
                store.save_turn(self.conversation["id"], "en", "fr", f"Thread {index}")
            except Exception as error:
                errors.append(error)
        threads = [threading.Thread(target=save, args=(self.store if i % 2 else second, i)) for i in range(12)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertFalse(errors)
        self.assertEqual(len(second.get_conversation(self.conversation["id"])["turns"]), 12)
    def test_omitted_turns_retained(self):
        self.save()
        data = self.store.get_conversation(self.conversation["id"])
        data["turns"] = []
        self.assertEqual(len(self.store.save_conversation(data)["turns"]), 1)
    def test_search_literals_and_translation(self):
        self.save("100% _ literal")
        self.assertEqual(len(self.store.list_conversations("100%")), 1)
        self.assertEqual(len(self.store.list_conversations("literal")), 1)
        self.assertEqual(self.store.list_conversations("absent"), [])
    def test_exports_current_full_text_formula_safe(self):
        source = " =HYPERLINK(\"bad\")\nFull text العربية"
        turn = self.save(source, warnings=[{"code": "numbers", "message": "Check numbers"}])
        text = self.store.export(self.conversation["id"], "txt")
        self.assertIn(source, text)
        self.assertIn("Check numbers", text)
        document = json.loads(self.store.export(self.conversation["id"], "json"))
        self.assertEqual(document["conversation"]["turns"][0]["raw_source"], source)
        rows = list(csv.reader(io.StringIO(self.store.export(self.conversation["id"], "csv"))))
        self.assertTrue(rows[1][4].startswith("'"))
        export = Path(self.temporary.name) / "out.csv"
        self.store.export(self.conversation["id"], "csv", export)
        self.assertTrue(export.read_bytes().startswith(b"\xef\xbb\xbf"))
        with self.assertRaises(StorageError):
            self.store.export(self.conversation["id"], "json", self.path)
    def test_backup_complete_and_no_sidecar(self):
        self.save("Backup 🙂")
        backup = Path(self.temporary.name) / "backup.sqlite3"
        self.store.backup(backup)
        restored = Store(backup)
        self.assertEqual(restored.get_conversation(self.conversation["id"])["turns"][0]["raw_source"], "Backup 🙂")
        self.assertEqual(restored.diagnostics()["integrity"], "ok")
        self.assertFalse(Path(str(self.path) + "-wal").exists())
        self.assertFalse(Path(str(self.path) + "-shm").exists())
    def test_deletion_cascades_and_not_found(self):
        turn = self.save()
        self.store.delete_conversation(self.conversation["id"])
        self.assertEqual(self.store.get_revisions(turn["id"]), [])
        with self.assertRaises(StorageError):
            self.store.get_conversation(self.conversation["id"])
    def test_concurrent_appends_no_overwrite(self):
        errors = []
        def save(index):
            try:
                self.save(f"Turn {index}")
            except Exception as error:
                errors.append(error)
        threads = [threading.Thread(target=save, args=(i,)) for i in range(15)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertFalse(errors)
        self.assertEqual(len(self.store.get_conversation(self.conversation["id"])["turns"]), 15)
    def test_corrupt_db_not_silently_replaced(self):
        bad = Path(self.temporary.name) / "corrupt.sqlite3"
        bad.write_bytes(b"original invalid database")
        with self.assertRaises(StorageError):
            Store(bad)
        self.assertEqual(bad.read_bytes(), b"original invalid database")

if __name__ == "__main__":
    unittest.main(verbosity=2)
