"""Native recording, free speech routes and bundled offline dictation fallback."""
from __future__ import annotations
import base64
import array
import asyncio
import contextlib
from collections import OrderedDict
import ctypes
from ctypes import wintypes
import io
import hashlib
import json
import locale
import os
import queue
import re
from pathlib import Path
import threading
import subprocess
import sys
import time
import tempfile
import uuid
import urllib.error
import urllib.parse
import urllib.request
import wave
import winsound
from xml.sax.saxutils import escape

class SpeechError(Exception):
    pass

class _TransientVoiceError(SpeechError):
    """A missing Edge worker result, eligible for one whole-passage retry."""
    pass

# Conservative exact-locale registry for this short-audio API; separate from text/TTS.
# Azure's registry uses bn-IN and ur-IN, not the project's bn-BD/ur-PK defaults.
AZURE_STT_LOCALES = frozenset(('en-US', 'ar-SA', 'fr-FR', 'tr-TR', 'fa-IR', 'ps-AF',
    'hi-IN', 'pa-IN', 'am-ET', 'so-SO', 'sw-KE', 'es-ES', 'de-DE', 'it-IT', 'pt-PT',
    'ru-RU', 'zh-CN', 'ja-JP', 'ko-KR', 'nl-NL', 'pl-PL', 'ro-RO', 'uk-UA', 'el-GR',
    'he-IL', 'id-ID'))
GOOGLE_STT_LOCALES = frozenset(('en-US', 'ar-SA', 'fr-FR', 'tr-TR', 'fa-IR', 'ur-PK',
    'hi-IN', 'bn-BD', 'pa-IN', 'sw-KE', 'es-ES', 'de-DE', 'it-IT', 'pt-PT', 'ru-RU',
    'zh-CN', 'ja-JP', 'ko-KR', 'nl-NL', 'pl-PL', 'ro-RO', 'uk-UA', 'el-GR', 'he-IL', 'id-ID'))

OFFLINE_MODEL = 'ggml-small-q5_1.bin'
OFFLINE_MODEL_LABEL = 'Whisper small-q5_1 multilingual model'
# Persian was technically supported by Whisper but failed the local quality
# fixtures. Keep its verified online route; do not silently use a poor fallback.
WHISPER_LOCALES = {code: code.split('-')[0] for code in (
    'en-US', 'ar-SA', 'fr-FR', 'tr-TR', 'ps-AF', 'ur-PK', 'hi-IN',
    'bn-BD', 'pa-IN', 'sd-PK', 'am-ET', 'so-SO', 'sw-KE', 'es-ES', 'de-DE',
    'it-IT', 'pt-PT', 'ru-RU', 'zh-CN', 'ja-JP', 'ko-KR', 'nl-NL', 'pl-PL',
    'ro-RO', 'uk-UA', 'el-GR', 'he-IL', 'id-ID')}
OMNILINGUAL_LOCALES = frozenset(('om-ET','ckb-IQ'))

def recognition_supported(lang, provider):
    return lang in (AZURE_STT_LOCALES if provider == 'azure' else GOOGLE_STT_LOCALES if provider in ('google', 'google_web') else WHISPER_LOCALES if provider == 'offline' else OMNILINGUAL_LOCALES if provider=='omnilingual' else (GOOGLE_STT_LOCALES | WHISPER_LOCALES.keys() | OMNILINGUAL_LOCALES) if provider in ('auto', 'free') else ())

def omnilingual_available(config=None, lang=None):
    import offline_omni
    return offline_omni.available(lang,config)

def recognize_omnilingual(audio,lang,config=None,cancel=None):
    import offline_omni
    try: return offline_omni.recognize(audio,lang,config,cancel)['text']
    except offline_omni.OmniError as error: raise SpeechError(str(error)) from error

class WaveFormat(ctypes.Structure):
    _pack_ = 1
    _fields_ = [('tag', wintypes.WORD), ('channels', wintypes.WORD),
                ('rate', wintypes.DWORD), ('bytes_per_second', wintypes.DWORD),
                ('block_align', wintypes.WORD), ('bits', wintypes.WORD), ('extra', wintypes.WORD)]

class WaveHeader(ctypes.Structure):
    _fields_ = [('data', ctypes.c_void_p), ('length', wintypes.DWORD),
                ('recorded', wintypes.DWORD), ('user', ctypes.c_size_t),
                ('flags', wintypes.DWORD), ('loops', wintypes.DWORD),
                ('next', ctypes.c_void_p), ('reserved', ctypes.c_size_t)]

def _wav_from_pcm(pcm):
    output = io.BytesIO()
    with wave.open(output, 'wb') as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000)
        wav.writeframes(pcm)
    return output.getvalue()


def record_wav(stop: threading.Event, limit: float = 50.0, preview_callback=None, preview_interval=3.0):
    """Capture 16 kHz PCM, returning all completed buffers including final partial audio."""
    if os.name != 'nt':
        raise SpeechError('Microphone recording requires Windows.')
    if not 0 < limit <= 50:
        raise SpeechError('Recording limit must be between 0 and 50 seconds.')
    if preview_callback is not None and not callable(preview_callback):
        raise SpeechError('Recording preview needs a callable receiver.')
    if isinstance(preview_interval, bool) or not isinstance(preview_interval, (int, float)) or not 2.5 <= preview_interval <= 10:
        raise SpeechError('Recording preview cadence must be between 2.5 and 10 seconds.')
    dll = ctypes.WinDLL('winmm')
    dll.waveInOpen.argtypes = [ctypes.POINTER(ctypes.c_void_p), wintypes.UINT, ctypes.POINTER(WaveFormat), ctypes.c_size_t, ctypes.c_size_t, wintypes.DWORD]
    for name in ('waveInPrepareHeader', 'waveInUnprepareHeader', 'waveInAddBuffer'):
        getattr(dll, name).argtypes = [ctypes.c_void_p, ctypes.POINTER(WaveHeader), wintypes.UINT]
    for name in ('waveInStart', 'waveInStop', 'waveInReset', 'waveInClose'):
        getattr(dll, name).argtypes = [ctypes.c_void_p]
    handle = ctypes.c_void_p()
    fmt = WaveFormat(1, 1, 16000, 32000, 2, 16, 0)
    status = dll.waveInOpen(ctypes.byref(handle), 0xFFFFFFFF, ctypes.byref(fmt), 0, 0, 0)
    if status:
        raise SpeechError('The microphone could not open. Check Windows microphone permission and the default input device.')
    headers, buffers, pending = [], [], []
    blocks = []
    start = time.monotonic()
    capped = False
    next_preview, preview_sequence = start + preview_interval, 0
    preview_error = None
    try:
        for _ in range(4):
            buffer = ctypes.create_string_buffer(6400)
            header = WaveHeader(ctypes.cast(buffer, ctypes.c_void_p), len(buffer), 0, 0, 0, 0, None, 0)
            if dll.waveInPrepareHeader(handle, ctypes.byref(header), ctypes.sizeof(header)):
                raise SpeechError('The microphone buffer could not be prepared.')
            headers.append(header)
            buffers.append(buffer)
            if dll.waveInAddBuffer(handle, ctypes.byref(header), ctypes.sizeof(header)):
                raise SpeechError('The microphone buffer could not start.')
            pending.append(len(headers) - 1)
        if dll.waveInStart(handle):
            raise SpeechError('The microphone could not start.')
        while not stop.is_set():
            if time.monotonic() - start >= limit:
                capped = True
                break
            while pending and headers[pending[0]].flags & 1:
                index = pending.pop(0)
                header, buffer = headers[index], buffers[index]
                blocks.append(buffer.raw[:header.recorded])
                header.recorded = 0
                if dll.waveInAddBuffer(handle, ctypes.byref(header), ctypes.sizeof(header)):
                    raise SpeechError('The microphone disconnected during capture.')
                pending.append(index)
            now = time.monotonic()
            if preview_callback and now >= next_preview and not stop.is_set():
                next_preview = now + preview_interval
                # Only copied completed buffers are read. The queued WinMM
                # buffers may still be written by the microphone driver.
                snapshot = b''.join(blocks)[:min(800000, int(limit * 16000)) * 2]
                if len(snapshot) >= 32000:
                    preview_sequence += 1
                    try:
                        preview_callback(_wav_from_pcm(snapshot), {'sequence': preview_sequence,
                            'duration_ms': round(len(snapshot) / 32), 'provisional': True, 'complete': False})
                    except Exception as error:
                        # A preview receiver never discards the complete turn.
                        preview_error = type(error).__name__
            stop.wait(0.015)
        if dll.waveInStop(handle) or dll.waveInReset(handle):
            raise SpeechError('The microphone could not finish cleanly. Retry or type the turn.')
        # Reset returns queued buffers in their capture order. Previously consumed buffers were requeued.
        for index in pending:
            header, buffer = headers[index], buffers[index]
            if header.recorded:
                blocks.append(buffer.raw[:header.recorded])
        raw = b''.join(blocks)
        # A delayed poll/reset can include samples past the wall-clock limit.
        # Bound the final partial capture by frames and expose the reached limit.
        maximum_bytes = min(800000, int(limit * 16000)) * 2
        if len(raw) > maximum_bytes:
            raw = raw[:maximum_bytes]
            capped = True
        if len(raw) < 3200:
            raise SpeechError('The recording was too short. Hold Record for a moment, then press Stop.')
        return _wav_from_pcm(raw), {'duration_ms': round(len(raw) / 32), 'complete': not capped,
                                   'limit_reached': capped, 'preview_snapshots': preview_sequence,
                                   'preview_capture_error': preview_error}
    finally:
        dll.waveInReset(handle)
        for header in headers:
            dll.waveInUnprepareHeader(handle, ctypes.byref(header), ctypes.sizeof(header))
        dll.waveInClose(handle)


class _CombinedCancel:
    def __init__(self, *events): self.events = tuple(event for event in events if event is not None)
    def is_set(self): return any(event.is_set() for event in self.events)
    def wait(self, timeout=None):
        end = None if timeout is None else time.monotonic() + max(0, timeout)
        while not self.is_set():
            remaining = .025 if end is None else min(.025, end - time.monotonic())
            if remaining <= 0: return self.is_set()
            if self.events: self.events[0].wait(remaining)
            else: time.sleep(remaining)
        return True


class PreviewRecognizer:
    """One ASR job and one replaceable pending snapshot; capture never waits."""
    def __init__(self, stop, lang, config, callback):
        self.cancel = threading.Event()
        self.stop = _CombinedCancel(self.cancel, stop, getattr(stop, 'abort_event', None))
        self.lang, self.config, self.callback = lang, {**config, '_preview': True}, callback
        self.condition = threading.Condition()
        self.pending = None
        self.last_text = None
        self.submitted = self.completed = self.attempted = 0
        self.last_error = None
        self.thread = threading.Thread(target=self._run, name='speech-preview', daemon=True)
        self.thread.start()

    def submit(self, audio, metadata):
        with self.condition:
            if self.stop.is_set(): return
            self.submitted += 1
            self.pending = (bytes(audio), dict(metadata))
            self.condition.notify()

    def close(self):
        self.cancel.set()
        with self.condition:
            self.pending = None
            self.condition.notify_all()

    def _run(self):
        while not self.stop.is_set():
            with self.condition:
                while self.pending is None and not self.stop.is_set(): self.condition.wait(.1)
                if self.stop.is_set(): return
                audio, metadata = self.pending
                self.pending = None
            self.attempted += 1
            try:
                value = recognize_with_fallback(audio, self.lang, self.config, self.stop)
                normalized = ' '.join(value['text'].split()).casefold()
                if self.stop.is_set() or normalized == self.last_text: continue
                self.last_text = normalized
                self.completed += 1
                self.callback({**value, **metadata, 'provisional': True, 'complete': False})
            except Exception as error:
                if not self.stop.is_set(): self.last_error = str(error)


def record_with_previews(stop, lang, config, preview_callback=None, limit=50.0):
    if preview_callback is None:
        return record_wav(stop, limit)
    if not callable(preview_callback):
        raise SpeechError('Recording preview needs a callable receiver.')
    preview = PreviewRecognizer(stop, lang, dict(config or {}), preview_callback)
    try:
        audio, metadata = record_wav(stop, limit, preview.submit)
    finally:
        # Do not join: Stop must go straight to full-audio final recognition.
        preview.close()
    return audio, {**metadata, 'preview_attempted': preview.attempted,
                   'preview_completed': preview.completed, 'preview_error': preview.last_error}

_REQUEST_SLOTS = threading.BoundedSemaphore(2)

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, 'Redirect refused', headers, fp)

def request(url, data, headers, cancel=None, timeout=20, maximum=16 * 1024 * 1024, method='POST'):
    if cancel and cancel.is_set():
        raise SpeechError('Speech cancelled.')
    if not _REQUEST_SLOTS.acquire(blocking=False):
        raise SpeechError('Speech service is busy. Wait for the previous request to finish.')
    result = queue.Queue(maxsize=1)
    def run():
        try:
            req = urllib.request.Request(url, data, headers, method=method)
            with urllib.request.build_opener(NoRedirect()).open(req, timeout=timeout) as response:
                body = response.read(maximum + 1)
                if len(body) > maximum:
                    raise SpeechError('Speech service returned an oversized response.')
                result.put((True, body))
        except urllib.error.HTTPError as error:
            result.put((False, SpeechError({401: 'Speech credentials were rejected.', 403: 'Speech access is unavailable for this resource.', 429: 'Speech service quota was reached.'}.get(error.code, f'Speech service returned HTTP {error.code}.'))))
        except Exception:
            result.put((False, SpeechError('Speech service could not be reached. Check connection and resource settings.')))
        finally:
            _REQUEST_SLOTS.release()
    threading.Thread(target=run, name='speech-http', daemon=True).start()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if cancel and cancel.is_set():
            raise SpeechError('Speech cancelled.')
        try:
            ok, value = result.get(timeout=0.05)
            if ok:
                return value
            raise value
        except queue.Empty:
            pass
    raise SpeechError('Speech service timed out. Your transcript is unchanged.')

def recognize_wav(audio, lang, config, cancel=None):
    config = dict(config or {})
    provider = config.get('speech_provider', 'auto')
    if provider in ('auto', 'free'):
        return recognize_with_fallback(audio, lang, config, cancel)['text']
    _speech_pcm(audio)
    if provider == 'offline':
        return recognize_offline(audio, lang, config, cancel)
    if provider == 'omnilingual':
        return recognize_omnilingual(audio, lang, config, cancel)
    if config.get('_preview') and provider in ('google_web', 'azure', 'google'):
        return _speech_cloud_worker('recognize', audio, lang, config, cancel, timeout=10)['text']
    if provider == 'google_web':
        return recognize_google_web(audio, lang, cancel)
    key = str(config.get('speech_key', '')).strip()
    if not key:
        raise SpeechError('Add a speech service key in Settings to use the microphone.')
    provider = config.get('speech_provider', 'azure')
    if not recognition_supported(lang, provider):
        raise SpeechError('This exact language locale is not configured for the selected speech provider. Type the turn instead.')
    if provider == 'azure':
        region = str(config.get('speech_region', '')).strip()
        if not region or not all(c.isalnum() or c == '-' for c in region):
            raise SpeechError('Enter your Azure Speech region in Settings.')
        url = f'https://{region}.stt.speech.microsoft.com/speech/recognition/conversation/cognitiveservices/v1?' + urllib.parse.urlencode({'language': lang, 'format': 'detailed', 'profanity': 'raw'})
        body = json.loads(request(url, audio, {'Ocp-Apim-Subscription-Key': key, 'Content-Type': 'audio/wav; codecs=audio/pcm; samplerate=16000', 'Accept': 'application/json'}, cancel))
        if body.get('RecognitionStatus') != 'Success':
            raise SpeechError('No clear speech was recognized. Try again or type the turn.')
        best = (body.get('NBest') or [{}])[0]
        text = best.get('Display') or body.get('DisplayText')
    elif provider == 'google':
        service_locale = {'pa-IN': 'pa-Guru-IN', 'zh-CN': 'cmn-Hans-CN'}.get(lang, lang)
        body = json.loads(request('https://speech.googleapis.com/v1/speech:recognize', json.dumps({'config': {'encoding': 'LINEAR16', 'sampleRateHertz': 16000, 'languageCode': service_locale, 'enableAutomaticPunctuation': True, 'profanityFilter': False}, 'audio': {'content': base64.b64encode(audio).decode('ascii')}}).encode('utf-8'), {'Content-Type': 'application/json', 'X-Goog-Api-Key': key}, cancel))
        text = ' '.join((r.get('alternatives') or [{}])[0].get('transcript', '') for r in body.get('results', []))
    else:
        raise SpeechError('Select a supported speech provider in Settings.')
    if not isinstance(text, str) or not text.strip():
        raise SpeechError('No clear speech was recognized. Try again or type the turn.')
    return text.strip()


def _pcm16(audio):
    try:
        with wave.open(io.BytesIO(audio), 'rb') as wav:
            if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getcomptype()) != (1, 2, 16000, 'NONE'):
                raise SpeechError('Dictation needs 16 kHz mono 16-bit PCM audio.')
            if not 0 < wav.getnframes() <= 800000:
                raise SpeechError('Dictation needs a nonempty recording of at most 50 seconds.')
            raw = wav.readframes(wav.getnframes())
            if len(raw) != wav.getnframes() * 2:
                raise SpeechError('The recording is incomplete. Retry the turn.')
            return raw
    except (wave.Error, EOFError) as error:
        raise SpeechError('The recording is not valid PCM audio.') from error


def _speech_pcm(audio):
    """Reject silence and pure DC without boosting or discarding quiet speech."""
    pcm = _pcm16(audio)
    samples = array.array('h', pcm)
    if sys.byteorder != 'little':
        samples.byteswap()
    if min(samples) == max(samples):
        raise SpeechError('The recording contains no changing audio signal. Check the microphone and speak, or type the turn.')
    return pcm


def _crc_table(polynomial, bits):
    rows = []
    mask = (1 << bits) - 1
    for value in range(256):
        value <<= bits - 8
        for _ in range(8):
            value = ((value << 1) ^ polynomial if value & (1 << (bits - 1)) else value << 1) & mask
        rows.append(value)
    return rows

_CRC8 = _crc_table(0x07, 8)
_CRC16 = _crc_table(0x8005, 16)

def pcm16_to_flac(audio):
    """Lossless uncompressed FLAC frames; no external codec installation or DLL.

    Implements STREAMINFO + fixed-block mono verbatim subframes. Audio is bounded
    to the native recorder's format and limit. CRCs and STREAMINFO MD5 protect it.
    """
    raw = _pcm16(audio)
    count = len(raw) // 2
    stream = b'\x10\x00\x10\x00' + b'\x00' * 6
    stream += ((16000 << 44) | (15 << 36) | count).to_bytes(8, 'big') + hashlib.md5(raw).digest()
    output = bytearray(b'fLaC\x80\x00\x00\x22' + stream)
    for frame_number, offset in enumerate(range(0, count, 4096)):
        block = raw[offset * 2:min(count, offset + 4096) * 2]
        header = bytearray(b'\xff\xf8\x70\x08' + chr(frame_number).encode('utf-8') + (len(block) // 2 - 1).to_bytes(2, 'big'))
        crc = 0
        for value in header:
            crc = _CRC8[crc ^ value]
        header.append(crc)
        samples = array.array('h', block)
        if sys.byteorder == 'little':
            samples.byteswap()
        frame = header + b'\x02' + samples.tobytes()
        crc = 0
        for value in frame:
            crc = ((crc << 8) ^ _CRC16[((crc >> 8) ^ value) & 255]) & 65535
        output.extend(frame + crc.to_bytes(2, 'big'))
    return bytes(output)


def recognize_google_web(audio, lang, cancel=None):
    if lang not in GOOGLE_STT_LOCALES:
        raise SpeechError('The free online dictation route does not support this exact locale. Use supported offline dictation or type the turn.')
    if cancel and cancel.is_set():
        raise SpeechError('Speech cancelled.')
    _speech_pcm(audio)
    # Public personal/testing client key distributed by SpeechRecognition, not a
    # paid user credential. This legacy route is revocable; offline is independent.
    client_key = 'AIzaSyBOti4mM-6x9WDnZIjIeyEU21OpBXqWBgw'
    url = 'https://www.google.com/speech-api/v2/recognize?' + urllib.parse.urlencode({'client': 'chromium', 'lang': lang, 'key': client_key, 'pFilter': 0})
    raw = request(url, pcm16_to_flac(audio), {'Content-Type': 'audio/x-flac; rate=16000', 'User-Agent': 'Mozilla/5.0'}, cancel, timeout=12, maximum=1024 * 1024)
    try:
        parts = []
        for line in raw.decode('utf-8').splitlines():
            if not line.strip():
                continue
            for result in json.loads(line).get('result', []):
                final = result.get('final')
                if type(final) is not bool:
                    raise ValueError('Missing or invalid final status')
                if not final:
                    continue
                candidates = result.get('alternative', [])
                if candidates and isinstance(candidates[0].get('transcript'), str):
                    parts.append(candidates[0]['transcript'].strip())
        text = ' '.join(parts).strip()
    except (UnicodeError, ValueError, TypeError, AttributeError) as error:
        raise SpeechError('Free online dictation returned an invalid response. Retry or choose offline.') from error
    if not text:
        raise SpeechError('No clear speech was recognized online. Retry or choose offline dictation.')
    if cancel and cancel.is_set():
        raise SpeechError('Speech cancelled.')
    return text


def offline_resources(config=None):
    return Path((config or {}).get('_speech_resources') or Path(__file__).resolve().parent / 'resources' / 'speech')


def offline_available(config=None, lang=None):
    if lang is not None and lang not in WHISPER_LOCALES:
        return False
    folder = offline_resources(config)
    return (folder / 'whisper-cli.exe').is_file() and (folder / OFFLINE_MODEL).is_file()


def offline_timeout(recording_seconds):
    """Bound a slow native child with loading headroom and a duration budget."""
    if isinstance(recording_seconds, bool) or not isinstance(recording_seconds, (int, float)) or not 0 < recording_seconds <= 50:
        raise SpeechError('Offline dictation needs a recording of at most 50 seconds.')
    return min(90.0, max(20.0, 10.0 + 1.5 * recording_seconds))


def recognize_offline(audio, lang, config=None, cancel=None):
    if lang == 'fa-IR':
        raise SpeechError('Offline Persian dictation was sidelined after quality checks. Use free online dictation or type the turn.')
    if lang not in WHISPER_LOCALES:
        raise SpeechError('The bundled offline model does not support this exact language. No other language was substituted.')
    pcm = _speech_pcm(audio)
    if cancel and cancel.is_set():
        raise SpeechError('Speech cancelled.')
    folder = offline_resources(config)
    if not offline_available(config):
        raise SpeechError('The bundled offline speech files are missing. Restore the complete portable app folder.')
    directory = Path((config or {}).get('_audio_dir') or tempfile.gettempdir())
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='dictation-', dir=directory) as scratch:
        wav = Path(scratch) / 'input.wav'
        output = Path(scratch) / 'transcript.txt'
        wav.write_bytes(audio)
        # The native narrow argv entry point may misread Unicode paths. The
        # model name is ASCII relative to a CreateProcessW cwd. Python opens
        # audio/transcript files with Unicode-safe APIs and passes their handles.
        # Dummy ASCII output-file keeps the segment callback active for stdin;
        # no output-format flag is set, so the CLI creates no resource files.
        args = [str(folder / 'whisper-cli.exe'), '--model', OFFLINE_MODEL, '--file', '-', '--language', WHISPER_LOCALES[lang], '--no-gpu', '--threads', str(min(2 if (config or {}).get('_preview') else 4, os.cpu_count() or 2)), '--no-prints', '--no-timestamps', '--output-file', 'transcript']
        with wav.open('rb') as input_file, output.open('wb') as output_file:
            try:
                process = subprocess.Popen(args, stdin=input_file, stdout=output_file, stderr=subprocess.DEVNULL, cwd=folder, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            except OSError as error:
                raise SpeechError('The bundled offline recognizer could not start. Restore the complete portable app folder or use free online dictation.') from error
            deadline = time.monotonic() + offline_timeout(len(pcm) / 32000)
            try:
                while process.poll() is None:
                    if cancel and cancel.wait(.05):
                        raise SpeechError('Speech cancelled.')
                    if not cancel:
                        time.sleep(.05)
                    if output.stat().st_size > 1024 * 1024:
                        raise SpeechError('Offline dictation returned an oversized transcript.')
                    if time.monotonic() > deadline:
                        raise SpeechError('Offline dictation exceeded its time limit. Try a shorter turn.')
                if process.returncode:
                    raise SpeechError('The bundled offline recognizer could not process this recording.')
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=5)
        try:
            if output.stat().st_size > 1024 * 1024:
                raise SpeechError('Offline dictation returned no usable transcript.')
            try:
                text = ' '.join(line.strip() for line in output.read_text(encoding='utf-8').splitlines() if line.strip())
            except UnicodeError as error:
                raise SpeechError('Offline dictation returned an invalid transcript.') from error
            if not text or re.fullmatch(r'[\s\[\]()♪♫.\-]*', text) or re.fullmatch(r'\s*\[(?:BLANK_AUDIO|silence|no speech|music)\]\s*', text, re.IGNORECASE):
                raise SpeechError('No clear speech was recognized offline. Try again or type the turn.')
            if cancel and cancel.is_set():
                raise SpeechError('Speech cancelled.')
            return text
        except OSError as error:
            raise SpeechError('Offline dictation could not read its completed transcript.') from error


def recognize_with_fallback(audio, lang, config=None, cancel=None):
    config = dict(config or {})
    provider = config.get('speech_provider', 'auto')
    _speech_pcm(audio)
    if cancel and cancel.is_set():
        raise SpeechError('Speech cancelled.')
    review = 'Review dictation before translating; names, numbers and negation can be misheard.'
    trace = []
    def completed(text, route, failures):
        if cancel and cancel.is_set():
            raise SpeechError('Speech cancelled.')
        warnings = [review]
        if failures:
            warnings.append('The first dictation route was unavailable; used ' + ('bundled offline dictation.' if route in ('offline','omnilingual') else 'free online dictation.'))
        if route == 'offline':
            warnings.append('Review offline wording carefully, especially names, numbers and low-resource languages.')
            if lang == 'zh-CN':
                warnings.append('Check Chinese characters carefully; the bundled model made a character error in a local synthetic test.')
            description = 'Bundled ' + OFFLINE_MODEL_LABEL + '; audio stayed on this PC.'
        elif route == 'google_web':
            description = 'Free Google online dictation; no user key.'
        elif route == 'omnilingual':
            description = 'Bundled Omnilingual CTC 300M int8; audio stayed on this PC.'
            warnings.append('Review multilingual dictation carefully. The CTC model has no language constraint; short clips and spelling can be wrong.')
        else:
            description = route + ' dictation'
        return {'text': text, 'provider': route, 'warnings': warnings, 'trace': trace + failures + [description]}
    if provider not in ('auto', 'free'):
        return completed(recognize_wav(audio, lang, config, cancel), provider, [])
    routes = []
    # Paired clean/quiet/noisy fixtures retained English and French quantities
    # better locally. Other supported locales prefer the free online route.
    if lang in ('en-US', 'fr-FR'):
        routes.append('offline')
    if lang in GOOGLE_STT_LOCALES:
        routes.append('google_web')
    if lang in WHISPER_LOCALES and 'offline' not in routes:
        routes.append('offline')
    if lang in OMNILINGUAL_LOCALES:
        routes.append('omnilingual')
    if lang == 'fa-IR':
        trace.append('Offline Persian route sidelined after local quality checks.')
    if not routes:
        raise SpeechError('This exact language is not supported by the available dictation routes. Type the turn instead.')
    failures = []
    for route in routes:
        if cancel and cancel.is_set():
            raise SpeechError('Speech cancelled.')
        try:
            text = recognize_wav(audio, lang, {**config, 'speech_provider': route}, cancel)
            return completed(text, route, failures)
        except SpeechError as error:
            if cancel and cancel.is_set():
                raise
            failures.append(route + ' route: ' + str(error))
    raise SpeechError('Dictation could not complete. ' + ' '.join(failures))


def _speech_worker_command(input_path, output_path):
    args = [sys.executable]
    if not getattr(sys, 'frozen', False): args.append(str(Path(__file__).resolve().with_name('app.py')))
    return args + ['--speech-preview-worker', str(input_path), '--speech-preview-output', str(output_path)]


def _speech_cloud_worker(task, content, lang, config, cancel=None, timeout=10):
    """A killable cloud/native-render worker, never a nested Whisper child."""
    cancel = cancel or threading.Event()
    if cancel.is_set(): raise SpeechError('Speech cancelled.')
    if task not in ('recognize', 'voice') or not .1 <= timeout <= 60:
        raise SpeechError('Invalid speech worker request.')
    provider = config.get('speech_provider') if task == 'recognize' else config.get('voice_provider')
    allowed = ('google_web', 'google', 'azure') if task == 'recognize' else ('google_web', 'windows', 'azure')
    if provider not in allowed: raise SpeechError('Unsupported isolated speech route.')
    directory = Path(config.get('_audio_dir') or tempfile.gettempdir()); directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='speech-worker-', dir=directory) as scratch:
        folder = Path(scratch); source, output = folder/'request.json', folder/'result.json'
        settings = {key: config.get(key, '') for key in ('speech_key', 'speech_region')}
        payload = {'version': 1, 'task': task, 'locale': lang, 'provider': provider, 'config': settings, 'timeout': timeout}
        if task == 'recognize':
            _speech_pcm(content); (folder/'input.wav').write_bytes(content); payload['audio_file'] = 'input.wav'
        else:
            _voice_chunks(content); payload['text'] = content
        source.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
        if cancel.is_set(): raise SpeechError('Speech cancelled.')
        try:
            process = subprocess.Popen(_speech_worker_command(source, output), stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except OSError as error: raise SpeechError('The bundled speech worker could not start.') from error
        deadline = time.monotonic() + timeout
        try:
            while process.poll() is None:
                if cancel.wait(.025): raise SpeechError('Speech cancelled.')
                if time.monotonic() >= deadline: raise SpeechError('The isolated speech route exceeded its time budget.')
                if output.exists() and output.stat().st_size > 65536: raise SpeechError('Speech worker returned an oversized response.')
            if cancel.is_set(): raise SpeechError('Speech cancelled.')
            if process.returncode or not output.is_file() or output.stat().st_size > 65536:
                raise SpeechError('The isolated speech route returned no complete response.')
            value = json.loads(output.read_text(encoding='utf-8'))
            if not isinstance(value, dict) or value.get('version') != 1 or value.get('provider') != provider:
                raise SpeechError('The speech worker returned an invalid response.')
            if value.get('error'): raise SpeechError(str(value['error'])[:1000])
            if task == 'recognize':
                if not isinstance(value.get('text'), str) or not 0 < len(value['text'].strip()) <= 50000:
                    raise SpeechError('The preview worker returned no usable text.')
            else:
                path = folder/'voice.wav'
                if value.get('audio_file') != 'voice.wav' or not path.is_file() or path.stat().st_size > 8*1024*1024:
                    raise SpeechError('The voice worker returned no complete PCM audio.')
                audio = path.read_bytes(); _voice_pcm(audio)
                if not isinstance(value.get('voice'), str) or value.get('locale') != lang:
                    raise SpeechError('The voice worker returned a different language.')
                value['audio'] = audio
            return value
        except (ValueError, UnicodeError, OSError) as error:
            raise SpeechError('The speech worker response could not be read.') from error
        finally:
            if process.poll() is None: process.kill()
            process.wait(timeout=5)


def run_speech_preview_worker(input_path, output_path):
    """Private protocol for cloud previews and complete voice reserve rendering.

    Recognizer providers are explicitly cloud-only. Native Whisper runs directly
    in the preview coordinator, so killing this worker cannot orphan a CLI.
    """
    try:
        source, output = Path(input_path), Path(output_path)
        if not source.is_file() or source.stat().st_size > 65536 or output.exists() or output.suffix != '.json' or output.parent.resolve() != source.parent.resolve(): return 1
        value = json.loads(source.read_text(encoding='utf-8'))
        if not isinstance(value, dict) or value.get('version') != 1: return 1
        task, lang, provider, timeout = (value.get(key) for key in ('task', 'locale', 'provider', 'timeout'))
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not .1 <= timeout <= 60: return 1
        supplied = value.get('config')
        if not isinstance(supplied, dict) or any(not isinstance(supplied.get(key, ''), str) or len(supplied.get(key, '')) > maximum for key, maximum in (('speech_key', 4096), ('speech_region', 128))): return 1
        config = {key: supplied.get(key, '') for key in ('speech_key', 'speech_region')}
        config['_audio_dir'] = str(source.parent)
        if task == 'recognize':
            if provider not in ('google_web', 'azure', 'google') or not recognition_supported(lang, provider) or value.get('audio_file') != 'input.wav': return 1
            audio_file = source.parent/'input.wav'
            if not audio_file.is_file() or not 44 < audio_file.stat().st_size <= 1700000: return 1
            config['speech_provider'] = provider
            result = {'version': 1, 'provider': provider, 'text': recognize_wav(audio_file.read_bytes(), lang, config, threading.Event())}
        elif task == 'voice':
            if provider not in ('google_web', 'windows', 'azure'): return 1
            if (source.parent/'voice.wav').exists(): return 1
            text = value.get('text'); _voice_chunks(text)
            config['voice_provider'] = provider
            prepared = _prepare_voice_direct(provider, text, lang, config, threading.Event(), timeout)
            audio = prepared.pop('audio'); _voice_pcm(audio)
            with (source.parent/'voice.wav').open('xb') as file: file.write(audio)
            result = {'version': 1, **prepared, 'audio_file': 'voice.wav'}
        else: return 1
        with output.open('x', encoding='utf-8') as file: json.dump(result, file, ensure_ascii=False)
        return 0
    except Exception as error:
        try:
            if not output.exists():
                with output.open('x', encoding='utf-8') as file:
                    json.dump({'version': 1, 'provider': value.get('provider'), 'error': str(error)[:1000]}, file)
                return 0
        except Exception: pass
        return 1


# Dialect-sensitive voices keep explicit tags. Dari and Kurdish/Oromo/Tigrinya
# have no verified matching public Google voice here and are not relabelled.
GOOGLE_TTS_LOCALES = {code: code.split('-')[0] for code in (
    'en-US', 'ar-SA', 'fr-FR', 'tr-TR', 'ur-PK', 'hi-IN', 'bn-BD',
    'pa-IN', 'sw-KE', 'es-ES', 'de-DE', 'it-IT', 'ru-RU', 'ja-JP', 'ko-KR',
    'nl-NL', 'pl-PL', 'ro-RO', 'uk-UA', 'el-GR', 'he-IL', 'id-ID')}
GOOGLE_TTS_LOCALES.update({'pt-PT': 'pt-PT', 'zh-CN': 'zh-CN', 'he-IL': 'iw', 'am-ET': 'am'})


def _voice_chunks(text, maximum=100):
    if not isinstance(text, str) or not text.strip() or len(text) > 6000:
        raise SpeechError('Voice needs nonempty text of at most 6,000 characters.')
    parts = []
    while text:
        cut = min(maximum, len(text))
        if cut < len(text):
            space = text.rfind(' ', 0, cut)
            if space > maximum // 3:
                cut = space + 1
        parts.append(text[:cut])
        text = text[cut:]
    return parts


def _valid_mp3(audio):
    return isinstance(audio, bytes) and len(audio) >= 256 and (audio.startswith(b'ID3') or any(audio[index] == 255 and audio[index + 1] & 0xE0 == 0xE0 for index in range(min(2048, len(audio) - 1))))


def google_tts_audio(text, lang, stop=None, timeout=12):
    if lang not in GOOGLE_TTS_LOCALES:
        raise SpeechError('No verified free voice exists for this exact language. No substitute language was used.')
    if not isinstance(text, str) or not text.strip() or len(text) > 100:
        raise SpeechError('Free voice requests need 1 to 100 characters per chunk.')
    locale_code = GOOGLE_TTS_LOCALES[lang]
    url = 'https://translate.google.com/translate_tts?' + urllib.parse.urlencode({'ie': 'UTF-8', 'client': 'tw-ob', 'tl': locale_code, 'q': text})
    audio = request(url, None, {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://translate.google.com/'}, stop, timeout=timeout, maximum=2 * 1024 * 1024, method='GET')
    if not _valid_mp3(audio):
        raise SpeechError('Free voice returned invalid audio. Nothing was played.')
    return audio


def mp3_to_wav(audio):
    """Decode with the bundled tiny codec, independent of Windows MP3 features."""
    if not _valid_mp3(audio) or len(audio) > 2 * 1024 * 1024:
        raise SpeechError('Free voice returned invalid or oversized audio.')
    try:
        import miniaudio
        info = miniaudio.mp3_get_info(audio)
        if not 0 < info.duration <= 60:
            raise SpeechError('The returned voice chunk duration is invalid.')
        decoded = miniaudio.decode(audio, output_format=miniaudio.SampleFormat.SIGNED16, nchannels=1, sample_rate=16000)
        samples = decoded.samples
        if decoded.sample_rate != 16000 or decoded.nchannels != 1 or samples.itemsize != 2 or not 0 < len(samples) <= 960000:
            raise SpeechError('The bundled decoder returned invalid voice samples.')
        if len(samples) / 16000 < info.duration - .25:
            raise SpeechError('The returned voice audio is incomplete. Nothing was played.')
        if sys.byteorder != 'little':
            samples.byteswap()
        pcm = samples.tobytes()
    except SpeechError:
        raise
    except Exception as error:
        raise SpeechError('The bundled voice decoder could not read this audio. Restore the complete portable app if codec files are missing.') from error
    output = io.BytesIO()
    with wave.open(output, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(pcm)
    return output.getvalue(), len(samples) / 16000


def inspect_mp3(path):
    """Decode/open duration check only; does not play sound."""
    _, duration = mp3_to_wav(Path(path).read_bytes())
    return {'duration_ms': round(duration * 1000), 'decoded': True, 'decoder': 'Bundled miniaudio; no Windows MP3 codec required.'}


def _play_mp3(path, stop):
    audio, duration = mp3_to_wav(Path(path).read_bytes())
    wav_path = Path(path).with_suffix('.wav')
    try:
        if stop.is_set():
            raise SpeechError('Voice cancelled.')
        wav_path.write_bytes(audio)
        if stop.is_set():
            raise SpeechError('Voice cancelled.')
        winsound.PlaySound(str(wav_path), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
        deadline = time.monotonic() + duration + .2
        while time.monotonic() < deadline and not stop.wait(.04):
            pass
        return not stop.is_set()
    finally:
        try:
            winsound.PlaySound(None, 0)
        finally:
            wav_path.unlink(missing_ok=True)


def _edge_tts_audio_inprocess(text, lang, stop, timeout=60):
    if lang not in AZURE_VOICES:
        raise SpeechError('No exact free Edge voice exists for this language.')
    if stop.is_set():
        raise SpeechError('Voice cancelled.')
    async def collect():
        import edge_tts
        result = bytearray()
        communicator = edge_tts.Communicate(text, AZURE_VOICES[lang], connect_timeout=8, receive_timeout=12)
        async for part in communicator.stream():
            if stop.is_set():
                raise SpeechError('Voice cancelled.')
            if part['type'] == 'audio':
                result.extend(part['data'])
                if len(result) > 2 * 1024 * 1024:
                    raise SpeechError('Free Edge voice returned oversized audio.')
        if not _valid_mp3(bytes(result)):
            raise SpeechError('Free Edge voice returned invalid audio.')
        return bytes(result)
    async def bounded():
        task = asyncio.create_task(collect())
        deadline = time.monotonic() + timeout
        try:
            while not task.done():
                if stop.is_set():
                    raise SpeechError('Voice cancelled.')
                if time.monotonic() > deadline:
                    raise SpeechError('Free Edge voice synthesis timed out.')
                await asyncio.wait({task}, timeout=.05)
            return await task
        finally:
            if not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
    try:
        return asyncio.run(bounded())
    except SpeechError:
        raise
    except Exception as error:
        raise SpeechError('The free Edge voice service is unavailable. Trying another available voice route.') from error


def run_edge_voice_worker(input_path, output_path):
    """Private CLI worker, before any GUI, user-data store or instance lock.

    Only the parent owns its time/cancel boundary. A blocked DNS resolver or
    asyncio executor teardown can be killed without delaying the parent task.
    """
    try:
        source, destination = Path(input_path), Path(output_path)
        if not source.is_file() or source.stat().st_size > 65536:
            return 1
        if destination.parent.resolve() != source.parent.resolve() or destination.suffix.lower() != '.mp3' or destination.exists():
            return 1
        payload = json.loads(source.read_text(encoding='utf-8'))
        if not isinstance(payload, dict) or payload.get('version') != 1:
            return 1
        text, lang, timeout = payload.get('text'), payload.get('locale'), payload.get('timeout')
        if not isinstance(text, str) or not text.strip() or len(text) > 6000 or lang not in AZURE_VOICES:
            return 1
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not .1 <= timeout <= 60:
            return 1
        audio = _edge_tts_audio_inprocess(text, lang, threading.Event(), timeout)
        if not _valid_mp3(audio) or len(audio) > 2 * 1024 * 1024:
            return 1
        with destination.open('xb') as file:
            file.write(audio)
        return 0
    except Exception:
        return 1


def _edge_worker_command(input_path, output_path):
    args = [sys.executable]
    if not getattr(sys, 'frozen', False):
        args.append(str(Path(__file__).resolve().with_name('app.py')))
    return args + ['--edge-voice-worker', str(input_path), '--edge-voice-output', str(output_path)]


def edge_tts_audio(text, lang, stop, timeout=60, directory=None):
    if lang not in AZURE_VOICES or not isinstance(text, str) or not text.strip() or len(text) > 6000:
        raise SpeechError('Free Edge voice needs valid text and an exact supported language.')
    if stop.is_set():
        raise SpeechError('Voice cancelled.')
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not .1 <= timeout <= 60:
        raise SpeechError('Free Edge voice needs a time budget between 0.1 and 60 seconds.')
    directory = Path(directory or tempfile.gettempdir())
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='edge-worker-', dir=directory) as scratch:
        source, destination = Path(scratch) / 'request.json', Path(scratch) / 'voice.mp3'
        source.write_text(json.dumps({'version': 1, 'text': text, 'locale': lang, 'timeout': timeout}, ensure_ascii=False), encoding='utf-8')
        if stop.is_set():
            raise SpeechError('Voice cancelled.')
        command = _edge_worker_command(source, destination)
        try:
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except OSError as error:
            raise SpeechError('The bundled free voice worker could not start.') from error
        deadline = time.monotonic() + timeout
        try:
            while process.poll() is None:
                if stop.wait(min(.05, max(0, deadline - time.monotonic()))):
                    raise SpeechError('Voice cancelled.')
                if time.monotonic() >= deadline:
                    raise SpeechError('Free Edge voice synthesis exceeded its time budget.')
            if stop.is_set():
                raise SpeechError('Voice cancelled.')
            if process.returncode != 0 or not destination.is_file():
                raise _TransientVoiceError('The free Edge voice worker returned no complete audio.')
            if not 256 <= destination.stat().st_size <= 2 * 1024 * 1024:
                raise SpeechError('The free Edge voice worker returned incomplete or oversized audio.')
            audio = destination.read_bytes()
            if not _valid_mp3(audio):
                raise SpeechError('The free Edge voice worker returned invalid audio.')
            return audio
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)


_VOICE_CACHE = OrderedDict()
_VOICE_CACHE_LOCK = threading.Lock()
_VOICE_CACHE_BYTES = 20 * 1024 * 1024
_VOICE_CACHE_TTL = 120.0
_VOICE_PREPARE_SLOTS = threading.BoundedSemaphore(2)
_VOICE_PLAYBACK_LOCK = threading.Lock()
VOICE_QUALITY_GRACE = .35


class VoiceSession:
    """Only actual failures in this service session affect short retry ordering."""
    def __init__(self): self.lock, self.failures = threading.Lock(), {}
    def failed(self, provider, lang, error):
        with self.lock: self.failures[(provider, lang)] = (time.monotonic() + 30, str(error)[:1000])
    def order(self, providers, lang):
        with self.lock:
            now = time.monotonic()
            self.failures = {key: value for key, value in self.failures.items() if value[0] > now}
            return sorted(providers, key=lambda provider: (provider, lang) in self.failures)


def voice_route_plan(lang, config=None):
    config = config or {}; selected = config.get('voice_provider', 'auto')
    if selected not in ('auto', 'edge_free', 'google_web', 'windows', 'azure', 'offline'):
        raise SpeechError('Select a supported voice provider.')
    offline = ['offline_piper'] if offline_voice_available(lang, config) else []
    providers = (['edge_free'] if lang in AZURE_VOICES else []) + offline + (['google_web'] if lang in GOOGLE_TTS_LOCALES else []) + ['windows']
    if selected == 'offline':
        providers = offline + ['windows']
    if selected == 'azure' and lang in AZURE_VOICES and config.get('speech_key'):
        providers.insert(0, 'azure')
    elif selected in providers:
        providers.remove(selected); providers.insert(0, selected)
    session = config.get('_voice_session')
    if selected == 'auto' and isinstance(session, VoiceSession): providers = session.order(providers, lang)
    return {'selected_provider': selected, 'preferred_provider': providers[0], 'providers': providers,
            'local_only': selected == 'offline',
            'basis': 'Mapped neural Edge voice, a bundled exact-locale reserve where available, supported Google voice, then exact installed Windows. Explicit Offline keeps synthesis local. Complete reserves can provide faster fallback.'}


def offline_voice_available(lang, config=None):
    import offline_voice
    return offline_voice.available(lang, config)


def voice_supported(lang, config=None, native_voices=()):
    config = config or {}
    native = bool(matching_sapi_voice(lang, native_voices, exact=True))
    if config.get('voice_provider') == 'offline':
        return offline_voice_available(lang, config) or native
    return lang in FREE_VOICE_LOCALES or offline_voice_available(lang, config) or native


def clear_voice_cache():
    with _VOICE_CACHE_LOCK: _VOICE_CACHE.clear()


def _voice_cache_key(provider, text, lang, config):
    credentials = (config.get('speech_key', '') + '\0' + config.get('speech_region', '')) if provider == 'azure' else ''
    identity = AZURE_VOICES.get(lang, '') if provider in ('azure', 'edge_free') else GOOGLE_TTS_LOCALES.get(lang, '')
    if provider == 'offline_piper':
        import offline_voice
        identity = offline_voice.cache_identity(lang)
    return provider, lang, identity, hashlib.sha256((text + '\0' + credentials).encode('utf-8')).digest()


def _voice_cache_get(key):
    with _VOICE_CACHE_LOCK:
        now = time.monotonic()
        for old in list(_VOICE_CACHE):
            if _VOICE_CACHE[old][0] <= now: del _VOICE_CACHE[old]
        if key not in _VOICE_CACHE: return None
        _, value = _VOICE_CACHE[key]; _VOICE_CACHE.move_to_end(key)
        return {**value, 'cache_hit': True}


def _voice_cache_put(key, value):
    size = len(value['audio'])
    if size > _VOICE_CACHE_BYTES: return
    with _VOICE_CACHE_LOCK:
        _VOICE_CACHE[key] = (time.monotonic() + _VOICE_CACHE_TTL, {**value, 'cache_hit': False})
        _VOICE_CACHE.move_to_end(key)
        while len(_VOICE_CACHE) > 4 or sum(len(row[1]['audio']) for row in _VOICE_CACHE.values()) > _VOICE_CACHE_BYTES:
            _VOICE_CACHE.popitem(last=False)


def _voice_pcm(audio):
    try:
        if not isinstance(audio, bytes) or not 44 < len(audio) <= 8 * 1024 * 1024:
            raise SpeechError('Prepared voice audio is empty or oversized.')
        with wave.open(io.BytesIO(audio), 'rb') as wav:
            if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getcomptype()) != (1, 2, 16000, 'NONE'):
                raise SpeechError('Prepared voice audio has an unsupported PCM format.')
            if not 0 < wav.getnframes() <= 240 * 16000:
                raise SpeechError('Voice playback needs a complete passage of at most four minutes.')
            pcm = wav.readframes(wav.getnframes())
            if len(pcm) != wav.getnframes() * 2:
                raise SpeechError('Prepared voice audio is incomplete. Nothing was played.')
            return pcm, wav.getnframes()/16000
    except (wave.Error, EOFError, ValueError, OverflowError) as error:
        raise SpeechError('Prepared voice audio is not valid PCM.') from error


def _prepare_native_voice(text, lang, stop, directory):
    import pythoncom
    import win32com.client
    candidate = matching_sapi_voice(lang, sapi_voices(), exact=True)
    if not candidate: raise SpeechError('No Windows voice is installed for this exact language.')
    path = Path(directory)/('windows-' + uuid.uuid4().hex + '.wav')
    pythoncom.CoInitialize()
    stream = None
    try:
        voice = win32com.client.Dispatch('SAPI.SpVoice')
        voice.Voice = next(token for token in voice.GetVoices() if token.Id == candidate['id'])
        audio_format = win32com.client.Dispatch('SAPI.SpAudioFormat'); audio_format.Type = 18  # 16 kHz, 16-bit mono
        stream = win32com.client.Dispatch('SAPI.SpFileStream'); stream.Format = audio_format
        stream.Open(str(path), 3, False)  # create-for-write, private file
        # SAPI otherwise may silently replace the requested PCM format with the
        # engine's preferred sample rate when assigning the output stream.
        voice.AllowAudioOutputFormatChangesOnNextSet = False
        voice.AudioOutputStream = stream
        voice.Speak(text, 1 | 16)
        while not voice.WaitUntilDone(40):
            if stop.is_set(): voice.Speak('', 3); raise SpeechError('Voice cancelled.')
        stream.Close(); stream = None
        audio = path.read_bytes(); _voice_pcm(audio)
        return {'audio': audio, 'voice': candidate['name'], 'provider': 'windows', 'locale': lang}
    finally:
        if stream is not None:
            with contextlib.suppress(Exception): stream.Close()
        pythoncom.CoUninitialize(); path.unlink(missing_ok=True)


def _prepare_voice_direct(provider, text, lang, config, stop, timeout):
    """Synthesize every chunk and decode once, before any sound is possible."""
    _voice_chunks(text)
    if stop.is_set(): raise SpeechError('Voice cancelled.')
    if provider == 'windows':
        return _prepare_native_voice(text, lang, stop, config['_audio_dir'])
    if provider == 'azure':
        audio = _azure_voice_audio(text, lang, config, stop, timeout)
        _voice_pcm(audio)
        return {'audio': audio, 'voice': AZURE_VOICES[lang], 'provider': provider, 'locale': lang}
    if provider not in ('edge_free', 'google_web') or lang not in (AZURE_VOICES if provider == 'edge_free' else GOOGLE_TTS_LOCALES):
        raise SpeechError('No verified voice exists for this exact language and provider.')
    deadline = time.monotonic() + timeout
    attempts = 2 if provider == 'edge_free' else 1
    for attempt in range(attempts):
        blocks = []; total = 0
        try:
            for chunk in _voice_chunks(text, 500 if provider == 'edge_free' else 100):
                if not chunk.strip(): continue
                if stop.is_set(): raise SpeechError('Voice cancelled.')
                remaining = deadline - time.monotonic()
                if remaining <= 0: raise SpeechError('Complete voice preparation exceeded its time budget.')
                mp3 = edge_tts_audio(chunk, lang, stop, remaining, directory=config.get('_audio_dir')) if provider == 'edge_free' else google_tts_audio(chunk, lang, stop, timeout=min(12, remaining))
                wav, _ = mp3_to_wav(mp3); pcm, _ = _voice_pcm(wav)
                total += len(pcm)
                if total > 240 * 32000: raise SpeechError('This complete voice passage is too long. Choose a shorter passage.')
                blocks.append(pcm)
            if stop.is_set(): raise SpeechError('Voice cancelled.')
            if time.monotonic() > deadline: raise SpeechError('Complete voice preparation exceeded its time budget.')
            audio = _wav_from_pcm(b''.join(blocks)); _voice_pcm(audio)
            return {'audio': audio, 'voice': AZURE_VOICES[lang] if provider == 'edge_free' else 'Free Google Translate voice',
                    'provider': provider, 'locale': lang, 'characters': len(text), 'decoded': True,
                    'synthesis_attempts': attempt + 1,
                    'preparation_trace': ['Retried the complete Edge passage once after a missing worker result; discarded all earlier chunks.'] if attempt else []}
        except _TransientVoiceError:
            if provider != 'edge_free' or attempt != 0 or stop.is_set() or deadline - time.monotonic() < .1:
                raise
            # Rebuild the entire passage. Previous chunks never escape this
            # attempt, and retry shares the same absolute preparation deadline.
            continue
    raise SpeechError('Voice preparation could not produce the complete passage.')


def _prepare_voice(provider, text, lang, config, stop, timeout):
    # Installed Windows voices can change independently of app settings. Keep
    # that optional renderer fresh instead of caching an unidentified token.
    key = _voice_cache_key(provider, text, lang, config); cached = _voice_cache_get(key) if provider != 'windows' else None
    if cached is not None:
        if stop.is_set(): raise SpeechError('Voice cancelled.')
        return cached
    if provider == 'offline_piper':
        import offline_voice
        try: value = offline_voice.prepare(text, lang, config, stop, timeout)
        except offline_voice.OfflineVoiceError as error: raise SpeechError(str(error)) from error
    elif provider == 'edge_free': value = _prepare_voice_direct(provider, text, lang, config, stop, timeout)
    else: value = _speech_cloud_worker('voice', text, lang, {**config, 'voice_provider': provider}, stop, timeout)
    if stop.is_set(): raise SpeechError('Voice cancelled.')
    _voice_pcm(value['audio'])
    if provider != 'windows': _voice_cache_put(key, value)
    return {**value, 'cache_hit': False}


def _play_wav_audio(audio, stop, directory=None):
    _, duration = _voice_pcm(audio)
    directory = Path(directory or tempfile.gettempdir()); directory.mkdir(parents=True, exist_ok=True)
    acquired = False
    try:
        queue_deadline = time.monotonic() + 5
        while not stop.is_set():
            if _VOICE_PLAYBACK_LOCK.acquire(timeout=.025): acquired = True; break
            if time.monotonic() >= queue_deadline:
                raise SpeechError('The previous voice is still playing. Stop it, then retry Listen.')
        if not acquired or stop.is_set(): return False
        with tempfile.TemporaryDirectory(prefix='voice-play-', dir=directory) as scratch:
            path = Path(scratch)/'complete.wav'; path.write_bytes(audio)
            if stop.is_set(): return False
            try:
                winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
                deadline = time.monotonic() + duration + .2
                while time.monotonic() < deadline and not stop.wait(.025): pass
                return not stop.is_set()
            finally: winsound.PlaySound(None, 0)
    finally:
        if acquired: _VOICE_PLAYBACK_LOCK.release()


def speak_free(text, lang, config, stop):
    _voice_chunks(text)
    if stop.is_set(): raise SpeechError('Voice cancelled.')
    config = dict(config or {}); plan = voice_route_plan(lang, config)
    directory = Path(config.get('_audio_dir') or tempfile.gettempdir()); directory.mkdir(parents=True, exist_ok=True)
    config['_audio_dir'] = str(directory)
    deadline = time.monotonic() + 60; changed = threading.Condition(); jobs = {}; errors = []; chosen = None
    session = config.get('_voice_session')
    def start(provider):
        local_stop = threading.Event(); cancel = _CombinedCancel(local_stop, stop)
        job = {'cancel': local_stop, 'done': False, 'value': None, 'error': None}; jobs[provider] = job
        def run():
            acquired = False
            try:
                if provider not in ('windows', 'offline_piper'):
                    while not cancel.is_set():
                        if _VOICE_PREPARE_SLOTS.acquire(timeout=.025): acquired = True; break
                        if time.monotonic() >= deadline: raise SpeechError('Voice preparation is busy.')
                    if not acquired: raise SpeechError('Voice cancelled.')
                remaining = deadline - time.monotonic()
                if remaining <= 0: raise SpeechError('Voice preparation exceeded its one-minute limit.')
                value = _prepare_voice(provider, text, lang, config, cancel, remaining)
                with changed: job['value'] = value
            except Exception as error:
                with changed: job['error'] = str(error)
                if not cancel.is_set() and isinstance(session, VoiceSession): session.failed(provider, lang, error)
            finally:
                if acquired: _VOICE_PREPARE_SLOTS.release()
                with changed: job['done'] = True; changed.notify_all()
        job['thread'] = threading.Thread(target=run, name='voice-prepare-' + provider, daemon=True)
        job['thread'].start()
    providers = plan['providers']; preferred = providers[0]
    start(preferred)
    # Windows is an exact-locale, lazy local fallback. An explicitly selected
    # Windows route gets the first attempt without speculative cloud uploads.
    if preferred not in ('windows', 'offline_piper'):
        reserve = next((provider for provider in providers[1:] if provider != 'windows'), None)
        if reserve: start(reserve)
    reserve_ready_at = None
    try:
        while chosen is None:
            if stop.is_set(): raise SpeechError('Voice cancelled.')
            if time.monotonic() >= deadline: raise SpeechError('Complete voice preparation exceeded its one-minute limit.')
            with changed:
                ready = [provider for provider in providers if provider in jobs and jobs[provider]['value'] is not None]
                active = [provider for provider, job in jobs.items() if not job['done']]
                if preferred in ready: chosen = jobs[preferred]['value']; break
                if ready:
                    if reserve_ready_at is None: reserve_ready_at = time.monotonic()
                    if preferred not in active or time.monotonic() - reserve_ready_at >= VOICE_QUALITY_GRACE:
                        selected = ready[0]; chosen = jobs[selected]['value']
                        if preferred in active: errors.append('Preferred ' + preferred + ' voice was not ready within the short quality grace; used the complete ' + selected + ' reserve.')
                        break
                # At most two online providers are prepared. Only move to the
                # exact-locale Windows renderer after every online attempt fails.
                unstarted = [provider for provider in providers if provider not in jobs]
                online_active = sum(provider not in ('windows', 'offline_piper') for provider in active)
                for provider in unstarted:
                    if provider == 'windows':
                        if not active and not ready: start(provider)
                    elif provider == 'offline_piper':
                        if not active and not ready: start(provider)
                    elif online_active < 2 and (preferred not in ('windows', 'offline_piper') or jobs[preferred]['done']):
                        start(provider); online_active += 1
                if not ready and all(job['done'] for job in jobs.values()) and len(jobs) == len(providers):
                    errors = [provider + ': ' + str(job['error']) for provider, job in jobs.items()]
                    raise SpeechError('No matching-language voice could prepare the complete passage. ' + ' '.join(errors))
                changed.wait(.025)
        for provider, job in jobs.items():
            if chosen.get('provider') != provider: job['cancel'].set()
            if job['error'] and 'cancelled' not in job['error'].lower(): errors.append(provider + ': ' + job['error'])
        if stop.is_set(): raise SpeechError('Voice cancelled.')
        complete = _play_wav_audio(chosen['audio'], stop, directory)
        return {key: value for key, value in {**chosen, 'complete': complete, 'cancelled': not complete,
            'selected_provider': plan['selected_provider'], 'preferred_provider': preferred,
            'prepared_providers': [provider for provider, job in jobs.items() if job['value'] is not None],
            'trace': errors}.items() if key not in ('audio', 'version', 'audio_file')}
    finally:
        for job in jobs.values(): job['cancel'].set()
        # Both online routes have hard child boundaries. This short join is for
        # prompt cleanup, never the old DNS/executor teardown wait.
        for job in jobs.values(): job['thread'].join(timeout=.15)

def sapi_voices():
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    try:
        voice = win32com.client.Dispatch('SAPI.SpVoice')
        rows = []
        for token in voice.GetVoices():
            codes = []
            for raw in token.GetAttribute('Language').split(';'):
                try:
                    codes.append(locale.windows_locale.get(int(raw, 16), '').replace('_', '-').lower())
                except ValueError:
                    pass
            rows.append({'id': token.Id, 'name': token.GetDescription(), 'locales': codes})
        return rows
    finally:
        pythoncom.CoUninitialize()

def matching_sapi_voice(lang, voices, exact=False):
    wanted = lang.lower()
    candidate = next((v for v in voices if wanted in v['locales']), None)
    if candidate:
        return candidate
    if exact:
        return None
    # Dialect-sensitive Portuguese/Chinese/Persian/Kurdish must not borrow another locale.
    if wanted.split('-')[0] in ('pt', 'zh', 'fa', 'ckb', 'ku', 'prs'):
        return None
    return next((v for v in voices if any(c.split('-')[0] == wanted.split('-')[0] for c in v['locales'])), None)

def speak_native(text, lang, stop):
    if stop.is_set():
        raise SpeechError('Voice cancelled.')
    import pythoncom
    import win32com.client
    if len(text) > 6000:
        raise SpeechError('This turn is too long for voice. Select a shorter passage.')
    candidate = matching_sapi_voice(lang, sapi_voices())
    if not candidate:
        raise SpeechError('No Windows voice is installed for this language. Text translation remains available.')
    pythoncom.CoInitialize()
    try:
        voice = win32com.client.Dispatch('SAPI.SpVoice')
        voice.Voice = next(token for token in voice.GetVoices() if token.Id == candidate['id'])
        voice.Speak(text, 1 | 16)  # async, explicitly plain text
        deadline = time.monotonic() + 240
        while not voice.WaitUntilDone(40):
            if stop.is_set() or time.monotonic() >= deadline:
                voice.Speak('', 3)
                if not stop.is_set():
                    raise SpeechError('Voice playback exceeded its time limit.')
                return {'cancelled': True}
        actual = next((code for code in candidate['locales'] if code.split('-')[0] == lang.lower().split('-')[0]), lang)
        return {'voice': candidate['name'], 'locale': actual, 'complete': True}
    finally:
        pythoncom.CoUninitialize()

AZURE_VOICES = {'en-US': 'en-US-JennyNeural', 'ar-SA': 'ar-SA-ZariyahNeural', 'fr-FR': 'fr-FR-DeniseNeural',
 'tr-TR': 'tr-TR-EmelNeural', 'fa-IR': 'fa-IR-DilaraNeural', 'ps-AF': 'ps-AF-LatifaNeural',
 'ur-PK': 'ur-PK-UzmaNeural', 'hi-IN': 'hi-IN-SwaraNeural', 'bn-BD': 'bn-BD-NabanitaNeural',
 'pa-IN': 'pa-IN-VaaniNeural', 'am-ET': 'am-ET-MekdesNeural', 'so-SO': 'so-SO-UbaxNeural',
 'sw-KE': 'sw-KE-ZuriNeural', 'es-ES': 'es-ES-ElviraNeural', 'de-DE': 'de-DE-KatjaNeural',
 'it-IT': 'it-IT-ElsaNeural', 'pt-PT': 'pt-PT-RaquelNeural', 'ru-RU': 'ru-RU-SvetlanaNeural',
 'zh-CN': 'zh-CN-XiaoxiaoNeural', 'ja-JP': 'ja-JP-NanamiNeural', 'ko-KR': 'ko-KR-SunHiNeural',
 'nl-NL': 'nl-NL-ColetteNeural', 'pl-PL': 'pl-PL-ZofiaNeural', 'ro-RO': 'ro-RO-AlinaNeural',
 'uk-UA': 'uk-UA-PolinaNeural', 'el-GR': 'el-GR-AthinaNeural', 'he-IL': 'he-IL-HilaNeural', 'id-ID': 'id-ID-GadisNeural'}
FREE_VOICE_LOCALES = frozenset(AZURE_VOICES) | frozenset(GOOGLE_TTS_LOCALES)

def _azure_voice_audio(text, lang, config, stop, timeout=20):
    """An explicit paid request, without playback or dependence on ASR selection."""
    _voice_chunks(text)
    if stop.is_set(): raise SpeechError('Voice cancelled.')
    if not config.get('speech_key'):
        raise SpeechError('An Azure Speech resource is required for this voice.')
    if lang not in AZURE_VOICES:
        raise SpeechError('No configured native Azure voice exists for this language.')
    region = config.get('speech_region', '')
    if not isinstance(region, str) or not region or len(region) > 128 or not all(c.isascii() and (c.isalnum() or c == '-') for c in region):
        raise SpeechError('Enter your Azure Speech region in Settings.')
    ssml = f'<speak version="1.0" xml:lang="{lang}"><voice name="{AZURE_VOICES[lang]}">{escape(text)}</voice></speak>'
    audio = request(f'https://{region}.tts.speech.microsoft.com/cognitiveservices/v1', ssml.encode('utf-8'), {'Ocp-Apim-Subscription-Key': config['speech_key'], 'Content-Type': 'application/ssml+xml', 'X-Microsoft-OutputFormat': 'riff-16khz-16bit-mono-pcm', 'User-Agent': 'GrayFeatherDesktop'}, stop, timeout=min(20, timeout), maximum=8*1024*1024)
    _voice_pcm(audio)
    if stop.is_set(): raise SpeechError('Voice cancelled.')
    return audio


def speak_azure(text, lang, config, stop):
    audio = _azure_voice_audio(text, lang, config, stop)
    complete = _play_wav_audio(audio, stop, config.get('_audio_dir'))
    return {'voice': AZURE_VOICES[lang], 'locale': lang, 'provider': 'azure', 'complete': complete, 'cancelled': not complete}
