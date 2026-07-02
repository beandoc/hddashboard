"""add ACM state-of-the-art optimizer fields to acm_recommendations

Adds model-based optimizer outputs: method, target-attainment probabilities,
ERI, resistance flag, optimizer dose, quantified iron dose, and HIF-PHI note.

Revision ID: h2i3j4k5l6m7
Revises: g1h2i3j4k5l6
Create Date: 2026-07-02

"""
from alembic import op

revision = 'h2i3j4k5l6m7'
down_revision = 'g1h2i3j4k5l6'
branch_labels = None
depends_on = None


_COLUMNS = [
    ('method',              'VARCHAR(24)'),
    ('prob_in_target',      'FLOAT'),
    ('prob_overshoot',      'FLOAT'),
    ('prob_undershoot',     'FLOAT'),
    ('eri',                 'FLOAT'),
    ('resistance_flag',     'BOOLEAN'),
    ('optimizer_dose_iu',   'FLOAT'),
    ('recommended_iron_mg', 'FLOAT'),
    ('hifphi_suggestion',   'TEXT'),
]


def upgrade() -> None:
    import sqlalchemy as sa
    bind = op.get_bind()
    if bind.dialect.name == 'sqlite':
        inspector = sa.inspect(bind)
        existing = [c['name'] for c in inspector.get_columns('acm_recommendations')]
        type_map = {
            'VARCHAR(24)': sa.String(24), 'FLOAT': sa.Float(),
            'BOOLEAN': sa.Boolean(), 'TEXT': sa.Text(),
        }
        for name, sqltype in _COLUMNS:
            if name not in existing:
                op.add_column('acm_recommendations', sa.Column(name, type_map[sqltype], nullable=True))
    else:
        for name, sqltype in _COLUMNS:
            op.execute(sa.text(
                f"ALTER TABLE acm_recommendations ADD COLUMN IF NOT EXISTS {name} {sqltype}"
            ))


def downgrade() -> None:
    for name, _ in reversed(_COLUMNS):
        op.drop_column('acm_recommendations', name)
