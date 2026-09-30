"""LLM assessor identity, oracle queries, run batches and judging jobs

Revision ID: 7f2c1a9e4b10
Revises: cd5ade427d8b
Create Date: 2026-09-03 10:20:00.000000

Written by hand: ``backend/alembic`` is mounted read-only into the API container, so
autogenerate cannot write here. Everything below is additive and nullable-or-defaulted,
so the upgrade is safe on a populated database.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "7f2c1a9e4b10"
down_revision: str | None = "cd5ade427d8b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # A topic's hand-built synonym query for the oracle pool run.
    op.add_column("query", sa.Column("oracle_query", sa.Text(), nullable=True))

    # Who produced a judgment: a human, the known-item generator, or a language model.
    op.add_column(
        "assessor",
        sa.Column("kind", sa.String(length=16), server_default="human", nullable=False),
    )
    op.add_column(
        "assessor",
        sa.Column(
            "meta",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.execute("UPDATE assessor SET kind = 'automatic' WHERE name = 'automatic (known-item)'")

    # The assessor's stated reason, for auditing single verdicts.
    op.add_column("judgment", sa.Column("note", sa.Text(), nullable=True))

    # Runs launched together by one request.
    op.add_column("eval_run", sa.Column("batch_id", sa.String(length=64), nullable=True))
    op.create_index(op.f("ix_eval_run_batch_id"), "eval_run", ["batch_id"], unique=False)

    op.create_table(
        "judging_job",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("collection_id", sa.Integer(), nullable=False),
        sa.Column("assessor_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("task_id", sa.String(length=64), nullable=True),
        sa.Column("total_pairs", sa.Integer(), server_default="0", nullable=False),
        sa.Column("judged_pairs", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failed_pairs", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["assessor_id"],
            ["assessor.id"],
            name=op.f("fk_judging_job_assessor_id_assessor"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["collection_id"],
            ["test_collection.id"],
            name=op.f("fk_judging_job_collection_id_test_collection"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_judging_job")),
    )
    op.create_index(op.f("ix_judging_job_created_at"), "judging_job", ["created_at"], unique=False)
    op.create_index(op.f("ix_judging_job_status"), "judging_job", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_judging_job_status"), table_name="judging_job")
    op.drop_index(op.f("ix_judging_job_created_at"), table_name="judging_job")
    op.drop_table("judging_job")
    op.drop_index(op.f("ix_eval_run_batch_id"), table_name="eval_run")
    op.drop_column("eval_run", "batch_id")
    op.drop_column("judgment", "note")
    op.drop_column("assessor", "meta")
    op.drop_column("assessor", "kind")
    op.drop_column("query", "oracle_query")
