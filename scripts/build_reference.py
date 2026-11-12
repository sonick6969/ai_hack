"""Freeze source-backed labels. Does NOT import the application parser or matcher.

Expected entity facts below are transcribed from Excel cells. The verifier in evaluate.py
checks identifiers against the original text and independent registry joins. Symptom
interpretation labels are explicitly provisional, not an expert gold standard.
"""
import hashlib
import json
from pathlib import Path

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'Данные_к_кейсу_06 (1).xlsx'
# id: candidate IDs, decision, literal model/serial/code fields, provisional symptom classes.
CASE = [
    (['EQ01','EQ02'],'ambiguous',[],[],[],['leak']),
    (['EQ03'],'unique',[],[],[],['error']),
    (['EQ04'],'unique',['C300'],[],[],['noise']),
    (['EQ05'],'exact',[],['211'],[],['error']),
    (['EQ06'],'exact',[],['119'],[],['flow']),
    (['EQ02'],'exact',[],['205'],[],['leak']),
    (['EQ08','EQ09'],'ambiguous',[],[],[],['flow']),
    (['EQ04'],'unique',[],[],[],['request']),
    ([], 'unknown',[],[],[],['unknown']),
    (['EQ03'],'unique',[],[],[],['error']),
    (['EQ10'],'unique',[],[],[],['leak']),
    (['EQ02'],'exact',[],['205'],[],['leak']),
    (['EQ11'],'exact',[],['207'],[],['maintenance']),
    (['EQ12'],'unique',[],[],[],['steam']),
    (['EQ07'],'exact',[],['214'],[],['noise']),
    (['EQ05'],'unique',[],[],[],['error']),
    (['EQ08'],'unique',[],[],[],['flow']),
    ([], 'unknown',[],['270'],[],['leak']),
    (['EQ03'],'unique',[],[],['E07'],['error']),
    ([], 'unknown',['C200'],['230'],[],['unknown']),
    (['EQ10'],'unique',[],[],['E11'],['error']),
    (['EQ09'],'unique',[],[],['E03'],['error']),
    (['EQ02'],'exact',[],['205'],[],['steam']),
]
CHALLENGES = [
    ('Кафе «Кедр»','На шильдике 205, вода справа после приготовления.', ['EQ02'],'exact',[],['205'],[],['leak']),
    ('Кафе «Кедр»','Одна из двух машин шумит, номер пока не знаем.', ['EQ01','EQ02'],'ambiguous',[],[],[],['noise']),
    ('Кафе «Кедрр»','C200, номер 205, вода справа.', ['EQ02'],'exact',['C200'],['205'],[],['leak']),
    ('Кафе «Кедр»','Модель С200, серийный номер 205. Постоянно гудит.', ['EQ02'],'exact',['C200'],['205'],[],['noise']),
    ('Кафе «Кедр»','Модель C999, течёт снизу.', [],'unknown',['C999'],[],[],['leak']),
    ('Кафе «Кедр»','Номер 205, модель C300, течь.', ['EQ02'],'conflict',['C300'],['205'],[],['leak']),
    ('Гостиница «Север»','Вторая машина, номер 270, течёт из-под поддона.', [],'unknown',[],['270'],[],['leak']),
    ('Кафе «Кедр»','Машина 101 и номер 205 обе текут.', ['EQ01','EQ02'],'conflict',[],['101','205'],[],['leak']),
    ('Кафе «Кедр»','Номер 108, кофе не выдаёт.', ['EQ03'],'conflict',[],['108'],[],['error']),
    ('Пекарня «Зерно»','Напор слабый на Садовй. На Ленина всё в порядке.', ['EQ08'],'unique',[],[],[],['flow']),
    ('Кафе «Угол»','C100, s/n 119. С утра кофе идёт медленно, работ не было.', ['EQ06'],'exact',['C100'],['119'],[],['flow']),
    ('Кафе «Угол»','Машина 999, не готовит кофе.', [],'unknown',[],['999'],[],['error']),
    ('Пекарня «Зерно»','На Ленина ошибка Е03, вода в баке есть.', ['EQ09'],'unique',[],[],['E03'],['error']),
    ('Кафе «Лист»','Машина 310 булькает на нагреве.', ['EQ04'],'exact',[],['310'],[],['noise']),
    ('Кафе «Угол»','Серийный номер 119, C100. Со вчера кофе почти не льётся.', ['EQ06'],'exact',['C100'],['119'],[],['flow']),
]


def main():
    wb = load_workbook(SOURCE, data_only=True)
    registry = {str(row[0].value): {'serial': str(row[4].value), 'model': str(row[3].value),
                 'client': row[1].value, 'source_ref': f'Оборудование!A{row[0].row}:H{row[0].row}'}
                for row in wb['Оборудование'].iter_rows(min_row=4) if row[0].value}
    records = []
    for i, row in enumerate(wb['Заявки'].iter_rows(min_row=4)):
        if not row[0].value:
            continue
        ids, status, models, serials, codes, symptoms = CASE[i]
        records.append({'id': str(row[0].value), 'split': 'case', 'sender': row[3].value, 'text': row[4].value,
                        'source_ref': f'Заявки!D{row[0].row}:E{row[0].row}',
                        'expected_ids': ids, 'expected_status': status, 'fields': {'models': models, 'serials': serials, 'codes': codes},
                        'symptoms_provisional': symptoms})
    for i, (sender, text, ids, status, models, serials, codes, symptoms) in enumerate(CHALLENGES, 1):
        records.append({'id': f'NEW-{i:02d}', 'split': 'challenge', 'sender': sender, 'text': text,
                        'source_ref': f'scripts/build_reference.py:CHALLENGES[{i-1}]', 'expected_ids': ids,
                        'expected_status': status, 'fields': {'models': models, 'serials': serials, 'codes': codes},
                        'symptoms_provisional': symptoms})
    for item in records:
        item['registry_evidence'] = [{**registry[k], 'id': k} for k in item['expected_ids']]
        item['reviewer'] = None
        item['reviewed_at'] = None
    document = {'version': 1, 'source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                'label_status': 'Literal identifiers and registry cells are machine-verifiable; symptom classes and address/client interpretation await independent expert review.',
                'records': records}
    (ROOT / 'evaluation' / 'reference.json').write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n')
    wb.close()
    print(f'Frozen {len(records)} examples, including all 23 original messages and 15 additional cases.')


if __name__ == '__main__':
    main()
