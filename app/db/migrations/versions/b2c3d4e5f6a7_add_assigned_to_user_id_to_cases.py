"""Add assigned_to_user_id to cases for stable doctor reference

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "cases",
        sa.Column(
            "assigned_to_user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    # Backfill from existing workspace_members for cases still actively assigned
    op.execute(
        """
        UPDATE cases
        SET assigned_to_user_id = workspace_members.user_id
        FROM workspace_members
        WHERE cases.assigned_to_member_id = workspace_members.id
        """
    )


def downgrade() -> None:
    op.drop_column("cases", "assigned_to_user_id")
