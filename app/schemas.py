from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field, field_validator


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=7000)

    @field_validator("content")
    @classmethod
    def trim_content(cls, value: str) -> str:
        return value.strip()


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=16000)
    mode: Literal["auto", "chat", "code"] = "auto"
    history: list[HistoryMessage] = Field(default_factory=list, max_length=20)

    @field_validator("message")
    @classmethod
    def trim_message(cls, value: str) -> str:
        return value.strip()


class LoginRequest(BaseModel):
    password: str = Field(min_length=1, max_length=512)
