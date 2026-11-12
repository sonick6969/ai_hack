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


def payload(facts):
    return {'status': 'completed', 'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': json.dumps({'facts': facts})}]}]}


def test_llm_response_schema_and_grounded_fields(enabled):
    def handler(request):
        body = json.loads(request.content)
        assert body['store'] is False and body['text']['format']['strict'] is True
        assert body['model'] == 'test-model' and request.url.path == '/v1/responses'
        return httpx.Response(200, json=payload([{'field': 'general_context', 'value': 'дребезжание на нагреве', 'quote': 'Слышно дребезжание на нагреве'}]))
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
