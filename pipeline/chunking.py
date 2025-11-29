import re
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional

import nltk
nltk.download('punkt')
from nltk.tokenize import sent_tokenize

from dataclasses import dataclass
from typing import List

SECTION_PATTERNS = {
    "DECISION": [
        r'\bD\sE\sC\sI\sS\sI\sO\sN\b'
    ],
    "SYLLABUS": [
        r'\bSYLLABUS\b'
    ],
    "FACTS": [
        r'\bTHE\s+FACTS\b',
        r'\bSTATEMENT\s+OF\s+FACTS\b',
        r'\bFACTS\b'
    ],
    "ISSUES": [
        r'\bISSUE[S]?\b',
        r'\bASSIGNED\s+ERRORS\b'
    ],
    "RULING": [
        r'\bRULING\b',
        r'\bDISCUSSION\b',
        r'\bTHE\s+COURT[’\'`]S?\s+RULING\b'
    ],
    "WHEREFORE": [
        r'\bWHEREFORE\b',
        r'\bSO\s+ORDERED\b'
    ]
}

@dataclass
class CaseMetadata:
    case_no: Optional[str]
    division: Optional[str]
    title: Optional[str]

def extract_case_metadata(text: str) -> CaseMetadata:
    """
    Very lightweight heuristics to grab:
    - G.R. No.
    - Division (FIRST/SECOND/THIRD/EN BANC)
    - Title (first non-empty line, usually)
    """
    # Case number like: G.R. No. 123456, G.R. Nos. 123456-78
    case_no_match = re.search(r'G\.\s*R\.\s*No[s]?\.\s*([A-Za-z0-9\-]+)', text)
    case_no = case_no_match.group(0) if case_no_match else None

    # Division (FIRST/SECOND/THIRD/EN BANC DIVISION)
    division_match = re.search(
        r'\b(FIRST|SECOND|THIRD)\s+DIVISION\b|\bEN\s+BANC\b',
        text,
        flags=re.IGNORECASE
    )
    division = division_match.group(0).upper() if division_match else None

    # Title: usually in first few lines; just grab a reasonable line
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    title = None
    if lines:
        # Sometimes first line is "Republic of the Philippines", so skip obvious boilerplate
        for ln in lines[:20]:
            if not re.search(r'Republic of the Philippines|Supreme Court', ln, re.IGNORECASE):
                title = ln
                break

    return CaseMetadata(case_no=case_no, division=division, title=title)

def build_section_regex():
    """
    Build a regex that matches any of the known section headings,
    but WITHOUT named groups. We'll map headings manually later.
    """
    all_patterns = []
    for patterns in SECTION_PATTERNS.values():
        for p in patterns:
            # Allow optional colon and ensure full line match
            all_patterns.append(rf"(?:{p})\s*:?\s*$")

    combined = r"^\s*(?:" + "|".join(all_patterns) + r")"
    return re.compile(combined, flags=re.MULTILINE | re.IGNORECASE)

SECTION_REGEX = build_section_regex()

@dataclass
class Section:
    name: str
    text: str

def identify_section_name_from_line(line: str) -> str | None:
    """
    Given a single line (no newline endings), return the canonical section
    name (e.g. 'FACTS') if this line is a heading, otherwise None.
    """
    stripped = line.strip()
    if not stripped:
        return None

    # Remove trailing colon if present: "FACTS:" -> "FACTS"
    stripped = stripped.rstrip(':').strip()

    for canonical, patterns in SECTION_PATTERNS.items():
        for p in patterns:
            # We treat patterns as plain strings here; make them strict equality
            if re.fullmatch(p, stripped, flags=re.IGNORECASE):
                return canonical

    return None


def split_into_sections_line_based(text: str) -> List[Section]:
    """
    Split the decision into sections using line-based heading detection.
    Handles cases where headings have blank lines before and after.
    """
    lines = text.split('\n')

    sections: List[Section] = []
    current_name = "PREAMBLE"
    current_lines: List[str] = []

    def flush_section():
        nonlocal current_name, current_lines, sections
        content = "\n".join(current_lines).strip()
        if content:
            sections.append(Section(name=current_name, text=content))
        current_lines = []

    for line in lines:
        maybe_name = identify_section_name_from_line(line)

        if maybe_name is not None:
            # We hit a new heading line like "FACTS" / "WHEREFORE", etc.

            # 1) Flush previous section if it has content
            flush_section()

            # 2) Start new section; we will keep the heading inside the text
            current_name = maybe_name
            # You can choose whether to include the heading text into the body
            current_lines = [f"{maybe_name}:", ""]  # empty line after heading
        else:
            # Just part of the current section body
            current_lines.append(line)

    # Flush last section
    flush_section()

    # If we never saw any headings, you'll just get PREAMBLE as FULL_TEXT
    if len(sections) == 1 and sections[0].name == "PREAMBLE":
        sections[0].name = "FULL_TEXT"

    return sections

def chunk_sentences(
    text: str,
    max_tokens: int = 350,
    overlap_sentences: int = 2
) -> List[str]:
    """
    Chunk text into sentence groups with token-length constraint
    and sentence-level overlap.
    """
    sentences = sent_tokenize(text)
    chunks: List[str] = []
    current: List[str] = []
    current_len = 0

    def token_count(s: str) -> int:
        return len(s.split())

    for i, sent in enumerate(sentences):
        sent_tokens = token_count(sent)

        # If adding this sentence stays within limit: just add
        if current_len + sent_tokens <= max_tokens:
            current.append(sent)
            current_len += sent_tokens
        else:
            # Close current chunk
            if current:
                chunks.append(" ".join(current))

            # Build new current chunk with overlap sentences + this one
            if overlap_sentences > 0:
                overlap = sentences[max(0, i - overlap_sentences):i]
            else:
                overlap = []

            current = overlap + [sent]
            current_len = sum(token_count(s) for s in current)

    if current:
        chunks.append(" ".join(current))

    # Remove tiny chunks (optional)
    cleaned_chunks = []
    for ch in chunks:
        if len(ch.split()) < 15 and cleaned_chunks:
            # Merge tiny chunk into previous
            cleaned_chunks[-1] += " " + ch
        else:
            cleaned_chunks.append(ch)

    return cleaned_chunks

@dataclass
class RagChunk:
    case_no: Optional[str]
    division: Optional[str]
    title: Optional[str]
    section: str
    chunk_index: int
    text: str

def build_rag_chunks(
    full_text: str,
    max_tokens: int = 350,
    overlap_sentences: int = 2
) -> List[Dict]:
    """
    High-level pipeline:
    1. Extract case metadata
    2. Split into sections
    3. Chunk each section by sentences with overlap
    4. Return list of dicts for storage
    """
    meta = extract_case_metadata(full_text)
    sections = split_into_sections_line_based(full_text)

    rag_chunks: List[RagChunk] = []

    for section in sections:
        sec_chunks = chunk_sentences(
            section.text,
            max_tokens=max_tokens,
            overlap_sentences=overlap_sentences
        )

        for idx, ch in enumerate(sec_chunks):
            rag_chunks.append(
                RagChunk(
                    case_no=meta.case_no,
                    division=meta.division,
                    title=meta.title,
                    section=section.name,
                    chunk_index=idx,
                    text=ch
                )
            )

    # Convert to serializable dicts
    return [asdict(c) for c in rag_chunks]
