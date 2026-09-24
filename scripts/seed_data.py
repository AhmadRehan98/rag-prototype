import argparse
import asyncio
import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.database.repositories import (
    ChunkRepository,
    DocumentRepository,
    UserRepository,
)
from src.database.connection import ASYNC_SESSION_LOCAL, init_db, close_db
from src.retrieval.indexer import ChunkIndexer

DEFAULT_IDENTITIES_PATH = Path("data/access/identities.json")

DEFAULT_CORPUS_PATH = Path("data/normalized/corpus.jsonl")

DEFAULT_ENTITLEMENTS_PATH = Path("data/access/entitlements.json")


class SeedDataError(ValueError):
    """Raised when supplied seed data cannot be safely interpreted."""


def load_json(path: Path) -> Any:
    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        for line_number, line in enumerate(file, start=1):
            line = line.strip()

            if not line:
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SeedDataError(
                    f"Invalid JSON on line {line_number} of " f"{path}: {exc}"
                ) from exc

            if not isinstance(record, dict):
                raise SeedDataError(
                    f"Expected JSON object on line " f"{line_number} of {path}."
                )

            records.append(record)

    return records


def first_present(
    data: dict[str, Any],
    *keys: str,
) -> Any:
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]

    return None


def require_string(
    data: dict[str, Any],
    *keys: str,
) -> str:
    value = first_present(data, *keys)

    if not isinstance(value, str) or not value.strip():
        raise SeedDataError(
            f"Missing required string field. " f"Expected one of: {keys}"
        )

    return value.strip()


def optional_string(
    data: dict[str, Any],
    *keys: str,
) -> str | None:
    value = first_present(data, *keys)

    if value is None:
        return None

    if not isinstance(value, str):
        raise SeedDataError(f"Expected a string for one of: {keys}")

    return value.strip() or None


def parse_date(
    value: Any,
) -> date | None:
    if value is None or value == "":
        return None

    if isinstance(value, date):
        return value

    if not isinstance(value, str):
        raise SeedDataError(f"Expected ISO date string, got: {value!r}")

    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise SeedDataError(f"Invalid ISO date: {value!r}") from exc


def normalise_string_list(
    value: Any,
    *,
    field_name: str,
) -> list[str]:
    if value is None:
        return []

    if not isinstance(value, list):
        raise SeedDataError(f"{field_name} must be a JSON array.")

    result: list[str] = []

    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise SeedDataError(f"{field_name} must contain non-empty strings.")

        result.append(item.strip())

    return list(dict.fromkeys(result))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def extract_users(
    raw: Any,
) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return raw

    if isinstance(raw, dict):
        for key in (
            "users",
            "identities",
            "data",
        ):
            value = raw.get(key)

            if isinstance(value, list):
                return value

    raise SeedDataError(
        "identities.json must contain either a JSON array "
        "or an object containing a users/identities/data array."
    )


def extract_user_fields(
    raw: dict[str, Any],
) -> dict[str, Any]:
    user_id = require_string(
        raw,
        "user_id",
        "id",
        "username",
    )

    display_name = require_string(
        raw,
        "display_name",
        "name",
    )

    department = require_string(
        raw,
        "department",
    )

    roles = normalise_string_list(
        first_present(
            raw,
            "roles",
            "role",
        ),
        field_name="roles",
    )

    groups = normalise_string_list(
        first_present(
            raw,
            "groups",
            "group",
        ),
        field_name="groups",
    )

    return {
        "user_id": user_id,
        "display_name": display_name,
        "department": department,
        "roles": roles,
        "groups": groups,
    }


def extract_document_fields(
    raw: dict[str, Any],
) -> dict[str, Any]:
    document_id = require_string(
        raw,
        "document_id",
        "id",
    )

    title = require_string(
        raw,
        "title",
        "name",
    )

    version = require_string(
        raw,
        "version",
    )

    status = require_string(
        raw,
        "status",
    )

    classification = require_string(
        raw,
        "classification",
    )

    effective_date = parse_date(
        first_present(
            raw,
            "effective_date",
            "effectiveDate",
        )
    )

    source_path = optional_string(
        raw,
        "source_path",
        "sourcePath",
        "path",
    )

    return {
        "document_id": document_id,
        "title": title,
        "version": version,
        "status": status,
        "classification": classification,
        "effective_date": effective_date,
        "source_path": source_path,
    }


def extract_permissions(
    raw: dict[str, Any],
) -> list[tuple[str, bool]]:
    """
    Extract explicit group permissions.

    Supported representations:

    allowed_groups: ["group-a", "group-b"]
    denied_groups: ["group-c"]

    permissions:
        [
            {"group": "group-a", "allowed": true},
            {"group": "group-b", "allowed": false}
        ]

    access:
        [
            {"group": "group-a", "allowed": true},
            {"group": "group-b", "allowed": false}
        ]

    If no authorization metadata is present, an empty list is
    returned. This means no group-specific restriction is
    represented by the supplied record.

    We deliberately do not infer access from classification,
    department, role, document content, or document title.
    """

    permissions: list[tuple[str, bool]] = []

    allowed_groups = normalise_string_list(
        first_present(
            raw,
            "allowed_groups",
            "allowedGroups",
        ),
        field_name="allowed_groups",
    )

    denied_groups = normalise_string_list(
        first_present(
            raw,
            "denied_groups",
            "deniedGroups",
        ),
        field_name="denied_groups",
    )

    for group in allowed_groups:
        permissions.append((group, True))

    for group in denied_groups:
        permissions.append((group, False))

    explicit_permissions = first_present(
        raw,
        "permissions",
        "access",
        "document_permissions",
    )

    if explicit_permissions is not None:
        if not isinstance(
            explicit_permissions,
            list,
        ):
            raise SeedDataError("Document permissions/access must be a JSON array.")

        for item in explicit_permissions:
            if not isinstance(item, dict):
                raise SeedDataError("Every document permission must be an object.")

            group = require_string(
                item,
                "group",
                "group_name",
            )

            allowed = item.get("allowed")

            if not isinstance(allowed, bool):
                raise SeedDataError(
                    f"Permission for group {group!r} "
                    f"must contain boolean 'allowed'."
                )

            permissions.append((group, allowed))

    return reconcile_permissions(permissions)


def reconcile_permissions(
    pairs: list[tuple[str, bool]],
) -> list[tuple[str, bool]]:
    """Deduplicate (group, allowed) pairs, raising if a group is given
    conflicting allow/deny values from different sources."""

    deduplicated: dict[str, bool] = {}

    for group, allowed in pairs:
        if group in deduplicated and deduplicated[group] != allowed:
            raise SeedDataError(f"Conflicting permissions for group " f"{group!r}.")

        deduplicated[group] = allowed

    return list(deduplicated.items())


def extract_document_overrides(
    raw: Any,
) -> dict[str, list[tuple[str, bool]]]:
    """
    Parse the `document_overrides` section of entitlements.json into a
    mapping of document_id -> [(group, allowed), ...].

    Classification-level `rules` in entitlements.json (e.g. INTERNAL ->
    all_employees) are deliberately not read here: they describe default,
    classification-driven access that the application applies at query
    time from DocumentModel.classification, and there is no table for
    them in the schema. Only explicit per-document overrides — including
    denies, which cannot be expressed via the corpus record alone — are
    persisted to document_overrides.
    """

    if not isinstance(raw, dict):
        raise SeedDataError("entitlements.json must contain a JSON object.")

    overrides_raw = raw.get("document_overrides", [])

    if not isinstance(overrides_raw, list):
        raise SeedDataError(
            "entitlements.json 'document_overrides' must be a JSON array."
        )

    overrides: dict[str, list[tuple[str, bool]]] = {}

    for item in overrides_raw:
        if not isinstance(item, dict):
            raise SeedDataError(
                "Every entry in entitlements.json 'document_overrides' "
                "must be a JSON object."
            )

        document_id = require_string(item, "document_id")

        allow_groups = normalise_string_list(
            first_present(item, "allow_groups", "allowed_groups"),
            field_name="allow_groups",
        )

        deny_groups = normalise_string_list(
            first_present(item, "deny_groups", "denied_groups"),
            field_name="deny_groups",
        )

        pairs = [(group, True) for group in allow_groups] + [
            (group, False) for group in deny_groups
        ]

        if document_id in overrides:
            raise SeedDataError(
                f"Duplicate document_overrides entry for "
                f"{document_id!r} in entitlements.json."
            )

        overrides[document_id] = reconcile_permissions(pairs)

    return overrides


def extract_chunks(
    raw: dict[str, Any],
) -> list[dict[str, Any]]:
    raw_chunks = raw.get("chunks")

    if raw_chunks is None:
        content = raw.get("content")

        if content is None:
            raise SeedDataError(
                "Document record contains neither 'chunks' " "nor 'content'."
            )

        if not isinstance(content, str):
            raise SeedDataError("Document 'content' must be a string.")

        return [
            {
                "chunk_index": 0,
                "content": content,
                "section_title": raw.get("section_title"),
                "metadata_json": {},
            }
        ]

    if not isinstance(raw_chunks, list):
        raise SeedDataError("'chunks' must be a JSON array.")

    chunks: list[dict[str, Any]] = []

    for position, raw_chunk in enumerate(raw_chunks):
        if not isinstance(raw_chunk, dict):
            raise SeedDataError("Every chunk must be a JSON object.")

        content = raw_chunk.get("content")

        if not isinstance(content, str) or not content.strip():
            raise SeedDataError("Every chunk must contain non-empty " "'content'.")

        chunk_index = raw_chunk.get(
            "chunk_index",
            position,
        )

        if not isinstance(chunk_index, int):
            raise SeedDataError("chunk_index must be an integer.")

        section_title = raw_chunk.get("section_title")

        if section_title is not None and not isinstance(
            section_title,
            str,
        ):
            raise SeedDataError("section_title must be a string.")

        metadata_json = raw_chunk.get(
            "metadata_json",
            {},
        )

        if not isinstance(metadata_json, dict):
            raise SeedDataError("metadata_json must be an object.")

        chunks.append(
            {
                "chunk_index": chunk_index,
                "content": content,
                "section_title": section_title,
                "metadata_json": metadata_json,
            }
        )

    return chunks


def extract_content_hash(
    raw: dict[str, Any],
    chunks: list[dict[str, Any]],
) -> str:
    supplied_hash = optional_string(
        raw,
        "content_hash",
        "contentHash",
    )

    if supplied_hash is not None:
        if len(supplied_hash) != 64:
            raise SeedDataError("content_hash must be a SHA-256 hexadecimal string.")

        return supplied_hash

    canonical_content = "\n".join(chunk["content"] for chunk in chunks)

    return sha256_text(canonical_content)


async def seed_users(
    session: AsyncSession,
    identities_path: Path,
) -> int:
    raw = load_json(identities_path)

    records = extract_users(raw)

    repository = UserRepository(session)

    created_count = 0

    for raw_user in records:
        if not isinstance(raw_user, dict):
            raise SeedDataError("Every identity must be a JSON object.")

        user_data = extract_user_fields(raw_user)

        user = await repository.get_by_user_id(user_data["user_id"])

        if user is None:
            user = await repository.create(**user_data)
            created_count += 1
        else:
            user.display_name = user_data["display_name"]
            user.department = user_data["department"]

            existing_roles = {item.role for item in user.roles}

            existing_groups = {item.group for item in user.groups}

            for role in user_data["roles"]:
                if role not in existing_roles:
                    await repository.add_role(
                        user,
                        role,
                    )

            for group in user_data["groups"]:
                if group not in existing_groups:
                    await repository.add_group(
                        user,
                        group,
                    )

    return created_count


async def seed_document(
    session: AsyncSession,
    raw: dict[str, Any],
    entitlement_overrides: dict[str, list[tuple[str, bool]]],
) -> tuple[bool, int]:
    document_data = extract_document_fields(raw)

    chunks = extract_chunks(raw)

    content_hash = extract_content_hash(
        raw,
        chunks,
    )

    permissions = reconcile_permissions(
        extract_permissions(raw)
        + entitlement_overrides.get(document_data["document_id"], [])
    )

    document_repository = DocumentRepository(session)

    chunk_repository = ChunkRepository(session)

    existing_documents = await document_repository.get_by_document_id(
        document_data["document_id"],
    )

    document = next(
        (
            candidate
            for candidate in existing_documents
            if candidate.version == document_data["version"]
        ),
        None,
    )

    created = document is None

    if document is None:
        document = await document_repository.create(
            **document_data,
            content_hash=content_hash,
        )
    else:
        document.title = document_data["title"]
        document.status = document_data["status"]
        document.classification = document_data["classification"]
        document.effective_date = document_data["effective_date"]
        document.source_path = document_data["source_path"]
        document.content_hash = content_hash

        await chunk_repository.delete_for_document(document.id)

    # Reload through the eager-loading query so `.override` is safely
    # populated. A bare read of an unloaded relationship on a persistent
    # object -- even one just created in this same session -- tries to
    # run a lazy SELECT outside of an async-safe context and raises
    # MissingGreenlet under AsyncSession; only a real selectinload query
    # (as get_by_id runs) avoids it.
    document = await document_repository.get_by_id(document.id)

    if permissions:
        override = await document_repository.create_override(document)

        # create_override() may have just inserted a brand-new override
        # row, whose `.groups` collection has likewise never been
        # eager-loaded. Reload once more so the read below is safe.
        document = await document_repository.get_by_id(document.id)
        override = document.override

        existing_groups = list(override.groups)

        for existing in existing_groups:
            await session.delete(existing)

        await session.flush()

        for group, allowed in permissions:
            await document_repository.set_group_permission(
                document,
                group,
                allowed,
            )
    else:
        if document.override is not None:
            for permission in list(document.override.groups):
                await session.delete(permission)

            await session.flush()

            await session.delete(document.override)

            await session.flush()

    await chunk_repository.create_many(
        document_db_id=document.id,
        chunks=chunks,
    )

    return (
        created,
        len(chunks),
    )


async def seed_documents(
    session: AsyncSession,
    corpus_path: Path,
    entitlement_overrides: dict[str, list[tuple[str, bool]]],
) -> tuple[int, int]:
    records = load_jsonl(corpus_path)

    created_count = 0
    chunk_count = 0

    for record in records:
        created, chunks = await seed_document(
            session,
            record,
            entitlement_overrides,
        )

        if created:
            created_count += 1

        chunk_count += chunks

    return (
        created_count,
        chunk_count,
    )


async def seed(
    identities_path: Path,
    corpus_path: Path,
    entitlements_path: Path,
) -> None:
    if not identities_path.exists():
        raise SeedDataError(f"Identity file does not exist: " f"{identities_path}")

    if not corpus_path.exists():
        raise SeedDataError(f"Corpus file does not exist: " f"{corpus_path}")

    if not entitlements_path.exists():
        raise SeedDataError(
            f"Entitlements file does not exist: " f"{entitlements_path}"
        )

    await init_db()  # ensure pgvector + tables exist

    entitlement_overrides = extract_document_overrides(load_json(entitlements_path))

    async with ASYNC_SESSION_LOCAL() as session:
        try:
            users_created = await seed_users(session, identities_path)
            documents_created, chunks_created = await seed_documents(
                session,
                corpus_path,
                entitlement_overrides,
            )
            await session.commit()
        except Exception:
            await session.rollback()
            raise

        # index data as well
        chunks_indexed = await ChunkIndexer(session).index_unindexed_chunks()

    await close_db()

    print("Database seed completed successfully.")
    print(f"New users: {users_created}")
    print(f"New documents: {documents_created}")
    print(f"Chunks processed: {chunks_created}")
    print(f"Chunks indexed: {chunks_indexed}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Seed users, documents, permissions, "
            "and chunks from the supplied assessment data."
        )
    )

    parser.add_argument(
        "--identities",
        type=Path,
        default=DEFAULT_IDENTITIES_PATH,
    )

    parser.add_argument(
        "--corpus",
        type=Path,
        default=DEFAULT_CORPUS_PATH,
    )

    parser.add_argument(
        "--entitlements",
        type=Path,
        default=DEFAULT_ENTITLEMENTS_PATH,
    )

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
