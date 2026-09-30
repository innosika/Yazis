"""Initial schema: dictionary, sense overrides, translation memory, OOV queue, documents.

Revision ID: 0001
Revises: None
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Trigram similarity is what gives the translation memory its fuzzy match percentage.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_table(
        "dict_entry",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("headword", sa.String(200), nullable=False),
        sa.Column("headword_norm", sa.String(200), nullable=False),
        sa.Column("pos", sa.String(32)),
        sa.Column("ipa", sa.String(200)),
        sa.Column("word_count", sa.Integer, nullable=False, server_default="1"),
        sa.Column("source", sa.String(32), nullable=False, server_default="freedict"),
        sa.Column("is_user", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("headword_norm", "pos", name="uq_dict_entry_headword_pos"),
    )
    op.create_index("ix_dict_entry_headword_norm", "dict_entry", ["headword_norm"])
    op.create_index("ix_dict_entry_lookup", "dict_entry", ["headword_norm", "pos"])
    op.create_index("ix_dict_entry_words", "dict_entry", ["word_count"])

    op.create_table(
        "dict_sense",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "entry_id",
            sa.Integer,
            sa.ForeignKey("dict_entry.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("idx", sa.Integer, nullable=False),
        sa.Column("gloss", sa.Text, nullable=False, server_default=""),
        sa.Column("labels", postgresql.ARRAY(sa.Text), nullable=False, server_default="{}"),
        sa.Column("domain_scores", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.UniqueConstraint("entry_id", "idx", name="uq_dict_sense_entry_idx"),
    )
    op.create_index("ix_dict_sense_entry_id", "dict_sense", ["entry_id"])
    op.create_index("ix_dict_sense_labels", "dict_sense", ["labels"], postgresql_using="gin")

    op.create_table(
        "dict_translation",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "sense_id",
            sa.Integer,
            sa.ForeignKey("dict_sense.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("idx", sa.Integer, nullable=False),
        sa.Column("form_accented", sa.String(200), nullable=False),
        sa.Column("form_plain", sa.String(200), nullable=False),
        sa.Column("is_user", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("sense_id", "idx", name="uq_dict_translation_sense_idx"),
    )
    op.create_index("ix_dict_translation_sense_id", "dict_translation", ["sense_id"])

    op.create_table(
        "sense_override",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("headword_norm", sa.String(200), nullable=False),
        sa.Column("pos", sa.String(16), nullable=False),
        sa.Column("domain_code", sa.String(16), nullable=False),
        sa.Column(
            "sense_id",
            sa.Integer,
            sa.ForeignKey("dict_sense.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "translation_id",
            sa.Integer,
            sa.ForeignKey("dict_translation.id", ondelete="SET NULL"),
        ),
        sa.Column("note", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "headword_norm", "pos", "domain_code", name="uq_sense_override_word_pos_domain"
        ),
    )

    op.create_table(
        "tm_unit",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source_text", sa.Text, nullable=False),
        sa.Column("source_norm", sa.Text, nullable=False),
        sa.Column("target_text", sa.Text, nullable=False),
        sa.Column("domain_code", sa.String(16), nullable=False, server_default="general"),
        sa.Column("origin", sa.String(16), nullable=False, server_default="post-edit"),
        sa.Column("hits", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("source_norm", "domain_code", name="uq_tm_unit_source_domain"),
    )
    op.execute(
        "CREATE INDEX ix_tm_unit_source_norm_trgm ON tm_unit USING gin (source_norm gin_trgm_ops)"
    )

    op.create_table(
        "oov_term",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("lemma", sa.String(200), nullable=False),
        sa.Column("pos", sa.String(16), nullable=False),
        sa.Column("occurrences", sa.Integer, nullable=False, server_default="1"),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("suggestion", postgresql.JSONB),
        sa.Column("context", sa.Text),
        sa.Column("first_seen", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_seen", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("lemma", "pos", name="uq_oov_term_lemma_pos"),
    )
    op.create_index("ix_oov_term_rank", "oov_term", ["status", "occurrences"])

    op.create_table(
        "document",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("source_text", sa.Text, nullable=False),
        sa.Column("domain_code", sa.String(16), nullable=False, server_default="general"),
        sa.Column("mode", sa.String(16), nullable=False, server_default="transfer"),
        sa.Column("stats", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("duration_ms", sa.Float, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_document_created", "document", ["created_at"])


def downgrade() -> None:
    op.drop_table("document")
    op.drop_table("oov_term")
    op.drop_table("tm_unit")
    op.drop_table("sense_override")
    op.drop_table("dict_translation")
    op.drop_table("dict_sense")
    op.drop_table("dict_entry")
