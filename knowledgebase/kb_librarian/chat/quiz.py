"""Parse the model's quiz reply defensively into a validated list of questions.

The prompt asks for strict JSON, but a model may still wrap it in code fences or add a sentence
around it; anything that is not one well-formed quiz of the expected shape is a parse error the
runner turns into ``ChatAnswer.error`` (the API answers 502), never a half-quiz.
"""

import json
from typing import Annotated

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

MAX_QUESTIONS, MAX_OPTIONS = 5, 6
Option = Annotated[str, Field(min_length=1, max_length=400)]


class QuizQuestion(BaseModel):
    q: Annotated[str, Field(min_length=1, max_length=600)]
    options: Annotated[list[Option], Field(min_length=2, max_length=MAX_OPTIONS)]
    answer: Annotated[int, Field(ge=0)]
    why: Annotated[str | None, Field(max_length=1000)] = ""

    @field_validator("why", mode="before")
    @classmethod
    def _null_why_is_empty(cls, value):
        return "" if value is None else value  # a model that writes "why": null has still produced a usable quiz

    @model_validator(mode="after")
    def _answer_in_range(self) -> "QuizQuestion":
        if self.answer >= len(self.options):
            raise ValueError(f"answer index {self.answer} is out of range for {len(self.options)} options")
        return self


class Quiz(BaseModel):
    questions: Annotated[list[QuizQuestion], Field(min_length=1, max_length=MAX_QUESTIONS)]


def extract_json_object(text: str) -> str:
    """The first ``{`` to the last ``}`` of the reply: prose or code fences around it are ignored."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in the reply")
    return text[start : end + 1]


def parse_quiz(text: str) -> list[dict]:
    """Questions as plain dicts (``q``, ``options``, ``answer``, ``why``); raises ``ValueError``."""
    try:
        quiz = Quiz.model_validate(json.loads(extract_json_object(text)))
    except json.JSONDecodeError as exc:
        raise ValueError(f"reply is not valid JSON: {exc.msg}") from exc
    except ValidationError as exc:
        raise ValueError(f"reply is not a well-formed quiz: {exc.error_count()} problem(s)") from exc
    return [question.model_dump() for question in quiz.questions]
