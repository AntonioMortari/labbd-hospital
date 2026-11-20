# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- **Apresentadores (Yuri e Antônio):** operam a interface ao vivo no seminário final de Laboratório de Banco de Dados (27/11/2026), com mouse e teclado, num notebook ligado à TV da sala.
- **Plateia (Prof. Eduardo Freitas e a turma):** assiste de longe, na TV; avalia a apresentação (40% da nota) e o uso do banco (40%). Precisa entender, sem ler código, o que o banco garantiu em cada ação.
- **Persona simulada:** a recepcionista de um hospital que cadastra pacientes, agenda consultas e cirurgias e registra atendimentos. Ela é a história que a demo conta, não um usuário real.
- A interface também precisa funcionar no celular (confirmado).

## Product Purpose

Interface do Tema 1 (Cadastro de Pacientes, Equipe Médica e Agendamentos) do Sistema de Gestão Hospitalar e Telemedicina. Permite cadastrar paciente, agendar consulta ou cirurgia, cancelar e realizar atendimento (que emite a fatura), e mostra ao vivo agenda, faturas e auditoria. Sucesso: a plateia vê o sistema funcionando como uma recepção real e, ao mesmo tempo, enxerga as regras do PostgreSQL agindo: o que foi gravado, o que foi recusado e por qual regra.

## Positioning

"Recepção + bastidores": cada ação da recepcionista vem acompanhada do que o banco fez por trás (constraint que recusou, trigger que gravou a auditoria, transação desfeita por rollback). O diferencial do Tema 1 é que as regras vivem no banco e não na aplicação; a interface torna isso visível.

## Operating Context

- Servida pela própria API FastAPI do Tema 1 (`cadastro/api/static/`), em `http://localhost:8081`, atrás do Nginx, com 3 réplicas da API.
- Usada durante a demonstração ao vivo, ao lado dos slides e do terminal (psql, teste de carga). O roteiro está em `cadastro/README.md`.
- Banco recriado antes de apresentar; dados de exemplo com IDs fixos (Ana Souza, Carlos Vencido com plano vencido, etc.).

## Capabilities and Constraints

- Rotas disponíveis: `GET/POST /pacientes`, `GET/PUT /pacientes/{id}`, `GET /medicos`, `/especialidades`, `/convenios` (com planos), `POST/GET /agendamentos`, `POST /agendamentos/{id}/cancelar`, `POST /agendamentos/{id}/realizar`, `GET /faturas`, `GET /auditoria`, `GET /health`.
- Erros chegam como `{"detail": "..."}`: 409 (CPF/CRM duplicado, horário indisponível), 422 (chave estrangeira, CHECK, plano vencido, status que não pode mudar, dado inválido), 404 (não encontrado).
- O cabeçalho `X-Usuario` identifica quem fez a alteração na auditoria.
- Stack fixa: HTML, CSS e JavaScript puros, sem framework e sem etapa de build, servidos como arquivo estático pela API. Não pode depender de rede além das fontes (a demo pode rodar sem internet; precisa degradar bem).
- Idioma: português do Brasil. Moeda: R$. Fuso: America/Sao_Paulo.
- Não há login nem autenticação (fora do escopo).

## Evidence on Hand

- Dados de exemplo reais do seed (`cadastro/db/04_seed.sql`): 4 especialidades, 2 convênios com 2 planos, 6 médicos, 8 pacientes, 6 agendamentos.
- Resultados medidos: 500 agendamentos simultâneos → 1 gravado e 499 recusados em cerca de 8 s; 66 testes automatizados.
- Não inventar números, depoimentos ou métricas além desses.

## Product Principles

1. O banco é o protagonista: toda recusa mostra a regra do PostgreSQL que a causou.
2. Legível de longe: quem está no fundo da sala precisa entender o que aconteceu.
3. Uma ação, uma consequência visível: depois de cada clique, a agenda, as faturas ou a auditoria mudam na hora, ou a recusa aparece explicada.
4. Honesto com os dados: só mostra o que a API devolveu; nada de valores simulados.

## Accessibility & Inclusion

Projeção em TV para leitura à distância: texto grande e alto contraste. Também usável no celular.
