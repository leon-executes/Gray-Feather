"""Safe Speech local filter, recovered from Gray Feather web v19C.
Parham (Leon) Faraji. PolyForm-Noncommercial-1.0.0.
Original history is preserved; only presentation and playback are masked.
No network triage, inferred sentence replacement or universal filtering claim.
"""
import re, unicodedata
from typing import Any, Dict, List, Tuple
_FILTER_TOKEN_SEP = r"[\W_]*"
CONTENT_FILTER_DEFAULT = True
CONTENT_FILTER_MAX_CHARS = 200000
CONTENT_FILTER_PLACEHOLDER_DISPLAY = '[filtered]'
CONTENT_FILTER_PLACEHOLDER_TTS = '…'
def clamp_text(text, limit):
    return str(text or '')
CONTENT_FILTER_REGEX_SPECS: List[Tuple[str, List[str]]] = [
    ("slur", [
        r"(?<![A-Za-z0-9])n"+_FILTER_TOKEN_SEP+r"[i1!]"+_FILTER_TOKEN_SEP+r"[gq]"+_FILTER_TOKEN_SEP+r"[gq]"+_FILTER_TOKEN_SEP+r"(?:[e3]"+_FILTER_TOKEN_SEP+r"r|a)(?![A-Za-z0-9])",
        r"(?<![A-Za-z0-9])f"+_FILTER_TOKEN_SEP+r"[a@4]"+_FILTER_TOKEN_SEP+r"g"+_FILTER_TOKEN_SEP+r"g?"+_FILTER_TOKEN_SEP+r"[o0]"+_FILTER_TOKEN_SEP+r"t(?![A-Za-z0-9])",
        r"(?<![A-Za-z0-9])k"+_FILTER_TOKEN_SEP+r"[i1!]"+_FILTER_TOKEN_SEP+r"k"+_FILTER_TOKEN_SEP+r"[e3](?![A-Za-z0-9])",
        r"(?<![A-Za-z0-9])ch"+_FILTER_TOKEN_SEP+r"[i1!]"+_FILTER_TOKEN_SEP+r"nk(?![A-Za-z0-9])",
        r"(?<![A-Za-z0-9])g"+_FILTER_TOKEN_SEP+r"[o0]"+_FILTER_TOKEN_SEP+r"[o0]"+_FILTER_TOKEN_SEP+r"k(?![A-Za-z0-9])",
        r"(?<![A-Za-z0-9])sp"+_FILTER_TOKEN_SEP+r"[i1!]"+_FILTER_TOKEN_SEP+r"c(?![A-Za-z0-9])",
        r"(?<![A-Za-z0-9])w"+_FILTER_TOKEN_SEP+r"[e3]"+_FILTER_TOKEN_SEP+r"tb"+_FILTER_TOKEN_SEP+r"[a@4]"+_FILTER_TOKEN_SEP+r"ck(?![A-Za-z0-9])",
        r"(?<![A-Za-z0-9])r"+_FILTER_TOKEN_SEP+r"[e3]"+_FILTER_TOKEN_SEP+r"t"+_FILTER_TOKEN_SEP+r"[a@4]"+_FILTER_TOKEN_SEP+r"rd(?:ed)?(?![A-Za-z0-9])",
        r"(?<![A-Za-z0-9])tr"+_FILTER_TOKEN_SEP+r"[a@4]"+_FILTER_TOKEN_SEP+r"nn"+_FILTER_TOKEN_SEP+r"y(?![A-Za-z0-9])",
    ]),
    ("profanity", [
        r"(?<![A-Za-z0-9])f"+_FILTER_TOKEN_SEP+r"[u*@]"+_FILTER_TOKEN_SEP+r"c"+_FILTER_TOKEN_SEP+r"k(?:"+_FILTER_TOKEN_SEP+r"(?:er|ing|ed))?(?![A-Za-z0-9])",
        r"(?<![A-Za-z0-9])f[\W_]*[u*@*]+[\W_]*(?:c[\W_]*k)?[\W_]*(?:er|ing|ed)?(?![A-Za-z0-9])",
        r"(?<![A-Za-z0-9])sh"+_FILTER_TOKEN_SEP+r"[i1!*]"+_FILTER_TOKEN_SEP+r"t(?:"+_FILTER_TOKEN_SEP+r"(?:ty|head))?(?![A-Za-z0-9])",
        r"(?<![A-Za-z0-9])b"+_FILTER_TOKEN_SEP+r"[i1!]"+_FILTER_TOKEN_SEP+r"t"+_FILTER_TOKEN_SEP+r"ch(?:es)?(?![A-Za-z0-9])",
        r"(?<![A-Za-z0-9])c"+_FILTER_TOKEN_SEP+r"[u*]"+_FILTER_TOKEN_SEP+r"n"+_FILTER_TOKEN_SEP+r"t(?![A-Za-z0-9])",
        r"(?<![A-Za-z0-9])[a@4]"+_FILTER_TOKEN_SEP+r"ss"+_FILTER_TOKEN_SEP+r"h"+_FILTER_TOKEN_SEP+r"[o0]"+_FILTER_TOKEN_SEP+r"l"+_FILTER_TOKEN_SEP+r"[e3](?![A-Za-z0-9])",
        r"(?<![A-Za-z0-9])b"+_FILTER_TOKEN_SEP+r"[a@4]"+_FILTER_TOKEN_SEP+r"st"+_FILTER_TOKEN_SEP+r"[a@4]"+_FILTER_TOKEN_SEP+r"rd(?![A-Za-z0-9])",
        r"(?<![A-Za-z0-9])d"+_FILTER_TOKEN_SEP+r"[a@4]"+_FILTER_TOKEN_SEP+r"mn(?:ed)?(?![A-Za-z0-9])",
        r"(?<![A-Za-z0-9])cr"+_FILTER_TOKEN_SEP+r"[a@4]"+_FILTER_TOKEN_SEP+r"p(?![A-Za-z0-9])",
        r"(?<![A-Za-z0-9])w"+_FILTER_TOKEN_SEP+r"[a@4]"+_FILTER_TOKEN_SEP+r"nk(?:er|ing)?(?![A-Za-z0-9])",
        r"(?<![A-Za-z0-9])tw"+_FILTER_TOKEN_SEP+r"[a@4]"+_FILTER_TOKEN_SEP+r"t(?![A-Za-z0-9])",
        r"(?<![A-Za-z0-9])m"+_FILTER_TOKEN_SEP+r"[o0]"+_FILTER_TOKEN_SEP+r"th"+_FILTER_TOKEN_SEP+r"[e3]"+_FILTER_TOKEN_SEP+r"rf"+_FILTER_TOKEN_SEP+r"[u*]"+_FILTER_TOKEN_SEP+r"ck(?:er|ing)?(?![A-Za-z0-9])",
        r"(?<![A-Za-z0-9])c"+_FILTER_TOKEN_SEP+r"[o0]"+_FILTER_TOKEN_SEP+r"cks"+_FILTER_TOKEN_SEP+r"[u*]"+_FILTER_TOKEN_SEP+r"ck(?:er|ing)?(?![A-Za-z0-9])",
        r"(?<![A-Za-z0-9])d"+_FILTER_TOKEN_SEP+r"[i1!]"+_FILTER_TOKEN_SEP+r"ck(?:head)?(?![A-Za-z0-9])",
        r"(?<![A-Za-z0-9])p"+_FILTER_TOKEN_SEP+r"[u*]"+_FILTER_TOKEN_SEP+r"ss"+_FILTER_TOKEN_SEP+r"y(?![A-Za-z0-9])",
        r"(?<![A-Za-z0-9])wh"+_FILTER_TOKEN_SEP+r"[o0]"+_FILTER_TOKEN_SEP+r"r"+_FILTER_TOKEN_SEP+r"[e3](?![A-Za-z0-9])",
        r"(?<![A-Za-z0-9])sl"+_FILTER_TOKEN_SEP+r"[u*]"+_FILTER_TOKEN_SEP+r"t(?![A-Za-z0-9])",
        r"(?<![A-Za-z0-9])pr"+_FILTER_TOKEN_SEP+r"[i1!]"+_FILTER_TOKEN_SEP+r"ck(?![A-Za-z0-9])",
        r"(?<![A-Za-z0-9])bl"+_FILTER_TOKEN_SEP+r"[o0]"+_FILTER_TOKEN_SEP+r"wj"+_FILTER_TOKEN_SEP+r"[o0]"+_FILTER_TOKEN_SEP+r"b(?![A-Za-z0-9])",
    ]),
]

# Literal multilingual terms. This list is intentionally PG-aggressive in v8.
# It includes common forms in Arabic-script Persian/Urdu/Punjabi, Gurmukhi Punjabi,
# romanized South Asian profanity, and major European languages. It avoids neutral
# clinical/safeguarding words; filter-off exists for verbatim evidence/safeguarding sessions.
CONTENT_FILTER_LITERAL_TERMS: List[Tuple[str, List[str]]] = [
    ("slur", [
        "عبيد", "زنجي", "كافر", "کافر", "حرامزاده", "حرامزاده‌ها", "حرامی", "چمار", "چوہڑا", "چوڑا", "چمار", "چمارا",
        "haramzada", "haramzadeh", "ibne haram", "kutti kaum",
    ]),
    ("profanity", [
        # Arabic / Persian / Kurdish / Urdu / Shahmukhi Punjabi core terms and variants
        "كس", "كسمك", "کسمک", "کص", "كص", "کصکش", "كسكش", "کوسکش", "کسکش", "کوس", "کس", "کسخل", "کصخل",
        "كیر", "کیر", "کیرم", "کیرتو", "کیرت", "کونی", "کون", "كون", "گوه", "گُه", "گه", "گوز", "خرا", "خراء", "زفت",
        "جنده", "جندہ", "مادرجنده", "مادر جنده", "مادرجندہ", "مادر جندہ", "جاکش", "جاكش", "لانت", "لعنتی",
        "چوت", "چوتیا", "چوتیئے", "چود", "چودنا", "چد", "چدنا", "چودو", "چودی", "مادرچود", "مادر چود",
        "بہنچود", "بہن چود", "بھنچود", "بھینچود", "بھین چود", "بینچود", "بوسڑی", "بوسڑیکے", "بوسڑی کے", "بوسدي", "بوسڈی", "بوسڈی کے",
        "گاند", "گانڈ", "لنڈ", "لُنڈ", "رندی", "رنڈی", "کنجر", "کنجری", "حرامی", "کتا", "کتی", "کتے", "کمیینہ", "کمینہ",
        "خنزیر", "سور", "لعنتی", "پدرسگ", "پدر سگ", "کس ننت", "کیرم دهنت", "کیرم دهنِت",
        # Gurmukhi Punjabi / Hindi-Urdu cognates
        "ਚੂਤ", "ਚੂਤੀਆ", "ਚੂਤਿਯਾ", "ਚੁਤੀਆ", "ਚੋਦ", "ਚੋਦਣਾ", "ਮਾਦਰਚੋਦ", "ਮਾਦਰ ਚੋਦ", "ਭੈਣਚੋਦ", "ਭੈਣ ਚੋਦ", "ਬਹਿਨਚੋਦ",
        "ਭੋਸੜੀ", "ਭੋਸੜੀਕੇ", "ਭੋਸਡੀਕੇ", "ਬੋਸੜੀ", "ਬੋਸੜੀਕੇ", "ਗਾਂਡ", "ਗੰਡ", "ਲੰਡ", "ਲੁੰਡ", "ਰੰਡੀ", "ਕੰਜਰ", "ਕੰਜਰੀ", "ਹਰਾਮੀ", "ਕੁੱਤਾ", "ਕੁੱਤੀ", "ਕਮੀਨਾ",
        "चूत", "चूतिया", "चोद", "चोदना", "मादरचोद", "मादर चोद", "बहनचोद", "भैनचोद", "भोसड़ी", "भोसड़ीके", "गांड", "लंड", "रंडी", "हरामी", "कुत्ता", "कुत्ती",
        # Romanized South Asian / Persian / Arabic-script profanity
        "madarchod", "madar chod", "maderchod", "mader chod", "motherchod", "bhenchod", "behenchod", "bhainchod", "bhen chod", "behen chod", "bhain chod",
        "bhosdike", "bhosdi ke", "bhosri", "bhosri ke", "bsdk", "chutiya", "chutia", "chootia", "chutya", "chut", "chod", "chodu", "chodna", "gaand", "gand", "lund", "loda", "lauda", "randi", "kanjar", "harami", "kutta", "kutti", "kameena", "kamina",
        "kir", "koskesh", "kos kesh", "jakesh", "jende", "jendeh", "madarjende", "madar jende", "kooni", "koon", "goh", "guh", "gooz", "pedarsag", "pedar sag",
        # Turkish / French / Spanish / generic international terms
        "orospu", "orospusu", "amk", "siktir", "sik", "bok", "piç", "pic", "göt", "got", "yarrak",
        "putain", "merde", "connard", "connarde", "salope", "enculé", "encule", "pute",
        "puta", "puto", "mierda", "cabrón", "cabron", "cabrona", "coño", "cono", "joder", "pendejo", "pendeja",
        "punda", "kuma", "mavi", "fala", "malaya",
    ]),
]

# Strict English detection list used for back-translation triage. If a non-English
# sentence back-translates into any of these, v8 replaces the whole sentence with
# PG text because term alignment is not reliable enough for surgical masking.
STRICT_ENGLISH_TRIAGE_TERMS = [
    "fuck", "fucker", "fucking", "shit", "bitch", "cunt", "asshole", "bastard", "motherfucker", "whore", "slut", "dick", "pussy",
    "chutiya", "madarchod", "bhenchod", "behenchod", "bhosdike", "harami", "randi", "kameena",
]

CONTENT_FILTER_REGEX_RULES: List[Tuple[str, re.Pattern[str]]] = [
    (label, re.compile(pattern, re.IGNORECASE | re.UNICODE))
    for label, patterns in CONTENT_FILTER_REGEX_SPECS
    for pattern in patterns
]


def parse_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"0", "false", "no", "off", "disabled"}


def normalize_filter_surface(text: str) -> str:
    text = unicodedata.normalize("NFKC", str(text or ""))
    text = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", text)
    text = re.sub(r"[\u064b-\u065f\u0670]", "", text)
    return text


def term_pattern(term: str) -> re.Pattern[str]:
    t = normalize_filter_surface(term).strip()
    if not t:
        return re.compile(r"a^")
    # Allow light separator obfuscation only for Latin/romanized terms.
    if re.fullmatch(r"[A-Za-z0-9' -]+", t):
        escaped = [re.escape(ch) for ch in t.replace(" ", "")]
        body = _FILTER_TOKEN_SEP.join(escaped)
        return re.compile(r"(?<![A-Za-z0-9])" + body + r"(?![A-Za-z0-9])", re.IGNORECASE | re.UNICODE)
    return re.compile(r"(?<![\w])" + re.escape(t) + r"(?![\w])", re.IGNORECASE | re.UNICODE)


# These short Latin strings are legitimate words or common fragments in other supported
# languages (for example English "got" and Kurmanji "kir"). Global filtering caused
# real translation damage, so v16 leaves them to language-aware/back-translation checks.
CONTENT_FILTER_AMBIGUOUS_LITERAL_TERMS = {
    # Latin-script collisions and ordinary words in supported languages.
    "amk", "bok", "fala", "goh", "got", "gooz", "guh", "kir", "koon",
    "kuma", "kutta", "kutti", "malaya", "mavi", "pic", "punda", "sik",
    # Arabic-script words that are common interrogatives, neutral nouns, or animal names.
    "کون", "كون", "کس", "گه", "کتا", "کتی", "کتے", "خنزیر", "سور", "کیر", "كیر",
    # Neutral dog terms in Gurmukhi and Devanagari.
    "ਕੁੱਤਾ", "ਕੁੱਤੀ", "कुत्ता", "कुत्ती",
}
CONTENT_FILTER_LITERAL_RULES: List[Tuple[str, re.Pattern[str]]] = [
    (label, term_pattern(term))
    for label, terms in CONTENT_FILTER_LITERAL_TERMS
    for term in sorted(terms, key=len, reverse=True)
    if term.strip() and normalize_filter_surface(term).casefold() not in CONTENT_FILTER_AMBIGUOUS_LITERAL_TERMS
]


def filter_replacement(label: str, purpose: str = "display") -> str:
    return CONTENT_FILTER_PLACEHOLDER_TTS if purpose == "tts" else CONTENT_FILTER_PLACEHOLDER_DISPLAY


def content_filter_text_local(text: Any, enabled: bool = CONTENT_FILTER_DEFAULT, purpose: str = "display") -> Tuple[str, Dict[str, int]]:
    original = clamp_text(text, CONTENT_FILTER_MAX_CHARS)
    if not enabled or not original:
        return original, {}
    counts: Dict[str, int] = {}
    result = normalize_filter_surface(original)

    def run_rule(label: str, pattern: re.Pattern[str], value: str) -> str:
        repl_text = filter_replacement(label, purpose)
        def repl(match: re.Match[str], *, _label: str = label, _replacement: str = repl_text) -> str:
            counts[_label] = counts.get(_label, 0) + 1
            return _replacement
        return pattern.sub(repl, value)

    for label, pattern in CONTENT_FILTER_REGEX_RULES:
        result = run_rule(label, pattern, result)
    for label, pattern in CONTENT_FILTER_LITERAL_RULES:
        result = run_rule(label, pattern, result)
    return (result, counts) if counts else (original, {})


def mask(text, enabled=True, purpose='display'):
    if not enabled: return str(text or '')
    value, _ = content_filter_text_local(text, True, purpose)
    return value.replace('[filtered]', '…') if purpose == 'tts' else value
