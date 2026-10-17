from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    Field,
    SecretStr,
    ValidationInfo,
    field_validator,
    model_validator,
)

from bookmark_organization.policy import FOLDER_PATHS, SOURCE_LABELS, VAGUE_LABELS

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
CODEX_MODEL = "gpt-6-luna"
CODEX_REASONING = "low"


class AppError(Exception):
    def __init__(self, code: str, status: int = 400):
        self.code = code
        self.status = status


class Endpoint(BaseModel):
    runtime: Literal["lmstudio", "ollama", "openrouter", "codex"] = "lmstudio"
    base_url: str = Field(
        default_factory=lambda data: (
            ""
            if data.get("runtime") == "codex"
            else OPENROUTER_BASE_URL
            if data.get("runtime") == "openrouter"
            else "http://localhost:1234/v1"
        ),
        validate_default=True,
    )
    model: str = Field(
        default_factory=lambda data: (
            CODEX_MODEL
            if data.get("runtime") == "codex"
            else "qwen3.5-9b-uncensored-hauhaucs-aggressive"
        ),
        validate_default=True,
    )

    @field_validator("model")
    @classmethod
    def codex_model(cls, value: str, info: ValidationInfo) -> str:
        if info.data.get("runtime") == "codex" and value != CODEX_MODEL:
            raise ValueError("Codex requires gpt-6-luna")
        return value

    @field_validator("base_url")
    @classmethod
    def allowed_endpoint(cls, value: str, info: ValidationInfo) -> str:
        if info.data.get("runtime") == "codex":
            if value:
                raise ValueError("Codex uses CLI authentication, not an API endpoint")
            return ""
        if info.data.get("runtime") == "openrouter":
            if value.rstrip("/") != OPENROUTER_BASE_URL:
                raise ValueError("official OpenRouter HTTPS endpoint required")
            return OPENROUTER_BASE_URL
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

    @model_validator(mode="after")
    def embedding_provider(self):
        if self.embedding.runtime == "codex":
            raise ValueError("Codex supports content analysis only")
        return self


class SettingsUpdate(Settings):
    # Credentials are accepted separately and never become job settings.
    openrouter_api_key: SecretStr = Field(default_factory=lambda: SecretStr(""))

    @field_validator("openrouter_api_key")
    @classmethod
    def valid_key(cls, value: SecretStr) -> SecretStr:
        key = value.get_secret_value().strip()
        if len(key) > 4096 or any(not 33 <= ord(c) <= 126 for c in key):
            raise ValueError("invalid API key")
        return SecretStr(key)

    def settings(self) -> Settings:
        return Settings.model_validate(self.model_dump(exclude={"openrouter_api_key"}))


class Analysis(BaseModel):
    suggested_name: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=2000)
    purpose: str = Field(min_length=1, max_length=1000)
    candidate_categories: list[str] = Field(min_length=1, max_length=10)

    @field_validator("candidate_categories")
    @classmethod
    def bounded_labels(cls, values: list[str]) -> list[str]:
        if any(not v.strip() or len(v) > 100 for v in values):
            raise ValueError("invalid label")
        return values


class OrganizationRules(BaseModel):
    naming_mode: Literal["purpose", "custom"] = "purpose"
    folder_mode: Literal["purpose", "custom"] = "purpose"
    naming_prompt: str = Field(default="", max_length=4000)
    folder_prompt: str = Field(default="", max_length=4000)

    @model_validator(mode="before")
    @classmethod
    def saved_shared_preset(cls, value):
        # Read older snapshots without rewriting their saved instructions.
        if isinstance(value, dict) and "preset" in value:
            value = dict(value)
            preset = value.pop("preset")
            value.setdefault("naming_mode", preset)
            value.setdefault("folder_mode", preset)
        return value

    @field_validator("naming_prompt", "folder_prompt")
    @classmethod
    def trim_prompt(cls, value: str) -> str:
        return value.strip()

    @property
    def custom_naming(self) -> bool:
        return self.naming_mode == "custom" and bool(self.naming_prompt)

    @property
    def custom_folders(self) -> bool:
        return self.folder_mode == "custom" and bool(self.folder_prompt)


class StructuredAnalysis(Analysis):
    suggested_name: str = Field(min_length=1, max_length=200, pattern=r"^[^\r\n]+$")
    candidate_categories: list[
        Annotated[
            str,
            Field(
                max_length=100,
                pattern=r"^[^/\\\r\n]{1,100}(/[^/\\\r\n]{1,100})?$",
            ),
        ]
    ] = Field(
        min_length=1,
        max_length=1,
        description="Choose exactly one destination path, at most two folder levels",
    )

    @field_validator("suggested_name")
    @classmethod
    def single_line_name(cls, value: str) -> str:
        value = value.strip()
        if not value or any(ord(char) < 32 for char in value):
            raise ValueError("nonempty single-line name required")
        return value

    @field_validator("candidate_categories")
    @classmethod
    def safe_path(cls, values: list[str]) -> list[str]:
        for value in values:
            parts = value.split("/")
            if not 1 <= len(parts) <= 2 or any(
                not part.strip()
                or part != part.strip()
                or part in {".", ".."}
                or "\\" in part
                or any(ord(char) < 32 for char in part)
                for part in parts
            ):
                raise ValueError("one or two safe folder names required")
        return values


class PurposeNameAnalysis(StructuredAnalysis):
    suggested_name: str = Field(
        min_length=3,
        max_length=200,
        pattern=r"^[^｜\r\n]+｜[^｜\r\n]+$",
        description="具体的な用途｜サイト・ツール・資料名［必要な種類・技術］",
    )

    @field_validator("suggested_name")
    @classmethod
    def purpose_name(cls, value: str) -> str:
        purpose, name = (part.strip() for part in value.split("｜"))
        if not purpose or not name or purpose in VAGUE_LABELS:
            raise ValueError("specific purpose and proper name required")
        return f"{purpose}｜{name}"


PurposeFolderPath = Annotated[
    str,
    Field(
        max_length=100,
        pattern=r"^[^/\\\r\n]{1,100}(/[^/\\\r\n]{1,100})?$",
        examples=FOLDER_PATHS,
    ),
]


class PurposeFolderAnalysis(StructuredAnalysis):
    candidate_categories: list[PurposeFolderPath] = Field(
        min_length=1,
        max_length=1,
        description="探す作業に最も合う用途パスを1つ選ぶ",
    )

    @field_validator("candidate_categories")
    @classmethod
    def purpose_path(cls, values: list[str]) -> list[str]:
        for value in values:
            parts = value.split("/")
            if not 1 <= len(parts) <= 2 or any(
                not part.strip()
                or part != part.strip()
                or part in VAGUE_LABELS | SOURCE_LABELS | {".", ".."}
                or "\\" in part
                or any(ord(char) < 32 for char in part)
                for part in parts
            ):
                raise ValueError("one or two specific purpose folders required")
        return values


class PurposeAnalysis(PurposeNameAnalysis, PurposeFolderAnalysis):
    candidate_categories: list[PurposeFolderPath] = Field(
        min_length=1,
        max_length=1,
        description="探す作業に最も合う用途パスを1つ選ぶ",
    )


def analysis_model(rules: OrganizationRules) -> type[Analysis]:
    if rules.custom_naming and rules.custom_folders:
        return StructuredAnalysis
    if rules.custom_naming:
        return PurposeFolderAnalysis
    if rules.custom_folders:
        return PurposeNameAnalysis
    return PurposeAnalysis


class JobRequest(BaseModel):
    folders: list[str] = Field(default_factory=list)
    all: bool = False
    destination: str | None = None
    token: str = Field(min_length=8, max_length=100)
    rules: OrganizationRules = Field(default_factory=OrganizationRules)
    base_proposal: str | None = None


class ProposalRequest(BaseModel):
    allow_incomplete: bool = False


class ItemEdit(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    parent: str
