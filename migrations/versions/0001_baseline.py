"""baseline: esquema completo da Fase 6 (14 tabelas)

Revision ID: 0001
Revises: 
Create Date: 2026-10-12 08:29:44.304793

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")  # pgvector (usado nas fases de busca vetorial)
    op.create_table('anexos_contratacao',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('id_pncp', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
    sa.Column('tipo_documento', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=True),
    sa.Column('titulo', sa.Text(), nullable=True),
    sa.Column('url_download', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('id_pncp', 'url_download', name='unq_anexo_contratacao')
    )
    op.create_index(op.f('ix_anexos_contratacao_id_pncp'), 'anexos_contratacao', ['id_pncp'], unique=False)
    op.create_table('embeddings_cache',
    sa.Column('content_hash', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
    sa.Column('backend', sqlmodel.sql.sqltypes.AutoString(length=32), nullable=False),
    sa.Column('texto_base', sa.Text(), nullable=False),
    sa.Column('embedding', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('content_hash', 'backend')
    )
    op.create_table('empresas',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('nome', sqlmodel.sql.sqltypes.AutoString(length=200), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('itens_contratacao',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('id_pncp', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
    sa.Column('numero_item', sa.Integer(), nullable=False),
    sa.Column('descricao', sa.Text(), nullable=False),
    sa.Column('tipo', sqlmodel.sql.sqltypes.AutoString(length=1), nullable=True),
    sa.Column('codigo_catmat_catser', sa.Integer(), nullable=True),
    sa.Column('quantidade', sa.Float(), nullable=True),
    sa.Column('unidade_medida', sqlmodel.sql.sqltypes.AutoString(length=30), nullable=True),
    sa.Column('valor_unitario_estimado', sa.Float(), nullable=True),
    sa.Column('valor_total_estimado', sa.Float(), nullable=True),
    sa.Column('exclusivo_me_epp', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('id_pncp', 'numero_item', name='unq_item_contratacao')
    )
    op.create_index(op.f('ix_itens_contratacao_codigo_catmat_catser'), 'itens_contratacao', ['codigo_catmat_catser'], unique=False)
    op.create_index(op.f('ix_itens_contratacao_id_pncp'), 'itens_contratacao', ['id_pncp'], unique=False)
    op.create_table('legal_embeddings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('chunk_id', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=False),
    sa.Column('source', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
    sa.Column('titulo', sqlmodel.sql.sqltypes.AutoString(length=512), nullable=False),
    sa.Column('fundamentacao', sqlmodel.sql.sqltypes.AutoString(length=512), nullable=False),
    sa.Column('texto', sa.Text(), nullable=False),
    sa.Column('embedding', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('dims', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_legal_embeddings_chunk_id'), 'legal_embeddings', ['chunk_id'], unique=True)
    op.create_index(op.f('ix_legal_embeddings_source'), 'legal_embeddings', ['source'], unique=False)
    op.create_table('perfis_interesse',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('empresa_id', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
    sa.Column('nome_perfil', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
    sa.Column('ufs_permitidas', postgresql.ARRAY(sa.String(length=2)), nullable=False),
    sa.Column('valor_minimo_item', sa.Float(), nullable=False),
    sa.Column('valor_maximo_item', sa.Float(), nullable=True),
    sa.Column('apenas_me_epp', sa.Boolean(), nullable=False),
    sa.Column('ativo', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_perfis_interesse_empresa_id'), 'perfis_interesse', ['empresa_id'], unique=False)
    op.create_table('tender_ingest',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('id_pncp', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
    sa.Column('orgao_comprador', sqlmodel.sql.sqltypes.AutoString(length=512), nullable=True),
    sa.Column('cnpj_orgao', sqlmodel.sql.sqltypes.AutoString(length=14), nullable=True),
    sa.Column('uf', sqlmodel.sql.sqltypes.AutoString(length=2), nullable=True),
    sa.Column('municipio', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=True),
    sa.Column('modalidade', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=True),
    sa.Column('objeto_resumido', sa.Text(), nullable=True),
    sa.Column('valor_total_estimado', sa.Float(), nullable=True),
    sa.Column('situacao', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=True),
    sa.Column('data_publicacao', sa.DateTime(), nullable=True),
    sa.Column('data_abertura_propostas', sa.DateTime(), nullable=True),
    sa.Column('data_encerramento_propostas', sa.DateTime(), nullable=True),
    sa.Column('status', sqlmodel.sql.sqltypes.AutoString(length=32), nullable=False),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_tender_ingest_cnpj_orgao'), 'tender_ingest', ['cnpj_orgao'], unique=False)
    op.create_index(op.f('ix_tender_ingest_id_pncp'), 'tender_ingest', ['id_pncp'], unique=True)
    op.create_index(op.f('ix_tender_ingest_status'), 'tender_ingest', ['status'], unique=False)
    op.create_index(op.f('ix_tender_ingest_uf'), 'tender_ingest', ['uf'], unique=False)
    op.create_table('digest_agendamentos',
    sa.Column('perfil_id', sa.Uuid(), nullable=False),
    sa.Column('telefone', sqlmodel.sql.sqltypes.AutoString(length=15), nullable=False),
    sa.Column('horario', sqlmodel.sql.sqltypes.AutoString(length=5), nullable=False),
    sa.Column('top_n', sa.Integer(), nullable=False),
    sa.Column('instance', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=True),
    sa.Column('ativo', sa.Boolean(), nullable=False),
    sa.Column('ultimo_envio_dia', sa.Date(), nullable=True),
    sa.Column('ultima_tentativa', sa.DateTime(timezone=True), nullable=True),
    sa.Column('ultimo_status', sqlmodel.sql.sqltypes.AutoString(length=300), nullable=True),
    sa.ForeignKeyConstraint(['perfil_id'], ['perfis_interesse.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('perfil_id')
    )
    op.create_table('matches_itens',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('perfil_id', sa.Uuid(), nullable=False),
    sa.Column('id_pncp', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
    sa.Column('numero_item', sa.Integer(), nullable=False),
    sa.Column('score_catmat', sa.Float(), nullable=False),
    sa.Column('score_lexico', sa.Float(), nullable=False),
    sa.Column('score_semantico', sa.Float(), nullable=False),
    sa.Column('score_total', sa.Float(), nullable=False),
    sa.Column('alerta', sa.Boolean(), nullable=False),
    sa.Column('status', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['perfil_id'], ['perfis_interesse.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('perfil_id', 'id_pncp', 'numero_item', name='unq_match_perfil_item')
    )
    op.create_index(op.f('ix_matches_itens_id_pncp'), 'matches_itens', ['id_pncp'], unique=False)
    op.create_index(op.f('ix_matches_itens_perfil_id'), 'matches_itens', ['perfil_id'], unique=False)
    op.create_index(op.f('ix_matches_itens_status'), 'matches_itens', ['status'], unique=False)
    op.create_table('perfis_descricao',
    sa.Column('perfil_id', sa.Uuid(), nullable=False),
    sa.Column('descricao', sa.Text(), nullable=False),
    sa.ForeignKeyConstraint(['perfil_id'], ['perfis_interesse.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('perfil_id')
    )
    op.create_table('regras_catalogo',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('perfil_id', sa.Uuid(), nullable=False),
    sa.Column('codigo_item', sa.Integer(), nullable=False),
    sa.Column('peso', sa.Float(), nullable=False),
    sa.ForeignKeyConstraint(['perfil_id'], ['perfis_interesse.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_regras_catalogo_perfil_id'), 'regras_catalogo', ['perfil_id'], unique=False)
    op.create_table('regras_palavras_chave',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('perfil_id', sa.Uuid(), nullable=False),
    sa.Column('tipo', sqlmodel.sql.sqltypes.AutoString(length=15), nullable=False),
    sa.Column('termo', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
    sa.ForeignKeyConstraint(['perfil_id'], ['perfis_interesse.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_regras_palavras_chave_perfil_id'), 'regras_palavras_chave', ['perfil_id'], unique=False)
    op.create_index(op.f('ix_regras_palavras_chave_termo'), 'regras_palavras_chave', ['termo'], unique=False)
    op.create_table('usuarios',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('empresa_id', sa.Uuid(), nullable=False),
    sa.Column('email', sqlmodel.sql.sqltypes.AutoString(length=254), nullable=False),
    sa.Column('nome', sqlmodel.sql.sqltypes.AutoString(length=120), nullable=False),
    sa.Column('senha_hash', sqlmodel.sql.sqltypes.AutoString(length=300), nullable=False),
    sa.Column('is_admin', sa.Boolean(), nullable=False),
    sa.Column('ativo', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('ultimo_login', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['empresa_id'], ['empresas.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_usuarios_email'), 'usuarios', ['email'], unique=True)
    op.create_index(op.f('ix_usuarios_empresa_id'), 'usuarios', ['empresa_id'], unique=False)
    op.create_table('sessoes',
    sa.Column('token_hash', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
    sa.Column('usuario_id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('token_hash')
    )
    op.create_index(op.f('ix_sessoes_expires_at'), 'sessoes', ['expires_at'], unique=False)
    op.create_index(op.f('ix_sessoes_usuario_id'), 'sessoes', ['usuario_id'], unique=False)
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f('ix_sessoes_usuario_id'), table_name='sessoes')
    op.drop_index(op.f('ix_sessoes_expires_at'), table_name='sessoes')
    op.drop_table('sessoes')
    op.drop_index(op.f('ix_usuarios_empresa_id'), table_name='usuarios')
    op.drop_index(op.f('ix_usuarios_email'), table_name='usuarios')
    op.drop_table('usuarios')
    op.drop_index(op.f('ix_regras_palavras_chave_termo'), table_name='regras_palavras_chave')
    op.drop_index(op.f('ix_regras_palavras_chave_perfil_id'), table_name='regras_palavras_chave')
    op.drop_table('regras_palavras_chave')
    op.drop_index(op.f('ix_regras_catalogo_perfil_id'), table_name='regras_catalogo')
    op.drop_table('regras_catalogo')
    op.drop_table('perfis_descricao')
    op.drop_index(op.f('ix_matches_itens_status'), table_name='matches_itens')
    op.drop_index(op.f('ix_matches_itens_perfil_id'), table_name='matches_itens')
    op.drop_index(op.f('ix_matches_itens_id_pncp'), table_name='matches_itens')
    op.drop_table('matches_itens')
    op.drop_table('digest_agendamentos')
    op.drop_index(op.f('ix_tender_ingest_uf'), table_name='tender_ingest')
    op.drop_index(op.f('ix_tender_ingest_status'), table_name='tender_ingest')
    op.drop_index(op.f('ix_tender_ingest_id_pncp'), table_name='tender_ingest')
    op.drop_index(op.f('ix_tender_ingest_cnpj_orgao'), table_name='tender_ingest')
    op.drop_table('tender_ingest')
    op.drop_index(op.f('ix_perfis_interesse_empresa_id'), table_name='perfis_interesse')
    op.drop_table('perfis_interesse')
    op.drop_index(op.f('ix_legal_embeddings_source'), table_name='legal_embeddings')
    op.drop_index(op.f('ix_legal_embeddings_chunk_id'), table_name='legal_embeddings')
    op.drop_table('legal_embeddings')
    op.drop_index(op.f('ix_itens_contratacao_id_pncp'), table_name='itens_contratacao')
    op.drop_index(op.f('ix_itens_contratacao_codigo_catmat_catser'), table_name='itens_contratacao')
    op.drop_table('itens_contratacao')
    op.drop_table('empresas')
    op.drop_table('embeddings_cache')
    op.drop_index(op.f('ix_anexos_contratacao_id_pncp'), table_name='anexos_contratacao')
    op.drop_table('anexos_contratacao')
    # ### end Alembic commands ###
