from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

EvidenceType = Literal["cv", "case_study", "review", "proposal", "repository"]


class SourceMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    source: str = Field(min_length=1, max_length=200)
    type: EvidenceType = "case_study"
    persona: str = Field(default="own", min_length=1, max_length=100)
    project: str = Field(default="Own portfolio", min_length=1, max_length=200)
    skills: list[str] = Field(default_factory=list, max_length=100)
    date: str = Field(default="unspecified", max_length=30)
    industry: str = Field(default="unspecified", max_length=100)
    outcome: Literal["unknown", "won", "replied", "ignored"] = "unknown"
    synthetic: bool = False

    @field_validator("source", "persona", "project")
    @classmethod
    def not_blank(cls, value):
        if not value.strip() or "\x00" in value:
            raise ValueError("Source metadata cannot be blank or contain NUL")
        return value.strip()

    @field_validator("skills")
    @classmethod
    def clean_skills(cls, values):
        result = {}
        for skill in values:
            skill = skill.strip()
            if not skill or len(skill) > 100:
                raise ValueError("Each skill must contain 1 to 100 characters")
            result.setdefault(skill.casefold(), skill)
        return sorted(result.values(), key=str.casefold)


class DocumentSection(BaseModel):
    text: str
    location: str
    metadata: SourceMetadata


class PortfolioDocument(BaseModel):
    sections: list[DocumentSection]
    raw_hash: str
    loader: str


class ChunkSettings(BaseModel):
    size: int = Field(default=1200, ge=40, le=20000)
    overlap: int = Field(default=150, ge=0)

    @model_validator(mode="after")
    def valid_overlap(self):
        if self.overlap >= self.size:
            raise ValueError("Chunk overlap must be smaller than chunk size")
        return self

    @property
    def version(self):
        return f"fixed-chars-v2:{self.size}:{self.overlap}"
