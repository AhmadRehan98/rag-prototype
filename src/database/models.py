"""SQLAlchemy models"""

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Date,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import declarative_base, relationship

from src.config.settings import settings

Base = declarative_base()


class UserModel(Base):
    """Based on identities.json"""

    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), unique=True, nullable=False, index=True)
    display_name = Column(String(255), nullable=False)
    department = Column(String(128), nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    roles = relationship(
        "UserRoleModel",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    groups = relationship(
        "UserGroupModel",
        back_populates="user",
        cascade="all, delete-orphan",
    )


class UserRoleModel(Base):
    """Based on identities.json. supplements base User table"""

    __tablename__ = "users_role"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = Column(String(64), nullable=False)
    user = relationship(
        "UserModel",
        back_populates="roles",
    )

    __table_args__ = (UniqueConstraint("user_id", "role"),)


class UserGroupModel(Base):
    """Based on identities.json. supplements base User table"""

    __tablename__ = "users_group"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    group = Column(String(64), nullable=False)
    user = relationship(
        "UserModel",
        back_populates="roles",
    )

    __table_args__ = (UniqueConstraint("user_id", "group"),)


class DocumentModel(Base):
    """Documents and their lifecycle/authority metadata."""

    __tablename__ = "documents"
    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(String(128), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    version = Column(String(32), nullable=False)
    status = Column(String(64), nullable=False, index=True)
    classification = Column(String(64), nullable=False, index=True)
    effective_date = Column(Date, nullable=True)
    content_hash = Column(String(64), nullable=False)
    source_path = Column(String(512), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    chunks = relationship(
        "ChunkModel",
        back_populates="document",
        cascade="all, delete-orphan",
    )
    override = relationship(
        "DocumentOverrideModel",
        back_populates="document",
        uselist=False,
        cascade="all, delete-orphan",
    )


class DocumentOverrideModel(Base):
    __tablename__ = "document_overrides"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(
        Integer,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    document = relationship(
        "DocumentModel",
        back_populates="override",
    )
    groups = relationship(
        "DocumentOverrideGroupModel",
        back_populates="override",
        cascade="all, delete-orphan",
    )


class DocumentOverrideGroupModel(Base):
    __tablename__ = "document_override_groups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_override_id = Column(
        Integer,
        ForeignKey("document_overrides.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    group = Column(String(64), nullable=False)
    allowed = Column(Boolean, nullable=False)
    override = relationship(
        "DocumentOverrideModel",
        back_populates="groups",
    )

    __table_args__ = (
        UniqueConstraint(
            "document_override_id",
            "group",
            name="uq_document_override_group",
        ),
    )


class ChunkModel(Base):
    __tablename__ = "chunks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_db_id = Column(
        Integer,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    section_title = Column(String(255), nullable=True)
    embedding = Column(
        Vector(settings.EMBEDDING_DIMENSION),
        nullable=True,
    )
    search_vector = Column(TSVECTOR, nullable=True)
    metadata_json = Column(
        JSONB,
        nullable=False,
        default=dict,
    )
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    document = relationship(
        "DocumentModel",
        back_populates="chunks",
    )

    __table_args__ = (
        UniqueConstraint(
            "document_db_id",
            "chunk_index",
            name="uq_chunk_document_index",
        ),
    )
