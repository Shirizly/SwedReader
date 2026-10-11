"use strict";

const $ = (id) => document.getElementById(id);
let doc = null;
let activeEls = [];
let sentenceElements = new Map();
let audioTimeline = [];
let activeAudioSentence = -1;

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

function clearAudio() {
  const player = $("audio-player");
  player.pause();
  player.removeAttribute("src");
  player.load();
  $("audio-player-bar").hidden = true;
  ["audio-previous", "audio-play", "audio-stop", "audio-next", "audio-seek", "audio-speed", "audio-speed-toggle"]
    .forEach((id) => { $(id).disabled = true; });
  $("audio-speed-popover").hidden = true;
  $("audio-speed-toggle").setAttribute("aria-expanded", "false");
  audioTimeline = [];
  activeAudioSentence = -1;
  sentenceElements.forEach((sentenceEl) => sentenceEl.classList.remove("audio-active"));
}

function updateAudioSpeedLabel(rate) {
  const label = `${rate.toFixed(1)}×`;
  $("audio-speed-value").textContent = label;
  $("audio-speed-toggle").textContent = `Speed ${label} ▾`;
  $("audio-speed-toggle").setAttribute("aria-label", `Playback speed: ${label}`);
}

function formatAudioTime(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return "0:00";
  const wholeSeconds = Math.floor(seconds);
  return `${Math.floor(wholeSeconds / 60)}:${String(wholeSeconds % 60).padStart(2, "0")}`;
}

function setActiveAudioSentence(index, scroll = false) {
  if (index === activeAudioSentence) {
    if (scroll && index >= 0) {
      const sentenceEl = sentenceElements.get(audioTimeline[index].id);
      if (sentenceEl) sentenceEl.scrollIntoView({ behavior: "smooth", block: "center" });
    }
    return;
  }
  if (activeAudioSentence >= 0) {
    const previous = sentenceElements.get(audioTimeline[activeAudioSentence].id);
    if (previous) previous.classList.remove("audio-active");
  }
  activeAudioSentence = index;
  if (index < 0 || index >= audioTimeline.length) {
    $("audio-status").textContent = "";
    return;
  }
  const entry = audioTimeline[index];
  const sentenceEl = sentenceElements.get(entry.id);
  if (sentenceEl) {
    sentenceEl.classList.add("audio-active");
    if (scroll) sentenceEl.scrollIntoView({ behavior: "smooth", block: "center" });
  }
  const total = doc.audio.total_sentences || audioTimeline.length;
  const coverage = audioTimeline.length < total
    ? ` (audio for ${audioTimeline.length} of ${total} sentences)`
    : "";
  $("audio-status").textContent = `Sentence ${index + 1} of ${audioTimeline.length}${coverage}`;
}

function audioSentenceAt(time) {
  let low = 0;
  let high = audioTimeline.length - 1;
  let previous = -1;
  while (low <= high) {
    const middle = Math.floor((low + high) / 2);
    const entry = audioTimeline[middle];
    if (time + 0.05 < entry.start) {
      high = middle - 1;
    } else if (time > entry.end + 0.05) {
      previous = middle;
      low = middle + 1;
    } else {
      return middle;
    }
  }
  return previous;
}

function updateAudioPosition() {
  const player = $("audio-player");
  const duration = Number.isFinite(player.duration) ? player.duration : 0;
  $("audio-seek").max = String(duration);
  $("audio-seek").value = String(player.currentTime || 0);
  $("audio-time").textContent = `${formatAudioTime(player.currentTime)} / ${formatAudioTime(duration)}`;
  const index = audioSentenceAt(player.currentTime);
  setActiveAudioSentence(index, index !== activeAudioSentence && !player.paused);
}

function setupAudio(documentData) {
  clearAudio();
  const audio = documentData.audio;
  if (!audio) return;
  const validUrl = typeof audio.url === "string"
    && audio.url.startsWith("content/audio/")
    && !audio.url.split("/").includes("..");
  if (!validUrl || !Array.isArray(audio.sentences) || !audio.sentences.length) {
    $("audio-player-bar").hidden = false;
    $("audio-status").textContent = "Audio metadata is unavailable for this document.";
    return;
  }
  let previousEnd = 0;
  for (const entry of audio.sentences) {
    if (typeof entry.id !== "string"
        || !sentenceElements.has(entry.id)
        || !Number.isFinite(entry.start)
        || !Number.isFinite(entry.end)
        || entry.start < previousEnd
        || entry.end <= entry.start) {
      $("audio-player-bar").hidden = false;
      $("audio-status").textContent = "Audio sentence timings are invalid.";
      return;
    }
    previousEnd = entry.end;
  }
  audioTimeline = audio.sentences;
  ["audio-previous", "audio-play", "audio-stop", "audio-next", "audio-seek", "audio-speed", "audio-speed-toggle"]
    .forEach((id) => { $(id).disabled = false; });
  const player = $("audio-player");
  player.src = audio.url;
  player.playbackRate = 1;
  $("audio-speed").value = "1";
  updateAudioSpeedLabel(1);
  $("audio-player-bar").hidden = false;
  $("audio-status").textContent = audioTimeline.length < (audio.total_sentences || audioTimeline.length)
    ? `Audio for the first ${audioTimeline.length} sentences.`
    : "Ready to play.";
  player.load();
}

function wireAudioControls() {
  const player = $("audio-player");
  player.addEventListener("timeupdate", updateAudioPosition);
  player.addEventListener("loadedmetadata", updateAudioPosition);
  player.addEventListener("durationchange", updateAudioPosition);
  player.addEventListener("play", () => { $("audio-play").textContent = "❚❚"; $("audio-play").setAttribute("aria-label", "Pause"); });
  player.addEventListener("pause", () => { $("audio-play").textContent = "▶"; $("audio-play").setAttribute("aria-label", "Play"); });
  player.addEventListener("ended", updateAudioPosition);
  player.addEventListener("error", () => { $("audio-status").textContent = "Could not load this audio file."; });
  $("audio-play").addEventListener("click", () => {
    if (player.paused) {
      player.play().catch((error) => { $("audio-status").textContent = `Could not play audio: ${error.message}`; });
    } else {
      player.pause();
    }
  });
  $("audio-stop").addEventListener("click", () => {
    player.pause();
    player.currentTime = 0;
    setActiveAudioSentence(-1);
    updateAudioPosition();
  });
  $("audio-previous").addEventListener("click", () => seekAudioSentence(Math.max(0, audioSentenceAt(player.currentTime) - 1)));
  $("audio-next").addEventListener("click", () => seekAudioSentence(Math.min(audioTimeline.length - 1, audioSentenceAt(player.currentTime) + 1)));
  $("audio-seek").addEventListener("input", () => {
    player.currentTime = Number($("audio-seek").value);
    updateAudioPosition();
  });
  $("audio-speed").addEventListener("input", () => {
    const rate = Number($("audio-speed").value);
    player.playbackRate = rate;
    updateAudioSpeedLabel(rate);
  });
  $("audio-speed-toggle").addEventListener("click", () => {
    const popover = $("audio-speed-popover");
    const open = popover.hidden;
    popover.hidden = !open;
    $("audio-speed-toggle").setAttribute("aria-expanded", String(open));
    if (open) $("audio-speed").focus();
  });
  document.addEventListener("click", (event) => {
    if (!$("audio-speed-control").contains(event.target)) {
      $("audio-speed-popover").hidden = true;
      $("audio-speed-toggle").setAttribute("aria-expanded", "false");
    }
  });
  document.addEventListener("keydown", (event) => {
    const popover = $("audio-speed-popover");
    if (event.key === "Escape" && !popover.hidden) {
      popover.hidden = true;
      $("audio-speed-toggle").setAttribute("aria-expanded", "false");
      $("audio-speed-toggle").focus();
    }
  });
}

function seekAudioSentence(index) {
  if (index < 0 || index >= audioTimeline.length) return;
  const player = $("audio-player");
  const resume = !player.paused;
  player.currentTime = audioTimeline[index].start;
  setActiveAudioSentence(index, true);
  if (resume) player.play().catch((error) => { $("audio-status").textContent = `Could not play audio: ${error.message}`; });
  updateAudioPosition();
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
  const glossary = doc.glossary || {};
  const entry = glossary[token.lemma + "|" + (token.pos || "")] || glossary[token.lemma] || {};
  return Array.isArray(entry) ? { dict: entry } : entry;
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
  const dictionaryMeaning = Array.isArray(entry.dict) ? entry.dict.join("; ") : "";
  const machineMeaning = entry.mt || "";
  try {
    if (token.lemma) {
      recordWordCheck({
        lemma: token.lemma,
        surface: token.text,
        meaning: dictionaryMeaning || machineMeaning,
        meaningSource: dictionaryMeaning ? "dictionary" : machineMeaning ? "machine translation" : "",
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
  if (sentence.id) sentenceElements.set(sentence.id, sEl);
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
  clearAudio();
  doc = d;
  sentenceElements = new Map();
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
  setupAudio(d);
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
    wireAudioControls();
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
