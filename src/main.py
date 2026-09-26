"""FastAPI app"""

from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from src.authorization.policy import AuthorizationPolicy
from src.routes import router


def create_app() -> FastAPI:
    """Application factory."""
    # Refuse to start with missing or invalid entitlements, instead of failing every query.
    AuthorizationPolicy()

    app = FastAPI(
        title="Rag Prototype Quest",
        description="Local RAG prototype with pre-retrieval authorization, evidence gating, and release-blocking evaluation.",
        version="0.1.0",
    )

    app.include_router(router)

    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        # Opening the app in a browser lands on the interactive API docs.
        return RedirectResponse(url="/docs")

    return app


app = create_app()
