from __future__ import annotations

import re
from pathlib import PurePath
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


ALLOWED_TEXT_EXTENSIONS = {
    ".txt", ".md", ".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx",
    ".html", ".htm", ".css", ".json", ".xml", ".yaml", ".yml", ".sql",
    ".sh", ".java", ".kt", ".php", ".go", ".rs", ".c", ".h", ".cpp",
    ".hpp", ".cs", ".toml", ".ini", ".log", ".csv", ".vue", ".svelte",
}


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=7000)

    @field_validator("content")
    @classmethod
    def trim_content(cls, value: str) -> str:
        return value.strip()


class TextAttachment(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    content: str = Field(max_length=200_000)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        safe = PurePath(value.replace("\\", "/")).name
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", safe)
        if not safe or PurePath(safe).suffix.lower() not in ALLOWED_TEXT_EXTENSIONS:
            raise ValueError("Bu dosya türü desteklenmiyor.")
        if safe.lower() == ".env":
            raise ValueError("Gizli ortam dosyaları yüklenemez.")
        return safe


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=16000)
    mode: Literal["auto", "chat", "code"] = "auto"
    history: list[HistoryMessage] = Field(default_factory=list, max_length=20)
    attachments: list[TextAttachment] = Field(default_factory=list, max_length=5)

    @field_validator("message")
    @classmethod
    def trim_message(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def limit_total_attachment_size(self):
        total = sum(len(item.content.encode("utf-8")) for item in self.attachments)
        if total > 600_000:
            raise ValueError("Ekli dosyaların toplamı 600 KB sınırını geçemez.")
        return self
