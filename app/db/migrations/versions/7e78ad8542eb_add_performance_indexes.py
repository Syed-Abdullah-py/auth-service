"""Add performance indexes on FK columns

Revision ID: 7e78ad8542eb
Revises: 31fb1a4aa513
Create Date: 2026-04-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '7e78ad8542eb'
down_revision: Union[str, None] = '31fb1a4aa513'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index('ix_patients_workspace_id', 'patients', ['workspace_id'])
    op.create_index('ix_cases_patient_id', 'cases', ['patient_id'])
    op.create_index('ix_cases_assigned_to_member_id', 'cases', ['assigned_to_member_id'])
    op.create_index('ix_workspace_members_workspace_id', 'workspace_members', ['workspace_id'])
    op.create_index('ix_workspace_members_user_id', 'workspace_members', ['user_id'])
    op.create_index('ix_join_requests_workspace_id', 'join_requests', ['workspace_id'])
    op.create_index('ix_invitations_workspace_id', 'invitations', ['workspace_id'])


def downgrade() -> None:
    op.drop_index('ix_invitations_workspace_id', table_name='invitations')
    op.drop_index('ix_join_requests_workspace_id', table_name='join_requests')
    op.drop_index('ix_workspace_members_user_id', table_name='workspace_members')
    op.drop_index('ix_workspace_members_workspace_id', table_name='workspace_members')
    op.drop_index('ix_cases_assigned_to_member_id', table_name='cases')
    op.drop_index('ix_cases_patient_id', table_name='cases')
    op.drop_index('ix_patients_workspace_id', table_name='patients')