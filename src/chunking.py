"""Structural chunking for Ayurveda IP/regulatory documents.

Legal/regulatory text breaks under fixed-token chunking because cross-references
("sub-section (1) of section 3", "clause (a) above") span exactly the structural
units the document itself defines. So we chunk along whatever structure the
document actually has, falling back to paragraphs only when no structure is
detectable — never on a fixed token/character window.

Strategy (tried in order, since real documents in this corpus use different
conventions — a numbered-clause Act, a numbered-paragraph guideline, and plain
prose all appear in the same corpus):
  1. Chapter headings ("CHAPTER I" + title line), if present.
  2. Numbered sections/paragraphs ("N. ..." or "N. Title.<dash>...") at line start,
     within each chapter (or the whole document if no chapters).
  3. If a section enumerates several lettered clauses ("(a)", "(b)", ...) and
     has no numeric subsections of its own, split per clause regardless of
     total length — long lettered lists dilute embedding relevance for any
     one clause even when the whole section is under the size cap.
  4. Else, if a section's body is long, split further at numbered sub-clauses
     ("(1)", "(2)", ...) at line start, keeping the parent section number attached.
  5. If no numbering is detected at all, fall back to paragraph grouping
     (blank-line-delimited), merged up to a target size — still never mid-sentence.
"""
import re
from bisect import bisect_right
from dataclasses import dataclass, field

SECTION_RE = re.compile(r"^[ \t]*(\d{1,4}[A-Z]{0,2})\.\s+(.*)$", re.MULTILINE)
# A second numbering convention, alongside the Act-style "N. Title.—" above:
# international treaty text (e.g. the WIPO GRATK Treaty) numbers "ARTICLE N"
# with its title on the following line, not inline. Character class includes
# U+00A0/U+202F (non-breaking/narrow-no-break space) because at least one real
# heading in that document used a narrow-no-break space instead of ASCII space
# after the article number — confirmed directly on the source PDF's extracted
# text, not a hypothetical. Only ever tried when SECTION_RE finds fewer than 2
# matches (see _chunk_region), so it can't affect any numbered-section document.
ARTICLE_HEADING_RE = re.compile(
    r"^ARTICLE\s+(\d{1,2})[ \t  ]*\r?\n[ \t  ]*([^\n]{2,80})[ \t  ]*$",
    re.MULTILINE,
)
SUBSECTION_RE = re.compile(r"^[ \t]*\((\d{1,3}[A-Za-z]?)\)\s+", re.MULTILINE)
LETTERED_CLAUSE_RE = re.compile(r"^[ \t]*\(([a-z]{1,3})\)\s+", re.MULTILINE)
# Subsection "(1)" is almost always inline right after the heading's own
# dash ("19. Powers...—(1) If..."), not at line start, so SUBSECTION_RE alone
# undercounts by one for most sections — used to correct that count before
# deciding whether a section already has its own numeric subsection structure.
_INLINE_FIRST_SUBSECTION_RE = re.compile(r"[—–]\s*\(1\)\s")

# Bare Acts print amendment footnotes ("3. Ins. by Act 15 of 2005, s. 2
# (w.e.f. 1-1-2005)") inline in the extracted text, numbered independently of
# (and colliding with) the real section numbers. These are recognizable by
# their content — legislative-amendment vocabulary a real section body never
# uses in its opening words — so they're filtered out before any numbering
# logic runs, rather than relying on numeric ordering alone.
FOOTNOTE_CONTENT_RE = re.compile(
    r"^(Ins\.|Subs\.|Omitted\s|Reps?\.|Renumbered|Added\s|Cl\.|Clause\s*\([a-z]+\)\s*(omitted|added|substituted|ins\.)"
    r"|Sub-?section\s*\(|\d{1,2}-\d{1,2}-\d{4}|Received\sthe\sassent)",
    re.IGNORECASE,
)

# A PDF line-wrap can put a calendar year at the very start of a line right
# before its own sentence-ending period — e.g. "...published in November
# \n2012. Mr. Ruiz contributed..." — which SECTION_RE then reads as a real
# section header "2012." No document in this corpus has anywhere near 1900+
# sections, so a 4-digit "section number" in a plausible year range is far
# more likely to be exactly this than a real section. Confirmed directly,
# not hypothetical: this exact case in the WIPO TK toolkit swallowed the
# rest of that 40-page document into one 79,710-character chunk, found live
# while testing the relevance-filter pipeline stage — see docs/decisions.md.
_PLAUSIBLE_YEAR_RE = re.compile(r"^(19|20)\d{2}$")

# Sections this short are almost always false positives from stray numbering,
# not real structure (a real Act section always has substantive body text).
MIN_SECTION_BODY_CHARS = 20
MAX_CHUNK_CHARS = 3000
PARAGRAPH_TARGET_CHARS = 1200

# A section enumerating this many distinct lettered clauses — e.g. the Patents
# Act's Section 3, "(a) ... (b) ... ... (p) an invention which, in effect, is
# traditional knowledge" — gets split per clause regardless of its total
# character count. The problem this fixes isn't length, it's semantic
# dilution: embedding one chunk covering 16 unrelated statutory exclusions
# pulls each individual clause's meaning toward the group average, measurably
# hurting retrieval for a specific clause (verified: isolating Section 3(p)
# alone raised its cosine similarity to a plain-language TK-patentability
# query from 0.455 to 0.568 — see docs/decisions.md).
MIN_LETTERED_CLAUSES_TO_SPLIT = 3


@dataclass
class Chunk:
    doc_id: str
    chunk_id: str
    heading: str
    section_number: str | None
    parent_section_number: str | None
    page_start: int
    page_end: int
    text: str
    char_count: int = field(init=False)

    def __post_init__(self):
        self.char_count = len(self.text)


# Standalone lines to drop before chunking: page-bottom footnote definitions
# (same content signature as FOOTNOTE_CONTENT_RE, anchored to a whole line) and
# bare page-number lines left over from the PDF's running header/footer.
_FOOTNOTE_LINE_RE = re.compile(
    r"^\d{1,3}[A-Za-z]?\.\s+(Ins\.|Subs\.|Omitted|Reps?\.|Renumbered|Added|Cl\.|"
    r"Sub-?clause\s*\(|Clause\s*\([a-z]+\)|Sub-?section\s*\(|Received\sthe\sassent|\d{1,2}-\d{1,2}-\d{4}).*$",
    re.IGNORECASE | re.MULTILINE,
)
_PAGE_NUMBER_LINE_RE = re.compile(
    r"^\s*(\d{1,4}|Page \d{1,4}(\s+of\s+\d{1,4})?)\s*$", re.MULTILINE | re.IGNORECASE
)
# Running-header document codes, e.g. the WIPO GRATK Treaty PDF prints
# "GRATK/DC/7" as its own line at every page break — administrative apparatus,
# not treaty text, and the all-caps-slash-digit shape is specific enough that
# no real section/clause text would ever appear as a standalone line matching it.
_DOC_CODE_HEADER_LINE_RE = re.compile(r"^[A-Z]{2,10}/[A-Z]{2,6}/\d{1,4}\s*$", re.MULTILINE)
# A document-conversion tool's own temp-file path, leaked into every page of
# the Biological Diversity Act 2002 mirror this corpus sources from (confirmed
# on the actual extracted text — a stray artifact of whatever HTML/DOC-to-PDF
# pipeline the source site used, not part of the Act itself).
_CONVERTER_ARTIFACT_LINE_RE = re.compile(r"^/root/convert/.*\.doc\s*$", re.MULTILINE | re.IGNORECASE)
_EXCESS_BLANK_LINES_RE = re.compile(r"\n{3,}")

# Bare Acts mark amendment-inserted spans with a footnote-reference digit glued
# directly onto an opening bracket, e.g. "3[11A. Publication of applications"
# or "4[(b) an invention...]". These are pure editorial apparatus (the actual
# citation is in the footnote line already stripped above) — but left in
# place, a marker glued onto a real section number ("3[11A.") hides that
# section's line-start from SECTION_RE entirely, silently merging that whole
# section's text into the previous one. Stripping the brackets (and the
# digit fused to an opening one) removes the ambiguity while keeping the
# substantive text intact.
_FUSED_FOOTNOTE_BRACKET_RE = re.compile(r"\d{1,3}\[")
_BARE_BRACKET_RE = re.compile(r"[\[\]]")

# Used by the dash-less section-title fallback (see _chunk_region) to reject a
# numbered-paragraph guideline's ordinary opening sentence, which can otherwise
# still slip past that fallback's other checks (short, single period, capital
# start, substantial text remaining). Indian bare-Act section titles are
# noun phrases or infinitive constructions ("...not to be made without
# approval", "...to be laid before Parliament") and never use a finite,
# conjugated verb the way explanatory prose does ("law HAS adequate
# provisions", "the Declaration RECOGNIZES the rights") -- confirmed against
# all 55 real Biological Diversity Act titles this fallback recovers, none of
# which match. "to have"/"to had" are deliberately excluded from this list
# since real titles do use that infinitive ("Act to have effect in addition
# to other Acts").
_FINITE_VERB_RE = re.compile(
    r"\b(is|are|was|were|has|recognizes?|provides?|includes?|means|requires?)\b", re.IGNORECASE
)
# A real title in this corpus never runs longer than this many words (the
# longest confirmed real one is 16); a guideline's misread opening sentence
# regularly does.
_MAX_TITLE_WORDS = 16


def _clean_page_text(text: str) -> str:
    text = _FOOTNOTE_LINE_RE.sub("", text)
    text = _PAGE_NUMBER_LINE_RE.sub("", text)
    text = _DOC_CODE_HEADER_LINE_RE.sub("", text)
    text = _CONVERTER_ARTIFACT_LINE_RE.sub("", text)
    text = _FUSED_FOOTNOTE_BRACKET_RE.sub("", text)
    text = _BARE_BRACKET_RE.sub("", text)
    text = _EXCESS_BLANK_LINES_RE.sub("\n\n", text)
    return text


def _build_page_offsets(pages: list[str]) -> tuple[str, list[int]]:
    """Join cleaned pages with a separator and return (full_text, offset-of-each-page-start)."""
    offsets = []
    parts = []
    pos = 0
    for page in pages:
        cleaned = _clean_page_text(page)
        offsets.append(pos)
        parts.append(cleaned)
        pos += len(cleaned) + 1  # +1 for the '\n' join separator
    return "\n".join(parts), offsets


def _page_for_offset(offsets: list[int], char_offset: int) -> int:
    """1-indexed page number containing char_offset."""
    idx = bisect_right(offsets, char_offset) - 1
    return max(idx, 0) + 1


def _paragraph_spans(text: str) -> list[tuple[int, int]]:
    """(start, end) of each non-blank paragraph in text, whitespace-trimmed.

    Works on character spans rather than extracted/rejoined strings, so a
    merged multi-paragraph block's offset is always exact — no fragile
    re-searching for reconstructed text back in the original.
    """
    spans, pos = [], 0
    boundaries = [m.start() for m in re.finditer(r"\n\s*\n", text)] + [len(text)]
    for boundary in boundaries:
        start, end = pos, boundary
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        if end > start:
            spans.append((start, end))
        pos = boundary
    return spans


def _merge_spans(spans: list[tuple[int, int]], target_chars: int) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    cur_start = cur_end = None
    for start, end in spans:
        if cur_start is None:
            cur_start, cur_end = start, end
        elif (cur_end - cur_start) + (end - start) > target_chars:
            merged.append((cur_start, cur_end))
            cur_start, cur_end = start, end
        else:
            cur_end = end
    if cur_start is not None:
        merged.append((cur_start, cur_end))
    return merged


def _fallback_paragraph_chunks(
    doc_id: str, text: str, offsets: list[int], base_offset: int, heading: str
) -> list[Chunk]:
    merged = _merge_spans(_paragraph_spans(text), PARAGRAPH_TARGET_CHARS)
    chunks = []
    for i, (start, end) in enumerate(merged, start=1):
        abs_start, abs_end = base_offset + start, base_offset + end
        chunks.append(
            Chunk(
                doc_id=doc_id,
                chunk_id=f"{doc_id}::para-{i}",
                heading=heading,
                section_number=None,
                parent_section_number=None,
                page_start=_page_for_offset(offsets, abs_start),
                page_end=_page_for_offset(offsets, abs_end),
                text=text[start:end],
                )
        )
    return chunks


def _split_by_lettered_clauses(
    doc_id: str,
    section_number: str,
    heading: str,
    body: str,
    body_start_offset: int,
    offsets: list[int],
) -> list[Chunk]:
    """Split a section into one chunk per lettered clause "(a)", "(b)", ...

    Only called when the section has no numeric "(1)"/"(2)" subsections of its
    own (checked by the caller) — avoids misreading letters nested a level
    below an existing numeric subsection (e.g. Section 25's "(1) ... (a) ...
    (2) ... (a) ..." would otherwise produce two colliding "clause-a" chunks).

    Each clause is prefixed with the section's own intro text (everything
    before the first clause) so a clause read alone — e.g. just "(p) an
    invention which, in effect, is traditional knowledge..." — keeps the
    "the following are not inventions" framing instead of losing it, the same
    class of bug as the earlier lost-preamble fix.
    """
    matches = _monotonic_lettered_clauses(body)
    intro = body[: matches[0].start()].strip()

    chunks = []
    for i, m in enumerate(matches):
        letter = m.group(1)
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        clause_text = body[start:end].strip()
        if not clause_text:
            continue
        full_text = f"{intro}\n{clause_text}" if intro else clause_text
        abs_start = body_start_offset + start
        abs_end = body_start_offset + end
        chunks.append(
            Chunk(
                doc_id=doc_id,
                chunk_id=f"{doc_id}::sec-{section_number}-clause-{letter}",
                heading=heading,
                section_number=f"{section_number}({letter})",
                parent_section_number=section_number,
                page_start=_page_for_offset(offsets, abs_start),
                page_end=_page_for_offset(offsets, abs_end),
                text=full_text,
            )
        )
    return chunks


def _split_section_body(
    doc_id: str,
    section_number: str,
    heading: str,
    body: str,
    body_start_offset: int,
    offsets: list[int],
) -> list[Chunk]:
    """Split an overlong section into sub-clause chunks, tagged with the parent section."""
    matches = list(SUBSECTION_RE.finditer(body))
    has_inline_subsection_1 = bool(_INLINE_FIRST_SUBSECTION_RE.search(body[:300]))
    effective_match_count = len(matches) + (1 if has_inline_subsection_1 else 0)
    if effective_match_count < 2:
        # No numeric "(1)", "(2)" subsections to split on (some documents use
        # decimal headings like "3.1" or named ones like "Guiding Principle 2"
        # instead, which this chunker doesn't parse as structure). Rather than
        # ship one huge undivided chunk, fall back to paragraph grouping — same
        # approach used for documents with no numbering at all — so retrieval
        # still gets reasonably sized pieces, at the cost of citing by
        # paragraph position instead of a specific named subsection.
        merged = _merge_spans(_paragraph_spans(body), PARAGRAPH_TARGET_CHARS)
        if len(merged) < 2:
            return [
                Chunk(
                    doc_id=doc_id,
                    chunk_id=f"{doc_id}::sec-{section_number}",
                    heading=heading,
                    section_number=section_number,
                    parent_section_number=None,
                    page_start=_page_for_offset(offsets, body_start_offset),
                    page_end=_page_for_offset(offsets, body_start_offset + len(body)),
                    text=body.strip(),
                )
            ]
        chunks = []
        for i, (start, end) in enumerate(merged, start=1):
            chunks.append(
                Chunk(
                    doc_id=doc_id,
                    chunk_id=f"{doc_id}::sec-{section_number}-part-{i}",
                    heading=heading,
                    section_number=section_number,
                    parent_section_number=section_number,
                    page_start=_page_for_offset(offsets, body_start_offset + start),
                    page_end=_page_for_offset(offsets, body_start_offset + end),
                    text=body[start:end],
                )
            )
        return chunks

    chunks = []
    # Subsection "(1)" is almost always inline with the section heading itself
    # ("19. Powers of Controller...—(1) If, in consequence...") rather than on
    # its own line, so SUBSECTION_RE's line-start match never finds it — the
    # first real match here is usually "(2)". Left alone, subsection (1)'s
    # entire text (everything before that first match) would be silently
    # dropped, the same class of bug as the earlier lost-preamble fix.
    leading_text = body[: matches[0].start()].strip()
    if len(leading_text) >= MIN_SECTION_BODY_CHARS:
        abs_start = body_start_offset
        abs_end = body_start_offset + matches[0].start()
        chunks.append(
            Chunk(
                doc_id=doc_id,
                chunk_id=f"{doc_id}::sec-{section_number}-sub-1",
                heading=heading,
                section_number=f"{section_number}(1)",
                parent_section_number=section_number,
                page_start=_page_for_offset(offsets, abs_start),
                page_end=_page_for_offset(offsets, abs_end),
                text=leading_text,
            )
        )

    for i, m in enumerate(matches):
        sub_num = m.group(1)
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        sub_text = body[start:end].strip()
        if not sub_text:
            continue
        abs_start = body_start_offset + start
        abs_end = body_start_offset + end
        chunks.append(
            Chunk(
                doc_id=doc_id,
                chunk_id=f"{doc_id}::sec-{section_number}-sub-{sub_num}",
                heading=heading,
                section_number=f"{section_number}({sub_num})",
                parent_section_number=section_number,
                page_start=_page_for_offset(offsets, abs_start),
                page_end=_page_for_offset(offsets, abs_end),
                text=sub_text,
            )
        )
    return chunks


def _numeric_key(section_number: str) -> tuple[int, str]:
    m = re.match(r"(\d+)([A-Z]*)", section_number)
    return int(m.group(1)), m.group(2)


def _filter_monotonic(matches: list[re.Match]) -> list[re.Match]:
    """Drop matches whose number doesn't continue the increasing sequence.

    Real section/paragraph numbering in these documents is strictly increasing
    and each number appears once. Footnotes (amendment notes at the bottom of
    an Act page) restart their own "1.", "2.", "3." numbering inline in the
    extracted text, which otherwise collides with real section numbers — this
    filter is what tells the two apart.
    """
    accepted = []
    last_key = (-1, "")
    for m in matches:
        key = _numeric_key(m.group(1))
        if key > last_key:
            accepted.append(m)
            last_key = key
    return accepted


def _monotonic_lettered_clauses(body: str) -> list[re.Match]:
    """LETTERED_CLAUSE_RE matches that continue a strictly increasing letter
    sequence (plain string comparison — correctly orders amendment-inserted
    letters too, e.g. "aa" < "ab" < "b").

    Unlike numbered sections, a lettered marker like "(b)" is short enough
    that it can coincidentally start a PDF-wrapped line mid-sentence (e.g. "...
    described in clause (b) of this section, the applicant shall...") without
    being a real new list item. Rejecting anything that doesn't continue the
    sequence — the same defense used against footnote-number collisions in
    _filter_monotonic — catches this False start.
    """
    accepted = []
    last_letter = ""
    for m in LETTERED_CLAUSE_RE.finditer(body):
        letter = m.group(1)
        if letter > last_letter:
            accepted.append(m)
            last_letter = letter
    return accepted


def _chunk_treaty_articles(
    doc_id: str, text: str, region_start_offset: int, offsets: list[int], matches: list[re.Match]
) -> list[Chunk]:
    """Chunk a treaty's "ARTICLE N" / title-on-next-line structure.

    Mirrors _chunk_region's own preamble + oversized-section handling (reusing
    _split_by_lettered_clauses / _split_section_body directly) rather than
    duplicating that logic — the only real difference is where the section
    number and heading come from.
    """
    chunks: list[Chunk] = []
    preamble = text[: matches[0].start()].strip()
    if len(preamble) >= MIN_SECTION_BODY_CHARS:
        chunks.append(
            Chunk(
                doc_id=doc_id,
                chunk_id=f"{doc_id}::preamble",
                heading="Preamble",
                section_number=None,
                parent_section_number=None,
                page_start=_page_for_offset(offsets, region_start_offset),
                page_end=_page_for_offset(offsets, region_start_offset + matches[0].start()),
                text=preamble,
            )
        )

    for i, m in enumerate(matches):
        section_number = f"Article {m.group(1)}"
        heading = m.group(2).strip()
        body_start = m.start()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[body_start:body_end]
        if len(body) < MIN_SECTION_BODY_CHARS:
            continue

        abs_body_start = region_start_offset + body_start
        slug = m.group(1)
        lettered_clause_count = len(_monotonic_lettered_clauses(body))
        if lettered_clause_count >= MIN_LETTERED_CLAUSES_TO_SPLIT:
            chunks.extend(
                _split_by_lettered_clauses(doc_id, section_number, heading, body, abs_body_start, offsets)
            )
        elif len(body) > MAX_CHUNK_CHARS:
            chunks.extend(
                _split_section_body(doc_id, section_number, heading, body, abs_body_start, offsets)
            )
        else:
            chunks.append(
                Chunk(
                    doc_id=doc_id,
                    chunk_id=f"{doc_id}::article-{slug}",
                    heading=heading,
                    section_number=section_number,
                    parent_section_number=None,
                    page_start=_page_for_offset(offsets, abs_body_start),
                    page_end=_page_for_offset(offsets, region_start_offset + body_end),
                    text=body.strip(),
                )
            )
    return chunks


def _chunk_region(
    doc_id: str, text: str, region_start_offset: int, offsets: list[int]
) -> list[Chunk]:
    """Chunk one contiguous region (e.g. one chapter, or the whole doc) by numbered sections."""
    raw_matches = list(SECTION_RE.finditer(text))
    content_filtered = [
        m for m in raw_matches
        if not FOOTNOTE_CONTENT_RE.match(m.group(2)) and not _PLAUSIBLE_YEAR_RE.match(m.group(1))
    ]
    matches = _filter_monotonic(content_filtered)
    if len(matches) < 2:
        article_matches = list(ARTICLE_HEADING_RE.finditer(text))
        if len(article_matches) >= 2:
            return _chunk_treaty_articles(doc_id, text, region_start_offset, offsets, article_matches)
        return _fallback_paragraph_chunks(
            doc_id, text, offsets, region_start_offset, heading="(unstructured)"
        )

    chunks = []
    preamble = text[: matches[0].start()].strip()
    if len(preamble) >= MIN_SECTION_BODY_CHARS:
        abs_start = region_start_offset
        abs_end = region_start_offset + matches[0].start()
        chunks.append(
            Chunk(
                doc_id=doc_id,
                chunk_id=f"{doc_id}::preamble",
                heading="Preamble",
                section_number=None,
                parent_section_number=None,
                page_start=_page_for_offset(offsets, abs_start),
                page_end=_page_for_offset(offsets, abs_end),
                text=preamble,
            )
        )
    for i, m in enumerate(matches):
        section_number = m.group(1)
        rest_of_line = m.group(2)
        body_start = m.start()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[body_start:body_end]
        if len(body) < MIN_SECTION_BODY_CHARS:
            continue

        # Heading = the title text, only if this section actually has one on its
        # opening line before an em/en-dash (Act style, e.g. "3. What are not
        # inventions.—"). Numbered-paragraph guidelines have no such title, so
        # don't misread their first sentence as a heading.
        heading_match = re.match(r"([^—–]{1,150})[—–]", rest_of_line)
        heading = heading_match.group(1).strip().rstrip(".") if heading_match else ""
        if not heading:
            # The Biological Diversity Act, 2002 prints section titles with NO
            # em/en-dash at all -- e.g. "55. Penalties." -- so the dash pattern
            # above misses every one of its sections, and they all fell through
            # to the generic "Paragraph N" below. Confirmed directly:
            # ::sec-55 (the section that answers the Act's own penalty
            # question) and ::sec-6 (the section sec-55 cross-references, by
            # number only, for the underlying approval requirement) both had
            # heading "Paragraph N" instead of their real title -- see
            # docs/decisions.md. Some of this Act's titles wrap onto the line
            # immediately after the section number (e.g. "6. Application for
            # ... without approval of \nNational Biodiversity Authority."), so
            # the candidate is allowed to borrow that one continuation line --
            # but no further, since a real title never runs past two printed
            # lines in this corpus while ordinary body prose regularly does.
            #
            # Numbered-paragraph guidelines (WIPO toolkit, IPO TK guidelines)
            # have no title at all -- their numbered "paragraph" IS the body,
            # so a short, period-terminated first sentence must not be misread
            # as a heading (the same risk the dash-pattern comment above
            # warns about). What tells the two apart isn't the candidate text
            # itself -- a real title and a short standalone sentence can look
            # identical -- it's what's left over afterwards: a real heading is
            # always followed by the section's own substantive body, whereas a
            # guideline paragraph's opening sentence is often the entire
            # paragraph, with nothing left but the next section marker.
            body_lines = body.splitlines()
            first_line = rest_of_line.strip()
            candidate = first_line
            consumed_lines = 1
            if not candidate.endswith(".") and len(body_lines) > 1:
                second_line = body_lines[1].strip()
                candidate = f"{first_line} {second_line}".strip()
                consumed_lines = 2
            remaining_body = "\n".join(body_lines[consumed_lines:]).strip()
            is_title_like = (
                candidate
                and len(candidate) <= 150
                and len(candidate.split()) <= _MAX_TITLE_WORDS
                and candidate.endswith(".")
                and candidate.count(".") == 1  # a single terminal period, not a full sentence
                and not candidate[:1].islower()
                and not _FINITE_VERB_RE.search(candidate)
                and len(remaining_body) >= MIN_SECTION_BODY_CHARS
            )
            heading = candidate.rstrip(".") if is_title_like else f"Paragraph {section_number}"

        abs_body_start = region_start_offset + body_start
        lettered_clause_count = len(_monotonic_lettered_clauses(body))
        numeric_subsection_count = len(SUBSECTION_RE.findall(body))
        if _INLINE_FIRST_SUBSECTION_RE.search(body[:300]):
            numeric_subsection_count += 1
        if lettered_clause_count >= MIN_LETTERED_CLAUSES_TO_SPLIT and numeric_subsection_count < 2:
            chunks.extend(
                _split_by_lettered_clauses(
                    doc_id, section_number, heading, body, abs_body_start, offsets
                )
            )
        elif len(body) > MAX_CHUNK_CHARS:
            chunks.extend(
                _split_section_body(
                    doc_id, section_number, heading, body, abs_body_start, offsets
                )
            )
        else:
            chunks.append(
                Chunk(
                    doc_id=doc_id,
                    chunk_id=f"{doc_id}::sec-{section_number}",
                    heading=heading,
                    section_number=section_number,
                    parent_section_number=None,
                    page_start=_page_for_offset(offsets, abs_body_start),
                    page_end=_page_for_offset(offsets, region_start_offset + body_end),
                    text=body.strip(),
                )
            )
    return chunks


def chunk_document(doc_id: str, pages: list[str], body_start_anchor: str | None = None) -> list[Chunk]:
    """Chunk a document's pages into structural chunks.

    body_start_anchor: if given, text before the first occurrence of this string
    (e.g. the enacting formula of an Act) is treated as front matter / table of
    contents and kept as a single unindexed-style chunk rather than being scanned
    for section numbers (a TOC lists section numbers too, and would otherwise be
    misread as real sections).
    """
    full_text, offsets = _build_page_offsets(pages)

    anchor_pos = 0
    front_matter_chunks: list[Chunk] = []
    if body_start_anchor:
        found = full_text.find(body_start_anchor)
        if found == -1:
            raise ValueError(
                f"{doc_id}: body_start_anchor {body_start_anchor!r} not found in extracted "
                "text (PDF text extraction can insert stray spaces/line-wraps — check the "
                "exact substring rather than silently chunking the whole document, TOC included)"
            )
        else:
            anchor_pos = found
            front_text = full_text[:anchor_pos].strip()
            if front_text:
                front_matter_chunks.append(
                    Chunk(
                        doc_id=doc_id,
                        chunk_id=f"{doc_id}::front-matter",
                        heading="Front matter / table of contents",
                        section_number=None,
                        parent_section_number=None,
                        page_start=_page_for_offset(offsets, 0),
                        page_end=_page_for_offset(offsets, anchor_pos),
                        text=front_text,
                    )
                )

    body_text = full_text[anchor_pos:]
    # Section numbering runs continuously across the whole document (it does not
    # restart per chapter), so matching/monotonic-filtering must run once over
    # the whole body — doing it chapter-by-chapter let a footnote's low number
    # slip past the monotonic check again at the start of each new chapter.
    chunks = list(front_matter_chunks)
    chunks.extend(_chunk_region(doc_id, body_text, anchor_pos, offsets))
    return chunks


# Build-time ceiling, deliberately NOT the same thing as MAX_CHUNK_CHARS
# (3000) above: that one is the splitting target the chunker aims for, while
# this is the point past which a chunk proves structure detection failed
# outright. The largest chunk in the clean 7-document corpus is 17,978 chars
# (WIPO toolkit), so this sits just above the real-world maximum. Not a style
# rule: a 79,710-char chunk once silently overflowed the local model's context
# window and produced a truncated answer with no error (docs/memory.md,
# 2026-09-15).
MAX_INDEXABLE_CHUNK_CHARS = 20_000


def validate_chunks(doc_id: str, chunks: list) -> None:
    """Raise if chunking produced output that would corrupt the index.

    Both failures here are silent ones, which is why they are checked at build
    time rather than trusted. Duplicate chunk_ids are the worse of the two:
    the vector store upserts by id, so duplicates do not error — they
    overwrite, and the corpus quietly ends up smaller than the chunk count
    says. A 635-page Act+Rules+Schedules compilation produced 1063 chunks
    under only 164 distinct ids, which would have discarded 899 of them
    without a word.
    """
    seen: dict[str, int] = {}
    for c in chunks:
        seen[c.chunk_id] = seen.get(c.chunk_id, 0) + 1
    duplicates = {cid: n for cid, n in seen.items() if n > 1}
    if duplicates:
        worst = sorted(duplicates.items(), key=lambda kv: -kv[1])[:5]
        raise ValueError(
            f"{doc_id}: {len(duplicates)} duplicate chunk_id(s) would silently "
            f"discard {sum(n - 1 for n in duplicates.values())} of {len(chunks)} "
            f"chunks at index time. Worst: {worst}. The document's numbering "
            f"most likely restarts (Act vs Rules vs Schedules) and needs "
            f"splitting into separate doc_ids, or a chunker that namespaces by part."
        )
    oversized = [c for c in chunks if c.char_count > MAX_INDEXABLE_CHUNK_CHARS]
    if oversized:
        worst = sorted(oversized, key=lambda c: -c.char_count)[:5]
        raise ValueError(
            f"{doc_id}: {len(oversized)} chunk(s) exceed MAX_INDEXABLE_CHUNK_CHARS "
            f"({MAX_INDEXABLE_CHUNK_CHARS}), meaning structure detection failed and whole "
            f"page ranges were swallowed. Worst: "
            + ", ".join(f"{c.chunk_id} ({c.char_count} chars, p{c.page_start}-{c.page_end})" for c in worst)
        )
