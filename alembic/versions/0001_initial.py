"""initial

Revision ID: 0001_initial
Revises: 
Create Date: 2025-09-06 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime

revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id', sa.Integer, primary_key=True, index=True),
        sa.Column('username', sa.String, nullable=True),
        sa.Column('first_name', sa.String, nullable=True),
        sa.Column('last_name', sa.String, nullable=True),
        sa.Column('notifications_enabled', sa.Boolean, default=True),
    )

    op.create_table(
        'weeks',
        sa.Column('week_id', sa.String, primary_key=True),
        sa.Column('created_at', sa.DateTime, default=datetime.utcnow),
    )

    op.create_table(
        'posts',
        sa.Column('id', sa.Integer, primary_key=True, index=True),
        sa.Column('week_id', sa.String, sa.ForeignKey("weeks.week_id", name="fk_posts_weeks")),
        sa.Column('title', sa.String, nullable=False),
        sa.Column('text', sa.Text, nullable=False),
        sa.Column('status', sa.String, default="draft"),
    )

    op.create_table(
        'post_edits',
        sa.Column('id', sa.Integer, primary_key=True, index=True),
        sa.Column('post_id', sa.Integer, sa.ForeignKey("posts.id", name="fk_edits_posts")),
        sa.Column('user_id', sa.Integer, sa.ForeignKey("users.id", name="fk_edits_users")),
        sa.Column('text', sa.Text, nullable=False),
        sa.Column('created_at', sa.DateTime, default=datetime.utcnow),
    )

    op.create_table(
        'post_versions',
        sa.Column('id', sa.Integer, primary_key=True, index=True),
        sa.Column('post_id', sa.Integer, sa.ForeignKey("posts.id", name="fk_versions_posts")),
        sa.Column('text', sa.Text, nullable=False),
        sa.Column('created_at', sa.DateTime, default=datetime.utcnow),
    )

    op.create_table(
        'subscriptions',
        sa.Column('id', sa.Integer, primary_key=True, index=True),
        sa.Column('user_id', sa.Integer, sa.ForeignKey("users.id", name="fk_subs_users")),
        sa.Column('plan', sa.String),
        sa.Column('start_date', sa.Date),
        sa.Column('end_date', sa.Date),
    )

    op.create_table(
        'orders',
        sa.Column('id', sa.Integer, primary_key=True, index=True),
        sa.Column('user_id', sa.Integer, sa.ForeignKey("users.id", name="fk_orders_users")),
        sa.Column('product_name', sa.String),
        sa.Column('price', sa.Integer),
        sa.Column('status', sa.String, default="pending"),
        sa.Column('created_at', sa.DateTime, default=datetime.utcnow),
    )

    op.create_table(
        'broadcasts',
        sa.Column('id', sa.Integer, primary_key=True, index=True),
        sa.Column('text', sa.Text, nullable=False),
        sa.Column('status', sa.String, default="scheduled"),
        sa.Column('scheduled_at', sa.DateTime, default=datetime.utcnow),
        sa.Column('recipients_count', sa.Integer, default=0),
        sa.Column('sent_count', sa.Integer, default=0),
    )

    op.create_table(
        'broadcast_recipients',
        sa.Column('id', sa.Integer, primary_key=True, index=True),
        sa.Column('broadcast_id', sa.Integer, sa.ForeignKey("broadcasts.id", name="fk_broadcast_users")),
        sa.Column('user_id', sa.Integer, sa.ForeignKey("users.id", name="fk_broadcast_users_id")),
        sa.Column('delivered', sa.Boolean, default=False),
    )


def downgrade() -> None:
    op.drop_table('broadcast_recipients')
    op.drop_table('broadcasts')
    op.drop_table('orders')
    op.drop_table('subscriptions')
    op.drop_table('post_versions')
    op.drop_table('post_edits')
    op.drop_table('posts')
    op.drop_table('weeks')
    op.drop_table('users')