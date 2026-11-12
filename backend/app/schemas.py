from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class NewMessage(StrictModel):
    sender: str = Field(min_length=2, max_length=200)
    text: str = Field(min_length=3, max_length=10000)
    channel: Literal['Ручной ввод', 'Почта', 'Звонок', 'Мессенджер'] = 'Ручной ввод'
    received_at: datetime | None = None
    request_id: str | None = Field(default=None, min_length=8, max_length=100, pattern=r'^[a-zA-Z0-9_-]+$')


class Revision(StrictModel):
    revision: int = Field(ge=1)


ANSWER_KEYS = {'leak_location', 'leak_timing', 'onset', 'after_work', 'error_code', 'noise_context', 'steam_context', 'general_context'}


class TicketPatch(Revision):
    issue_types: list[Literal['leak', 'flow', 'error', 'noise', 'steam', 'maintenance', 'request', 'unknown']] | None = Field(default=None, min_length=1, max_length=8)
    equipment_id: str | None = Field(default=None, max_length=30)
    equipment_confirmed: bool | None = None
    address_confirmed: bool | None = None
    symptom: str | None = Field(default=None, max_length=3000)
    symptom_confirmed: bool | None = None
    answers: dict[str, str] | None = None
    purpose: Literal['diagnostic', 'repair', 'maintenance'] | None = None
    purpose_note: str | None = Field(default=None, max_length=2000)
    plan_confirmed: bool | None = None
    visit_date: date | None = None
    uncertainties: str | None = Field(default=None, max_length=3000)
    identity_resolution: str | None = Field(default=None, max_length=1000)
    duplicate_resolution: str | None = Field(default=None, max_length=1000)

    @field_validator('answers')
    @classmethod
    def validate_answers(cls, value):
        if value is not None and (set(value) - ANSWER_KEYS or any(len(v) > 1000 for v in value.values())):
            raise ValueError('Неизвестное уточнение или ответ длиннее 1000 символов')
        return value


class PlanCreate(Revision):
    sku: str = Field(min_length=1, max_length=30)
    warehouse: Literal['Москва', 'Тула']
    quantity: int = Field(default=1, ge=1, le=100)


class Approval(Revision):
    name: str = Field(min_length=3, max_length=150)
    note: str = Field(min_length=5, max_length=1000)


class Merge(Revision):
    target_id: int = Field(ge=1)
    target_revision: int = Field(ge=1)
    reason: str = Field(min_length=5, max_length=1000)


class Transfer(Revision):
    available_on: date
    note: str = Field(min_length=5, max_length=1000)


class Manager(Revision):
    note: str = Field(min_length=5, max_length=1000)
