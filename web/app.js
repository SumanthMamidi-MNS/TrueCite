/* TrueCite — consultation client.
   Plain JS, no build step: nothing between this and a demo screen that can break.

   Shape is a chat app because that's how the tool is actually used — an officer
   asks, reads, asks again, and comes back tomorrow wanting the thread. The
   verification pipeline runs inside the assistant's message and collapses to a
   badge once it settles, so it reassures on first use without becoming clutter. */

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

const splashT0 = performance.now();
const thread = $("#thread");
const empty = $("#empty");
const composer = $("#composer");
const input = $("#q");
const sendBtn = $("#send");
const historyEl = $("#history");
const chatTitle = $("#chat-title");

const STORE_KEY = "ipsakti.conversations.v1";
const SCOPE_KEY = "ipsakti.jurisdiction.v1";

/* Jurisdiction scope. "all" is the absence of a filter, not a third value the
   API knows about — it sends no `jurisdiction` param at all (see ask()).
   `tag` is what gets stamped on the answer; `full` is the title/screen-reader
   sentence, spelled out because "India only" on its own is a label, not a
   statement of what was searched. */
const SCOPE_META = {
  all: {
    tag: "All sources",
    full: "Answered from the whole corpus — Indian and international instruments together.",
  },
  india: {
    tag: "India only",
    full: "Answered from Indian instruments only — no treaty or international source was consulted.",
  },
  international: {
    tag: "International only",
    full: "Answered from international instruments only — no Indian Act, Rule or guideline was consulted.",
  },
};
const isScope = (v) => Object.prototype.hasOwnProperty.call(SCOPE_META, v);

/* Confidence, as the pipeline reports it. Three states, no fourth: an
   unrecognised value means "we don't know what this is", which renders no
   advisory at all rather than a guessed label (see normalizeAdvisory).
   `filled` is how many of the three meter segments light up — the count, not
   the colour, is what carries the state, so it survives greyscale and
   colour-blindness. */
const CONFIDENCE_META = {
  high: { label: "High", filled: 3 },
  moderate: { label: "Moderate", filled: 2 },
  low: { label: "Low", filled: 1 },
};
const isConfidence = (v) => Object.prototype.hasOwnProperty.call(CONFIDENCE_META, v);

/* Readable names for the regime keys routing.py emits. Same convention as
   KNOWN_MODEL_NAMES below: a known key gets the phrasing a lawyer would use,
   an unknown one gets a readable de-slugged fallback rather than a wrong
   label or a raw "drug-regulatory" leaking onto the screen. */
const REGIME_LABELS = {
  patent: "Patent law",
  trademark: "Trade mark law",
  gi: "Geographical indications",
  design: "Industrial designs",
  copyright: "Copyright",
  "plant-variety": "Plant varieties and farmers' rights",
  "trade-secret": "Trade secrets and confidential information",
  abs: "Access and benefit-sharing",
  tk: "Traditional-knowledge protection",
  "drug-regulatory": "Drug regulation and licensing",
  "food-cosmetic": "Food and cosmetic regulation",
};
const regimeLabel = (r) =>
  REGIME_LABELS[r] || String(r).replace(/[-_]+/g, " ").replace(/^\w/, (c) => c.toUpperCase());

let conversations = loadStore();
let scope = loadScope();
let activeId = null;
let stream = null;
let busy = false;

/* ───────── helpers ───────── */

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const uid = () => Math.random().toString(36).slice(2, 10);
const nearBottom = () => thread.scrollHeight - thread.scrollTop - thread.clientHeight < 160;
const toBottom = (force = false) => { if (force || nearBottom()) thread.scrollTop = thread.scrollHeight; };

function loadStore() {
  try { return JSON.parse(localStorage.getItem(STORE_KEY)) || []; }
  catch { return []; }
}
function saveStore() {
  try { localStorage.setItem(STORE_KEY, JSON.stringify(conversations.slice(0, 40))); }
  catch { /* private mode / quota — history is a convenience, not load-bearing */ }
}

function loadScope() {
  // Same shape as loadStore above: any storage failure (private mode, blocked
  // site data) falls back to the unfiltered default rather than throwing, and
  // an unrecognised stored value is treated as unset.
  try {
    const v = localStorage.getItem(SCOPE_KEY);
    return isScope(v) ? v : "all";
  } catch { return "all"; }
}
function saveScope(v) {
  try { localStorage.setItem(SCOPE_KEY, v); }
  catch { /* private mode / quota — the choice still holds for this session */ }
}

// Paints the jurisdiction stamp on one answer. `value` is the scope that
// answer actually ran under, never the live control: an unrecognised or
// missing value (a conversation stored before this feature existed, replayed
// from localStorage) renders nothing at all rather than claiming a scope that
// was never applied — same convention as coverageHTML.
function paintScopeTag(el, value) {
  if (!el) return;
  if (!isScope(value)) { el.hidden = true; return; }
  const meta = SCOPE_META[value];
  el.className = `scope-tag scope-tag-${value}`;
  el.innerHTML = `<span class="sr-only">Sources used — </span>${esc(meta.tag)}`;
  el.title = meta.full;
  el.hidden = false;
}

function tierClass(level = "") {
  const l = level.toLowerCase();
  return l.includes("act") ? "act" : l.includes("guideline") ? "guideline" : "informational";
}

/* ───────── conversation state ───────── */

function activeConv() { return conversations.find((c) => c.id === activeId); }

function newConversation() {
  if (busy) return;
  activeId = null;
  thread.innerHTML = "";
  thread.appendChild(empty);
  empty.hidden = false;
  chatTitle.textContent = "New consultation";
  renderHistory();
  input.focus();
}

function ensureConversation(firstQuestion) {
  if (activeConv()) return activeConv();
  const conv = {
    id: uid(),
    title: firstQuestion.length > 52 ? firstQuestion.slice(0, 52).trim() + "…" : firstQuestion,
    at: Date.now(),
    turns: [],
  };
  conversations.unshift(conv);
  activeId = conv.id;
  chatTitle.textContent = conv.title;
  renderHistory();
  return conv;
}

function renderHistory() {
  if (!conversations.length) { historyEl.innerHTML = ""; return; }
  historyEl.innerHTML =
    `<p class="history-label">Recent</p>` +
    conversations
      .map((c) => `<button class="hist-item${c.id === activeId ? " active" : ""}" data-id="${c.id}">
          <span>${esc(c.title)}</span></button>`)
      .join("");
  $$(".hist-item", historyEl).forEach((b) =>
    b.addEventListener("click", () => openConversation(b.dataset.id)));
}

function openConversation(id) {
  if (busy) return;
  const conv = conversations.find((c) => c.id === id);
  if (!conv) return;
  activeId = id;
  chatTitle.textContent = conv.title;
  empty.hidden = true;
  thread.innerHTML = "";
  conv.turns.forEach((t) => {
    thread.appendChild(userMessage(t.q));
    thread.appendChild(replayAssistant(t.result, t.meta));
  });
  renderHistory();
  toBottom(true);
}

/* ───────── message construction ───────── */

function userMessage(text) {
  const el = document.createElement("article");
  el.className = "msg msg-user";
  el.innerHTML = `<div class="avatar">You</div><div><p class="q">${esc(text)}</p></div>`;
  return el;
}

function botShell() {
  const el = document.createElement("article");
  el.className = "msg msg-bot";
  el.innerHTML = `
    <div class="avatar">
      <svg viewBox="0 0 24 24" fill="none"><path d="M12 2.5 20.5 7v10L12 21.5 3.5 17V7z"/><path d="m8.2 12.1 2.6 2.7 5-5.6"/></svg>
    </div>
    <div class="msg-body"></div>`;
  return el;
}

function attachPipeline(body, scopeValue) {
  const node = $("#tpl-pipeline").content.cloneNode(true);
  body.appendChild(node);
  const verify = $(".verify", body);
  $(".verify-summary", verify).addEventListener("click", () =>
    verify.classList.toggle("collapsed"));
  // Stamped up front, not on completion: while the pipeline is still running
  // it says which instruments are being searched, and it is the same element
  // that remains as the answer's permanent scope label afterwards.
  paintScopeTag($("[data-scope-tag]", verify), scopeValue);
  return verify;
}

/* ───────── answer rendering (shared by live + replay) ───────── */

function answerHTML(res) {
  const discarded = res.discarded || [];
  if (res.refused) {
    return `
      <div class="refusal">
        <div class="refusal-icon"><svg viewBox="0 0 24 24" fill="none"><path d="M12 8v5m0 3.5v.01"/><circle cx="12" cy="12" r="9"/></svg></div>
        <div>
          <h4>Not enough grounded support to answer</h4>
          <p>${esc(res.answer)}</p>
          <p class="why">${esc(res.why || "")}</p>
        </div>
      </div>
      ${discardedHTML(discarded)}`;
  }
  return `
    <div class="answer">
      ${res.claims.map((c, i) => `
        <div class="claim" style="animation-delay:${i * 80}ms">
          <p class="claim-text">${esc(c.text)}</p>
          <button class="cite-pill" type="button" data-src="${esc(c.source ?? "")}">${esc(c.citation)}</button>
        </div>`).join("")}
    </div>
    ${coverageHTML(res)}
    ${sourcesHTML(res.sources || [])}
    ${discardedHTML(discarded)}`;
}

function coverageHTML(res) {
  // res.coverage is undefined for any conversation stored before this
  // feature existed (replayed from localStorage), and null whenever the
  // check failed open — both cases render nothing, same as "not assessed".
  if (!res.coverage || res.coverage.addresses !== false) return "";
  return `
    <div class="coverage-note">
      <strong>May not fully answer your question.</strong> ${esc(res.coverage.gap || "")}
    </div>`;
}

/* ───────── advisory (commentary ABOUT an answer) ─────────
   The terminal `advisory` event — disclaimer, confidence, escalation offer,
   out-of-coverage regimes, TKDL pointer. Deliberately rendered as its own
   block BELOW the answer and never inside it: none of it is a verified claim
   drawn from a passage, and styling it like one would be the exact
   misrepresentation this tool exists to avoid. Nothing here is wired to JS
   behaviour (the escalation panel is a native <details>, the contacts are
   plain links), so a replayed thread renders identically to a live one. */

// Anything that isn't a well-formed advisory becomes null, and null renders
// nothing at all. A conversation stored before this event existed has no
// meta.advisory and lands here too — same convention as paintScopeTag and
// coverageHTML: silence rather than a label that was never actually emitted.
function normalizeAdvisory(ev) {
  if (!ev || typeof ev !== "object" || !isConfidence(ev.confidence)) return null;

  const strList = (v) =>
    Array.isArray(v) ? v.filter((s) => typeof s === "string" && s.trim()) : [];

  const g = ev.escalation_guidance;
  const guidance = g && typeof g === "object" ? {
    summary: typeof g.summary === "string" ? g.summary : "",
    contacts: (Array.isArray(g.contacts) ? g.contacts : [])
      .filter((c) => c && typeof c === "object")
      .map((c) => ({ who: String(c.who ?? ""), when: String(c.when ?? ""), where: String(c.where ?? "") }))
      .filter((c) => c.who),
  } : null;

  const p = ev.prior_art_pointer;
  const pointer = p && typeof p === "object" && typeof p.pointer === "string" && p.pointer.trim()
    // Defaults to "not searchable" on anything other than an explicit true:
    // the failure that matters here is claiming a TKDL search happened.
    ? { pointer: p.pointer, searchable_by_this_tool: p.searchable_by_this_tool === true }
    : null;

  return {
    disclaimer: typeof ev.disclaimer === "string" ? ev.disclaimer : "",
    confidence: ev.confidence,
    escalate: ev.escalate === true,
    escalation_reasons: strList(ev.escalation_reasons),
    escalation_guidance: guidance,
    regimes_out_of_coverage: strList(ev.regimes_out_of_coverage),
    prior_art_pointer: pointer,
  };
}

// A contact's `where` is rendered as a link only if it really is an http(s)
// URL; anything else prints as text. The advisory comes from our own backend,
// but a link is the one thing on this block a user will click without reading.
function safeUrl(u) {
  try {
    const p = new URL(String(u), location.href);
    return p.protocol === "https:" || p.protocol === "http:" ? p.href : null;
  } catch { return null; }
}

function confidenceHTML(adv) {
  const meta = CONFIDENCE_META[adv.confidence];
  const segs = [0, 1, 2].map((i) => `<i${i < meta.filled ? ' class="on"' : ""}></i>`).join("");
  return `
    <div class="advisory-top">
      <span class="conf conf-${adv.confidence}">
        <span class="sr-only">Confidence in this answer — </span>
        <span class="conf-key">Confidence</span>
        <span class="conf-meter" aria-hidden="true">${segs}</span>
        <span class="conf-val">${meta.label}</span>
      </span>
      <p class="conf-note">How closely the retrieved passages matched the question — not a judgement that the answer is right.</p>
    </div>`;
}

// Out of coverage = a body of law this case touches and this corpus has no
// source for. Full block with a heading, not a footnote: the user is being
// told that part of their question is unanswered here, which is materially
// different from the answer being incomplete.
function outOfCoverageHTML(regimes) {
  if (!regimes.length) return "";
  return `
    <div class="no-coverage">
      <h4>This question also touches law this tool has no sources for</h4>
      <ul class="regime-list">
        ${regimes.map((r) => `<li>${esc(regimeLabel(r))}</li>`).join("")}
      </ul>
      <p>Nothing above is drawn from ${regimes.length === 1 ? "it" : "them"}. Treat that part of the question as unanswered here, not as settled.</p>
    </div>`;
}

// Rendered in full, never clamped or summarised: the pointer's whole point is
// the sentence at the end about fabricated TKDL record numbers.
function priorArtHTML(p) {
  if (!p) return "";
  return `
    <div class="prior-art">
      <p class="prior-art-key">
        <span>Traditional-knowledge prior art</span>
        ${p.searchable_by_this_tool ? "" : `<span class="prior-art-flag">not searchable by this tool</span>`}
      </p>
      <p class="prior-art-text">${esc(p.pointer)}</p>
    </div>`;
}

// Collapsed by default. It is an offer, not a warning — it should be findable
// on the answers that warrant it without shouting on any of them.
function escalationHTML(adv) {
  if (!adv.escalate) return "";
  const reasons = adv.escalation_reasons;
  const guidance = adv.escalation_guidance;
  if (!reasons.length && !guidance) return "";
  const contacts = guidance?.contacts || [];
  return `
    <details class="acc acc-escalate">
      <summary><span class="caret">›</span> Worth putting to a person${reasons.length ? ` — ${reasons.length} reason${reasons.length === 1 ? "" : "s"}` : ""}</summary>
      ${guidance?.summary ? `<p class="escalate-lede">${esc(guidance.summary)}</p>` : ""}
      ${reasons.length ? `
        <p class="escalate-key">Why this came up</p>
        <ul class="escalate-why">${reasons.map((r) => `<li>${esc(r)}</li>`).join("")}</ul>` : ""}
      ${contacts.length ? `
        <p class="escalate-key">Who to ask</p>
        <div class="contacts">
          ${contacts.map((c) => {
            const href = safeUrl(c.where);
            return `
            <div class="contact">
              <p class="contact-who">${esc(c.who)}</p>
              ${c.when ? `<p class="contact-when">${esc(c.when)}</p>` : ""}
              ${c.where ? (href
                ? `<a class="contact-where" href="${esc(href)}" target="_blank" rel="noopener">${esc(c.where)}</a>`
                : `<p class="contact-where-plain">${esc(c.where)}</p>`) : ""}
            </div>`;
          }).join("")}
        </div>` : ""}
    </details>`;
}

function advisoryHTML(adv) {
  if (!adv) return "";
  return `
    <section class="advisory" aria-label="About this answer">
      ${confidenceHTML(adv)}
      ${outOfCoverageHTML(adv.regimes_out_of_coverage)}
      ${priorArtHTML(adv.prior_art_pointer)}
      ${escalationHTML(adv)}
      ${adv.disclaimer ? `<p class="advisory-disclaimer">${esc(adv.disclaimer)}</p>` : ""}
    </section>`;
}

// Always lands immediately above the action buttons, wherever it arrives from
// — the advisory event precedes `complete` on an answer but follows `refused`
// on both refusal paths, so this is called both before and after the answer
// itself has been painted.
function renderAdvisory(body, adv) {
  const html = advisoryHTML(adv);
  if (!html || $(".advisory", body)) return;
  const actions = $(".msg-actions", body);
  if (actions) actions.insertAdjacentHTML("beforebegin", html);
  else body.insertAdjacentHTML("beforeend", html);
}

function sourcesHTML(sources) {
  if (!sources.length) return "";
  return `
    <details class="acc acc-sources">
      <summary><span class="caret">›</span> Sources consulted (${sources.length})</summary>
      ${sources.map((s) => `
        <article class="source" data-src-index="${s.index}">
          <div class="source-top">
            <span class="tier tier-${tierClass(s.authority_level)}">${esc(s.authority_level)}</span>
            ${s.section_number ? `<span class="source-sec">§${esc(s.section_number)}</span>` : ""}
            <span class="source-date">${esc(s.effective_date)}</span>
          </div>
          <p class="source-name">${esc(s.short_name)}</p>
          <p class="source-text">${esc(s.text)}</p>
          <button class="source-more" type="button">Show full passage</button>
        </article>`).join("")}
    </details>`;
}

function discardedHTML(discarded) {
  if (!discarded.length) return "";
  return `
    <details class="acc">
      <summary><span class="caret">›</span> What this answer left out (${discarded.length})</summary>
      ${discarded.map((d) => `
        <div class="discarded-item">
          <p class="dropped">${esc(d.text)}</p>
          <p class="why">Dropped — ${esc(d.reason)}</p>
        </div>`).join("")}
    </details>`;
}

function actionsHTML() {
  return `
    <div class="msg-actions">
      <button class="act-btn copy-btn" type="button">
        <svg viewBox="0 0 24 24"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/></svg>
        Copy with citations
      </button>
      <button class="act-btn translate-btn" type="button">
        <svg viewBox="0 0 24 24"><path d="M4 6h9M8 3v3m0 0c0 4-2.5 7-6 8.5M8 6c1.4 2.6 3.5 4.5 6 5.7M13 21l4-9 4 9M14.5 18h5"/></svg>
        <span class="translate-label">हिंदी में देखें</span>
      </button>
    </div>`;
}

function wireAnswer(body, res) {
  $$(".source-more", body).forEach((btn) =>
    btn.addEventListener("click", () => {
      const card = btn.closest(".source");
      btn.textContent = card.classList.toggle("expanded") ? "Collapse" : "Show full passage";
    }));

  $$(".cite-pill", body).forEach((pill) =>
    pill.addEventListener("click", () => {
      const acc = $(".acc-sources", body);
      if (acc) acc.open = true;
      const card = $(`.source[data-src-index="${pill.dataset.src}"]`, body);
      if (!card) return;
      card.scrollIntoView({ behavior: "smooth", block: "center" });
      card.classList.add("flash");
      setTimeout(() => card.classList.remove("flash"), 1100);
    }));

  const answerText = () =>
    res.refused ? res.answer : res.claims.map((c) => `${c.text} ${c.citation}`).join("\n\n");

  const copy = $(".copy-btn", body);
  if (copy) copy.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(answerText());
      copy.classList.add("copied");
      copy.lastChild.textContent = " Copied";
      setTimeout(() => { copy.classList.remove("copied"); copy.lastChild.textContent = " Copy with citations"; }, 1600);
    } catch { /* clipboard blocked — nothing useful to do */ }
  });

  const translateBtn = $(".translate-btn", body);
  if (translateBtn) translateBtn.addEventListener("click", () => translateAnswer(body, translateBtn, answerText()));
}

async function translateAnswer(body, btn, text) {
  let panel = $(".translation", body);

  // Already fetched once — this click is just a show/hide toggle, no refetch.
  if (panel) {
    const showing = panel.hidden;
    panel.hidden = !showing;
    $(".translate-label", btn).textContent = showing ? "अंग्रेज़ी में देखें" : "हिंदी में देखें";
    return;
  }

  if (btn.disabled) return;
  btn.disabled = true;
  const label = $(".translate-label", btn);
  const originalLabel = label.textContent;
  label.textContent = "अनुवाद हो रहा है…";

  try {
    const res = await fetch("/api/translate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, language: "Hindi" }),
    });
    if (!res.ok) throw new Error(String(res.status));
    const { translated } = await res.json();

    panel = document.createElement("div");
    panel.className = "translation";
    panel.innerHTML = `
      <p class="translation-note">मशीन अनुवाद — मूल अंग्रेज़ी उत्तर के आधार पर, स्रोत के विरुद्ध स्वतंत्र रूप से सत्यापित नहीं (Machine translation of the verified English answer — not independently re-checked against the source).</p>
      <p class="translation-text"></p>`;
    $(".translation-text", panel).textContent = translated;
    body.insertBefore(panel, $(".msg-actions", body));
    label.textContent = "अंग्रेज़ी में देखें";
  } catch {
    label.textContent = originalLabel;
    btn.classList.add("translate-error");
    setTimeout(() => btn.classList.remove("translate-error"), 1600);
  } finally {
    btn.disabled = false;
  }
}

function replayAssistant(res, meta = {}) {
  const el = botShell();
  const body = $(".msg-body", el);
  body.innerHTML = `
    <div class="verify collapsed">
      <button class="verify-summary${res.refused ? " warn" : ""}" type="button">
        <span class="vs-text">${esc(meta.summary || (res.refused ? "Refused — not grounded" : "Verified"))}</span>
        <span class="caret">›</span>
      </button>
      <span class="scope-tag" data-scope-tag hidden></span>
    </div>
    ${answerHTML(res)}
    ${advisoryHTML(normalizeAdvisory(meta.advisory))}
    ${actionsHTML()}`;
  paintScopeTag($("[data-scope-tag]", body), meta.scope);
  wireAnswer(body, res);
  return el;
}

/* ───────── live run ───────── */

function ask(question) {
  if (busy) return;
  // A previous run's stream can still be open here — a refusal holds it for a
  // beat waiting on its advisory (see closeStream) — and an EventSource left
  // dangling would reconnect and re-run that old question.
  if (stream) { stream.close(); stream = null; }
  busy = true;
  sendBtn.disabled = true;
  empty.hidden = true;

  // Read once, here. Everything downstream — the request, the stamp on the
  // answer, the record written to localStorage — uses this snapshot, so
  // changing the control mid-run can't retroactively relabel an answer.
  const askScope = scope;

  const conv = ensureConversation(question);
  thread.appendChild(userMessage(question));

  const msg = botShell();
  const body = $(".msg-body", msg);
  thread.appendChild(msg);
  const verify = attachPipeline(body, askScope);
  toBottom(true);

  const stepEl = (n) => $(`.step[data-step="${n}"]`, verify);
  const setStep = (n, state, detail) => {
    const el = stepEl(n);
    if (!el) return;
    el.classList.remove("active", "done", "failed");
    if (state) el.classList.add(state);
    if (detail) {
      const d = $("[data-detail]", el);
      d.textContent = detail;
      d.classList.add("data");
    }
  };

  const t0 = performance.now();
  const timeEl = $("[data-elapsed]", verify);
  const timer = setInterval(() => {
    timeEl.textContent = ((performance.now() - t0) / 1000).toFixed(1) + "s";
  }, 100);

  let drafted = 0;
  let sources = [];
  // The advisory is terminal but its position relative to the terminal event
  // differs by path: BEFORE `complete` on a successful answer, AFTER
  // `refused` on both refusal paths. Rather than depend on that ordering,
  // whichever arrives second paints/records what the first one left pending.
  let advisory = null;
  let pushedTurn = null;
  let closeTimer = null;

  // Last few turns of THIS conversation, sent so a follow-up ("what about
  // for Unani?") can be rewritten into a standalone question before
  // retrieval — see generate._condense_followup. Empty on a fresh
  // conversation's first question, so nothing changes for a one-off ask.
  const historyPayload = conv.turns.slice(-3).map((t) => ({ q: t.q, a: t.result.answer }));
  const hasHistory = historyPayload.length > 0;
  if (hasHistory) $('.step[data-step="condense"]', verify).hidden = false;
  setStep(hasHistory ? "condense" : "retrieval", "active");

  const historyParam = hasHistory ? `&history=${encodeURIComponent(JSON.stringify(historyPayload))}` : "";
  // "All sources" sends no param at all rather than jurisdiction=all — the
  // API treats an absent (or unrecognised) value as "no filter", so omitting
  // it is the literal request, not a shorthand for one.
  const scopeParam = askScope === "all" ? "" : `&jurisdiction=${encodeURIComponent(askScope)}`;
  // Captured locally as well as globally: a refusal now leaves this stream
  // open for a beat (see finish/closeStream below) while the advisory that
  // follows it arrives, so the close has to target THIS EventSource even if
  // another question has started in the meantime.
  const es = new EventSource(`/api/ask?q=${encodeURIComponent(question)}${historyParam}${scopeParam}`);
  stream = es;

  es.onmessage = (m) => {
    const ev = JSON.parse(m.data);

    if (ev.type === "stage" && ev.stage === "condense" && ev.status === "done") {
      setStep("condense", "done",
        ev.meta.rewritten ? `Interpreted as: “${ev.meta.standalone_question}”` : "Already a standalone question");
    }

    if (ev.type === "stage" && ev.stage === "retrieval" && ev.status === "start") {
      setStep("retrieval", "active");
    }

    if (ev.type === "stage" && ev.stage === "retrieval" && ev.status === "done") {
      setStep("retrieval", "done", `${ev.meta.candidates_examined} passages examined · ${ev.meta.selected} carried forward`);
      setStep("gate", "active");
    }

    if (ev.type === "stage" && ev.stage === "gate" && ev.status === "done") {
      const { best_distance: best, threshold, passed } = ev.meta;
      if (best != null) {
        const g = $("[data-gauge]", verify);
        g.hidden = false;
        g.classList.toggle("over", !passed);
        countUp($("[data-gauge-value]", verify), best);
        $("[data-gauge-threshold]", verify).textContent = threshold.toFixed(2);
        requestAnimationFrame(() => {
          $("[data-gauge-fill]", verify).style.width =
            Math.min(100, (best / (threshold * 1.25)) * 100) + "%";
        });
      }
      setStep("gate", passed ? "done" : "failed",
        `best match ${best.toFixed(3)} — ${passed ? "clears" : "misses"} the ${threshold.toFixed(2)} limit`);
      // Deliberately doesn't activate "relevance" or "generation" here — the
      // relevance stage is off by default (see docs/decisions.md: it made
      // the false-refusal rate worse in testing) and may not run at all, so
      // each step activates itself from its own "start" event instead of
      // being chained from the step before it.
    }

    if (ev.type === "stage" && ev.stage === "relevance" && ev.status === "start") {
      stepEl("relevance").hidden = false;
      setStep("relevance", "active");
    }

    if (ev.type === "stage" && ev.stage === "relevance" && ev.status === "done") {
      setStep("relevance", "done",
        ev.meta.failed_open
          ? `Screening unavailable — all ${ev.meta.total} passages carried forward`
          : `${ev.meta.kept} of ${ev.meta.total} passages kept${ev.meta.dropped ? ` · ${ev.meta.dropped} set aside as off-topic` : ""}`);
    }

    if (ev.type === "sources") sources = ev.sources;

    if (ev.type === "advisory") {
      advisory = normalizeAdvisory(ev);
      // Arrived after the answer was already painted (the refusal paths):
      // append it now and amend the record already written to localStorage,
      // so a reload of this same thread shows what the live run showed.
      if (pushedTurn) {
        if (advisory) {
          renderAdvisory(body, advisory);
          pushedTurn.meta.advisory = advisory;
          saveStore();
          toBottom();
        }
        // Nothing further is coming on this stream, and leaving it open would
        // let EventSource re-open it and silently re-run the question.
        closeStream();
      }
    }

    if (ev.type === "stage" && ev.stage === "generation" && ev.status === "start") {
      setStep("generation", "active");
    }

    if (ev.type === "stage" && ev.stage === "generation" && ev.status === "done") {
      drafted = ev.meta.drafted;
      setStep("generation", drafted ? "done" : "failed",
        drafted ? `${drafted} claim${drafted === 1 ? "" : "s"} drafted, each bound to one passage`
                : "0 claims drafted — declined to assert anything the passages don't support");
      if (drafted) setStep("verification", "active");
    }

    if (ev.type === "claim") {
      const li = document.createElement("li");
      li.className = "claim-check";
      li.dataset.idx = ev.index;
      li.innerHTML = `<p>${esc(ev.text)}</p><span class="verdict checking"><span class="spinner"></span>checking</span>`;
      $("[data-checks]", verify).appendChild(li);
      toBottom();
    }

    if (ev.type === "claim_result") {
      const li = $(`.claim-check[data-idx="${ev.index}"]`, verify);
      if (li) {
        li.classList.add(ev.supported ? "pass" : "fail");
        const tally = ev.votes?.length ? ` ${ev.votes.filter(Boolean).length}/${ev.votes.length}` : "";
        $(".verdict", li).outerHTML = ev.supported
          ? `<span class="verdict pass">✓ verified${tally}</span>`
          : `<span class="verdict fail">✕ unsupported</span>`;
      }
      toBottom();
    }

    if (ev.type === "stage" && ev.stage === "coverage" && ev.status === "start") {
      setStep("cite", "done", "Citations resolved by authority and date");
      setStep("coverage", "active");
    }

    if (ev.type === "stage" && ev.stage === "coverage" && ev.status === "done") {
      setStep("coverage", "done",
        !ev.meta.available ? "Not assessed"
        : ev.meta.addresses ? "Addresses the question as asked"
        : `May not fully cover: ${ev.meta.gap}`);
    }

    if (ev.type === "complete" || ev.type === "refused") {
      const res = ev.result;
      res.sources = sources;
      const secs = ((performance.now() - t0) / 1000).toFixed(1);

      let summary;
      if (ev.type === "complete") {
        setStep("verification", "done",
          `${res.claims.length} upheld · ${(res.discarded || []).length} discarded`);
        setStep("cite", "done", "Citations resolved by authority and date");
        summary = `✓ Verified · ${res.claims.length} claim${res.claims.length === 1 ? "" : "s"} upheld` +
          ((res.discarded || []).length ? ` · ${res.discarded.length} discarded` : "") +
          (res.coverage && res.coverage.addresses === false ? ` · may not fully answer` : "") +
          ` · ${sources.length} source${sources.length === 1 ? "" : "s"} · ${secs}s`;
      } else {
        const atGate = ev.refusal_stage === "gate";
        // Distinguishing "nothing was asserted" from "what was asserted failed"
        // matters — claiming Layer 2 struck claims down when none were ever
        // drafted would be a better story than the truth.
        res.why = atGate
          ? "Stopped at Layer 1 — no passage came close enough to the question to answer from."
          : drafted === 0
          ? "Stopped before Layer 2 — passages were retrieved, but none supported a specific answer, so nothing was asserted rather than filling the gap."
          : "Stopped at Layer 2 — claims were drafted, but none survived checking against the passage they cited.";
        if (atGate) {
          setStep("relevance", null, "Skipped — nothing confident enough to screen");
          setStep("generation", null, "Skipped — nothing confident enough to draft from");
          setStep("verification", null, "Skipped");
        } else if (drafted === 0) {
          setStep("verification", null, "Skipped — nothing was asserted to verify");
        } else {
          setStep("verification", "failed", "No claim survived verification");
        }
        setStep("cite", null, "Skipped — nothing to cite");
        setStep("coverage", null, "Skipped — no answer to check");
        summary = `Refused · ${atGate ? "no confident match" : "nothing verifiable"} · ${secs}s`;
      }

      clearInterval(timer);
      const sumBtn = $(".verify-summary", verify);
      sumBtn.hidden = false;
      sumBtn.classList.toggle("warn", ev.type === "refused");
      $(".vs-text", sumBtn).textContent = summary;
      setTimeout(() => verify.classList.add("collapsed"), 900);

      body.insertAdjacentHTML("beforeend",
        answerHTML(res) + advisoryHTML(advisory) + actionsHTML());
      wireAnswer(body, res);
      pushedTurn = { q: question, result: res, meta: { summary, scope: askScope, advisory } };
      conv.turns.push(pushedTurn);
      conv.at = Date.now();
      saveStore();
      // A refusal is not the last event on the wire: the advisory follows it,
      // and closing here would drop the disclaimer and the escalation offer
      // on exactly the answers that need them most. The composer is released
      // now either way; only the socket waits, and only briefly.
      finish({ keepStream: ev.type === "refused" });
      if (ev.type === "refused") closeTimer = setTimeout(closeStream, 4000);
      toBottom();
    }

    // A third, distinct terminal state — NOT the grounding refusal above,
    // and NOT a raw pipeline error below: the LLM provider itself (Gemini's
    // free tier in production) reported a rate-limit/quota condition, so
    // nothing was fabricated and nothing about the corpus was judged. Own
    // markup/color (blue, not the refusal's amber) on purpose, so it never
    // reads as "not enough grounded information".
    if (ev.type === "provider_unavailable") {
      clearInterval(timer);
      const sumBtn = $(".verify-summary", verify);
      sumBtn.hidden = false;
      sumBtn.classList.add("busy");
      $(".vs-text", sumBtn).textContent = `Service busy · ${((performance.now() - t0) / 1000).toFixed(1)}s`;
      body.insertAdjacentHTML("beforeend", `
        <div class="provider-unavailable">
          <div class="provider-unavailable-icon"><svg viewBox="0 0 24 24" fill="none"><path d="M12 7v5l3.3 2"/><circle cx="12" cy="12" r="9"/></svg></div>
          <div><h4>Temporarily unavailable</h4><p>${esc(ev.message)}</p></div>
        </div>`);
      finish();
      toBottom();
    }

    if (ev.type === "error") {
      clearInterval(timer);
      body.insertAdjacentHTML("beforeend", `
        <div class="refusal"><div class="refusal-icon"><svg viewBox="0 0 24 24" fill="none"><path d="M12 8v5m0 3.5v.01"/><circle cx="12" cy="12" r="9"/></svg></div>
        <div><h4>Pipeline error</h4><p>${esc(ev.message)}</p>
        <p class="why">Check that Ollama is running with qwen2.5:7b pulled.</p></div></div>`);
      finish();
    }
  };

  // Also the path taken when the server closes the connection normally after
  // the last event: closing unconditionally here is what stops EventSource
  // from reconnecting and re-running the question behind the user's back.
  es.onerror = () => {
    clearInterval(timer);
    if (busy) finish();
    else closeStream();
  };

  function closeStream() {
    if (closeTimer) { clearTimeout(closeTimer); closeTimer = null; }
    es.close();
    if (stream === es) stream = null;
  }

  function finish({ keepStream = false } = {}) {
    busy = false;
    sendBtn.disabled = false;
    if (!keepStream) closeStream();
  }
}

function countUp(el, to, decimals = 3, ms = 700) {
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) {
    el.textContent = to.toFixed(decimals); return;
  }
  const t0 = performance.now();
  const tick = (now) => {
    const p = Math.min(1, (now - t0) / ms);
    el.textContent = (to * (1 - Math.pow(1 - p, 3))).toFixed(decimals);
    if (p < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

/* ───────── model badge ───────── */

const KNOWN_MODEL_NAMES = {
  "qwen2.5:7b": "Qwen 2.5 7B",
  "llama3.1:8b": "Llama 3.1 8B",
  "gemma2:2b": "Gemma 2 2B",
};

function formatModelName(raw) {
  if (KNOWN_MODEL_NAMES[raw]) return KNOWN_MODEL_NAMES[raw];
  // Unrecognized model id — fall back to a readable guess rather than a
  // hardcoded name, so an operator swapping OLLAMA_MODEL/ANTHROPIC_MODEL
  // always sees *something* accurate instead of a stale label.
  return raw.replace(/[:_-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

// "local (Ollama)" is only true for the Ollama provider — once deployed
// with LLM_PROVIDER=anthropic this is a cloud API, so the badge must say
// so instead of carrying "local" over by mistake.
const PROVIDER_LABELS = { ollama: "local (Ollama)", anthropic: "Anthropic API", gemini: "Gemini API" };

// The "Known limitations" modal's first bullet is the one fact that changes
// with whichever provider is actually configured (see index.html's
// #limit-provider, README's Known limitations section). Built from
// /api/config's real {model, provider} rather than hardcoded, so it can
// never go stale once this is deployed with a real Gemini/Anthropic key —
// see loadModelBadge() below, which is the only caller. The other bullets
// in that modal (over-refusal framing, follow-up resolution, statutory
// vocabulary, Hindi-via-translation, not-production-scale) don't depend on
// the provider and stay static in index.html — no reason to make those
// dynamic too.
function limitationsProviderText(model, provider) {
  const modelLabel = formatModelName(model);
  if (provider === "ollama") {
    // The 5/11 false-refusal number was measured specifically against this
    // local model (see README's Known limitations) — safe to state as-is
    // only in the case that actually produced it.
    return `<b>Local model substitution.</b> Verification and generation run on a local ${esc(modelLabel)} via Ollama, not the Claude API this was scoped for. Measured cost: a 5/11 false-refusal rate on answerable evaluation questions.`;
  }
  // A cloud provider is active: "local model substitution" and the 5/11
  // figure (both specific to the Ollama dev setup) would be false here, so
  // this names the real active model instead of repeating either claim.
  const providerLabel = PROVIDER_LABELS[provider] || provider;
  return `<b>Model in use.</b> Verification and generation run on ${esc(modelLabel)} via the ${esc(providerLabel)}. The false-refusal and citation-accuracy numbers elsewhere in this app were measured during development against the local Ollama model, not yet re-measured on this provider.`;
}

async function loadModelBadge() {
  const modelEl = $("#model-name");
  const corpusEl = $("#corpus-count");
  const limitEl = $("#limit-provider");
  const scopeCountEl = $("#scope-counts");
  try {
    const res = await fetch("/api/config");
    if (!res.ok) throw new Error(String(res.status));
    const { model, provider, corpus_docs, jurisdictions } = await res.json();
    modelEl.textContent = `${formatModelName(model)} · ${PROVIDER_LABELS[provider] || provider}`;
    corpusEl.textContent = `${corpus_docs} primary source${corpus_docs === 1 ? "" : "s"} indexed`;
    // Counted server-side from the same document registry the retrieval
    // filter uses, so the split shown next to the toggle is always the split
    // the toggle actually produces. Left blank (and hidden by CSS) if an
    // older server doesn't report it — never a guessed or hardcoded number.
    if (scopeCountEl && jurisdictions) {
      scopeCountEl.textContent =
        `${jurisdictions.india} Indian · ${jurisdictions.international} international`;
    }
    if (limitEl) limitEl.innerHTML = limitationsProviderText(model, provider);
  } catch {
    modelEl.textContent = "Model unavailable — is the server running?";
    $("#model-note .dot-model")?.classList.add("down");
    corpusEl.textContent = "Corpus status unavailable";
    // limitEl is deliberately left untouched on failure — index.html's
    // static fallback text (accurate for the default local-dev setup)
    // stays visible rather than being replaced with something guessed.
  }
}

/* ───────── splash ───────── */

// Rotating micro-copy under the progress bar — decoration layered on top of
// the real wait below, never a reason to extend it (see hideSplash, which
// clears this on the same real-readiness condition it already used). Each
// line names something the boot sequence plausibly is doing: the page's own
// pipeline-shaped UI is being built, and loadModelBadge()'s /api/config call
// (fired alongside this) is literally connecting to the model and reading
// the corpus count — not invented copy disconnected from the actual init
// sequence.
const SPLASH_STATUS_LINES = [
  "Loading the verification pipeline…",
  "Connecting to the model…",
  "Checking the corpus index…",
];
let splashStatusTimer = null;
function startSplashStatusCycle() {
  const statusEl = $("#splash-status");
  // Reduced motion: skip the cycle entirely and leave the first line
  // (already in the static HTML) showing — cycling text is motion too, even
  // without a CSS animation driving it, so it gets the same opt-out as the
  // staggered entrance below.
  if (!statusEl || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  let i = 0;
  splashStatusTimer = setInterval(() => {
    i = (i + 1) % SPLASH_STATUS_LINES.length;
    statusEl.textContent = SPLASH_STATUS_LINES[i];
  }, 1000);
}
startSplashStatusCycle();

// "Ready" = the DOM this script runs against is already built (this file is
// a plain, non-deferred <script> at the end of <body>, so that's true the
// moment this runs) AND the first real network round-trip — the same
// /api/config fetch loadModelBadge() already needs for the sidebar badges —
// has settled, success or failure. A floor of 400ms keeps it from flashing
// uselessly when the server's already warm; it never waits longer than that
// on its own, only until the real fetch resolves.
let splashDone = false;
function hideSplash() {
  if (splashDone) return;
  splashDone = true;
  if (splashStatusTimer) { clearInterval(splashStatusTimer); splashStatusTimer = null; }
  const splash = $("#splash");
  if (!splash) return;
  const wait = Math.max(0, 400 - (performance.now() - splashT0));
  setTimeout(() => {
    splash.classList.add("hide");
    splash.addEventListener("transitionend", () => splash.remove(), { once: true });
  }, wait);
}
// Safety net only — if the backend is up but never answers (not the
// "resolves for real" condition itself, just a backstop so a broken
// deployment can't strand a visitor behind the splash indefinitely).
setTimeout(hideSplash, 20000);

/* ───────── wiring ───────── */

function autoGrow() {
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, 168) + "px";
}

function submit() {
  const q = input.value.trim();
  if (!q || busy) return;
  input.value = "";
  autoGrow();
  ask(q);
}

composer.addEventListener("submit", (e) => { e.preventDefault(); submit(); });
input.addEventListener("input", autoGrow);
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); }
});

$$(".sugg").forEach((s) => s.addEventListener("click", () => {
  if (busy) return;
  ask(s.dataset.q);
}));

$("#new-chat").addEventListener("click", newConversation);

/* Jurisdiction control. The stored choice is applied to the radios on boot
   rather than the markup's `checked` being the source of truth, so a reload
   lands on what was last chosen; if storage is unavailable, loadScope() has
   already resolved to "all" and this just re-asserts the default. Deliberately
   usable while a question is in flight — the run already captured its own
   scope, so the only thing changing it affects is the next question. */
const scopeInputs = $$(".scope-input");
scopeInputs.forEach((i) => {
  i.checked = i.value === scope;
  i.addEventListener("change", () => {
    if (!i.checked || !isScope(i.value)) return;
    scope = i.value;
    saveScope(scope);
  });
});

const openNav = () => { document.body.classList.add("nav-open"); $("#scrim").hidden = false; };
const closeNav = () => { document.body.classList.remove("nav-open"); $("#scrim").hidden = true; };
$("#side-open").addEventListener("click", openNav);
$("#side-close").addEventListener("click", closeNav);
$("#scrim").addEventListener("click", closeNav);
historyEl.addEventListener("click", closeNav);

const modal = $("#limits-modal");
$("#limits-link").addEventListener("click", () => (modal.hidden = false));
$("#modal-close").addEventListener("click", () => (modal.hidden = true));
modal.addEventListener("click", (e) => { if (e.target === modal) modal.hidden = true; });

const aboutModal = $("#about-modal");
$("#about-link").addEventListener("click", () => (aboutModal.hidden = false));
$("#about-modal-close").addEventListener("click", () => (aboutModal.hidden = true));
aboutModal.addEventListener("click", (e) => { if (e.target === aboutModal) aboutModal.hidden = true; });

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    if (!modal.hidden) modal.hidden = true;
    if (!aboutModal.hidden) aboutModal.hidden = true;
  }
  if ((e.key === "/" || (e.key === "k" && (e.metaKey || e.ctrlKey))) && document.activeElement !== input) {
    e.preventDefault(); input.focus();
  }
});

renderHistory();
loadModelBadge().finally(hideSplash);
input.focus();
