"""Portable Gray Feather core: bounded translation routes and SQLite history.

No dependency beyond Python's standard library. Preserve the exact original;
review aids never rewrite text or claim a translation confidence score.
"""
from __future__ import annotations
import csv
import hashlib
import html
from http.cookiejar import CookieJar
import io
import json
import math
import os
import queue
import re
import socket
import sqlite3
import tempfile
import threading
import time
import unicodedata
import uuid
from collections import Counter, OrderedDict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPCookieProcessor, HTTPRedirectHandler, Request, build_opener

MAX_TEXT_CHARS = 200_000
MAX_CONTEXT_CHARS = 20_000
PROVIDER_NAMES = {"google_web": "Google Web", "bing_web": "Microsoft Bing", "mymemory": "MyMemory", "index_web": "Index Translate",
                  "lingva": "Lingva", "libretranslate": "LibreTranslate",
                  "azure": "Microsoft Azure", "google": "Google Cloud", "deepl": "DeepL"}
KEY_PROVIDERS = frozenset(("azure", "google", "deepl"))
PROVIDER_FAMILIES = {"google_web": "google", "google": "google", "lingva": "google", "index_web": "bilibili_index",
                     "bing_web": "microsoft", "azure": "microsoft", "deepl": "deepl",
                     "mymemory": "unverified", "libretranslate": "server_defined"}
DEFAULT_PROVIDERS = ("google_web", "bing_web", "mymemory")

@dataclass(frozen=True)
class Language:
    code: str
    name: str
    native: str
    bcp47: str
    rtl: bool = False
    popular: bool = False

LANGUAGES = (
    Language("en", "English", "English", "en-US", popular=True),
    Language("ar", "Arabic", "العربية", "ar-SA", True, True),
    Language("fr", "French", "Français", "fr-FR", popular=True),
    Language("tr", "Turkish", "Türkçe", "tr-TR", popular=True),
    Language("fa", "Persian / Farsi", "فارسی", "fa-IR", True, True),
    Language("prs", "Dari", "دری", "fa-AF", True, True),
    Language("ps", "Pashto", "پښتو", "ps-AF", True, True),
    Language("ur", "Urdu", "اردو", "ur-PK", True, True),
    Language("hi", "Hindi", "हिन्दी", "hi-IN", popular=True),
    Language("bn", "Bengali / Bangla", "বাংলা", "bn-BD", popular=True),
    Language("pa", "Punjabi (Gurmukhi)", "ਪੰਜਾਬੀ", "pa-IN", popular=True),
    Language("sd", "Sindhi", "سنڌي", "sd-PK", True, True),
    Language("am", "Amharic", "አማርኛ", "am-ET", popular=True),
    Language("ti", "Tigrinya", "ትግርኛ", "ti-ET", popular=True),
    Language("om", "Oromo", "Afaan Oromoo", "om-ET", popular=True),
    Language("so", "Somali", "Soomaali", "so-SO", popular=True),
    Language("sw", "Swahili", "Kiswahili", "sw-KE", popular=True),
    Language("ckb", "Kurdish Sorani / Central Kurdish", "کوردیی ناوەندی", "ckb-IQ", True, True),
    Language("kmr", "Kurdish Kurmanji / Northern Kurdish", "Kurmancî", "ku-TR", popular=True),
    Language("es", "Spanish", "Español", "es-ES"),
    Language("de", "German", "Deutsch", "de-DE"),
    Language("it", "Italian", "Italiano", "it-IT"),
    Language("pt", "Portuguese (Portugal)", "Português", "pt-PT"),
    Language("ru", "Russian", "Русский", "ru-RU"),
    Language("zh", "Chinese (Simplified)", "中文", "zh-CN"),
    Language("ja", "Japanese", "日本語", "ja-JP"),
    Language("ko", "Korean", "한국어", "ko-KR"),
    Language("nl", "Dutch", "Nederlands", "nl-NL"),
    Language("pl", "Polish", "Polski", "pl-PL"),
    Language("ro", "Romanian", "Română", "ro-RO"),
    Language("uk", "Ukrainian", "Українська", "uk-UA"),
    Language("el", "Greek", "Ελληνικά", "el-GR"),
    Language("he", "Hebrew", "עברית", "he-IL", True),
    Language("id", "Indonesian", "Bahasa Indonesia", "id-ID"),
)
LANG_BY_CODE = {language.code: language for language in LANGUAGES}

class TranslationError(Exception):
    def __init__(self, kind: str, message: str, retryable: bool = False, *, status_code=None, retry_after_seconds=None):
        self.kind, self.message, self.retryable = kind, message, retryable
        self.status_code, self.retry_after_seconds = status_code, retry_after_seconds
        super().__init__(message)

class Cancelled(TranslationError):
    def __init__(self):
        super().__init__("cancelled", "Translation cancelled.")

class StorageError(Exception):
    pass

class RevisionConflict(StorageError):
    pass

@dataclass(frozen=True)
class TranslationWarning:
    code: str
    message: str
    source_values: tuple[str, ...] = ()
    target_values: tuple[str, ...] = ()
    def to_dict(self):
        return asdict(self)

@dataclass(frozen=True)
class TranslationResult:
    text: str
    provider: str
    source_code: str
    target_code: str
    warnings: tuple[TranslationWarning, ...]
    elapsed_ms: int
    review_text: str = ""
    review_provider: str = ""
    backtranslation: str = ""
    backtranslation_provider: str = ""
    trace: tuple[dict[str, Any], ...] = ()
    cached: bool = False
    def to_dict(self):
        return asdict(self)

@dataclass(frozen=True)
class ProviderConfig:
    provider: str
    key: str = field(default="", repr=False)
    region: str = ""
    endpoint: str = ""
    timeout: float = 15.0
    glossary_id: str = ""
    model_type: str = "prefer_quality_optimized"

def validate_text(text, name="Text", maximum=MAX_TEXT_CHARS, allow_empty=False):
    if not isinstance(text, str):
        raise TranslationError("input", f"{name} must be text.")
    if len(text) > maximum:
        raise TranslationError("input", f"{name} exceeds {maximum:,} characters; divide it into separate turns.")
    if "\x00" in text or any(0xD800 <= ord(c) <= 0xDFFF for c in text):
        raise TranslationError("input", f"{name} contains invalid Unicode characters.")
    if not allow_empty and not text.strip():
        raise TranslationError("input", f"Enter {name.lower()} first.")
    return text

def _state(deadline, cancel):
    if cancel is not None and cancel.is_set():
        raise Cancelled()
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TranslationError("timeout", "The translation deadline expired. Your source is preserved.", True)
    return remaining

def provider_language(provider, code, target=False):
    if code not in LANG_BY_CODE:
        raise TranslationError("language", f"Unknown language code: {code!r}.")
    if provider in ("azure", "bing_web"):
        if code == "om":
            raise TranslationError("unsupported", "Oromo is not listed for this Microsoft route. Select Google Web.")
        return {"ckb": "ku", "kmr": "kmr", "pt": "pt-pt", "zh": "zh-Hans"}.get(code, code)
    if provider == "google":
        if code == "prs":
            raise TranslationError("unsupported", "Google Cloud has no separate Dari identity. Select Azure for Dari.")
        return {"kmr": "ku", "pt": "pt-PT", "zh": "zh-CN"}.get(code, code)
    if provider in ("google_web", "lingva"):
        return {"prs": "fa", "kmr": "ku", "pt": "pt-PT", "zh": "zh-CN"}.get(code, code)
    if provider == "mymemory":
        return {"prs": "fa", "kmr": "ku", "pt": "pt-PT", "zh": "zh-CN"}.get(code, code)
    if provider == "libretranslate":
        # Models are installed by the selected server; rejection of an absent
        # model is a route failure, never permission to substitute a language.
        return {"prs": "fa", "kmr": "ku", "zh": "zh"}.get(code, code)
    if provider == "deepl":
        baseline = {"en", "ar", "fr", "tr", "es", "de", "it", "pt", "ru", "zh", "ja", "ko", "nl", "pl", "ro", "uk", "el", "he", "id"}
        if code not in baseline:
            raise TranslationError("unsupported", f"{LANG_BY_CODE[code].name} is outside this app's verified DeepL baseline. Select Azure or Google Cloud.")
        if target:
            return {"en": "EN-GB", "pt": "PT-PT", "zh": "ZH-HANS"}.get(code, code.upper())
        return code.upper()
    raise TranslationError("provider", "Choose a recognised translation provider.")

def _route_warnings(provider, source_code, target_code):
    warnings = []
    if provider in ("google_web", "lingva", "mymemory", "libretranslate") and "prs" in (source_code, target_code):
        warnings.append(TranslationWarning("language_approximation", "This route uses Persian for Dari. Vocabulary and regional usage can differ; review the result or choose Microsoft Bing for a distinct Dari route."))
    if provider == "libretranslate" and "pt" in (source_code, target_code):
        warnings.append(TranslationWarning("language_approximation", "This LibreTranslate route uses generic Portuguese; Portugal usage depends on the server's model."))
    return warnings

def _independent(first, second):
    a, b = PROVIDER_FAMILIES.get(first), PROVIDER_FAMILIES.get(second)
    # MyMemory may contain machine translations from other services. A Google
    # mirror or two Microsoft frontends are likewise not independent engines.
    return a is not None and b is not None and not {a, b}.intersection({"unverified", "server_defined"}) and a != b

def provider_supports(provider, source_code, target_code):
    try:
        provider_language(provider, source_code)
        provider_language(provider, target_code, True)
        return True
    except TranslationError:
        return False

def split_text(text, *, max_chars=5000, max_bytes=60_000):
    """Lossless UTF-8 chunks, preferring paragraph/sentence/word boundaries."""
    validate_text(text, allow_empty=True)
    if max_chars < 1 or max_bytes < 4:
        raise ValueError("Chunk limits must fit at least one Unicode character.")
    chunks, start = [], 0
    while start < len(text):
        low, high = start + 1, min(len(text), start + max_chars)
        if len(text[start:low].encode("utf-8")) > max_bytes:
            raise TranslationError("input", "A Unicode character exceeds the selected request limit.")
        while low < high:
            middle = (low + high + 1) // 2
            if len(text[start:middle].encode("utf-8")) <= max_bytes:
                low = middle
            else:
                high = middle - 1
        end = low
        if end < len(text):
            floor = start + max(1, (end - start) // 2)
            breaks = list(re.finditer(r"\n\s*\n|[.!?。！？](?=\s)|\s+", text[floor:end]))
            if breaks:
                end = floor + breaks[-1].end()
            elif end > start + 1:
                while end > start + 1 and (unicodedata.combining(text[end]) or text[end] in "\ufe0f\u200d"):
                    end -= 1
        chunks.append(text[start:end])
        start = end
    return chunks

_NUMBERS = re.compile(r"(?<![A-Za-z_\d])[-+−]?(?:\d{1,2}[hH]\d{2}(?!\w)|\d+(?:[.,٫٬]\d+)*(?:[/:–-]\d+)*)")
_LINKS = re.compile(r"https?://[^\s<>\"']+|(?<![\w@])[\w.!#$%&'*+/=?^`{|}~-]+@[\w.-]+\.[A-Za-z]{2,}")
_REFERENCE = re.compile(r"(?<![A-Za-z0-9_])(?:[A-Z0-9]+(?:[-/][A-Z0-9]+)+|[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+|[A-Z]{2,}\d{2,})(?![A-Za-z0-9_])")
_CURRENCIES = re.compile(r"[£€$¥₹₽₩]|(?<![A-Za-z0-9_])(?:GBP|EUR|USD|JPY|CNY|INR|RUB|KRW)(?![A-Za-z0-9_])")
_CURRENCY_NAMES = {"£": "GBP", "€": "EUR", "$": "USD", "₹": "INR", "₽": "RUB", "₩": "KRW"}
_UNITS = re.compile(r"(?<![A-Za-z_\d])([-+−]?\d+(?:[.,٫٬]\d+)*)\s*(°C|°F|℃|℉|mcg|µg|μg|mg|kg|mL|ml|cm|mm|km|g|L|l|m)(?=$|[^\w]|[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af])")
_UNIT_NAMES = {"mcg": "µg", "μg": "µg", "mL": "ml", "l": "L", "℃": "°C", "℉": "°F"}
_NEGATION = {
    "en": re.compile(r"\b(?:no|not|never|without|cannot|can't|don't|doesn't|won't|mustn't)\b", re.I),
    "fr": re.compile(r"\b(?:pas|jamais|sans|aucun|aucune)\b", re.I),
    "de": re.compile(r"\b(?:nicht|kein\w*|niemals|ohne)\b", re.I),
    "es": re.compile(r"\b(?:no|nunca|sin|ningún|ninguna)\b", re.I),
    "tr": re.compile(r"\b(?:hayır|değil|yok)\b", re.I),
    "ar": re.compile(r"(?:^|\s)(?:لا|ليس|لن|لم|بدون)(?:\s|$)"),
    "fa": re.compile(r"(?:^|\s)(?:نه|نیست|بدون)(?:\s|$)"),
}
def _number(token):
    result = "".join(str(unicodedata.decimal(c)) if c.isdecimal() else c for c in token)
    result = result.replace("−", "-").replace("٫", ".").replace("٬", ",")
    clock = re.fullmatch(r"(\d{1,2})[hH](\d{2})", result)
    if clock and int(clock[1]) < 24 and int(clock[2]) < 60:
        return clock[1] + ":" + clock[2]
    if re.fullmatch(r"[-+]?\d{1,3}(?:[.,]\d{3})+", result):
        return result.replace(",", "").replace(".", "")
    if result.count(",") == 1 and "." not in result:
        result = result.replace(",", ".")
    return result

def extract_facts(text):
    identifiers, references = [], []
    masked = list(text)
    for match in _LINKS.finditer(text):
        identifiers.append(match.group().rstrip(".,;:!?)]}"))
        masked[match.start():match.end()] = " " * (match.end() - match.start())
    plain = "".join(masked)
    for match in _REFERENCE.finditer(plain):
        value = match.group()
        if any(c.isdigit() for c in value) and any(c.isalpha() for c in value):
            references.append(value)
            masked[match.start():match.end()] = " " * (match.end() - match.start())
    plain = "".join(masked)
    return {"numbers": tuple(_number(m.group()) for m in _NUMBERS.finditer(plain)),
            "identifiers": tuple(identifiers), "references": tuple(references),
            "currencies": tuple(_CURRENCY_NAMES.get(m.group(), m.group()) for m in _CURRENCIES.finditer(plain)),
            "units": tuple(_number(m.group(1)) + " " + _UNIT_NAMES.get(m.group(2), m.group(2)) for m in _UNITS.finditer(plain))}

def check_translation(source, target, source_code="en", target_code="fr"):
    """Review aids only. No warnings does not establish accuracy."""
    original, translated, warnings = extract_facts(source), extract_facts(target), []
    messages = {"numbers": "Numeric details differ. Review amounts, dates, times and quantities; formatting can vary by language.",
                "identifiers": "An email address or web address differs. Check the exact address before using it.",
                "references": "A reference or identifier differs. Check the exact letters and digits.",
                "currencies": "Currency markers differ. Verify the currency; translated currency names or symbol placement can vary.",
                "units": "A measurement or unit marker differs. Verify the amount and unit; translated unit names or formatting can vary."}
    for kind, message in messages.items():
        if Counter(original[kind]) != Counter(translated[kind]):
            warnings.append(TranslationWarning(kind, message, original[kind], translated[kind]))
    if source_code in _NEGATION and _NEGATION[source_code].search(source):
        warnings.append(TranslationWarning("negation", "The source contains a possible negation. Confirm that the translated meaning retains it; fact checks cannot establish this."))
    if source.strip() and not target.strip():
        warnings.append(TranslationWarning("empty", "The provider returned no translated text."))
    elif source_code != target_code and source.strip() == target.strip() and any(c.isalpha() for c in source):
        warnings.append(TranslationWarning("unchanged", "Output matches the source. Names can remain unchanged; verify that this turn was translated."))
    return tuple(warnings)

def _currency_quality_selection(source, primary, alternative):
    """Select a whole independent result only for an explicit currency swap.

    Missing markers, written-out numbers, and wording differences never trigger
    selection. A selected alternative must preserve exact references/addresses
    and add no numeric or unit facts detectable by these limited review aids.
    """
    original, first, second = extract_facts(source), extract_facts(primary), extract_facts(alternative)
    a, b, c = (Counter(value["currencies"]) for value in (original, first, second))
    if not a or not b or not set(b).difference(a) or c != a:
        return False
    if any(Counter(second[kind]) != Counter(original[kind]) for kind in ("identifiers", "references")):
        return False
    return not any(Counter(second[kind]) - Counter(original[kind]) for kind in ("numbers", "units"))

def _identity_quality_selection(source, primary, alternative):
    """Only a full fact-preserving result can repair a changed address/ID."""
    original, first, second = extract_facts(source), extract_facts(primary), extract_facts(alternative)
    mismatches = tuple(kind for kind in ("identifiers", "references") if original[kind] and Counter(first[kind]) != Counter(original[kind]))
    if not mismatches or any(Counter(second[kind]) != Counter(original[kind]) for kind in original):
        return ()
    return mismatches

_ENGLISH_IDIOMS = (
    (re.compile(r"\bcall\s+it\s+a\s+day\b", re.I), "'call it a day' often means finish work for today"),
    (re.compile(r"\bpick\s+(?:this|it)\s+up\s+tomorrow\b", re.I), "'pick this/it up tomorrow' can mean resume the task tomorrow; collection of an object is also possible"),
    (re.compile(r"\bball\s+is\s+in\s+(?:your|their|his|her|our|my)\s+court\b", re.I), "'the ball is in your court' often means the next decision or action is your responsibility"),
    (re.compile(r"\b(?:on|onto)\s+the\s+back\s+burner\b", re.I), "'on the back burner' often means postponed or given lower priority"),
    (re.compile(r"\bpiece\s+of\s+cake\b", re.I), "'a piece of cake' can mean easy, or it can refer to food"),
    (re.compile(r"\bbreak\s+the\s+ice\b", re.I), "'break the ice' can mean ease an awkward social situation, or literally break ice"),
)
_EMBEDDED_INSTRUCTIONS = re.compile(r"\b(?:(?:translate|rewrite|paraphrase|summari[sz]e)\s+(?:this|the following|only)|quoted\s+(?:text|clause)|(?:draft\s+)?clause\s+(?:says|reads)|(?:keep|preserve|retain)\s+(?:this|the following)\s+(?:text|code|date)\s+exactly)\b", re.I)

def source_review_aids(source, source_code):
    """Flag known source risks without pretending to analyse target meaning."""
    if source_code != "en":
        return ()
    warnings = []
    meanings = [meaning for pattern, meaning in _ENGLISH_IDIOMS if pattern.search(source)]
    if meanings:
        warnings.append(TranslationWarning("idiom", "Possible English idiom: " + "; ".join(meanings) + ". Confirm the intended meaning; both engines can give a literal reading."))
    if _EMBEDDED_INSTRUCTIONS.search(source):
        warnings.append(TranslationWarning("embedded_instruction", "The source contains quoted or translation-instruction wording. Confirm that the entire source, including surrounding notes, was translated. A service can treat these words as instructions and omit text."))
    return tuple(warnings)

class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def _quota_pause_seconds(value):
    """Short process-local circuit, based only on an observed HTTP/JSON 429."""
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        try:
            stamp = parsedate_to_datetime(value)
            seconds = (stamp - datetime.now(timezone.utc)).total_seconds()
        except (TypeError, ValueError, OverflowError):
            seconds = 60.0
    return min(120.0, max(1.0, seconds)) if math.isfinite(seconds) else 60.0

class HTTPTransport:
    """Hard caller deadline/cancel with four bounded, daemon network workers.

    Stalled OS DNS can outlive a request. It cannot delay UI return or app exit,
    and slots bound abandoned operations instead of creating an unbounded queue.
    """
    _default_slots = threading.BoundedSemaphore(4)
    def __init__(self, max_active=4):
        if not isinstance(max_active, int) or max_active < 1:
            raise ValueError("Network capacity must be a positive integer.")
        # Replacing settings/Translator objects does not reset the default cap.
        self._slots = self._default_slots if max_active == 4 else threading.BoundedSemaphore(max_active)
        self._cookies = CookieJar()

    def request_json(self, provider, url, payload, headers, deadline, cancel):
        return self._request(provider, url, payload, headers, deadline, cancel, text=False)

    def request_text(self, provider, url, headers, deadline, cancel):
        return self._request(provider, url, None, headers, deadline, cancel, text=True)

    def _request(self, provider, url, payload, headers, deadline, cancel, *, text):
        _state(deadline, cancel)
        if not self._slots.acquire(blocking=False):
            raise TranslationError("busy", "Previous network requests are finishing. Try again shortly.", True)
        replies = queue.Queue(maxsize=1)
        def perform():
            try:
                remaining = _state(deadline, cancel)
                body = payload if isinstance(payload, bytes) else (None if payload is None else json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
                request = Request(url, body, dict(headers), method="GET" if body is None else "POST")
                with build_opener(_NoRedirect(), HTTPCookieProcessor(self._cookies)).open(request, timeout=max(.1, min(remaining, 15.0))) as response:
                    parts, size = [], 0
                    while True:
                        _state(deadline, cancel)
                        part = response.read(65536)
                        if not part:
                            break
                        size += len(part)
                        if size > 4 * 1024 * 1024:
                            raise TranslationError("response", "Provider response exceeded the safe response limit.")
                        parts.append(part)
                    content = b"".join(parts).decode("utf-8-sig")
                    result = content if text else json.loads(content)
                replies.put((True, result))
            except HTTPError as error:
                status = error.code
                retry_after = error.headers.get("Retry-After") if error.headers else None
                error.close()
                name = PROVIDER_NAMES[provider]
                if status in (401, 403):
                    message = "rejected the key or account permission" if provider in KEY_PROVIDERS else "rejected this public-service session"
                    exc = TranslationError("credentials", f"{name} {message} (HTTP {status}).")
                elif status in (429, 456):
                    exc = TranslationError("quota", f"{name} reached an account or request limit (HTTP {status}).", status == 429, status_code=status, retry_after_seconds=_quota_pause_seconds(retry_after) if status == 429 else None)
                elif status in (400, 404, 413, 422):
                    exc = TranslationError("request", f"{name} rejected the requested language or settings (HTTP {status}).")
                else:
                    exc = TranslationError("service", f"{name} is unavailable (HTTP {status}).", status in (408, 500, 502, 503, 504, 529))
                replies.put((False, exc))
            except TranslationError as error:
                replies.put((False, error))
            except (socket.timeout, TimeoutError):
                replies.put((False, TranslationError("timeout", "The translation connection timed out. Your source is preserved.", True)))
            except (URLError, OSError):
                replies.put((False, TranslationError("network", "The translation service could not be reached. Check the connection and provider settings.", True)))
            except Exception:
                # Never leak URLs, provider response bodies, keys or source text.
                replies.put((False, TranslationError("response", "The provider returned an unreadable response.")))
            finally:
                self._slots.release()
        threading.Thread(target=perform, name="GrayFeatherHTTP", daemon=True).start()
        while True:
            remaining = _state(deadline, cancel)
            try:
                success, result = replies.get(timeout=min(.05, remaining))
            except queue.Empty:
                continue
            _state(deadline, cancel)
            if not success:
                raise result
            return result

def _endpoint(config):
    defaults = {"google_web": "https://translate.googleapis.com/translate_a/single",
                "bing_web": "https://www.bing.com/ttranslatev3",
                "mymemory": "https://api.mymemory.translated.net/get",
                "lingva": "", "libretranslate": "",
                "azure": "https://api.cognitive.microsofttranslator.com", "google": "https://translation.googleapis.com/language/translate/v2", "deepl": "https://api-free.deepl.com" if config.key.endswith(":fx") else "https://api.deepl.com"}
    if config.provider not in defaults:
        raise TranslationError("provider", "Unknown translation provider.")
    endpoint = (config.endpoint or defaults[config.provider]).rstrip("/")
    parsed = urlsplit(endpoint)
    host = parsed.hostname or ""
    try:
        valid_port = parsed.port in (None, 443)
    except ValueError:
        valid_port = False
    if config.provider in ("lingva", "libretranslate"):
        try:
            port_valid = parsed.port is None or 1 <= parsed.port <= 65535
        except ValueError:
            port_valid = False
        scheme_valid = parsed.scheme == "https" or (parsed.scheme == "http" and host in ("localhost", "127.0.0.1", "::1"))
        if not host or not port_valid or not scheme_valid or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise TranslationError("settings", "Configure this server with an HTTPS base URL (HTTP is allowed for a local loopback server).")
        suffix = "/api/v1" if config.provider == "lingva" else "/translate"
        return endpoint if parsed.path.endswith(suffix) else endpoint + suffix
    free_paths = {"google_web": ("translate.googleapis.com", "/translate_a/single"),
                  "bing_web": ("www.bing.com", "/ttranslatev3"),
                  "mymemory": ("api.mymemory.translated.net", "/get")}
    if config.provider in free_paths:
        expected_host, expected_path = free_paths[config.provider]
        if parsed.scheme != "https" or not valid_port or host != expected_host or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", expected_path):
            raise TranslationError("settings", "Use the recognised HTTPS endpoint for this public translation service.")
        return endpoint if parsed.path else endpoint + expected_path
    allowed = ((config.provider == "azure" and (host == "api.cognitive.microsofttranslator.com" or host.endswith(".cognitiveservices.azure.com"))) or (config.provider == "google" and host == "translation.googleapis.com") or (config.provider == "deepl" and host in ("api.deepl.com", "api-free.deepl.com")))
    if parsed.scheme != "https" or not valid_port or parsed.username or parsed.password or parsed.query or parsed.fragment or not allowed:
        raise TranslationError("settings", "Use an official HTTPS translation endpoint.")
    if config.provider == "azure":
        if host.endswith(".cognitiveservices.azure.com"):
            if parsed.path not in ("", "/translator/text/v3.0"):
                raise TranslationError("settings", "Use the Azure resource base URL or /translator/text/v3.0 path.")
            return endpoint + ("/translator/text/v3.0" if not parsed.path else "") + "/translate"
        if parsed.path not in ("", "/translate"):
            raise TranslationError("settings", "Use the Azure Translator base URL.")
        return endpoint if parsed.path else endpoint + "/translate"
    if config.provider == "google":
        if parsed.path != "/language/translate/v2":
            raise TranslationError("settings", "Use Google's official Cloud Translation v2 endpoint.")
        return endpoint
    if parsed.path not in ("", "/v2/translate"):
        raise TranslationError("settings", "Use the DeepL API base URL or /v2/translate endpoint.")
    return endpoint if parsed.path else endpoint + "/v2/translate"

class Translator:
    def __init__(self, configs=None, enabled_order=None, *, allow_fallback=True, transport=None, cache_size=128, cache_chars=4_000_000):
        if configs is None:
            configs = [ProviderConfig(provider) for provider in DEFAULT_PROVIDERS]
        values = list(configs.values()) if isinstance(configs, Mapping) else list(configs)
        self.configs = {config.provider: config for config in values}
        self.enabled_order = tuple(enabled_order) if enabled_order is not None else tuple(self.configs)
        self.allow_fallback, self.transport = bool(allow_fallback), transport or HTTPTransport()
        self.cache_size, self.cache_chars = max(0, cache_size), max(0, cache_chars)
        self._cache, self._cache_cost, self._lock = OrderedDict(), 0, threading.RLock()
        self._quota_until = {}
        self._bing_credentials, self._bing_until, self._bing_lock = None, 0.0, threading.Lock()
        for config in values:
            if config.provider not in PROVIDER_NAMES:
                raise TranslationError("settings", "Choose a recognised configured translation provider.")
        if len(self.enabled_order) != len(set(self.enabled_order)) or any(p not in self.configs for p in self.enabled_order):
            raise TranslationError("settings", "Enabled providers must be unique configured provider names.")
    def clear_cache(self):
        with self._lock:
            self._cache.clear()
            self._cache_cost = 0
    def _quota_remaining(self, provider):
        with self._lock:
            until = self._quota_until.get(provider, 0.0)
            remaining = until - time.monotonic()
            if remaining <= 0:
                self._quota_until.pop(provider, None)
                return 0.0
            return remaining
    def _pause_after_429(self, provider, error):
        if provider in KEY_PROVIDERS or error.status_code != 429 or error.kind != "quota":
            return
        seconds = _quota_pause_seconds(error.retry_after_seconds)
        with self._lock:
            self._quota_until[provider] = time.monotonic() + seconds
    def _cached(self, key):
        with self._lock:
            value = self._cache.pop(key, None)
            if value is None:
                return None
            if time.monotonic() - value[0] > 600:
                self._cache_cost -= len(key[0]) + len(value[1]) + len(key[4])
                return None
            self._cache[key] = value
            return value[1]
    def _remember(self, key, text):
        cost = len(key[0]) + len(text) + len(key[4])
        if self.cache_size <= 0 or cost > self.cache_chars:
            return
        with self._lock:
            old = self._cache.pop(key, None)
            if old:
                self._cache_cost -= len(key[0]) + len(old[1]) + len(key[4])
            self._cache[key] = (time.monotonic(), text)
            self._cache_cost += cost
            while len(self._cache) > self.cache_size or self._cache_cost > self.cache_chars:
                previous, old = self._cache.popitem(last=False)
                self._cache_cost -= len(previous[0]) + len(old[1]) + len(previous[4])
    def _configured(self, provider):
        config = self.configs.get(provider)
        if config is None:
            return False
        return bool(config.key.strip()) if provider in KEY_PROVIDERS else (bool(config.endpoint.strip()) if provider in ("lingva", "libretranslate") else True)
    def available_opinion_providers(self, source_code, target_code, used_providers=()):
        """Configured unused free routes; availability is never a live-health claim.

        A provider ID is distinct from a translation engine. MyMemory has mixed
        provenance, Lingva mirrors Google, and a custom server's model is not
        established by its URL. None is treated as an independent vote.
        """
        if source_code not in LANG_BY_CODE or target_code not in LANG_BY_CODE:
            raise TranslationError("language", "Choose recognised source and target languages.")
        if isinstance(used_providers, (str, bytes, Mapping)):
            raise TranslationError("input", "Used providers must be a collection of provider identities.")
        try:
            used = tuple(used_providers)
        except TypeError:
            raise TranslationError("input", "Used providers must be a collection of provider identities.") from None
        if any(not isinstance(p, str) or p not in PROVIDER_NAMES and p != "original" for p in used):
            raise TranslationError("input", "An existing opinion has an unrecognised provider identity.")
        if source_code == target_code:
            return ()
        candidates = []
        for provider in self.enabled_order:
            config = self.configs[provider]
            if provider in used or provider in KEY_PROVIDERS or config.key.strip() or not self._configured(provider) or not provider_supports(provider, source_code, target_code):
                continue
            try:
                _endpoint(config)
                if isinstance(config.timeout, bool) or not isinstance(config.timeout, (int, float)) or not math.isfinite(config.timeout) or not .1 <= config.timeout <= 120:
                    continue
            except TranslationError:
                continue
            family = PROVIDER_FAMILIES[provider]
            independent = bool(used) and all(_independent(provider, existing) for existing in used)
            if provider == "mymemory":
                provenance = "mixed_unverified"
            elif provider == "libretranslate":
                provenance = "server_model_unverified"
            elif any(PROVIDER_FAMILIES.get(existing) == family for existing in used):
                provenance = "correlated_engine"
            elif independent:
                provenance = "separate_engine"
            else:
                provenance = "known_engine"
            remaining = self._quota_remaining(provider)
            candidates.append({"provider": provider, "label": PROVIDER_NAMES[provider], "family": family,
                "provenance": provenance, "independent_of_used": independent,
                "language_approximation": bool(_route_warnings(provider, source_code, target_code)),
                "availability": "temporarily_paused" if remaining else "configured_not_probed",
                **({"retry_in_seconds": math.ceil(remaining)} if remaining else {})})
        candidates.sort(key=lambda item: (not item["independent_of_used"], item["language_approximation"]))
        return tuple(candidates)
    def additional_opinion(self, source_text, source_code, target_code, *, used_providers=(), cancel=None, deadline_seconds=30.0):
        """Translate the complete original via an unused free route on demand.

        Returns a separate result for comparison. It never alters a preceding
        result, automatically chooses a winner, or represents agreement as a
        correctness score. Failed chunks are discarded before another route.
        """
        validate_text(source_text, "Source")
        if isinstance(deadline_seconds, bool) or not isinstance(deadline_seconds, (int, float)) or not math.isfinite(deadline_seconds) or not .1 <= deadline_seconds <= 180:
            raise TranslationError("settings", "Overall deadline must be between 0.1 and 180 seconds.")
        began = time.monotonic()
        deadline = began + deadline_seconds
        _state(deadline, cancel)
        candidates = self.available_opinion_providers(source_code, target_code, used_providers)
        if not self.allow_fallback:
            candidates = candidates[:1]
        trace = []
        for item in candidates:
            provider = item["provider"]
            _state(deadline, cancel)
            try:
                text, cached = self._translate_with(provider, source_text, source_code, target_code, deadline, cancel, "", "", trace)
            except Cancelled:
                raise
            except TranslationError as error:
                trace.append({"provider": provider, "status": error.kind, "phase": "additional_opinion"})
                if error.kind == "timeout" and time.monotonic() >= deadline:
                    raise
                continue
            _state(deadline, cancel)
            warnings = list(check_translation(source_text, text, source_code, target_code))
            warnings.extend(source_review_aids(source_text, source_code))
            warnings.extend(_route_warnings(provider, source_code, target_code))
            descriptions = {
                "mixed_unverified": "MyMemory combines translation-memory matches and machine translation with mixed, unverified engine provenance. It is an additional provider opinion, not a known independent vote.",
                "server_model_unverified": "The configured LibreTranslate server's underlying model is not established. This is an additional route opinion; independence is unverified.",
                "correlated_engine": "This route uses an engine already represented in the existing opinions. Its errors can be correlated; it is not an independent vote.",
                "separate_engine": "This complete opinion uses a separate engine from the recorded opinions. Agreement cannot establish correctness.",
                "known_engine": "This complete provider output is an opinion for human comparison. Agreement cannot establish correctness.",
            }
            warnings.append(TranslationWarning("opinion_provenance", descriptions[item["provenance"]]))
            if any(step.get("phase") == "additional_opinion" for step in trace):
                warnings.append(TranslationWarning("fallback", f"The complete additional opinion came from {PROVIDER_NAMES[provider]} after another unused route failed."))
            trace.append({"provider": provider, "status": "opinion_complete", "provenance": item["provenance"],
                          "independent_of_used": item["independent_of_used"]})
            return TranslationResult(text, provider, source_code, target_code, tuple(warnings),
                int((time.monotonic()-began)*1000), trace=tuple(trace), cached=cached)
        raise TranslationError("opinion_unavailable", "No further unused free provider completed this language pair. Your existing translations and exact source remain available.")
    def _bing_session(self, deadline, cancel, headers):
        while not self._bing_lock.acquire(timeout=min(.05, _state(deadline, cancel))):
            pass
        try:
            if self._bing_credentials is not None and time.monotonic() < self._bing_until:
                return self._bing_credentials
            page = self.transport.request_text("bing_web", "https://www.bing.com/translator", headers, deadline, cancel)
            if not isinstance(page, str):
                raise TranslationError("response", "Microsoft Bing returned an unexpected public page.")
            nonce = re.search(r'params_AbusePreventionHelper\s*=\s*\[\s*(\d{1,20})\s*,\s*"([^"\r\n]{1,1024})"\s*,\s*(\d{1,12})\s*\]', page)
            ig = re.search(r'IG\s*:\s*"([A-Fa-f0-9]{8,64})"', page)
            iid = re.search(r'data-iid\s*=\s*"([A-Za-z0-9_.-]{1,128})"', page)
            if not nonce or not ig or not iid:
                raise TranslationError("service", "Microsoft Bing's public session is unavailable. Another enabled route can be used.")
            key, token, ttl = nonce.groups()
            self._bing_credentials = (key, token, ig[1], iid[1])
            self._bing_until = time.monotonic() + min(900, max(1, int(ttl) / 1000 - 30))
            return self._bing_credentials
        finally:
            self._bing_lock.release()
    def _invalidate_bing_session(self):
        with self._bing_lock:
            self._bing_credentials, self._bing_until = None, 0.0
    def _translate_with(self, provider, source, source_code, target_code, deadline, cancel, context, glossary, trace):
        config = self.configs.get(provider)
        if config is None:
            raise TranslationError("settings", "Selected translation provider is not configured.")
        if provider in KEY_PROVIDERS and not config.key.strip():
            raise TranslationError("credentials", f"Add a {PROVIDER_NAMES.get(provider, provider)} API key in Settings.")
        # Independent providers must not depend on the health of an unused
        # configuration. Validate the selected route before cache or credentials
        # leave this process; optional review failures stay isolated warnings.
        if isinstance(config.timeout, bool) or not isinstance(config.timeout, (int, float)) or not math.isfinite(config.timeout) or not .1 <= config.timeout <= 120:
            raise TranslationError("settings", "Timeout must be between 0.1 and 120 seconds.")
        endpoint = _endpoint(config)
        src, tgt = provider_language(provider, source_code), provider_language(provider, target_code, True)
        if context and provider != "deepl":
            raise TranslationError("unsupported", "Context is supported by the DeepL adapter only. Remove context or select DeepL.")
        glossary_id = glossary if glossary is not None else config.glossary_id
        if glossary_id and provider != "deepl":
            raise TranslationError("unsupported", "Hosted glossary IDs are supported by the DeepL adapter only.")
        if glossary_id and (not isinstance(glossary_id, str) or len(glossary_id) > 200 or not re.fullmatch(r"[A-Za-z0-9_-]+", glossary_id)):
            raise TranslationError("settings", "Supply a DeepL hosted glossary ID for this language pair.")
        key = (source, source_code, target_code, provider, context, glossary_id, config.endpoint, config.model_type, hashlib.sha256(config.key.encode()).digest())
        cached = self._cached(key)
        if cached is not None:
            _state(deadline, cancel)
            trace.append({"provider": provider, "status": "cached", "chunks": 0, "family": PROVIDER_FAMILIES[provider], "access": "key" if provider in KEY_PROVIDERS else "public"})
            return cached, True
        remaining = self._quota_remaining(provider)
        if remaining:
            trace.append({"provider": provider, "status": "temporarily_paused", "retry_in_seconds": math.ceil(remaining), "reason": "observed_429"})
            raise TranslationError("quota", f"{PROVIDER_NAMES[provider]} is briefly paused after HTTP 429. Retry in about {math.ceil(remaining)} seconds; another enabled route can be used.")
        chars, size = {"google_web": (1800, 2400), "bing_web": (4500, 18_000), "mymemory": (500, 500),
                       "lingva": (1200, 2400), "libretranslate": (4500, 18_000),
                       "azure": (20_000, 160_000), "google": (5_000, 60_000), "deepl": (25_000, 90_000)}[provider]
        chunks, outputs = split_text(source, max_chars=chars, max_bytes=size), []
        headers = {"Content-Type": "application/json; charset=UTF-8", "Accept": "application/json", "User-Agent": "GrayFeather/1.0"}
        for index, chunk in enumerate(chunks):
            _state(deadline, cancel)
            if not chunk.strip():
                outputs.append(chunk)
                continue
            leading, trailing = re.match(r"\s*", chunk).group(), re.search(r"\s*$", chunk).group()
            content = chunk[len(leading):len(chunk) - len(trailing) if trailing else len(chunk)]
            if provider == "google_web":
                url = endpoint + "?" + urlencode({"client": "gtx", "sl": src, "tl": tgt, "dt": "t", "ie": "UTF-8", "oe": "UTF-8", "q": content})
                payload, auth = None, headers
            elif provider == "mymemory":
                url, payload, auth = endpoint + "?" + urlencode({"q": content, "langpair": src + "|" + tgt}), None, headers
            elif provider == "lingva":
                url, payload, auth = endpoint + "/" + quote(src, safe="") + "/" + quote(tgt, safe="") + "/" + quote(content, safe=""), None, headers
            elif provider == "libretranslate":
                url, auth = endpoint, headers
                payload = {"q": content, "source": src, "target": tgt, "format": "text"}
                if config.key:
                    payload["api_key"] = config.key
            elif provider == "bing_web":
                url, payload = endpoint, None
                auth = {**headers, "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) GrayFeather/1.1", "Referer": "https://www.bing.com/translator", "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}
            elif provider == "azure":
                url = endpoint + "?" + urlencode({"api-version": "3.0", "from": src, "to": tgt, "textType": "plain"})
                payload, auth = [{"Text": content}], {**headers, "Ocp-Apim-Subscription-Key": config.key}
                if config.region:
                    auth["Ocp-Apim-Subscription-Region"] = config.region
            elif provider == "google":
                url, auth = endpoint + "?" + urlencode({"key": config.key}), headers
                payload = {"q": [content], "source": src, "target": tgt, "format": "text", "model": "nmt"}
            else:
                url, auth = endpoint, {**headers, "Authorization": "DeepL-Auth-Key " + config.key}
                payload = {"text": [content], "source_lang": src, "target_lang": tgt, "preserve_formatting": True, "model_type": config.model_type}
                if context:
                    payload["context"] = context
                if glossary_id:
                    payload["glossary_id"] = glossary_id
            if len(json.dumps(payload, ensure_ascii=False).encode()) > (128 * 1024 if provider == "deepl" else 1024 * 1024):
                raise TranslationError("input", "Source and context exceed the provider request size. Reduce context or divide the turn.")
            attempt = 0
            while True:
                begin = time.monotonic()
                try:
                    request_deadline = min(deadline, begin + config.timeout)
                    if provider == "bing_web":
                        session_key, token, ig, iid = self._bing_session(request_deadline, cancel, auth)
                        url = endpoint + "?" + urlencode({"isVertical": "1", "IG": ig, "IID": iid})
                        payload = urlencode({"fromLang": src, "text": content, "to": tgt, "token": token, "key": session_key}).encode("utf-8")
                    response = self.transport.request_json(provider, url, payload, auth, request_deadline, cancel)
                    if provider == "bing_web" and isinstance(response, dict):
                        status = response.get("statusCode")
                        if status in (401, 403):
                            raise TranslationError("credentials", "Microsoft Bing's public session expired.")
                        if status == 429:
                            raise TranslationError("quota", "Microsoft Bing reached a public-service request limit.", status_code=429)
                        raise TranslationError("request", "Microsoft Bing rejected this translation request.")
                    if provider in ("azure", "bing_web"):
                        candidates = response[0]["translations"]
                        if not isinstance(response, list) or len(candidates) != 1 or candidates[0].get("to", "").lower() != tgt.lower():
                            raise ValueError()
                        if provider == "azure" and len(response) != 1:
                            raise ValueError()
                        if provider == "bing_web" and any(not isinstance(extra, dict) or not extra or not set(extra).issubset({"inputTransliteration", "script"}) or any(not isinstance(value, str) for value in extra.values()) for extra in response[1:]):
                            raise ValueError()
                        translated = candidates[0]["text"]
                    elif provider == "google_web":
                        rows = response[0]
                        if not isinstance(response, list) or not isinstance(rows, list) or not rows:
                            raise ValueError()
                        if any(not isinstance(row, list) or len(row) < 2 or not isinstance(row[0], str) or not row[0].strip() or not isinstance(row[1], str) for row in rows):
                            raise ValueError()
                        # Public web endpoints can return a plausible partial
                        # result. Verify that every submitted source span was
                        # covered before committing any translated chunk.
                        if "".join(row[1] for row in rows) != content:
                            raise ValueError()
                        translated = "".join(row[0] for row in rows)
                    elif provider == "mymemory":
                        status = response.get("responseStatus")
                        if response.get("quotaFinished") or str(status) in ("403", "429"):
                            raise TranslationError("quota", "MyMemory's free usage limit was reached.", status_code=429 if str(status) == "429" else None)
                        if isinstance(status, bool) or str(status) != "200":
                            raise TranslationError("service", "MyMemory could not translate this request.")
                        translated = response["responseData"]["translatedText"]
                        if not isinstance(translated, str):
                            raise ValueError()
                        translated = html.unescape(translated)
                        if translated.upper().startswith("MYMEMORY WARNING:"):
                            raise TranslationError("quota", "MyMemory's free usage limit was reached.")
                    elif provider in ("lingva", "libretranslate"):
                        if response.get("error"):
                            raise TranslationError("service", f"{PROVIDER_NAMES[provider]} could not translate this request.")
                        translated = response["translation" if provider == "lingva" else "translatedText"]
                    elif provider == "google":
                        candidates = response["data"]["translations"]
                        if len(candidates) != 1:
                            raise ValueError()
                        translated = html.unescape(candidates[0]["translatedText"])
                    else:
                        candidates = response["translations"]
                        if len(candidates) != 1:
                            raise ValueError()
                        translated = candidates[0]["text"]
                    if not isinstance(translated, str) or not translated.strip():
                        raise ValueError()
                    validate_text(translated, "Provider output", MAX_TEXT_CHARS * 4)
                    _state(deadline, cancel)
                    trace.append({"provider": provider, "status": "ok", "chunk": index + 1, "chunks": len(chunks), "attempt": attempt + 1, "elapsed_ms": int((time.monotonic() - begin) * 1000), "family": PROVIDER_FAMILIES[provider], "access": "key" if provider in KEY_PROVIDERS else "public"})
                    outputs.append(leading + translated + trailing)
                    break
                except (KeyError, IndexError, TypeError, ValueError, AttributeError):
                    trace.append({"provider": provider, "status": "response", "phase": "parse", "chunk": index + 1})
                    raise TranslationError("response", f"{PROVIDER_NAMES[provider]} returned an incomplete or unexpected response.") from None
                except TranslationError as error:
                    self._pause_after_429(provider, error)
                    trace.append({"provider": provider, "status": error.kind, "chunk": index + 1, "attempt": attempt + 1})
                    if provider == "bing_web" and error.kind == "credentials" and attempt < 1:
                        self._invalidate_bing_session()
                    elif isinstance(error, Cancelled) or not error.retryable or attempt >= 1 or error.kind == "quota" or _state(deadline, cancel) < 1:
                        raise
                    attempt += 1
                    if cancel is not None:
                        if cancel.wait(.2):
                            raise Cancelled()
                    else:
                        time.sleep(.2)
        output = "".join(outputs)
        validate_text(output, "Complete provider output", MAX_TEXT_CHARS * 4)
        self._remember(key, output)
        return output, False
    def translate(self, source_text, source_code, target_code, *, provider=None, cancel=None, glossary=None, context="", independent_review=False, backtranslate=False, deadline_seconds=60.0):
        validate_text(source_text, "Source")
        validate_text(context, "Context", MAX_CONTEXT_CHARS, True)
        if source_code not in LANG_BY_CODE or target_code not in LANG_BY_CODE:
            raise TranslationError("language", "Choose recognised source and target languages.")
        if not math.isfinite(deadline_seconds) or not .1 <= deadline_seconds <= 180:
            raise TranslationError("settings", "Overall deadline must be between 0.1 and 180 seconds.")
        begin = time.monotonic()
        deadline = begin + deadline_seconds
        _state(deadline, cancel)
        if source_code == target_code:
            return TranslationResult(source_text, "original", source_code, target_code, (), 0, trace=({"provider": "original", "status": "same_language"},))
        available = [p for p in self.enabled_order if provider_supports(p, source_code, target_code)]
        # Prefer a distinct language identity to a labelled approximation.
        # In particular, Bing supplies Dari, while Google uses Persian for it.
        if provider is None:
            available.sort(key=lambda p: bool(_route_warnings(p, source_code, target_code)))
            # A scoped, user-observed English/Persian preference. This is not a
            # universal quality score, and an explicit selection always wins.
            # Swap only these free routes, preserving other configured positions.
            if {source_code, target_code} == {"en", "fa"} and "google_web" in available and "bing_web" in available:
                google_index, bing_index = available.index("google_web"), available.index("bing_web")
                if bing_index > google_index:
                    available[google_index], available[bing_index] = available[bing_index], available[google_index]
        order = tuple(([provider] + [p for p in available if p != provider]) if provider else available)
        if not order:
            if self.enabled_order:
                raise TranslationError("unsupported", "No enabled route supports this language pair. Choose another translation service in Settings.")
            raise TranslationError("settings", "Enable a translation route in Settings. Free routes do not require a key.")
        if provider is not None and provider not in self.configs:
            raise TranslationError("settings", "Selected provider is not configured.")
        if not self.allow_fallback:
            order = order[:1]
        trace, selected, last_error, cached = [], "", None, False
        for candidate in order:
            _state(deadline, cancel)
            try:
                output, cached = self._translate_with(candidate, source_text, source_code, target_code, deadline, cancel, context, glossary, trace)
                selected = candidate
                break
            except Cancelled:
                raise
            except TranslationError as error:
                last_error = error
                trace.append({"provider": candidate, "status": error.kind, "phase": "primary"})
                if error.kind == "timeout" and time.monotonic() >= deadline:
                    raise
        if not selected:
            raise last_error
        warnings = []
        if trace and trace[0].get("provider") != selected:
            warnings.append(TranslationWarning("fallback", f"The complete turn was translated by {PROVIDER_NAMES[selected]} after an earlier enabled route failed."))
        review_text = review_provider = reverse = reverse_provider = ""
        if independent_review:
            candidates = [p for p in self.enabled_order if _independent(selected, p) and self._configured(p) and provider_supports(p, source_code, target_code)]
            if not candidates:
                warnings.append(TranslationWarning("review_unavailable", "A separate translation engine is unavailable for this pair. Mirrors and MyMemory are not counted as independent review."))
            else:
                try:
                    second = candidates[0]
                    review_text, review_cached = self._translate_with(second, source_text, source_code, target_code, deadline, cancel, context if second == "deepl" else "", glossary if second == "deepl" else "", trace)
                    review_provider = second
                    currency_selection = _currency_quality_selection(source_text, output, review_text)
                    identity_selection = _identity_quality_selection(source_text, output, review_text)
                    if {selected, review_provider} == {"google_web", "bing_web"} and not context and not glossary and (currency_selection or identity_selection):
                        output, review_text = review_text, output
                        selected, review_provider = review_provider, selected
                        cached = review_cached
                        reason = "currency_identity" if currency_selection else ("address_identity" if "identifiers" in identity_selection else "reference_identity")
                        detail = "an explicit currency identity" if currency_selection else ("an email address or web address" if "identifiers" in identity_selection else "an exact reference or identifier")
                        trace.append({"provider": selected, "status": "quality_selected", "replaced_provider": review_provider, "reason": reason})
                        warnings.append(TranslationWarning("quality_selection", f"{PROVIDER_NAMES[selected]} was selected because {PROVIDER_NAMES[review_provider]} changed {detail}. The original output remains as the alternative for review."))
                    warnings.append(TranslationWarning("independent_review", "A second provider is available for human comparison. Agreement cannot establish correctness."))
                    warnings.extend(TranslationWarning(w.code, "Alternative translation: " + w.message, w.source_values, w.target_values) for w in _route_warnings(review_provider, source_code, target_code))
                    for warning in check_translation(source_text, review_text, source_code, target_code):
                        if warning.code in ("numbers", "identifiers", "references", "currencies", "units", "unchanged"):
                            warnings.append(TranslationWarning("review_" + warning.code, "Alternative translation: " + warning.message, warning.source_values, warning.target_values))
                    if context or glossary:
                        warnings.append(TranslationWarning("review_conditions", "The alternative uses only its own supported context or glossary; review conditions can differ."))
                except Cancelled:
                    raise
                except TranslationError:
                    warnings.append(TranslationWarning("review_failed", "Independent review could not finish. The primary translation remains available."))
        warnings[0:0] = list(check_translation(source_text, output, source_code, target_code)) + _route_warnings(selected, source_code, target_code) + list(source_review_aids(source_text, source_code))
        if backtranslate:
            candidates = [p for p in self.enabled_order if _independent(selected, p) and self._configured(p) and provider_supports(p, target_code, source_code) and (selected in KEY_PROVIDERS or p not in KEY_PROVIDERS)]
            if self._configured(selected) and provider_supports(selected, target_code, source_code):
                candidates.append(selected)
            if not self.allow_fallback:
                candidates = candidates[:1]
            for candidate in candidates:
                try:
                    reverse, _ = self._translate_with(candidate, output, target_code, source_code, deadline, cancel, "", "", trace)
                    reverse_provider = candidate
                    correlation = "a separate translation engine" if _independent(reverse_provider, selected) else "the same engine or an unverified source, with potentially correlated errors"
                    warnings.append(TranslationWarning("backtranslation", f"Backtranslation uses {correlation}. A similar round trip cannot establish accuracy."))
                    break
                except Cancelled:
                    raise
                except TranslationError as error:
                    trace.append({"provider": candidate, "status": error.kind, "phase": "backtranslation"})
            if not reverse_provider:
                warnings.append(TranslationWarning("backtranslation_failed", "Backtranslation could not finish. The primary translation remains available."))
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        return TranslationResult(output, selected, source_code, target_code, tuple(warnings), int((time.monotonic() - begin) * 1000), review_text, review_provider, reverse, reverse_provider, tuple(trace), cached)

def _utc():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")
def _json(value):
    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    except (TypeError, ValueError) as error:
        raise StorageError("Metadata must contain valid JSON values.") from error
def atomic_write(path, content):
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix="." + destination.name + ".", suffix=".tmp", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content.encode("utf-8") if isinstance(content, str) else content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
def _safe_csv(value):
    text = str(value if value is not None else "")
    if text.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")):
        return "'" + text
    return text

class _ClosingConnection:
    def __init__(self, connection):
        self.connection = connection
    def __enter__(self):
        self.connection.__enter__()
        return self.connection
    def __exit__(self, kind, value, traceback):
        try:
            return self.connection.__exit__(kind, value, traceback)
        finally:
            self.connection.close()

class Store:
    """SQLite FULL synchronous transactions with originals and turn revisions.

    DELETE journalling avoids persistent WAL/SHM sidecar files. Every connection
    closes after its operation. Whole-snapshot saves and drafts are atomic.
    """
    def __init__(self, path):
        self.path, self._lock = Path(path), threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self._connection() as connection:
                version = connection.execute("PRAGMA user_version").fetchone()[0]
                if version not in (0, 1):
                    raise StorageError("This history needs a newer Gray Feather version.")
                if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise StorageError("History needs recovery. Preserve the file and restore a verified backup.")
                connection.executescript("""
                CREATE TABLE IF NOT EXISTS conversations(id TEXT PRIMARY KEY,title TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,revision INTEGER NOT NULL DEFAULT 1,metadata TEXT NOT NULL DEFAULT '{}');
                CREATE TABLE IF NOT EXISTS turns(id TEXT PRIMARY KEY,conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,seq INTEGER NOT NULL,speaker TEXT NOT NULL,source_lang TEXT NOT NULL,target_lang TEXT NOT NULL,raw_source TEXT NOT NULL,reviewed_source TEXT NOT NULL,translated_text TEXT NOT NULL,provider TEXT NOT NULL,warnings TEXT NOT NULL,metadata TEXT NOT NULL,revision INTEGER NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,deleted INTEGER NOT NULL DEFAULT 0,UNIQUE(conversation_id,seq));
                CREATE TABLE IF NOT EXISTS turn_revisions(turn_id TEXT NOT NULL REFERENCES turns(id) ON DELETE CASCADE,revision INTEGER NOT NULL,saved_at TEXT NOT NULL,snapshot TEXT NOT NULL,PRIMARY KEY(turn_id,revision));
                CREATE INDEX IF NOT EXISTS conversations_updated ON conversations(updated_at DESC);
                CREATE INDEX IF NOT EXISTS turns_conversation ON turns(conversation_id,seq);
                PRAGMA user_version=1;
                """)
                if "deleted" not in {row[1] for row in connection.execute("PRAGMA table_info(turns)")}:
                    connection.execute("ALTER TABLE turns ADD COLUMN deleted INTEGER NOT NULL DEFAULT 0")
        except sqlite3.Error as error:
            raise StorageError("Local history could not be opened. Check the data folder and preserve the database for recovery.") from error
    def _connection(self, write=False):
        connection = sqlite3.connect(self.path, timeout=5.0)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA journal_mode=DELETE")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("PRAGMA busy_timeout=5000")
            if write:
                connection.execute("BEGIN IMMEDIATE")
        except Exception:
            connection.close()
            raise
        return _ClosingConnection(connection)
    @staticmethod
    def _decode(row):
        data = dict(row)
        for key in ("metadata", "warnings"):
            if key in data:
                data[key] = json.loads(data[key])
        return data
    def _get(self, connection, identity):
        row = connection.execute("SELECT * FROM conversations WHERE id=?", (identity,)).fetchone()
        if row is None:
            raise StorageError("This conversation no longer exists.")
        data = self._decode(row)
        data["turns"] = [self._decode(turn) for turn in connection.execute("SELECT * FROM turns WHERE conversation_id=? AND deleted=0 ORDER BY seq", (identity,))]
        data["drafts"] = data["metadata"].get("drafts", {"1": "", "2": ""})
        return data
    def new_conversation(self, title="New conversation", *, metadata=None):
        validate_text(title, "Title", 300)
        identity, stamp = uuid.uuid4().hex, _utc()
        with self._lock, self._connection(write=True) as connection:
            connection.execute("INSERT INTO conversations(id,title,created_at,updated_at,metadata) VALUES(?,?,?,?,?)", (identity, title, stamp, stamp, _json(metadata or {})))
            return self._get(connection, identity)
    def get_conversation(self, conversation_id):
        with self._lock, self._connection() as connection:
            return self._get(connection, conversation_id)
    def list_conversations(self, query="", limit=100):
        if not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise StorageError("History limit must be between 1 and 1000.")
        validate_text(query, "Search", 1000, True)
        with self._lock, self._connection() as connection:
            if query:
                escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                rows = connection.execute("""SELECT c.*,(SELECT COUNT(*) FROM turns t WHERE t.conversation_id=c.id) AS turn_count FROM conversations c WHERE c.title LIKE ? ESCAPE '\\' OR EXISTS(SELECT 1 FROM turns t WHERE t.conversation_id=c.id AND (t.raw_source LIKE ? ESCAPE '\\' OR t.reviewed_source LIKE ? ESCAPE '\\' OR t.translated_text LIKE ? ESCAPE '\\')) ORDER BY c.updated_at DESC,c.id LIMIT ?""", ("%" + escaped + "%",) * 4 + (limit,)).fetchall()
            else:
                rows = connection.execute("SELECT c.*,(SELECT COUNT(*) FROM turns t WHERE t.conversation_id=c.id) AS turn_count FROM conversations c ORDER BY c.updated_at DESC,c.id LIMIT ?", (limit,)).fetchall()
            return [self._decode(row) for row in rows]
    def update_conversation(self, conversation_id, title, *, expected_revision=None, metadata=None):
        validate_text(title, "Title", 300)
        with self._lock, self._connection(write=True) as connection:
            existing = self._get(connection, conversation_id)
            if expected_revision is not None and existing["revision"] != expected_revision:
                raise RevisionConflict("Conversation changed. Reload before saving.")
            connection.execute("UPDATE conversations SET title=?,metadata=?,updated_at=?,revision=revision+1 WHERE id=?", (title, _json(metadata if metadata is not None else existing["metadata"]), _utc(), conversation_id))
            return self._get(connection, conversation_id)
    def save_turn(self, conversation_id, source_lang, target_lang, raw_source, translated_text="", provider="", *, reviewed_source=None, turn_id=None, expected_revision=None, warnings=(), metadata=None, speaker="1", seq=None):
        with self._lock, self._connection(write=True) as connection:
            return self._save_turn(connection, conversation_id, source_lang, target_lang, raw_source, translated_text, provider, reviewed_source=reviewed_source, turn_id=turn_id, expected_revision=expected_revision, warnings=warnings, metadata=metadata, speaker=speaker, seq=seq)
    def _save_turn(self, connection, conversation_id, source_lang, target_lang, raw_source, translated_text="", provider="", *, reviewed_source=None, turn_id=None, expected_revision=None, warnings=(), metadata=None, speaker="1", seq=None):
        if source_lang not in LANG_BY_CODE or target_lang not in LANG_BY_CODE or str(speaker) not in ("1", "2"):
            raise StorageError("A turn needs recognised languages and speaker 1 or 2.")
        validate_text(raw_source, "Original source", allow_empty=True)
        reviewed = raw_source if reviewed_source is None else validate_text(reviewed_source, "Reviewed source", allow_empty=True)
        validate_text(translated_text, "Translated text", MAX_TEXT_CHARS * 4, True)
        validate_text(provider, "Provider", 100, True)
        warning_data = [value.to_dict() if isinstance(value, TranslationWarning) else value for value in warnings]
        warning_json, metadata_json = _json(warning_data), _json(metadata or {})
        if len(warning_json) + len(metadata_json) > 2_000_000:
            raise StorageError("Turn metadata exceeds the storage limit.")
        if connection.execute("SELECT id FROM conversations WHERE id=?", (conversation_id,)).fetchone() is None:
            raise StorageError("This conversation no longer exists.")
        if turn_id:
            validate_text(turn_id, "Turn identity", 100)
        existing = connection.execute("SELECT * FROM turns WHERE id=?", (turn_id,)).fetchone() if turn_id else None
        stamp = _utc()
        if existing:
            if existing["conversation_id"] != conversation_id:
                raise StorageError("A turn cannot move between conversations.")
            if expected_revision is not None and existing["revision"] != expected_revision:
                raise RevisionConflict("Turn changed. Reload its latest revision before saving.")
            if raw_source != existing["raw_source"]:
                raise StorageError("Original source is immutable. Save corrections in reviewed_source.")
            if seq is not None and seq != existing["seq"]:
                raise StorageError("Turn order is immutable.")
            comparable = {"source_lang": source_lang, "target_lang": target_lang, "reviewed_source": reviewed, "translated_text": translated_text, "provider": provider, "warnings": warning_json, "metadata": metadata_json, "speaker": str(speaker)}
            if not existing["deleted"] and all(existing[key] == value for key, value in comparable.items()):
                return self._decode(existing)
            revision = existing["revision"] + 1
            connection.execute("UPDATE turns SET source_lang=?,target_lang=?,reviewed_source=?,translated_text=?,provider=?,warnings=?,metadata=?,revision=?,updated_at=?,speaker=?,deleted=0 WHERE id=?", (source_lang, target_lang, reviewed, translated_text, provider, warning_json, metadata_json, revision, stamp, str(speaker), turn_id))
        else:
            if expected_revision not in (None, 0):
                raise RevisionConflict("This turn no longer exists. Reload before saving.")
            turn_id = turn_id or uuid.uuid4().hex
            if seq is None:
                seq = connection.execute("SELECT COALESCE(MAX(seq),0)+1 FROM turns WHERE conversation_id=?", (conversation_id,)).fetchone()[0]
            if not isinstance(seq, int) or isinstance(seq, bool) or seq < 1:
                raise StorageError("Turn order must be a positive integer.")
            revision = 1
            connection.execute("INSERT INTO turns VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (turn_id, conversation_id, seq, str(speaker), source_lang, target_lang, raw_source, reviewed, translated_text, provider, warning_json, metadata_json, revision, stamp, stamp, 0))
        turn = self._decode(connection.execute("SELECT * FROM turns WHERE id=?", (turn_id,)).fetchone())
        connection.execute("INSERT INTO turn_revisions VALUES(?,?,?,?)", (turn_id, revision, stamp, _json(turn)))
        connection.execute("UPDATE conversations SET updated_at=?,revision=revision+1 WHERE id=?", (stamp, conversation_id))
        return turn
    def save_conversation(self, data, turns=None, *, title=None, expected_revision=None, metadata=None):
        """Atomic snapshot save; omitted existing turns are retained for safety.

        Accepts a conversation dict (GUI contract), or id + turns. All submitted
        revisions must match. Drafts are persisted in conversation metadata.
        """
        deletions = ()
        dictionary_save = isinstance(data, Mapping)
        if isinstance(data, Mapping):
            identity, turns = data["id"], data.get("turns", ())
            title = data.get("title", title)
            expected_revision = data.get("revision", expected_revision)
            metadata = dict(data.get("metadata", metadata or {}))
            deletions = data.get("deleted_turn_ids", ())
            if not isinstance(deletions, (list, tuple)) or any(not isinstance(value, str) for value in deletions):
                raise StorageError("Deleted turns must be an explicit list of identities.")
            if "drafts" in data:
                drafts = data["drafts"]
                if not isinstance(drafts, dict) or set(drafts) - {"1", "2"}:
                    raise StorageError("Drafts need speaker keys 1 and 2.")
                metadata["drafts"] = {speaker: validate_text(drafts.get(speaker, ""), "Draft", allow_empty=True) for speaker in ("1", "2")}
        else:
            identity = data
            turns = turns or ()
        if title is not None:
            validate_text(title, "Title", 300)
        validate_text(identity, "Conversation identity", 100)
        with self._lock, self._connection(write=True) as connection:
            found = connection.execute("SELECT id FROM conversations WHERE id=?", (identity,)).fetchone()
            if found is None:
                if not dictionary_save or expected_revision not in (None, 0):
                    raise RevisionConflict("This conversation no longer exists. Reload before saving.")
                stamp = _utc()
                connection.execute("INSERT INTO conversations(id,title,created_at,updated_at,metadata) VALUES(?,?,?,?,?)", (identity, title or "New conversation", stamp, stamp, _json(metadata or {})))
                expected_revision = None
            existing = self._get(connection, identity)
            if expected_revision is not None and existing["revision"] != expected_revision:
                raise RevisionConflict("Conversation changed. Reload before saving.")
            for turn in turns:
                values = {key: value for key, value in turn.items() if key in {"source_lang", "target_lang", "raw_source", "translated_text", "provider", "reviewed_source", "warnings", "metadata", "speaker", "seq"}}
                if turn.get("id"):
                    values["turn_id"] = turn["id"]
                if "revision" in turn:
                    values["expected_revision"] = turn["revision"]
                self._save_turn(connection, identity, **values)
            submitted_ids = {turn.get("id") for turn in turns}
            if submitted_ids & set(deletions):
                raise StorageError("A turn cannot be saved and deleted in the same snapshot.")
            for turn_id in set(deletions):
                row = connection.execute("SELECT * FROM turns WHERE id=? AND conversation_id=?", (turn_id, identity)).fetchone()
                if row is None:
                    raise StorageError("A deleted turn must belong to this conversation.")
                if not row["deleted"]:
                    stamp, revision = _utc(), row["revision"] + 1
                    connection.execute("UPDATE turns SET deleted=1,revision=?,updated_at=? WHERE id=?", (revision, stamp, turn_id))
                    snapshot = self._decode(connection.execute("SELECT * FROM turns WHERE id=?", (turn_id,)).fetchone())
                    connection.execute("INSERT INTO turn_revisions VALUES(?,?,?,?)", (turn_id, revision, stamp, _json(snapshot)))
                    connection.execute("UPDATE conversations SET updated_at=?,revision=revision+1 WHERE id=?", (stamp, identity))
            target_title = title if title is not None else existing["title"]
            target_meta = _json(metadata if metadata is not None else existing["metadata"])
            if target_title != existing["title"] or target_meta != _json(existing["metadata"]):
                connection.execute("UPDATE conversations SET title=?,metadata=?,updated_at=?,revision=revision+1 WHERE id=?", (target_title, target_meta, _utc(), identity))
            return self._get(connection, identity)
    def get_revisions(self, turn_id):
        with self._lock, self._connection() as connection:
            return [json.loads(row[0]) for row in connection.execute("SELECT snapshot FROM turn_revisions WHERE turn_id=? ORDER BY revision", (turn_id,))]
    def delete_conversation(self, conversation_id, *, expected_revision=None):
        with self._lock, self._connection(write=True) as connection:
            existing = self._get(connection, conversation_id)
            if expected_revision is not None and existing["revision"] != expected_revision:
                raise RevisionConflict("Conversation changed. Reload before deleting.")
            connection.execute("DELETE FROM conversations WHERE id=?", (conversation_id,))
    def export(self, conversation_id, format="txt", destination=None, *, snapshot=None):
        conversation = self.get_conversation(conversation_id) if snapshot is None else snapshot
        if snapshot is not None:
            if not isinstance(snapshot, Mapping) or snapshot.get('id') != conversation_id:
                raise StorageError('The export snapshot does not match this conversation.')
            validate_text(snapshot['title'], 'Export title', 300)
            for turn in snapshot.get('turns', ()):
                if turn['source_lang'] not in LANG_BY_CODE or turn['target_lang'] not in LANG_BY_CODE:
                    raise StorageError('The export contains an unknown language.')
                for key in ('raw_source', 'reviewed_source', 'translated_text'):
                    validate_text(turn[key], 'Export text', MAX_TEXT_CHARS * 4, True)
        format = format.lower()
        if format == "json":
            text = json.dumps({"format": "gray-feather-conversation", "version": 1, "exported_at": _utc(), "conversation": conversation}, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
        elif format == "txt":
            lines = [conversation["title"], "Gray Feather transcript", "", "Review aids are limited checks, not translation confidence.", ""]
            for turn in conversation["turns"]:
                lines += [f"{turn['seq']}. Speaker {turn['speaker']} · {LANG_BY_CODE[turn['source_lang']].name} → {LANG_BY_CODE[turn['target_lang']].name}", "Original: " + turn["raw_source"]]
                if turn["reviewed_source"] != turn["raw_source"]:
                    lines.append("Reviewed source: " + turn["reviewed_source"])
                lines += ["Translation: " + turn["translated_text"], "Provider: " + (PROVIDER_NAMES.get(turn["provider"], turn["provider"]) or "Pending")]
                for warning in turn["warnings"]:
                    lines.append("Review: " + (warning.get("message", "") if isinstance(warning, dict) else str(warning)))
                lines.append("")
            text = "\n".join(lines)
        elif format == "csv":
            stream = io.StringIO(newline="")
            writer = csv.writer(stream)
            keys = ("seq", "speaker", "source_lang", "target_lang", "raw_source", "reviewed_source", "translated_text", "provider", "revision", "warnings")
            writer.writerow(keys)
            for turn in conversation["turns"]:
                writer.writerow(_safe_csv(_json(turn[key]) if key == "warnings" else turn[key]) for key in keys)
            text = stream.getvalue()
        else:
            raise StorageError("Choose TXT, CSV or JSON export.")
        if destination is not None:
            if Path(destination).resolve() == self.path.resolve():
                raise StorageError("An export cannot overwrite the history database.")
            atomic_write(destination, ("\ufeff" if format == "csv" else "") + text)
        return text
    def backup(self, destination):
        path = Path(destination)
        if path.resolve() == self.path.resolve():
            raise StorageError("Backup must use a different path from the active database.")
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix="." + path.name + ".", suffix=".tmp", dir=path.parent)
        os.close(descriptor)
        try:
            with self._lock, self._connection() as source:
                target = sqlite3.connect(temporary)
                try:
                    source.backup(target)
                    if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                        raise StorageError("Backup did not pass its integrity check.")
                finally:
                    target.close()
            with open(temporary, "rb+") as stream:
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            return path
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    def diagnostics(self):
        with self._lock, self._connection() as connection:
            return {"schema": connection.execute("PRAGMA user_version").fetchone()[0], "integrity": connection.execute("PRAGMA quick_check").fetchone()[0], "conversations": connection.execute("SELECT COUNT(*) FROM conversations").fetchone()[0], "turns": connection.execute("SELECT COUNT(*) FROM turns").fetchone()[0], "sqlite": sqlite3.sqlite_version, "journal_mode": connection.execute("PRAGMA journal_mode").fetchone()[0]}
