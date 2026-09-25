"""Request/response schemas for the question-answering API."""

from typing import Literal

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    """A question asked on behalf of one of the supplied user identities."""

    user_id: str = Field(min_length=1, max_length=64)
    question: str = Field(min_length=1, max_length=1000)


class Source(BaseModel):
    """Evidence the answer may cite as [citation]. Only built from authorized,
    trusted documents."""

    citation: int
    chunk_id: int
    document_id: str
    title: str
    version: str
    status: str
    effective_date: str | None
    authority: Literal["authoritative", "advisory"]
    content: str


class ExcludedSource(BaseModel):
    """A relevant authorized document that was deliberately not used."""

    document_id: str
    title: str
    version: str
    status: str
    reason: Literal["retired", "unverified", "unrecognized_status", "superseded"]


QueryStatus = Literal[
    "answered",
    "insufficient_evidence",
    "no_relevant_evidence",
    "answer_rejected",  # The model's output failed a guard.
    "generation_unavailable",
]


class QueryResponse(BaseModel):
    status: QueryStatus
    answer: str | None = None
    missing_information: str | None = None
    rejection_reason: str | None = None
    sources: list[Source] = []
    excluded_sources: list[ExcludedSource] = []


class DocumentSummary(BaseModel):
    """Metadata of a document a user is authorized to read (no content)."""

    document_id: str
    title: str
    version: str
    status: str
    classification: str


class UserProfile(BaseModel):
    """Public view of a supplied user identity."""

    user_id: str
    display_name: str
    department: str
    roles: list[str]
    groups: list[str]
