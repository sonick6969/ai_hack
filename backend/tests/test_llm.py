import json

import httpx
import pytest

from backend.app.extraction import extract, local_extract


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setenv('LLM_ENABLED', 'true')
    monkeypatch.setenv('OPENAI_API_KEY', 'test-key-not-real')
    monkeypatch.setenv('LLM_MODEL', 'test-model')
    monkeypatch.setenv('LLM_TIMEOUT_SECONDS', '0.1')


def payload(facts, assertions=None, uncertainties=None):
    facts = [{'machine': None, **f} for f in facts]
    data = {'facts': facts, 'assertions': assertions or [], 'uncertainties': uncertainties or []}
    return {'status': 'completed', 'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': json.dumps(data)}]}]}


def test_llm_response_schema_and_grounded_fields(enabled):
    def handler(request):
        body = json.loads(request.content)
        assert body['store'] is False and body['text']['format']['strict'] is True
        assert body['model'] == 'test-model' and request.url.path == '/v1/responses'
        return httpx.Response(200, json=payload([{'field': 'general_context', 'value': 'дребезжание на нагреве', 'quote': 'Слышно дребезжание на нагреве'}],
            [{'symptom':'noise', 'status':'current', 'quote':'Слышно дребезжание на нагреве', 'machine':None}]))
    result = extract('Слышно дребезжание на нагреве', transport=httpx.MockTransport(handler))
    assert result['engine'] == 'local+llm' and result['llm_status'] == 'ok'
    assert result['facts']['general_context'] == 'дребезжание на нагреве'
    assert not any(k in result for k in ('equipment_id', 'ready', 'diagnosis', 'part'))


@pytest.mark.parametrize('response', [
    {'status': 'incomplete', 'output': []},
    {'status': 'completed', 'output': [{'type': 'message', 'content': [{'type': 'refusal', 'refusal': 'No'}]}]},
    {'status': 'completed', 'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': 'not json'}]}]},
    payload([{'field': 'leak_location', 'value': 'справа', 'quote': 'вода справа'}]),
    payload([{'field': 'error_code', 'value': 'сломанный насос', 'quote': 'сломанный насос'}]),
    payload([{'field': 'ready', 'value': 'true', 'quote': 'true'}]),
])
def test_invalid_refused_and_hallucinated_llm_fall_back(enabled, response):
    text = 'На машине 205 течь снизу после приготовления. Сказали: сломанный насос.'
    result = extract(text, transport=httpx.MockTransport(lambda r: httpx.Response(200, json=response)))
    assert result['llm_status'] == 'invalid_or_error_fallback'
    assert result['facts'] == local_extract(text)['facts']


def test_llm_timeout_falls_back_without_losing_message(enabled):
    def timeout(request):
        raise httpx.ReadTimeout('test timeout', request=request)
    result = extract('На C200, номер 205, течёт справа.', transport=httpx.MockTransport(timeout))
    assert result['llm_status'] == 'timeout_fallback'
    assert result['serials'] == ['205']


def test_http_error_falls_back(enabled):
    result = extract('C200 гудит', transport=httpx.MockTransport(lambda r: httpx.Response(503, text='service unavailable')))
    assert result['llm_status'] == 'invalid_or_error_fallback' and result['engine'] == 'local'


def test_missing_key_is_explicit(monkeypatch):
    monkeypatch.setenv('LLM_ENABLED', 'true'); monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    assert extract('Течёт снизу')['llm_status'] == 'not_configured'


def test_llm_can_classify_a_new_observation_instead_of_only_adding_facts(enabled):
    text = 'На машине 119 эспрессо едва сочится из носиков.'
    assert local_extract(text)['symptoms'] == ['unknown']
    data = payload([], [{'symptom': 'flow', 'status': 'current', 'quote': text, 'machine': '119'}])
    result = extract(text, transport=httpx.MockTransport(lambda r: httpx.Response(200, json=data)))
    assert result['symptoms'] == ['flow'] and result['llm_status'] == 'ok'
    assert result['assertions'][0]['provider'] == 'llm'


def test_llm_current_denied_past_and_suspected_symptoms_are_used(enabled):
    text = 'Раньше слабый поток. Машина 205 больше не течёт. Теперь гудит. Возможно, пар слабый.'
    assertions = [
        {'symptom': 'flow', 'status': 'past', 'quote': 'Раньше слабый поток.', 'machine': '205'},
        {'symptom': 'leak', 'status': 'negated', 'quote': 'Машина 205 больше не течёт.', 'machine': '205'},
        {'symptom': 'noise', 'status': 'current', 'quote': 'Теперь гудит.', 'machine': '205'},
        {'symptom': 'steam', 'status': 'suspected', 'quote': 'Возможно, пар слабый.', 'machine': '205'},
    ]
    result = extract(text, transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload([], assertions))))
    assert result['llm_status'] == 'ok' and result['symptoms'] == ['noise']
    assert result['negated_symptoms'] == ['leak'] and result['suspected_symptoms'] == ['steam']
    assert result['past_symptoms'] == ['flow']


def test_llm_cannot_attach_a_broad_quote_to_the_wrong_machine(enabled):
    text = 'Машина 205 не течёт. Машина 119 течёт.'
    assertions = [{'symptom':'leak','status':'current','quote':text,'machine':'205'}]
    result = extract(text,transport=httpx.MockTransport(lambda r:httpx.Response(200,json=payload([],assertions))))
    assert result['llm_status'] == 'invalid_or_error_fallback'


def test_llm_separate_machine_fragments_are_accepted(enabled):
    text = 'Машина 205 не течёт. Машина 119 гудит.'
    assertions = [{'symptom':'leak','status':'negated','quote':'Машина 205 не течёт.','machine':'205'},
                  {'symptom':'noise','status':'current','quote':'Машина 119 гудит.','machine':'119'}]
    result = extract(text,transport=httpx.MockTransport(lambda r:httpx.Response(200,json=payload([],assertions))))
    assert result['llm_status'] == 'ok' and result['symptoms'] == ['noise']
    assert next(a for a in result['assertions'] if a['status'] == 'current')['machine'] == '119'


@pytest.mark.parametrize('assertion', [
    {'symptom': 'leak', 'status': 'current', 'quote': 'Машина 205 не течёт', 'machine': '205'},
    {'symptom': 'leak', 'status': 'current', 'quote': 'течёт', 'machine': '205'},
    {'symptom': 'leak', 'status': 'negated', 'quote': 'несуществующий фрагмент', 'machine': '205'},
    {'symptom': 'noise', 'status': 'current', 'quote': 'гудит', 'machine': '999'},
    {'symptom': 'diagnosis', 'status': 'current', 'quote': 'гудит', 'machine': '205'},
])
def test_invalid_symptom_evidence_falls_back_atomically(enabled, assertion):
    text = 'Машина 205 не течёт, но гудит.'
    result = extract(text, transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload([], [assertion]))))
    assert result['llm_status'] == 'invalid_or_error_fallback'
    assert result['symptoms'] == ['noise']


def test_strict_schema_requires_all_fields_and_forbids_operations():
    from backend.app.extraction import LLMExtraction
    schema = LLMExtraction.model_json_schema()
    assert schema['additionalProperties'] is False
    assert set(schema['required']) == {'facts', 'assertions', 'uncertainties'}
    for value in schema['$defs'].values():
        assert value['additionalProperties'] is False
        assert set(value['required']) == set(value['properties'])
