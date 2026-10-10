"use strict";

const $ = (id) => document.getElementById(id);
let doc = null;
let activeEls = [];

function el(tag, props = {}, text) {
  const e = document.createElement(tag);
  Object.assign(e, props);
  if (text !== undefined) e.textContent = text;
  return e;
}

function showError(msg) {
  const box = $("error");
  box.textContent = msg;
  box.hidden = false;
}

async function fetchJson(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`);
  return res.json();
}

function validate(d) {
  if (!d || !Array.isArray(d.paragraphs)) throw new Error("Malformed document: no paragraphs");
  for (const p of d.paragraphs) {
    if (!Array.isArray(p.sentences)) throw new Error("Malformed document: no sentences");
    for (const s of p.sentences) {
      if (typeof s.translation !== "string" || !Array.isArray(s.tokens)) {
        throw new Error("Malformed document: bad sentence " + (s.id ?? "?"));
      }
    }
  }
}

async function loadIndex() {
  const docs = (await fetchJson("content/index.json")).documents;
  // Present only when served locally by the pipeline; a 404 on GitHub Pages is expected.
  try {
    const priv = await fetchJson("content-private/index.json");
    for (const d of priv.documents) docs.push({ ...d, lane: "private" });
  } catch (_) { /* no private content */ }
  return docs;
}

function clearActive() {
  activeEls.forEach((e) => e.classList.remove("active", "in-group"));
  activeEls = [];
  document.querySelectorAll(".sentence.active").forEach((e) => e.classList.remove("active"));
}

function renderPanel(sentence, token, group) {
  const panel = $("panel");
  panel.replaceChildren();
  panel.append(el("h2", {}, token.text));
  if (token.lemma && token.lemma !== token.text) {
    panel.append(el("p", { className: "muted" }, "Base form: " + token.lemma));
  }
  const meaning = group ? group.in_context : token.in_context;
  const glosses = (doc.glossary && doc.glossary[token.lemma]) || [];
  if (meaning) {
    const label = group
      ? "In this sentence (" + group.token_ids.map((i) => sentence.tokens[i].text).join(" ") + "): "
      : "In this sentence: ";
    panel.append(el("p", {}, label + meaning + " (machine-aligned)"));
  }
  if (glosses.length) panel.append(el("p", {}, "Dictionary: " + glosses.join(", ")));
  if (!meaning && !glosses.length) panel.append(el("p", { className: "muted" }, "No entry for this word."));
  panel.append(el("p", { className: "muted" }, "Sentence translation: " + sentence.translation));
  const close = el("button", { type: "button" }, "Close");
  close.addEventListener("click", closePanel);
  panel.append(close);
  panel.hidden = false;
}

function closePanel() {
  clearActive();
  $("panel").hidden = true;
}

function selectWord(sentence, sentenceEl, index, tokenEls) {
  clearActive();
  const token = sentence.tokens[index];
  const group = (sentence.groups || []).find((g) => g.token_ids.includes(index));
  const targets = group ? group.token_ids : [index];
  for (const i of targets) {
    tokenEls[i].classList.add(group ? "in-group" : "active");
    activeEls.push(tokenEls[i]);
  }
  sentenceEl.classList.add("active");
  renderPanel(sentence, token, group);
}

function renderSentence(sentence) {
  const sEl = el("span", { className: "sentence" });
  const tokenEls = [];
  sentence.tokens.forEach((t, i) => {
    if (t.is_word) {
      const w = el("span", { className: "word", tabIndex: 0, role: "button" }, t.text);
      w.addEventListener("click", () => selectWord(sentence, sEl, i, tokenEls));
      w.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); w.click(); }
      });
      tokenEls.push(w);
      sEl.append(w);
    } else {
      const span = el("span", {}, t.text);
      tokenEls.push(span);
      sEl.append(span);
    }
    if (t.ws) sEl.append(document.createTextNode(t.ws));
  });
  const tr = el("span", { className: "sentence-tr" }, sentence.translation);
  tr.hidden = !$("show-all").checked;
  const btn = el("button", { type: "button", className: "tr-btn", title: "Show sentence translation" }, "EN");
  btn.addEventListener("click", () => { tr.hidden = !tr.hidden; });
  sEl.append(btn);
  return [sEl, tr];
}

function renderDocument(d) {
  validate(d);
  doc = d;
  $("error").hidden = true;
  $("doc-title").textContent = d.title || "";
  const text = $("text");
  text.replaceChildren();
  for (const p of d.paragraphs) {
    if (p.heading) text.append(el("h2", {}, p.heading));
    const pe = el("p");
    for (const s of p.sentences) pe.append(...renderSentence(s));
    text.append(pe);
  }
  const att = $("attribution");
  att.replaceChildren();
  att.append(document.createTextNode(`Source: ${d.attribution || d.source_url || ""}. Licence: ${d.license || "unknown"}. Words and sentences were tokenized and machine-translated. `));
  for (const [label, url] of [["Original", d.source_url], ["History", d.history_url], ["Licence text", d.license_url]]) {
    if (url && /^https?:\/\//.test(url)) {
      att.append(el("a", { href: url, rel: "noopener" }, label), document.createTextNode(" "));
    }
  }
  closePanel();
}

async function openDoc(path) {
  try {
    renderDocument(await fetchJson(path));
  } catch (err) {
    showError("Could not load document: " + err.message);
  }
}

async function init() {
  try {
    const docs = await loadIndex();
    const select = $("doc-select");
    for (const d of docs) {
      select.append(el("option", { value: d.path }, d.title + (d.lane === "private" ? " [private]" : "")));
    }
    select.addEventListener("change", () => openDoc(select.value));
    $("show-all").addEventListener("change", (ev) => {
      document.querySelectorAll(".sentence-tr").forEach((t) => { t.hidden = !ev.target.checked; });
    });
    document.addEventListener("keydown", (ev) => { if (ev.key === "Escape") closePanel(); });
    if (docs.length) await openDoc(docs[0].path);
    else showError("No documents available.");
  } catch (err) {
    showError("Could not load the document list: " + err.message);
  }
}

init();
