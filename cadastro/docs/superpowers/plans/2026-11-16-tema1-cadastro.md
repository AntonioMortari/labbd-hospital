# Tema 1 — Cadastro, Agendamentos e Faturamento: Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Núcleo relacional do Sistema de Gestão Hospitalar (PostgreSQL + API FastAPI em 3 réplicas atrás de Nginx), com integridade, anti-conflito de horário, auditoria e faturamento transacional garantidos pelo banco.

**Architecture:** As regras vivem em SQL (`db/*.sql`, executados pelo entrypoint do Postgres na 1ª subida). A API é fina: SQL escrito à mão com asyncpg, traduzindo SQLSTATE em HTTP. A estrutura espelha o Tema 3 (`LabBD/emergencia`).

**Tech Stack:** Docker Compose, postgres:16-alpine, Python 3.12, FastAPI 0.115.0, uvicorn[standard] 0.30.6, asyncpg 0.29.0, nginx:alpine; testes com pytest 8.3.3, httpx 0.27.2 e psycopg[binary] 3.2.3 rodando num container.

**Spec:** `docs/superpowers/specs/2026-11-16-tema1-cadastro-design.md`

## Global Constraints

- Porta pública do Nginx: **8081**; Postgres exposto em **5433** (host) → 5432.
- Banco `hospital`, usuário `postgres`, senha `postgres` (ambiente de demo).
- `TZ=America/Sao_Paulo` e `PGTZ=America/Sao_Paulo` no container do Postgres.
- API com `deploy.replicas: 3`, uvicorn na porta 8000 dentro da rede.
- Sem ORM. Toda regra de negócio do enunciado é garantida pelo banco (constraint, trigger ou procedure).
- Toda escrita na API roda numa transação que começa com `SELECT set_config('app.usuario', $1, true)` (valor do cabeçalho `X-Usuario`, padrão `api`).
- Erros: 23P01→409, 23505→409, 23503→422, 23514→422, classe 22 (dados inválidos)→422, P0001→422; corpo `{"detail": "<mensagem>"}`.
- Mudou um `.sql`? Recriar: `docker compose down -v && docker compose up -d --build`.
- Commits: só se o repositório git estiver ativo (perguntar antes de `git init`).

## Review Focus

1. **Período invertido** (`fim` ≤ `inicio`) num `POST /agendamentos` → 422 com mensagem, não 500. (Task 5)
2. **Paciente com plano mas sem carteirinha/validade** → 422 (CHECK). (Tasks 1 e 5)
3. **Realizar atendimento cancelado ou já realizado** → 422 e nenhuma fatura nova. (Task 3)
4. **Data sem fuso** (`"2026-11-27T09:00:00"`) é interpretada como horário de São Paulo, e consultas encostadas (09:00–09:30 e 09:30–10:00) não conflitam. (Tasks 1 e 5)
5. **Cancelar e reagendar o mesmo horário** funciona (o cancelado libera o horário). (Tasks 1 e 5)

---

## Estrutura de arquivos

```
cadastro/
├── docker-compose.yml          postgres, api(×3), nginx, tests(profile test), loadtest(profile test)
├── nginx.conf
├── README.md                   como subir, testar e roteiro da demo
├── db/01_schema.sql            extensão, tabelas, constraints
├── db/02_auditoria.sql         tabela auditoria + fn_auditoria + triggers
├── db/03_faturamento.sql       procedure realizar_atendimento
├── db/04_seed.sql              dados de exemplo
├── api/Dockerfile, requirements.txt
├── api/main.py                 app, rotas
├── api/db.py                   pool asyncpg, helper de transação com usuário, mapeamento de erros
├── api/static/index.html       página de demo
├── tests/Dockerfile, requirements.txt
├── tests/conftest.py           fixtures: conexão psycopg (rollback), cliente httpx
├── tests/test_schema.py, test_auditoria.py, test_faturamento.py, test_seed.py, test_api.py
└── loadtest/Dockerfile, test.py
```

---

### Task 1: Infraestrutura + schema com integridade e anti-conflito

**Files:**
- Create: `docker-compose.yml` (só `postgres` e `tests` nesta task), `db/01_schema.sql`, `tests/Dockerfile`, `tests/requirements.txt`, `tests/conftest.py`, `tests/test_schema.py`

**Interfaces:**
- Produces (tabelas, nomes exatos):
  - `especialidade(id serial PK, nome text NOT NULL UNIQUE, valor_consulta numeric(10,2) NOT NULL CHECK (>0))`
  - `convenio(id serial PK, nome text NOT NULL UNIQUE, cnpj char(14) NOT NULL UNIQUE CHECK (cnpj ~ '^[0-9]{14}$'))`
  - `plano(id serial PK, convenio_id int NOT NULL FK, nome text NOT NULL, cobertura_pct numeric(5,2) NOT NULL CHECK (0..100), UNIQUE(convenio_id, nome))`
  - `paciente(id serial PK, nome text NOT NULL, cpf char(11) NOT NULL UNIQUE CHECK (~ '^[0-9]{11}$'), data_nascimento date NOT NULL CHECK (<= current_date), telefone text, plano_id int FK, carteirinha text, validade_carteirinha date)` + `CHECK ((plano_id IS NULL) = (carteirinha IS NULL) AND (plano_id IS NULL) = (validade_carteirinha IS NULL))` chamado `plano_completo`
  - `medico(id serial PK, nome text NOT NULL, crm text NOT NULL UNIQUE, especialidade_id int NOT NULL FK)`
  - `agendamento(id serial PK, paciente_id int NOT NULL FK, medico_id int NOT NULL FK, tipo text NOT NULL CHECK IN ('consulta','cirurgia'), periodo tstzrange NOT NULL CHECK (NOT isempty(periodo)), status text NOT NULL DEFAULT 'agendado' CHECK IN ('agendado','realizado','cancelado'), valor_cirurgia numeric(10,2) CHECK (>0), criado_em timestamptz NOT NULL DEFAULT now())` + `CHECK ((tipo = 'cirurgia') = (valor_cirurgia IS NOT NULL))` + exclusion constraints `sem_conflito_medico` e `sem_conflito_paciente` exatamente como na spec §6
  - `fatura(id serial PK, agendamento_id int NOT NULL UNIQUE FK, valor_total, valor_convenio, valor_paciente numeric(10,2) NOT NULL CHECK (>=0), emitida_em timestamptz NOT NULL DEFAULT now())` + `CHECK (valor_convenio + valor_paciente = valor_total)`
- Produces (fixtures em `tests/conftest.py`):
  - `db` → `psycopg.Connection` (autocommit off) que faz `rollback()` no teardown
  - `db_commit` → `psycopg.Connection` com autocommit on, para testes de concorrência (o teste limpa o que criou)
  - `make(db) -> dict` helpers: `nova_especialidade(db, **kw) -> int`, `novo_convenio_plano(db, cobertura=70) -> int` (plano_id), `novo_paciente(db, plano_id=None, validade=None) -> int` (gera CPF único), `novo_medico(db, especialidade_id) -> int`, `novo_agendamento(db, paciente_id, medico_id, inicio, fim, tipo='consulta', valor_cirurgia=None) -> int`
  - `DATABASE_URL=postgresql://postgres:postgres@postgres:5432/hospital`, `BASE_URL=http://nginx`

- [ ] **Step 1: Infra.** `docker-compose.yml` com `postgres` (image `postgres:16-alpine`, env `POSTGRES_DB=hospital`, `POSTGRES_PASSWORD=postgres`, `TZ`, `PGTZ`, volumes `./db:/docker-entrypoint-initdb.d:ro` e `pg-data:/var/lib/postgresql/data`, porta `5433:5432`, healthcheck `pg_isready -U postgres -h localhost -d hospital` interval 3s retries 20) e `tests` (build `./tests`, profile `test`, volume `./tests:/tests`, env `DATABASE_URL`/`BASE_URL`, depends_on postgres healthy). `tests/Dockerfile`: python:3.12-slim, instala requirements, `WORKDIR /tests`, `CMD ["pytest","-q"]`.

- [ ] **Step 2: Testes que falham** em `tests/test_schema.py` (cada um espera `psycopg.errors.<Erro>` com `pytest.raises`):
  - `test_cpf_duplicado` → `UniqueViolation`
  - `test_cpf_invalido` (`'123'`) → `CheckViolation`
  - `test_plano_sem_carteirinha` (plano_id preenchido, carteirinha nula) → `CheckViolation`
  - `test_medico_com_especialidade_inexistente` (id 999999) → `ForeignKeyViolation`
  - `test_apagar_medico_com_agendamento` → `ForeignKeyViolation`
  - `test_cirurgia_sem_valor` → `CheckViolation`
  - `test_conflito_mesmo_medico` (09:00–09:30 e 09:15–09:45, pacientes diferentes) → `ExclusionViolation`
  - `test_conflito_mesmo_paciente` (médicos diferentes, horários sobrepostos) → `ExclusionViolation`
  - `test_horarios_encostados_ok` (09:00–09:30 e 09:30–10:00, mesmo médico) → os dois inserem
  - `test_cancelado_libera_horario` (cancela o 1º, insere sobreposto) → insere
  - `test_periodo_invertido` (`tstzrange('…10:00','…09:00')`) → `DataException` (subclasse de `psycopg.errors.DataError`)
  - `test_hora_sem_fuso_e_sao_paulo`: insere `'2026-11-27 09:00'` e confere `lower(periodo) = '2026-11-27 12:00+00'`
  - `test_corrida_mesmo_horario` (usa `db_commit`): 20 threads, cada uma com conexão própria, inserem o mesmo médico/horário com pacientes distintos → exatamente 1 sucesso e 19 `ExclusionViolation`; limpa no fim

- [ ] **Step 3: Rodar e ver falhar.** `docker compose up -d postgres && docker compose --profile test run --rm tests pytest -q test_schema.py` → falham (tabelas inexistentes).

- [ ] **Step 4: Implementar `db/01_schema.sql`** com `CREATE EXTENSION IF NOT EXISTS btree_gist;` e as tabelas da seção Interfaces.

- [ ] **Step 5: Recriar e passar.** `docker compose down -v && docker compose up -d postgres && docker compose --profile test run --rm tests pytest -q test_schema.py` → todos PASS.

- [ ] **Step 6: Commit** (se git ativo): `feat: schema com integridade e anti-conflito de horário`.

---

### Task 2: Auditoria por trigger

**Files:**
- Create: `db/02_auditoria.sql`, `tests/test_auditoria.py`

**Interfaces:**
- Consumes: tabelas e helpers da Task 1.
- Produces: `auditoria(id bigserial PK, tabela text NOT NULL, operacao text NOT NULL CHECK IN ('INSERT','UPDATE','DELETE'), registro_id int NOT NULL, dados_antigos jsonb, dados_novos jsonb, usuario text NOT NULL, em timestamptz NOT NULL DEFAULT clock_timestamp())`; função `fn_auditoria() RETURNS trigger`; triggers `trg_auditoria_paciente`, `trg_auditoria_medico`, `trg_auditoria_plano` (`AFTER INSERT OR UPDATE OR DELETE FOR EACH ROW`).

- [ ] **Step 1: Testes que falham** em `tests/test_auditoria.py`:
  - `test_update_paciente_registra_antes_e_depois`: `set_config('app.usuario','recepcao1',true)`, muda telefone; última linha de auditoria tem `tabela='paciente'`, `operacao='UPDATE'`, `dados_antigos->>'telefone'` = antigo, `dados_novos->>'telefone'` = novo, `usuario='recepcao1'`
  - `test_insert_e_delete_registrados`: inserir e apagar um paciente geram `INSERT` (antigos nulo) e `DELETE` (novos nulo)
  - `test_update_sem_mudanca_nao_registra`: `UPDATE paciente SET nome = nome` não cria linha
  - `test_sem_usuario_usa_current_user`: sem `set_config`, `usuario = 'postgres'`
  - `test_medico_e_plano_auditados`: update em `medico` e em `plano` gera linha com a tabela certa

- [ ] **Step 2: Rodar e ver falhar.** `docker compose --profile test run --rm tests pytest -q test_auditoria.py` → FAIL.

- [ ] **Step 3: Implementar `db/02_auditoria.sql`.** Usuário: `coalesce(nullif(current_setting('app.usuario', true), ''), current_user)`. Em UPDATE, `IF OLD IS NOT DISTINCT FROM NEW THEN RETURN NULL`. `registro_id` = `coalesce(NEW.id, OLD.id)`.

- [ ] **Step 4: Recriar e passar** (`down -v`, `up -d postgres`, rodar `test_schema.py test_auditoria.py`) → PASS.

- [ ] **Step 5: Commit** (se git ativo): `feat: auditoria de cadastros sensíveis por trigger`.

---

### Task 3: Procedure de faturamento transacional

**Files:**
- Create: `db/03_faturamento.sql`, `tests/test_faturamento.py`

**Interfaces:**
- Consumes: tabelas da Task 1.
- Produces: `PROCEDURE realizar_atendimento(p_agendamento_id int, INOUT p_fatura_id int DEFAULT NULL)`. Chamada: `CALL realizar_atendimento(%s, NULL)` retorna uma linha com `p_fatura_id`. Erros com `ERRCODE = 'P0001'` e mensagens: `Agendamento % não encontrado`, `Agendamento % não pode ser realizado (status: %)`, `Plano do paciente vencido em %`.

- [ ] **Step 1: Testes que falham** em `tests/test_faturamento.py` (valor_consulta 200.00 nos helpers):
  - `test_consulta_com_plano_70`: fatura `valor_total=200.00`, `valor_convenio=140.00`, `valor_paciente=60.00`; status vira `realizado`
  - `test_particular_convenio_paga_zero`: `valor_convenio=0`, `valor_paciente=200.00`
  - `test_cirurgia_usa_valor_cirurgia`: `valor_cirurgia=5000.00`, plano 100% → convênio 5000.00, paciente 0
  - `test_arredondamento`: valor 99.99, plano 33.33% → convênio `33.33`, paciente `66.66`, soma = total
  - `test_plano_vencido_desfaz_tudo`: validade = data do atendimento − 1 dia → `RaiseException` com "vencido"; depois do `rollback`, status ainda `agendado` e nenhuma fatura (verificar numa conexão nova)
  - `test_validade_no_dia_ok`: validade = data do atendimento → fatura criada
  - `test_cancelado_nao_fatura` e `test_ja_realizado_nao_fatura` → `RaiseException`
  - `test_inexistente` (id 999999) → `RaiseException` "não encontrado"
  - `test_duas_chamadas_simultaneas` (`db_commit`, 2 threads) → exatamente 1 fatura; a outra recebe `RaiseException`

- [ ] **Step 2: Rodar e ver falhar** → FAIL.

- [ ] **Step 3: Implementar `db/03_faturamento.sql`** seguindo a spec §8 (`SELECT … FOR UPDATE`; data do atendimento = `lower(periodo)::date`; `valor_convenio = round(valor_total * cobertura_pct / 100, 2)`; `valor_paciente = valor_total - valor_convenio`).

- [ ] **Step 4: Recriar e passar** os três arquivos de teste → PASS.

- [ ] **Step 5: Commit** (se git ativo): `feat: faturamento transacional ligado ao plano`.

---

### Task 4: Dados de exemplo

**Files:**
- Create: `db/04_seed.sql`, `tests/test_seed.py`

**Interfaces:**
- Produces: dados com nomes fixos que a demo e o loadtest usam:
  - especialidades `Clínica Geral` (150.00), `Cardiologia` (300.00), `Ortopedia` (250.00), `Pediatria` (180.00)
  - convênios `Saúde Total` (planos `Básico` 70%, `Premium` 100%) e `VidaMais` (`Essencial` 50%, `Plus` 80%)
  - 6 médicos (CRM `CRM-SP 100001`…`100006`), o 1º é de Clínica Geral
  - 8 pacientes; o paciente com CPF `00000000002` (`Carlos Vencido`) tem validade `current_date - 30`; dois particulares; os demais com validade `current_date + 365`
  - 6 agendamentos entre `current_date + 1` e `current_date + 11`, todos `agendado`, horários sem conflito

- [ ] **Step 1: Testes que falham** em `tests/test_seed.py`: contagens (4, 2, 4 planos, 6, 8, ≥6), existência de `Carlos Vencido` com validade < hoje, ao menos 2 pacientes com `plano_id IS NULL`.
- [ ] **Step 2: Rodar e ver falhar** → FAIL.
- [ ] **Step 3: Implementar `db/04_seed.sql`** (inserções com subselects por nome/CRM, sem ids fixos).
- [ ] **Step 4: Recriar e rodar toda a suíte** → PASS (os testes das Tasks 1–3 criam os próprios dados e não dependem do seed).
- [ ] **Step 5: Commit** (se git ativo): `feat: dados de exemplo para a demo`.

---

### Task 5: API (3 réplicas) + Nginx

**Files:**
- Create: `api/Dockerfile`, `api/requirements.txt`, `api/db.py`, `api/main.py`, `nginx.conf`, `tests/test_api.py`
- Modify: `docker-compose.yml` (adicionar `api` e `nginx`; `tests` passa a depender de `nginx`)

**Interfaces:**
- Consumes: tabelas, procedure e seed das Tasks 1–4.
- Produces (`api/db.py`):
  - `async def init_pool(dsn: str) -> None` / `async def close_pool() -> None`
  - `@asynccontextmanager async def tx(usuario: str) -> AsyncIterator[asyncpg.Connection]` — adquire conexão, abre transação, faz o `set_config`
  - `def erro_http(e: asyncpg.PostgresError) -> HTTPException` — mapa da seção Global Constraints; mensagem = `e.message` (para 23P01: `"Horário indisponível para este médico ou paciente"`)
- Produces (HTTP, base `http://localhost:8081`): rotas da spec §9. `POST` de criação → **201** com a linha criada. `PUT /pacientes/{id}` inexistente → 404. `POST /agendamentos/{id}/realizar` → 201 com a fatura. Corpo de agendamento: `{paciente_id:int, medico_id:int, tipo:"consulta"|"cirurgia", inicio:str ISO, fim:str ISO, valor_cirurgia?:float}`; resposta inclui `inicio`/`fim` (de `lower`/`upper`) em ISO.
- `api/Dockerfile` igual ao do Tema 3 (uvicorn `--workers 2`, porta 8000). `nginx.conf` igual ao do Tema 3. Compose: `api` com `DATABASE_URL`, `deploy.replicas: 3`, depends_on postgres healthy; `nginx` com `8081:80`.

- [ ] **Step 1: Testes que falham** em `tests/test_api.py` (httpx contra `BASE_URL`; cada teste cria seus próprios dados via API com CPF aleatório):
  - `test_health` → 200
  - `test_cria_e_lista_paciente` → 201, depois aparece em `GET /pacientes/{id}`
  - `test_cpf_duplicado_409`
  - `test_paciente_plano_incompleto_422`
  - `test_agendamento_medico_inexistente_422`
  - `test_conflito_409` (dois agendamentos sobrepostos, mesmo médico) e mensagem `"Horário indisponível…"`
  - `test_periodo_invertido_422`
  - `test_cancelar_e_reagendar` → cancelar 200, reagendar o mesmo horário 201
  - `test_put_registra_auditoria_com_usuario`: `PUT` com header `X-Usuario: recepcao1` → `GET /auditoria?limit=5` contém linha `paciente`/`UPDATE`/`recepcao1`
  - `test_put_inexistente_404`
  - `test_realizar_gera_fatura` → 201 com `valor_convenio` + `valor_paciente` = `valor_total`; aparece em `GET /faturas`
  - `test_realizar_plano_vencido_422`: agendar `Carlos Vencido` (`GET /pacientes` filtrando o nome) e realizar → 422 com "vencido"; `GET /agendamentos` mostra status `agendado`
  - `test_listas` → `/medicos`, `/especialidades`, `/convenios` (com `planos` aninhados) retornam 200 e não vazias
- [ ] **Step 2: Rodar e ver falhar.** `docker compose up -d --build && docker compose --profile test run --rm tests pytest -q test_api.py` → FAIL.
- [ ] **Step 3: Implementar `api/db.py` e `api/main.py`.** Pool asyncpg com `min_size=2, max_size=20` por processo; um `@app.exception_handler(asyncpg.PostgresError)` usando `erro_http`. Agendamento: `tstzrange($3::timestamptz, $4::timestamptz, '[)')`. Convênios com planos: `json_agg`.
- [ ] **Step 4: Rodar toda a suíte** → PASS. Conferir `docker compose ps` com 3 réplicas `api`.
- [ ] **Step 5: Commit** (se git ativo): `feat: API FastAPI com 3 réplicas atrás do Nginx`.

---

### Task 6: Página de demo

**Files:**
- Create: `api/static/index.html`
- Modify: `api/main.py` (rota `GET /` → `FileResponse("static/index.html")`), `tests/test_api.py`

**Interfaces:**
- Consumes: `GET /agendamentos`, `GET /faturas`, `GET /auditoria?limit=10`.

- [ ] **Step 1: Teste que falha:** `test_pagina_demo` → `GET /` 200, `text/html`, contém `id="agenda"`, `id="faturas"`, `id="auditoria"`.
- [ ] **Step 2: Rodar e ver falhar.**
- [ ] **Step 3: Implementar** a página: HTML + JS puro, três tabelas atualizadas por `fetch` a cada 2 s; status com cor (agendado/realizado/cancelado).
- [ ] **Step 4: Rodar (rebuild da api) e passar;** abrir `http://localhost:8081` e ver os três blocos com o seed.
- [ ] **Step 5: Commit** (se git ativo): `feat: página de demo`.

---

### Task 7: Teste de corrida (500 agendamentos simultâneos)

**Files:**
- Create: `loadtest/Dockerfile` (igual ao do Tema 3), `loadtest/test.py`
- Modify: `docker-compose.yml` (serviço `loadtest`, profile `test`, `BASE_URL=http://nginx`)

**Interfaces:**
- Consumes: `POST /pacientes`, `POST /agendamentos`, `POST /agendamentos/{id}/cancelar`, `GET /medicos`.

- [ ] **Step 1: Implementar `loadtest/test.py`** conforme spec §12 e §15: prefixo aleatório de CPF; médico = primeiro de `GET /medicos`; horário amanhã 07:00–07:30 (São Paulo); `asyncio.gather` dos 500 POSTs com `httpx.Limits(max_connections=300)`; imprimir exatamente `[RACE] sucessos=<n> (esperado=1) conflitos=<m>`; cancelar o vencedor; sair com código 1 se `sucessos != 1`.
- [ ] **Step 2: Rodar duas vezes seguidas.** `docker compose --profile test run --rm --build loadtest` → as duas imprimem `sucessos=1 (esperado=1) conflitos=499` e saem com 0.
- [ ] **Step 3: Commit** (se git ativo): `feat: teste de corrida de agendamentos`.

---

### Task 8: README com roteiro da demo

**Files:**
- Create: `README.md`

- [ ] **Step 1: Escrever** como subir (`docker compose up -d --build`), recriar (`down -v`), rodar testes e loadtest, conectar no DBeaver (`localhost:5433`, `hospital`, `postgres/postgres`), e os 7 passos da spec §13 com o comando `curl` de cada um e a saída esperada.
- [ ] **Step 2: Executar o roteiro inteiro do zero** (`down -v`, `up -d --build`, cada comando do README) e corrigir o README onde a saída real diferir.
- [ ] **Step 3: Commit** (se git ativo): `docs: README e roteiro da demo`.
