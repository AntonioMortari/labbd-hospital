# Monitoramento de sinais vitais

Protótipo local de monitoramento contínuo para dezenas de pacientes. A stack usa
FastAPI, TimescaleDB, Grafana, nginx e um simulador de monitores. A ingestão é
feita por lotes, as leituras ficam em uma hypertable e os alertas persistidos
aparecem como notificações no topo da interface.

> **Uso de demonstração:** os pacientes e sinais vitais são sintéticos. Este
> projeto não substitui dispositivos médicos, avaliação clínica ou validação
> regulatória.

> **Integração ao sistema hospitalar:** este módulo é o **Tema 5** do sistema. Para não colidir com os outros temas, as portas
> foram deslocadas: interface em **http://localhost:8085** (ou pela aba **Sinais vitais** de http://localhost:8000), API em `8086`,
> TimescaleDB em `5435` e Grafana em `3001`. A interface usa o mesmo estilo dos outros módulos e tem a aba **Banco por dentro**
> (hypertable, chunks, agregações contínuas e políticas de retenção, lidos do TimescaleDB). Os comandos abaixo, de PowerShell,
> valem no Linux com `cp .env.example .env`. Os exemplos com `localhost:8080` e `:3000` usam hoje `8085` e `3001`.

## Arquitetura

```text
Monitores / simulador
        │ POST /api/v1/readings (lotes)
        ▼
FastAPI ───────────────► TimescaleDB
  │                       ├─ vital_signs (hypertable)
  │                       ├─ agregações contínuas 1 min / 1 hora
  │                       └─ pacientes, dispositivos e alertas
  ├─ worker periódico ──► webhook opcional
  └─ API de pacientes, alertas e tendências
        ▲
Frontend nginx ──────────┤
        └───────────────► Grafana (consultas SQL)
```

## Executar localmente

Requisitos: Docker Desktop com Docker Compose v2.

```powershell
if (!(Test-Path .env)) { Copy-Item .env.example .env }
# Edite .env e troque as senhas locais antes de expor qualquer porta.
docker compose up -d --build
```

Abra `http://localhost:8080`. A documentação interativa da API fica em
`http://localhost:8080/api/docs`; o Grafana em `http://localhost:3000`.
Credenciais locais são configuradas por `GRAFANA_ADMIN_USER` e
`GRAFANA_ADMIN_PASSWORD`.

Para parar sem apagar os dados:

```powershell
docker compose down
```

Os dados do TimescaleDB e do Grafana ficam em volumes nomeados. **Não use
`docker compose down -v`** se quiser preservá-los.

## Modelo de dados e retenção

As migrations SQL versionadas ficam em `backend/migrations/` e são aplicadas
automaticamente na inicialização:

- `patients`: pacientes sintéticos e leito.
- `devices`: monitores associados a cada paciente.
- `vital_signs`: horário com fuso, paciente, dispositivo, FC (`hr`), SpO₂,
  pressão sistólica (`bp_sys`) e diastólica (`bp_dia`).
- `alerts`: histórico de alertas, incluindo início, última leitura e resolução.

`vital_signs` é uma hypertable particionada por `observed_at`, em chunks diários.
Índices por paciente/tempo e dispositivo/tempo aceleram consultas. A chave
única `(observed_at, patient_id, device_id)` dá idempotência às gravações.

Políticas automáticas do TimescaleDB:

| Dados | Agregação | Retenção |
|---|---:|---:|
| Leituras brutas | por segundo | 30 dias |
| `vital_signs_1m` | média por minuto | 365 dias |
| `vital_signs_1h` | média por hora | 5 anos |

As agregações contínuas são atualizadas pelo banco. Para alterar a retenção,
crie uma nova migration SQL versionada e ajuste as políticas correspondentes.

## Ingestão em lote

O endpoint aceita até 5.000 leituras por requisição. Ele valida intervalos,
fuso horário, vínculo paciente/dispositivo e grava os registros via `COPY` para
uma tabela temporária, inserindo no hypertable em uma transação. Chaves
repetidas são ignoradas; valores conflitantes para a mesma chave no mesmo lote
retornam `409`.

```bash
curl -X POST http://localhost:8080/api/v1/readings \
  -H "Content-Type: application/json" \
  -d '{
    "readings": [{
      "observed_at": "2026-11-23T20:30:00Z",
      "patient_id": "patient_001",
      "device_id": "monitor_patient_001",
      "hr": 82,
      "spo2": 97,
      "bp_sys": 120,
      "bp_dia": 78
    }]
  }'
```

Resposta: `{"accepted":1,"duplicates":0,"received":1}`. O endpoint direto também
fica disponível em `http://localhost:8000/api/v1/readings`. Os limites máximos
por sinal e o tamanho máximo do lote estão definidos em `backend/app/schemas.py`.

## Dados externos para demonstração

Por padrão, a demonstração usa nomes brasileiros sintéticos locais, para manter
uma identificação natural e consistente entre reinicializações. A integração
com a API pública [RandomUser](https://randomuser.me/documentation) continua
disponível como opção: defina `RANDOMUSER_ENABLED=true` para importar somente
nomes sintéticos. Ela não pede email, endereço, telefone ou identificadores e
nunca recebe dados do sistema. As métricas continuam sendo geradas pelo
simulador.

Controle a integração com `RANDOMUSER_ENABLED` e `RANDOMUSER_API_URL` no `.env`.

## Consultas analíticas

```bash
curl "http://localhost:8080/api/v1/analytics/trends/patient_001?minutes=60"
```

A consulta usa a agregação de um minuto e retorna média móvel de SpO₂ de 5
minutos, delta em relação ao minuto anterior, z-score de 1 hora e inclinação de
regressão linear. Pacientes desconhecidos retornam `404`.

O Grafana também consulta o TimescaleDB diretamente. A dashboard contém
frequência cardíaca, pressão sistólica/diastólica, SpO₂ e sua média móvel, com
legendas por extenso. As bolinhas ao lado dos pacientes refletem o estado atual
dos alertas.

## Alertas e notificações

O worker avalia as leituras a cada `ALERT_POLL_SECONDS` e só abre um alerta
quando a condição persiste pelo intervalo configurado:

| Regra | Padrão | Variável |
|---|---:|---|
| SpO₂ abaixo de 90% | 30 s | `SPO2_ALERT_SECONDS` |
| FC acima de 120 bpm | 60 s | `HEART_RATE_ALERT_SECONDS` |
| Pressão sistólica abaixo de 90 mmHg | 60 s | `HYPOTENSION_ALERT_SECONDS` |

Os alertas ativos são idempotentes, ficam gravados em `alerts` e são resolvidos
quando a condição deixa de persistir. A interface os mostra em notificações no
topo; o painel/tabela antigo de alertas foi removido.

Para encaminhar novos alertas a um webhook, configure `ALERT_WEBHOOK_URL`. O
backend envia um `POST` JSON com `event: "vital_alert"` e os dados do alerta.
Falhas de entrega são registradas em log estruturado; o alerta permanece
armazenado e visível na interface.

## Testes

```bash
docker compose exec api pytest -q
./verify.sh
```

`verify.sh` também testa a criação de um alerta de SpO₂ sustentada usando um
paciente temporário e remove os dados de teste ao terminar. Se
`ALERT_WEBHOOK_URL` estiver configurada, essa verificação é ignorada para não
enviar um alerta sintético ao webhook.

O teste de carga gera um milhão de pontos por padrão, distribuídos pelos
pacientes cadastrados, com lotes e concorrência configuráveis:

```bash
docker compose exec api python -m app.load_test \
  --points 1000000 --batch-size 2000 --workers 4
```

A saída informa quantidade aceita, pontos por segundo, latência mediana por
lote e latência da consulta de tendências. Para uma execução rápida, use
`--points 10000`.

## Configuração

As opções de conexão, pool, webhook, API externa, intervalos do worker e ritmo
do simulador são carregadas de variáveis de ambiente. Consulte `.env.example`.
O Compose tem senhas padrão **somente para desenvolvimento local**; substitua
ambas as senhas antes de disponibilizar o sistema fora da máquina local.
