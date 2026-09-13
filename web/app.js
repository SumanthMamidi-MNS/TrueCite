/* IP-SAKTI Sahayak — consultation client.
   Plain JS, no build step: nothing between this and a demo screen that can break.

   Shape is a chat app because that's how the tool is actually used — an officer
   asks, reads, asks again, and comes back tomorrow wanting the thread. The
   verification pipeline runs inside the assistant's message and collapses to a
   badge once it settles, so it reassures on first use without becoming clutter. */

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

const thread = $("#thread");
const empty = $("#empty");
const composer = $("#composer");
const input = $("#q");
const sendBtn = $("#send");
const historyEl = $("#history");
const chatTitle = $("#chat-title");

const STORE_KEY = "ipsakti.conversations.v1";

let conversations = loadStore();
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

function attachPipeline(body) {
  const node = $("#tpl-pipeline").content.cloneNode(true);
  body.appendChild(node);
  const verify = $(".verify", body);
  $(".verify-summary", verify).addEventListener("click", () =>
    verify.classList.toggle("collapsed"));
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
    ${sourcesHTML(res.sources || [])}
    ${discardedHTML(discarded)}`;
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

  const copy = $(".copy-btn", body);
  if (copy) copy.addEventListener("click", async () => {
    const text = res.refused
      ? res.answer
      : res.claims.map((c) => `${c.text} ${c.citation}`).join("\n\n");
    try {
      await navigator.clipboard.writeText(text);
      copy.classList.add("copied");
      copy.lastChild.textContent = " Copied";
      setTimeout(() => { copy.classList.remove("copied"); copy.lastChild.textContent = " Copy with citations"; }, 1600);
    } catch { /* clipboard blocked — nothing useful to do */ }
  });
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
    </div>
    ${answerHTML(res)}
    ${actionsHTML()}`;
  wireAnswer(body, res);
  return el;
}

/* ───────── live run ───────── */

function ask(question) {
  if (busy) return;
  busy = true;
  sendBtn.disabled = true;
  empty.hidden = true;

  const conv = ensureConversation(question);
  thread.appendChild(userMessage(question));

  const msg = botShell();
  const body = $(".msg-body", msg);
  thread.appendChild(msg);
  const verify = attachPipeline(body);
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

  // Last few turns of THIS conversation, sent so a follow-up ("what about
  // for Unani?") can be rewritten into a standalone question before
  // retrieval — see generate._condense_followup. Empty on a fresh
  // conversation's first question, so nothing changes for a one-off ask.
  const historyPayload = conv.turns.slice(-3).map((t) => ({ q: t.q, a: t.result.answer }));
  const hasHistory = historyPayload.length > 0;
  if (hasHistory) $('.step[data-step="condense"]', verify).hidden = false;
  setStep(hasHistory ? "condense" : "retrieval", "active");

  const historyParam = hasHistory ? `&history=${encodeURIComponent(JSON.stringify(historyPayload))}` : "";
  stream = new EventSource(`/api/ask?q=${encodeURIComponent(question)}${historyParam}`);

  stream.onmessage = (m) => {
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
      if (passed) setStep("generation", "active");
    }

    if (ev.type === "sources") sources = ev.sources;

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
          setStep("generation", null, "Skipped — nothing confident enough to draft from");
          setStep("verification", null, "Skipped");
        } else if (drafted === 0) {
          setStep("verification", null, "Skipped — nothing was asserted to verify");
        } else {
          setStep("verification", "failed", "No claim survived verification");
        }
        setStep("cite", null, "Skipped — nothing to cite");
        summary = `Refused · ${atGate ? "no confident match" : "nothing verifiable"} · ${secs}s`;
      }

      clearInterval(timer);
      const sumBtn = $(".verify-summary", verify);
      sumBtn.hidden = false;
      sumBtn.classList.toggle("warn", ev.type === "refused");
      $(".vs-text", sumBtn).textContent = summary;
      setTimeout(() => verify.classList.add("collapsed"), 900);

      body.insertAdjacentHTML("beforeend", answerHTML(res) + actionsHTML());
      wireAnswer(body, res);
      conv.turns.push({ q: question, result: res, meta: { summary } });
      conv.at = Date.now();
      saveStore();
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

  stream.onerror = () => { if (busy) { clearInterval(timer); finish(); } };

  function finish() {
    busy = false;
    sendBtn.disabled = false;
    if (stream) { stream.close(); stream = null; }
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
const PROVIDER_LABELS = { ollama: "local (Ollama)", anthropic: "Anthropic API" };

async function loadModelBadge() {
  const modelEl = $("#model-name");
  const corpusEl = $("#corpus-count");
  try {
    const res = await fetch("/api/config");
    if (!res.ok) throw new Error(String(res.status));
    const { model, provider, corpus_docs } = await res.json();
    modelEl.textContent = `${formatModelName(model)} · ${PROVIDER_LABELS[provider] || provider}`;
    corpusEl.textContent = `${corpus_docs} primary source${corpus_docs === 1 ? "" : "s"} indexed`;
  } catch {
    modelEl.textContent = "Model unavailable — is the server running?";
    $("#model-note .dot-model")?.classList.add("down");
    corpusEl.textContent = "Corpus status unavailable";
  }
}

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

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !modal.hidden) modal.hidden = true;
  if ((e.key === "/" || (e.key === "k" && (e.metaKey || e.ctrlKey))) && document.activeElement !== input) {
    e.preventDefault(); input.focus();
  }
});

renderHistory();
loadModelBadge();
input.focus();
