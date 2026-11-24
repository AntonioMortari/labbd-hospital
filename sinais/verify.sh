#!/usr/bin/env sh
set -eu

check() {
  description="$1"
  shift
  "$@"
  printf '✅ %s\n' "$description"
}

BASE_URL="http://localhost:${FRONTEND_PORT:-8085}"
GRAFANA_URL="http://localhost:${GRAFANA_PORT:-3001}"
GRAFANA_USER=$(docker exec vitals_grafana printenv GF_SECURITY_ADMIN_USER)
GRAFANA_PASSWORD=$(docker exec vitals_grafana printenv GF_SECURITY_ADMIN_PASSWORD)
export BASE_URL GRAFANA_URL GRAFANA_USER GRAFANA_PASSWORD

check "5 serviços principais em execução" sh -c 'count=$(docker compose ps --status running --services | wc -l); test "$count" -ge 5'
check "API saudável pelo proxy do frontend" sh -c 'curl -fsS "$BASE_URL/health" | grep -q "\"status\":\"ok\""'
check "Grafana saudável" sh -c 'curl -fsS "$GRAFANA_URL/api/health" | grep -q "\"database\": \"ok\""'
check "Frontend e notificações carregados" sh -c 'curl -fsS "$BASE_URL/" | grep -q "alert-notifications"'
check "Painel legado de alertas removido" sh -c '! curl -fsS "$BASE_URL/" | grep -q "PAINEL DE ALERTAS"'
check "Dashboard Grafana publicado" sh -c 'curl -fsS -u "$GRAFANA_USER:$GRAFANA_PASSWORD" "$GRAFANA_URL/api/dashboards/uid/vitals-main" | grep -q "Monitoramento de sinais vitais"'
check "Datasource TimescaleDB publicado" sh -c 'curl -fsS -u "$GRAFANA_USER:$GRAFANA_PASSWORD" "$GRAFANA_URL/api/datasources" | grep -q "TimescaleDB-Vitals"'
check "Modelo, ingestão idempotente e API analítica" docker compose exec -T api python -m app.verify_stack

printf '🎉 SISTEMA OK\n'
