// Aba "Banco": diagrama e detalhes lidos de GET /banco/estrutura (catálogo do PostgreSQL). Só leitura.
(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const W = 210, GAP_X = 70, GAP_Y = 26, TOPO = 34, LIN = 24;
  let est = null, sel = null, aba = "colunas", carregando = false;

  const altura = (t) => TOPO + t.colunas.length * LIN;

  // coluna da esquerda = tabelas que não dependem de ninguém; cada tabela fica à direita de quem ela referencia
  function posicionar() {
    const prof = {};
    const nivel = (n, vistos = []) => {
      if (prof[n] !== undefined) return prof[n];
      if (vistos.includes(n)) return 0;
      const pais = est.relacoes.filter((r) => r.de === n && r.para !== n).map((r) => r.para);
      return (prof[n] = pais.length ? 1 + Math.max(...pais.map((p) => nivel(p, [...vistos, n]))) : 0);
    };
    est.tabelas.forEach((t) => nivel(t.nome));
    const camadas = [];
    est.tabelas.forEach((t) => (camadas[prof[t.nome]] ||= []).push(t));
    const pos = {};
    camadas.forEach((cam, i) => {
      if (i > 0) { // reduz cruzamentos: perto do centro dos pais
        const media = (t) => { const ps = est.relacoes.filter((r) => r.de === t.nome).map((r) => pos[r.para]?.y ?? 0); return ps.length ? ps.reduce((a, b) => a + b, 0) / ps.length : 0; };
        cam.sort((a, b) => media(a) - media(b));
      }
      let y = 0;
      cam.forEach((t) => { pos[t.nome] = { x: i * (W + GAP_X), y, h: altura(t) }; y += altura(t) + GAP_Y; });
    });
    const larg = camadas.length * W + (camadas.length - 1) * GAP_X;
    const alt = Math.max(...Object.values(pos).map((p) => p.y + p.h));
    return { pos, larg, alt };
  }

  function chaves(c) {
    return (c.pk ? '<span class="chave pk">PK</span>' : "") + (c.fk ? '<span class="chave fk">FK</span>' : "");
  }

  function desenharDiagrama() {
    const { pos, larg, alt } = posicionar();
    const caixa = $("#banco-diagrama");
    const k = Math.max(0.6, Math.min(1, (caixa.clientWidth - 32) / larg));
    const nos = est.tabelas.map((t) => `<button type="button" class="no-tabela ${sel === t.nome ? "sel" : ""}" data-tabela="${esc(t.nome)}" style="left:${pos[t.nome].x}px;top:${pos[t.nome].y}px;width:${W}px" aria-label="Tabela ${esc(t.nome)}, ${t.linhas} linhas">
      <header>${esc(t.nome)}<small>${t.linhas} linhas</small></header>
      ${t.colunas.map((c) => `<div class="col">${chaves(c)}<b>${esc(c.nome)}</b><span>${esc(c.tipo)}</span></div>`).join("")}</button>`).join("");
    const lig = est.relacoes.map((r) => {
      const filho = pos[r.de], pai = pos[r.para];
      const tf = est.tabelas.find((t) => t.nome === r.de), tp = est.tabelas.find((t) => t.nome === r.para);
      const yf = filho.y + TOPO + tf.colunas.findIndex((c) => c.nome === r.colunas[0]) * LIN + LIN / 2;
      const yp = pai.y + TOPO + tp.colunas.findIndex((c) => c.nome === r.colunas_ref[0]) * LIN + LIN / 2;
      const x1 = filho.x, x2 = pai.x + W, dx = Math.max(30, (x1 - x2) / 2);
      const ativa = sel === r.de || sel === r.para;
      return `<path class="lig ${ativa ? "ativa" : ""}" d="M${x1},${yf} C${x1 - dx},${yf} ${x2 + dx},${yp} ${x2},${yp}"/>
        <text class="card-n lig-n ${ativa ? "ativa" : ""}" x="${x1 - 12}" y="${yf - 6}">N</text><text class="card-n lig-n ${ativa ? "ativa" : ""}" x="${x2 + 5}" y="${yp - 6}">1</text>`;
    }).join("");
    caixa.innerHTML = `<div style="height:${alt * k}px"><div class="diagrama" style="width:${larg}px;height:${alt}px;transform:scale(${k})"><svg>${lig}</svg>${nos}</div></div>`;
  }

  function resumo() {
    const n = (f) => est.tabelas.reduce((s, t) => s + f(t), 0);
    $("#banco-resumo").innerHTML = [
      ["Tabelas", est.tabelas.length], ["Chaves estrangeiras", est.relacoes.length],
      ["Restrições", n((t) => t.restricoes.length)], ["Triggers", n((t) => t.triggers.length)],
    ].map(([a, b]) => `<div><dt>${a}</dt><dd>${b}</dd></div>`).join("");
  }

  const tabelaPor = (nome) => est.tabelas.find((t) => t.nome === nome);

  function painelColunas(t) {
    return `<table class="tabela"><thead><tr><th>Coluna</th><th>Tipo</th><th>Regras da coluna</th><th>Padrão</th></tr></thead><tbody>${t.colunas.map((c) => `<tr>
      <td class="forte">${esc(c.nome)}</td><td class="mono">${esc(c.tipo)}</td>
      <td>${chaves(c)} ${c.fk ? `<button class="link" type="button" data-ir="${esc(c.fk.tabela)}">→ ${esc(c.fk.tabela)}.${esc(c.fk.coluna)}</button>` : ""}
        ${c.unica ? '<span class="chave">UNIQUE</span>' : ""} ${c.obrigatoria ? '<span class="chave">NOT NULL</span>' : ""}</td>
      <td class="mono">${c.padrao ? esc(c.padrao) : '<span class="nulo">—</span>'}</td></tr>`).join("")}</tbody></table>`;
  }

  function painelRegras(t) {
    const rs = t.restricoes.length ? `<ul class="regra-lista">${t.restricoes.map((r) => `<li><div class="t"><span class="selo ${r.tipo === "EXCLUDE" ? "aviso" : r.tipo === "FOREIGN KEY" ? "destaque" : ""} sem-ponto">${esc(r.tipo)}</span>${esc(r.nome)}</div><code>${esc(r.definicao)}</code></li>`).join("")}</ul>` : '<p class="vazio">Sem restrições.</p>';
    const gs = t.triggers.length ? `<ul class="regra-lista">${t.triggers.map((g) => `<li><div class="t"><span class="selo gravado sem-ponto">${esc(g.momento)} ${esc(g.evento)}</span>${esc(g.nome)}</div><code>executa ${esc(g.funcao)}()</code></li>`).join("")}</ul>` : '<p class="vazio" style="padding:8px 20px 16px">Nenhum trigger nesta tabela.</p>';
    return `<p class="regra-titulo">Restrições (${t.restricoes.length})</p>${rs}<p class="regra-titulo">Triggers (${t.triggers.length})</p>${gs}`;
  }

  async function painelDados(t) {
    $("#banco-painel").innerHTML = '<p class="vazio" style="padding:20px">Carregando…</p>';
    let corpo;
    try { corpo = await (await fetch(`/banco/tabelas/${encodeURIComponent(t.nome)}/dados?limit=50`)).json(); } catch { corpo = null; }
    if (sel !== t.nome || aba !== "dados") return;
    if (!corpo || !corpo.linhas) { $("#banco-painel").innerHTML = '<p class="vazio" style="padding:20px">Não foi possível ler os dados.</p>'; return; }
    if (!corpo.linhas.length) { $("#banco-painel").innerHTML = '<p class="vazio" style="padding:20px">Tabela vazia.</p>'; return; }
    const cols = t.colunas.map((c) => c.nome);
    const cel = (v) => v === null || v === undefined ? '<span class="nulo">NULL</span>' : esc(typeof v === "object" ? JSON.stringify(v) : v);
    $("#banco-painel").innerHTML = `<table class="tabela"><thead><tr>${cols.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>${corpo.linhas.map((l) => `<tr>${cols.map((c) => `<td class="mono">${cel(l[c])}</td>`).join("")}</tr>`).join("")}</tbody></table>
      <p class="dica" style="padding:12px 20px">Mostrando as ${corpo.linhas.length} linhas mais recentes (de ${t.linhas}).</p>`;
  }

  function detalhe() {
    const t = tabelaPor(sel);
    $("#banco-detalhe").hidden = !t;
    if (!t) return;
    $("#banco-titulo").textContent = t.nome;
    const refs = est.relacoes.filter((r) => r.para === t.nome).map((r) => r.de);
    $("#banco-sub").textContent = `${t.linhas} linhas · ${t.colunas.length} colunas` + (refs.length ? ` · referenciada por ${[...new Set(refs)].join(", ")}` : "");
    if (aba === "colunas") $("#banco-painel").innerHTML = painelColunas(t);
    else if (aba === "regras") $("#banco-painel").innerHTML = painelRegras(t);
    else painelDados(t);
  }

  function rotinas() {
    const caixa = $("#banco-rotinas");
    caixa.hidden = !est.rotinas.length;
    caixa.className = "cartao rotinas";
    caixa.innerHTML = `<p class="rotinas-titulo">Procedures e funções (${est.rotinas.length})</p>${est.rotinas.map((r) => `<details><summary><span class="selo ${r.tipo === "procedure" ? "aviso" : ""} sem-ponto">${esc(r.tipo)}</span>${esc(r.nome)}(${esc(r.argumentos)})</summary><pre>${esc(r.definicao)}</pre></details>`).join("")}`;
  }

  function escolher(nome) {
    sel = nome; desenharDiagrama(); detalhe();
  }

  async function carregar() {
    if (carregando) return;
    carregando = true;
    try {
      est = await (await fetch("/banco/estrutura")).json();
      if (!sel || !tabelaPor(sel)) sel = est.tabelas.find((t) => t.nome === "agendamento")?.nome || est.tabelas[0]?.nome;
      resumo(); desenharDiagrama(); detalhe(); rotinas();
    } catch {
      $("#banco-diagrama").innerHTML = '<div class="estado-vazio"><strong>Não foi possível ler o banco</strong><span>A API não respondeu.</span></div>';
    } finally { carregando = false; }
  }

  function aoMudarRota() {
    const aqui = location.hash === "#/banco";
    $(".app").classList.toggle("sem-bastidores", aqui);
    if (aqui) carregar();
  }

  document.addEventListener("click", (e) => {
    const no = e.target.closest("[data-tabela]");
    if (no) return escolher(no.dataset.tabela);
    const ir = e.target.closest("[data-ir]");
    if (ir) escolher(ir.dataset.ir);
  });
  document.querySelectorAll("input[name=banco-aba]").forEach((r) => r.addEventListener("change", () => { aba = r.value; detalhe(); }));
  $("#banco-atualizar").addEventListener("click", carregar);
  window.addEventListener("hashchange", aoMudarRota);
  window.addEventListener("resize", () => { if (est && location.hash === "#/banco") desenharDiagrama(); });
  aoMudarRota();
})();
