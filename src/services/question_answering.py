"""Question-answering flow:
check user exists -> authorized scope & retrieval -> evidence selection -> generation -> guards to verify citation legitimacy.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from src.authorization.service import AuthorizationService
from src.config.settings import settings
from src.database.repositories.users import UserRepository
from src.domain.errors import UserNotFoundError
from src.domain.models import ExcludedSource, QueryRequest, QueryResponse, Source
from src.evidence.selection import EvidenceSelector, EvidenceSet
from src.generation.answer import AnswerGenerator, AnswerRejectedError
from src.generation.llm import LLMClient, LlamaCppClient, LLMUnavailableError
from src.retrieval.retriever import HybridRetriever

NO_EVIDENCE_MESSAGE = "I couldn't find current, trustworthy information that you have access to which answers this question."  # no sources at all found from allowed docs
INSUFFICIENT_MESSAGE = "The sources you have access to don't contain the information needed to answer this question."  # no claims
REJECTED_MESSAGE = "I couldn't produce an answer that is fully supported by the sources. Please review the sources listed below directly."  # Guard Failure, LLM incomplete JSON.
UNAVAILABLE_MESSAGE = "The answer service is temporarily unavailable. The relevant sources are listed below."  # LLM Down


class QuestionAnsweringService:
    """Orchestrates one query for one user.

    Authorization runs before retrieval, so only documents the user may access can be scored, returned, or passed to later stages.
    """

    def __init__(self, session: AsyncSession, llm: LLMClient | None = None) -> None:
        self.user_repo = UserRepository(session)
        self.authorization = AuthorizationService(session)
        self.retriever = HybridRetriever(session)
        self.selector = EvidenceSelector()
        self.generator = AnswerGenerator(llm or LlamaCppClient())

    async def answer_question(self, request: QueryRequest) -> QueryResponse:
        user = await self.user_repo.get_by_user_id(request.user_id)
        if user is None:
            raise UserNotFoundError(f"Unknown user: {request.user_id}")
        # grab only authed docs
        allowed_ids = await self.authorization.get_authorized_document_ids(user)
        chunks = await self.retriever.retrieve(
            question=request.question,
            allowed_document_ids=allowed_ids,
            top_k=settings.RETRIEVAL_TOP_K,
        )
        # filter evidence
        evidence_set = self.selector.select(chunks)
        sources, excluded = _sources(evidence_set), _excluded(evidence_set)

        if not evidence_set.is_sufficient:
            return QueryResponse(
                status="no_relevant_evidence",
                answer=NO_EVIDENCE_MESSAGE,
                excluded_sources=excluded,
            )

        try:
            generated = await self.generator.generate(
                request.question, evidence_set.evidence
            )
        except LLMUnavailableError:
            return QueryResponse(
                status="generation_unavailable",
                answer=UNAVAILABLE_MESSAGE,
                sources=sources,
                excluded_sources=excluded,
            )
        except AnswerRejectedError as exc:
            return QueryResponse(
                status="answer_rejected",
                answer=REJECTED_MESSAGE,
                rejection_reason=exc.code,
                sources=sources,
                excluded_sources=excluded,
            )

        return QueryResponse(
            status="answered" if generated.answerable else "insufficient_evidence",
            answer=generated.text or INSUFFICIENT_MESSAGE,
            missing_information=generated.missing_information,
            sources=sources,
            excluded_sources=excluded,
        )


def _sources(evidence_set: EvidenceSet) -> list[Source]:
    # citation numbers match the [n] ids given to the model in build_messages
    return [
        Source(
            citation=number,
            chunk_id=item.chunk.chunk_id,
            document_id=item.chunk.document_id,
            title=item.chunk.document_title,
            version=item.chunk.version,
            status=item.chunk.status,
            effective_date=item.chunk.effective_date,
            authority=item.authority,
            content=item.chunk.content,
        )
        for number, item in enumerate(evidence_set.evidence, start=1)
    ]


def _excluded(evidence_set: EvidenceSet) -> list[ExcludedSource]:
    return [
        ExcludedSource(
            document_id=item.chunk.document_id,
            title=item.chunk.document_title,
            version=item.chunk.version,
            status=item.chunk.status,
            reason=item.reason,
        )
        for item in evidence_set.excluded
    ]
