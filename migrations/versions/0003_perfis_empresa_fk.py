"""perfis_interesse.empresa_id: UUID com chave estrangeira para empresas

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-12 15:30:00

"""
import os
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, Sequence[str], None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FK = "perfis_interesse_empresa_id_fkey"
REMOVER_ORFAOS = "LICITALL_REMOVER_PERFIS_ORFAOS"

# Perfil sem empresa válida: texto que não é UUID (ex.: e-mail, de antes da autenticação real) ou UUID de empresa inexistente.
_ORFAOS = """
    from perfis_interesse p
    where not (
        p.empresa_id::text ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        and exists (select 1 from empresas e where e.id::text = lower(p.empresa_id::text))
    )
"""


def upgrade() -> None:
    """Liga cada perfil à sua empresa; excluir a empresa exclui os perfis (e, em cascata, regras, matches e agendamentos).

    Perfis órfãos não são apagados em silêncio: a migração para e diz quantos são. Para removê-los, rode de novo com
    LICITALL_REMOVER_PERFIS_ORFAOS=1. Tolerante a bancos que já têm o tipo novo (criados por `create_all`).
    """
    bind = op.get_bind()
    insp = sa.inspect(bind)
    coluna = next(c for c in insp.get_columns("perfis_interesse") if c["name"] == "empresa_id")
    tem_fk = any(fk["referred_table"] == "empresas" for fk in insp.get_foreign_keys("perfis_interesse"))

    orfaos = bind.execute(sa.text(f"select p.id, p.nome_perfil, p.empresa_id::text {_ORFAOS} order by p.nome_perfil")).all()
    if orfaos:
        if os.environ.get(REMOVER_ORFAOS) != "1":
            exemplos = "; ".join(f"{nome!r} (empresa_id={emp!r})" for _, nome, emp in orfaos[:5])
            raise RuntimeError(
                f"{len(orfaos)} perfil(is) de interesse sem empresa válida, inacessíveis a qualquer usuário: {exemplos}. "
                f"Para removê-los (com regras, oportunidades e agendamentos), rode a migração com {REMOVER_ORFAOS}=1."
            )
        bind.execute(sa.text(f"delete from perfis_interesse where id in (select p.id {_ORFAOS})"))

    if not isinstance(coluna["type"], sa.Uuid):
        op.alter_column(
            "perfis_interesse", "empresa_id",
            type_=sa.Uuid(), existing_type=sa.String(length=64), existing_nullable=False,
            postgresql_using="lower(empresa_id)::uuid",
        )
    if not tem_fk:
        op.create_foreign_key(FK, "perfis_interesse", "empresas", ["empresa_id"], ["id"], ondelete="CASCADE")


def downgrade() -> None:
    op.drop_constraint(FK, "perfis_interesse", type_="foreignkey")
    op.alter_column(
        "perfis_interesse", "empresa_id",
        type_=sa.String(length=64), existing_type=sa.Uuid(), existing_nullable=False,
        postgresql_using="empresa_id::text",
    )
