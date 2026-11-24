# Como plugar o seu módulo no sistema

Cada tema é um **módulo independente**: tem a própria pasta, o próprio `docker-compose.yml`, o próprio banco e a
própria porta. Um **gateway** (Nginx, porta 8000) reúne todos e dá um endereço para cada um. Você não precisa mudar
nada no código dos outros temas, e eles não precisam mudar nada no seu.

| Tema | Pasta | Porta | Endereço pelo gateway | Banco |
|---|---|---|---|---|
| 1 Cadastro e Agendamentos | `cadastro/` | 8081 | `cadastro.localhost:8000` | PostgreSQL |
| 2 Interações Medicamentosas | `grafo/` | 8082 | `grafo.localhost:8000` | grafos |
| 3 Triagem e Leitos | `emergencia/` | 8080 | `triagem.localhost:8000` | Redis |
| 4 Prontuário (PEP) | `prontuario/` | 8084 | `prontuario.localhost:8000` | documentos |
| 5 Sinais Vitais | `sinais/` | 8085 | `sinais.localhost:8000` | série temporal |

A tabela vem de [`modulos.json`](../modulos.json), que é a fonte única. Se precisar de outra porta ou pasta, mude lá
e rode `python3 integracao/sistema.py gerar`.

## O contrato (só 4 regras)

1. **Pasta e compose.** Seu módulo mora na pasta da tabela, com um `docker-compose.yml` que sobe tudo (aplicação e banco).
2. **Porta.** A aplicação (ou o Nginx na frente dela) publica **a porta da tabela** no computador.
3. **`/health`.** `GET /health` responde `200`. É isso que faz o módulo aparecer "No ar" no hub.
4. **Raiz.** Sua interface e sua API funcionam servidas na raiz `/`, como já fazem hoje. O gateway não usa prefixo
   de rota (por isso cada módulo ganha um subdomínio): nada precisa mudar nos seus caminhos.

Para começar do zero, copie [`modelo-modulo/`](modelo-modulo/) para a sua pasta. Ele já cumpre as 4 regras: é só trocar
o serviço `web` pela sua aplicação e o seu banco.

## Aparência: o kit de estilo (recomendado)

O sistema é mostrado numa aplicação só (o **shell**, em `localhost:8000`), que abre cada módulo numa aba. Para as telas
parecerem do mesmo sistema, use o kit em [`kit/`](kit/):

1. Copie `kit/kit.css`, `kit/embed.js` e `kit/fonts/` para a pasta estática do seu módulo.
2. Importe `kit.css` e `embed.js` na sua página. O kit traz cores, fonte, botões, campos, tabelas, selos e cartões.
3. Dentro do shell, o módulo abre com `?embed=1` e `embed.js` marca `<html class="embed">`. Esconda o que o shell já mostra
   (a marca/logo, por exemplo) com `.embed ...`.
4. Se a tela principal não for a raiz `/`, diga qual em `modulos.json` (campo `entrada`, por exemplo `"/operacao"`).

O Tema 1 (`cadastro/`) e a tela de operação do Tema 3 (`emergencia/api/static/operacao.html`) são exemplos prontos.

## Bastidores: o que o banco executou (opcional)

Quem tem um painel "Bastidores" pode mostrar, num modal ao clicar na ação, os comandos que o banco recebeu (SQL, Cypher, MongoDB ou Redis):

1. O navegador manda `X-Log: 1` na requisição.
2. A API registra os comandos daquela requisição e devolve no cabeçalho `X-DB-Log` (JSON comprimido com zlib e em base64). Exemplos prontos:
   `dblog.py` + `db.py` no Tema 1 (asyncpg), `grafo/main.py` (Neo4j), `prontuario/api/main.py` (MongoDB) e `emergencia/api/main.py` (Redis).
3. A interface usa `detalhes.js` do kit: `Detalhes.decodificar(resposta.headers.get("X-DB-Log"))` e `Detalhes.abrir(evento)`.
4. Se houver nginx na frente da API, aumente `proxy_buffer_size` (o cabeçalho pode passar de 4 KB).

## Identidade do paciente: quem é o dono

O **Tema 1 é o dono do cadastro de pacientes e médicos**. Os outros temas guardam **só o `paciente_id`** (número
inteiro) e buscam o resto na API do Tema 1. Assim o paciente é o mesmo em todos os bancos.

| O que você precisa | Chamada |
|---|---|
| Dados de um paciente | `GET /pacientes/{id}` |
| Procurar por nome | `GET /pacientes?nome=ana` |
| Lista de médicos (com especialidade) | `GET /medicos` |
| Planos e convênios | `GET /convenios` |

**Do servidor de vocês (container para container):** use `http://host.docker.internal:8081`. No `docker-compose.yml`
do seu serviço, acrescente:

```yaml
    extra_hosts:
      - "host.docker.internal:host-gateway"
```

**Do navegador (a interface de vocês chamando o Tema 1):** use `http://cadastro.localhost:8000`. O Tema 1 já aceita
pedidos de qualquer endereço `*.localhost`, e só desses (CORS).

Exemplo, na interface do seu módulo:

```js
const r = await fetch("http://cadastro.localhost:8000/pacientes/1");
const paciente = await r.json();   // { id: 1, nome: "Ana Souza", cpf: "...", plano_id: 1, ... }
```

Para registrar quem fez uma alteração na auditoria do Tema 1, envie o cabeçalho `X-Usuario`.

## Comandos

```bash
python3 integracao/sistema.py subir            # sobe todos os módulos que já têm pasta, e o gateway
python3 integracao/sistema.py subir grafo      # sobe só o seu módulo (e o gateway)
python3 integracao/sistema.py status           # quem está no ar
python3 integracao/sistema.py parar            # derruba tudo (não apaga os dados)
```

Abra **http://localhost:8000** para ver o hub, com o estado de cada módulo atualizado a cada 4 segundos.
Módulo que não está no ar mostra um aviso no próprio endereço dele, em vez de quebrar.

## Problemas comuns

- **"Fora do ar" no hub, mas o módulo está rodando.** Confira a porta publicada e se `GET /health` devolve 200 (teste com
  `curl localhost:PORTA/health`).
- **`xxx.localhost` não abre.** Chrome e Firefox resolvem sozinhos. No `curl`, use
  `curl -H "Host: grafo.localhost" localhost:8000/`.
- **Porta ocupada.** Outro programa usa a porta da tabela. Pare-o ou combine outra porta e mude `modulos.json`.
- **Seu container não alcança o Tema 1.** Faltou o `extra_hosts` acima.
- **Nomes de serviço repetidos.** Não é problema: cada módulo roda no próprio compose, então `api`, `redis` e `web`
  podem se repetir entre temas.
