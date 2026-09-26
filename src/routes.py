"""FastAPI route handlers."""

import json
from typing import Any, List
from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.authorization.service import AuthorizationService
from src.config.settings import settings
from src.database.connection import get_db_session
from src.database.repositories import UserRepository
from src.domain.errors import UserNotFoundError
from src.domain.models import DocumentSummary, QueryRequest, QueryResponse, UserProfile
from src.services.question_answering import QuestionAnsweringService

router = APIRouter(prefix="/api/v1", tags=["Rag Prototype Quest"])


def load_query_examples() -> dict[str, dict[str, Any]]:
    """The evaluation cases as ready-to-send requests for the /docs "Examples" dropdown. Only the user_id and question are used: answers always come from the live pipeline. Without the cases file the docs simply have no examples."""
    path = settings.resolve_path(settings.EVALUATION_CASES_PATH)
    if not path.exists():
        return {}

    examples = {}
    with path.open(encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            case = json.loads(line)
            # One example per run: the authorization case asks the same
            # question as two users.
            for run in case["runs"]:
                examples[f"{case['id']}-{run['user_id']}"] = {
                    "summary": f"Incident {case['incident']}, {case['family']} ({run['user_id']})",
                    "value": {"user_id": run["user_id"], "question": case["question"]},
                }
    return examples


@router.post("/query", response_model=QueryResponse, summary="Answer employee inquiry")
async def query_endpoint(
    request: QueryRequest = Body(openapi_examples=load_query_examples()),
    session: AsyncSession = Depends(get_db_session),
) -> QueryResponse:
    """
    Unexpected errors are deliberately not caught here: FastAPI returns a
    generic 500 without exception details, so internal state (SQL, document
    content) never reaches the client.
    """
    qa_service = QuestionAnsweringService(session)
    try:
        return await qa_service.answer_question(request)
    except UserNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get(
    "/users", response_model=List[UserProfile], summary="List available user identities"
)
async def list_users_endpoint(
    session: AsyncSession = Depends(get_db_session),
) -> List[UserProfile]:
    """List sample authenticated employee identities for testing."""
    user_repo = UserRepository(session)
    return [
        UserProfile(
            user_id=user.user_id,
            display_name=user.display_name,
            department=user.department,
            roles=[item.role for item in user.roles],
            groups=[item.group for item in user.groups],
        )
        for user in await user_repo.list_all()
    ]


@router.get(
    "/users/{user_id}/documents",
    response_model=List[DocumentSummary],
    summary="List the documents a user is authorized to read",
)
async def list_user_documents_endpoint(
    user_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> List[DocumentSummary]:
    """The same authorization check /query runs before retrieval, shown directly.

    Only authorized documents are listed, so a restricted document never
    appears (not even as "denied") for a user who may not read it.
    """
    user = await UserRepository(session).get_by_user_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown user: {user_id}"
        )

    documents = await AuthorizationService(session).get_authorized_documents(user)
    return [
        DocumentSummary(
            document_id=document.document_id,
            title=document.title,
            version=document.version,
            status=document.status,
            classification=document.classification,
        )
        for document in documents
    ]


@router.get("/health", summary="Health check endpoint")
async def health_check_endpoint() -> dict:
    """System health check."""
    return {"status": "healthy", "service": "rag-prototype-quest"}
