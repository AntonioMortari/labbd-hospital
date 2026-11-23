# Roteiro de apresentação: Tema 2 (Interações medicamentosas e rede de contágio, banco de grafos)

Sistema 1 · Gestão Hospitalar e Telemedicina · Laboratório de Banco de Dados · Prof. Eduardo Freitas · 27/11/2026

Duração prevista: **10 a 12 minutos**, mais perguntas. Banco: **Neo4j** (grafo de propriedades, linguagem Cypher).

---

## 1. O que o enunciado pede (e onde cada item aparece)

| O enunciado pede | Onde mostramos |
|---|---|
| Nós para pacientes, medicamentos, patologias e profissionais | Aba **Rede** e Neo4j Browser (`MATCH (n) RETURN n`) |
| Mapear contraindicações e cruzamentos de alergias | Aba **Riscos** (alergia e contraindicação) |
| Travessia no grafo que identifica **riscos de interações cruzadas ao prescrever vários remédios** | Aba **Riscos**, "Ver como o grafo respondeu", e a demonstração ao vivo da seção 6 |
| Eficiência algorítmica na detecção, **em comparação a buscas relacionais** | Aba **Grafo vs SQL** e `PROFILE` no Neo4j Browser (seções 9 e 10) |
| Rede de contágio | Aba **Rede** e consulta de contatos em até 2 saltos (seção 8) |
| Mostrar contribuições e o banco funcionando | Seções 4 a 11, e a seção 12 (contribuições) |

Avaliação: apresentação 40%, uso dos bancos 40%, relatório 20%. Este roteiro cobre os dois primeiros.

---

## 2. Antes de entrar (checklist, 5 minutos antes)

1. Subir o sistema e conferir que o Tema 2 está no ar:

```bash
python3 integracao/sistema.py subir
python3 integracao/sistema.py status        # Tema 2 grafo: "no ar"
```

2. Abrir **http://localhost:8000** e clicar na aba **Interações**.
3. Na aba **Cadastrar**: clicar **Limpar o grafo** (confirmar) e depois **Carregar demonstração**. Isso garante o cenário exato deste roteiro (12 nós, 21 relações).
4. (Opcional) Na mesma aba, **Importar pacientes do cadastro**. Os pacientes 1, 2 e 3 já existem na demonstração com os mesmos nomes do cadastro do Tema 1.
5. Em outra aba do navegador, abrir o **Neo4j Browser**: **http://localhost:7474**
   - Connect URL: `bolt://localhost:7687`
   - Usuário: `neo4j` · Senha: `demonstracao123`
   - Deixar a tela limpa (`:clear`).
6. Aumentar o zoom do navegador (Ctrl +) para a TV.

**Cenário da demonstração** (dados fictícios): 3 pacientes, 5 medicamentos, 2 patologias, 2 profissionais.

| Paciente | Usa | Tem | Alergia | O que o grafo deve achar |
|---|---|---|---|---|
| Ana Souza (1) | Varfarina, Ácido acetilsalicílico, Penicilina | Úlcera gástrica | Penicilina | **3 alertas**: interação Varfarina + AAS; alergia à Penicilina; AAS contraindicado para úlcera |
| Carlos Vencido (2) | Ibuprofeno, Metformina | Insuficiência renal | nenhuma | **1 alerta**: Ibuprofeno contraindicado para insuficiência renal |
| Beatriz Lima (3) | Ibuprofeno | Úlcera gástrica | nenhuma | **1 alerta**: Ibuprofeno contraindicado para úlcera |

Contatos: Ana ↔ Carlos ↔ Beatriz (uma cadeia). Profissionais: Dra. Marina Costa atende Ana e Beatriz; Dr. Paulo Mendes atende Carlos.

---

## 3. Abertura (1 min)

**Falar:**
- "Em um hospital, o risco de uma prescrição não está em um remédio isolado, está na **combinação** dele com o que o paciente já toma, com as alergias dele e com as doenças que ele tem."
- "Esses dados são cheios de **relacionamentos**. Por isso usamos um banco de grafos: o relacionamento é parte do dado, não algo reconstruído com JOIN."
- "Vamos mostrar o modelo, a detecção de riscos por travessia, a rede de contatos, o Neo4j por dentro e uma comparação com SQL."

**Tela:** aba **Interações** aberta em **Riscos**.

---

## 4. O modelo (1,5 min): nós e relações

**Falar:** quatro tipos de nó e sete tipos de relação.

| Nós | Relações |
|---|---|
| Paciente, Medicamento, Patologia, Profissional | `USA`, `ALERGICO_A`, `TEM`, `CONTRAINDICADO_PARA`, `INTERAGE_COM`, `ATENDE`, `CONTATO_COM` |

**Mostrar no sistema:** aba **Rede**.
- As colunas são os tipos de nó (profissionais, pacientes, medicamentos, patologias). As cores das linhas são os tipos de relação (legenda no topo).
- **Clicar em "Ana Souza"**: as ligações dela ficam destacadas e o rodapé diz "6 ligações diretas". Mostrar que ela se liga a medicamentos (`USA`), a uma patologia (`TEM`), a um profissional (`ATENDE`) e a outro paciente (`CONTATO_COM`).
- Observação: `INTERAGE_COM` liga dois medicamentos entre si; `CONTRAINDICADO_PARA` liga medicamento a patologia (linha tracejada).

**Mostrar no Neo4j Browser** (mesmo grafo, visão nativa):

```cypher
MATCH (n) RETURN n LIMIT 50
```

Os nós aparecem coloridos por tipo. Clicar num nó mostra as propriedades (`id`, `nome`); clicar numa seta mostra a observação da relação.

---

## 5. Riscos de um paciente (2,5 min): a travessia

Voltar ao sistema, aba **Riscos**.

**Ana Souza** (já selecionada):
- Resumo no topo: **"Ana Souza tem 3 alertas nos remédios em uso."**
- **Interação entre medicamentos:** "Varfarina e Ácido acetilsalicílico estão em uso juntos e interagem."
- **Alergia:** "Alérgico a Penicilina, que está em uso."
- **Contraindicação:** "Ácido acetilsalicílico é contraindicado para Úlcera gástrica, que o paciente tem."

**Falar (a ideia central):** "O sistema não procura em tabelas. Ele **parte do paciente e caminha pelas ligações**: do paciente até os remédios que ele usa, e de cada remédio até quem interage com ele, até quem é contraindicado para as doenças dele. Só entram na conta os remédios que **o próprio paciente usa**."

**Mostrar a consulta:** abrir "Ver como o grafo respondeu" no cartão de interação. O Cypher é:

```cypher
MATCH (p:Paciente {id: $id})
      -[:USA]->(a:Medicamento)
      -[:INTERAGE_COM]-(b:Medicamento)
      <-[:USA]-(p)
WHERE a.id < b.id
RETURN a.nome, b.nome
```

**Explicar a leitura:** "parte do paciente, segue `USA` até um remédio A, segue `INTERAGE_COM` até um remédio B, e só vale se o **mesmo paciente também usa B**. O `a.id < b.id` evita mostrar o par duas vezes."

**Comparar pacientes** (trocar no seletor):
- **Carlos Vencido:** 1 alerta (Ibuprofeno × insuficiência renal). Ele usa Ibuprofeno e Metformina, e **não** aparece interação, porque a Varfarina e o AAS não são dele.
- **Beatriz Lima:** 1 alerta (Ibuprofeno × úlcera).

**Falar:** "Ibuprofeno interage com Varfarina e com AAS. Mas só gera alerta quando **o mesmo paciente** usa os dois. É a travessia respeitando o contexto de cada paciente."

---

## 6. Ao vivo: criar uma prescrição e ver o alerta nascer (2 min)

Esta é a demonstração mais forte: **mudar o dado, não a consulta**.

1. Seletor em **Carlos Vencido**: confirmar **1 alerta**.
2. Ir para a aba **Cadastrar**, cartão **Nova relação**:
   - Relação: **Paciente usa medicamento**
   - Origem: **Carlos Vencido (2)**
   - Destino: **Varfarina (m1)**
   - Observação: opcional → **Ligar**.
3. (Opcional) abrir **Bastidores do Neo4j** (botão no topo): mostra a chamada `POST /relacoes/prescricoes` e a resposta.
4. Voltar a **Riscos** com Carlos: agora **2 alertas**. Surgiu "**Varfarina e Ibuprofeno** estão em uso juntos e interagem".

**Falar:** "Não mudamos nenhuma consulta nem tabela. Criamos **uma ligação** e o risco apareceu, porque a Varfarina já interagia com o Ibuprofeno no grafo. É isso que o grafo faz bem: descobrir combinações que ninguém escreveu à mão."

**Para repetir a apresentação:** Cadastrar → **Limpar o grafo** → **Carregar demonstração**.

---

## 7. Cadastro de nós (30 s, só se sobrar tempo)

Na aba **Cadastrar**, cartão **Novo nó**: tipo *Medicamento*, código `m6`, nome "Medicamento X" → **Criar nó**. Mostrar que o nó aparece em **Rede** e que dá para ligá-lo (interação, contraindicação) com **Nova relação**. Os cadastros são `MERGE` (não duplicam).

---

## 8. Rede de contato / contágio (1,5 min)

**Falar:** "A mesma ideia serve para investigar contatos. Cada paciente tem contatos diretos, e a cadeia pode ter mais de um salto."

**No sistema:** aba **Riscos**, seção **Contatos diretos** de Ana: **Carlos Vencido**. (Aviso na tela: a consulta lista contatos, não conclui transmissão.)
Aba **Rede**: clicar em **Carlos** e mostrar que ele liga Ana e Beatriz.

**No Neo4j Browser:**

```cypher
// contatos diretos e indiretos (até 2 saltos) de Ana
MATCH path = (p:Paciente {id:'1'})-[:CONTATO_COM*1..2]-(q:Paciente)
WHERE q <> p
RETURN path
```

Resultado: **Carlos Vencido** (1 salto) e **Beatriz Lima** (2 saltos, via Carlos).

**Falar:** "`*1..2` significa 'de 1 a 2 saltos'. Para ir a 3 ou 4 saltos basta mudar o número. Em SQL cada salto é mais um JOIN da tabela de contatos com ela mesma."

**Bônus** (cruzando tipos de nó): quais profissionais atenderam alguém do círculo de Ana:

```cypher
MATCH (pr:Profissional)-[:ATENDE]->(q:Paciente)-[:CONTATO_COM*0..2]-(:Paciente {id:'1'})
RETURN DISTINCT pr.nome, q.nome
```

Resultado: Dra. Marina Costa (Ana e Beatriz) e Dr. Paulo Mendes (Carlos).

---

## 9. Neo4j Browser por dentro (2 min)

Já no **http://localhost:7474** (login na seção 2). Roteiro de consultas, na ordem:

| # | Comando | O que mostrar |
|---|---|---|
| 1 | `MATCH (n) RETURN labels(n)[0] AS tipo, count(*) AS qtd ORDER BY tipo` | Tabela com a contagem por tipo: 8 pacientes (3 da demonstração + importados), 5 medicamentos, 2 patologias, 2 profissionais |
| 2 | `MATCH ()-[r]->() RETURN type(r) AS relacao, count(*) AS qtd ORDER BY relacao` | As 7 relações e quantas existem de cada |
| 3 | `MATCH path = (p:Paciente {id:'1'})-[:USA]->(a:Medicamento)-[:INTERAGE_COM]-(b:Medicamento)<-[:USA]-(p) WHERE a.id < b.id RETURN path` | O **desenho do caminho** da interação: Ana → Varfarina ↔ AAS ← Ana (o triângulo) |
| 4 | `MATCH path = (p:Paciente {id:'1'})-[:USA]->(:Medicamento)<-[:ALERGICO_A]-(p) RETURN path` | O caminho da alergia (Ana, Penicilina) |
| 5 | `MATCH (p:Paciente)-[:USA]->(a:Medicamento)-[:CONTRAINDICADO_PARA]->(d:Patologia)<-[:TEM]-(p) RETURN p.nome, a.nome, d.nome ORDER BY p.nome` | **Todos** os pacientes com contraindicação de uma vez: Ana (AAS × úlcera), Beatriz (Ibuprofeno × úlcera), Carlos (Ibuprofeno × insuficiência renal) |
| 6 | `SHOW CONSTRAINTS` | As restrições de unicidade por tipo de nó (`paciente_id`, `medicamento_id`...) que a API cria ao subir |
| 7 | `PROFILE MATCH (p:Paciente {id:'1'})-[:USA]->(a:Medicamento)-[:INTERAGE_COM]-(b:Medicamento)<-[:USA]-(p) WHERE a.id < b.id RETURN a.nome, b.nome` | O **plano de execução**: aba "Plan" mostra os operadores e os `db hits` (neste grafo, **66 db hits**) |

**Falar sobre a consulta 5:** "A mesma pergunta, para o hospital inteiro, é a mesma consulta sem o filtro de paciente. Não existe uma 'tabela de riscos': eles são **calculados pela travessia**."

**Falar sobre o `PROFILE`:** "Ele mostra por onde o banco passou. O ponto de partida é uma busca pelo índice do paciente; daí em diante ele **segue ponteiros entre nós vizinhos**, sem varrer tabelas. Quanto maior o grafo, mais isso importa, porque o custo depende dos vizinhos visitados e não do tamanho total."

---

## 10. Grafo vs SQL (2 min)

Voltar ao sistema, aba **Grafo vs SQL**.

**Falar a pergunta:** "Este paciente toma remédios que interagem entre si?"

| Grafo (Cypher) | Relacional (SQL) |
|---|---|
| **1 caminho**: paciente → remédio → remédio interagente → o mesmo paciente | **4 junções**: `uso` ×2, `medicamento` ×2, `interacao` (nos dois sentidos) |
| A relação é um dado guardado e seguido direto | A relação precisa ser reconstruída por JOIN a cada consulta |

**Mostrar:** os dois códigos lado a lado (o SQL completo está em `grafo/comparacao.sql`).

**Argumentos para a conversa (corretos e seguros):**
1. **Legibilidade:** o Cypher descreve o desenho do caminho; o SQL descreve como juntar tabelas.
2. **Custo da travessia:** no grafo, seguir uma relação é seguir um ponteiro do nó para o vizinho. Em SQL, cada JOIN depende de índices e de combinar linhas.
3. **Profundidade:** perguntas de "quantos saltos" (contatos de contatos) crescem em JOINs no SQL e viram `*1..N` no Cypher.

**Seja honesto sobre a medição (importante para a nota):**
- O enunciado pede para **destacar a eficiência** em relação a buscas relacionais. O projeto **não mediu tempos**, e o material do grupo diz isso explicitamente.
- O que **dá para afirmar**: a diferença de forma (1 caminho × 4 junções) e o `PROFILE` mostrando o caminho percorrido.
- O que **não dá para afirmar**: "o grafo é X vezes mais rápido". Com 8 pacientes e 5 remédios, qualquer banco responde em milissegundos, e os tempos que a tela mostra (da ordem de 10 a 20 ms, mais altos na primeira chamada) **não** servem de prova.
- Como medir de forma justa: mesmo volume nos dois bancos (milhares de pacientes), índices equivalentes, confirmar resultados idênticos, aquecer, repetir e comparar **mediana e percentil 95**.

> **Sugestão:** se houver tempo antes de 27/11, vale implementar essa medição (gerar um volume grande no Neo4j e no SQL e cronometrar). É o único item do enunciado que hoje está explicado, mas não demonstrado com números. Dá para pedir isso depois.

---

## 11. Integração com o sistema (1 min)

**Falar:** "Este módulo é independente: tem a própria pasta, o próprio compose e o próprio banco, e entra no sistema pela porta 8082 e pelo `/health`."

**Mostrar:**
- Aba **Cadastrar → Importar pacientes do cadastro**: os pacientes vêm do **Tema 1** (PostgreSQL). O Tema 1 é o dono da identidade do paciente; no grafo guardamos só o `id` dele e o nome.
- Mensagem: "8 de 8 pacientes importados do cadastro".
- **Bastidores do Neo4j:** lista as chamadas feitas e o resultado de cada uma.

**Falar:** "O hospital tem vários bancos, cada um onde faz mais sentido: PostgreSQL para o cadastro e agendamento, Redis para a fila, MongoDB para o prontuário e Neo4j para os relacionamentos."

---

## 12. Contribuições e aprendizados (1 min)

**Contribuições** (confirmar com o grupo e ajustar nomes):
- Modelagem do grafo (4 tipos de nó, 7 relações) e API em FastAPI com consultas parametrizadas.
- Consultas de risco: interação cruzada, alergia, contraindicação e contatos.
- Modelo SQL equivalente (`comparacao.sql`) e roteiro de comparação.
- Integração ao sistema (interface, `/health`, importação de pacientes do cadastro).

**Aprendizados** (sugestões):
- Quando o problema é de **relacionamento**, o grafo descreve a pergunta quase como ela é falada.
- Cada banco tem o seu papel; a integração depende de uma **identidade comum** (o `paciente_id` do cadastro).
- Dados de saúde exigem cuidado: **dados fictícios**, sem substituir validação clínica, e uma base de conhecimento revisada por profissionais antes de uso real.

---

## 13. Cronograma sugerido

| Tempo | Parte | Tela |
|---|---|---|
| 0:00 | Abertura | Riscos |
| 1:00 | Modelo | Rede + Neo4j Browser (`MATCH (n) RETURN n`) |
| 2:30 | Riscos de um paciente (Ana, Carlos, Beatriz) | Riscos |
| 5:00 | Prescrição ao vivo (Carlos + Varfarina) | Cadastrar → Riscos |
| 7:00 | Contatos e rede de contágio | Rede + Neo4j Browser |
| 8:30 | Neo4j Browser por dentro (consultas 1 a 7, `PROFILE`) | Neo4j Browser |
| 10:30 | Grafo vs SQL | Grafo vs SQL |
| 12:00 | Integração, contribuições e aprendizados | Cadastrar (importar) |

Se faltar tempo, corte: a seção 7 (cadastro de nós), a consulta bônus da seção 8 e as consultas 4 a 6 da seção 9.

---

## 14. Perguntas prováveis e respostas

**"Por que grafo e não SQL para isso?"**
Porque a pergunta é sobre **caminhos** entre coisas (paciente → remédio → remédio) e a profundidade pode variar (contatos de contatos). No grafo a relação é guardada e seguida; no SQL é reconstruída com JOIN a cada consulta, e cada nível extra é mais um JOIN.

**"O grafo é mais rápido? Quanto?"**
Não medimos, então não afirmamos um número. Explicamos o motivo estrutural (seguir ponteiros contra juntar tabelas) e mostramos o `PROFILE`. Uma medição justa pede o mesmo volume e índices equivalentes nos dois bancos e mediana/p95.

**"Como o sistema sabe que dois remédios interagem?"**
Pela relação `INTERAGE_COM` cadastrada entre os dois. Os dados são **fictícios** e a base deve ser alimentada e revisada por profissionais. Não há doses, datas nem gravidade da interação.

**"O sistema impede a prescrição?"**
Não. Ele **identifica e mostra** os riscos; não bloqueia nem substitui validação clínica.

**"Dá para a interação ser nos dois sentidos?"**
A relação é gravada num sentido, mas a consulta a lê **sem direção** (`-[:INTERAGE_COM]-`), então vale para A→B e B→A. O `a.id < b.id` evita repetir o par.

**"E se eu cadastrar o mesmo paciente duas vezes?"**
Os cadastros usam `MERGE` e há restrição de unicidade por `id` em cada tipo de nó (`SHOW CONSTRAINTS`). O mesmo `id` não duplica.

**"Onde ficam os dados? Se reiniciar, perde?"**
No volume `neo4j-data` do Docker. Reiniciar os containers não apaga. `docker compose down -v` apaga.

**"Como isso se liga ao resto do hospital?"**
Pelo `paciente_id` do cadastro (Tema 1). A tela importa os pacientes de lá. Ligar as prescrições reais do prontuário (Tema 4) ao grafo é um passo futuro.

**"Segurança?"**
É uma demonstração: a senha do banco é de exemplo, não há autenticação na API e os dados são fictícios. Para uso real seriam necessários autenticação, autorização, auditoria e proteção de dados.

---

## 15. Plano B (se algo falhar)

| Problema | O que fazer |
|---|---|
| Aba **Interações** diz "fora do ar" | `python3 integracao/sistema.py subir grafo` e esperar uns 30 s (o Neo4j demora para iniciar). Conferir com `python3 integracao/sistema.py status` |
| Grafo vazio na tela | Cadastrar → **Carregar demonstração** |
| Neo4j Browser não conecta | Conferir a URL `bolt://localhost:7687`, usuário `neo4j`, senha `demonstracao123`. Se o navegador pedir "Connect", clicar em Connect de novo |
| Estado estranho depois de testar | Cadastrar → **Limpar o grafo** → **Carregar demonstração** |
| O sistema inteiro não abre | Mostrar o módulo direto: **http://localhost:8082** (mesma interface), e o Neo4j Browser em **http://localhost:7474** |
| Sem internet / sem navegador do app | Tudo roda local, nada depende da internet |

Comandos de apoio:

```bash
python3 integracao/sistema.py status                       # quem está no ar
cd grafo && docker compose up -d --build                    # sobe só o Tema 2 (API em :8082, Neo4j Browser em :7474)
docker compose logs --tail 30 neo4j                         # se o banco não sobe
```

---

## 16. Avisos finais

- Dados da demonstração são **fictícios**; os nomes de medicamentos e as interações servem para ilustrar o modelo, **não** são recomendação clínica.
- Os tempos mostrados na tela são de uma máquina local com poucos dados. Não use esses números como evidência de velocidade.
- Ensaiar uma vez do início ao fim, incluindo o "Limpar o grafo → Carregar demonstração", para saber o tempo real.
