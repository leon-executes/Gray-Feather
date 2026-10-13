"""Deterministic local performance benchmark; no providers, fabricated accuracy or user data."""
import json
from pathlib import Path
import statistics
import tempfile
import time
import uuid
import engine

def distribution(values):
    ordered = sorted(values)
    return {'samples': len(values), 'p50_ms': round(statistics.median(ordered), 3),
            'p95_ms': round(ordered[min(len(ordered)-1, int(len(ordered)*.95))], 3),
            'maximum_ms': round(max(ordered), 3)}

def measure(operation, n):
    timings = []
    for _ in range(n):
        start = time.perf_counter()
        operation()
        timings.append((time.perf_counter()-start)*1000)
    return distribution(timings)

def run(report):
    directory = Path(report).parent / '.benchmark-temp'
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=directory) as task:
        store = engine.Store(Path(task)/'history.sqlite3')
        conversation = store.new_conversation('Synthetic performance corpus')
        identity = conversation['id']
        source = 'Temperature 38.5 C at 14:30. Reference GF-2198. Email test@example.com.'
        source_sha = source
        # Use one transactional snapshot to populate realistic history size.
        turns = [{'id': uuid.uuid4().hex, 'source_lang': 'en', 'target_lang': 'fr', 'raw_source': source,
                  'reviewed_source': source, 'translated_text': 'Fixture output for storage only.',
                  'speaker': str(1+i%2), 'provider': 'fixture'} for i in range(1000)]
        start = time.perf_counter()
        store.save_conversation({'id':identity,'revision':conversation['revision'],'turns':turns})
        populate_ms = (time.perf_counter()-start)*1000
        append = measure(lambda: store.save_turn(identity,'en','fr',source,translated_text='Fixture output',provider='fixture'),30)
        load = measure(lambda: store.get_conversation(identity),30)
        checks = measure(lambda: engine.check_translation(source,source,'en','fr'),200)
        cache_preserves = source == source_sha
        backup = measure(lambda: store.backup(Path(task)/'backup.sqlite3'),5)
        result = {'scope':'Local application operations only; synthetic corpus; no translation model accuracy measurement.',
                  'turns':1030,'initial_1000_turn_transaction_ms':round(populate_ms,3),
                  'append_full_durability':append,'load_1030_turns':load,'fact_review':checks,
                  'verified_backup':backup,'source_preserved':cache_preserves,
                  'database_bytes':(Path(task)/'history.sqlite3').stat().st_size}
    Path(report).write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))

if __name__ == '__main__':
    import sys
    run(sys.argv[1] if len(sys.argv)>1 else 'verification/local-performance.json')
