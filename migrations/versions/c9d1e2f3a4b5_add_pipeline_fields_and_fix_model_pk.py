"""Add pipeline fields to documents; fix AGMT_MODELS_STG primary key

Revision ID: c9d1e2f3a4b5
Revises: b6cb821a5854
Create Date: 2026-07-24

Changes
-------
documents table
  + current_step      INTEGER  DEFAULT 0
  + confidence_score  INTEGER
  + error_message     TEXT
  + agmt_id           VARCHAR(50)

AGMT_MODELS_STG
  - Drop FK from AGMT_MDL_NORMAL_STG.MODEL_SEQ → AGMT_MODELS_STG.MODEL_SEQ
    (MODEL_SEQ is no longer the sole primary key, so the FK reference is invalid)
  - Drop sole PK on MODEL_SEQ
  - Add surrogate autoincrement  id  column as the new PK
  - Add UNIQUE(AGMT_ID, MODEL_SEQ) to preserve logical uniqueness per agreement
"""
from alembic import op
import sqlalchemy as sa


revision = "c9d1e2f3a4b5"
down_revision = "b6cb821a5854"
branch_labels = None
depends_on = None


def upgrade():
    # ------------------------------------------------------------------
    # 1. New columns on documents
    # ------------------------------------------------------------------
    op.add_column(
        "documents",
        sa.Column("current_step", sa.Integer(), server_default="0", nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("confidence_score", sa.Integer(), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("agmt_id", sa.String(length=50), nullable=True),
    )

    # ------------------------------------------------------------------
    # 2. Fix AGMT_MODELS_STG primary key
    #
    # We use raw SQL because:
    #  a) The original FK on AGMT_MDL_NORMAL_STG was created without an
    #     explicit name, so PostgreSQL auto-generated one.  A PL/pgSQL
    #     block discovers and drops it safely.
    #  b) Adding a SERIAL column and promoting it to PK is simpler in SQL
    #     than through op.* calls when the table already has a PK.
    # ------------------------------------------------------------------

    # 2a. Drop the unnamed FK from AGMT_MDL_NORMAL_STG.MODEL_SEQ → AGMT_MODELS_STG
    op.execute(
        """
        DO $$
        DECLARE r RECORD;
        BEGIN
            FOR r IN (
                SELECT tc.constraint_name
                FROM   information_schema.table_constraints  tc
                JOIN   information_schema.key_column_usage   kcu
                       ON  tc.constraint_name = kcu.constraint_name
                       AND tc.table_schema    = kcu.table_schema
                WHERE  tc.table_name      = 'AGMT_MDL_NORMAL_STG'
                AND    tc.constraint_type = 'FOREIGN KEY'
                AND    kcu.column_name    = 'MODEL_SEQ'
            ) LOOP
                EXECUTE format(
                    'ALTER TABLE "AGMT_MDL_NORMAL_STG" DROP CONSTRAINT "%s"',
                    r.constraint_name
                );
            END LOOP;
        END $$;
        """
    )

    # 2b. Drop the existing sole PK on AGMT_MODELS_STG (constraint name is
    #     "AGMT_MODELS_STG_pkey" — the default PostgreSQL naming convention).
    op.execute(
        'ALTER TABLE "AGMT_MODELS_STG" DROP CONSTRAINT IF EXISTS "AGMT_MODELS_STG_pkey"'
    )

    # 2c. Add the surrogate id column with SERIAL (auto-populates existing rows)
    op.execute(
        'ALTER TABLE "AGMT_MODELS_STG" ADD COLUMN id SERIAL'
    )

    # 2d. Promote id to PK
    op.execute(
        'ALTER TABLE "AGMT_MODELS_STG" ADD PRIMARY KEY (id)'
    )

    # 2e. Unique constraint on (AGMT_ID, MODEL_SEQ) for data integrity
    op.execute(
        """
        ALTER TABLE "AGMT_MODELS_STG"
        ADD CONSTRAINT uq_agmt_model_seq UNIQUE ("AGMT_ID", "MODEL_SEQ")
        """
    )


def downgrade():
    # ------------------------------------------------------------------
    # Remove documents columns
    # ------------------------------------------------------------------
    op.drop_column("documents", "agmt_id")
    op.drop_column("documents", "error_message")
    op.drop_column("documents", "confidence_score")
    op.drop_column("documents", "current_step")

    # ------------------------------------------------------------------
    # Reverting AGMT_MODELS_STG is destructive (id values have no meaning
    # in the original schema).  This downgrade only removes the unique
    # constraint and the id column; it does NOT restore the original
    # MODEL_SEQ-only PK because that would break any existing rows.
    # Run a manual schema reset if a full rollback is required.
    # ------------------------------------------------------------------
    op.execute(
        'ALTER TABLE "AGMT_MODELS_STG" DROP CONSTRAINT IF EXISTS uq_agmt_model_seq'
    )
    op.execute(
        'ALTER TABLE "AGMT_MODELS_STG" DROP CONSTRAINT IF EXISTS "AGMT_MODELS_STG_pkey"'
    )
    op.execute(
        'ALTER TABLE "AGMT_MODELS_STG" DROP COLUMN IF EXISTS id'
    )
    # Restore original PK (will fail if duplicate MODEL_SEQ rows exist)
    op.execute(
        'ALTER TABLE "AGMT_MODELS_STG" ADD PRIMARY KEY ("MODEL_SEQ")'
    )
