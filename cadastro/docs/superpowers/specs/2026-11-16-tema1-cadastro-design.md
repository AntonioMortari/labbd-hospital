# Tema 1 — Cadastro de Pacientes, Equipe Médica e Agendamentos (design)

Data: 16/11/2026 · Seminário final (P2) de Laboratório de Banco de Dados · apresentação em 27/11/2026
Responsáveis: Yuri e Antônio

## 1. Intenção

Construir o núcleo relacional do Sistema de Gestão Hospitalar (Sistema 1) para a apresentação de 27/11.
O enunciado (p2) pede para enfatizar:

- integridade referencial estrita;
- controle de concorrência que impeça agendamentos duplicados no mesmo horário;
- triggers e stored procedures para auditoria de alterações em cadastros sensíveis;
- transações seguras que amarram o faturamento da consulta ao plano de saúde.

Avaliação: apresentação 40%, **uso do banco 40%**, relatório 20%. Por isso o trabalho pesado fica no SQL
(constraints, triggers, procedures, transações) e a aplicação é fina.

A estrutura copia a do Tema 3 (Stéfano, `LabBD/emergencia`) para facilitar a integração do sistema único que
é demonstrado na primeira parte da apresentação.

## 2. Objetivos, não-objetivos e anti-objetivos

**Objetivos**
- Banco PostgreSQL com todas as regras do enunciado garantidas **pelo banco**, não pela API.
- Demonstrações ao vivo reproduzíveis com comandos simples (`curl`, `docker compose`, `psql`).
- Teste de corrida: 500 agendamentos simultâneos para o mesmo médico e horário → exatamente 1 sucesso.
- Tudo containerizado (exigência do p2).

**Não-objetivos**
- Login/autenticação, telas completas de cadastro, layout caprichado.
- Integração efetiva com os Temas 2–5 (fica para depois; só deixamos o caminho aberto).
- Medição de desempenho como a do Tema 3 (opcional, só se sobrar tempo).

**Anti-objetivos (falharia mesmo "funcionando")**
- Regra de negócio importante implementada só no Python (ex.: checar conflito de horário com `SELECT` antes do
  `INSERT`). O professor precisa ver o banco garantindo.
- Uso de ORM que esconda o SQL.

## 3. Restrições

- Docker e Docker Compose; a aplicação também precisa ser containerizada.
- Mesma stack do Tema 3: Python 3.12, FastAPI 0.115.0, uvicorn[standard] 0.30.6, Nginx, 3 réplicas da API.
- Porta pública **8081** (a 8080 é do Tema 3; os dois sistemas precisam rodar juntos no mesmo notebook).
- Prazo: 27/11/2026.

## 4. Abordagens consideradas

| Abordagem | Prós | Contras |
|---|---|---|
| **A. PostgreSQL + API Python/FastAPI (estrutura do Tema 3)** ← escolhida | Integra com o Tema 3 sem esforço; mesma demo de corrida; atende "aplicação containerizada" | Um pouco mais de trabalho que só SQL |
| B. Só PostgreSQL no Docker + demo via DBeaver/psql | Rápido, foco total em SQL | Pode não contar como "aplicação"; não integra com os outros temas |
| C. Node/TypeScript (NestJS) + ORM | Stack conhecida do Antônio | ORM esconde o SQL avaliado; destoa do Tema 3 |

Escolha: **A**, aprovada em 16/11. (Inicialmente recomendei Node; troquei para Python depois de ver o projeto do
Tema 3, para facilitar a integração.)

## 5. Arquitetura

```
cliente ──► nginx (localhost:8081) ──► api ×3 (FastAPI + asyncpg) ──► postgres (volume pg-data)
                                                                       ▲
                                                 DBeaver/psql (localhost:5433) para mostrar o banco
```

Estrutura de pastas (`LabBD/cadastro`):

```
cadastro/
├── docker-compose.yml     postgres + api (deploy.replicas: 3) + nginx + loadtest (profile "test")
├── nginx.conf             igual ao do Tema 3 (upstream api:8000)
├── db/                    montado em /docker-entrypoint-initdb.d (roda só na 1ª subida do volume)
│   ├── 01_schema.sql
│   ├── 02_auditoria.sql
│   ├── 03_faturamento.sql
│   └── 04_seed.sql
├── api/
│   ├── main.py, Dockerfile, requirements.txt
│   └── static/index.html
└── loadtest/
    ├── Dockerfile
    └── test.py
```

- Imagem `postgres:16-alpine`, healthcheck `pg_isready`, volume `pg-data`, porta `5433:5432`.
- A API usa **asyncpg com SQL escrito à mão** e um pool de conexões.
- Recriar o banco do zero (ex.: depois de mudar um `.sql`): `docker compose down -v && docker compose up -d --build`.

## 6. Modelo de dados (`01_schema.sql`)

Extensão: `CREATE EXTENSION btree_gist;` (necessária para a exclusion constraint com `=` em inteiro).

| Tabela | Colunas principais | Regras |
|---|---|---|
| `especialidade` | id, nome, valor_consulta | nome `UNIQUE`; valor_consulta `> 0` |
| `convenio` | id, nome, cnpj | nome e cnpj `UNIQUE`; cnpj com 14 dígitos (`CHECK`) |
| `plano` | id, convenio_id, nome, cobertura_pct | FK convênio; `UNIQUE(convenio_id, nome)`; cobertura entre 0 e 100 |
| `paciente` | id, nome, cpf, data_nascimento, telefone, plano_id, carteirinha, validade_carteirinha | cpf `UNIQUE` com 11 dígitos; nascimento ≤ hoje; FK plano (nulo = particular); plano, carteirinha e validade são todos nulos ou todos preenchidos |
| `medico` | id, nome, crm, especialidade_id | crm `UNIQUE`; FK especialidade |
| `agendamento` | id, paciente_id, medico_id, tipo, periodo (`tstzrange`), status, valor_cirurgia, criado_em | FKs; tipo ∈ {consulta, cirurgia}; status ∈ {agendado, realizado, cancelado}; `valor_cirurgia` preenchido ⇔ tipo = cirurgia; período não vazio |
| `fatura` | id, agendamento_id, valor_total, valor_convenio, valor_paciente, emitida_em | FK agendamento `UNIQUE` (uma fatura por atendimento); valores ≥ 0; `valor_convenio + valor_paciente = valor_total` |
| `auditoria` | id, tabela, operacao, registro_id, dados_antigos (jsonb), dados_novos (jsonb), usuario, em | só recebe inserções do trigger |

FKs com `ON DELETE RESTRICT` (padrão): não se apaga médico, plano ou paciente que tenha agendamentos.

### Concorrência: sem agendamento duplicado

```sql
ALTER TABLE agendamento ADD CONSTRAINT sem_conflito_medico
  EXCLUDE USING gist (medico_id WITH =, periodo WITH &&) WHERE (status <> 'cancelado');
ALTER TABLE agendamento ADD CONSTRAINT sem_conflito_paciente
  EXCLUDE USING gist (paciente_id WITH =, periodo WITH &&) WHERE (status <> 'cancelado');
```

O banco recusa qualquer sobreposição de horário do mesmo médico (ou do mesmo paciente), mesmo com transações
concorrentes vindas de réplicas diferentes da API. Agendamentos cancelados liberam o horário. Erro gerado:
`23P01 exclusion_violation`, que a API devolve como **409**.

**Fila por médico (adicionado na implementação, 16/11):** com centenas de inserções simultâneas no mesmo
intervalo, as transações se esperavam dentro da exclusion constraint e o Postgres desfazia parte delas por
deadlock (`40P01`, ~1 s para detectar cada um), o que estourava o timeout do Nginx. Um trigger
`BEFORE INSERT OR UPDATE` em `agendamento` trava a linha do médico (`SELECT … FOR NO KEY UPDATE`): as
tentativas para o mesmo médico entram em fila e cada uma encontra o conflito já gravado. A constraint continua
sendo a garantia; a API também trata `40P01` como 409.

## 7. Auditoria (`02_auditoria.sql`)

- Função de trigger `fn_auditoria()` (PL/pgSQL), ligada `AFTER INSERT OR UPDATE OR DELETE` em `paciente`,
  `medico` e `plano` (cadastros sensíveis).
- Grava `to_jsonb(OLD)` e `to_jsonb(NEW)`, a operação, o id do registro e o momento.
- Usuário: `coalesce(current_setting('app.usuario', true), current_user)`. A API, dentro de cada transação de
  escrita, executa `SELECT set_config('app.usuario', $1, true)` com o valor do cabeçalho `X-Usuario`
  (padrão `api`). Assim a auditoria registra quem fez a alteração na aplicação, não só o usuário do banco.
- Um `UPDATE` que não muda nada não gera registro (comparar `OLD IS DISTINCT FROM NEW`).

## 8. Faturamento (`03_faturamento.sql`)

`CREATE PROCEDURE realizar_atendimento(p_agendamento_id int, INOUT p_fatura_id int DEFAULT NULL)`:

1. `SELECT ... FOR UPDATE` no agendamento (trava a linha; duas chamadas simultâneas não faturam duas vezes).
2. Se não existe → erro; se status ≠ `agendado` → erro.
3. Valor: `valor_consulta` da especialidade do médico (consulta) ou `valor_cirurgia` (cirurgia).
4. Paciente com plano: exige `validade_carteirinha >= data do atendimento`, senão `RAISE EXCEPTION`
   (“plano vencido”). Cobertura = `valor_total * cobertura_pct / 100`. Particular: convênio paga 0.
5. Insere a fatura e muda o status para `realizado`.

Como a procedure é chamada dentro de uma transação, qualquer erro desfaz tudo: nem fatura, nem mudança de status.
Erros de regra usam `RAISE EXCEPTION ... USING ERRCODE = 'P0001'`; a API devolve **422** com a mensagem.

## 9. API (`api/main.py`)

| Método e rota | O que faz |
|---|---|
| `GET /health` | `SELECT 1` |
| `GET /pacientes`, `GET /pacientes/{id}` | lista / detalhe |
| `POST /pacientes` | cadastra |
| `PUT /pacientes/{id}` | altera (gera auditoria) |
| `GET /medicos`, `GET /especialidades`, `GET /convenios` | listas (com planos no convênio) |
| `POST /agendamentos` | `{paciente_id, medico_id, tipo, inicio, fim, valor_cirurgia?}` |
| `GET /agendamentos?medico_id=&data=` | agenda |
| `POST /agendamentos/{id}/cancelar` | status → cancelado |
| `POST /agendamentos/{id}/realizar` | `CALL realizar_atendimento($1, NULL)` → devolve a fatura |
| `GET /faturas` | lista |
| `GET /auditoria?limit=` | últimos registros |
| `GET /` | `static/index.html` |

Tradução de erros do banco:

| SQLSTATE | Significado | HTTP |
|---|---|---|
| 23P01 | horário em conflito | 409 |
| 23505 | duplicado (CPF, CRM…) | 409 |
| 23503 | referência inexistente (FK) | 422 |
| 23514 | `CHECK` violado | 422 |
| P0001 | regra da procedure (plano vencido etc.) | 422 |

Toda escrita roda em `async with conn.transaction():` e começa com o `set_config` do usuário.

## 10. Página de demo (`static/index.html`)

Uma página simples, sem framework, com três blocos atualizados por `fetch` a cada 2 s: agenda do dia, faturas e
últimos registros de auditoria. Serve para a plateia ver o efeito de cada comando da demo.

## 11. Dados de exemplo (`04_seed.sql`)

- 4 especialidades (Clínica Geral, Cardiologia, Ortopedia, Pediatria) com valores de consulta.
- 2 convênios com 2 planos cada (coberturas diferentes, ex.: 70% e 100%).
- 6 médicos, 8 pacientes: com plano válido, **com plano vencido** (para a demo de rollback) e particulares.
- Alguns agendamentos no dia da apresentação.

## 12. Teste de corrida (`loadtest/test.py`, profile `test`)

1. Cria 500 pacientes (CPFs gerados a partir do índice) via API.
2. Dispara 500 `POST /agendamentos` **simultâneos** (httpx + asyncio, como no Tema 3) para o mesmo médico e
   o mesmo horário, cada um com um paciente diferente.
3. Imprime `sucessos=1 (esperado=1) conflitos=499`.
4. Cancela o agendamento vencedor para a demo poder ser repetida.

Rodar: `docker compose --profile test run --rm loadtest`.

## 13. Roteiro das demonstrações (base para a apresentação)

1. `docker compose ps` — postgres, 3 APIs, nginx.
2. Integridade: cadastrar paciente com CPF repetido → 409; agendar com médico inexistente → 422.
3. Conflito simples: dois agendamentos sobrepostos → o segundo dá 409.
4. Corrida: o loadtest → 1 sucesso, 499 conflitos.
5. Auditoria: `PUT /pacientes/{id}` → aparece em `GET /auditoria` com antes/depois e usuário.
6. Faturamento: realizar atendimento de paciente com plano válido → fatura com divisão convênio/paciente.
7. Rollback: realizar atendimento de paciente com plano vencido → 422 e, no banco, nada mudou
   (status ainda `agendado`, nenhuma fatura).

## 14. Integração futura (fora deste escopo)

- Nginx único na frente de todos os temas, com prefixos (`/cadastro`, `/triagem`, …).
- O paciente do Tema 3 hoje tem ID próprio (uuid). O caminho natural é a triagem receber o `paciente_id` do Tema 1.
  Combinar com o Stéfano depois que as duas partes estiverem funcionando.

## 15. Decisões tomadas na revisão (calls do Claude, revisar)

- **Fuso horário:** `TZ=America/Sao_Paulo` e `PGTZ=America/Sao_Paulo` no container do Postgres; a API recebe
  `inicio`/`fim` em ISO 8601 e monta o período em SQL: `tstzrange($n::timestamptz, $m::timestamptz, '[)')`
  (fim aberto: uma consulta que termina às 10:00 não conflita com outra que começa às 10:00).
- **Healthcheck:** `pg_isready -U postgres -h localhost` (com `-h`, o check só passa depois que os scripts de
  `db/` terminaram, porque durante a inicialização o Postgres não escuta em TCP).
- **Seed com datas relativas:** agendamentos e validades usam `current_date` (ex.: `current_date + 9`), para a
  demo funcionar em qualquer dia; o paciente "vencido" tem validade `current_date - 30`.
- **Loadtest repetível:** os CPFs dos 500 pacientes usam um prefixo aleatório por execução, para não colidir
  com execuções anteriores; o horário disputado é fixo (amanhã às 07:00) e o vencedor é cancelado no fim.

## 16. Decisões deixadas para quem implementar

- Nomes exatos de colunas e mensagens de erro, desde que sigam as regras acima.
- Formato JSON das respostas.
- Visual da página de demo.
- Testes automatizados: preferir testes que rodem contra o Postgres real (subido pelo compose), porque o que
  se testa são as regras do banco.
