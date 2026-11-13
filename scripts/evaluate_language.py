"""Read-only evaluation of the new language corpus against the captured original run."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.extraction import local_extract


def correct(case, result):
    if set(result['symptoms']) - {'unknown'} != set(case['current']):
        return False
    for expected, field in [('negated', 'negated_symptoms'), ('past', 'past_symptoms'), ('suspected', 'suspected_symptoms')]:
        if not set(case.get(expected, [])) <= set(result.get(field, [])):
            return False
    if case.get('uncertain') and not result.get('uncertainties'):
        return False
    for machine, expected in case.get('machines', {}).items():
        actual = {a['symptom'] for a in result['assertions'] if a['machine'] == machine and a['status'] == 'current'}
        if actual != set(expected):
            return False
    return True


def main():
    cases = json.loads((ROOT / 'evaluation/language_cases.json').read_text())
    captured = json.loads((ROOT / 'evaluation/language_comparison.json').read_text())
    old = {r['id']: r for r in captured['results']}
    rows = [{'id': case['id'], 'before_pass': old[case['id']]['before_pass'],
             'after_pass': correct(case, local_extract(case['text']))} for case in cases]
    summary = {'mode': 'local; no LLM requests', 'baseline_commit': captured['baseline_commit'],
               'cases': len(rows), 'before_pass': sum(r['before_pass'] for r in rows),
               'after_pass': sum(r['after_pass'] for r in rows), 'current_errors': [r['id'] for r in rows if not r['after_pass']]}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return int(bool(summary['current_errors']))


if __name__ == '__main__':
    raise SystemExit(main())
