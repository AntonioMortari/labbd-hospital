# Auditoria de UX e UI do sistema hospitalar (shell + 5 módulos)

Data: 24/11/2026. Método: duas avaliações independentes (revisão de design e fluxos; detector + medições no navegador em 1366×768, 1024×768 e 390×844) e síntese.

## Nota geral

- Heurísticas de Nielsen: **24/40** (bom na tese de domínio, médio na usabilidade geral).
- Carga cognitiva: **alta** (5 de 8 itens do checklist falham).
- Detector: 4 achados, 3 falsos positivos (o painel de TV usa tokens `var(--tv-*)` que o detector não resolve; o contraste real é 17,9:1 e 8,5:1) e 1 real e defensável (ponto pulsante de status no Tema 5).

## Corrigido nesta rodada (bugs concretos)

| Problema | Onde | Correção |
|---|---|---|
| Tabela de tendência maior que a tela (1.787 px num container de 1.176; sem barra de rolagem) | Tema 5, Banco por dentro | `.tabela-rolagem` não existia no kit (o wrapper era inerte). Criada no kit; tabela reduzida de 13 para 7 colunas com cabeçalhos em português; tabelas de regras e políticas envolvidas |
| Shell com 832 px de largura em tela de 390 px (conteúdo cortado) | `integracao/hub/index.html` | `grid-template-columns: minmax(0, 1fr)` e `min-width: 0` na barra |
| Tabelas cortadas no celular (Fila, Alertas, Políticas) | Temas 3 e 5 | Mesma causa: `.tabela-rolagem` |
| Resumo de 4 métricas estourando em 390 px | Temas 3 e 4 | `.resumo` em 2 colunas abaixo de 560 px; Mongo em 3 colunas compactas |
| Abas quebrando em duas linhas, largura fixa | Temas 2 a 5 | Abas com a largura do próprio texto, rolagem se não couberem |
| "958 min" de espera | Tema 3 | Formato "15 h 58 min" / "2 d 3 h" |
| "cadastro #3" | Tema 3 | "paciente do cadastro" |
| "Internar" e "Internar em leito" parecidos | Tema 3 | "Internar direto" (na fila) e "Escolher leito" (nos chamados) |
| Botões "Bastidores" e "Corrigir" parecendo texto/desabilitados | Temas 2, 3, 4 | Estilo de botão com borda |
| Painel de TV sem título (h1) | Tema 3 | h1 acessível oculto |
| Borda dos campos 1,5:1 (WCAG 1.4.11) e foco 2,5:1 | kit e Cadastro | Borda `#8793A3` (3:1) e foco sólido `#0F766E` |
| Faixa de alertas ocupando meia tela no celular; alerta não levava ao paciente | Tema 5 | Até 3 alertas, só o título no celular, clique abre o paciente; lista ordenada por gravidade, abre no primeiro em alerta |
| Rodapé do shell falando com o desenvolvedor (`modulos.json`, `/health`) | Shell | Removido |
| Páginas antigas em cache (aba Banco "não abria", tabelas sem correção) | Shell e módulos | `Cache-Control: no-cache` e `kit.css?v=2` |

## Pendente: mudanças de fluxo (decisão necessária)

**P1. Nenhum paciente atravessa os módulos.** A mesma Ana Souza (id 1) está em Cadastro, Interações, Triagem, Prontuário e Sinais, mas nada liga uma tela à outra. O shell vende "um sistema só" e entrega cinco sites. Proposta: tela inicial como roteiro da jornada da recepcionista em 5 passos, e um "paciente em foco" levado pelo shell (`#/prontuario?p=1`) que pré-seleciona o paciente nos módulos.

**P1. Fluxos comprimidos numa tela.** Triagem mistura fila, chamados e leitos; Prontuário mostra o documento inteiro de 7 seções num scroll e o diálogo de alteração pede dado, responsável e justificativa juntos; Interações tem a demonstração escondida na aba Cadastrar. Proposta por módulo na seção "Fluxo por módulo" abaixo.

**P1. Jargão na plateia.** SQLSTATE 23P01, EXCLUDE, Cypher, hypertable, chunks, TTL, scripts Lua, "agregações contínuas". Proposta: título humano grande ("Horário já ocupado") e o termo técnico pequeno e recolhido; uma frase de definição por termo; botão "Bastidores" virar "O que o banco fez".

**P1. Legibilidade na TV.** Corpo de 16 px, rótulos de 13 px, `--texto-3` fraco à distância. Proposta: modo "Apresentar" no shell (tecla P) que sobe a escala para 20 px e esconde as dicas.

**P2. Bastidores sem lugar fixo fora do Cadastro.** Temas 2 a 4 escondem o que o banco respondeu atrás de um botão. Proposta: aviso de uma linha por ação ("Gravado · ZADD na fila") com "ver detalhes".

**P2. Três esqueletos diferentes.** Cadastro (menu lateral + painel fixo + gaveta) contra páginas centradas com abas (demais), e nomes diferentes para o mesmo conceito ("Banco", "Redis por dentro", "MongoDB por dentro", "Banco por dentro"). Proposta: padronizar cabeçalho (título + 1 frase + 1 ação), posição das abas e o nome "Por dentro do <banco>".

**P2. Alvos de toque de 34 a 42 px** (recomendado 44). `button.link` do diagrama do Cadastro com 24 px.

**P3. Diagrama ER do Cadastro com texto de 11 px**; "1 linhas" sem plural; seletor "Atendente" cortado.

## Fluxo por módulo (onde se perde e proposta)

- **Cadastro:** "Realizar" gera a fatura em outra aba e a plateia perde o efeito. Mostrar "Fatura emitida" no próprio cartão. Confirmação leve em "Cancelar". Separar no menu "Recepção" (Agenda, Pacientes, Faturas) de "Bastidores" (Auditoria, Banco).
- **Interações:** a ordem das abas contraria o fluxo. Reordenar: Dados, Riscos, Rede, Comparar. "Ver como o grafo respondeu" aberto por padrão no primeiro alerta.
- **Triagem:** um próximo passo por paciente (Aguardando, Chamado, Internado) com um botão cujo rótulo diz o destino. A "Simular disputa" (a joia do Redis) vira cartão de demonstração próprio.
- **Prontuário:** depois de salvar, aviso "v4 guardada em Versões [Ver o que mudou]". "Carregar exemplos" para um menu "...".
- **Sinais vitais:** abrir já no primeiro paciente em alerta (feito), um gráfico principal grande e três pequenos (pendente), frase de abertura em linguagem de recepção no Banco por dentro.

## Personas (resumo)

- **Apresentador ao vivo:** sem ordem de demonstração na tela; bastidores abertos à mão; ações destrutivas ao lado das normais.
- **Plateia na TV:** texto pequeno, jargão sem definição; só o painel de TV da Triagem é legível de longe.
- **Recepcionista:** o fluxo do Cadastro funciona, mas depois precisa "lembrar o ID".
