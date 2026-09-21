"""FastAPI app"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def create_app() -> FastAPI:
    """Application factory."""
    app = FastAPI(
        title="Rag Prototype Quest",
        description="Local RAG prototype with pre-retrieval authorization, evidence gating, and release-blocking evaluation.",
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    return app


app = create_app()
