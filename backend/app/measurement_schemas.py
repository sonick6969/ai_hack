from typing import Literal

from pydantic import Field, model_validator

from .schemas import StrictModel

QUALITY_KEYS = {'machine', 'address', 'symptoms', 'confirmed_facts', 'history', 'parts_warehouse', 'purpose', 'uncertainties'}


class MeasurementStart(StrictModel):
    participant: str = Field(min_length=2, max_length=80)
    participant_kind: Literal['dispatcher', 'tester', 'automated'] = 'tester'
    method: Literal['manual', 'pilot']
    context: Literal['controlled', 'field', 'practice'] = 'practice'
    comparison_key: str = Field(default='', max_length=100)
    process_description: str = Field(min_length=8, max_length=1000)
    ticket_id: int | None = Field(default=None, ge=1)
    client_id: str = Field(min_length=8, max_length=100, pattern=r'^[a-zA-Z0-9_-]+$')
    request_id: str = Field(min_length=8, max_length=100, pattern=r'^[a-zA-Z0-9_-]+$')

    @model_validator(mode='after')
    def context_is_valid(self):
        if self.method == 'pilot' and self.ticket_id is None:
            raise ValueError('Для пилота выберите заявку.')
        if self.method == 'manual' and self.ticket_id is not None:
            raise ValueError('Ручной замер не привязывается к подсказкам пилота.')
        if self.context == 'controlled' and not self.comparison_key:
            raise ValueError('Для сравнительного эксперимента нужен ключ пары задач.')
        return self


class Pulse(StrictModel):
    client_id: str = Field(min_length=8, max_length=100)
    sequence: int = Field(ge=1)
    activations: int = Field(default=0, ge=0, le=1000000)


class MeasurementTransition(StrictModel):
    client_id: str = Field(min_length=8, max_length=100)
    revision: int = Field(ge=1)
    state: Literal['working', 'waiting', 'paused', 'finished', 'abandoned']
    reason: Literal['', 'client', 'stock', 'senior', 'other'] = ''
    outcome: Literal['ready', 'blocked', 'manager', 'abandoned'] | None = None
    note: str = Field(default='', max_length=2000)


class MeasurementArtifact(StrictModel):
    client_id: str = Field(min_length=8, max_length=100)
    revision: int = Field(ge=1)
    text: str = Field(min_length=20, max_length=30000)


class MeasurementReview(StrictModel):
    reviewer: str = Field(min_length=2, max_length=80)
    reviewer_kind: Literal['engineer', 'test_reviewer'] = 'test_reviewer'
    artifact_hash: str = Field(min_length=64, max_length=64)
    checks: dict[str, bool]
    critical_errors: list[Literal['wrong_equipment', 'missing_answer', 'incompatible_part', 'missing_reserve', 'missing_transfer', 'missing_approval', 'unsafe_instruction', 'unsupported_diagnosis', 'wrong_decision']]
    note: str = Field(min_length=5, max_length=3000)

    @model_validator(mode='after')
    def all_sections_reviewed(self):
        if set(self.checks) != QUALITY_KEYS:
            raise ValueError('Проверьте все восемь разделов карточки.')
        return self
