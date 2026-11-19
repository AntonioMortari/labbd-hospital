# Tema 1 — Cadastro de Pacientes, Equipe Médica e Agendamentos

Sistema de Gestão Hospitalar · Laboratório de Banco de Dados · Seminário final (P2) · 27/11/2026
Banco relacional (PostgreSQL) · Yuri e Antônio

O núcleo relacional do sistema. As regras que o enunciado pede são garantidas **pelo próprio banco**:

| Exigência | Onde está | Arquivo |
|---|---|---|
| Integridade referencial | chaves estrangeiras, `UNIQUE`, `CHECK` | `db/01_schema.sql` |
| Sem agendamento duplicado no mesmo horário | *exclusion constraint* (`EXCLUDE USING gist`) + trigger de fila por médico | `db/01_schema.sql` |
| Auditoria de cadastros sensíveis | trigger + função PL/pgSQL `fn_auditoria`; a trilha não pode ser alterada nem apagada | `db/02_auditoria.sql` |
| Ciclo de vida do agendamento | trigger `trg_transicao_status`: só `agendado → realizado/cancelado` | `db/01_schema.sql` |
| Faturamento ligado ao plano, numa transação | stored procedure `realizar_atendimento` | `db/03_faturamento.sql` |

## Arquitetura

```
cliente ──► nginx (localhost:8081) ──► api ×3 (FastAPI + asyncpg) ──► postgres (localhost:5433)
```

Mesma estrutura do Tema 3 (`LabBD/emergencia`): Nginx na frente, 3 cópias idênticas da API e o estado no banco.
A API só executa SQL escrito à mão (sem ORM).

## Subir

```bash
docker compose up -d --build
```

- Página de demo: http://localhost:8081 (agenda, faturas e auditoria, atualizando a cada 2 s)
- Documentação da API: http://localhost:8081/docs
- DBeaver/pgAdmin: host `localhost`, porta `5433`, banco `hospital`, usuário `postgres`, senha `postgres`

Os scripts de `db/` só rodam na **primeira** subida do volume. Para recriar o banco do zero
(depois de mudar um `.sql`, ou **antes de apresentar**, para apagar os dados dos testes):

```bash
docker compose down -v && docker compose up -d --build
```

## Testes

```bash
docker compose --profile test run --rm tests                  # 66 testes (banco + API)
docker compose --profile test run --rm --build loadtest       # corrida: 500 agendamentos simultâneos
```

Os testes gravam dados no banco. Antes da apresentação, recrie o banco com `down -v`.

## Dados de exemplo (IDs fixos depois de recriar o banco)

As datas são relativas ao dia em que o banco foi recriado ("amanhã" = dia seguinte à recriação).

| Agendamento | Paciente | Plano | Médico | Quando |
|---|---|---|---|---|
| 1 | Ana Souza (id 1) | Saúde Total Básico, 70%, válido | Dra. Marina Costa (id 1), Clínica Geral, R$ 150 | amanhã 08:00 |
| 2 | Carlos Vencido (id 2) | Saúde Total Básico, **vencido há 30 dias** | Dr. Paulo Mendes (id 2), Cardiologia | amanhã 09:00 |
| 3 | Beatriz Lima (id 3) | Saúde Total Premium, 100% | Dr. Paulo Mendes | em 2 dias, 10:00 |
| 4 | Diego Martins (id 4) | VidaMais Essencial, 50% | Dra. Renata Dias, **cirurgia** R$ 8.000 | em 4 dias, 08:00 |
| 5 | Fábio Nunes (id 6) | particular | Dr. Tiago Ramos | em 7 dias, 14:00 |
| 6 | Gabriela Torres (id 7) | particular | Dr. Sérgio Pinto, Pediatria | em 11 dias, 15:00 |

## Roteiro da demonstração

Pré-requisito: banco recriado (`docker compose down -v && docker compose up -d --build`) e a página
http://localhost:8081 aberta ao lado. As variáveis abaixo deixam os comandos mais curtos:

```bash
# DIA = o dia da consulta da Ana no banco ("amanhã" em relação ao dia em que o banco foi recriado)
DIA=$(docker compose exec -T postgres psql -U postgres -d hospital -Atc "SELECT lower(periodo)::date FROM agendamento WHERE id = 1")
J='Content-Type: application/json'; W='\nHTTP %{http_code}\n'
```

### 1. Os componentes

```bash
docker compose ps
```

Esperado: `postgres`, `api-1`, `api-2`, `api-3` e `nginx`, todos `running`.

### 2. Integridade: o banco recusa dados inválidos

CPF repetido (a Ana já tem esse CPF):

```bash
curl -s -X POST localhost:8081/pacientes -H "$J" -d '{"nome":"Ana Cópia","cpf":"00000000001","data_nascimento":"1990-01-01"}' -w "$W"
```

Esperado: `HTTP 409` com `duplicate key value violates unique constraint "paciente_cpf_key"`.

Agendamento com médico que não existe:

```bash
curl -s -X POST localhost:8081/agendamentos -H "$J" -d "{\"paciente_id\":6,\"medico_id\":999,\"tipo\":\"consulta\",\"inicio\":\"${DIA}T16:00\",\"fim\":\"${DIA}T16:30\"}" -w "$W"
```

Esperado: `HTTP 422` com `violates foreign key constraint "agendamento_medico_id_fkey"`.

### 3. Conflito de horário

A Dra. Marina já atende a Ana no dia `$DIA` das 08:00 às 08:30. Tentando encaixar o Fábio às 08:15:

```bash
curl -s -X POST localhost:8081/agendamentos -H "$J" -d "{\"paciente_id\":6,\"medico_id\":1,\"tipo\":\"consulta\",\"inicio\":\"${DIA}T08:15\",\"fim\":\"${DIA}T08:45\"}" -w "$W"
```

Esperado: `HTTP 409` com `Horário indisponível para este médico ou paciente`.

### 4. Concorrência: 500 recepcionistas ao mesmo tempo

```bash
docker compose --profile test run --rm --build loadtest
```

Esperado: `[RACE] sucessos=1 (esperado=1) conflitos=499`, em poucos segundos. Os pedidos passam pelas
3 réplicas da API. Duas peças do banco trabalham juntas:

- a **exclusion constraint** `sem_conflito_medico` é a garantia: o Postgres nunca grava dois horários
  sobrepostos para o mesmo médico;
- o trigger **`trg_fila_por_medico`** trava a linha do médico (`SELECT … FOR NO KEY UPDATE`) antes da
  inserção, e as 500 tentativas entram em fila. Sem ele, as transações se esperavam umas às outras dentro da
  constraint e o Postgres precisava desfazer parte delas por *deadlock* (cerca de 1 s para detectar cada um).
  Na primeira versão, isso fazia a corrida levar mais de 60 s e o Nginx devolver 502.

### 5. Auditoria por trigger

```bash
docker compose exec postgres psql -U postgres -d hospital -c "BEGIN; SELECT set_config('app.usuario', 'recepcao1', true); UPDATE paciente SET telefone = '(19) 98888-0000' WHERE id = 1; COMMIT;"
docker compose exec postgres psql -U postgres -d hospital -c "SELECT usuario, operacao, dados_antigos->>'telefone' AS antes, dados_novos->>'telefone' AS depois, to_char(em, 'DD/MM HH24:MI:SS') AS quando FROM auditoria WHERE tabela = 'paciente' AND registro_id = 1 ORDER BY id DESC LIMIT 1;"
```

Esperado: `recepcao1 | UPDATE | (19) 99111-0001 | (19) 98888-0000 | <data e hora>`. A alteração também aparece
na página. Pela API, o usuário vai no cabeçalho `X-Usuario` (ex.: `PUT /pacientes/1`).

### 6. Faturamento numa transação

Atendimento da Ana (consulta de R$ 150, plano com 70% de cobertura):

```bash
curl -s -X POST localhost:8081/agendamentos/1/realizar -w "$W"
```

Esperado: `HTTP 201` com `"valor_total":150.0,"valor_convenio":105.0,"valor_paciente":45.0`. O agendamento
passa a `realizado` na página.

### 7. Rollback: plano vencido não fatura nada

```bash
curl -s -X POST localhost:8081/agendamentos/2/realizar -w "$W"
docker compose exec postgres psql -U postgres -d hospital -c "SELECT id, status FROM agendamento WHERE id = 2;" -c "SELECT count(*) AS faturas_do_carlos FROM fatura WHERE agendamento_id = 2;"
```

Esperado: `HTTP 422` com `Plano do paciente vencido em <data>`; no banco, o agendamento 2 continua `agendado`
e `faturas_do_carlos = 0`. A procedure chegou a começar, mas o erro desfez tudo.

## Estrutura

```
cadastro/
├── docker-compose.yml   postgres, api (3 réplicas), nginx, tests e loadtest (profile "test")
├── nginx.conf
├── db/                  01_schema · 02_auditoria · 03_faturamento · 04_seed
├── api/                 main.py (rotas), db.py (pool, transação, erros), static/index.html
├── tests/               pytest contra o banco e a API reais
├── loadtest/            corrida de 500 agendamentos
└── docs/superpowers/    design e plano de implementação
```
