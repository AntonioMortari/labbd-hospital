# Interface da recepção (redesign) — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reescrever `cadastro/api/static/` como um app organizado: menu lateral, uma tela por tarefa, formulários em gaveta e o painel fixo "Bastidores do banco".

**Architecture:** Página única (HTML/CSS/JS puros) com quatro telas trocadas por hash (`#/agenda`, `#/pacientes`, `#/faturas`, `#/auditoria`). Todo acesso à API passa por `api()`; toda resposta de escrita vira um evento em `bastidores.registrar()`. Nada muda na API nem no banco.

**Tech Stack:** HTML/CSS/JS sem build; Inter auto-hospedada (variável, woff2); FastAPI já serve `/static`.

**Spec:** `docs/superpowers/specs/2026-11-19-interface-redesign-design.md`

## Global Constraints
- Só `cadastro/api/static/` muda (mais um teste em `tests/test_api.py`).
- Sem dependência de rede: fontes e ícones locais (ícones em SVG inline, traço 1.75, 20px).
- Texto ≥16px na área de trabalho; números tabulares; contraste ≥4.5:1.
- `#agenda`, `#faturas`, `#auditoria` continuam existindo.
- Cores: fundo `#F6F7F9`, cartão `#FFFFFF`, borda `#E3E6EB`, texto `#0F172A`, texto secundário `#475467`, destaque `#0F766E`, gravado `#15803D`, recusado `#B42318`, alerta `#B54708`. Cantos 12px (cartão), 8px (controle).
- Sem commits durante a execução (o usuário decide no fim).

## Review Focus
1. Erro do banco dentro da gaveta: o formulário continua aberto com os dados preenchidos e mostra o alerta; o painel também registra.
2. Painel com muitos eventos: lista rola dentro do painel, mantém no máximo 30 cartões, o mais novo em cima.
3. Agenda vazia ou filtro sem resultado: mensagem de estado vazio com ação ("Novo agendamento").
4. API fora do ar: placa do painel registra "Sem conexão" (status 0) sem quebrar a página.
5. Celular (390px): sem rolagem horizontal da página; tabelas viram listas; gaveta ocupa a largura toda.

---

### Task 1: Estrutura (HTML), fonte e sistema visual (CSS)

**Files:**
- Modify: `api/static/index.html` (reescrita), `api/static/app.css` (reescrita), `tests/test_api.py`
- Create: `api/static/fonts/inter-latin.woff2`, `inter-latin-ext.woff2` (via `impeccable font-fetch Inter`); remover os arquivos Overpass

**Interfaces:**
- Produces (DOM): `nav .nav-item[data-view]` (agenda, pacientes, faturas, auditoria) com `.contador`; `select#usuario`; `section.view#view-<nome>` com `#agenda`, `#pacientes-tabela`, `#faturas`, `#resumo-faturas`, `#auditoria`; `#filtro-medico`; botões `[data-abrir="paciente"|"agendamento"]`; gavetas `aside.gaveta#gaveta-paciente` e `#gaveta-agendamento` com `form` e `.alerta` vazio; painel `aside#bastidores` com `ol#eventos` e `.vazio`; botão `#abrir-bastidores` (celular) com `.contador`.
- Produces (CSS): componentes `.botao` (primario/secundario/fantasma/perigo, tamanho `sm`), `.selo` (gravado/recusado/neutro/alerta/destaque), `.tabela`, `.cartao`, `.campo`, `.alerta`, `.gaveta`, `.evento`.

- [ ] **Step 1: Teste que falha** — `test_interface_estrutura`: `GET /` contém `id="bastidores"`, `data-view="agenda"`, `data-view="pacientes"`, `data-view="faturas"`, `data-view="auditoria"`, `id="gaveta-agendamento"`, `id="gaveta-paciente"`; `GET /static/fonts/inter-latin.woff2` → 200 `font/woff2`. Ajustar `test_arquivos_da_interface` para a fonte Inter.
- [ ] **Step 2: Rodar e ver falhar.** `docker compose up -d --build api && docker compose --profile test run --rm tests pytest -q -p no:cacheprovider test_api.py -k "interface or arquivos"` → FAIL.
- [ ] **Step 3: Escrever `index.html` e `app.css`** conforme Interfaces e Global Constraints. Layout desktop: grade `240px 1fr 360px`, altura da janela, menu e painel fixos, área principal rola. ≤1100px: menu vira barra de abas no topo, painel vira gaveta à direita aberta por `#abrir-bastidores`. ≤720px: tabelas viram listas (cada linha um bloco).
- [ ] **Step 4: Rodar e passar** (rebuild da api + restart do nginx) → PASS.

### Task 2: Dados e telas (JS)

**Files:**
- Modify: `api/static/app.js` (reescrita)

**Interfaces:**
- Consumes: DOM da Task 1; rotas da API (`/pacientes`, `/medicos`, `/convenios`, `/agendamentos`, `/faturas`, `/auditoria?limit=`).
- Produces: `api(metodo, caminho, corpo) -> Promise<{ok, status, dados}>`; `estado`; `irPara(view)`; `render.agenda()`, `render.pacientes()`, `render.faturas()`, `render.auditoria()`; `atualizar()` (a cada 3 s; cadastros a cada 15 s).

- [ ] **Step 1: Implementar** navegação por hash (padrão `#/agenda`), contadores no menu, as quatro telas (agenda agrupada por dia a partir de hoje, até 60 itens, filtro por médico, ações só em `agendado`, selo de status e selo "cirurgia R$ …"; pacientes com selo do plano/"Particular" e "Vencido" quando `validade_carteirinha` < hoje; faturas com resumo de 4 números e tabela; auditoria com "campo: antes → <b>depois</b>"), estados vazios com ação.
- [ ] **Step 2: Verificar no navegador** (banco recriado): cada item do menu mostra sua tela; contadores batem com a API; sem erros de JS no console.

### Task 3: Gavetas, ações e Bastidores (JS)

**Interfaces:**
- Consumes: Task 2.
- Produces: `gaveta.abrir(nome)`, `gaveta.fechar()`; `bastidores.registrar({ok, status, titulo, detalhe, regra, sqlstate})`; `REGRAS` (mesmo mapa de regras → tipo/explicação da versão anterior).

- [ ] **Step 1: Implementar** gavetas (foco no primeiro campo, Esc fecha, clique fora fecha, botão Salvar com estado "Salvando…"); envio de paciente e agendamento; Realizar e Cancelar na agenda; em erro: gaveta continua aberta com `.alerta` (título em português + regra + SQLSTATE) e o painel registra; em sucesso: gaveta fecha, painel registra, linha nova é destacada. Painel: cartão com selo Gravado/Recusado, código HTTP, título, linha da regra (`tipo` + `<code>nome</code>` + explicação), SQLSTATE, hora; máximo 30; o mais novo destacado; contador no botão do celular.
- [ ] **Step 2: Verificar no navegador** os cinco casos: conflito (409 `sem_conflito_medico`), CPF duplicado (409 `paciente_cpf_key`), período invertido (422 SQLSTATE 22000), plano vencido (422 `realizar_atendimento`), realizar com sucesso (201, fatura). Mais os itens 1, 2 e 4 da Review Focus.

### Task 4: Verificação final

- [ ] **Step 1:** `docker compose --profile test run --rm tests` → todos passam.
- [ ] **Step 2:** capturas 1440×900 e 390×844 com banco recriado (`impeccable first-viewport … --figures-supplied`); conferir item 5 da Review Focus e que nada corta.
- [ ] **Step 3:** atualizar README (linha da interface) e `DESIGN.md` para o sistema novo.
