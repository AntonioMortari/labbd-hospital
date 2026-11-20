# Design — Interface da recepção (Tema 1)

Sistema visual da interface em `cadastro/api/static/` (redesign de 19/11/2026). Objetivo: um sistema de recepção
organizado, uma tarefa por tela, com os bastidores do PostgreSQL sempre visíveis.

## Estrutura

| Área | O que é |
|---|---|
| Menu lateral (232px) | marca, navegação (Agenda, Pacientes, Faturas, Auditoria) com contadores, seletor de atendente |
| Área principal | cabeçalho da tela (título, uma frase, botão principal) + um cartão com o conteúdo |
| Bastidores do banco (352px) | lista de respostas do PostgreSQL, a mais recente em destaque, até 30 cartões |
| Gavetas (480px) | formulários de novo paciente e novo agendamento; erro do banco aparece dentro delas |

Abaixo de 1100px o menu vira barra de abas e os bastidores viram gaveta (botão com contador). Abaixo de 720px as
tabelas viram listas.

## Tokens

| Token | Valor | Uso |
|---|---|---|
| `--fundo` | `#F6F7F9` | fundo da página |
| `--cartao` | `#FFFFFF` | cartões, menu, painel, gavetas |
| `--borda` / `--borda-forte` / `--linha` | `#E3E6EB` / `#CDD3DB` / `#EEF0F3` | divisões e contornos |
| `--texto` / `--texto-2` / `--texto-3` | `#0F172A` / `#475467` / `#5D6B7E` | texto principal, secundário, terciário |
| `--destaque` / `-escuro` / `-claro` | `#0F766E` / `#0B5F59` / `#E6F4F2` | ação principal, item ativo, selo "agendado" |
| `--gravado*` | `#15803D`, `#DCFCE7`, `#166534` | selo e cartão "Gravado", "Realizado" |
| `--recusado*` | `#B42318`, `#FEE4E2`, `#912018` | selo e cartão "Recusado", "Vencido", alerta da gaveta |
| `--alerta-claro` / `--alerta-texto` | `#FEF0C7` / `#93370D` | selo de cirurgia, operação UPDATE |
| `--neutro-claro` / `--neutro-texto` | `#EEF2F6` / `#344054` | contadores, "Particular", código |
| `--raio` / `--raio-c` | 12px / 8px | cartões / controles |

Tipografia: Inter (variável, servida localmente), números tabulares. Título de tela 1.75rem/700; títulos de
painel 1.0625–1.25rem/700; corpo 1rem; rótulos e cabeçalhos de tabela .8125–.875rem/600. Código e nomes de regras
em monoespaçada do sistema.

## Componentes

- **Botão**: primário (destaque), secundário (branco com borda), fantasma; tamanho `sm` nas linhas da tabela;
  variante `perigo` para Cancelar.
- **Selo**: pílula com ponto; variantes `gravado`/`realizado`, `recusado`/`vencido`, `agendado`/`destaque`,
  `cancelado` (riscado), `aviso`; `sem-ponto` para rótulos que não são estado.
- **Tabela**: cabeçalho discreto, linhas de 56px, linha de grupo por dia, linha nova realçada por 1,6s.
- **Cartão de evento** (bastidores): selo Gravado/Recusado, código HTTP, hora, título em português, tipo + nome
  da regra (EXCLUDE, UNIQUE, CHECK, FOREIGN KEY, PROCEDURE, TRIGGER) e SQLSTATE.
- **Gaveta**: topo com título e fechar, corpo rolável, rodapé com Cancelar + ação principal; Esc e clique fora
  fecham; em erro continua aberta com os dados e um alerta.
- **Estado vazio**: título, frase e a ação que resolve.

## Regras

1. Uma tarefa por tela; formulários só aparecem quando pedidos.
2. Toda resposta do banco vira um cartão nos bastidores, com a regra que decidiu.
3. Cor carrega significado (gravado, recusado, aviso); o destaque verde-azulado é só para ação e seleção.
4. Sombra só no que flutua (gaveta, cartão de evento mais recente); o resto é borda.
