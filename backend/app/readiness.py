from .answers import answer_record, substantive
from .rules import questions_for, warranty_for


def assess(ticket, data, messages, analysis, matching, equipment, plans, duplicates):
    questions = questions_for(analysis, data)
    at = max((m['received_at'] for m in messages), default=ticket['created_at'])
    warranty = warranty_for(equipment, analysis, at)
    approval = data.get('approval')
    checks = []

    def check(key, label, passed, detail, rule, action, applicable=True, basis='case', reason=None):
        state = 'not_required' if not applicable else 'completed' if passed else 'action_required'
        checks.append({'key': key, 'label': label, 'state': state, 'passed': state == 'completed',
                       'detail': detail, 'reason': reason or (detail if state == 'action_required' else ''),
                       'next_action': action if state == 'action_required' else '', 'rule': rule, 'basis': basis})

    check('registry', 'Машина в реестре', equipment and ticket['state'] == 'open',
          'Выезд возможен только на обслуживаемую машину. Вне реестра — менеджеру.', 'П-1, П-2', 'Уточните машину')
    check('identity', 'Машина и адрес подтверждены', equipment and data.get('equipment_confirmed') and data.get('address_confirmed'),
          'Машина или адрес ещё не подтверждены клиентом.', 'П-1', 'Подтвердите машину и адрес')
    identity_consistent = matching['status'] not in ('conflict', 'unknown') and (not equipment or any(c['id'] == equipment['id'] for c in matching['candidates']))
    check('identity_conflict', 'Противоречия идентификации разрешены',
          identity_consistent or (equipment and substantive(data.get('identity_resolution', ''), 5)),
          matching['reason'] if matching['status'] in ('conflict', 'unknown') else 'Выбранная машина не соответствует исходным данным; требуется объяснение.',
          'П-1, П-2', 'Разрешите противоречие в данных машины', applicable=not identity_consistent)
    symptom_content = substantive(data.get('symptom', ''), 8)
    check('symptom', 'Симптом подтверждён диспетчером', data.get('symptom_confirmed') and symptom_content,
          'Нужно содержательное описание наблюдаемого симптома; неизвестный ответ его не заменяет.' if not symptom_content else
          'Описание записано, но подтверждение диспетчера ещё не отмечено.', 'П-4',
          'Подтвердите наблюдаемый симптом' if symptom_content else 'Уточните наблюдаемый симптом')
    unresolved = [q['question'] for q in questions if not q['resolved']]
    question_bases = {q['basis'] for q in questions if not q['resolved']} or {q['basis'] for q in questions}
    question_basis = 'mixed' if len(question_bases) > 1 else next(iter(question_bases), 'product')
    check('questions', 'Обязательные уточнения получены', not unresolved,
          '; '.join(unresolved) if unresolved else 'Все обязательные ответы записаны.',
          'П-5' if any(q['basis'] == 'case' for q in questions) else 'Контроль диспетчера',
          'Уточните точный код ошибки' if any(q['key'] == 'error_code' and not q['resolved'] for q in questions) else 'Получите ответ клиента',
          applicable=bool(questions), basis=question_basis)
    check('duplicates', 'Повторы разобраны', not duplicates or substantive(data.get('duplicate_resolution', ''), 5),
          f'Возможных связанных заявок: {len(duplicates)}. Объедините или запишите причину отдельного выезда.' if duplicates else 'Открытых кандидатов на объединение нет.',
          'П-3', 'Проверьте повторы обращений', applicable=bool(duplicates))
    purpose_ok = data.get('purpose') in ('diagnostic', 'repair', 'maintenance') and substantive(data.get('purpose_note', ''), 8) and data.get('plan_confirmed')
    check('purpose', 'Цель и состав выезда согласованы', purpose_ok,
          'Опишите и согласуйте работы и ограничения. Ремонт и обслуживание могут выполняться без замены деталей.',
          'Контроль диспетчера · по П-4', 'Согласуйте цель и состав работ', basis='product')
    check('compatibility', 'Детали совместимы с моделью', all(p['compatible'] for p in plans),
          'Проверка по справочнику моделей; без деталей проверка не требуется.', 'П-7', 'Проверьте совместимость деталей', applicable=bool(plans))
    lacking_stock = [p for p in plans if p['quantity'] - p['reserved_quantity'] > p['free']]
    check('reservation', 'Все запланированные детали зарезервированы', all(p['reserved_quantity'] == p['quantity'] for p in plans),
          'Нет свободного остатка на выбранном складе: ' + ', '.join(p['sku'] + ' · ' + p['warehouse'] for p in lacking_stock) if lacking_stock else
          'Резерв ещё не подтверждён. Доступный остаток сам по себе не является резервом.',
          'П-8', 'Проверьте детали и выберите другой склад' if lacking_stock else 'Зарезервируйте детали', applicable=bool(plans))
    transfer_ok = all(not p['transfer_required'] or (p['transfer_confirmed'] and p['available_on'] and (data.get('visit_date') or '') >= p['available_on']) for p in plans)
    check('transfer', 'Склад и срок получения согласованы', transfer_ok,
          'Между городами — 1 рабочий день. Нужны согласованный перевоз и дата визита не раньше получения.',
          'П-8', 'Согласуйте перевоз и дату визита', applicable=any(p['transfer_required'] for p in plans))
    check('approval', 'Гарантийное согласование получено', not warranty['required'] or
          (approval and approval.get('revision') == ticket['revision'] and substantive(approval.get('name', '')) and substantive(approval.get('note', ''), 5)),
          warranty['reason'] + ('. Запишите согласование старшего инженера.' if warranty['required'] else ''),
          'П-9', 'Получите согласование старшего инженера', applicable=warranty['required'])
    check('safe_actions', 'Запрос самостоятельного ремонта обработан', answer_record(data, 'general_context')['status'] == 'answered',
          'Инструкции по разборке не передаются. Зафиксируйте содержательный симптом и согласуйте выезд.',
          'П-10', 'Уточните симптом вместо самостоятельного ремонта', applicable=analysis['unsafe_request'])
    blockers = [c for c in checks if c['state'] == 'action_required']
    can_prepare = not blockers
    ready = can_prepare and ticket['prepared_revision'] == ticket['revision']
    return {'can_prepare': can_prepare, 'ready': ready, 'checks': checks, 'blockers': blockers,
            'passed': sum(c['state'] == 'completed' for c in checks),
            'total': sum(c['state'] != 'not_required' for c in checks),
            'not_required': sum(c['state'] == 'not_required' for c in checks),
            'questions': questions, 'warranty': warranty,
            'status': 'ready' if ready else 'manager' if ticket['state'] == 'manager' else 'review' if can_prepare else 'blocked'}
