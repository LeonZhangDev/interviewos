"""v0.7 baseline schema.

Captures the exact table set that app startup previously created with
Base.metadata.create_all. Existing v0.7 databases should be stamped with this
revision before upgrading: `alembic stamp 0001_v07_baseline`.

Revision ID: 0001_v07_baseline
Revises:
Create Date: 2026-09-06

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001_v07_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('coding_challenges',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('slug', sa.String(length=120), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('category', sa.String(length=80), nullable=False),
    sa.Column('difficulty', sa.Integer(), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('function_name', sa.String(length=120), nullable=False),
    sa.Column('starter_code', sa.Text(), nullable=False),
    sa.Column('reference_solution', sa.Text(), nullable=False),
    sa.Column('public_tests', sa.Text(), nullable=False),
    sa.Column('hidden_tests', sa.Text(), nullable=False),
    sa.Column('expected_time', sa.String(length=80), nullable=False),
    sa.Column('expected_space', sa.String(length=80), nullable=False),
    sa.Column('hints', sa.Text(), nullable=False),
    sa.Column('tags', sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_coding_challenges_category'), 'coding_challenges', ['category'], unique=False)
    op.create_index(op.f('ix_coding_challenges_slug'), 'coding_challenges', ['slug'], unique=True)
    op.create_table('interview_sessions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('role', sa.String(length=120), nullable=False),
    sa.Column('focus', sa.String(length=255), nullable=False),
    sa.Column('difficulty', sa.String(length=40), nullable=False),
    sa.Column('duration', sa.Integer(), nullable=False),
    sa.Column('script', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('mastery',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('topic', sa.String(length=120), nullable=False),
    sa.Column('score', sa.Float(), nullable=False),
    sa.Column('due_at', sa.DateTime(), nullable=False),
    sa.Column('interval_days', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('topic', name='uq_mastery_topic')
    )
    op.create_index(op.f('ix_mastery_topic'), 'mastery', ['topic'], unique=False)
    op.create_table('question_import_batches',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('owner', sa.String(length=80), nullable=False),
    sa.Column('source_format', sa.String(length=20), nullable=False),
    sa.Column('total', sa.Integer(), nullable=False),
    sa.Column('created', sa.Integer(), nullable=False),
    sa.Column('skipped', sa.Integer(), nullable=False),
    sa.Column('errors_json', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_question_import_batches_owner'), 'question_import_batches', ['owner'], unique=False)
    op.create_table('questions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('slug', sa.String(length=120), nullable=False),
    sa.Column('category', sa.String(length=80), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('difficulty', sa.Integer(), nullable=False),
    sa.Column('answer', sa.Text(), nullable=False),
    sa.Column('code', sa.Text(), nullable=False),
    sa.Column('followups', sa.Text(), nullable=False),
    sa.Column('project_link', sa.String(length=120), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_questions_category'), 'questions', ['category'], unique=False)
    op.create_index(op.f('ix_questions_slug'), 'questions', ['slug'], unique=True)
    op.create_table('repositories',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('provider', sa.String(length=20), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('url', sa.String(length=500), nullable=False),
    sa.Column('branch', sa.String(length=120), nullable=False),
    sa.Column('last_commit', sa.String(length=64), nullable=False),
    sa.Column('file_count', sa.Integer(), nullable=False),
    sa.Column('summary', sa.Text(), nullable=False),
    sa.Column('synced_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('provider', 'url', 'branch', name='uq_repository_source')
    )
    op.create_index(op.f('ix_repositories_provider'), 'repositories', ['provider'], unique=False)
    op.create_table('system_design_canvases',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('owner', sa.String(length=80), nullable=False),
    sa.Column('case_id', sa.String(length=120), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('nodes_json', sa.Text(), nullable=False),
    sa.Column('edges_json', sa.Text(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_system_design_canvases_case_id'), 'system_design_canvases', ['case_id'], unique=False)
    op.create_index(op.f('ix_system_design_canvases_owner'), 'system_design_canvases', ['owner'], unique=False)
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('username', sa.String(length=80), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('password_hash', sa.String(length=500), nullable=False),
    sa.Column('display_name', sa.String(length=120), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)
    op.create_table('answer_versions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('question_id', sa.Integer(), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('score', sa.Float(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['question_id'], ['questions.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_answer_versions_question_id'), 'answer_versions', ['question_id'], unique=False)
    op.create_table('code_explanation_attempts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('question_id', sa.Integer(), nullable=True),
    sa.Column('code', sa.Text(), nullable=False),
    sa.Column('explanation', sa.Text(), nullable=False),
    sa.Column('score', sa.Float(), nullable=False),
    sa.Column('feedback', sa.Text(), nullable=False),
    sa.Column('followup', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['question_id'], ['questions.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('coding_submissions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('challenge_id', sa.Integer(), nullable=False),
    sa.Column('code', sa.Text(), nullable=False),
    sa.Column('passed', sa.Integer(), nullable=False),
    sa.Column('public_passed', sa.Integer(), nullable=False),
    sa.Column('public_total', sa.Integer(), nullable=False),
    sa.Column('hidden_passed', sa.Integer(), nullable=False),
    sa.Column('hidden_total', sa.Integer(), nullable=False),
    sa.Column('time_complexity', sa.String(length=80), nullable=False),
    sa.Column('space_complexity', sa.String(length=80), nullable=False),
    sa.Column('time_match', sa.Integer(), nullable=False),
    sa.Column('space_match', sa.Integer(), nullable=False),
    sa.Column('mode', sa.String(length=30), nullable=False),
    sa.Column('duration_ms', sa.Float(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['challenge_id'], ['coding_challenges.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_coding_submissions_challenge_id'), 'coding_submissions', ['challenge_id'], unique=False)
    op.create_table('coding_wrongbook',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('challenge_id', sa.Integer(), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('last_error', sa.Text(), nullable=False),
    sa.Column('last_code', sa.Text(), nullable=False),
    sa.Column('resolved', sa.Integer(), nullable=False),
    sa.Column('last_attempt_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['challenge_id'], ['coding_challenges.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('challenge_id', name='uq_coding_wrong_challenge')
    )
    op.create_index(op.f('ix_coding_wrongbook_challenge_id'), 'coding_wrongbook', ['challenge_id'], unique=False)
    op.create_table('interview_recordings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('session_id', sa.Integer(), nullable=False),
    sa.Column('owner', sa.String(length=80), nullable=False),
    sa.Column('mime_type', sa.String(length=120), nullable=False),
    sa.Column('file_path', sa.String(length=700), nullable=False),
    sa.Column('transcript', sa.Text(), nullable=False),
    sa.Column('duration_ms', sa.Float(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['session_id'], ['interview_sessions.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_interview_recordings_owner'), 'interview_recordings', ['owner'], unique=False)
    op.create_index(op.f('ix_interview_recordings_session_id'), 'interview_recordings', ['session_id'], unique=False)
    op.create_table('interview_reports',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('session_id', sa.Integer(), nullable=False),
    sa.Column('overall_score', sa.Float(), nullable=False),
    sa.Column('skill_scores', sa.Text(), nullable=False),
    sa.Column('strengths', sa.Text(), nullable=False),
    sa.Column('weaknesses', sa.Text(), nullable=False),
    sa.Column('review_plan', sa.Text(), nullable=False),
    sa.Column('summary', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['session_id'], ['interview_sessions.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_interview_reports_session_id'), 'interview_reports', ['session_id'], unique=False)
    op.create_table('interview_turns',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('session_id', sa.Integer(), nullable=False),
    sa.Column('question_id', sa.Integer(), nullable=True),
    sa.Column('interviewer_prompt', sa.Text(), nullable=False),
    sa.Column('user_answer', sa.Text(), nullable=False),
    sa.Column('score', sa.Float(), nullable=False),
    sa.Column('feedback', sa.Text(), nullable=False),
    sa.Column('followup', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['question_id'], ['questions.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['session_id'], ['interview_sessions.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_interview_turns_session_id'), 'interview_turns', ['session_id'], unique=False)
    op.create_table('repo_files',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('repository_id', sa.Integer(), nullable=False),
    sa.Column('path', sa.String(length=700), nullable=False),
    sa.Column('language', sa.String(length=80), nullable=False),
    sa.Column('size', sa.Integer(), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('symbols', sa.Text(), nullable=False),
    sa.Column('knowledge', sa.Text(), nullable=False),
    sa.Column('questions', sa.Text(), nullable=False),
    sa.ForeignKeyConstraint(['repository_id'], ['repositories.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('repository_id', 'path', name='uq_repo_file_path')
    )
    op.create_index(op.f('ix_repo_files_path'), 'repo_files', ['path'], unique=False)
    op.create_index(op.f('ix_repo_files_repository_id'), 'repo_files', ['repository_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_repo_files_repository_id'), table_name='repo_files')
    op.drop_index(op.f('ix_repo_files_path'), table_name='repo_files')
    op.drop_table('repo_files')
    op.drop_index(op.f('ix_interview_turns_session_id'), table_name='interview_turns')
    op.drop_table('interview_turns')
    op.drop_index(op.f('ix_interview_reports_session_id'), table_name='interview_reports')
    op.drop_table('interview_reports')
    op.drop_index(op.f('ix_interview_recordings_session_id'), table_name='interview_recordings')
    op.drop_index(op.f('ix_interview_recordings_owner'), table_name='interview_recordings')
    op.drop_table('interview_recordings')
    op.drop_index(op.f('ix_coding_wrongbook_challenge_id'), table_name='coding_wrongbook')
    op.drop_table('coding_wrongbook')
    op.drop_index(op.f('ix_coding_submissions_challenge_id'), table_name='coding_submissions')
    op.drop_table('coding_submissions')
    op.drop_table('code_explanation_attempts')
    op.drop_index(op.f('ix_answer_versions_question_id'), table_name='answer_versions')
    op.drop_table('answer_versions')
    op.drop_index(op.f('ix_users_username'), table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
    op.drop_index(op.f('ix_system_design_canvases_owner'), table_name='system_design_canvases')
    op.drop_index(op.f('ix_system_design_canvases_case_id'), table_name='system_design_canvases')
    op.drop_table('system_design_canvases')
    op.drop_index(op.f('ix_repositories_provider'), table_name='repositories')
    op.drop_table('repositories')
    op.drop_index(op.f('ix_questions_slug'), table_name='questions')
    op.drop_index(op.f('ix_questions_category'), table_name='questions')
    op.drop_table('questions')
    op.drop_index(op.f('ix_question_import_batches_owner'), table_name='question_import_batches')
    op.drop_table('question_import_batches')
    op.drop_index(op.f('ix_mastery_topic'), table_name='mastery')
    op.drop_table('mastery')
    op.drop_table('interview_sessions')
    op.drop_index(op.f('ix_coding_challenges_slug'), table_name='coding_challenges')
    op.drop_index(op.f('ix_coding_challenges_category'), table_name='coding_challenges')
    op.drop_table('coding_challenges')
