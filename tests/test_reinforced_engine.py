"""Observable final-output, privacy, cancellation and consultation boundaries."""
import threading
import time
import unittest
from unittest.mock import patch

import engine
from reinforced_engine import ReinforcedTranslator



class FakeIndex:
    text = 'Envoyez 12 GBP à wrong@example.org.'
    repair_text = 'Envoyez 12 GBP à help@example.org.'
    calls = []
    def __init__(self, **kwargs): pass
    def translate(self,*args,**kwargs):
        self.calls.append('translate')
        return {'text':self.text,'metadata':{},'cached':False}
    def repair(self,*args,**kwargs):
        self.calls.append('repair')
        return {'text':self.repair_text,'metadata':{}}


class ReinforcedIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.base=engine.Translator()
        self.layer=ReinforcedTranslator(self.base,index_factory=None)
    def fixture(self, outputs):
        def call(provider,text,source,target,deadline,stop,context,glossary,trace):
            engine._state(deadline,stop)
            value=outputs[provider]
            if isinstance(value,Exception): raise value
            trace.append({'provider':provider,'status':'complete'})
            return value,False
        return patch.object(self.base,'_translate_with',side_effect=call)
    def test_fact_repair_changes_main_and_keeps_original(self):
        with self.fixture({'google_web':'Envoyez 12 GBP à wrong@example.org.',
                           'bing_web':'Envoyez 12 GBP à help@example.org.'}):
            result=self.layer.translate('Send 12 GBP to help@example.org.','en','fr')
        self.assertEqual(result.provider,'bing_web')
        self.assertEqual(result.text,'Envoyez 12 GBP à help@example.org.')
        self.assertIn('wrong@example.org',result.review_text)
        self.assertTrue(any(t.get('changed') for t in result.trace))
    def test_agreement_or_fluency_does_not_license_semantic_rewrite(self):
        with self.fixture({'google_web':'Ne lui promettez pas cela.','bing_web':'Ne le lui promettez pas.'}):
            result=self.layer.translate('Do not promise him that.','en','fr')
        self.assertEqual(result.provider,'google_web')
        self.assertFalse(any(t.get('changed') for t in result.trace))
    def test_disabled_fallback_does_not_promote_failed_primary(self):
        self.base.allow_fallback=False
        with self.fixture({'google_web':engine.TranslationError('quota','Unavailable'), 'bing_web':'Bonjour'}):
            with self.assertRaises(engine.TranslationError): self.layer.translate('Hello','en','fr')
    def test_complete_primary_survives_failed_consultation(self):
        with self.fixture({'google_web':'Bonjour','bing_web':engine.TranslationError('timeout','Unavailable')}):
            result=self.layer.translate('Hello','en','fr')
        self.assertEqual(result.text,'Bonjour')
    def test_all_online_failures_are_reported(self):
        with self.fixture({'google_web':engine.TranslationError('quota','Unavailable'),
                           'bing_web':engine.TranslationError('service','Unavailable'),
                           'mymemory':engine.TranslationError('quota','Unavailable')}):
            with self.assertRaises(engine.TranslationError): self.layer.translate('Hello','en','fr')
    def test_production_model_repair_requires_improved_source_checks(self):
        self.layer.index=FakeIndex();FakeIndex.calls=[]
        with patch.object(FakeIndex,'text','Envoyez 15 GBP à wrong@example.org.'), self.fixture({
                           'google_web':'Envoyez 13 GBP à wrong@example.org.',
                           'bing_web':'Envoyez 14 GBP à other@example.org.'}):
            result=self.layer.translate('Send 12 GBP to help@example.org.','en','fr')
        self.assertEqual(result.provider,'index_web')
        self.assertIn('help@example.org',result.text)
        self.assertIn('repair',FakeIndex.calls)



    def test_measured_index_oromo_reverse_exclusion_prevents_http(self):
        self.layer.index=FakeIndex();FakeIndex.calls=[]
        with patch.object(self.base,'_translate_with') as network:
            with self.assertRaises(engine.TranslationError):
                self.layer.translate('Akkam','om','en',provider='index_web')
        network.assert_not_called();self.assertEqual(FakeIndex.calls,[])


    def test_cancel_wait_protocol_supports_transport_retries(self):
        from reinforced_engine import _Stop
        stop=_Stop(None,threading.Event())
        self.assertFalse(stop.wait(.001))
        stop.local.set();self.assertTrue(stop.wait(1))

    def test_invalid_deadline_does_not_start_network(self):
        for value in (True,0,-1,float('nan'),float('inf')):
            with self.subTest(value=value), self.assertRaises(engine.TranslationError):
                self.layer.translate('Hello','en','fr',deadline_seconds=value)

    def test_arabic_dual_does_not_block_voice_as_missing_two(self):
        from reinforced_engine import _warnings
        self.assertNotIn('numbers',[w.code for w in _warnings('Bring 2 copies.','أحضر نسختين.','en','ar')])

    def test_source_bound_signed_temperature_symbols_are_not_false_voice_blocks(self):
        from reinforced_engine import _warnings
        source='Keep it at minus 12 degrees Celsius, not plus 12.'
        good='Gardez-le à -12 °C, pas à +12 °C.'
        self.assertFalse({'numbers','units'} & {w.code for w in _warnings(source,good,'en','fr')})
        bad='Gardez-le à -12 °F, pas à +12 °F.'
        self.assertIn('units',{w.code for w in _warnings(source,bad,'en','fr')})

    def test_disabled_improvement_uses_only_base_contract(self):
        self.layer.index=FakeIndex();FakeIndex.calls=[]
        expected=engine.TranslationResult('Bonjour','google_web','en','fr',(),0)
        with patch.object(self.base,'translate',return_value=expected) as original:
            self.assertIs(self.layer.translate('Hello','en','fr',improve=False),expected)
        self.assertFalse(FakeIndex.calls)
        self.assertIsNone(original.call_args.kwargs['provider'])

    def test_user_glossary_primary_cannot_be_replaced_by_unconstrained_ai(self):
        self.base=engine.Translator([engine.ProviderConfig('deepl',key='fixture',glossary_id='fixture'),
            engine.ProviderConfig('google_web')],enabled_order=['deepl','google_web'])
        self.layer=ReinforcedTranslator(self.base,index_factory=FakeIndex)
        FakeIndex.calls=[]
        with self.fixture({'deepl':'Envoyez 12 GBP à wrong@example.org.',
                           'google_web':'Envoyez 12 GBP à help@example.org.'}):
            result=self.layer.translate('Send 12 GBP to help@example.org.','en','fr',provider='deepl')
        self.assertEqual(result.provider,'deepl')
        self.assertNotIn('repair',FakeIndex.calls)
        self.assertIn('review_conditions',[w.code for w in result.warnings])
    def test_cancelled_request_never_starts_any_engine(self):
        event=threading.Event();event.set()
        with patch.object(self.base,'_translate_with') as network:
            with self.assertRaises(engine.Cancelled): self.layer.translate('Hello','en','fr',cancel=event)
        network.assert_not_called()
    def test_late_cancel_discards_complete_candidates(self):
        event=threading.Event()
        def call(*args,**kwargs): event.set(); return 'Bonjour',False
        with patch.object(self.base,'_translate_with',side_effect=call):
            with self.assertRaises(engine.Cancelled): self.layer.translate('Hello','en','fr',cancel=event)
    def test_pair_preference_preserves_persian_bing(self):
        with self.fixture({'google_web':'سلام','bing_web':'درود'}):
            result=self.layer.translate('Hello','en','fa')
        self.assertEqual(result.provider,'bing_web')
    def test_parallel_consultation_is_bounded_and_policy_ordered(self):
        barrier=threading.Barrier(2)
        def call(provider,*args): barrier.wait(timeout=2); return ('Bonjour' if provider=='google_web' else 'Salut'),False
        with patch.object(self.base,'_translate_with',side_effect=call):
            result=self.layer.translate('Hello','en','fr')
        self.assertEqual(result.provider,'google_web')
    def test_same_language_preserves_exact_text_without_models(self):
        with patch.object(self.base,'_translate_with') as network:
            result=self.layer.translate('Exact\n text','fa','fa')
        self.assertEqual(result.text,'Exact\n text');network.assert_not_called()
