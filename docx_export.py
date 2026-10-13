"""Dependency-free Word transcript export with atomic replacement and full text."""
from __future__ import annotations
import datetime
import os
from pathlib import Path
import tempfile
from xml.sax.saxutils import escape
import zipfile

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'

def _text(value):
    if not isinstance(value, str):
        raise ValueError('Word export fields must contain text.')
    # XML cannot represent these controls. Display their code points instead of
    # dropping characters; the original stored text is never changed.
    return ''.join(c if c in '\t\r\n' or 0x20 <= ord(c) <= 0xD7FF or 0xE000 <= ord(c) <= 0xFFFD or 0x10000 <= ord(c) <= 0x10FFFF else f'\\u{ord(c):04x}' for c in value)

def _paragraph(text, *, style='Normal', rtl=False, locale='en-US', bold=False):
    content = _text(text).replace('\r\n', '\n').replace('\r', '\n')
    properties = f'<w:pStyle w:val="{style}"/>'
    if rtl:
        properties += '<w:bidi/><w:jc w:val="right"/>'
    runs = []
    pieces = content.replace('\t', '\n\t\n').split('\n')
    for index, piece in enumerate(pieces):
        if piece == '\t':
            runs.append('<w:r><w:tab/></w:r>')
            continue
        if index and pieces[index - 1] != '\t':
            runs.append('<w:r><w:br/></w:r>')
        rp = f'<w:lang w:val="{escape(locale)}" w:bidi="{escape(locale)}"/>'
        if rtl:
            rp += '<w:rtl/>'
        if bold:
            rp += '<w:b/>'
        runs.append(f'<w:r><w:rPr>{rp}</w:rPr><w:t xml:space="preserve">{escape(piece)}</w:t></w:r>')
    return f'<w:p><w:pPr>{properties}</w:pPr>{"".join(runs)}</w:p>'

def export_docx(conversation, destination):
    import engine
    destination = Path(destination)
    if not isinstance(conversation, dict) or not isinstance(conversation.get('turns'), list):
        raise ValueError('Choose a saved conversation to export.')
    title = conversation.get('title', 'Conversation')
    engine.validate_text(title, 'Export title', 300, True)
    turns = conversation['turns']
    for turn in turns:
        if turn.get('source_lang') not in engine.LANG_BY_CODE or turn.get('target_lang') not in engine.LANG_BY_CODE:
            raise ValueError('The export contains an unknown language.')
        for name in ('raw_source', 'reviewed_source', 'translated_text'):
            engine.validate_text(turn.get(name, ''), 'Export text', engine.MAX_TEXT_CHARS * 4, True)
    now = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    parts = {
      '[Content_Types].xml': '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/><Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/><Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/></Types>',
      '_rels/.rels': '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/></Relationships>',
      'word/_rels/document.xml.rels': '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>',
      'docProps/core.xml': f'<?xml version="1.0" encoding="UTF-8"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:title>{escape(_text(title))}</dc:title><dc:creator>Gray Feather</dc:creator><dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created></cp:coreProperties>',
      'docProps/app.xml': '<?xml version="1.0" encoding="UTF-8"?><Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"><Application>Gray Feather</Application></Properties>',
      'word/styles.xml': f'''<?xml version="1.0" encoding="UTF-8"?><w:styles xmlns:w="{W}"><w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:cs="Arial"/><w:sz w:val="24"/><w:szCs w:val="24"/><w:color w:val="000000"/></w:rPr></w:rPrDefault><w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="276" w:lineRule="auto"/><w:widowControl/></w:pPr></w:pPrDefault></w:docDefaults><w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style><w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:pPr><w:keepNext/><w:spacing w:before="0" w:after="240"/></w:pPr><w:rPr><w:b/><w:sz w:val="36"/><w:color w:val="000000"/></w:rPr></w:style><w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:pPr><w:keepNext/><w:outlineLvl w:val="0"/><w:spacing w:before="240" w:after="140"/></w:pPr><w:rPr><w:b/><w:sz w:val="28"/><w:color w:val="000000"/></w:rPr></w:style><w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:pPr><w:keepNext/><w:outlineLvl w:val="1"/><w:spacing w:before="160" w:after="80"/></w:pPr><w:rPr><w:b/><w:color w:val="000000"/></w:rPr></w:style></w:styles>''',
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.grayfeather-export-', suffix='.docx', dir=destination.parent)
    os.close(fd)
    staged = Path(name)
    try:
        with zipfile.ZipFile(staged, 'w', compression=zipfile.ZIP_DEFLATED) as package:
            for name, value in parts.items():
                package.writestr(name, value.encode('utf-8'))
            with package.open('word/document.xml', 'w') as document:
                def write(value): document.write(value.encode('utf-8'))
                write(f'<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="{W}"><w:body>')
                write(_paragraph('Gray Feather conversation transcript', style='Title'))
                write(_paragraph(title or 'Conversation'))
                write(_paragraph('Original and reviewed words, completed translations and available review aids from this saved session. Provider comparisons and back translations are advisory. Unsupported control characters are shown as escaped Unicode codes.'))
                if not turns:
                    write(_paragraph('This session has no saved turns.'))
                for index, turn in enumerate(turns, 1):
                    src, tgt = engine.LANG_BY_CODE[turn['source_lang']], engine.LANG_BY_CODE[turn['target_lang']]
                    write(_paragraph(f'Turn {index} Speaker {turn.get("speaker", "")}', style='Heading1'))
                    write(_paragraph(src.name + ' to ' + tgt.name))
                    for heading, text, language in (
                        ('Original', turn.get('raw_source', ''), src),
                        ('Reviewed source', turn.get('reviewed_source', ''), src),
                        ('Translation', turn.get('translated_text', ''), tgt)):
                        if heading == 'Reviewed source' and (not text or text == turn.get('raw_source', '')):
                            continue
                        write(_paragraph(heading, style='Heading2'))
                        write(_paragraph(text or 'No completed text', rtl=language.rtl, locale=language.bcp47))
                    provider = engine.PROVIDER_NAMES.get(turn.get('provider'), turn.get('provider') or 'Pending')
                    write(_paragraph('Provider ' + provider))
                    metadata = turn.get('metadata', {})
                    alternatives = []
                    review_text = turn.get('review_text', metadata.get('review_text', ''))
                    if review_text:
                        alternatives.append({'text': review_text, 'provider': turn.get('review_provider', metadata.get('review_provider', ''))})
                    alternatives.extend(turn.get('extra_opinions', metadata.get('extra_opinions', turn.get('opinions', metadata.get('opinions', [])))))
                    for number, opinion in enumerate(alternatives, 2):
                        write(_paragraph(f'Opinion {number}', style='Heading2'))
                        write(_paragraph(str(opinion.get('text', '')), rtl=tgt.rtl, locale=tgt.bcp47))
                        write(_paragraph('Provider ' + engine.PROVIDER_NAMES.get(opinion.get('provider'), opinion.get('provider', ''))))
                    reverse = turn.get('backtranslation', metadata.get('backtranslation', ''))
                    if reverse:
                        write(_paragraph('Advisory back translation', style='Heading2'))
                        write(_paragraph(reverse, rtl=src.rtl, locale=src.bcp47))
                    for warning in turn.get('warnings', []):
                        message = warning.get('message', '') if isinstance(warning, dict) else str(warning)
                        write(_paragraph('Review ' + message))
                write('<w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="720" w:footer="720" w:gutter="0"/></w:sectPr></w:body></w:document>')
        with staged.open('r+b') as stream:
            os.fsync(stream.fileno())
        os.replace(staged, destination)
    finally:
        staged.unlink(missing_ok=True)
    return str(destination)
