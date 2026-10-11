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
  const publicIndex = await fetchJson("content/index.json");
  if (!publicIndex || !Array.isArray(publicIndex.documents)) {
    throw new Error("The public document list is malformed.");
  }
  const docs = publicIndex.documents;
  const privateResponse = await fetch("content-private/index.json");
  if (privateResponse.ok) {
    const priv = await privateResponse.json();
    if (!priv || !Array.isArray(priv.documents)) {
      throw new Error("The private document list is malformed.");
    }
    for (const d of priv.documents) docs.push({ ...d, lane: "private" });
  } else if (privateResponse.status !== 404) {
    throw new Error(`content-private/index.json: HTTP ${privateResponse.status}`);
  }
  return docs;
}

function clearActive() {
  activeEls.forEach((e) => e.classList.remove("active", "in-group"));
  activeEls = [];
  document.querySelectorAll(".sentence-hl").forEach((e) => e.classList.remove("sentence-hl"));
}

function entryFor(token) {
  return (doc.glossary && doc.glossary[token.lemma + "|" + (token.pos || "")]) || {};
}

function renderPanel(sentence, sentenceEl, token, group) {
  const panel = $("panel");
  panel.replaceChildren();
  const entry = entryFor(token);
  const dictAll = Array.isArray(entry.dict) ? entry.dict.join(", ") : "";
  const dictShort = Array.isArray(entry.dict) ? entry.dict.slice(0, 2).join(", ") : "";
  const mt = entry.mt || "";
  const fallback = dictShort || mt;  // a curated dictionary beats a context-free machine translation
  const aligned = group ? group.in_context : token.in_context;
  const check = group ? group.check : token.check;
  // Meanings flagged "weak" (only articles/pronouns, e.g. "me") or "wide" (scattered, unrelated to the
  // fallbacks) are ignored in favour of the fallbacks.
  const meaning = (check !== "weak" && check !== "wide" && aligned) || fallback;
  panel.append(meaning
    ? el("p", { className: "meaning" }, meaning)
    : el("p", { className: "muted" }, "No translation available."));
  if (token.lemma && token.lemma.toLowerCase() !== token.text.toLowerCase()) {
    panel.append(el("p", { className: "muted" }, "Base form: " + token.lemma));
  }
  if (dictAll && dictAll !== meaning) panel.append(el("p", { className: "muted" }, "Dictionary: " + dictAll));
  if (check === "diff" && mt && mt !== meaning && !dictAll.includes(mt)) {
    panel.append(el("p", { className: "muted" }, "Other translation: " + mt));
  }

  const trBox = el("p", { className: "sentence-translation" }, sentence.translation);
  trBox.hidden = true;
  const toggle = el("button", { type: "button" }, "Show sentence translation");
  toggle.addEventListener("click", () => {
    const show = trBox.hidden;
    trBox.hidden = !show;
    sentenceEl.classList.toggle("sentence-hl", show);
    toggle.textContent = show ? "Hide sentence translation" : "Show sentence translation";
  });
  const close = el("button", { type: "button", className: "close" }, "Close");
  close.addEventListener("click", closePanel);
  panel.append(toggle, trBox, close);
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
  const entry = entryFor(token);
  const aligned = group ? group.in_context : token.in_context;
  const check = group ? group.check : token.check;
  const meaning = (check !== "weak" && check !== "wide" && aligned)
    || entry.dict?.[0] || entry.mt || "";
  try {
    if (token.lemma) {
      recordWordCheck({
        lemma: token.lemma,
        surface: token.text,
        meaning,
        docId: doc.id,
      });
    }
  } catch (err) {
    showError("Could not save learning progress: " + err.message);
  }
  const targets = group ? group.token_ids : [index];
  for (const i of targets) {
    tokenEls[i].classList.add(group ? "in-group" : "active");
    activeEls.push(tokenEls[i]);
  }
  renderPanel(sentence, sentenceEl, token, group);
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
  return sEl;
}

function renderDocument(d) {
  validate(d);
  doc = d;
  $("error").hidden = true;
  const title = $("doc-title");
  title.replaceChildren();
  if (d.title_sentence) title.append(renderSentence(d.title_sentence));
  else title.textContent = d.title || "";
  $("byline").textContent = d.author || "";
  $("reading-complete").hidden = true;
  const text = $("text");
  text.replaceChildren();
  for (const p of d.paragraphs) {
    if (p.heading) text.append(el("h2", {}, p.heading));
    const pe = el("p");
    for (const s of p.sentences) pe.append(renderSentence(s));
    text.append(pe);
  }
  const att = $("attribution");
  att.replaceChildren();
  att.append(document.createTextNode(`Source: ${(d.attribution || d.source_url || "").replace(/[.\s]+$/, "")}. Licence: ${d.license || "unknown"}. Words and sentences were tokenized and machine-translated. `));
  if (d.dictionary && d.dictionary.name) {
    att.append(document.createTextNode(`Dictionary entries: ${d.dictionary.name} (${d.dictionary.license || ""}). `));
    if (/^https?:\/\//.test(d.dictionary.url || "")) {
      att.append(el("a", { href: d.dictionary.url, rel: "noopener" }, d.dictionary.name), document.createTextNode(" "));
    }
  }
  for (const [label, url] of [["Original", d.source_url], ["History", d.history_url], ["Licence text", d.license_url]]) {
    if (url && /^https?:\/\//.test(url)) {
      att.append(el("a", { href: url, rel: "noopener" }, label), document.createTextNode(" "));
    }
  }
  closePanel();
  try {
    recordDocumentExposure(d);
  } catch (err) {
    showError("Could not save learning progress: " + err.message);
  }
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
      select.append(el("option", { value: d.path },
        d.title + (d.author ? " – " + d.author : "") + (d.lane === "private" ? " [private]" : "")));
    }
    select.addEventListener("change", () => openDoc(select.value));
    document.addEventListener("keydown", (ev) => { if (ev.key === "Escape") closePanel(); });
    if (!docs.length) {
      showError("No documents available.");
      return;
    }
    const requestedPath = new URLSearchParams(window.location.search).get("story");
    const selectedDoc = requestedPath
      ? docs.find((candidate) => candidate.path === requestedPath)
      : docs[0];
    if (!selectedDoc) {
      showError("The requested document is not in the available document list.");
      return;
    }
    select.value = selectedDoc.path;
    await openDoc(selectedDoc.path);

    const completion = $("reading-complete");
    const observer = new IntersectionObserver((entries) => {
      if (!entries.some((entry) => entry.isIntersecting) || !doc) return;
      const lookups = getLookupCount(doc.id);
      completion.replaceChildren(
        el("strong", {}, "Story complete."),
        el("span", {}, ` You looked up ${lookups} ${lookups === 1 ? "word" : "words"} in this story. `),
      );
      const quizLink = el("a", {
        href: `quiz.html?story=${encodeURIComponent(doc.id)}`,
      }, "Practice these words");
      completion.append(quizLink);
      completion.hidden = false;
    }, { threshold: 0.1 });
    observer.observe($("attribution"));
  } catch (err) {
    showError("Could not load the document list: " + err.message);
  }
}

init();
