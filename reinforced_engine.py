"""Whole-candidate consultation and bounded source-anchored automatic repair.

The base HTTP engine remains responsible for complete responses, quotas and
transport cancellation. Local selections are strictly offline. No majority vote
or back-translation similarity is treated as evidence of semantic correctness.
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
import threading
import time
import math

import engine
from local_ai import LocalAI, LocalAIError, LocalAICancelled
from index_engine import IndexTranslator, supports as index_supports
from reinforcement import Candidate, critical_checks, reinforce, route_order

LOCAL = ('index_local', 'hy_mt_local', 'gemma_local')
FAMILIES = {**engine.PROVIDER_FAMILIES, 'index_local':'bilibili_index', 'hy_mt_local': 'tencent_hy_mt2', 'gemma_local': 'google_gemma4'}


def _warnings(source_text, translated, source_code, target_code):
    warnings = list(engine.check_translation(source_text, translated, source_code, target_code))
    # An explicitly verified grammatical dual is not a missing numeric fact.
    check = critical_checks(source_text, translated, source_code, target_code)
    if check.get('number_equivalences') and check['facts_equal']['numbers']:
        warnings = [item for item in warnings if item.code != 'numbers']
    if check['signed_numbers']['status'] == 'preserved' and check['facts_equal']['numbers']:
        warnings = [item for item in warnings if item.code != 'numbers']
    if check.get('unit_equivalences') and check['facts_equal']['units']:
        warnings = [item for item in warnings if item.code != 'units']
    critical = set(check['hard_violations']) - {'numbers','identifiers','references','currencies','units'}
    if critical:
        warnings.append(engine.TranslationWarning('critical_details','A critical source detail remains unresolved. Check this turn before using or speaking it.'))
    return warnings


class _Stop:
    def __init__(self, parent, shutdown):
        self.parent, self.shutdown, self.local = parent, shutdown, threading.Event()
    def is_set(self):
        return self.local.is_set() or self.shutdown.is_set() or bool(self.parent and self.parent.is_set())
    def wait(self, timeout=None):
        finish = None if timeout is None else time.monotonic() + timeout
        while not self.is_set():
            remaining = .05 if finish is None else min(.05, finish-time.monotonic())
            if remaining <= 0:
                return False
            self.local.wait(remaining)
        return True


class ReinforcedTranslator:
    def __init__(self, base, *, local_factory=LocalAI, index_factory=IndexTranslator, shutdown=None):
        self.base = base
        self.models = {name: local_factory(model=name) for name in LOCAL}
        self.index = index_factory(transport=base.transport, timeout=12) if index_factory else None
        self.shutdown = shutdown or threading.Event()

    def local_available(self, provider, source, target):
        model = self.models[provider]
        return model.capabilities(source, target)['supported'] and model.available()['available']

    def _candidate(self, provider, text, source, target, deadline, stop, context=''):
        engine._state(deadline, stop)
        trace = []
        if provider == 'index_web':
            if self.index is None:
                raise engine.TranslationError('settings', 'Index Translate is unavailable.')
            result = self.index.translate(text,source,target,cancel_event=stop,
                deadline_seconds=max(.1,deadline-time.monotonic()))
            return Candidate(result['text'],provider,'bilibili_index',metadata=result['metadata']), list(result['metadata'].get('trace',())), result.get('cached',False)
        if provider in LOCAL:
            try:
                result = self.models[provider].translate(text, source, target,
                    cancel_event=stop, deadline_seconds=max(.1, deadline - time.monotonic()))
                return Candidate(result['text'], provider, FAMILIES[provider], metadata=result.get('metadata', {})), list(result.get('trace', ())), False
            except LocalAICancelled as error:
                raise engine.Cancelled() from error
            except LocalAIError as error:
                raise engine.TranslationError('local', str(error)) from error
        output, cached = self.base._translate_with(provider, text, source, target,
            deadline, stop, context if provider == 'deepl' else '', None, trace)
        config = self.base.configs.get(provider)
        return Candidate(output, provider, FAMILIES.get(provider, 'unverified'),
            metadata={'glossary':bool(provider == 'deepl' and config and config.glossary_id)}), trace, cached

    def translate(self, text, source, target, *, provider='auto', cancel=None,
                  context='', backtranslate=False, deadline_seconds=60, improve=True):
        engine.validate_text(text, 'Source')
        engine.validate_text(context, 'Context', engine.MAX_CONTEXT_CHARS, True)
        if source not in engine.LANG_BY_CODE or target not in engine.LANG_BY_CODE:
            raise engine.TranslationError('language', 'Choose recognised source and target languages.')
        if source == target:
            return self.base.translate(text, source, target, cancel=cancel)
        if isinstance(deadline_seconds, bool) or not isinstance(deadline_seconds, (int,float)) or not math.isfinite(deadline_seconds) or not .1 <= deadline_seconds <= 180:
            raise engine.TranslationError('settings', 'Overall deadline must be between 0.1 and 180 seconds.')
        started = time.monotonic()
        deadline = started + min(120, max(.1, deadline_seconds))
        stop = _Stop(cancel, self.shutdown)
        trace, candidates, cached_by_provider = [], [], {}
        if provider == 'index_web' and not index_supports(source,target):
            from index_engine import build_prompt
            build_prompt(text,source,target)  # Specific measured exclusion, before any request.
        # An explicitly local engine never transmits text to an online reserve.
        if provider in LOCAL or provider == 'index_web' and not improve:
            item, events, cached = self._candidate(provider, text, source, target, deadline, stop)
            decision = reinforce(text,source,target,item,(),context=bool(context)) if improve else None
            final_text = decision.text if decision else item.text
            warnings = _warnings(text, final_text, source, target)
            original = ''
            if decision:
                events.append({'phase':'reinforcement','status':decision.method,'changed':decision.changed,
                    'provider':provider,'reasons':list(decision.reasons),'audit':decision.audit})
                if decision.changed:
                    original = item.text
                    warnings.append(engine.TranslationWarning('reinforcement_applied','A source-bound detail was repaired locally; the earlier wording is retained in Review.'))
            if stop.is_set():
                raise engine.Cancelled()
            return engine.TranslationResult(final_text, provider, source, target, tuple(warnings),
                int((time.monotonic()-started)*1000), review_text=original,review_provider=provider if original else '',
                trace=tuple(events + [{'provider':provider,'status':'offline_complete' if provider in LOCAL else 'complete'}]))
        if not improve and provider != 'reinforced':
            return self.base.translate(text,source,target,provider=None if provider in ('auto',None) else provider,
                cancel=cancel,context=context,backtranslate=backtranslate,deadline_seconds=deadline_seconds)
        enabled = [p for p in self.base.enabled_order if self.base._configured(p)]
        if self.index is not None and index_supports(source,target):
            enabled.append('index_web')
        order = list(route_order(source, target, enabled))
        if provider not in ('auto', 'reinforced', None):
            if provider not in enabled:
                raise engine.TranslationError('settings', 'Selected provider is not configured.')
            order = [provider] + [p for p in order if p != provider]
        if not order:
            order = []
        if not self.base.allow_fallback and order:
            # Consultation can compare, but never substitutes another engine
            # when the selected engine failed and fallback was disabled.
            required_primary = order[0]
        else:
            required_primary = None
        parallel = order[:1]
        if parallel:
            second = next((p for p in order[1:] if engine._independent(parallel[0], p)
                and not engine._route_warnings(p, source, target)
                and (parallel[0] in engine.KEY_PROVIDERS or p not in engine.KEY_PROVIDERS)), None)
            if second:
                parallel.append(second)
            if 'index_web' in order and 'index_web' not in parallel:
                parallel.append('index_web')
        errors = {}
        pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix='translation-consult')
        try:
            futures = {p: pool.submit(self._candidate,p,text,source,target,deadline,stop,context) for p in parallel}
            # Preserve policy order regardless of which network request finishes first.
            for p in parallel:
                try:
                    candidate, events, cached = futures[p].result()
                    candidates.append(candidate); trace.extend(events); cached_by_provider[p] = cached
                except engine.Cancelled:
                    raise
                except engine.TranslationError as error:
                    errors[p] = error; trace.append({'provider':p,'status':error.kind,'phase':'consultation'})
            if required_primary and required_primary in errors:
                raise errors[required_primary]
            if not candidates:
                reserves = [p for p in order if p not in parallel]
                # Native trials found meaning regressions in all small models.
                # They remain explicit offline choices, never silent substitutes.
                for p in reserves if self.base.allow_fallback else ():
                    try:
                        candidate, events, cached = self._candidate(p,text,source,target,deadline,stop,context)
                        candidates.append(candidate); trace.extend(events); cached_by_provider[p] = cached
                        break
                    except engine.Cancelled:
                        raise
                    except engine.TranslationError as error:
                        errors[p] = error; trace.append({'provider':p,'status':error.kind,'phase':'reserve'})
            if not candidates:
                raise next(reversed(errors.values())) if errors else engine.TranslationError('unsupported','No available engine supports this exact language pair.')
            primary = candidates[0]
            protected_glossary = bool(primary.metadata.get('glossary'))
            decision = reinforce(text, source, target, primary, candidates[1:], context=bool(context),glossary=protected_glossary)
            # Consult the larger free model only for unresolved critical details.
            # Its rewrite still has to improve demonstrable source checks.
            checks = critical_checks(text, decision.text, source, target)
            if (not context and not protected_glossary and len(text) <= 1200 and time.monotonic() + 2 < deadline
                    and self.index is not None and index_supports(source,target)
                    and checks.get('needs_consultation')):
                try:
                    fixed = self.index.repair(text, decision.text, source, target,
                        other_candidates=tuple(c.text for c in candidates if c.text != decision.text)[:2],
                        cancel_event=stop, deadline_seconds=min(12, deadline-time.monotonic()))
                    candidate = Candidate(fixed['text'], 'index_web', 'bilibili_index', metadata=fixed.get('metadata',{}))
                    candidates.append(candidate)
                    decision = reinforce(text, source, target, primary, candidates[1:])
                    trace.append({'provider':'index_web','status':'repair_evaluated','selected':decision.text == candidate.text and decision.changed})
                except engine.Cancelled:
                    raise
                except engine.TranslationError:
                    trace.append({'provider':'index_web','status':'repair_unavailable'})
            if stop.is_set():
                raise engine.Cancelled()
            warnings = _warnings(text, decision.text, source, target)
            if decision.provider not in LOCAL:
                warnings += engine._route_warnings(decision.provider, source, target)
            warnings += list(engine.source_review_aids(text, source))
            if protected_glossary or context:
                warnings.append(engine.TranslationWarning('review_conditions','Alternatives do not share the selected glossary or context; the primary wording was preserved.'))
            trace.append({'phase':'reinforcement','status':decision.method,'changed':decision.changed,
                'provider':decision.provider,'reasons':list(decision.reasons),'audit':decision.audit})
            if decision.changed:
                warnings.append(engine.TranslationWarning('reinforcement_applied','The main translation was improved using source-anchored checks; the earlier wording is retained in Review.'))
            alternative = next((c for c in candidates if c.text != decision.text), None)
            reverse = reverse_provider = ''
            if backtranslate and time.monotonic()+1 < deadline:
                reverse_order = [p for p in route_order(target, source, enabled)
                    if engine._independent(decision.provider, p)
                    and (decision.provider in engine.KEY_PROVIDERS or p not in engine.KEY_PROVIDERS)]
                if decision.provider in enabled and engine.provider_supports(decision.provider, target, source):
                    reverse_order.append(decision.provider)
                if not self.base.allow_fallback:
                    reverse_order = reverse_order[:1]
                for p in reverse_order:
                    try:
                        reverse_candidate, events, _ = self._candidate(p,decision.text,target,source,deadline,stop)
                        reverse, reverse_provider = reverse_candidate.text, p; trace.extend(events); break
                    except engine.Cancelled:
                        raise
                    except engine.TranslationError:
                        continue
                if reverse:
                    warnings.append(engine.TranslationWarning('backtranslation','Back translation is advisory; it does not certify meaning.'))
            if stop.is_set():
                raise engine.Cancelled()
            return engine.TranslationResult(decision.text, decision.provider, source, target, tuple(warnings),
                int((time.monotonic()-started)*1000), alternative.text if alternative else '',
                alternative.provider if alternative else '', reverse, reverse_provider, tuple(trace),
                bool(cached_by_provider.get(decision.provider)) and not decision.changed)
        finally:
            stop.local.set()
            pool.shutdown(wait=True, cancel_futures=True)
