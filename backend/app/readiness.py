from .rules import questions_for, warranty_for


def assess(ticket, data, messages, analysis, matching, equipment, plans, duplicates):
    questions = questions_for(analysis, data)
    at = max((m['received_at'] for m in messages), default=ticket['created_at'])
    warranty = warranty_for(equipment, analysis, at)
    approval = data.get('approval')
    checks = []

    def check(key, label, passed, detail, rule):
        checks.append({'key': key, 'label': label, 'passed': bool(passed), 'detail': detail, 'rule': rule})

    check('registry', 'Машина в реестре', equipment and ticket['state'] == 'open',
          'Выезд возможен только на обслуживаемую машину. Вне реестра — менеджеру.', 'П-1, П-2')
    check('identity', 'Машина и адрес подтверждены', equipment and data.get('equipment_confirmed') and data.get('address_confirmed'),
          'Сверьте шильдик и адрес с клиентом, затем подтвердите выбор.', 'П-1')
    identity_consistent = matching['status'] not in ('conflict', 'unknown') and (not equipment or any(c['id'] == equipment['id'] for c in matching['candidates']))
    check('identity_conflict', 'Противоречия идентификации разрешены',
          identity_consistent or (equipment and len(data.get('identity_resolution', '')) >= 5),
          matching['reason'] if matching['status'] in ('conflict', 'unknown') else 'Выбранная машина должна соответствовать исходным данным; ручное исправление требует объяснения.', 'П-1, П-2')
    check('symptom', 'Симптом подтверждён диспетчером', data.get('symptom_confirmed') and len(data.get('symptom', '').strip()) >= 8,
          'Запишите наблюдаемый симптом. Предположение о причине не заменяет описание.', 'П-4')
    unresolved = [q['question'] for q in questions if not q['resolved']]
    check('questions', 'Обязательные уточнения получены', not unresolved,
          '; '.join(unresolved) if unresolved else 'Все обязательные ответы записаны.', 'П-5')
    check('duplicates', 'Повторы разобраны', not duplicates or len(data.get('duplicate_resolution', '')) >= 5,
          f'Возможных связанных заявок: {len(duplicates)}. Объедините или запишите причину отдельного выезда.' if duplicates else 'Открытых кандидатов на объединение нет.', 'П-3')
    purpose_ok = data.get('purpose') in ('diagnostic', 'repair', 'maintenance') and len(data.get('purpose_note', '')) >= 8 and data.get('plan_confirmed')
    if data.get('purpose') in ('repair', 'maintenance') and not plans:
        purpose_ok = False
    check('purpose', 'Цель и состав выезда согласованы', purpose_ok,
          'Для выезда без деталей выберите диагностику и подтвердите план. Ремонт и замена требуют плана деталей.', 'П-4')
    check('compatibility', 'Детали совместимы с моделью', all(p['compatible'] for p in plans),
          'Проверка по справочнику моделей, без взаимозаменяемости разных серий прокладок.', 'П-7')
    check('reservation', 'Все запланированные детали зарезервированы', all(p['reserved_quantity'] == p['quantity'] for p in plans),
          'Резерв должен быть подтверждён в пилоте. Свободный остаток сам по себе не является резервом.', 'П-8')
    transfer_ok = all(not p['transfer_required'] or (p['transfer_confirmed'] and p['available_on'] and (data.get('visit_date') or '') >= p['available_on']) for p in plans)
    check('transfer', 'Склад и срок получения согласованы', transfer_ok,
          'Между городами — 1 рабочий день. Нужны согласованный перевоз и дата визита не раньше получения.', 'П-8')
    check('approval', 'Гарантийное согласование получено', not warranty['required'] or (approval and approval.get('revision') == ticket['revision']),
          warranty['reason'] + ('. Запишите согласование старшего инженера.' if warranty['required'] else ''), 'П-9')
    check('safe_actions', 'Запрос самостоятельного ремонта обработан', not analysis['unsafe_request'] or bool(data.get('answers', {}).get('general_context')),
          'Инструкции по разборке не передаются. Зафиксируйте симптом и согласуйте выезд.', 'П-10')
    blockers = [c for c in checks if not c['passed']]
    can_prepare = not blockers
    ready = can_prepare and ticket['prepared_revision'] == ticket['revision']
    return {'can_prepare': can_prepare, 'ready': ready, 'checks': checks, 'blockers': blockers,
            'passed': len(checks) - len(blockers), 'total': len(checks),
            'questions': questions, 'warranty': warranty,
            'status': 'ready' if ready else 'manager' if ticket['state'] == 'manager' else 'review' if can_prepare else 'blocked'}
