"""QuestionAnsweringService: which status each pipeline outcome returns.

The user lookup, authorization and retrieval are replaced by fakes, and the LLM
by FakeLLM, so no database or model is needed.
"""

import json
from types import SimpleNamespace as NS

import pytest

from src.domain.errors import UserNotFoundError
from src.domain.models import QueryRequest
from src.generation.llm import LLMUnavailableError
from src.services.question_answering import QuestionAnsweringService


class FakeLLM:
    def __init__(self, output: str | None = None, error: Exception | None = None) -> None:
        self.output = output
        self.error = error
        self.calls = 0

    async def complete_json(self, messages, json_schema):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.output


def model_output(*claims, answerable=True, missing=""):
    return json.dumps({
        "answerable": answerable,
        "claims": [{"text": text, "sources": sources} for text, sources in claims],
        "missing_information": missing,
    })


def make_service(chunks, llm, *, known_user=True):
    async def get_by_user_id(user_id):
        return NS(user_id=user_id) if known_user else None

    async def get_authorized_document_ids(user):
        return [1]

    async def retrieve(**kwargs):
        return chunks

    service = QuestionAnsweringService(session=None, llm=llm)
    service.user_repo = NS(get_by_user_id=get_by_user_id)
    service.authorization = NS(get_authorized_document_ids=get_authorized_document_ids)
    service.retriever = NS(retrieve=retrieve)
    return service


async def ask(service):
    return await service.answer_question(QueryRequest(user_id="u-test", question="q?"))


@pytest.mark.asyncio
async def test_unknown_user_is_refused_before_anything_runs(make_chunk):
    llm = FakeLLM(model_output(("Some content.", [1])))
    with pytest.raises(UserNotFoundError):
        await ask(make_service([make_chunk()], llm, known_user=False))
    assert llm.calls == 0


@pytest.mark.asyncio
async def test_no_trusted_relevant_evidence_skips_the_llm_and_returns_no_sources(make_chunk):
    llm = FakeLLM(model_output(("Some content.", [1])))
    chunks = [make_chunk("OFF-TOPIC", similarity=0.3), make_chunk("OLD", status="Retired")]
    response = await ask(make_service(chunks, llm))
    assert response.status == "no_relevant_evidence"
    assert response.sources == []
    assert [item.document_id for item in response.excluded_sources] == ["OLD"]
    assert llm.calls == 0


@pytest.mark.asyncio
async def test_llm_outage_returns_sources_but_no_answer(make_chunk):
    llm = FakeLLM(error=LLMUnavailableError("ConnectError"))
    response = await ask(make_service([make_chunk("POL")], llm))
    assert response.status == "generation_unavailable"
    assert response.missing_information is None
    assert [item.document_id for item in response.sources] == ["POL"]


@pytest.mark.asyncio
async def test_guard_failure_withholds_the_model_text(make_chunk):
    llm = FakeLLM(model_output(("Support responds within 6 hours.", [1])))
    response = await ask(make_service([make_chunk("CONTRACT")], llm))
    assert response.status == "answer_rejected"
    assert response.rejection_reason == "unsupported_number"
    assert "6 hours" not in response.model_dump_json()
    assert [item.document_id for item in response.sources] == ["CONTRACT"]


@pytest.mark.asyncio
async def test_supported_answer_citations_match_the_listed_sources(make_chunk):
    chunks = [
        make_chunk("MEMO", status="Active advisory", content="Memo text.", similarity=0.9),
        make_chunk("POL", content="Policy text.", similarity=0.7),
    ]
    llm = FakeLLM(model_output(("Policy text.", [1]), ("Memo text.", [2])))
    response = await ask(make_service(chunks, llm))
    assert response.status == "answered"
    assert response.answer == "- Policy text. [1]\n- Memo text. [2]"
    # The authoritative source is [1] even though the advisory one is more similar.
    assert [(s.citation, s.document_id) for s in response.sources] == [(1, "POL"), (2, "MEMO")]


@pytest.mark.asyncio
async def test_model_refusal_becomes_insufficient_evidence(make_chunk):
    llm = FakeLLM(model_output(answerable=False, missing="A signed service-level schedule."))
    response = await ask(make_service([make_chunk("CONTRACT")], llm))
    assert response.status == "insufficient_evidence"
    assert response.missing_information == "A signed service-level schedule."
    assert [item.document_id for item in response.sources] == ["CONTRACT"]
