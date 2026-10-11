from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator


class AppError(Exception):
    def __init__(self, code: str, status: int = 400):
        self.code = code
        self.status = status


class Endpoint(BaseModel):
    runtime: Literal["lmstudio", "ollama"] = "lmstudio"
    base_url: str = "http://localhost:1234/v1"
    model: str = "qwen3.5-9b-uncensored-hauhaucs-aggressive"

    @field_validator("base_url")
    @classmethod
    def local_only(cls, value: str) -> str:
        u = urlsplit(value)
        if (
            u.scheme not in {"http", "https"}
            or u.hostname not in {"localhost", "127.0.0.1", "::1"}
            or u.username
            or u.password
            or u.query
            or u.fragment
            or u.path.rstrip("/") != "/v1"
        ):
            raise ValueError("loopback /v1 endpoint required")
        return value.rstrip("/")


class InferenceSettings(BaseModel):
    source: Literal["runtime", "app"] = "app"
    thinking: bool = False
    temperature: float = Field(default=0.7, ge=0, le=2, allow_inf_nan=False)
    top_k: int | None = Field(default=20, ge=0, le=1000)
    top_p: float | None = Field(default=0.95, gt=0, le=1, allow_inf_nan=False)
    min_p: float | None = Field(default=0, ge=0, le=1, allow_inf_nan=False)
    repeat_penalty: float | None = Field(default=None, gt=0, le=3, allow_inf_nan=False)
    presence_penalty: float | None = Field(
        default=None, ge=-2, le=2, allow_inf_nan=False
    )


class Settings(BaseModel):
    generation: Endpoint = Field(default_factory=Endpoint)
    embedding: Endpoint = Field(
        default_factory=lambda: Endpoint(model="text-embedding-embeddinggemma-2")
    )
    overall_timeout: float = Field(default=45, ge=5, le=90)
    connect_timeout: float = Field(default=10, ge=1, le=20)
    read_timeout: float = Field(default=20, ge=1, le=45)
    max_bytes: int = Field(default=5 * 1024 * 1024, ge=1024, le=10 * 1024 * 1024)
    redirects: int = Field(default=5, ge=0, le=10)
    retrieval_concurrency: int = Field(default=2, ge=1, le=2)
    rendering: bool = False
    context_chars: int = Field(default=12000, ge=1000, le=24000)
    output_tokens: int = Field(default=8192, ge=256, le=65536)
    distance_threshold: float = Field(default=0.25, gt=0, lt=1)
    api_timeout: float = Field(default=0, ge=0, le=86400, allow_inf_nan=False)
    inference: InferenceSettings = Field(default_factory=InferenceSettings)


class Analysis(BaseModel):
    suggested_name: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=2000)
    type: str = Field(min_length=1, max_length=100)
    purpose: str = Field(min_length=1, max_length=1000)
    candidate_categories: list[str] = Field(min_length=1, max_length=10)
    tags: list[str] = Field(max_length=20)

    @field_validator("candidate_categories", "tags")
    @classmethod
    def bounded_labels(cls, values: list[str]) -> list[str]:
        if any(not v.strip() or len(v) > 100 for v in values):
            raise ValueError("invalid label")
        return values


class JobRequest(BaseModel):
    folders: list[str] = Field(default_factory=list)
    all: bool = False
    destination: str | None = None
    token: str = Field(min_length=8, max_length=100)


class ProposalRequest(BaseModel):
    allow_incomplete: bool = False


class ItemEdit(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    parent: str
