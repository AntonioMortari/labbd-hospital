const $ = (id) => document.getElementById(id);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const TZ = "America/Sao_Paulo";
const quando = (iso) => new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short", timeZone: TZ });
let lista = [], pacientes = {}, medicos = {}, doc = null, eventos = 0, ultimoResp = "", acaoAtual = null;

// ---- cadastro do Tema 1 (dono da identidade de pacientes e médicos)
function urlCadastro() {
  const h = location.hostname, porta = location.port ? ":" + location.port : "";
  return h.startsWith("prontuario.") ? `${location.protocol}//cadastro.${h.slice(11)}${porta}` : `${location.protocol}//cadastro.localhost:8000`;
}
async function carregarCadastro() {
  try {
    const [ps, ms] = await Promise.all(["/pacientes", "/medicos"].map((u) => fetch(urlCadastro() + u).then((r) => r.json())));
    pacientes = Object.fromEntries(ps.map((p) => [p.id, p])); medicos = Object.fromEntries(ms.map((m) => [m.id, m]));
  } catch { pacientes = {}; medicos = {}; }
}
const nomePaciente = (id) => pacientes[id]?.nome ?? `Paciente ${id} (fora do cadastro)`;
const nomeMedico = (id) => medicos[id]?.nome ?? `Médico ${id}`;

// ---- API + bastidores
const REGRAS = {
  "GET /prontuarios": "find() sem filtro, ordenado por paciente_id. Cada prontuário é um documento só, com tudo embutido.",
  "GET /prontuarios/{n}": "find_one({paciente_id}): uma leitura traz o prontuário inteiro (evoluções, exames, prescrições), sem JOIN.",
  "POST /prontuarios": "insert_one. O índice único em paciente_id impede dois prontuários para o mesmo paciente.",
  "GET /prontuarios/{n}/versoes": "find() em historico_versoes ordenado por numero_versao; a diferença entre cópias seguidas mostra o que mudou.",
  "GET /prontuarios/{n}/versoes/{n}": "Lê a cópia daquela versão em historico_versoes (ou o documento atual, se for a última).",
  "GET /colecoes": "listCollections, índices e um documento de exemplo de cada coleção.",
};
const ALTERA = "1) insert_one em historico_versoes: cópia da versão N com data, responsável e justificativa (índice único por prontuário+versão). 2) update_one só se versao ainda for N: $set nas seções e $inc na versao. Se outra alteração chegou antes, a segunda recebe 409.";
function regraDe(op) {
  const [metodo, caminho] = op.split(" ");
  const g = caminho.replace(/\/\d+/g, "/{n}");
  if (metodo !== "GET" && /^\/prontuarios\/\{n\}\//.test(g)) return ALTERA;
  return REGRAS[`${metodo} ${g}`] || "";
}
// ---- detalhes de cada ação: clicar (ou Enter) num cartão abre o que o banco executou
const detalhesPorId = new Map(); let seqDetalhe = 0;
function ligarDetalhes() {
  const abrir = (el) => { const ev = detalhesPorId.get(el?.dataset.ev); if (ev) Detalhes.abrir(ev); };
  $("log").addEventListener("click", (e) => abrir(e.target.closest("[data-ev]")));
  $("log").addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { const c = e.target.closest("[data-ev]"); if (c) { e.preventDefault(); abrir(c); } } });
}

async function api(metodo, url, corpo) {
  const op = `${metodo} ${url}`, t0 = performance.now();
  let status = 0, dados = {}, consultas = [];
  try {
    const r = await fetch(url, { method: metodo, headers: { "X-Log": "1", ...(corpo ? { "Content-Type": "application/json" } : {}) }, ...(corpo ? { body: JSON.stringify(corpo) } : {}) });
    status = r.status; dados = await r.json().catch(() => ({}));
    consultas = await Detalhes.decodificar(r.headers.get("X-DB-Log")) || [];
  } catch { dados = { detail: "API fora do ar" }; }
  const ok = status >= 200 && status < 300;
  let detalhe = "";
  if (!ok) detalhe = typeof dados.detail === "string" ? dados.detail : Array.isArray(dados.detail) ? dados.detail.map((e) => `${(e.loc || []).slice(1).join(".")}: ${e.msg}`).join("; ") : "Pedido recusado";
  registrar(op, ok, status, detalhe, performance.now() - t0, { consultas, resposta: dados });
  return { ok, status, dados, detalhe };
}
function registrar(op, ok, status, detalhe, ms, extra = {}) {
  const regra = regraDe(op);
  const ev = { titulo: op, op, ok, status, ms, regra: detalhe || regra, ...extra }, id = String(++seqDetalhe); detalhesPorId.set(id, ev);
  const li = document.createElement("li");
  li.className = `evento ${ok ? "ok" : "erro"} ${ev.consultas?.length ? "clicavel" : ""}`;
  if (ev.consultas?.length) { li.dataset.ev = id; li.tabIndex = 0; li.setAttribute("role", "button"); }
  li.innerHTML = `<div class="evento-topo"><span class="selo ${ok ? "gravado" : "recusado"}">${ok ? "executado" : "recusado"}</span><b>${status || "—"}</b><time>${new Date().toLocaleTimeString("pt-BR")}</time></div>
    <div><b>${esc(op)}</b> · ${Math.round(ms)} ms${detalhe ? ` · ${esc(detalhe)}` : ""}</div>${regra && ok ? `<div class="evento-regra">${esc(regra)}</div>` : ""}${Detalhes.rodape(ev)}`;
  $("log").querySelector(".vazio")?.remove(); $("log").prepend(li);
  while ($("log").children.length > 20) $("log").lastChild.remove();
  $("conta-eventos").textContent = ++eventos;
}

// ---- lista e seleção
async function carregarLista(manter) {
  const r = await api("GET", "/prontuarios");
  if (!r.ok) return;
  lista = r.dados;
  const atual = manter ?? $("sel-paciente").value;
  $("sel-paciente").innerHTML = lista.length ? lista.map((p) => `<option value="${p.paciente_id}">${esc(nomePaciente(p.paciente_id))} · v${p.versao}</option>`).join("") : '<option value="">Nenhum prontuário</option>';
  if (atual && lista.some((p) => String(p.paciente_id) === String(atual))) $("sel-paciente").value = atual;
  await mostrar();
}
async function mostrar() {
  const id = $("sel-paciente").value;
  const aba = document.querySelector("input[name=aba]:checked").value;
  if (aba === "mongo") return carregarMongo();
  if (!id) {
    $("conteudo").innerHTML = '<div class="cartao estado-vazio"><strong>Nenhum prontuário ainda</strong><span>Crie um para um paciente do cadastro ou carregue os exemplos.</span></div>';
    $("versoes").innerHTML = ""; doc = null; return;
  }
  if (aba === "versoes") return carregarVersoes(id);
  const r = await api("GET", `/prontuarios/${id}`);
  if (r.ok && $("sel-paciente").value === id) { doc = r.dados; desenhar(); }
}

// ---- prontuário
const fichas = (itens, selo) => itens.length ? `<div class="fichas">${itens.map((i) => `<span class="selo ${selo} sem-ponto">${esc(i)}</span>`).join("")}</div>` : '<span class="dica">Nenhum registro</span>';
function kv(obj) {
  return `<dl class="resultado">${Object.entries(obj).map(([k, v]) =>
    v !== null && typeof v === "object" && !Array.isArray(v) ? `<dt>${esc(k)}</dt><dd class="aninhado">${kv(v)}</dd>` : `<dt>${esc(k)}</dt><dd>${esc(Array.isArray(v) ? v.join(", ") : v)}</dd>`).join("")}</dl>`;
}
function desenhar() {
  const d = doc, h = d.historico_clinico;
  const ev = d.evolucoes.map((e, i) => ({ e, i })).reverse();
  $("conteudo").innerHTML = `
    <dl class="cartao resumo" style="margin-bottom:16px">
      <div><dt>Versão atual</dt><dd>v${d.versao}</dd></div><div><dt>Evoluções</dt><dd>${d.evolucoes.length}</dd></div>
      <div><dt>Exames</dt><dd>${d.exames.length}</dd></div><div><dt>Prescrições</dt><dd>${d.prescricoes.length}</dd></div></dl>
    <section class="cartao bloco"><header><h2>Histórico clínico</h2><button class="botao secundario sm" data-acao="historico">Editar</button></header>
      <div class="corpo"><div><span class="rotulo">Alergias</span>${fichas(h.alergias || [], "recusado")}</div>
        <div><span class="rotulo">Doenças crônicas</span>${fichas(h.doencas_cronicas || [], "aviso")}</div>
        <div><span class="rotulo">Antecedentes</span><p>${esc(h.antecedentes) || '<span class="dica">Nenhum registro</span>'}</p></div></div></section>
    <section class="cartao bloco"><header><h2>Evoluções</h2><button class="botao primario sm" data-acao="evolucao">+ Nova evolução</button></header>
      ${ev.length ? ev.map(({ e, i }) => `<div class="item"><div class="item-topo"><b>${esc(quando(e.data))}</b><span class="meta">${esc(nomeMedico(e.medico_id))}</span><button class="botao secundario sm" data-acao="corrigir" data-i="${i}">Corrigir</button></div><p>${esc(e.descricao)}</p></div>`).join("") : '<p class="vazio">Nenhuma evolução registrada.</p>'}</section>
    <section class="cartao bloco"><header><h2>Exames</h2><button class="botao primario sm" data-acao="exame">+ Novo exame</button></header>
      ${d.exames.length ? [...d.exames].reverse().map((x) => `<div class="item"><div class="item-topo"><b>${esc(x.tipo)}</b><span class="meta">${esc(quando(x.data))}${x.laboratorio ? " · " + esc(x.laboratorio) : ""}</span></div>${kv(x.resultado || {})}${x.laudo ? `<p>${esc(x.laudo)}</p>` : ""}</div>`).join("") : '<p class="vazio">Nenhum exame registrado.</p>'}</section>
    <section class="cartao bloco"><header><h2>Prescrições</h2><button class="botao primario sm" data-acao="prescricao">+ Nova prescrição</button></header>
      ${d.prescricoes.length ? [...d.prescricoes].reverse().map((p) => `<div class="item"><div class="item-topo"><b>${esc(p.medicamento)}</b><span class="meta">${esc(quando(p.data))} · ${esc(nomeMedico(p.medico_id))}</span></div><p>${[p.dosagem, p.frequencia, p.duracao].filter(Boolean).map(esc).join(" · ")}</p>${p.observacoes ? `<p class="dica">${esc(p.observacoes)}</p>` : ""}</div>`).join("") : '<p class="vazio">Nenhuma prescrição registrada.</p>'}</section>`;
}

// ---- diálogo genérico de alteração (sempre com responsável e justificativa: é a auditoria)
const lista_ = (t) => t.split(",").map((s) => s.trim()).filter(Boolean);
const campo = (rot, html, dica) => `<label class="campo">${rot}${dica ? ` <span class="dica">${dica}</span>` : ""}${html}</label>`;
const input = (n, v = "", extra = "") => `<input class="controle" name="${n}" value="${esc(v)}" ${extra}>`;
const area = (n, v = "", rows = 3, cls = "") => `<textarea class="controle area ${cls}" name="${n}" rows="${rows}">${esc(v)}</textarea>`;
const hc = () => doc.historico_clinico;
const ACOES = {
  historico: { titulo: "Editar histórico clínico", campos: () => campo("Alergias", input("alergias", (hc().alergias || []).join(", ")), "separe por vírgula") + campo("Doenças crônicas", input("doencas", (hc().doencas_cronicas || []).join(", ")), "separe por vírgula") + campo("Antecedentes", area("antecedentes", hc().antecedentes)),
    enviar: (v, a) => api("PUT", `/prontuarios/${doc.paciente_id}/historico-clinico`, { ...a, alergias: lista_(v.alergias), doencas_cronicas: lista_(v.doencas), antecedentes: v.antecedentes }) },
  evolucao: { titulo: "Nova evolução", campos: () => campo("Descrição", area("descricao", "", 4)), enviar: (v, a) => api("POST", `/prontuarios/${doc.paciente_id}/evolucoes`, { ...a, descricao: v.descricao }) },
  corrigir: { titulo: "Corrigir evolução", campos: (i) => campo("Descrição", area("descricao", doc.evolucoes[i].descricao, 4)), enviar: (v, a, i) => api("PUT", `/prontuarios/${doc.paciente_id}/evolucoes/${i}`, { ...a, descricao: v.descricao }) },
  exame: { titulo: "Novo exame", campos: () => campo("Tipo", input("tipo", "", 'list="tipos" placeholder="ex.: Glicemia em jejum"') + '<datalist id="tipos"><option>Glicemia em jejum</option><option>Hemograma completo</option><option>Colesterol total</option><option>Raio-X de tórax</option></datalist>') + campo("Laboratório", input("laboratorio")) +
      campo("Resultado", area("resultado", '{\n  "glicose": 92,\n  "unidade": "mg/dL"\n}', 6, "json"), "estrutura livre: cada tipo de exame tem os seus campos") + campo("Laudo", area("laudo", "", 2)),
    enviar: (v, a) => { let resultado; try { resultado = JSON.parse(v.resultado); } catch { return { ok: false, detalhe: "O resultado precisa ser um JSON válido." }; }
      if (!resultado || typeof resultado !== "object" || Array.isArray(resultado)) return { ok: false, detalhe: "O resultado precisa ser um objeto JSON, como { \"campo\": valor }." };
      return api("POST", `/prontuarios/${doc.paciente_id}/exames`, { ...a, tipo: v.tipo, laboratorio: v.laboratorio, resultado, laudo: v.laudo }); } },
  prescricao: { titulo: "Nova prescrição", campos: () => campo("Medicamento", input("medicamento")) + `<div class="dupla">${campo("Dosagem", input("dosagem", "", 'placeholder="ex.: 1 comprimido"'))}${campo("Frequência", input("frequencia", "", 'placeholder="ex.: A cada 12 horas"'))}</div>` + campo("Duração", input("duracao", "", 'placeholder="ex.: 5 dias"')) + campo("Observações", area("observacoes", "", 2)),
    enviar: (v, a) => api("POST", `/prontuarios/${doc.paciente_id}/prescricoes`, { ...a, medicamento: v.medicamento, dosagem: v.dosagem, frequencia: v.frequencia, duracao: v.duracao, observacoes: v.observacoes }) },
  novo: { titulo: "Novo prontuário", semAuditoria: true,
    campos: () => { const livres = Object.values(pacientes).filter((p) => !lista.some((l) => l.paciente_id === p.id));
      return campo("Paciente do cadastro", livres.length ? `<select class="controle" name="paciente">${livres.map((p) => `<option value="${p.id}">${esc(p.nome)}</option>`).join("")}</select>` : '<input class="controle" name="paciente" type="number" min="1" placeholder="Código do paciente">', livres.length ? "" : "cadastro indisponível ou todos já têm prontuário") +
        campo("Alergias", input("alergias"), "separe por vírgula") + campo("Doenças crônicas", input("doencas"), "separe por vírgula") + campo("Antecedentes", area("antecedentes")); },
    enviar: (v) => api("POST", "/prontuarios", { paciente_id: Number(v.paciente), historico_clinico: { alergias: lista_(v.alergias), doencas_cronicas: lista_(v.doencas), antecedentes: v.antecedentes } }) },
};
function abrir(nome, i) {
  const a = ACOES[nome]; acaoAtual = { a, i };
  $("dlg-titulo").textContent = a.titulo; $("dlg-campos").innerHTML = a.campos(i); $("dlg-erro").hidden = true;
  $("dlg-auditoria").hidden = !!a.semAuditoria; $("f-justificativa").value = "";
  const ids = Object.keys(medicos);
  $("f-responsavel").outerHTML = ids.length ? `<select class="controle" id="f-responsavel">${ids.map((m) => `<option value="${m}">${esc(medicos[m].nome)}</option>`).join("")}</select>` : '<input class="controle" id="f-responsavel" type="number" min="1" placeholder="Código do médico">';
  if (ids.length && ultimoResp) $("f-responsavel").value = ultimoResp;
  $("dlg").showModal(); $("dlg-campos").querySelector("input,textarea,select")?.focus();
}
$("dlg-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const { a, i } = acaoAtual, v = Object.fromEntries(new FormData($("dlg-form")));
  const aud = a.semAuditoria ? {} : { responsavel_id: Number($("f-responsavel").value), justificativa: $("f-justificativa").value.trim() };
  $("dlg-ok").disabled = true;
  const r = await a.enviar(v, aud, i);
  $("dlg-ok").disabled = false;
  if (!r.ok) { $("dlg-erro").textContent = r.detalhe || "Não foi possível salvar."; $("dlg-erro").hidden = false; return; }
  if (!a.semAuditoria) ultimoResp = $("f-responsavel").value;
  $("dlg").close();
  carregarLista(a === ACOES.novo ? String(Number(v.paciente)) : undefined);
});
document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-acao]"); if (b) abrir(b.dataset.acao, Number(b.dataset.i));
  const f = e.target.closest("[data-fechar]"); if (f) f.closest("dialog").close();
  const v = e.target.closest("[data-versao]"); if (v) verVersao(v.dataset.versao);
});
$("novo").addEventListener("click", () => abrir("novo"));
$("exemplos").addEventListener("click", async () => { const r = await api("POST", "/demonstracao"); if (r.ok) carregarLista(); });

// ---- versões
const ROTULO_SECAO = { historico_clinico: "Histórico clínico", evolucoes: "Evolução", exames: "Exame", prescricoes: "Prescrição" };
function rotulo(c) {
  const m = c.match(/^(historico_clinico|evolucoes|exames|prescricoes)(?:\[(\d+)\])?(?:\.(.+))?$/);
  if (!m) return c;
  return `${ROTULO_SECAO[m[1]]}${m[2] !== undefined ? " " + (Number(m[2]) + 1) : ""}${m[3] ? " · " + m[3].replace(/_/g, " ") : ""}`;
}
function resumo(v) {
  if (v === null || v === undefined) return "—";
  if (Array.isArray(v)) return v.join(", ") || "(vazio)";
  if (typeof v === "object") return v.tipo || v.medicamento || v.descricao || JSON.stringify(v);
  return String(v);
}
async function carregarVersoes(id) {
  const r = await api("GET", `/prontuarios/${id}/versoes`);
  if (!r.ok || $("sel-paciente").value !== id) return;
  const d = r.dados, itens = [...d.alteracoes].reverse();
  $("versoes").innerHTML = `<div class="cartao bloco"><header><h2>Histórico de alterações</h2><span class="selo destaque sem-ponto">versão atual: v${d.versao_atual}</span></header>
    ${itens.map((a) => `<div class="versao"><div class="versao-topo"><span class="selo aviso sem-ponto">v${a.de_versao} → v${a.para_versao}</span><b>${esc(quando(a.auditoria.data_alteracao))}</b><span class="meta">${esc(nomeMedico(a.auditoria.responsavel_id))}</span>
        <button class="botao secundario sm" data-versao="${a.de_versao}">Ver a v${a.de_versao}</button></div><div class="just">${esc(a.auditoria.justificativa)}</div>
        ${a.mudancas.length ? `<div class="mudanca">${a.mudancas.map((m) => `<span class="caminho">${esc(rotulo(m.caminho))}</span><span>${m.antes == null ? `<span class="depois">adicionado: ${esc(resumo(m.depois))}</span>` : m.depois == null ? `<span class="antes">${esc(resumo(m.antes))}</span> removido` : `<span class="antes">${esc(resumo(m.antes))}</span> → <span class="depois">${esc(resumo(m.depois))}</span>`}</span>`).join("")}</div>` : ""}</div>`).join("")}
    <div class="versao"><div class="versao-topo"><span class="selo gravado sem-ponto">v1</span><b>${esc(quando(d.criado_em))}</b><span class="meta">Prontuário criado</span></div></div></div>`;
}
async function verVersao(n) {
  const r = await api("GET", `/prontuarios/${$("sel-paciente").value}/versoes/${n}`);
  if (!r.ok) return;
  $("dv-titulo").textContent = `Versão ${n} do prontuário`; $("dv-json").textContent = JSON.stringify(r.dados, null, 2); $("dlg-versao").showModal();
}

// ---- MongoDB por dentro
const PORQUE = {
  prontuarios: "Um documento por paciente, com tudo embutido: histórico clínico, evoluções, exames e prescrições. Uma leitura traz o prontuário inteiro, sem JOIN. Cada exame tem os campos que precisar (veja resultado de glicemia versus hemograma): o esquema evolui sem migração.",
  historico_versoes: "A cópia de cada versão anterior, com a auditoria (quem, quando e por quê). O índice único (prontuario_id, numero_versao) garante uma cópia por versão e barra duas alterações simultâneas: a segunda recebe 409 em vez de sobrescrever.",
};
async function carregarMongo() {
  const r = await api("GET", "/colecoes");
  if (!r.ok) return;
  const d = r.dados;
  $("mongo").innerHTML = `<dl class="cartao resumo tres" style="margin-bottom:16px"><div><dt>Banco</dt><dd>${esc(d.banco)}</dd></div><div><dt>MongoDB</dt><dd>${esc(d.versao_mongo)}</dd></div><div><dt>Coleções</dt><dd>${d.colecoes.length}</dd></div></dl>` +
    d.colecoes.map((c) => `<article class="cartao bloco colecao"><header><h2>${esc(c.nome)}</h2><span class="selo destaque sem-ponto">${c.documentos} ${c.documentos === 1 ? "documento" : "documentos"}</span></header>
      <div class="corpo">${PORQUE[c.nome] ? `<p>${esc(PORQUE[c.nome])}</p>` : ""}
        <div class="fichas">${c.indices.map((i) => `<span class="selo ${i.unico ? "gravado" : ""} sem-ponto">índice ${esc(i.nome)}${i.unico ? " · único" : ""}</span>`).join("")}</div>
        <span class="rotulo">Documento de exemplo</span><pre class="codigo">${esc(JSON.stringify(c.exemplo, null, 2))}</pre></div></article>`).join("");
}

// ---- abas e bastidores
document.querySelectorAll("input[name=aba]").forEach((r) => r.addEventListener("change", () => {
  ["prontuario", "versoes", "mongo"].forEach((v) => { $(`view-${v}`).hidden = !(r.checked && r.value === v); });
  mostrar();
}));
$("sel-paciente").addEventListener("change", mostrar);
$("abrir-bastidores").addEventListener("click", () => { $("bastidores").hidden = !$("bastidores").hidden; });
$("fechar-bastidores").addEventListener("click", () => { $("bastidores").hidden = true; $("abrir-bastidores").focus(); });
carregarCadastro().then(() => carregarLista());
ligarDetalhes();
