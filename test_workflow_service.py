"""Exports and revised facade contracts; synthetic words, no live services."""
import copy
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET
import zipfile

from app import Service
from docx_export import export_docx
from engine import TranslationResult
import settings

def conversation():
    return {'id':'docx-fixture','title':'Synthetic session <&>', 'source1':'en','source2':'ar', 'drafts':{'1':'','2':''}, 'turns':[
      {'id':'turn-1','speaker':'1','seq':1,'source_lang':'en','target_lang':'ar','raw_source':'Do not pay £50.\nBring 2 copies.\tGF-4821',
       'reviewed_source':'Do not pay £50.\nBring 2 signed copies.\tGF-4821','translated_text':'لا تدفع £50.\nأحضر نسختين.',
       'provider':'google_web','status':'complete','warnings':[{'message':'Review negation'}],
       'review_text':'لا تدفع £50. أحضر نسختين.','review_provider':'bing_web',
       'opinions':[{'text':'نسختان للمراجعة','provider':'mymemory'}], 'backtranslation':'Do not pay £50. Bring two copies.'}]}

class DocxExportTests(unittest.TestCase):
    def test_word_package_preserves_complete_fields_and_rtl(self):
        original=conversation();before=copy.deepcopy(original)
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'Conversation café العربية.docx'
            export_docx(original,output)
            with zipfile.ZipFile(output) as package:
                self.assertIsNone(package.testzip())
                for item in package.namelist(): ET.fromstring(package.read(item))
                tree=ET.fromstring(package.read('word/document.xml'))
                ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
                text='\n'.join(t.text or '' for t in tree.findall('.//w:t',ns))
                for expected in ('£50','Bring 2 copies.','GF-4821','Bring 2 signed copies.','لا تدفع £50.','نسختان للمراجعة','Opinion 3','Advisory back translation','Review negation'):
                    self.assertIn(expected,text)
                self.assertTrue(tree.findall('.//w:bidi',ns))
                self.assertTrue(tree.findall('.//w:tab',ns))
                self.assertTrue(tree.findall('.//w:br',ns))
            self.assertEqual(original,before)

    def test_failed_atomic_replacement_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'keep.docx';output.write_bytes(b'prior valid export')
            with patch('docx_export.os.replace',side_effect=PermissionError('Locked file')),self.assertRaises(PermissionError):
                export_docx(conversation(),output)
            self.assertEqual(output.read_bytes(),b'prior valid export')
            self.assertEqual([p.name for p in Path(folder).iterdir()],['keep.docx'])

    def test_unsupported_control_is_visible_not_silently_deleted(self):
        data=conversation();data['turns'][0]['raw_source']='Keep\x0bthis'
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'escaped.docx';export_docx(data,output)
            with zipfile.ZipFile(output) as package:
                xml=package.read('word/document.xml').decode('utf-8')
            self.assertIn('Keep\\u000bthis',xml)
            ET.fromstring(xml)
        self.assertEqual(data['turns'][0]['raw_source'],'Keep\x0bthis')

    def test_unknown_language_preserves_existing_output(self):
        data=conversation();data['turns'][0]['target_lang']='invented'
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'keep.docx';output.write_bytes(b'prior')
            with self.assertRaisesRegex(ValueError,'unknown language'): export_docx(data,output)
            self.assertEqual(output.read_bytes(),b'prior')

    def test_service_docx_export_uses_visible_snapshot_and_protects_history(self):
        with tempfile.TemporaryDirectory() as folder:
            service=Service(folder);saved=service.save_conversation(conversation())
            visible=copy.deepcopy(saved);visible['turns'][0]['translated_text']='Visible complete snapshot'
            output=Path(folder)/'visible.docx';service.export_conversation(visible,output,'docx')
            with zipfile.ZipFile(output) as package: self.assertIn(b'Visible complete snapshot',package.read('word/document.xml'))
            self.assertNotEqual(service.load_conversation(saved['id'])['turns'][0]['translated_text'],'Visible complete snapshot')
            with self.assertRaises(ValueError): service.export_conversation(visible,Path(folder)/'conversations.sqlite3','docx')
            service.shutdown()

class WorkflowServiceTests(unittest.TestCase):
    def test_preview_has_no_opinions_reverse_output_or_history_write(self):
        with tempfile.TemporaryDirectory() as folder:
            service=Service(folder)
            value=TranslationResult('Bonjour','google_web','en','fr',(),1)
            with patch('engine.Translator.translate',return_value=value) as translate:
                result=service.translate_preview('Hello','en','fr',threading.Event())
            self.assertTrue(result['provisional']);self.assertFalse(result['complete'])
            self.assertFalse(translate.call_args.kwargs['independent_review'])
            self.assertFalse(translate.call_args.kwargs['backtranslate'])
            self.assertEqual(translate.call_args.kwargs['deadline_seconds'],6)
            self.assertEqual(service.list_conversations(),[])
            service.shutdown()

    def test_reset_preserves_optional_credentials_context_and_history(self):
        with tempfile.TemporaryDirectory() as folder:
            service=Service(folder);service.save_conversation(conversation())
            service.save_settings({'theme':'light','text_size':19,'context':'Approved terminology','voice_enabled':False})
            result=service.reset_settings()
            self.assertEqual((result['theme'],result['text_size']),('dark',12))
            self.assertTrue(result['voice_enabled']);self.assertTrue(result['auto_speak'])
            self.assertEqual(result['context'],'Approved terminology')
            self.assertEqual(len(service.list_conversations()),1)
            service.shutdown()

    def test_visual_changes_preserve_translation_session(self):
        with tempfile.TemporaryDirectory() as folder:
            service=Service(folder);translator=service._make_translator()
            service.save_settings({'text_size':12,'theme':'light','voice_enabled':False})
            self.assertIs(service._make_translator(),translator)
            service.save_settings({'provider':'bing_web'})
            self.assertIsNot(service._make_translator(),translator)
            service.shutdown()

    def test_voice_choices_and_toggle_are_validated_and_persisted(self):
        with tempfile.TemporaryDirectory() as folder:
            prefs=settings.Settings(Path(folder)/'settings.json')
            self.assertEqual(prefs.get()['text_size'],12)
            self.assertTrue(prefs.get()['voice_enabled'])
            for provider in ('auto','edge_free','google_web','windows','azure'):
                prefs.save({'voice_provider':provider,'voice_enabled':False})
                reopened=settings.Settings(prefs.path).get()
                self.assertEqual(reopened['voice_provider'],provider)
                self.assertFalse(reopened['voice_enabled']);self.assertFalse(reopened['auto_speak'])
            with self.assertRaises(ValueError): prefs.save({'voice_provider':'invented'})

    def test_legacy_settings_do_not_diverge_from_visible_voice_control(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'settings.json'
            settings.atomic_json(path, {'version':1,'settings':{'auto_speak':False},'credentials':''})
            current=settings.Settings(path).get()
            self.assertEqual(current['auto_speak'],current['voice_enabled'])

    def test_voice_facade_uses_one_policy_for_every_language_and_selection(self):
        with tempfile.TemporaryDirectory() as folder:
            service=Service(folder);stop=threading.Event()
            for provider,language,locale in (('auto','en','en-US'),('windows','fr','fr-FR'),('auto','om','om-ET'),('azure','fa','fa-IR')):
                service.save_settings({'voice_provider':provider})
                with patch('speech.speak_free',return_value={'complete':True}) as speak:
                    service.speak('Synthetic words',language,stop)
                self.assertEqual(speak.call_args.args[1],locale)
                self.assertEqual(speak.call_args.args[2]['voice_provider'],provider)
                self.assertIs(speak.call_args.args[2]['_voice_session'],service._voice_session)
                self.assertIs(speak.call_args.args[3],stop)
            service.shutdown()

if __name__=='__main__': unittest.main()
