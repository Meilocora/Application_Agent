"""Load the candidate's documents and turn them into a structured CandidateProfile.

Extraction costs an LLM call, so the result is cached on disk and only recomputed when
the documents change (detected via a content hash).
"""

import hashlib
import json
from pathlib import Path

from agents import Runner
from docx import Document
from docx.table import Table
from pypdf import PdfReader

from application_agent.config import DATA_DIR, PROFILE_DIR
from application_agent.job_agents import profile_extractor
from application_agent.models import CandidateProfile

SUPPORTED_SUFFIXES = {".pdf", ".docx", ".md", ".txt"}  # .docx only - the old binary .doc is not supported
CACHE_FILE = DATA_DIR / "profile_cache.json"


def _read_table(table: Table) -> list[str]:
    """One line per table row, cells separated by " | "."""
    lines = []
    for row in table.rows:
        cells: list[str] = []
        for cell in row.cells:
            text = cell.text.strip()
            # Merged cells are returned once per grid column - keep each text only once.
            if text and (not cells or cells[-1] != text):
                cells.append(text)
        if cells:
            lines.append(" | ".join(cells))
    return lines


def _read_docx(path: Path) -> str:
    """Text of a Word file. CVs often use tables for their layout, so tables are read too."""
    lines: list[str] = []
    # iter_inner_content() keeps the order of paragraphs and tables as in the document.
    for block in Document(str(path)).iter_inner_content():
        if isinstance(block, Table):
            lines.extend(_read_table(block))
        elif block.text.strip():
            lines.append(block.text)
    return "\n".join(lines)


def _read_file(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
    if suffix == ".docx":
        return _read_docx(path)
    return path.read_text(encoding="utf-8")


def load_documents(profile_dir: Path = PROFILE_DIR) -> str:
    """Concatenate all supported documents, each prefixed with its file name."""
    files = sorted(
        p
        for p in profile_dir.glob("*")
        # "~$CV.docx" is the lock file Word creates while CV.docx is open - not a document.
        if p.suffix.lower() in SUPPORTED_SUFFIXES and not p.name.startswith("~$")
    )
    if not files:
        raise FileNotFoundError(f"No profile documents found in {profile_dir}. Put your CV there as PDF or Word file.")
    return "\n\n".join(f"=== {path.name} ===\n{_read_file(path).strip()}" for path in files)


async def get_profile(force_refresh: bool = False) -> CandidateProfile:
    """Return the candidate profile, from cache if the documents are unchanged."""
    documents = load_documents()
    digest = hashlib.sha256(documents.encode()).hexdigest() # Compute a hash of the concatenated documents to detect changes

    # Check cache first
    if not force_refresh and CACHE_FILE.exists():
        cached = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        if cached["hash"] == digest:
            return CandidateProfile.model_validate(cached["profile"])

    # If cache is missing or outdated, extract profile from documents
    result = await Runner.run(profile_extractor, documents)
    profile: CandidateProfile = result.final_output

    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(
        json.dumps({"hash": digest, "profile": profile.model_dump()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return profile
