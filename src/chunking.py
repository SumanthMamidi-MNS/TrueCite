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
  3. If a section's body is long, split further at numbered sub-clauses
     ("(1)", "(2)", ...) at line start, keeping the parent section number attached.
  4. If no numbering is detected at all, fall back to paragraph grouping
     (blank-line-delimited), merged up to a target size — still never mid-sentence.
"""
import re
from bisect import bisect_right
from dataclasses import dataclass, field

SECTION_RE = re.compile(r"^[ \t]*(\d{1,4}[A-Z]{0,2})\.\s+(.*)$", re.MULTILINE)
SUBSECTION_RE = re.compile(r"^[ \t]*\((\d{1,3}[A-Za-z]?)\)\s+", re.MULTILINE)

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

# Sections this short are almost always false positives from stray numbering,
# not real structure (a real Act section always has substantive body text).
MIN_SECTION_BODY_CHARS = 20
MAX_CHUNK_CHARS = 3000
PARAGRAPH_TARGET_CHARS = 1200


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
_PAGE_NUMBER_LINE_RE = re.compile(r"^\s*\d{1,4}\s*$", re.MULTILINE)
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


def _clean_page_text(text: str) -> str:
    text = _FOOTNOTE_LINE_RE.sub("", text)
    text = _PAGE_NUMBER_LINE_RE.sub("", text)
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


def _split_into_paragraphs(text: str) -> list[str]:
    raw = re.split(r"\n\s*\n", text)
    return [p.strip() for p in raw if p.strip()]


def _merge_paragraphs(paragraphs: list[str], target_chars: int) -> list[str]:
    merged, current = [], ""
    for para in paragraphs:
        if current and len(current) + len(para) > target_chars:
            merged.append(current)
            current = para
        else:
            current = f"{current}\n\n{para}" if current else para
    if current:
        merged.append(current)
    return merged


def _fallback_paragraph_chunks(
    doc_id: str, text: str, offsets: list[int], base_offset: int, heading: str
) -> list[Chunk]:
    paragraphs = _split_into_paragraphs(text)
    merged = _merge_paragraphs(paragraphs, PARAGRAPH_TARGET_CHARS)
    chunks = []
    cursor = 0
    for i, block in enumerate(merged, start=1):
        start = base_offset + text.index(block, cursor)
        cursor = text.index(block, cursor) + len(block)
        end = start + len(block)
        chunks.append(
            Chunk(
                doc_id=doc_id,
                chunk_id=f"{doc_id}::para-{i}",
                heading=heading,
                section_number=None,
                parent_section_number=None,
                page_start=_page_for_offset(offsets, start),
                page_end=_page_for_offset(offsets, end),
                text=block,
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
    if len(matches) < 2:
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


def _chunk_region(
    doc_id: str, text: str, region_start_offset: int, offsets: list[int]
) -> list[Chunk]:
    """Chunk one contiguous region (e.g. one chapter, or the whole doc) by numbered sections."""
    raw_matches = list(SECTION_RE.finditer(text))
    content_filtered = [m for m in raw_matches if not FOOTNOTE_CONTENT_RE.match(m.group(2))]
    matches = _filter_monotonic(content_filtered)
    if len(matches) < 2:
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
            heading = f"Paragraph {section_number}"

        abs_body_start = region_start_offset + body_start
        if len(body) > MAX_CHUNK_CHARS:
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
