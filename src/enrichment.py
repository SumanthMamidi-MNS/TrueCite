"""Cross-reference enrichment for retrieval scoring only (never for what generation sees).

Measured defect (docs/decisions.md, 2026-09-16): the Biological Diversity Act's
penalty question ("What is the penalty ... for contravening its access
provisions?") has its gold answer in ::sec-55 ("55. Penalties. (1) Whoever
contravenes ... the provisions of section 3 or section 4 or section 6 shall be
punishable..."). Section 55 never contains the words "access" or "approval" —
that subject matter lives in sections 3, 4 and 6, which sec-55 references only
by number, not by restating their content. No amount of BM25 stemming or
vector-embedding tuning on sec-55's own text can close that gap, because the
gap isn't a vocabulary-matching problem, it's a missing-context problem: a
reader (human or embedding model) who doesn't already know what section 3, 4
and 6 say has no way to know sec-55 is about "access provisions" at all.

The fix: when a chunk references another section of the SAME document by
number, and that section's heading was already recovered during chunking
(docs/decisions.md), append a short "[Cross-references: ...]" trailer built
from those headings to the text that gets EMBEDDED/TOKENIZED for scoring.
Headings only, never full section bodies — a heading is a reliable one-line
summary of what a section is about; splicing in another section's actual body
text would risk misattributing that body's content to the chunk being scored.

THE SAFETY PROPERTY (see indexing.py / bm25_retrieval.py): this module's
output is used only to decide *whether a chunk is a good match for a query*.
It must never reach generation, Layer 2 verification, citations, or the UI —
those all read the chunk's true, unenriched `text`. If sec-55's embedded/
tokenized form claims something about sections 3/4/6, and that trailer ever
leaked into what a user reads as sec-55's content, that would be a fabricated
citation. So the wiring in indexing.py and bm25_retrieval.py is deliberately
asymmetric: enriched text in, true text out.

Second defect found on the same held-out question set (docs/decisions.md,
2026-09-16): short chunks that never mention their own document's identity
lose retrieval to longer chunks that happen to repeat the question's topic
words. E.g. the WIPO GRATK treaty's Article 17 ("This Treaty shall enter
into force three months after 15 eligible parties ... have deposited their
instruments of ratification or accession.") ranked vector >40 for "When does
the WIPO treaty on genetic resources and associated traditional knowledge
come into force?" — the chunk itself never says "WIPO", "treaty", "genetic
resources" or "traditional knowledge"; a reader (human or embedding model)
who doesn't already know which document/section this is has no way to
connect the two. Same pattern for the Patents Act's §3(i)/§3(j) clauses
("Can ... be patented in India?" / "Are medicinal plants ... patentable in
India?") — the clause text never restates "patent" or "India".

The fix: `build_context_header` prepends ONE short, strictly factual header
line — "[<document title> — <section label>: <heading>]" — built only from
existing metadata (authority.py's title, plus the chunk's own section_number/
heading), to the text that gets EMBEDDED/TOKENIZED for scoring. Same safety
property as the cross-reference trailer above: scored only, never returned.
`CONTEXT_HEADER_ENABLED` is a module-level on/off switch for A/B measurement;
when False, `build_retrieval_text`'s output is byte-identical to the
pre-header function.
"""
import re

from authority import AUTH_LEVEL_ACT, get_authority

# Matches "section 3", "sections 3", case-insensitively on the word "section"
# but case-SENSITIVE on the trailing letter suffix (this corpus's real
# examples, e.g. "11A", are always uppercase) — plus, via the repeating group,
# a same-style list like "section 3 or section 4 or section 6" or
# "sections 3, 4 and 6" as ONE match, so a list is recognized as a whole
# rather than only ever catching its first member.
_SECTION_LIST_RE = re.compile(
    r"\b(?i:sections?)\s+\d{1,3}[A-Z]?"
    r"(?:\s*(?:,|or|and)\s*(?:(?i:sections?)\s+)?\d{1,3}[A-Z]?)*"
)
_NUMBER_RE = re.compile(r"\d{1,3}[A-Z]?")

# "sub-section (N) of section M" must resolve to M, not N — N is a subsection
# of the CURRENT section (internal structure, not a cross-document reference).
# This needs no special handling below: _SECTION_LIST_RE requires "section(s)"
# to be followed directly by a digit, and "sub-section (2)" has "(2)" after
# it, not a bare digit, so the regex simply never matches the "sub-section"
# half — only the later "section 24" half matches, which is exactly M.

# MANDATORY exclusion (see module docstring / task): a reference immediately
# followed by "of the <Name> Act" names a DIFFERENT statute's section, e.g.
# biological_diversity_act_2002::sec-3's "clause (30) of section 2 of the
# Income-tax Act, 1961" — enriching that chunk with the Biological Diversity
# Act's OWN section 2 heading would attribute someone else's Act's provision
# to this one. Checked immediately after each individual number match (not
# the whole list match), anchored so only text directly adjacent qualifies —
# a list member earlier in a series ("section 3 or section 4" before "of the
# X Act") is not touched by a phrase that trails a later member.
_CROSS_STATUTE_RE = re.compile(r"\s*of\s+the\s+[A-Z][A-Za-z\-]*(?:\s+[A-Za-z\-]+){0,5}\s+Act\b")
_CROSS_STATUTE_LOOKAHEAD_CHARS = 120

MAX_REFERENCES = 5
# "~400" per the task spec (approximate, not a hard 400): the real sec-55
# trailer for all three of its references (sections 3, 4 and 6, each with
# their real recovered headings) measures 401 chars. Capping at a literal
# 400 would arbitrarily drop the third reference over a single character,
# for no principled reason — 420 keeps this the realistic case that
# motivated the whole task while still being "~400", not some much larger
# number.
MAX_TRAILER_CHARS = 420

# Headings the chunker assigns when it could NOT recover a real section title
# (see chunking.py) — these carry no usable summary, so a chunk keyed under
# one of them must never be offered as a cross-reference target, and must
# never be surfaced as a "real heading" in the context header either.
_GENERIC_HEADINGS = frozenset({"(unstructured)", "Preamble", "Front matter / table of contents"})

# A/B switch for the context-header change (docs/decisions.md, 2026-09-16).
# False makes build_retrieval_text byte-identical to the pre-header function.
CONTEXT_HEADER_ENABLED = True

# "~200 chars" per the task spec — kept short since this is one factual line,
# not a substitute for the passage itself.
MAX_HEADER_CHARS = 200


def _section_label(chunk: dict) -> str | None:
    """A short, factual section label for the header, or None if the chunk
    has no section_number (front matter / preamble).

    Treaty articles (chunking.py's `_chunk_treaty_articles`) already store
    "Article N" as the whole section_number, so that's used verbatim. Every
    other document numbers by Act "section" or guideline "paragraph" —
    neither word is itself in the metadata, so which one to use is derived
    from authority.py's existing authority_level (Act vs. Guideline/
    Informational) rather than invented per document.
    """
    section_number = chunk.get("section_number")
    if not section_number:
        return None
    if section_number.startswith("Article "):
        return section_number
    doc_id = chunk.get("doc_id")
    try:
        authority_level = get_authority(doc_id)["authority_level"]
    except KeyError:
        authority_level = None
    if authority_level == AUTH_LEVEL_ACT:
        return f"§{section_number}"
    return f"paragraph {section_number}"


def _header_heading(chunk: dict) -> str | None:
    """The chunk's real recovered heading for the header, or None.

    Same "is this a real heading" test as build_headings_by_section: skips
    the chunker's generic placeholders ("Paragraph N", "(unstructured)",
    "Preamble", "Front matter / table of contents") — those carry no
    factual content, so including one would pad the header without adding
    any real document identity.
    """
    heading = (chunk.get("heading") or "").strip()
    if not heading or heading.startswith("Paragraph ") or heading in _GENERIC_HEADINGS:
        return None
    return heading


def build_context_header(chunk: dict) -> str:
    """"[<document title> — <section label>: <heading>]" or "" if disabled
    or the chunk's doc_id has no authority.py entry.

    Strictly factual: every word here comes from authority.py's title field
    or the chunk's own section_number/heading metadata — no synonyms, no
    glosses on what the section is "about".
    """
    if not CONTEXT_HEADER_ENABLED:
        return ""
    try:
        title = get_authority(chunk.get("doc_id"))["short_name"]
    except KeyError:
        return ""
    if not title:
        return ""

    section_label = _section_label(chunk)
    heading = _header_heading(chunk)

    if section_label and heading:
        prefix = f"{title} — {section_label}: "
        budget = MAX_HEADER_CHARS - len("[]") - len(prefix)
        if budget <= 10:
            # Title + section label alone already fill the cap — drop the
            # heading rather than emit an over-cap header.
            body = f"{title} — {section_label}"
        elif len(heading) > budget:
            body = f"{prefix}{heading[:budget].rstrip()}..."
        else:
            body = f"{prefix}{heading}"
    elif section_label:
        body = f"{title} — {section_label}"
    else:
        body = title

    header = f"[{body}]"
    if len(header) > MAX_HEADER_CHARS:
        header = header[: MAX_HEADER_CHARS - 4].rstrip() + "...]"
    return header


def _base_section_number(chunk: dict) -> str | None:
    """The section number a chunk belongs to, stripped of any clause/subsection suffix.

    Split chunks (chunking.py's sec-N-sub-M, sec-N-clause-x) carry the parent
    section's number in `parent_section_number` and their OWN compound number
    (e.g. "25(1)") in `section_number`; unsplit chunks carry only the plain
    number in `section_number`. Either way, the leading digits(+letter) is the
    real section identity a cross-reference like "section 25" is pointing at.
    """
    raw = chunk.get("parent_section_number") or chunk.get("section_number")
    if not raw:
        return None
    match = re.match(r"\d{1,4}[A-Za-z]{0,2}", raw)
    return match.group(0) if match else None


def build_headings_by_section(chunks: list[dict]) -> dict[str, str]:
    """Map base section number -> recovered heading, for ONE document's chunks.

    Caller must pass chunks from a single document — headings are only ever
    valid cross-reference targets for chunks of THAT SAME document (a
    "section 3" reference in the Patents Act must never resolve to the
    Biological Diversity Act's section 3, or any other document's).
    Split chunks (sub-1, clause-a, ...) all carry their parent section's own
    heading (chunking.py passes the same `heading` through to every split
    piece), so any one of them is a valid source; `setdefault` just keeps the
    first one seen rather than needing them to agree, which they always do.
    """
    headings: dict[str, str] = {}
    for chunk in chunks:
        key = _base_section_number(chunk)
        if key is None:
            continue
        heading = (chunk.get("heading") or "").strip()
        if not heading or heading.startswith("Paragraph ") or heading in _GENERIC_HEADINGS:
            continue
        headings.setdefault(key, heading)
    return headings


def build_retrieval_text(chunk: dict, headings_by_section: dict[str, str]) -> str:
    """Return a contextual header + `chunk["text"]` + a same-document
    cross-reference trailer, for SCORING only.

    `headings_by_section` must come from `build_headings_by_section` run over
    the SAME document as `chunk` (see that function's docstring) — this
    function does not itself check doc_id, so passing a mismatched mapping
    would silently attribute another document's section content to this one.

    The header (see `build_context_header`) is a no-op — this function
    returns exactly what it did before the header existed — whenever
    `CONTEXT_HEADER_ENABLED` is False.
    """
    body = _with_cross_references(chunk, headings_by_section)
    header = build_context_header(chunk)
    return f"{header}\n\n{body}" if header else body


def _with_cross_references(chunk: dict, headings_by_section: dict[str, str]) -> str:
    """The pre-header build_retrieval_text logic, unchanged: chunk text plus
    an optional same-document cross-reference trailer."""
    text = chunk["text"]
    self_number = _base_section_number(chunk)

    refs: dict[str, str] = {}
    for list_match in _SECTION_LIST_RE.finditer(text):
        for num_match in _NUMBER_RE.finditer(list_match.group()):
            number = num_match.group(0)
            if number in refs:
                continue
            if self_number and number == self_number:
                continue
            abs_end = list_match.start() + num_match.end()
            lookahead = text[abs_end : abs_end + _CROSS_STATUTE_LOOKAHEAD_CHARS]
            if _CROSS_STATUTE_RE.match(lookahead):
                continue
            heading = headings_by_section.get(number)
            if not heading:
                continue
            refs[number] = heading
            if len(refs) >= MAX_REFERENCES:
                break
        if len(refs) >= MAX_REFERENCES:
            break

    if not refs:
        return text

    entries: list[str] = []
    for number, heading in refs.items():
        entry = f"section {number} — {heading}"
        trailer_len = len(f"\n\n[Cross-references: {'; '.join(entries + [entry])}]")
        if trailer_len > MAX_TRAILER_CHARS:
            if not entries:
                # Even one entry alone overflows the cap (an unusually long
                # heading) — truncate the heading text itself rather than
                # emit an over-cap trailer or drop the reference entirely.
                prefix_len = len(f"\n\n[Cross-references: section {number} — ]")
                budget = MAX_TRAILER_CHARS - prefix_len
                if budget > 10:
                    entries.append(f"section {number} — {heading[:budget].rstrip()}...")
            break
        entries.append(entry)

    if not entries:
        return text

    return text + f"\n\n[Cross-references: {'; '.join(entries)}]"
