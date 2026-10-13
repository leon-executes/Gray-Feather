"""Upgrade compatibility and Index-outage behavior. Synthetic inputs only."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import engine
from app import Service
from settings import Settings, RETIRED_TRANSLATION_PROVIDERS
from reinforced_engine import ReinforcedTranslator
from tests.test_reinforced_engine import FakeIndex
from tests import test_reinforced_engine


class TranslationUpgradeTests(unittest.TestCase):
    def test_saved_offline_choice_migrates_without_resetting_preferences(self):
        for provider in RETIRED_TRANSLATION_PROVIDERS:
            with self.subTest(provider=provider), tempfile.TemporaryDirectory() as folder:
                path=Path(folder)/'settings.json'
                original=json.dumps({'version':1,'settings':{'provider':provider,
                    'theme':'light','source1':'fa','source2':'prs','voice_enabled':False,
                    'safe_speech':False,'text_size':16,'free_fallback':True}})
                path.write_text(original,encoding='utf-8')
                with patch.object(engine.HTTPTransport,'request_json') as network:
                    prefs=Settings(path)
                network.assert_not_called()
                self.assertEqual(path.read_text(encoding='utf-8'),original)
                value=prefs.get()
                self.assertEqual(value['provider'],'auto')
                self.assertEqual((value['theme'],value['source1'],value['source2'],value['text_size']),('light','fa','prs',16))
                self.assertFalse(value['voice_enabled']);self.assertFalse(value['safe_speech'])
                self.assertIn('online',prefs.notice)
                prefs.save({'theme':'dark'})
                self.assertEqual(Settings(path).get()['provider'],'auto')

    def test_retired_selections_rejected_without_http(self):
        with tempfile.TemporaryDirectory() as folder:
            service=Service(folder)
            for provider in RETIRED_TRANSLATION_PROVIDERS:
                with self.subTest(provider=provider), patch.object(engine.HTTPTransport,'request_json') as network:
                    with self.assertRaises(ValueError):service.save_settings({'provider':provider})
                    with self.assertRaises(engine.TranslationError):service.translate('Private draft','en','fr',provider=provider)
                    with self.assertRaises(engine.TranslationError):ReinforcedTranslator(service._make_translator()).translate('Private draft','en','fr',provider=provider)
                    with patch.object(service,'settings',return_value={**service.settings(),'provider':provider}):
                        with self.assertRaises(engine.TranslationError):service.translate_preview('Private draft','en','fr')
                    network.assert_not_called()
            service.shutdown()

    def test_opinions_exclude_retired_engines_and_keep_historical_provenance(self):
        with tempfile.TemporaryDirectory() as folder:
            service=Service(folder)
            options=service.available_opinion_providers('en','fr',('index_local',))
            self.assertFalse(RETIRED_TRANSLATION_PROVIDERS & {p['provider'] for p in options})
            self.assertFalse(next(p for p in options if p['provider']=='index_web')['independent'])
            options=service.available_opinion_providers('en','fr',('index_web','google_web'))
            self.assertNotIn('index_web',{p['provider'] for p in options})
            self.assertTrue(options)
            self.assertEqual(service.available_opinion_providers('fr','fr'),())
            service.shutdown()

    def test_settings_offer_online_index_only(self):
        from PySide6.QtWidgets import QApplication,QComboBox
        import ui
        app=QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as folder:
            pane=ui.SettingsPane(Settings(Path(folder)/'settings.json').get())
            values={combo.itemData(i) for combo in pane.findChildren(QComboBox) for i in range(combo.count())}
            self.assertIn('index_web',values)
            self.assertFalse(RETIRED_TRANSLATION_PROVIDERS & values)
            pane.close();pane.deleteLater();app.processEvents()


class IndexContingencyTests(unittest.TestCase):
    def setUp(self):
        self.base=engine.Translator()
        self.layer=ReinforcedTranslator(self.base,index_factory=FakeIndex)
    fixture=test_reinforced_engine.ReinforcedIntegrationTests.fixture

    def test_index_outages_keep_complete_candidate_and_skip_second_repair(self):
        for kind in ('timeout','quota','service','response','network'):
            with self.subTest(kind=kind), patch.object(self.layer.index,'translate',side_effect=engine.TranslationError(kind,'Unavailable')), patch.object(self.layer.index,'repair') as repair, self.fixture({'google_web':'Envoyez 13 GBP à wrong@example.org.','bing_web':'Envoyez 14 GBP à other@example.org.'}):
                result=self.layer.translate('Send 12 GBP to help@example.org.','en','fr')
            self.assertTrue(result.text);self.assertTrue(result.warnings)
            self.assertTrue(any(t.get('provider')=='index_web' and t.get('status')==kind for t in result.trace))
            repair.assert_not_called()

    def test_index_outage_preserves_deterministic_repair(self):
        with patch.object(self.layer.index,'translate',side_effect=engine.TranslationError('timeout','Unavailable')), self.fixture({'google_web':'Envoyez 12 GBP à wrong@example.org.','bing_web':'Envoyez 12 GBP à wrong@example.org.'}):
            result=self.layer.translate('Send 12 GBP to help@example.org.','en','fr')
        self.assertIn('help@example.org',result.text)
        self.assertIn('wrong@example.org',result.review_text)

    def test_selected_index_outage_falls_back_only_when_allowed(self):
        for allowed in (True,False):
            self.base.allow_fallback=allowed
            with self.subTest(allowed=allowed), patch.object(self.layer.index,'translate',side_effect=engine.TranslationError('timeout','Unavailable')), self.fixture({'google_web':'Bonjour','bing_web':'Bonjour'}):
                if allowed:
                    result=self.layer.translate('Hello','en','fr',provider='index_web')
                    self.assertEqual(result.text,'Bonjour');self.assertNotEqual(result.provider,'index_web')
                else:
                    with self.assertRaises(engine.TranslationError):self.layer.translate('Hello','en','fr',provider='index_web')

    def test_repair_outage_keeps_previous_complete_result(self):
        with patch.object(self.layer.index,'translate',return_value={'text':'Envoyez 15 GBP à wrong@example.org.','metadata':{}}), patch.object(self.layer.index,'repair',side_effect=engine.TranslationError('timeout','Unavailable')), self.fixture({'google_web':'Envoyez 13 GBP à wrong@example.org.','bing_web':'Envoyez 14 GBP à wrong@example.org.'}):
            result=self.layer.translate('Send 12 GBP to help@example.org.','en','fr')
        self.assertTrue(result.text)
        self.assertIn({'provider':'index_web','status':'repair_unavailable'},result.trace)

    def test_service_cooldown_preserves_cache_then_recovers(self):
        from index_engine import IndexTranslator
        from tests.test_index_engine import FakeTransport,response
        now=[100.0]
        transport=FakeTransport(lambda *args: response('Bonjour'))
        adapter=IndexTranslator(transport=transport)
        with patch('index_engine.time.monotonic',side_effect=lambda:now[0]):
            adapter.translate('Hello','en','fr')
            for kind in ('timeout','network','service','response'):
                transport.callback=lambda *args,k=kind: (_ for _ in ()).throw(engine.TranslationError(k,'Unavailable'))
                with self.assertRaises(engine.TranslationError):adapter.translate('Next '+kind,'en','fr')
                count=len(transport.calls)
                self.assertTrue(adapter.translate('Hello','en','fr')['cached'])
                with self.assertRaises(engine.TranslationError):adapter.translate('Other '+kind,'en','fr')
                self.assertEqual(len(transport.calls),count)
                now[0]+=31
                transport.callback=lambda *args:response('Recovered')
                self.assertEqual(adapter.translate('Recovered '+kind,'en','fr')['text'],'Recovered')
