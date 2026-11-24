const $ = (id) => document.getElementById(id);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const NOS = { pacientes: "Paciente", medicamentos: "Medicamento", patologias: "Patologia", profissionais: "Profissional" };
// [origem, destino, texto, tipo da relação no Neo4j, cor]
const REL = {
  prescricoes: ["Paciente", "Medicamento", "Paciente usa medicamento", "USA", "#64748B"],
  alergias: ["Paciente", "Medicamento", "Paciente é alérgico a medicamento", "ALERGICO_A", "#B42318"],
  diagnosticos: ["Paciente", "Patologia", "Paciente tem patologia", "TEM", "#B45309"],
  contraindicacoes: ["Medicamento", "Patologia", "Medicamento é contraindicado para patologia", "CONTRAINDICADO_PARA", "#DC2626"],
  interacoes: ["Medicamento", "Medicamento", "Medicamento interage com medicamento", "INTERAGE_COM", "#EA580C"],
  atendimentos: ["Profissional", "Paciente", "Profissional atende paciente", "ATENDE", "#94A3B8"],
  contatos: ["Paciente", "Paciente", "Paciente teve contato com paciente", "CONTATO_COM", "#0F766E"],
};
const COR_REL = Object.fromEntries(Object.values(REL).map((r) => [r[3], r[4]]));
let nos = [], arestas = [], selNo = null, eventos = 0, confirmaLimpar = null;

// ---- chamadas à API, registradas nos bastidores
// ---- detalhes de cada ação: clicar (ou Enter) num cartão abre o que o banco executou
const detalhesPorId = new Map(); let seqDetalhe = 0;
function ligarDetalhes() {
  const abrir = (el) => { const ev = detalhesPorId.get(el?.dataset.ev); if (ev) Detalhes.abrir(ev); };
  $("log").addEventListener("click", (e) => abrir(e.target.closest("[data-ev]")));
  $("log").addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { const c = e.target.closest("[data-ev]"); if (c) { e.preventDefault(); abrir(c); } } });
}

async function api(op, metodo, url, corpo) {
  const t0 = performance.now();
  let status = 0, dados = null, consultas = [];
  try {
    const r = await fetch(url, { method: metodo, headers: { "X-Log": "1", ...(corpo ? { "Content-Type": "application/json" } : {}) }, ...(corpo ? { body: JSON.stringify(corpo) } : {}) });
    status = r.status; dados = await r.json().catch(() => ({}));
    consultas = await Detalhes.decodificar(r.headers.get("X-DB-Log")) || [];
  } catch { dados = { detail: "API fora do ar" }; }
  const ok = status >= 200 && status < 300;
  registrar(op, ok, status, ok ? "" : (typeof dados.detail === "string" ? dados.detail : "Pedido recusado"), performance.now() - t0, { consultas, resposta: dados });
  return { ok, dados };
}
function registrar(op, ok, status, detalhe, ms, extra = {}) {
  const ev = { titulo: op, op, ok, status, ms, ...extra }, id = String(++seqDetalhe); detalhesPorId.set(id, ev);
  const li = document.createElement("li");
  li.className = `evento ${ok ? "ok" : "erro"} ${ev.consultas?.length ? "clicavel" : ""}`;
  if (ev.consultas?.length) { li.dataset.ev = id; li.tabIndex = 0; li.setAttribute("role", "button"); }
  li.innerHTML = `<div class="evento-topo"><span class="selo ${ok ? "gravado" : "recusado"}">${ok ? "executado" : "recusado"}</span><b>${status || "—"}</b><time>${new Date().toLocaleTimeString("pt-BR")}</time></div>
    <div><b>${esc(op)}</b> · ${Math.round(ms)} ms${detalhe ? ` · ${esc(detalhe)}` : ""}</div>${Detalhes.rodape(ev)}`;
  $("log").querySelector(".vazio")?.remove();
  $("log").prepend(li);
  while ($("log").children.length > 20) $("log").lastChild.remove();
  $("conta-eventos").textContent = ++eventos;
}
function mensagem(texto, erro) {
  const m = $("msg"); m.hidden = false; m.textContent = texto; m.classList.toggle("erro", !!erro);
  clearTimeout(window.__msg); window.__msg = setTimeout(() => { m.hidden = true; }, 7000);
}

// ---- dados do grafo
async function carregar() {
  const r = await api("GET /grafo", "GET", "/grafo");
  if (!r.ok) return;
  nos = r.dados.nos; arestas = r.dados.arestas;
  preencherPacientes(); preencherRelacao(); desenharRede();
  if (!$("view-riscos").hidden) analisar();
}
const porTipo = (t) => nos.filter((n) => n.tipo === t);

function preencherPacientes() {
  const atual = $("sel-paciente").value, ps = porTipo("Paciente");
  $("sel-paciente").innerHTML = ps.length ? ps.map((p) => `<option value="${esc(p.id)}">${esc(p.nome)} (${esc(p.id)})</option>`).join("") : '<option value="">Nenhum paciente no grafo</option>';
  if (atual && ps.some((p) => p.id === atual)) $("sel-paciente").value = atual;
}

// ---- riscos
const GRUPOS = [
  ["interacoes", "Interação entre medicamentos", "aviso", (r) => `<b>${esc(r.medicamento)}</b> e <b>${esc(r.relacionado)}</b> estão em uso juntos e interagem.`],
  ["alergias", "Alergia", "recusado", (r) => `Alérgico a <b>${esc(r.medicamento)}</b>, que está em uso.`],
  ["contraindicacoes", "Contraindicação", "recusado", (r) => `<b>${esc(r.medicamento)}</b> é contraindicado para <b>${esc(r.patologia)}</b>, que o paciente tem.`],
  ["contatos", "Contatos diretos", "destaque", (r) => `<b>${esc(r.nome)}</b> <span class="obs">(código ${esc(r.id)})</span>`],
];
const consulta = (c) => `<details class="ver-consulta"><summary>Ver como o grafo respondeu · ${c.tempo_ms} ms</summary><pre class="codigo">${esc(c.cypher)}</pre></details>`;
async function analisar() {
  const id = $("sel-paciente").value;
  if (!nos.length) {
    $("riscos").innerHTML = '<div class="cartao estado-vazio"><strong>O grafo está vazio</strong><span>Carregue a demonstração ou importe os pacientes do cadastro.</span><button class="botao primario" type="button" id="demo-vazio">Carregar demonstração</button></div>';
    $("resumo-risco").textContent = ""; return;
  }
  if (!id) { $("riscos").innerHTML = '<div class="cartao estado-vazio"><strong>Nenhum paciente no grafo</strong><span>Importe os pacientes do cadastro na aba Cadastrar.</span></div>'; return; }
  const r = await api(`GET /pacientes/${id}/analise`, "GET", `/pacientes/${encodeURIComponent(id)}/analise`);
  if (!r.ok || id !== $("sel-paciente").value) return;
  const d = r.dados, alertas = d.interacoes.length + d.alergias.length + d.contraindicacoes.length;
  $("resumo-risco").textContent = "";
  const nome = nos.find((n) => n.tipo === "Paciente" && n.id === id)?.nome || id;
  const cartoes = GRUPOS.slice(0, 3).map(([k, titulo, selo, fmt], i) => d[k].length ? `<article class="cartao grupo-risco"><header><span class="selo ${selo} sem-ponto">${esc(titulo)}</span><span class="n">${d[k].length}</span></header>
      ${d[k].map((x) => `<div class="risco">${fmt(x)}</div>`).join("")}${consulta(d.consultas[i])}</article>` : "").join("");
  const sem = GRUPOS.slice(0, 3).filter(([k]) => !d[k].length).map((g) => g[1].toLowerCase());
  const contatos = d.contatos;
  $("riscos").innerHTML = `<div class="manchete ${alertas ? "com-alertas" : "ok"}"><b>${esc(nome)}</b> ${alertas ? `tem <b>${alertas} ${alertas === 1 ? "alerta" : "alertas"}</b> nos remédios em uso.` : "não tem nenhum alerta nos remédios em uso."}</div>
    ${cartoes ? `<div class="grupos">${cartoes}</div>` : ""}
    ${sem.length && alertas ? `<p class="dica sem">Sem: ${sem.join(", ")}.</p>` : ""}
    <h2 class="subtitulo">Contatos diretos <span class="dica">pessoas ligadas a este paciente (não indica transmissão)</span></h2>
    <div class="cartao grupo-risco">${contatos.length ? contatos.map((x) => `<div class="risco">${GRUPOS[3][3](x)}</div>`).join("") : '<div class="risco ok">Nenhum contato registrado.</div>'}${consulta(d.consultas[3])}</div>`;
}

// ---- rede (colunas por tipo; arestas coloridas por relação)
function desenharRede() {
  $("legenda-rede").innerHTML = Object.values(REL).map((r) => `<span><i style="border-color:${r[4]}"></i>${r[3]}</span>`).join("");
  if (!nos.length) { $("rede").innerHTML = '<div class="estado-vazio"><strong>O grafo está vazio</strong><span>Carregue a demonstração na aba Cadastrar.</span></div>'; return; }
  const cols = ["Profissional", "Paciente", "Medicamento", "Patologia"], X = { Profissional: 100, Paciente: 340, Medicamento: 610, Patologia: 865 };
  const W = 960, NW = 150, NH = 30, DY = 44, TOPO = 52;
  const linhas = Math.max(...cols.map((c) => porTipo(c).length), 1), H = linhas * DY + TOPO + 16;
  const pos = {};
  cols.forEach((c) => porTipo(c).forEach((n, i) => { pos[`${c}:${n.id}`] = { x: X[c], y: TOPO + i * DY, tipo: c, n }; }));
  const vizinhos = new Set();
  if (selNo) arestas.forEach((a) => { const o = `${a.de_tipo}:${a.de}`, d = `${a.para_tipo}:${a.para}`; if (o === selNo) vizinhos.add(d); if (d === selNo) vizinhos.add(o); });
  const arestasSvg = arestas.map((a) => {
    const o = pos[`${a.de_tipo}:${a.de}`], d = pos[`${a.para_tipo}:${a.para}`]; if (!o || !d) return "";
    let path;
    if (o.x === d.x) { // mesma coluna: arco para o lado
      const lado = o.tipo === "Paciente" ? -1 : 1, x = o.x + lado * NW / 2, off = lado * 70;
      path = `M${x},${o.y} C${x + off},${o.y} ${x + off},${d.y} ${x},${d.y}`;
    } else {
      const dir = o.x < d.x ? 1 : -1, x1 = o.x + dir * NW / 2, x2 = d.x - dir * NW / 2, m = (x1 + x2) / 2;
      path = `M${x1},${o.y} C${m},${o.y} ${m},${d.y} ${x2},${d.y}`;
    }
    const toca = selNo && (`${a.de_tipo}:${a.de}` === selNo || `${a.para_tipo}:${a.para}` === selNo);
    return `<path class="aresta ${selNo && !toca ? "apagada" : ""}" d="${path}" stroke="${COR_REL[a.relacao] || "#999"}" ${a.relacao === "CONTRAINDICADO_PARA" ? 'stroke-dasharray="6 4"' : ""}><title>${esc(a.de)} ${esc(a.relacao)} ${esc(a.para)}${a.observacao ? " · " + esc(a.observacao) : ""}</title></path>`;
  }).join("");
  const nosSvg = Object.entries(pos).map(([k, p]) => {
    const apagado = selNo && k !== selNo && !vizinhos.has(k);
    const nome = p.n.nome.length > 20 ? p.n.nome.slice(0, 19) + "…" : p.n.nome;
    return `<g class="no-g t-${p.tipo} ${k === selNo ? "sel" : ""} ${apagado ? "apagado" : ""}" data-no="${esc(k)}" transform="translate(${p.x - NW / 2},${p.y - NH / 2})"><rect width="${NW}" height="${NH}" rx="8"/><text x="${NW / 2}" y="${NH / 2 + 4}" text-anchor="middle">${esc(nome)}</text><title>${esc(p.tipo)} · ${esc(p.n.nome)} (${esc(p.n.id)})</title></g>`;
  }).join("");
  const titulos = cols.map((c) => `<text class="col-titulo" x="${X[c]}" y="20" text-anchor="middle">${c}s</text>`).join("");
  $("rede").innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Rede de nós e relações">${titulos}${arestasSvg}${nosSvg}</svg>`;
  const info = selNo && pos[selNo];
  $("rede-info").textContent = info ? `${info.tipo}: ${info.n.nome} · ${vizinhos.size} ${vizinhos.size === 1 ? "ligação" : "ligações"} diretas` : "Clique num nó para destacar as ligações dele.";
}

// ---- cadastro de nós e relações
function preencherRelacao() {
  const [o, d] = REL[$("rel-tipo").value] || REL.prescricoes;
  const opts = (t) => porTipo(t).map((n) => `<option value="${esc(n.id)}">${esc(n.nome)} (${esc(n.id)})</option>`).join("") || '<option value="">Nenhum nó deste tipo</option>';
  const to = $("rel-origem").value, td = $("rel-destino").value;
  $("rel-origem").innerHTML = opts(o); $("rel-destino").innerHTML = opts(d);
  if (porTipo(o).some((n) => n.id === to)) $("rel-origem").value = to;
  if (porTipo(d).some((n) => n.id === td)) $("rel-destino").value = td;
}
$("rel-tipo").addEventListener("change", preencherRelacao);
$("form-no").addEventListener("submit", async (e) => {
  e.preventDefault();
  const tipo = $("no-tipo").value, id = $("no-id").value.trim(), nome = $("no-nome").value.trim();
  const r = await api(`POST /nos/${tipo}`, "POST", `/nos/${tipo}`, { id, nome });
  mensagem(r.ok ? `${NOS[tipo]} "${nome}" salvo.` : "Não foi possível criar o nó.", !r.ok);
  if (r.ok) { $("no-id").value = ""; $("no-nome").value = ""; carregar(); }
});
$("form-rel").addEventListener("submit", async (e) => {
  e.preventDefault();
  const tipo = $("rel-tipo").value, origem = $("rel-origem").value, destino = $("rel-destino").value;
  if (!origem || !destino) return mensagem("Escolha origem e destino (crie os nós antes).", true);
  const r = await api(`POST /relacoes/${tipo}`, "POST", `/relacoes/${tipo}`, { origem, destino, observacao: $("rel-obs").value });
  mensagem(r.ok ? "Relação criada." : "Não foi possível criar a relação.", !r.ok);
  if (r.ok) { $("rel-obs").value = ""; carregar(); }
});
async function demo() {
  const r = await api("POST /demonstracao/completa", "POST", "/demonstracao/completa");
  mensagem(r.ok ? `Demonstração carregada: ${r.dados.nos} nós e ${r.dados.relacoes} relações.` : "Falha ao carregar a demonstração.", !r.ok);
  if (r.ok) carregar();
}
$("demo").addEventListener("click", demo);
document.addEventListener("click", (e) => { if (e.target.id === "demo-vazio") demo(); });
$("limpar").addEventListener("click", async () => {
  if (!confirmaLimpar) {
    $("limpar").textContent = "Confirmar? Apaga todo o grafo";
    confirmaLimpar = setTimeout(() => { confirmaLimpar = null; $("limpar").textContent = "Limpar o grafo"; }, 4000);
    return;
  }
  clearTimeout(confirmaLimpar); confirmaLimpar = null; $("limpar").textContent = "Limpar o grafo";
  const r = await api("DELETE /grafo", "DELETE", "/grafo");
  mensagem(r.ok ? "Grafo limpo." : "Não foi possível limpar.", !r.ok);
  selNo = null; carregar();
});

// ---- integração com o cadastro (Tema 1): ele é o dono da identidade do paciente
function urlCadastro() {
  const h = location.hostname, porta = location.port ? ":" + location.port : "";
  return h.startsWith("grafo.") ? `${location.protocol}//cadastro.${h.slice(6)}${porta}` : `${location.protocol}//cadastro.localhost:8000`;
}
$("importar").addEventListener("click", async () => {
  let ps;
  try { ps = await (await fetch(`${urlCadastro()}/pacientes`)).json(); } catch { return mensagem("Cadastro do Tema 1 indisponível.", true); }
  let ok = 0;
  for (const p of ps) { const r = await api(`POST /nos/pacientes (cadastro #${p.id})`, "POST", "/nos/pacientes", { id: String(p.id), nome: p.nome }); if (r.ok) ok++; }
  mensagem(`${ok} de ${ps.length} pacientes importados do cadastro (o código no grafo é o id do cadastro).`, ok !== ps.length);
  carregar();
});

// ---- abas, bastidores, rede
document.querySelectorAll("input[name=aba]").forEach((r) => r.addEventListener("change", () => {
  ["riscos", "rede", "cadastrar", "sql"].forEach((v) => { $(`view-${v}`).hidden = !(r.checked && r.value === v); });
  if (r.checked && r.value === "riscos") analisar();
}));
$("abrir-bastidores").addEventListener("click", () => { $("bastidores").hidden = !$("bastidores").hidden; });
$("fechar-bastidores").addEventListener("click", () => { $("bastidores").hidden = true; $("abrir-bastidores").focus(); });
$("sel-paciente").addEventListener("change", analisar);
$("rede").addEventListener("click", (e) => {
  const g = e.target.closest("[data-no]"); selNo = g && g.dataset.no !== selNo ? g.dataset.no : null; desenharRede();
});

$("no-tipo").innerHTML = Object.entries(NOS).map(([k, v]) => `<option value="${k}">${v}</option>`).join("");
$("rel-tipo").innerHTML = Object.entries(REL).map(([k, r]) => `<option value="${k}">${r[2]}</option>`).join("");
$("sql-interacao").textContent = `SELECT DISTINCT a.nome, b.nome, i.observacao
FROM uso u1
JOIN uso u2
  ON u2.paciente_id = u1.paciente_id
 AND u1.medicamento_id < u2.medicamento_id
JOIN medicamento a ON a.id = u1.medicamento_id
JOIN medicamento b ON b.id = u2.medicamento_id
JOIN interacao i
  ON (i.medicamento_a = a.id AND i.medicamento_b = b.id)
  OR (i.medicamento_a = b.id AND i.medicamento_b = a.id)
WHERE u1.paciente_id = ?;`;
$("cy-interacao").textContent = `MATCH (p:Paciente {id: $id})
      -[:USA]->(a:Medicamento)
      -[:INTERAGE_COM]-(b:Medicamento)
      <-[:USA]-(p)
WHERE a.id < b.id
RETURN a.nome, b.nome`;
carregar();
ligarDetalhes();
