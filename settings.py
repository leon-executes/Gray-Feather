"""Atomic settings and Windows user-bound protected credentials. No secrets in logs."""
from __future__ import annotations
import base64
import copy
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import threading

RETIRED_TRANSLATION_PROVIDERS = frozenset(('index_local', 'hy_mt_local', 'gemma_local'))

DEFAULTS = {
    'provider': 'auto', 'reinforce': True, 'backtranslate': True, 'free_fallback': True,
    'theme': 'dark', 'source1': 'en', 'source2': 'fr',
    'providers': {'azure': {'key': '', 'region': '', 'endpoint': ''},
                  'google': {'key': '', 'endpoint': ''},
                  'deepl': {'key': '', 'endpoint': ''}},
    'speech_provider': 'auto', 'speech_key': '', 'speech_region': '',
    'voice_provider': 'auto', 'voice_enabled': True, 'safe_speech': True,
    'window_geometry': '',
    'auto_speak': True, 'restore_last': True, 'text_size': 12, 'context': '',
}

class SettingsError(Exception):
    pass

class BLOB(ctypes.Structure):
    _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_ubyte))]

def _blob(raw: bytes):
    buf = (ctypes.c_ubyte * len(raw)).from_buffer_copy(raw)
    return BLOB(len(raw), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte))), buf

def protect(raw: bytes, decrypt: bool = False) -> bytes:
    if os.name != 'nt':
        raise SettingsError('Credential protection requires Windows.')
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    inp, keep = _blob(raw)
    result = BLOB()
    func = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    func.argtypes = [ctypes.POINTER(BLOB), ctypes.c_void_p, ctypes.c_void_p,
                     ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(BLOB)]
    func.restype = wintypes.BOOL
    if not func(ctypes.byref(inp), None, None, None, None, 1, ctypes.byref(result)):
        raise SettingsError('Credentials could not be unlocked for this Windows account. Re-enter your keys in Settings.')
    try:
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        kernel.LocalFree(result.pbData)

def atomic_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    try:
        with temporary.open('w', encoding='utf-8', newline='\n') as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)

class Settings:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.RLock()
        self.notice = ''
        self._data = copy.deepcopy(DEFAULTS)
        if not path.exists():
            return
        try:
            doc = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(doc, dict) or doc.get('version') != 1:
                raise ValueError('Unknown settings format')
            saved = doc.get('settings', {})
            if isinstance(saved, dict) and saved.get('provider') in RETIRED_TRANSLATION_PROVIDERS:
                saved = {**saved, 'provider': 'auto'}
                self.notice = 'Offline text translation was removed. Translation now uses online services; other preferences are unchanged.'
            self._merge(saved)
            if doc.get('credentials'):
                try:
                    values = json.loads(protect(base64.b64decode(doc['credentials'], validate=True), True))
                    self._merge(values)
                except Exception:
                    self.notice = 'This Windows account cannot unlock the saved credentials. Re-enter them in Settings.'
            # Keyless builds before free translation had review switched off.
            # Upgrade that obsolete default, while preserving new explicit choices.
            if 'free_fallback' not in doc.get('settings', {}) and not any(config.get('key') for config in self._data['providers'].values()):
                self._data['reinforce'] = True
                self._data['backtranslate'] = True
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            self._data = copy.deepcopy(DEFAULTS)
            self.notice = 'Settings could not be read. Defaults are active; the existing file has been preserved.'

    def _merge(self, values):
        if not isinstance(values, dict):
            raise ValueError('Settings must be an object')
        values = copy.deepcopy(values)
        # The visible Voice Enabled control is authoritative in the revised UI.
        # Keep the prior internal preference in sync for existing integrations.
        if 'voice_enabled' in values:
            values['auto_speak'] = values['voice_enabled']
        merged = copy.deepcopy(self._data)
        for key, value in values.items():
            if key == 'providers':
                if not isinstance(value, dict):
                    raise ValueError('Provider settings must be an object')
                for provider, config in value.items():
                    if provider not in merged['providers']:
                        continue
                    if not isinstance(config, dict):
                        raise ValueError('Provider configuration must be an object')
                    for name, field in config.items():
                        if name == 'free' and provider == 'deepl':
                            if type(field) is not bool:
                                raise ValueError('DeepL endpoint selection must be a boolean')
                            merged['providers'][provider][name] = field
                        elif name in ('key', 'region', 'endpoint', 'glossary_id'):
                            if not isinstance(field, str) or len(field) > 4096:
                                raise ValueError('Provider setting must be a bounded string')
                            merged['providers'][provider][name] = field
            elif key in DEFAULTS:
                expected = type(DEFAULTS[key])
                if type(value) is not expected or (isinstance(value, str) and len(value) > 8192):
                    raise ValueError('Invalid settings value')
                merged[key] = value
        if merged['theme'] not in ('dark', 'light'):
            raise ValueError('Choose a supported theme')
        if merged['provider'] not in ('auto', 'reinforced', 'index_web', 'google_web', 'bing_web', 'mymemory', 'lingva', 'azure', 'google', 'deepl'):
            raise ValueError('Choose a supported translation provider')
        if merged['speech_provider'] not in ('auto', 'google_web', 'offline', 'omnilingual', 'azure', 'google'):
            raise ValueError('Choose a supported speech provider')
        if merged['voice_provider'] not in ('auto', 'offline', 'basic', 'edge_free', 'google_web', 'windows', 'azure'):
            raise ValueError('Choose a supported voice provider')
        if not 10 <= merged['text_size'] <= 24:
            raise ValueError('Reading size must be between 10 and 24')
        self._data = merged

    def get(self):
        with self._lock:
            result = copy.deepcopy(self._data)
            result['auto_speak'] = result['voice_enabled']
            # Earlier builds saved Azure as the default before a speech resource
            # existed. Reopen those settings with the usable, keyless route.
            if result['speech_provider'] in ('azure', 'google') and not result['speech_key'].strip():
                result['speech_provider'] = 'auto'
            if result['provider'] in ('azure', 'google', 'deepl') and not result['providers'][result['provider']]['key'].strip():
                result['provider'] = 'auto'
            return result

    def save(self, values):
        with self._lock:
            old = copy.deepcopy(self._data)
            try:
                self._merge(values)
                public = copy.deepcopy(self._data)
                private = {'providers': {}}
                for name, config in public['providers'].items():
                    private['providers'][name] = {'key': config.pop('key', '')}
                private['speech_key'] = public.pop('speech_key', '')
                has_keys = bool(private['speech_key']) or any(v['key'] for v in private['providers'].values())
                encrypted = base64.b64encode(protect(json.dumps(private).encode('utf-8'))).decode('ascii') if has_keys else ''
                atomic_json(self.path, {'version': 1, 'settings': public, 'credentials': encrypted})
            except Exception:
                self._data = old
                raise
            self.notice = ''
            return self.get()
