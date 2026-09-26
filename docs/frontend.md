# Frontend — TrueCite

The browser application: what it is built with, how it is structured, how it
talks to the backend, what every part of the screen does, and where it stores
anything.

## At a glance

| | |
|---|---|
| **Stack** | Plain HTML, CSS and JavaScript — no framework, no build step, no bundler |
| **Dependencies** | None. Zero npm packages; nothing to install |
| **Files** | `web/index.html` (278 lines), `web/styles.css` (757), `web/app.js` (1,092) |
| **Served by** | The FastAPI backend — `/` returns `index.html`, `web/` is mounted as static files |
| **Transport** | Server-sent events (`EventSource`) for the pipeline; `fetch` for config and translation |
| **Fonts** | Fraunces (display serif), Inter (body), IBM Plex Mono (data, citations) — Google Fonts |
| **External requests** | Google Fonts only. No analytics, no trackers, no CDN scripts |
| **Storage** | Browser `localStorage` only — nothing is sent to a server to be kept |

**Why no framework.** The interface is one screen that renders a stream of
pipeline events. Plain JavaScript does that directly, keeps the page
dependency-free and auditable, and removes a build step. There is no React,
Vue or Tailwind anywhere in the project.

## Screen structure

| Region | What it does |
|---|---|
| **Splash** | Covers first load while the page initialises and the first `/api/config` check completes. Removed on real readiness, not a timer. |
| **Sidebar** | TrueCite wordmark, "New consultation", past conversations, live corpus count, active model and provider, links to *About* and *Known limitations* |
| **Header** | Current conversation title and the "3-layer verification" marker |
| **Thread** | The conversation: user questions and verified answers |
| **Empty state** | Shown before the first question — five suggested questions by category, including one that is designed to be refused |
| **Scope bar** | The jurisdiction control — *All sources / India / International* — with live per-jurisdiction document counts |
| **Composer** | Question input; Enter sends, Shift+Enter adds a line |
| **Modals** | *Known limitations* (text adapts to the active provider) and *About* |

## One answer, from question to screen

1. The scope in force is **snapshotted** when the question is sent, so changing
   the control mid-answer can never relabel an answer already in flight.
2. `ask()` opens an `EventSource` to
   `/api/ask?q=…&history=…&jurisdiction=…`. *All sources* sends no
   `jurisdiction` parameter at all.
3. A **live pipeline stepper** fills in as `stage` events arrive — retrieval
   counts, the confidence gate's actual distance against its 0.90 limit,
   drafting, each claim's verification votes, citation, coverage.
4. On `complete`, the stepper **collapses to one summary line**
   (e.g. *Verified · 1 claim upheld · 6 sources · 64.6s*) and the answer
   renders beneath it.
5. The `advisory` event renders under the answer (see below).
6. The turn is saved to `localStorage` with its scope and advisory, so a
   reloaded conversation shows exactly what it showed live.

The frontend handles every event type the backend emits: `stage`, `sources`,
`claim`, `claim_result`, `refused`, `advisory`, `complete`,
`provider_unavailable`, `error`. A provider outage shows a calm "the AI server
is busy" message rather than a stack trace.

## What an answer shows

- **Verified claims**, each followed by its citation in
  `[Source · §section · effective date]` form.
- **Coverage note**, when the answer may not fully address the question.
- **Sources consulted** — collapsible, with each passage's authority level.
- **Left out** — claims that failed verification, listed rather than hidden.
- **Scope label** — *India only*, *International only* or *All sources*.
- **Advisory panel**
  - **Confidence** — *High / Moderate / Low*, captioned plainly as how closely
    the passages matched, *not* a judgement that the answer is right. Visually
    distinct from the green *Verified* badge, because the two are different
    claims.
  - **Law not covered** — any regime the question touches that has no source
    in the corpus.
  - **Traditional-knowledge prior art** — a pointer to the TKDL, stating that
    this tool cannot search it.
  - **Worth putting to a person** — collapsed by default; the pipeline's own
    reasons shown verbatim, with named bodies and their links.
  - **Disclaimer** — "information, not legal advice", on every answer and every
    refusal.
- **Actions** — *Copy with citations*, and *View in Hindi*, which calls
  `/api/translate` on the already-verified answer.

A **refusal** shows why and where it stopped (Layer 1 or Layer 2), a Low
confidence reading, and the escalation panel.

## Local storage

| Key | Holds |
|---|---|
| `ipsakti.conversations.v1` | Up to 40 conversations, each with its turns, scope and advisory |
| `ipsakti.jurisdiction.v1` | The last chosen scope |

Every read and write is wrapped in `try/catch`: in a private window or with
site data blocked, the app still works and simply forgets on reload.
Conversations stored before a feature existed render without that feature
rather than with a guessed value.

## Main functions in `app.js`

| Area | Functions |
|---|---|
| Storage | `loadStore`, `saveStore`, `loadScope`, `saveScope` |
| Conversations | `newConversation`, `ensureConversation`, `renderHistory`, `openConversation`, `replayAssistant` |
| Asking | `ask`, `submit`, `autoGrow` |
| Rendering | `attachPipeline`, `answerHTML`, `coverageHTML`, `sourcesHTML`, `discardedHTML`, `actionsHTML`, `wireAnswer` |
| Advisory | `normalizeAdvisory`, `renderAdvisory`, `confidenceHTML`, `outOfCoverageHTML`, `priorArtHTML`, `escalationHTML`, `safeUrl` |
| Scope | `paintScopeTag` |
| Config | `loadModelBadge`, `formatModelName`, `limitationsProviderText` |
| Translation | `translateAnswer` |
| Splash | `startSplashStatusCycle`, `hideSplash` |

`safeUrl` only renders a link for an `http(s)` URL; anything else is shown as
text. `normalizeAdvisory` turns any malformed advisory into nothing rather than
a partial panel.

## Accessibility and responsiveness

- Works down to 375px wide with no horizontal scrolling (verified in a
  browser). The sidebar becomes a slide-in drawer on narrow screens.
- The scope control is a real radio group with visible keyboard focus.
- The escalation panel is a native `<details>` element, so it works by
  keyboard and screen reader without script.
- Honours `prefers-reduced-motion`, including an explicit override for
  staggered animation *delays*, which a duration-only rule misses.

## Not in the frontend yet

- The **formulation classifier** exists in the backend but has no screen —
  there is no guided question flow for classifying a product.
- No voice input or output, and no languages beyond English and Hindi.
