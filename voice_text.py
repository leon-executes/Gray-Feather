"""Conservative speech-only number spelling. Original display text is untouched.
Copyright 2026 Parham (Leon) Faraji. SPDX-License-Identifier: MIT

Tigrinya vocabulary cross-checked against fgaim/tigrinya-numbers (CC BY-SA 4.0).
Sorani digit vocabulary cross-checked against RevgeAI/vekol-tts-ckb-edge.
No calendar inference, floating-point conversion, rounding or integer truncation.
"""
import re
import unicodedata

DIGITS = {
    'tir': ('ዜሮ','ሓደ','ክልተ','ሰለስተ','ኣርባዕተ','ሓሙሽተ','ሽዱሽተ','ሸውዓተ','ሸሞንተ','ትሽዓተ'),
    'ckb': ('سفر','یەک','دوو','سێ','چوار','پێنج','شەش','حەوت','هەشت','نۆ'),
    'som': ('eber','kow','laba','saddex','afar','shan','lix','toddoba','siddeed','sagaal'),
}
SIGNS = {
    'tir': {'.':'ነጥቢ','٫':'ነጥቢ','-':'ኣሉታ','−':'ኣሉታ',':':'ክልተ ነጥቢ','፡':'ክልተ ነጥቢ','/':'ስላሽ','%':'ሚእታዊት'},
    'ckb': {'.':'خاڵ','٫':'خاڵ','-':'سالب','−':'سالب',':':'دوو خاڵ','/':'سلەش','%':'لە سەدا'},
}

def spell_numbers(text, language):
    """Read numeric tokens literally, digit by digit, preserving leading zeros.

    Dates and times stay in their written order. Unsupported mathematical and
    currency symbols are left for the strict model guard, never silently lost.
    """
    if language not in DIGITS:
        return text
    if language == 'som':
        # Only plain unsigned integers are covered. Leave other notation
        # intact so the model guard refuses it instead of losing a sign,
        # decimal point, time separator or unit.
        if re.search(r'\d\s*[.,:/%−-]\s*\d|[−-]\s*\d|\d\s*%',text):return text
        return re.sub(r'\d+',lambda m:' '+' '.join(DIGITS['som'][unicodedata.decimal(c)] for c in m.group())+' ',text)
    def token(match):
        parts=[]
        for char in match.group():
            if char.isdecimal(): parts.append(DIGITS[language][unicodedata.decimal(char)])
            elif char in SIGNS[language]: parts.append(SIGNS[language][char])
            else: parts.append(char)
        return ' ' + ' '.join(parts) + ' '
    return re.sub(r'[−-]?\d+(?:[.:/٫፡−-]\d+)*%?', token, text)

