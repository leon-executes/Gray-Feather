"""Source-anchored decisions over complete candidates; no network or voting.

Literal checks cannot establish general meaning, actor roles or fluent wording.
Only explicit violations trigger conservative whole-result replacement. A
separately requested model repair is labelled as such, never as verified truth.
"""
from __future__ import annotations
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import date
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence
import unicodedata
from decimal import Decimal, InvalidOperation

LANGUAGE_CODES = tuple("en ar fr tr fa prs ps ur hi bn pa sd am ti om so sw ckb kmr es de it pt ru zh ja ko nl pl ro uk el he id".split())
HY_LANGUAGES = frozenset("en ar fr tr fa ur hi bn es de it pt ru zh ja ko nl pl uk he id".split())

@dataclass(frozen=True)
class Candidate:
    text: str
    provider: str
    family: str = ""
    complete: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class ReinforcementDecision:
    text: str
    provider: str
    original_primary: Candidate
    changed: bool
    method: str
    reasons: tuple[str, ...]
    audit: tuple[dict[str, Any], ...]
    candidate_checks: tuple[dict[str, Any], ...]
    def to_dict(self):
        return asdict(self)

def _sha(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()

@lru_cache(maxsize=1)
def _routes():
    path = Path(__file__).with_name("language_routes.json")
    return json.loads(path.read_text(encoding="utf-8"))

def route_order(source_code, target_code, enabled):
    """Configured-only availability order, not an invented accuracy ranking."""
    if source_code not in LANGUAGE_CODES or target_code not in LANGUAGE_CODES:
        raise ValueError("Unknown language identity.")
    enabled = tuple(dict.fromkeys(enabled))
    data = _routes()
    direction = data["directions"].get(source_code + ">" + target_code, {})
    preferences = direction.get("measured_order", []) if direction.get("evidence_approved", False) else direction.get("preference_order", [])
    # Stable exact-before-approximation; preserve caller order otherwise.
    def key(provider):
        supported = True
        approximate = False
        if provider in ("bing_web", "azure") and "om" in (source_code, target_code):
            supported = False
        elif provider == "hy_mt_local":
            supported = {source_code, target_code} <= HY_LANGUAGES
        elif provider == "index_web":
            supported = "prs" not in (source_code, target_code) and (source_code, target_code) != ("om", "en")
        elif provider == "deepl":
            supported = {source_code, target_code} <= frozenset("en ar fr tr es de it pt ru zh ja ko nl pl ro uk el he id".split())
        elif provider == "google" and "prs" in (source_code, target_code):
            supported = False
        elif provider in ("google_web", "mymemory", "lingva", "libretranslate"):
            approximate = "prs" in (source_code, target_code)
        elif provider not in data["providers"]:
            supported = False
        return supported, approximate
    eligible = [provider for provider in enabled if key(provider)[0]]
    return tuple(sorted(eligible, key=lambda provider: (key(provider)[1], preferences.index(provider) if provider in preferences else len(preferences), enabled.index(provider))))

@lru_cache(maxsize=1)
def _calendar_data():
    path = Path(__file__).parent / "resources" / "reinforcement" / "calendar_lexicon.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8")).get("languages", {})

def _decimal(value):
    return "".join(str(unicodedata.decimal(c)) if c.isdecimal() else c for c in value).replace("−", "-").replace("٫", ".")

def _month_matches(text, code):
    record = _calendar_data().get(code, {})
    if not record.get("complete") or record.get("calendar") != "gregorian":
        return []
    matches = []
    seen = set()
    for number, forms in record["months"].items():
        for context, word in forms.items():
            # Numeric names (Chinese 10月 etc.) are handled by existing number
            # checks, not rewritten as alphabetic month names.
            if any(c.isdecimal() for c in word) or len(word) < 2:
                continue
            pattern = re.compile(r"(?<!\w)" + re.escape(word) + r"(?!\w)", re.I)
            for match in pattern.finditer(text):
                identity = (match.start(), match.end(), int(number))
                if identity not in seen:
                    seen.add(identity)
                    matches.append({"start": match.start(), "end": match.end(), "month": int(number), "context": context, "word": match.group()})
    return sorted(matches, key=lambda item: item["start"])

def _date_anchor(text, match):
    plain = _decimal(text)
    # Decimal normalization preserves offsets (one character to one character).
    years = list(re.finditer(r"(?<!\d)(?:19|20|21)\d{2}(?!\d)", plain))
    if len(years) != 1:
        return None
    year = years[0]
    if min(abs(year.start() - match["end"]), abs(match["start"] - year.end())) > 32:
        return None
    candidates = []
    for number in re.finditer(r"(?<![\d/:])\d{1,2}(?![\d/:])", plain):
        if number.start() >= match["start"] and number.end() <= match["end"]:
            continue
        value = int(number.group())
        distance = min(abs(number.start() - match["end"]), abs(match["start"] - number.end()))
        if 1 <= value <= 31 and distance <= 8:
            between = plain[min(number.end(), match["end"]):max(number.start(), match["start"])]
            if not any(c.isalpha() for c in between):
                candidates.append((distance, value))
    if not candidates:
        return None
    candidates.sort()
    if len(candidates) > 1 and candidates[0][0] == candidates[1][0]:
        return None
    day, year_number = candidates[0][1], int(year.group())
    try:
        date(year_number, match["month"], day)
    except ValueError:
        return None
    return day, year_number

_CALENDAR_CONVERSION = re.compile(r"\b(?:hijri|islamic|ethiopic|ethiopian|julian|lunar|hebrew|persian\s+calendar|convert\w*\s+(?:the\s+)?date|calendar\s+conversion)\b", re.I)

def _calendar_check(source, target, source_code, target_code):
    source_matches, target_matches = _month_matches(source, source_code), _month_matches(target, target_code)
    active = len(source_matches) == 1 and _date_anchor(source, source_matches[0]) is not None and not _CALENDAR_CONVERSION.search(source)
    result = {"status": "unresolved", "source_active": bool(active), "reason": "A unique aligned native Gregorian date is not available."}
    if _CALENDAR_CONVERSION.search(source) or len(source_matches) != 1 or len(target_matches) != 1:
        return result
    a, b = source_matches[0], target_matches[0]
    source_anchor, target_anchor = _date_anchor(source, a), _date_anchor(target, b)
    if source_anchor is None or source_anchor != target_anchor:
        return result
    return {"status": "preserved" if a["month"] == b["month"] else "violation", "source_active": True, "source_month": a["month"], "target_month": b["month"], "anchor": source_anchor, "source_match": a, "target_match": b}

def _day_matches(text, code):
    days = _calendar_data().get(code, {}).get("days", {})
    matches, seen = [], set()
    for identity, forms in days.items():
        for word in set(forms.values()):
            if len(word) < 2:
                continue
            for match in re.finditer(r"(?<!\w)" + re.escape(word) + r"(?!\w)", text, re.I):
                key = (match.start(), match.end(), identity)
                if key not in seen:
                    seen.add(key)
                    matches.append({"start": match.start(), "end": match.end(), "day": identity, "word": match.group()})
    return sorted(matches, key=lambda item: item["start"])

def calendar_glossary(source, source_code, target_code):
    """Native CLDR names only in one explicitly anchored Gregorian source date."""
    months = _month_matches(source, source_code)
    if len(months) != 1 or _date_anchor(source, months[0]) is None or _CALENDAR_CONVERSION.search(source) or any(mark in source for mark in ('"', '“', '”', '`')):
        return {}
    target = _calendar_data().get(target_code, {})
    if not target.get("complete"):
        return {}
    terms = {months[0]["word"]: target["months"][str(months[0]["month"])]["format"]}
    for match in _day_matches(source, source_code):
        forms = target.get("days", {}).get(match["day"], {})
        if forms.get("format"):
            terms[match["word"]] = forms["format"]
    return terms

def _weekday_check(source, target, source_code, target_code, calendar):
    if not calendar.get("source_active"):
        return {"status": "not_applicable"}
    first, second = _day_matches(source, source_code), _day_matches(target, target_code)
    if not first:
        return {"status": "not_applicable"}
    a, b = Counter(item["day"] for item in first), Counter(item["day"] for item in second)
    status = "preserved" if a == b else "violation" if b and b - a else "unresolved"
    return {"status": status, "source": tuple(a.elements()), "target": tuple(b.elements()), "limits": "Exact native CLDR forms only. Unknown variants remain unresolved; names are never blindly replaced."}

_SIGNED_WORDS = re.compile(r"\b(minus|negative|plus|positive)\s+(\d+(?:[.,]\d+)?)\b", re.I)
_EXPLICIT_SIGNS = re.compile(r"(?<![\w\d])([+\-−])\s*(\d+(?:[.,٫]\d+)?)")

_SIGNED_QUANTITY = re.compile(r"(?<![\w\d])(?P<sign>minus|negative|plus|positive|[+−-])\s*(?P<number>\d+(?:[.]\d+)?)\s*(?P<unit>°\s*[CFK]|degrees?\s+(?:Celsius|Fahrenheit|Kelvin)|mg|kg|ml|cm|mm|km|g)\b", re.I)

def source_signed_quantities(source, source_code):
    """Prompt constraints for explicit English signed quantities, never arithmetic.

    Only a signed numeral immediately attached to a known written unit is
    eligible. Identifiers, unsigned numbers, subtraction and unaligned ranges
    are left untouched; no translated-language sign dictionary is inferred.
    """
    if source_code != "en":
        return ()
    result = []
    for match in _SIGNED_QUANTITY.finditer(source):
        before = source[:match.start()].rstrip()
        if before and (before[-1].isdigit() or before[-1] in ")=/*"):
            continue
        sign = "-" if match["sign"].lower() in ("minus", "negative", "−", "-") else "+"
        result.append({"source": match.group(), "signed_number": sign + match["number"], "unit": match["unit"], "start": match.start(), "end": match.end()})
        contrast = re.match(r"\s*,?\s*not\s+(minus|negative|plus|positive|[+−-])\s*(\d+(?:[.]\d+)?)(?=\s*(?:[.!?;]|$))", source[match.end():], re.I)
        if contrast:
            other_sign = "-" if contrast[1].lower() in ("minus", "negative", "−", "-") else "+"
            result.append({"source": contrast.group().strip(), "signed_number": other_sign + contrast[2], "unit": match["unit"], "unit_inherited": True, "start": match.end() + contrast.start(), "end": match.end() + contrast.end()})
    return tuple(result)

def _signed_values(text, code):
    def unary(match):
        before = text[:match.start()].rstrip()
        return not before or not (before[-1].isdigit() or before[-1] in ")=/*")
    values = [("-" if m[1] in ("-", "−") else "+") + _decimal(m[2]).replace(",", ".") for m in _EXPLICIT_SIGNS.finditer(text) if unary(m)]
    if code == "en":
        values += [("-" if m[1].lower() in ("minus", "negative") else "+") + m[2].replace(",", ".") for m in _SIGNED_WORDS.finditer(text) if unary(m)]
    return tuple(values)

_EN_CONTRAST = re.compile(r"(?<!\w)(\d+(?:[.]\d+)?)\s*(mg|kg|ml|cm|mm|km|g)\s*,?\s*not\s+(\d+(?:[.]\d+)?)\s*\2\b", re.I)
_AM_REVERSED = re.compile(r"(?<!\w)(\d+(?:[.٫]\d+)?)\s*(mg|kg|ml|cm|mm|km|g)\s+ሳይሆን\s+(\d+(?:[.٫]\d+)?)\s*\2\b", re.I)

def _money_pairs(text):
    from engine import _CURRENCIES, _CURRENCY_NAMES, _number
    number = r"[-+−]?\d+(?:[.,٫٬]\d+)*"
    pairs, spans = [], set()
    for pattern in ("(?P<currency>" + _CURRENCIES.pattern + ")\\s*(?P<number>" + number + ")", "(?P<number>" + number + ")\\s*(?P<currency>" + _CURRENCIES.pattern + ")"):
        for match in re.finditer(pattern, text):
            if match.span() in spans:
                continue
            token = _decimal(match["number"])
            # A single three-digit separator can mean a decimal or thousands.
            # Do not manufacture an amount identity from ambiguous formatting.
            if re.search(r"[.,٬]\d{3}(?:\D|$)", token) or token.count(".") + token.count(",") + token.count("٬") > 1:
                continue
            try:
                value = format(Decimal(_number(token)).normalize(), "f")
            except InvalidOperation:
                continue
            spans.add(match.span())
            pairs.append((_CURRENCY_NAMES.get(match["currency"], match["currency"]), value))
    return tuple(pairs)

def _outside_quote(text, start, end):
    # Apostrophes inside words are not treated as quote delimiters. Unclosed
    # literal delimiters sideline relational repair rather than guessing scope.
    patterns = (r'"(?:[^"\\]|\\.)*"', r"“[^”]*”", r"`[^`]*`")
    quoted = [match.span() for pattern in patterns for match in re.finditer(pattern, text)]
    masked = list(text)
    for first, last in quoted:
        masked[first:last] = " " * (last-first)
    if any(mark in "".join(masked) for mark in ('"', '“', '”', '`')):
        return False
    return not any(start < last and end > first for first, last in quoted)

def _negative_promise(source, text, source_code, target_code):
    if (source_code, target_code) != ("en", "nl"):
        return {"status": "not_applicable"}
    source_matches = [match for match in re.finditer(r"(?<!\w)Do\s+not\s+promise\s+to\s+[^.!?\n]+(?:[.!?]|$)", source, re.I) if _outside_quote(source, *match.span())]
    if len(source_matches) != 1:
        return {"status": "not_applicable"}
    if any(_outside_quote(source, *match.span()) for match in re.finditer(r"\b(?:call|phone|ring|reward\w*)\b", source, re.I)):
        return {"status": "unresolved", "reason": "Another calling/rewarding action makes clause alignment ambiguous."}
    bad_pattern = r"(?<!\w)(?:Bel\s+niet\s+dat\s+(?:je|u|jij)\s+|Beloon\s+niet\s+om\s+)[^.!?\n]+(?:[.!?]|$)"
    good_pattern = r"(?<!\w)Beloof\s+niet\s+(?:dat\s+(?:je|u|jij)\s+|om\s+)[^.!?\n]+(?:[.!?]|$)"
    bad = [match for match in re.finditer(bad_pattern, text, re.I) if _outside_quote(text, *match.span())]
    good = [match for match in re.finditer(good_pattern, text, re.I) if _outside_quote(text, *match.span())]
    if len(bad) == 1 and not good:
        match = bad[0]
        word_length = len(match.group().split(None, 1)[0])
        return {"status": "violation", "reason": "The unique negative promise clause uses Dutch Bel (call) or Beloon (reward) instead of Beloof (promise).", "start": match.start(), "end": match.end(), "before": match.group(), "after": ("Beloof" if match.group()[0].isupper() else "beloof") + match.group()[word_length:]}
    if len(good) == 1 and not bad:
        return {"status": "preserved", "limits": "Negative promise verb only; complement meaning is not certified."}
    return {"status": "unresolved", "reason": "An exact unique Dutch negative promise clause is not aligned."}

def _opaque_literals(text, kind):
    from engine import _LINKS, _REFERENCE
    values = []
    pattern = _REFERENCE if kind == "reference" else _LINKS
    for match in pattern.finditer(text):
        value = match.group().rstrip(".,;:!?)]}") if kind != "reference" else match.group()
        if kind == "email" and (value.startswith(("http://", "https://")) or "@" not in value):
            continue
        if kind == "url" and not value.startswith(("http://", "https://")):
            continue
        if kind == "reference" and not (any(c.isdigit() for c in value) and any(c.isalpha() for c in value)):
            continue
        values.append({"value": value, "start": match.start(), "end": match.start() + len(value)})
    return values

def _opaque_edit(source, target, first):
    """One complete opaque atom per subtype, no additions or missing content."""
    from engine import extract_facts
    original, translated = extract_facts(source), extract_facts(target)
    for subtype in ("email", "url", "reference"):
        a, b = _opaque_literals(source, subtype), _opaque_literals(target, subtype)
        if len(a) != 1 or len(b) != 1 or a[0]["value"] == b[0]["value"]:
            continue
        before, after = b[0]["value"], a[0]["value"]
        if source.count(after) != 1 or target.count(before) != 1:
            continue
        fact_kind = "references" if subtype == "reference" else "identifiers"
        if any(not equal for kind, equal in first["facts_equal"].items() if kind != fact_kind):
            continue
        if set(first["hard_violations"]) - {fact_kind}:
            continue
        if Counter(original[fact_kind]) - Counter(translated[fact_kind]) != Counter({after: 1}) or Counter(translated[fact_kind]) - Counter(original[fact_kind]) != Counter({before: 1}):
            continue
        return {"kind": subtype, "start": b[0]["start"], "end": b[0]["end"], "before": before, "after": after}
    return None

def critical_checks(source, text, source_code, target_code):
    # Lazy import keeps this module safe to import from engine.py itself.
    from engine import extract_facts
    unit_equivalences = []
    def literal_signs(value, code):
        if code == "en":
            def replace(match):
                before = value[:match.start()].rstrip()
                if before and (before[-1].isdigit() or before[-1] in ")=/*"):
                    return match.group()
                return ("-" if match[1].lower() in ("minus", "negative") else "+") + match[2]
            value = _SIGNED_WORDS.sub(replace, value)
            # Exact English written physical units have stable symbol identities;
            # this is not a guessed target-language terminology dictionary.
            return re.sub(r"\bdegrees?\s+(Celsius|Fahrenheit)\b", lambda match: "°C" if match[1].lower() == "celsius" else "°F", value, flags=re.I)
        return value
    if source_code == "en":
        for match in re.finditer(r"\bdegrees?\s+(Celsius|Fahrenheit)\b", source, re.I):
            unit_equivalences.append({"source": match.group(), "unit": "°C" if match[1].lower() == "celsius" else "°F", "limits": "Written English physical unit identity only; quantities and signs are checked separately."})
    original, translated = extract_facts(literal_signs(source, source_code)), extract_facts(literal_signs(text, target_code))
    for item in source_signed_quantities(source, source_code):
        if item.get("unit_inherited"):
            unit = item["unit"]
            unit = "°C" if unit.lower().endswith("celsius") else "°F" if unit.lower().endswith("fahrenheit") else unit
            inherited = item["signed_number"] + " " + unit
            original["units"] = tuple(original["units"]) + (inherited,)
            unit_equivalences.append({"source": item["source"], "unit": inherited, "limits": "Unique immediately adjacent not-plus/minus contrast inherits the exact written source unit."})
    equivalences = []
    # Arabic's productive dual inflection can express exactly two copies
    # without a digit. This narrowly source-bound equivalence does not infer
    # other written quantities, allocation, negation or actor roles.
    if source_code == "en" and target_code == "ar" and len(re.findall(r"(?<!\w)2\s+copies(?!\w)", source, re.I)) == 1:
        duals = re.findall(r"(?<!\w)(?:نسختين|نسختان)(?!\w)", text)
        a, b = Counter(original.get("numbers", ())), Counter(translated.get("numbers", ()))
        if len(duals) == 1 and sum(text.count(form) for form in ("نسختين", "نسختان")) == 1 and a.get("2") == 1 and a - b == Counter({"2": 1}) and not b - a:
            translated["numbers"] = tuple(translated["numbers"]) + ("2",)
            equivalences.append({"kind": "numbers", "source": "2 copies", "target": duals[0], "value": "2", "limits": "Quantity only; no polarity, allocation or role assurance."})
    hard, unresolved = [], []
    equal = {}
    for kind in original:
        a, b = Counter(original[kind]), Counter(translated[kind])
        equal[kind] = a == b
        if a == b:
            continue
        if kind in ("identifiers", "references") or (kind == "currencies" and a and b and b - a) or (kind == "units" and a and b and b - a):
            hard.append(kind)
        else:
            unresolved.append(kind)
    source_money, target_money = _money_pairs(source), _money_pairs(text)
    monetary = {"status": "not_applicable", "source": source_money, "target": target_money}
    if original["currencies"]:
        monetary["status"] = "preserved" if Counter(source_money) == Counter(target_money) and len(source_money) == len(original["currencies"]) == len(translated["currencies"]) else "unresolved"
        if (source_money and target_money and len(source_money) == len(original["currencies"]) and len(target_money) == len(translated["currencies"]) and Counter(target_money) - Counter(source_money)):
            monetary["status"] = "violation"
            hard.append("currency_amounts")
    promise = _negative_promise(source, text, source_code, target_code)
    if promise["status"] == "violation":
        hard.append("negative_promise")
    calendar = _calendar_check(source, text, source_code, target_code)
    if calendar["status"] == "violation":
        hard.append("calendar_month")
    elif calendar.get("source_active") and calendar["status"] == "unresolved":
        unresolved.append("calendar_month")
    weekdays = _weekday_check(source, text, source_code, target_code, calendar)
    if weekdays["status"] == "violation":
        hard.append("calendar_weekdays")
    elif weekdays["status"] == "unresolved":
        unresolved.append("calendar_weekdays")
    signs = _signed_values(source, source_code)
    target_signs = _signed_values(text, target_code)
    sign_status = "not_applicable"
    if signs:
        sign_status = "preserved" if Counter(signs) == Counter(target_signs) else "unresolved"
        if target_signs and Counter(target_signs) != Counter(signs):
            hard.append("signed_numbers")
            sign_status = "violation"
        elif sign_status == "unresolved":
            unresolved.append("signed_numbers")
    contrast = {"status": "not_applicable"}
    source_contrasts = list(_EN_CONTRAST.finditer(source)) if source_code == "en" else []
    if len(source_contrasts) == 1 and target_code == "am":
        a = source_contrasts[0]
        observed = list(_AM_REVERSED.finditer(_decimal(text)))
        if len(observed) == 1 and observed[0][1] == a[1] and observed[0][3] == a[3] and a[1] != a[3]:
            contrast = {"status": "violation", "reason": "Amharic A ሳይሆን B means not A but B; the source asserts A and rejects B."}
            hard.append("numeric_contrast")
        elif len(observed) == 1 and observed[0][1] == a[3] and observed[0][3] == a[1] and a[1] != a[3]:
            contrast = {"status": "preserved", "reason": "The unique Amharic not-B-but-A numeric contrast retains the source's asserted and rejected quantities."}
        else:
            contrast = {"status": "unresolved", "reason": "Absence of a reversed marker does not prove the translated scope."}
            unresolved.append("numeric_contrast")
    consultation = tuple(hard) + tuple(kind for kind in ("signed_numbers", "numeric_contrast", "calendar_month", "calendar_weekdays") if kind in unresolved and kind not in hard)
    return {"hard_violations": tuple(hard), "violations": tuple(hard), "unresolved": tuple(unresolved), "consultation_reasons": consultation, "needs_consultation": bool(consultation), "facts_equal": equal, "currency_amounts": monetary, "negative_promise": promise,
            "facts": translated, "number_equivalences": tuple(equivalences), "unit_equivalences": tuple(unit_equivalences), "calendar": calendar, "calendar_weekdays": weekdays, "signed_numbers": {"status": sign_status, "source": signs, "target": target_signs}, "numeric_contrast": contrast,
            "literal_complete": all(equal.values()) and not hard and not set(unresolved).intersection({"signed_numbers", "calendar_month", "calendar_weekdays"})}

def _candidate(value):
    if isinstance(value, Candidate):
        return value
    if isinstance(value, Mapping):
        return Candidate(value["text"], value["provider"], value.get("family", ""), value.get("complete", True), value.get("metadata", {}))
    raise TypeError("A complete Candidate or candidate dictionary is required.")

def _valid(candidate):
    return candidate.complete is True and isinstance(candidate.text, str) and bool(candidate.text.strip()) and "\x00" not in candidate.text and not any(0xD800 <= ord(c) <= 0xDFFF for c in candidate.text)

def reinforce(source, source_code, target_code, primary, alternatives=(), *, policy="conservative", glossary=False, context=False):
    """Apply one reversible, source-bound whole selection or aligned month repair.

    policy='source_anchored_model' permits an explicitly requested model repair
    bound to both exact source and original candidate hashes. Fact preservation
    remains necessary, not a claim that model rewriting always improves meaning.
    """
    if source_code not in LANGUAGE_CODES or target_code not in LANGUAGE_CODES:
        raise ValueError("Unknown language identity.")
    if policy not in ("conservative", "source_anchored_model"):
        raise ValueError("Unknown reinforcement policy.")
    primary = _candidate(primary)
    if not _valid(primary):
        raise ValueError("The primary candidate must be a complete valid result.")
    candidates = [primary] + [_candidate(item) for item in alternatives]
    checks = []
    for item in candidates:
        check = critical_checks(source, item.text, source_code, target_code) if _valid(item) else {"hard_violations": ("incomplete",), "literal_complete": False, "unresolved": ()}
        checks.append({"provider": item.provider, "text_sha256": _sha(item.text) if isinstance(item.text, str) else "", **check})
    selected, method, reasons, edit = primary, "unchanged", (), None
    first = checks[0]
    if not glossary and not context:
        for item, check in zip(candidates[1:], checks[1:]):
            if not _valid(item) or item.text == primary.text or not check["literal_complete"]:
                continue
            # A complete result must resolve the particular observed violation;
            # unknown Amharic contrast scope cannot claim a role repair.
            polarity_recovery = first.get("signed_numbers", {}).get("status") == "unresolved" and check.get("signed_numbers", {}).get("status") == "preserved"
            if (first["hard_violations"] or polarity_recovery) and not check["hard_violations"]:
                if "numeric_contrast" in first["hard_violations"] and check.get("numeric_contrast", {}).get("status") != "preserved":
                    continue
                if "calendar_month" in first["hard_violations"] and check.get("calendar", {}).get("status") != "preserved":
                    continue
                if "currency_amounts" in first["hard_violations"] and check.get("currency_amounts", {}).get("status") != "preserved":
                    continue
                if "negative_promise" in first["hard_violations"]:
                    if check.get("negative_promise", {}).get("status") != "preserved":
                        continue
                    quotes = lambda value: re.findall(r'"(?:[^"\\]|\\.)*"|“[^”]*”|`[^`]*`', value)
                    if quotes(primary.text) != quotes(item.text):
                        continue
                selected, method = item, "whole_candidate"
                reasons = tuple(first["hard_violations"]) + (("explicit_signed_polarity_recovery",) if polarity_recovery else ())
                break
        if method == "unchanged" and policy == "source_anchored_model":
            for item, check in zip(candidates[1:], checks[1:]):
                meta = item.metadata
                if (_valid(item) and item.provider in ("hy_mt_local", "gemma_local", "index_web") and meta.get("operation") == "repair"
                    and meta.get("source_sha256") == _sha(source) and meta.get("candidate_sha256") == _sha(primary.text)
                    and meta.get("direction_approved") is True and isinstance(meta.get("evidence_id"), str) and bool(meta["evidence_id"].strip())
                    and check["literal_complete"] and item.text != primary.text
                    and "numeric_contrast" not in first["hard_violations"]):
                    selected, method, reasons = item, "model_repair", ("Explicit source-bound model repair; semantic improvement is not established by literal checks.",)
                    break
        calendar = first.get("calendar", {})
        promise = first.get("negative_promise", {})
        if method == "unchanged":
            literal_edit = _opaque_edit(source, primary.text, first)
            if literal_edit:
                changed = primary.text[:literal_edit["start"]] + literal_edit["after"] + primary.text[literal_edit["end"]:]
                check = critical_checks(source, changed, source_code, target_code)
                if check["literal_complete"]:
                    selected = Candidate(changed, primary.provider, primary.family, True, primary.metadata)
                    method, reasons, edit = "opaque_literal_repair", ("One unique corrupted opaque literal restored exactly from the source; all other protected facts retained.",), literal_edit
        if method == "unchanged" and promise.get("status") == "violation" and set(first["hard_violations"]) == {"negative_promise"} and all(first["facts_equal"].values()):
            changed = primary.text[:promise["start"]] + promise["after"] + primary.text[promise["end"]:]
            check = critical_checks(source, changed, source_code, target_code)
            if check["literal_complete"]:
                selected = Candidate(changed, primary.provider, primary.family, True, primary.metadata)
                method, reasons = "negative_promise_repair", ("The unique unquoted English do-not-promise clause restores Dutch Beloof in its complete existing clause; the complement and quoted words are retained.",)
                edit = {"start": promise["start"], "end": promise["end"], "before": promise["before"], "after": promise["after"]}
        if method == "unchanged" and calendar.get("status") == "violation" and not (set(first["hard_violations"]) - {"calendar_month"}):
            source_match = calendar["source_match"]
            # Quoted literals/instructions and explicit non-Gregorian conversions
            # have no licence for surgical rewriting.
            if not any(mark in source for mark in ('"', '“', '”', '`')) and all(first["facts_equal"].values()):
                match = calendar["target_match"]
                forms = _calendar_data()[target_code]["months"][str(calendar["source_month"])]
                replacement = forms.get(match["context"], forms["format"])
                if match["word"].isupper():
                    replacement = replacement.upper()
                elif match["word"][:1].isupper():
                    replacement = replacement[:1].upper() + replacement[1:]
                changed = primary.text[:match["start"]] + replacement + primary.text[match["end"]:]
                check = critical_checks(source, changed, source_code, target_code)
                if check["literal_complete"]:
                    selected = Candidate(changed, primary.provider, primary.family, True, primary.metadata)
                    method, reasons = "calendar_repair", ("Unique Gregorian day/year alignment retained; named month restored from the source using Unicode CLDR.",)
                    edit = {"start": match["start"], "end": match["end"], "before": match["word"], "after": replacement, "source_month": calendar["source_month"], "target_month_before": calendar["target_month"], "anchor": calendar["anchor"]}
    changed = selected.text != primary.text
    audit = ({"method": method, "source_sha256": _sha(source), "original_sha256": _sha(primary.text), "selected_sha256": _sha(selected.text), "original_provider": primary.provider, "selected_provider": selected.provider, "edit": edit,
              "limits": "Literal preservation does not establish negation, role allocation, terminology or overall translation accuracy."},)
    return ReinforcementDecision(selected.text, selected.provider, primary, changed, method, reasons, audit, tuple(checks))
