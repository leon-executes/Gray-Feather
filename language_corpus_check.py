"""Explicit live all-language/style test; never run during ordinary translation."""
from __future__ import annotations
import hashlib,json,time
from pathlib import Path
from engine import Cancelled,LANG_BY_CODE,LANGUAGES,TranslationError,validate_text

PATH=Path(__file__).resolve().parent/'resources'/'test'/'translation-all-languages.json'

def cases():
 values=json.loads(PATH.read_text(encoding='utf8'))
 if not isinstance(values,list):raise ValueError('Language corpus must be a list.')
 identifiers=set()
 for value in values:
  validate_text(value['source'],'Fixture source')
  if value['id'] in identifiers:raise ValueError('Duplicate corpus identity.')
  identifiers.add(value['id'])
  if value['source_code'] not in LANG_BY_CODE or value['target_code'] not in LANG_BY_CODE or value['source_code']==value['target_code']:
   raise ValueError('Invalid or trivial language fixture.')
  if hashlib.sha256(value['source'].encode('utf8')).hexdigest()!=value['source_utf8_sha256']:
   raise ValueError('Language fixture source hash differs.')
  if not value.get('critical_semantic_predicates'):raise ValueError('Meaning criteria absent.')
 if {v['target_code'] for v in values}!={l.code for l in LANGUAGES}:raise ValueError('Registered language omitted.')
 return values

def run(service,*,styles=None,languages=None,cancel_event=None,progress=None,delay_seconds=.05):
 """Call the real facade sequentially; complete rows carry exact input criteria.

 The caller supplies a fresh keyless test data directory. No dictionary string
 matching, private history lookup, parallel request burst or semantic score.
 """
 if service.settings().get('providers') and any(config.get('key') for config in service.settings()['providers'].values()):
  raise ValueError('Use a fresh keyless benchmark profile; paid credentials must not enter this test.')
 rows=[];begin=time.perf_counter()
 values=[r for r in cases() if (styles is None or r['category'] in styles) and (languages is None or r['target_code'] in languages)]
 for index,case in enumerate(values,1):
  if cancel_event is not None and cancel_event.is_set():raise Cancelled()
  row=dict(case);start=time.perf_counter()
  try:
   value=service.translate(case['source'],case['source_code'],case['target_code'],reinforce=True,cancel_event=cancel_event)
   row.update(success=True,text=value['text'],provider=value['provider'],second_opinion=value.get('review_text',''),second_provider=value.get('review_provider',''),
     backtranslation=value.get('backtranslation',''),backtranslation_provider=value.get('backtranslation_provider',''),checks=value.get('checks',[]),trace=value.get('trace',[]),cached=value.get('cached',False))
   if value['provider'] not in ('google_web','bing_web','mymemory','lingva','libretranslate'):
    raise ValueError('A keyed route entered the free benchmark.')
  except Cancelled:raise
  except Exception as error:row.update(success=False,error=str(error))
  row['seconds']=round(time.perf_counter()-start,3);rows.append(row)
  if progress:progress(index,len(values),row)
  if delay_seconds and index<len(values):
   if cancel_event is not None:
    if cancel_event.wait(delay_seconds):raise Cancelled()
   else:time.sleep(delay_seconds)
 from app import VERSION
 return {'version':VERSION,'scope':'Actual keyless translation across a developer-constructed all-language contrastive/style corpus. Completion and comparison counts are not semantic accuracy.',
  'corpus_sha256':hashlib.sha256(PATH.read_bytes()).hexdigest(),'cases':len(rows),'successful_cases':sum(r['success'] for r in rows),
  'failed_cases':sum(not r['success'] for r in rows),'target_languages':sorted({r['target_code'] for r in rows}),
  'style_categories':sorted({r['category'] for r in rows}),'independent_comparisons':sum(bool(r.get('second_opinion')) and {r.get('provider'),r.get('second_provider')}=={'google_web','bing_web'} for r in rows),
  'advisory_reverse_outputs':sum(bool(r.get('backtranslation')) for r in rows),'elapsed_seconds':round(time.perf_counter()-begin,3),'results':rows,
  'semantic_review':{'status':'Pending complete-output inspection against each case’s explicit critical predicates. No target dictionary gold strings or universal accuracy percentage.'}}
