"""Real native UI/ASR/translation/voice workflow; only capture receives fixture WAV."""
import hashlib
import io
import time
import wave
from pathlib import Path
from PySide6.QtCore import QTimer


def start(window, service, application, report):
    import speech
    from app import write_report, VERSION
    fixture = Path(__file__).resolve().parents[1] / 'resources' / 'test' / 'long-en-speech.wav'
    audio = fixture.read_bytes()
    with wave.open(io.BytesIO(audio), 'rb') as source:
        rate, channels, width = source.getframerate(), source.getnchannels(), source.getsampwidth()
        frames = source.readframes(source.getnframes())
    duration_ms = round(len(frames) * 1000 / (rate * channels * width))
    original_capture = speech.record_wav
    original_recognize, original_speak = service.recognize, service.speak
    state = {
        'version': VERSION, 'successful': False, 'phase': 'recording',
        'scope': 'Actual native Record/Stop buttons and real preview coordinator, bundled/local or configured live recognition, free preview/final translation and actual voice dispatch. A nonrepeating synthetic 23-second WAV replaces microphone capture only. This check does not claim to capture a physical microphone or certify semantic accuracy.',
        'fixture': fixture.name, 'fixture_sha256': hashlib.sha256(audio).hexdigest(),
        'audio_duration_ms': duration_ms, 'capture_preview_snapshots': [], 'recognized_previews': [],
        'requested_speech_provider': service.settings().get('speech_provider', 'auto'),
        'requested_voice_provider': service.settings().get('voice_provider', 'auto'),
        'voice_dispatches': 0,
    }
    began = time.monotonic()

    def snapshot(seconds):
        stream = io.BytesIO()
        with wave.open(stream, 'wb') as target:
            target.setnchannels(channels)
            target.setsampwidth(width)
            target.setframerate(rate)
            target.writeframes(frames[:int(rate * seconds) * channels * width])
        return stream.getvalue()

    def fixture_capture(stop, limit=50, preview_callback=None, preview_interval=3.0):
        capture_began = time.monotonic()
        for sequence, seconds in ((1, 8), (2, 16)):
            if stop.wait(max(0.0, 2.5 * sequence - (time.monotonic() - capture_began))):
                break
            if preview_callback:
                state['capture_preview_snapshots'].append({'sequence': sequence, 'audio_duration_ms': seconds * 1000})
                preview_callback(snapshot(seconds), {'sequence': sequence, 'duration_ms': seconds * 1000, 'complete': False})
        if not stop.wait(35):
            raise speech.SpeechError('UI Stop was not delivered to synthetic capture.')
        return audio, {'duration_ms': duration_ms, 'complete': True, 'limit_reached': False,
                       'preview_snapshots': len(state['capture_preview_snapshots'])}

    def observe_recognition(source_lang, cancel_event, preview_callback=None):
        callback = preview_callback
        if callback:
            def observe_preview(value):
                state['recognized_previews'].append({key: value.get(key) for key in ('text', 'provider', 'sequence', 'duration_ms', 'complete', 'provisional')})
                callback(value)
            preview_callback = observe_preview
        value = original_recognize(source_lang, cancel_event, preview_callback=preview_callback)
        state['actual_speech_provider'] = value.get('provider', '')
        state['recognition_trace'] = value.get('trace', [])
        state['recognized_text'] = value.get('text', '')
        return value

    def observe_speak(*args, **kwargs):
        state['voice_dispatches'] += 1
        state['voice_text'], state['voice_language'] = args[0], args[1]
        value = original_speak(*args, **kwargs)
        state['voice_result'] = value
        return value

    speech.record_wav = fixture_capture
    service.recognize, service.speak = observe_recognition, observe_speak
    timer = QTimer(window)
    timer.setInterval(100)

    def finish(error=None):
        timer.stop()
        speech.record_wav = original_capture
        service.recognize, service.speak = original_recognize, original_speak
        if error:
            state['error'] = str(error)
        state['elapsed_seconds'] = round(time.monotonic() - began, 3)
        state['screenshot'] = str(Path(report).with_suffix('.png'))
        window.grab().save(state['screenshot'])
        write_report(report, state)
        window.stop_everything()
        application.quit()

    def poll():
        try:
            elapsed = time.monotonic() - began
            if elapsed > 90:
                raise RuntimeError('Live UI workflow deadline expired: ' + state['phase'])
            panel = window.panels['1']
            if state['phase'] == 'recording':
                preview_ready = bool(panel.preview_active and panel.received.toPlainText().strip())
                second_preview = any(int(item.get('sequence') or 0) >= 2 for item in state['recognized_previews'])
                if preview_ready and second_preview and len(state['capture_preview_snapshots']) == 2:
                    if window.conversation['turns'] or any(window.conversation.get('drafts', {}).values()):
                        raise RuntimeError('Provisional words entered saved session content.')
                    if state['voice_dispatches']:
                        raise RuntimeError('A provisional translation triggered voice.')
                    state['provisional_words'] = panel.dictation_preview.toPlainText()
                    state['provisional_translation'] = panel.received.toPlainText()
                    state['provisional_not_saved_or_spoken'] = True
                    window.grab().save(str(Path(report).with_name(Path(report).stem + '-preview.png')))
                    state['phase'] = 'finalizing'
                    panel.record_button.click()
                elif elapsed > 32:
                    raise RuntimeError('Two cumulative recognition snapshots did not produce a live translation: ' + window.notice.text())
            elif state['phase'] == 'finalizing':
                if window.recording_token or window.translation_token or getattr(window, 'pending_final_translation', None):
                    return
                turns = window.conversation['turns']
                if len(turns) != 1 or turns[0].get('status') != 'complete':
                    raise RuntimeError('Stop did not create exactly one completed final turn: ' + window.notice.text())
                turn = turns[0]
                if not turn.get('translated_text'):
                    raise RuntimeError('Final output is missing.')
                if panel.source.toPlainText() != turn['raw_source'] or panel.received.toPlainText() != turn['translated_text']:
                    state.update(visible_source=panel.source.toPlainText(), stored_raw_source=turn['raw_source'],
                                 visible_translation=panel.received.toPlainText(), stored_translation=turn['translated_text'])
                    raise RuntimeError('Same-side source and translation differ from the final turn.')
                saved = service.load_conversation(window.conversation['id'])['turns']
                if len(saved) != 1 or saved[0]['raw_source'] != state['recognized_text'] or saved[0]['translated_text'] != turn['translated_text']:
                    raise RuntimeError('Final UI text and stored turn differ.')
                state.update(primary=turn['provider'], second_engine=turn['review_provider'], source_preserved=True,
                             translated_text=turn['translated_text'], second_opinion=turn.get('review_text', ''),
                             independent_review_available=bool(turn.get('review_text')), actual_warnings=turn.get('warnings', []),
                             backtranslation=turn.get('backtranslation', ''), checks=turn.get('checks', []),
                             exactly_one_saved_final_turn=True, same_side_source_and_translation=True, keys_required=False)
                state['phase'] = 'speaking'
            elif state['phase'] == 'speaking' and not window.voice_token:
                if state['voice_dispatches'] != 1 or not state.get('voice_result') or state['voice_result'].get('complete') is not True:
                    raise RuntimeError('Final automatic voice did not finish once: ' + window.notice.text())
                state.update(successful=True, phase='complete', record_enabled=panel.record_button.isEnabled())
                finish()
        except Exception as error:
            finish(error)

    window.new_conversation()
    window.panels['1'].set_code('en')
    window.panels['2'].set_code('fr')
    settings = service.settings()
    settings.update(voice_enabled=True, auto_speak=True)
    window._save_settings(settings)
    if not window.panels['1'].record_button.isEnabled():
        finish('No-key Record Speech button is disabled.')
        return
    window.panels['1'].record_button.click()
    timer.timeout.connect(poll)
    timer.start()
