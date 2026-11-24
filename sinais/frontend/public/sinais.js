const $ = (id) => document.getElementById(id);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const ESTADO = { normal: ["Normal", "gravado"], warning: ["Observação", "aviso"], critical: ["Crítico", "recusado"] };
let patients = [], selectedId = null, lastIds = null, polling = false, ultimaVista = "";

// ---- pacientes
function renderPatientList() {
  $("patient-list").innerHTML = patients.map((p) => `<button type="button" class="paciente-botao ${p.id === selectedId ? "sel" : ""}" data-id="${esc(p.id)}" aria-pressed="${p.id === selectedId}">
    <span class="ponto ${esc(p.status)}" title="${esc(ESTADO[p.status]?.[0])}"></span><span class="nome"><b>${esc(p.name)}</b><small>${esc(p.bed)}</small></span></button>`).join("");
}
function sinal(rotulo, valor, unidade, ruim) {
  return `<div class="sinal ${ruim ? "ruim" : ""}"><span>${rotulo}</span><b>${valor ?? "–"}</b><small>${unidade}</small></div>`;
}
function renderSelected() {
  const p = patients.find((x) => x.id === selectedId);
  if (!p) return;
  const [rot, selo] = ESTADO[p.status] || ["–", ""];
  $("patient-name").textContent = p.name; $("patient-bed").textContent = p.bed;
  $("pulse").className = `pulso ${p.status}`; $("pulse").setAttribute("aria-label", rot);
  $("patient-status").className = `selo ${selo}`; $("patient-status").textContent = rot;
  $("patient-vitals").innerHTML = p.observed_at
    ? sinal("Frequência cardíaca", p.hr, "bpm", p.hr > 120) + sinal("Saturação de O₂", p.spo2, "%", p.spo2 < 90) + sinal("Pressão arterial", `${p.bp_sys}/${p.bp_dia}`, "mmHg", p.bp_sys < 90)
    : '<p class="dica">Aguardando a primeira leitura…</p>';
}
let periodo = 15;
function painel(id, panelId, minutos) {
  // o parâmetro _r muda a cada recarga: força o Grafana a abrir de novo e descarta qualquer zoom feito no gráfico
  return `/grafana/d-solo/vitals-main/patient-overview?var-patient_id=${encodeURIComponent(id)}&panelId=${panelId}&kiosk&theme=light&refresh=5s&from=now-${minutos}m&to=now&_r=${Date.now()}`;
}
function carregarGraficos() {
  if (!selectedId) return;
  $("hr-frame").src = painel(selectedId, 1, periodo); $("bp-frame").src = painel(selectedId, 2, periodo);
  $("spo2-frame").src = painel(selectedId, 6, periodo); $("trend-frame").src = painel(selectedId, 7, Math.max(60, periodo));
}
function selectPatient(id) {
  selectedId = id;
  carregarGraficos();
  renderPatientList(); renderSelected();
}
$("periodo").addEventListener("change", () => { periodo = Number($("periodo").value); carregarGraficos(); });
$("restaurar").addEventListener("click", () => { periodo = 15; $("periodo").value = "15"; carregarGraficos(); });
function irParaPaciente(id) { document.querySelector("input[name=aba][value=monitor]").click(); selectPatient(id); window.scrollTo({ top: 0, behavior: "smooth" }); }
$("notification-list").addEventListener("click", (e) => { const a = e.target.closest("[data-paciente]"); if (a) irParaPaciente(a.dataset.paciente); });
$("notification-list").addEventListener("keydown", (e) => { const a = e.target.closest("[data-paciente]"); if (a && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); irParaPaciente(a.dataset.paciente); } });
$("patient-list").addEventListener("click", (e) => { const b = e.target.closest("[data-id]"); if (b) selectPatient(b.dataset.id); });

// ---- alertas
const quando = (s) => s < 60 ? `${s} s` : `${Math.floor(s / 60)} min ${s % 60} s`;
function renderAlertas(alerts) {
  $("conta-alertas").textContent = alerts.length || "";
  $("patient-count").textContent = `${patients.length} pacientes · ${alerts.length} ${alerts.length === 1 ? "alerta ativo" : "alertas ativos"}`;
  const faixa = $("alert-notifications"); faixa.hidden = alerts.length === 0;
  const ids = alerts.map((a) => a.alert_id).join(",");
  if (ids !== lastIds) {
    lastIds = ids;
    $("notification-heading").textContent = alerts.length ? `Alertas ativos (${alerts.length})` : "";
    $("notification-list").innerHTML = alerts.slice(0, 3).map((a) => `<div class="item-alerta clicavel" data-paciente="${esc(a.patient_id)}" role="button" tabindex="0"><span class="quem">${esc(a.patient_name)} · ${esc(a.bed)}</span><span>${esc(a.title)}: ${esc(a.description)}</span></div>`).join("") + (alerts.length > 3 ? `<div class="item-alerta">E mais ${alerts.length - 3} na aba Alertas.</div>` : "");
    $("alertas-vazio").hidden = alerts.length > 0; $("tab-alertas").hidden = alerts.length === 0;
    $("tab-alertas").querySelector("tbody").innerHTML = alerts.map((a) => `<tr><td class="forte">${esc(a.patient_name)}<span class="sub">${esc(a.bed)}</span></td>
      <td><span class="selo ${a.severity === "critical" ? "recusado" : "aviso"}">${a.severity === "critical" ? "Crítico" : "Observação"}</span> ${esc(a.title)}<span class="sub">${esc(a.description)}</span></td>
      <td>${esc(a.measured_value)} <span class="sub">limite ${esc(a.threshold)}</span></td><td>${quando(a.sustained_seconds)}</td></tr>`).join("");
  }
}

async function poll() {
  if (polling) return;
  polling = true;
  try {
    const [pr, ar] = await Promise.all([fetch("/api/v1/patients"), fetch("/api/v1/alerts")]);
    if (!pr.ok || !ar.ok) throw new Error("API");
    const ordem = { critical: 0, warning: 1, normal: 2 };
    patients = (await pr.json()).sort((a, b) => (ordem[a.status] ?? 3) - (ordem[b.status] ?? 3) || a.bed.localeCompare(b.bed));
    const alerts = await ar.json();
    $("offline-banner").hidden = true;
    if (!patients.some((p) => p.id === selectedId)) { if (patients[0]) selectPatient(patients[0].id); }
    else { renderPatientList(); renderSelected(); }
    renderAlertas(alerts);
  } catch { $("offline-banner").hidden = false; }
  finally { polling = false; }
}

// ---- banco por dentro (TimescaleDB)
const r1 = (v) => v == null ? "–" : (Math.round(Number(v) * 10) / 10).toLocaleString("pt-BR");
const hora = (iso) => iso ? new Date(iso).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }) : "–";
const COLUNAS_TEND = [["bucket", "Horário", hora], ["hr_avg", "FC média (bpm)", r1], ["spo2_avg", "SpO₂ média (%)", r1], ["bp_sys_avg", "PA sistólica", r1],
  ["spo2_moving_avg_5m", "SpO₂ média 5 min", r1], ["spo2_delta_1m", "Variação 1 min", r1], ["spo2_zscore_1h", "Desvio (z-score)", r1]];
const fmt = (n) => Number(n).toLocaleString("pt-BR");
const dh = (iso) => iso ? new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" }) : "–";
async function carregarBanco() {
  if ($("view-banco").hidden) return;
  let d, t = null;
  try { d = await (await fetch("/api/v1/db/estrutura")).json(); } catch { return; }
  try { const r = await fetch(`/api/v1/analytics/trends/${encodeURIComponent(selectedId || "patient_001")}?minutes=10`); t = r.ok ? await r.json() : null; } catch { /* sem tendência */ }
  const foto = JSON.stringify([d, t]); if (foto === ultimaVista) return; ultimaVista = foto;
  const vs = d.hypertables.find((h) => h.nome === "vital_signs");
  const linhasTend = Array.isArray(t) ? t : (t && (t.points || t.trends || t.rows)) || [];
  $("banco").innerHTML = `
    <dl class="cartao resumo" style="margin-bottom:16px"><div><dt>TimescaleDB</dt><dd>${esc(d.versao_timescaledb)}</dd></div>
      <div><dt>Leituras guardadas</dt><dd>${vs ? fmt(vs.linhas) : "–"}</dd></div><div><dt>Chunks (partições)</dt><dd>${vs ? vs.chunks : "–"}</dd></div>
      <div><dt>Entrando agora</dt><dd>${fmt(d.ingestao.ultimo_minuto)}<small class="dica"> /min</small></dd></div></dl>
    <article class="cartao bloco"><h2>vital_signs <span class="selo destaque sem-ponto">hypertable</span></h2>
      <p class="porque">Tabela de leituras (FC, SpO₂ e pressão) particionada automaticamente por tempo em <b>chunks diários</b>. Consultas por intervalo de tempo só tocam os chunks necessários, e apagar dados antigos é descartar chunks inteiros. A chave única (horário, paciente, dispositivo) torna a gravação idempotente: reenviar um lote não duplica.</p>
      <div class="fichas"><span class="selo sem-ponto">${vs ? esc(vs.tamanho) : "–"} em disco</span><span class="selo sem-ponto">de ${dh(d.ingestao.mais_antiga)} até ${dh(d.ingestao.mais_recente)}</span><span class="selo sem-ponto">${d.ingestao.pacientes_ativos} pacientes enviando</span></div>
      <span class="dica">Chunks mais recentes</span>
      <div class="fichas">${d.chunks.map((c) => `<span class="selo sem-ponto mono">${esc(c.nome)} · ${esc(c.inicio.slice(0, 10))}</span>`).join("")}</div></article>
    <article class="cartao bloco"><h2>Agregações contínuas <span class="selo gravado sem-ponto">calculadas pelo banco</span></h2>
      <p class="porque">Médias por minuto e por hora mantidas pelo próprio TimescaleDB, sem código de aplicação. Os gráficos e a análise de tendência leem estas agregações, não os milhões de leituras brutas.</p>
      <div class="fichas">${d.agregacoes.map((a) => `<span class="selo sem-ponto mono">${esc(a.nome)} ← ${esc(a.origem)}</span>`).join("")}</div></article>
    <article class="cartao"><div style="padding:18px 20px 0"><h2 style="font-size:1.0625rem">Políticas automáticas</h2><p class="porque" style="margin-top:6px">Retenção: dados brutos ficam 30 dias; as médias por minuto, 1 ano; as por hora, 5 anos.</p></div>
      <div class="tabela-rolagem"><table class="tabela"><thead><tr><th>Tipo</th><th>Tabela</th><th>O que faz</th><th>Roda a cada</th></tr></thead><tbody>
      ${d.politicas.map((p) => `<tr><td><span class="selo ${p.tipo === "retenção" ? "aviso" : "destaque"} sem-ponto">${esc(p.tipo)}</span></td><td class="mono">${esc(p.tabela)}</td><td>${esc(p.detalhe)}</td><td class="mono">${esc(p.roda_a_cada)}</td></tr>`).join("")}</tbody></table></div></article>
    ${linhasTend.length ? `<h2 class="subtitulo">Tendência (consulta analítica) <span class="dica">${esc(selectedId)} · últimos 10 minutos, vinda da agregação de 1 minuto</span></h2>
      <div class="cartao"><div class="tabela-rolagem"><table class="tabela"><thead><tr>${COLUNAS_TEND.map(([, r]) => `<th>${r}</th>`).join("")}</tr></thead><tbody>
      ${linhasTend.slice(-8).map((l) => `<tr>${COLUNAS_TEND.map(([k, , f]) => `<td class="mono">${esc(f ? f(l[k]) : l[k])}</td>`).join("")}</tr>`).join("")}</tbody></table></div>
      <p class="dica" style="padding:12px 20px">Média móvel, variação e z-score vêm de funções de janela sobre a agregação de 1 minuto. O resultado completo (13 campos) está em <code>/api/v1/analytics/trends/&lt;paciente&gt;</code>.</p></div>` : ""}`;
}

document.querySelectorAll("input[name=aba]").forEach((r) => r.addEventListener("change", () => {
  ["monitor", "alertas", "banco"].forEach((v) => { $(`view-${v}`).hidden = !(r.checked && r.value === v); });
  if (r.checked && r.value === "banco") { ultimaVista = ""; carregarBanco(); }
}));
function relogio() { $("clock").textContent = new Date().toLocaleTimeString("pt-BR"); }
poll(); relogio(); setInterval(poll, 5000); setInterval(relogio, 1000); setInterval(carregarBanco, 5000);
