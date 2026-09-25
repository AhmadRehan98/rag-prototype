"""Seed the database from the supplied assessment data.

Every run deletes all users and documents (their roles, groups, overrides and
chunks cascade) and inserts them again, in one transaction, from:

- identities.json: users with their roles and groups.
- corpus.jsonl: one document per line. The whole content becomes one chunk,
  so it must fit the embedding model's input (checked before anything is written).
- entitlements.json: per-document allow/deny overrides, merged with each
  document's allowed_groups. Classification rules are not stored; the
  AuthorizationPolicy reads them from the file at query time.

Deleting first means anything removed from these files (a user, a group, a
document, an override) also disappears from the database. Then every chunk is embedded.
"""

import argparse
import asyncio
import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.database.connection import ASYNC_SESSION_LOCAL, close_db, init_db
from src.database.repositories import (
    ChunkRepository,
    DocumentRepository,
    UserRepository,
)
from src.retrieval.embeddings import embedding_service
from src.retrieval.indexer import ChunkIndexer

DEFAULT_IDENTITIES_PATH = Path("data/access/identities.json")

DEFAULT_CORPUS_PATH = Path("data/normalized/corpus.jsonl")

DEFAULT_ENTITLEMENTS_PATH = Path("data/access/entitlements.json")


class SeedDataError(ValueError):
    """Raised when supplied seed data cannot be safely interpreted."""


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue

            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise SeedDataError(
                    f"Invalid JSON on line {line_number} of {path}: {exc}"
                ) from exc

    return records


def require_string(data: dict[str, Any], key: str) -> str:
    value = data.get(key)

    if not isinstance(value, str) or not value.strip():
        # Name the field only: the record may be a restricted document, and its
        # content must not end up in console output or logs.
        raise SeedDataError(f"Missing or empty string field {key!r}.")

    return value.strip()


def string_list(data: dict[str, Any], key: str) -> list[str]:
    value = data.get(key, [])

    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise SeedDataError(f"{key!r} must be a list of non-empty strings.")

    # Strip and drop duplicates, keeping the order.
    return list(dict.fromkeys(item.strip() for item in value))


def parse_date(value: Any) -> date | None:
    if not value:
        return None

    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise SeedDataError(f"Invalid ISO date: {value!r}") from exc


def check_documents_fit_embedding_model(records: list[dict[str, Any]]) -> None:
    """Each document is embedded whole, as one chunk. A longer document would
    have its end silently cut off by the embedding model, so refuse instead."""
    limit = embedding_service.max_tokens

    for record in records:
        tokens = embedding_service.token_count(require_string(record, "content"))

        if tokens > limit:
            raise SeedDataError(
                f"{record['document_id']} v{record['version']} is {tokens} tokens; "
                f"the embedding model reads at most {limit}. "
                "It needs to be split into several chunks."
            )


def load_overrides(
    entitlements: dict[str, Any],
) -> dict[str, list[tuple[str, bool]]]:
    """document_id -> [(group, allowed)] from entitlements.json's document_overrides."""
    overrides: dict[str, list[tuple[str, bool]]] = {}

    for item in entitlements.get("document_overrides", []):
        document_id = require_string(item, "document_id")

        if document_id in overrides:
            raise SeedDataError(f"Duplicate document_overrides entry for {document_id!r}.")

        overrides[document_id] = [
            (group, True) for group in string_list(item, "allow_groups")
        ] + [(group, False) for group in string_list(item, "deny_groups")]

    return overrides


def merge_permissions(pairs: list[tuple[str, bool]]) -> list[tuple[str, bool]]:
    """Drop duplicate (group, allowed) pairs; a group both allowed and denied is an error."""
    merged: dict[str, bool] = {}

    for group, allowed in pairs:
        if merged.get(group, allowed) != allowed:
            raise SeedDataError(f"Group {group!r} is both allowed and denied.")

        merged[group] = allowed

    return list(merged.items())


async def seed_users(session: AsyncSession, identities: dict[str, Any]) -> int:
    repository = UserRepository(session)
    users = identities.get("users", [])

    for user in users:
        await repository.create(
            user_id=require_string(user, "user_id"),
            display_name=require_string(user, "display_name"),
            department=require_string(user, "department"),
            roles=string_list(user, "roles"),
            groups=string_list(user, "groups"),
        )

    return len(users)


async def seed_documents(
    session: AsyncSession,
    records: list[dict[str, Any]],
    overrides: dict[str, list[tuple[str, bool]]],
) -> int:
    document_repository = DocumentRepository(session)
    chunk_repository = ChunkRepository(session)

    for record in records:
        document_id = require_string(record, "document_id")
        content = require_string(record, "content")
        permissions = merge_permissions(
            [(group, True) for group in string_list(record, "allowed_groups")]
            + overrides.get(document_id, [])
        )

        document = await document_repository.create(
            document_id=document_id,
            title=require_string(record, "title"),
            version=require_string(record, "version"),
            status=require_string(record, "status"),
            classification=require_string(record, "classification"),
            effective_date=parse_date(record.get("effective_date")),
            content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            source_path=record.get("source_path"),
            permissions=permissions,
        )

        await chunk_repository.create_many(
            document_db_id=document.id,
            chunks=[{"chunk_index": 0, "content": content}],
        )

    return len(records)


async def seed(
    identities_path: Path,
    corpus_path: Path,
    entitlements_path: Path,
) -> None:
    for path in (identities_path, corpus_path, entitlements_path):
        if not path.exists():
            raise SeedDataError(f"File does not exist: {path}")

    identities = load_json(identities_path)
    records = load_jsonl(corpus_path)
    overrides = load_overrides(load_json(entitlements_path))

    # An override for a document that isn't in the corpus is most likely a
    # typo that would leave the intended document unprotected.
    unknown = set(overrides) - {record.get("document_id") for record in records}
    if unknown:
        raise SeedDataError(f"document_overrides for unknown documents: {sorted(unknown)}")

    # Checked before anything is deleted or written.
    check_documents_fit_embedding_model(records)

    await init_db()  # ensure the pgvector extension exists

    async with ASYNC_SESSION_LOCAL() as session:
        try:
            # Roles and groups cascade with users; overrides, override
            # groups and chunks cascade with documents.
            await UserRepository(session).delete_all()
            await DocumentRepository(session).delete_all()
            users_seeded = await seed_users(session, identities)
            documents_seeded = await seed_documents(session, records, overrides)
            await session.commit()
        except Exception:
            await session.rollback()
            raise

        chunks_indexed = await ChunkIndexer(session).index_unindexed_chunks()

    await close_db()

    print("Database seed completed successfully.")
    print(f"Users: {users_seeded}")
    print(f"Documents: {documents_seeded}")
    print(f"Chunks indexed: {chunks_indexed}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Replace all users, documents, permissions and chunks "
            "with the supplied assessment data."
        )
    )

    parser.add_argument("--identities", type=Path, default=DEFAULT_IDENTITIES_PATH)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS_PATH)
    parser.add_argument("--entitlements", type=Path, default=DEFAULT_ENTITLEMENTS_PATH)

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    try:
        asyncio.run(
            seed(
                identities_path=args.identities,
                corpus_path=args.corpus,
                entitlements_path=args.entitlements,
            )
        )
    except SeedDataError as exc:
        raise SystemExit(f"Seed failed: {exc}") from exc


if __name__ == "__main__":
    main()
