# Interface da recepção — redesign (Tema 1)

Data: 19/11/2026 · substitui o visual "Sinalização Hospitalar" (achado confuso e poluído pelo usuário)

## Intenção
Mesmas funções e a mesma exibição dos bastidores do banco, mas organizadas: uma tela por tarefa, componentes
consistentes, cara de sistema bem-feito. Usada ao vivo num notebook ligado à TV e também no celular.

## Abordagens consideradas
- **Menu lateral + painel fixo "Bastidores do banco"** ← escolhida pelo usuário: organizado e o banco sempre visível.
- Abas no topo + aviso flutuante: mais limpo, mas o banco só aparece no instante da ação.
- Tela dividida recepção/console: destaque máximo ao banco, recepção espremida.

## Estrutura
- **Menu lateral (240px):** marca "Hospital · Recepção"; itens Agenda, Pacientes, Faturas, Auditoria, com ícone
  e contador; no rodapé, o seletor de guichê (vai no cabeçalho `X-Usuario`, aparece na auditoria).
- **Área principal:** cabeçalho da tela (título, uma frase, botão principal) e o conteúdo em um cartão.
  - **Agenda:** filtro por médico; tabela agrupada por dia (hora, paciente, médico, tipo, status, ações
    Realizar / Cancelar). Cirurgia com selo e valor.
  - **Pacientes:** tabela (nome, CPF, nascimento, plano ou "Particular", validade com selo "vencido").
  - **Faturas:** resumo (faturas, total, parte do convênio, parte dos pacientes) e tabela.
  - **Auditoria:** tabela (quando, guichê, tabela, operação, registro, o que mudou como "campo: antes → depois").
- **Formulários** (novo paciente, novo agendamento) abrem numa **gaveta lateral**; erro do banco aparece como
  alerta dentro da gaveta, além do painel.
- **Painel "Bastidores do banco" (360px, fixo à direita):** cada resposta vira um cartão no topo: selo
  Gravado/Recusado, código HTTP, o que aconteceu, tipo + nome da regra (EXCLUDE `sem_conflito_medico`, UNIQUE,
  CHECK, FOREIGN KEY, PROCEDURE `realizar_atendimento`, TRIGGER), SQLSTATE e hora. O mais recente em destaque.
- **Celular / tela estreita:** menu vira barra de abas; o painel vira uma gaveta aberta por um botão com contador.

## Visual (minhas escolhas)
Fundo cinza muito claro, cartões brancos com borda fina, cantos 12px, sombra suave só em gaveta/overlay. Uma cor
de destaque (verde-azulado hospitalar), verde para gravado, vermelho para recusado, âmbar para alerta. Fonte Inter
servida localmente, números tabulares. Ícones em SVG próprio, traço único. Tamanhos legíveis na TV (texto ≥16px).

## Restrições
- Só muda `cadastro/api/static/`; API e banco ficam como estão (já devolvem `sqlstate` e `regra`).
- HTML/CSS/JS puros, sem build, sem rede além de arquivos locais.
- Os elementos `#agenda`, `#faturas`, `#auditoria` continuam existindo (teste da página).

## Fora do escopo
Login, edição de paciente pela interface (a demo de UPDATE continua no psql), integração com outros temas.
