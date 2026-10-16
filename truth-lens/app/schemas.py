from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator


class AnalysisRequest(BaseModel):
    claim: str | None = Field(default=None, max_length=6000)
    article_url: HttpUrl | None = None

    @field_validator("claim")
    @classmethod
    def strip_claim(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Enter a claim or provide an article URL.")
        return value

    @model_validator(mode="after")
    def require_input(self):
        if not self.claim and not self.article_url:
            raise ValueError("Enter a claim or provide an article URL.")
        return self


class Source(BaseModel):
    title: str
    publisher: str
    url: HttpUrl
    rating: str
    review_date: str | None = None
    source_type: Literal["fact_check", "news"] = "fact_check"


class AnalysisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    claim: str
    article_url: str | None
    verdict: str
    verdict_label: str
    summary: str
    mode: str
    sources: list[Source]
    keywords: list[str]
    created_at: str
