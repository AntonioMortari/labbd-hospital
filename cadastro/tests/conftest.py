import os
import random
import uuid

import psycopg
import pytest

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5433/hospital")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8081")


def conectar(autocommit: bool = False) -> psycopg.Connection:
    return psycopg.connect(DATABASE_URL, autocommit=autocommit)


@pytest.fixture
def db():
    """Conexão cujo trabalho é desfeito (rollback) no fim do teste."""
    conn = conectar()
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()


@pytest.fixture
def db_commit():
    """Conexão com autocommit, para testes de concorrência. O teste limpa o que criar."""
    conn = conectar(autocommit=True)
    try:
        yield conn
    finally:
        conn.close()


def cpf_unico() -> str:
    return f"{random.randrange(10**11):011d}"


def _id(conn, sql, params):
    return conn.execute(sql, params).fetchone()[0]


def nova_especialidade(conn, nome=None, valor_consulta=200.00) -> int:
    nome = nome or f"Esp {uuid.uuid4().hex[:8]}"
    return _id(conn, "INSERT INTO especialidade (nome, valor_consulta) VALUES (%s, %s) RETURNING id",
               (nome, valor_consulta))


def novo_convenio_plano(conn, cobertura=70) -> int:
    """Cria um convênio com um plano e devolve o id do plano."""
    cnpj = f"{random.randrange(10**14):014d}"
    conv = _id(conn, "INSERT INTO convenio (nome, cnpj) VALUES (%s, %s) RETURNING id",
               (f"Conv {uuid.uuid4().hex[:8]}", cnpj))
    return _id(conn, "INSERT INTO plano (convenio_id, nome, cobertura_pct) VALUES (%s, %s, %s) RETURNING id",
               (conv, "Plano", cobertura))


def novo_paciente(conn, plano_id=None, validade=None, cpf=None) -> int:
    carteirinha = f"CART-{uuid.uuid4().hex[:6]}" if plano_id else None
    if plano_id and validade is None:
        validade = "2099-12-31"
    return _id(conn,
               """INSERT INTO paciente (nome, cpf, data_nascimento, plano_id, carteirinha, validade_carteirinha)
                  VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
               (f"Paciente {uuid.uuid4().hex[:6]}", cpf or cpf_unico(), "1990-05-10",
                plano_id, carteirinha, validade))


def novo_medico(conn, especialidade_id) -> int:
    return _id(conn, "INSERT INTO medico (nome, crm, especialidade_id) VALUES (%s, %s, %s) RETURNING id",
               (f"Dr {uuid.uuid4().hex[:6]}", f"CRM-T {uuid.uuid4().hex[:10]}", especialidade_id))


def novo_agendamento(conn, paciente_id, medico_id, inicio, fim, tipo="consulta", valor_cirurgia=None) -> int:
    return _id(conn,
               """INSERT INTO agendamento (paciente_id, medico_id, tipo, periodo, valor_cirurgia)
                  VALUES (%s, %s, %s, tstzrange(%s::timestamptz, %s::timestamptz, '[)'), %s) RETURNING id""",
               (paciente_id, medico_id, tipo, inicio, fim, valor_cirurgia))
