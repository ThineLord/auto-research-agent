"""Deterministic literature survey mode.

The survey workflow intentionally avoids provider calls. It collects paper-like
metadata from the selected project, normalizes and deduplicates it, then writes a
structured survey report plus machine-readable metadata.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlparse

from rich.console import Console

from .config import LiteratureSurveyConfig
from .project_input import ProjectInput
from .storage import display_path, write_json_file, write_text

COMMON_WORDS = {
    "about",
    "across",
    "after",
    "against",
    "agent",
    "agents",
    "also",
    "among",
    "approach",
    "based",
    "because",
    "been",
    "being",
    "benchmark",
    "benchmarks",
    "between",
    "data",
    "dataset",
    "datasets",
    "during",
    "each",
    "evaluation",
    "from",
    "have",
    "into",
    "large",
    "learning",
    "method",
    "methods",
    "model",
    "models",
    "paper",
    "papers",
    "research",
    "results",
    "study",
    "system",
    "systems",
    "task",
    "tasks",
    "that",
    "their",
    "these",
    "this",
    "through",
    "using",
    "with",
    "work",
}

TOPIC_KEYWORDS = (
    "agent",
    "alignment",
    "benchmark",
    "context",
    "dataset",
    "evaluation",
    "memory",
    "planning",
    "privacy",
    "rag",
    "reasoning",
    "retrieval",
    "safety",
    "survey",
    "tool",
)
METHOD_KEYWORDS = (
    "ablation",
    "adapter",
    "anonymization",
    "attention",
    "chain-of-thought",
    "classification",
    "clustering",
    "contrastive",
    "differential privacy",
    "fine-tuning",
    "graph",
    "prompting",
    "redaction",
    "retrieval",
    "simulation",
    "synthetic data",
)
DATASET_KEYWORDS = (
    "arc",
    "daily dialog",
    "dailydialog",
    "gsm8k",
    "hotpotqa",
    "mmlu",
    "persona-chat",
    "squad",
    "truthfulqa",
)
BENCHMARK_KEYWORDS = (
    "accuracy",
    "auc",
    "benchmark",
    "bleu",
    "exact match",
    "f1",
    "human evaluation",
    "latency",
    "precision",
    "recall",
    "rouge",
    "win rate",
)

FIELD_ALIASES = {
    "title": "title",
    "paper": "title",
    "name": "title",
    "authors": "authors",
    "author": "authors",
    "year": "year",
    "date": "year",
    "venue": "venue",
    "conference": "venue",
    "journal": "venue",
    "url": "url",
    "link": "url",
    "doi": "doi",
    "arxiv": "arxiv_id",
    "arxiv_id": "arxiv_id",
    "arxiv id": "arxiv_id",
    "abstract": "abstract",
    "summary": "abstract",
    "topic": "topics",
    "topics": "topics",
    "theme": "topics",
    "themes": "topics",
    "method": "methods",
    "methods": "methods",
    "approach": "methods",
    "approaches": "methods",
    "benchmark": "benchmarks",
    "benchmarks": "benchmarks",
    "metric": "benchmarks",
    "metrics": "benchmarks",
    "dataset": "datasets",
    "datasets": "datasets",
    "data": "datasets",
    "limitation": "limitations",
    "limitations": "limitations",
    "weakness": "limitations",
    "weaknesses": "limitations",
    "future": "future_work",
    "future work": "future_work",
    "future direction": "future_work",
    "future directions": "future_work",
    "open problem": "future_work",
    "open problems": "future_work",
}


@dataclass
class PaperMetadata:
    title: str
    authors: tuple[str, ...] = ()
    year: int | None = None
    venue: str = ""
    url: str = ""
    doi: str = ""
    arxiv_id: str = ""
    abstract: str = ""
    topics: tuple[str, ...] = ()
    methods: tuple[str, ...] = ()
    benchmarks: tuple[str, ...] = ()
    datasets: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    future_work: tuple[str, ...] = ()
    source_paths: tuple[str, ...] = ()
    source_kinds: tuple[str, ...] = ()
    raw_citation: str = ""


@dataclass
class SurveyResult:
    papers: list[PaperMetadata]
    source_files: list[Path]
    report_path: Path
    metadata_path: Path
    related_work_path: Path
    manifest_path: Path


def _normalize_space(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _split_list(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        raw_items = [str(item) for item in value]
    else:
        text = str(value)
        raw_items = re.split(r"\s*(?:,|;|\||/|\band\b)\s*", text)
    items: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        cleaned = _normalize_space(item).strip(" .")
        if not cleaned:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        items.append(cleaned)
    return tuple(items)


def _clean_url(value: str) -> str:
    url = _normalize_space(value).strip("<>()[]{}.,;")
    if not url:
        return ""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return ""
    return url.rstrip(".")


def _normalize_doi(value: str) -> str:
    text = _normalize_space(value).strip("<>()[]{}.,;")
    if not text:
        return ""
    text = re.sub(r"^(?:doi:\s*|https?://(?:dx\.)?doi\.org/)", "", text, flags=re.IGNORECASE)
    match = re.search(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", text, flags=re.IGNORECASE)
    if not match:
        return ""
    return match.group(0).rstrip(".,;)").lower()


def _normalize_arxiv_id(value: str) -> str:
    text = _normalize_space(value).strip("<>()[]{}.,;")
    if not text:
        return ""
    text = re.sub(r"^(?:arxiv:\s*|https?://arxiv\.org/(?:abs|pdf)/)", "", text, flags=re.IGNORECASE)
    text = text.removesuffix(".pdf").strip()
    patterns = (
        r"(?P<new>[0-9]{4}\.[0-9]{4,5})(?:v\d+)?",
        r"(?P<old>[a-z-]+(?:\.[a-z-]+)?/[0-9]{7})(?:v\d+)?",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            groups = match.groupdict()
            return (groups.get("new") or groups.get("old") or "").casefold()
    return ""


def _extract_year(value: object) -> int | None:
    match = re.search(r"\b(19|20)\d{2}\b", str(value or ""))
    if not match:
        return None
    return int(match.group(0))


def _extract_url(text: str) -> str:
    match = re.search(r"https?://[^\s)\]>\"']+", text)
    return _clean_url(match.group(0)) if match else ""


def _extract_doi(text: str) -> str:
    return _normalize_doi(text)


def _extract_arxiv_id(text: str) -> str:
    patterns = (
        r"arxiv[:\s]+([0-9]{4}\.[0-9]{4,5}(?:v\d+)?|[a-z-]+(?:\.[a-z-]+)?/[0-9]{7}(?:v\d+)?)",
        r"arxiv\.org/(?:abs|pdf)/([0-9]{4}\.[0-9]{4,5}(?:v\d+)?|[a-z-]+(?:\.[a-z-]+)?/[0-9]{7}(?:v\d+)?)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return _normalize_arxiv_id(match.group(1))
    return ""


def _strip_identifier_noise(text: str) -> str:
    stripped = re.sub(r"https?://[^\s)\]>\"']+", " ", text)
    stripped = re.sub(
        r"\bdoi:\s*10\.\d{4,9}/[-._;()/:A-Z0-9]+\b",
        " ",
        stripped,
        flags=re.IGNORECASE,
    )
    stripped = re.sub(
        r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b",
        " ",
        stripped,
        flags=re.IGNORECASE,
    )
    stripped = re.sub(
        r"\barxiv[:\s]+(?:[0-9]{4}\.[0-9]{4,5}(?:v\d+)?|[a-z-]+(?:\.[a-z-]+)?/[0-9]{7}(?:v\d+)?)",
        " ",
        stripped,
        flags=re.IGNORECASE,
    )
    return _normalize_space(stripped)


def _canonical_title(title: str) -> str:
    normalized = title.casefold()
    normalized = re.sub(r"`[^`]*`", " ", normalized)
    normalized = re.sub(r"https?://\S+", " ", normalized)
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return _normalize_space(normalized)


def _dedupe_tuple(*groups: Sequence[str]) -> tuple[str, ...]:
    items: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for item in group:
            cleaned = _normalize_space(item).strip(" .")
            if not cleaned:
                continue
            key = cleaned.casefold()
            if key in seen:
                continue
            seen.add(key)
            items.append(cleaned)
    return tuple(items)


def _clip_sentence(text: str, max_chars: int = 220) -> str:
    cleaned = _normalize_space(text)
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 3].rstrip(" ,;") + "..."


def _term_matches(text: str, terms: Sequence[str]) -> tuple[str, ...]:
    lower = text.casefold()
    matches: list[str] = []
    for term in terms:
        if re.search(rf"(?<![a-z0-9]){re.escape(term.casefold())}(?![a-z0-9])", lower):
            matches.append(term)
    return tuple(matches)


def _key_phrases(text: str, *, limit: int = 5) -> tuple[str, ...]:
    words = [
        word.casefold()
        for word in re.findall(r"[A-Za-z][A-Za-z0-9\-]{3,}", text)
        if word.casefold() not in COMMON_WORDS
    ]
    counts = Counter(words)
    return tuple(word for word, _count in counts.most_common(limit))


def _extract_issue_lines(text: str, markers: Sequence[str], *, limit: int = 4) -> tuple[str, ...]:
    lines: list[str] = []
    marker_pattern = re.compile("|".join(re.escape(marker) for marker in markers), re.IGNORECASE)
    for raw_line in text.splitlines():
        line = _normalize_space(raw_line).strip("-*#> ")
        if len(line) < 20:
            continue
        if marker_pattern.search(line):
            lines.append(_clip_sentence(line))
        if len(lines) >= limit:
            break
    return tuple(lines)


def _source_kind(path: Path, project_dir: Path) -> str:
    rel = path.resolve().relative_to(project_dir.resolve()).as_posix()
    if rel == "task.md":
        return "task"
    if rel == "memory.md":
        return "memory"
    if rel.startswith("runs/"):
        return "run_output"
    if rel.startswith("outputs/") or rel.startswith("artifacts/"):
        return "artifact"
    return "project_markdown"


def collect_source_files(project_dir: Path, config: LiteratureSurveyConfig) -> list[Path]:
    """Collect survey source files from a project without leaving the project root."""

    candidates: dict[Path, None] = {}
    if config.include_task:
        candidates[project_dir / "task.md"] = None
    if config.include_memory:
        candidates[project_dir / "memory.md"] = None
    if config.include_project_markdown:
        for path in project_dir.glob("*.md"):
            candidates[path] = None
    if config.include_run_outputs:
        for path in project_dir.glob("runs/**/*.md"):
            candidates[path] = None

    for glob_pattern in config.source_globs:
        for path in project_dir.glob(glob_pattern):
            candidates[path] = None

    source_files: list[Path] = []
    project_resolved = project_dir.resolve()
    for path in sorted(candidates, key=lambda item: item.as_posix()):
        try:
            resolved = path.resolve()
            resolved.relative_to(project_resolved)
        except ValueError:
            continue
        if not resolved.exists() or not resolved.is_file():
            continue
        if config.output_dir and config.output_dir in resolved.relative_to(project_resolved).parts:
            continue
        if resolved.suffix.lower() not in {".md", ".txt"}:
            continue
        source_files.append(resolved)
        if len(source_files) >= config.max_source_files:
            break
    return source_files


def _parse_yaml_like_frontmatter(text: str) -> list[dict[str, object]]:
    blocks: list[dict[str, object]] = []
    pattern = re.compile(r"(?ms)^---\s*\n(?P<body>.*?)\n---\s*$")
    for match in pattern.finditer(text):
        data: dict[str, object] = {}
        current_key = ""
        for raw_line in match.group("body").splitlines():
            line = raw_line.rstrip()
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            list_match = re.match(r"\s*-\s+(.+)", line)
            if list_match and current_key:
                current = data.setdefault(current_key, [])
                if isinstance(current, list):
                    current.append(list_match.group(1).strip())
                continue
            key_match = re.match(r"\s*([A-Za-z][A-Za-z0-9 _-]+):\s*(.*)", line)
            if key_match:
                key = key_match.group(1).strip().casefold().replace("-", " ")
                current_key = FIELD_ALIASES.get(key, key)
                value = key_match.group(2).strip().strip("\"'")
                data[current_key] = [] if value == "" else value
        if data.get("title"):
            blocks.append(data)
    return blocks


def _parse_key_value_blocks(text: str) -> list[dict[str, object]]:
    blocks: list[dict[str, object]] = []
    current: dict[str, object] = {}

    def flush() -> None:
        nonlocal current
        if current.get("title"):
            blocks.append(current)
        current = {}

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            if current:
                flush()
            continue
        match = re.match(
            r"^(?:[-*]\s*)?(?P<key>[A-Za-z][A-Za-z0-9 _/-]{1,30}):\s*(?P<value>.+)$",
            line,
        )
        if not match:
            continue
        key = match.group("key").strip().casefold().replace("-", " ")
        field_name = FIELD_ALIASES.get(key)
        if field_name is None:
            continue
        if field_name == "title" and current.get("title"):
            flush()
        current[field_name] = match.group("value").strip()
    if current:
        flush()
    return blocks


def _split_table_row(row: str) -> list[str]:
    stripped = row.strip().strip("|")
    return [_normalize_space(cell) for cell in stripped.split("|")]


def _is_separator_row(row: str) -> bool:
    cells = _split_table_row(row)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in cells)


def _parse_markdown_tables(text: str) -> list[dict[str, object]]:
    rows = text.splitlines()
    blocks: list[dict[str, object]] = []
    index = 0
    while index < len(rows) - 1:
        header_line = rows[index].strip()
        separator_line = rows[index + 1].strip()
        if "|" not in header_line or not _is_separator_row(separator_line):
            index += 1
            continue
        headers = [
            FIELD_ALIASES.get(cell.casefold().replace("-", " "), cell.casefold())
            for cell in _split_table_row(header_line)
        ]
        index += 2
        while index < len(rows) and "|" in rows[index]:
            cells = _split_table_row(rows[index])
            row_data = {
                headers[cell_index]: value
                for cell_index, value in enumerate(cells)
                if cell_index < len(headers) and value
            }
            if row_data.get("title"):
                blocks.append(row_data)
            index += 1
    return blocks


def _parse_references(text: str) -> list[dict[str, object]]:
    blocks: list[dict[str, object]] = []
    in_references = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if re.match(r"^#{1,4}\s+(references|bibliography|works cited)\b", line, re.IGNORECASE):
            in_references = True
            continue
        if in_references and re.match(r"^#{1,4}\s+\S+", line):
            break
        if not in_references:
            continue
        match = re.match(r"^(?:[-*]|\d+[.)])\s+(.+)$", line)
        if not match:
            continue
        citation = _normalize_space(match.group(1))
        if len(citation) < 20:
            continue
        year = _extract_year(citation)
        url = _extract_url(citation)
        doi = _extract_doi(citation)
        arxiv_id = _extract_arxiv_id(citation)
        if year is None and not (url or doi or arxiv_id):
            continue
        title = ""
        authors = ""
        venue = ""
        link_match = re.search(r"\[([^\]]+)]\((https?://[^)]+)\)", citation)
        if link_match:
            title = link_match.group(1)
            url = _clean_url(link_match.group(2)) or url
        year_match = re.search(r"\b(?:19|20)\d{2}\b", citation)
        if year_match:
            before_year = citation[: year_match.start()].strip(" ().")
            authors = _normalize_space(re.sub(r"\[[^\]]+]\([^)]+\)", " ", before_year))
            after_year = _strip_identifier_noise(citation[year_match.end() :]).strip(" ().")
            segments = [
                segment.strip(" .")
                for segment in re.split(r"\.\s+", after_year)
                if segment.strip(" .")
            ]
            if not title:
                title = segments[0] if segments else before_year
            if len(segments) > 1:
                venue = segments[1]
        title = _normalize_space(title).strip("- ")
        if not title:
            title = citation
        blocks.append(
            {
                "title": title,
                "authors": authors,
                "year": year,
                "venue": venue,
                "url": url,
                "doi": doi,
                "arxiv_id": arxiv_id,
                "raw_citation": citation,
            }
        )
    return blocks


def _paper_from_block(
    block: Mapping[str, object],
    *,
    source_path: Path,
    source_kind: str,
) -> PaperMetadata | None:
    title = _normalize_space(block.get("title", ""))
    if not title or len(_canonical_title(title)) < 4:
        return None
    abstract = _normalize_space(block.get("abstract", ""))
    raw_context = "\n".join(str(value) for value in block.values())
    url = _clean_url(str(block.get("url", ""))) or _extract_url(raw_context)
    doi = _normalize_doi(str(block.get("doi", ""))) or _extract_doi(raw_context)
    arxiv_id = _normalize_arxiv_id(str(block.get("arxiv_id", ""))) or _extract_arxiv_id(raw_context)
    context = f"{raw_context}\n{abstract}"
    topics = _dedupe_tuple(
        _split_list(block.get("topics")),
        _term_matches(context, TOPIC_KEYWORDS),
        _key_phrases(f"{title} {abstract}", limit=3),
    )
    methods = _dedupe_tuple(
        _split_list(block.get("methods")), _term_matches(context, METHOD_KEYWORDS)
    )
    benchmarks = _dedupe_tuple(
        _split_list(block.get("benchmarks")),
        _term_matches(context, BENCHMARK_KEYWORDS),
    )
    datasets = _dedupe_tuple(
        _split_list(block.get("datasets")), _term_matches(context, DATASET_KEYWORDS)
    )
    limitations = _dedupe_tuple(
        _split_list(block.get("limitations")),
        _extract_issue_lines(context, ("limitation", "weakness", "challenge", "risk"), limit=3),
    )
    future_work = _dedupe_tuple(
        _split_list(block.get("future_work")),
        _extract_issue_lines(context, ("future", "open problem", "gap", "next"), limit=3),
    )
    return PaperMetadata(
        title=title,
        authors=_split_list(block.get("authors")),
        year=_extract_year(block.get("year")),
        venue=_normalize_space(block.get("venue", "")),
        url=url,
        doi=doi,
        arxiv_id=arxiv_id,
        abstract=abstract,
        topics=topics,
        methods=methods,
        benchmarks=benchmarks,
        datasets=datasets,
        limitations=limitations,
        future_work=future_work,
        source_paths=(str(source_path),),
        source_kinds=(source_kind,),
        raw_citation=_normalize_space(block.get("raw_citation", "")),
    )


def parse_papers_from_file(path: Path, project_dir: Path) -> list[PaperMetadata]:
    text = path.read_text(encoding="utf-8", errors="replace")
    source_kind = _source_kind(path, project_dir)
    blocks: list[dict[str, object]] = []
    blocks.extend(_parse_yaml_like_frontmatter(text))
    blocks.extend(_parse_markdown_tables(text))
    blocks.extend(_parse_key_value_blocks(text))
    blocks.extend(_parse_references(text))
    papers: list[PaperMetadata] = []
    for block in blocks:
        paper = _paper_from_block(
            block,
            source_path=path,
            source_kind=source_kind,
        )
        if paper is not None:
            papers.append(paper)
    return papers


def _dedupe_keys(paper: PaperMetadata) -> tuple[str, ...]:
    keys: list[str] = []
    if paper.doi:
        keys.append(f"doi:{paper.doi.casefold()}")
    if paper.arxiv_id:
        keys.append(f"arxiv:{paper.arxiv_id.casefold()}")
    if paper.url:
        keys.append(f"url:{paper.url.casefold().rstrip('/')}")
    title_key = _canonical_title(paper.title)
    if title_key:
        keys.append(f"title:{title_key}")
    return tuple(dict.fromkeys(keys))


def _dedupe_key(paper: PaperMetadata) -> str:
    keys = _dedupe_keys(paper)
    return keys[0] if keys else f"title:{_canonical_title(paper.title)}"


def _prefer_text(*values: str) -> str:
    for value in values:
        cleaned = _normalize_space(value)
        if cleaned:
            return cleaned
    return ""


def _merge_papers(first: PaperMetadata, second: PaperMetadata) -> PaperMetadata:
    return PaperMetadata(
        title=_prefer_text(first.title, second.title),
        authors=_dedupe_tuple(first.authors, second.authors),
        year=first.year or second.year,
        venue=_prefer_text(first.venue, second.venue),
        url=_prefer_text(first.url, second.url),
        doi=_prefer_text(first.doi, second.doi),
        arxiv_id=_prefer_text(first.arxiv_id, second.arxiv_id),
        abstract=_prefer_text(first.abstract, second.abstract),
        topics=_dedupe_tuple(first.topics, second.topics),
        methods=_dedupe_tuple(first.methods, second.methods),
        benchmarks=_dedupe_tuple(first.benchmarks, second.benchmarks),
        datasets=_dedupe_tuple(first.datasets, second.datasets),
        limitations=_dedupe_tuple(first.limitations, second.limitations),
        future_work=_dedupe_tuple(first.future_work, second.future_work),
        source_paths=_dedupe_tuple(first.source_paths, second.source_paths),
        source_kinds=_dedupe_tuple(first.source_kinds, second.source_kinds),
        raw_citation=_prefer_text(first.raw_citation, second.raw_citation),
    )


def deduplicate_papers(papers: Iterable[PaperMetadata], *, max_papers: int) -> list[PaperMetadata]:
    by_key: dict[str, PaperMetadata] = {}
    for paper in papers:
        keys = _dedupe_keys(paper)
        existing_key = next((key for key in keys if key in by_key), "")
        if existing_key:
            merged = _merge_papers(by_key[existing_key], paper)
            for key in _dedupe_tuple(keys, _dedupe_keys(merged)):
                by_key[key] = merged
        else:
            for key in keys:
                by_key[key] = paper
    unique_papers: dict[str, PaperMetadata] = {}
    for paper in by_key.values():
        unique_papers[_dedupe_key(paper)] = paper
    return sorted(
        unique_papers.values(),
        key=lambda paper: (paper.year or 0, paper.title.casefold()),
        reverse=True,
    )[:max_papers]


def collect_papers(
    project_dir: Path, config: LiteratureSurveyConfig
) -> tuple[list[PaperMetadata], list[Path]]:
    source_files = collect_source_files(project_dir, config)
    collected: list[PaperMetadata] = []
    for path in source_files:
        collected.extend(parse_papers_from_file(path, project_dir))
    return deduplicate_papers(collected, max_papers=config.max_papers), source_files


def _count_terms(papers: Sequence[PaperMetadata], attr: str) -> Counter[str]:
    counter: Counter[str] = Counter()
    for paper in papers:
        counter.update(getattr(paper, attr))
    return counter


def _format_terms(terms: Iterable[str], *, empty: str = "not enough evidence") -> str:
    values = [_normalize_space(term) for term in terms if _normalize_space(term)]
    return ", ".join(values) if values else empty


def _format_paper_label(paper: PaperMetadata) -> str:
    year = f" ({paper.year})" if paper.year else ""
    venue = f", {paper.venue}" if paper.venue else ""
    return f"{paper.title}{year}{venue}"


def _representative_papers(
    papers: Sequence[PaperMetadata], *, limit: int = 8
) -> list[PaperMetadata]:
    return sorted(
        papers,
        key=lambda paper: (
            len(paper.topics) + len(paper.methods) + len(paper.benchmarks) + len(paper.datasets),
            len(paper.authors) + int(bool(paper.year)) + int(bool(paper.url or paper.doi)),
            paper.year or 0,
        ),
        reverse=True,
    )[:limit]


def _build_theme_groups(papers: Sequence[PaperMetadata]) -> dict[str, list[PaperMetadata]]:
    groups: dict[str, list[PaperMetadata]] = defaultdict(list)
    for paper in papers:
        keys = list(paper.topics[:3] or paper.methods[:2] or ("uncategorized",))
        for key in keys:
            groups[key].append(paper)
    return dict(sorted(groups.items(), key=lambda item: (-len(item[1]), item[0].casefold())))


def _metadata_quality_summary(papers: Sequence[PaperMetadata]) -> dict[str, int]:
    return {
        "paper_count": len(papers),
        "missing_authors_count": sum(1 for paper in papers if not paper.authors),
        "missing_year_count": sum(1 for paper in papers if paper.year is None),
        "missing_venue_count": sum(1 for paper in papers if not paper.venue),
        "missing_url_or_identifier_count": sum(
            1 for paper in papers if not (paper.url or paper.doi or paper.arxiv_id)
        ),
        "metadata_only_record_count": sum(1 for paper in papers if not paper.abstract),
        "with_doi_count": sum(1 for paper in papers if bool(paper.doi)),
        "with_arxiv_id_count": sum(1 for paper in papers if bool(paper.arxiv_id)),
        "with_url_count": sum(1 for paper in papers if bool(paper.url)),
    }


def _source_summary(source_files: Sequence[Path], project_dir: Path) -> dict[str, Any]:
    kind_counts = Counter(_source_kind(path, project_dir) for path in source_files)
    return {
        "source_file_count": len(source_files),
        "by_kind": dict(sorted(kind_counts.items())),
    }


def _representative_group_summary(
    papers: Sequence[PaperMetadata], *, limit: int = 8
) -> list[dict[str, Any]]:
    groups = _build_theme_groups(papers)
    summary: list[dict[str, Any]] = []
    for theme, theme_papers in list(groups.items())[:limit]:
        summary.append(
            {
                "theme": theme,
                "paper_count": len(theme_papers),
                "representative_titles": [
                    paper.title for paper in _representative_papers(theme_papers, limit=3)
                ],
            }
        )
    return summary


def _render_comparison_table(papers: Sequence[PaperMetadata]) -> str:
    lines = [
        "| Paper | Year | Themes | Methods | Benchmarks/Datasets | Limitations |",
        "|---|---:|---|---|---|---|",
    ]
    for paper in _representative_papers(papers, limit=12):
        eval_terms = _dedupe_tuple(paper.benchmarks, paper.datasets)
        lines.append(
            "| "
            f"{_format_paper_label(paper)} | "
            f"{paper.year or ''} | "
            f"{_format_terms(paper.topics[:4])} | "
            f"{_format_terms(paper.methods[:4])} | "
            f"{_format_terms(eval_terms[:4])} | "
            f"{_format_terms(paper.limitations[:2])} |"
        )
    return "\n".join(lines)


def generate_related_work(papers: Sequence[PaperMetadata]) -> str:
    if not papers:
        return (
            "Related work could not be generated because no paper metadata was found in the "
            "selected project sources. Add paper tables, references, or metadata blocks and rerun "
            "`--survey`."
        )

    groups = _build_theme_groups(papers)
    paragraphs: list[str] = []
    for theme, theme_papers in list(groups.items())[:4]:
        labels = [
            _format_paper_label(paper) for paper in _representative_papers(theme_papers, limit=4)
        ]
        method_terms = _count_terms(theme_papers, "methods").most_common(4)
        eval_terms = (
            _count_terms(theme_papers, "benchmarks") + _count_terms(theme_papers, "datasets")
        ).most_common(4)
        paragraphs.append(
            f"Work on {theme} is represented by {_format_terms(labels)}. "
            f"Across this cluster, recurring methods include "
            f"{_format_terms(term for term, _count in method_terms)}. "
            f"Evaluation commonly relies on {_format_terms(term for term, _count in eval_terms)}."
        )
    return "\n\n".join(paragraphs)


def generate_survey_report(
    *,
    papers: Sequence[PaperMetadata],
    source_files: Sequence[Path],
    project_input: ProjectInput,
    generated_at: str,
) -> str:
    theme_groups = _build_theme_groups(papers)
    topic_counts = _count_terms(papers, "topics")
    method_counts = _count_terms(papers, "methods")
    benchmark_counts = _count_terms(papers, "benchmarks")
    dataset_counts = _count_terms(papers, "datasets")
    limitation_counts = _count_terms(papers, "limitations")
    future_counts = _count_terms(papers, "future_work")
    representative = _representative_papers(papers)
    related_work = generate_related_work(papers)
    metadata_quality = _metadata_quality_summary(papers)

    lines: list[str] = [
        "# Literature Survey Report",
        "",
        f"- project: {project_input.project_name}",
        f"- title: {project_input.project_title}",
        f"- generated_at: {generated_at}",
        f"- source_files_scanned: {len(source_files)}",
        f"- unique_papers: {len(papers)}",
        "",
        "## Executive Summary",
        "",
    ]
    if papers:
        lines.extend(
            [
                f"This survey collected {len(papers)} unique papers from existing project files "
                f"and organized them into {len(theme_groups)} research themes.",
                f"Dominant themes: {_format_terms(term for term, _count in topic_counts.most_common(6))}.",
                f"Recurring methods: {_format_terms(term for term, _count in method_counts.most_common(6))}.",
                f"Common evaluation signals: {_format_terms(term for term, _count in (benchmark_counts + dataset_counts).most_common(6))}.",
            ]
        )
    else:
        lines.append(
            "No paper metadata was found. Add references, markdown tables, or Title/Authors/Year "
            "blocks to the selected project, then rerun survey mode."
        )

    lines.extend(["", "## Metadata Quality", ""])
    if papers:
        lines.extend(
            [
                f"- missing authors: {metadata_quality['missing_authors_count']}",
                f"- missing years: {metadata_quality['missing_year_count']}",
                f"- missing venues: {metadata_quality['missing_venue_count']}",
                "- missing URL/DOI/arXiv identifiers: "
                f"{metadata_quality['missing_url_or_identifier_count']}",
                f"- metadata-only records: {metadata_quality['metadata_only_record_count']}",
            ]
        )
    else:
        lines.append("- No paper records were available for quality checks.")

    lines.extend(["", "## Research Landscape", ""])
    if theme_groups:
        for theme, theme_papers in list(theme_groups.items())[:8]:
            lines.append(
                f"- {theme}: {len(theme_papers)} paper(s); representative work: "
                f"{_format_terms(_format_paper_label(paper) for paper in _representative_papers(theme_papers, limit=3))}."
            )
    else:
        lines.append("- No landscape groups available yet.")

    lines.extend(["", "## Major Themes", ""])
    if theme_groups:
        for theme, theme_papers in list(theme_groups.items())[:8]:
            methods = _count_terms(theme_papers, "methods").most_common(5)
            datasets = _count_terms(theme_papers, "datasets").most_common(5)
            benchmarks = _count_terms(theme_papers, "benchmarks").most_common(5)
            lines.extend(
                [
                    f"### {theme}",
                    "",
                    f"- papers: {len(theme_papers)}",
                    f"- recurring methods: {_format_terms(term for term, _count in methods)}",
                    f"- datasets: {_format_terms(term for term, _count in datasets)}",
                    f"- evaluation approaches: {_format_terms(term for term, _count in benchmarks)}",
                    "",
                ]
            )
    else:
        lines.append("No major themes were extracted.")

    lines.extend(["## Representative Papers", ""])
    if representative:
        for paper in representative:
            lines.append(
                f"- **{_format_paper_label(paper)}**: "
                f"{paper.abstract or 'metadata-only record'} "
                f"Methods: {_format_terms(paper.methods[:3])}. "
                f"Evaluation: {_format_terms(_dedupe_tuple(paper.benchmarks, paper.datasets)[:3])}."
            )
    else:
        lines.append("- No representative papers available.")

    lines.extend(["", "## Comparison Tables", ""])
    lines.append(_render_comparison_table(papers) if papers else "No comparison table available.")

    lines.extend(["", "## Research Gaps", ""])
    if limitation_counts:
        for limitation, count in limitation_counts.most_common(8):
            lines.append(f"- ({count} paper/source mention(s)) {limitation}")
    else:
        lines.append("- Limitation evidence is sparse; add explicit limitation notes per paper.")

    lines.extend(["", "## Future Directions", ""])
    if future_counts:
        for direction, count in future_counts.most_common(8):
            lines.append(f"- ({count} paper/source mention(s)) {direction}")
    else:
        lines.append("- Future-work evidence is sparse; add explicit future-work notes per paper.")

    lines.extend(["", "## Related Work Draft", "", related_work, "", "## References", ""])
    if papers:
        for index, paper in enumerate(papers, start=1):
            author_text = _format_terms(paper.authors, empty="Unknown authors")
            year_text = str(paper.year) if paper.year else "n.d."
            venue_text = f" {paper.venue}." if paper.venue else ""
            link_text = f" {paper.url}" if paper.url else ""
            lines.append(
                f"{index}. {author_text}. {year_text}. {paper.title}.{venue_text}{link_text}"
            )
    else:
        lines.append("No references collected.")

    lines.extend(["", "## Source Files", ""])
    for path in source_files:
        try:
            rel = path.relative_to(project_input.project_dir)
        except ValueError:
            rel = path
        lines.append(f"- {rel}")
    return "\n".join(lines).rstrip() + "\n"


def _survey_repo_root(project_dir: Path) -> Path | None:
    if project_dir.parent.name == "projects":
        return project_dir.parent.parent
    return None


def _serialize_paper_for_artifact(paper: PaperMetadata, repo_root: Path | None) -> dict[str, Any]:
    payload = asdict(paper)
    payload["source_paths"] = [
        display_path(path, repo_root) for path in payload.get("source_paths", [])
    ]
    return payload


def _project_metadata_for_artifact(
    project_input: ProjectInput,
    repo_root: Path | None,
) -> dict[str, Any]:
    metadata = project_input.as_metadata()
    metadata["project_dir"] = display_path(project_input.project_dir, repo_root)
    metadata["task_path"] = display_path(project_input.task_path, repo_root)
    return metadata


def run_literature_survey_mode(
    *,
    console: Console,
    project_input: ProjectInput,
    config: LiteratureSurveyConfig,
    output_path: Path | None = None,
) -> SurveyResult:
    console.rule("Literature Survey Mode")
    console.print(
        "[cyan]Survey constraints:[/cyan] local deterministic collection, no provider calls"
    )

    project_dir = project_input.project_dir
    repo_root = _survey_repo_root(project_dir)
    artifact_project_metadata = _project_metadata_for_artifact(project_input, repo_root)
    generated_at = datetime.now().isoformat()
    output_dir = project_dir / config.output_dir
    report_path = output_path or (output_dir / "survey_report.md")
    if not report_path.is_absolute():
        report_path = project_dir / report_path
    report_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path = report_path.with_name("paper_metadata.json")
    related_work_path = report_path.with_name("related_work.md")
    manifest_path = report_path.with_name("survey_manifest.json")

    papers, source_files = collect_papers(project_dir, config)
    metadata_quality = _metadata_quality_summary(papers)
    source_summary = _source_summary(source_files, project_dir)
    representative_groups = _representative_group_summary(papers)
    report = generate_survey_report(
        papers=papers,
        source_files=source_files,
        project_input=project_input,
        generated_at=generated_at,
    )
    related_work = generate_related_work(papers)

    write_text(report_path, report)
    write_text(related_work_path, "# Related Work Draft\n\n" + related_work)
    write_json_file(
        metadata_path,
        {
            "generated_at": generated_at,
            "project": artifact_project_metadata,
            "paper_count": len(papers),
            "metadata_quality": metadata_quality,
            "representative_groups": representative_groups,
            "papers": [_serialize_paper_for_artifact(paper, repo_root) for paper in papers],
        },
    )
    write_json_file(
        manifest_path,
        {
            "generated_at": generated_at,
            "mode": "literature_survey",
            "project": artifact_project_metadata,
            "config": asdict(config),
            "source_files": [display_path(path, repo_root) for path in source_files],
            "source_summary": source_summary,
            "paper_count": len(papers),
            "metadata_quality": metadata_quality,
            "representative_groups": representative_groups,
            "outputs": {
                "report": display_path(report_path, repo_root),
                "paper_metadata": display_path(metadata_path, repo_root),
                "related_work": display_path(related_work_path, repo_root),
            },
        },
    )

    console.print(f"[green]Scanned source files:[/green] {len(source_files)}")
    console.print(f"[green]Unique papers collected:[/green] {len(papers)}")
    console.print(f"[green]Saved survey report:[/green] {display_path(report_path, repo_root)}")
    console.print(f"[green]Saved paper metadata:[/green] {display_path(metadata_path, repo_root)}")
    console.print(
        f"[green]Saved related work draft:[/green] {display_path(related_work_path, repo_root)}"
    )
    return SurveyResult(
        papers=papers,
        source_files=list(source_files),
        report_path=report_path,
        metadata_path=metadata_path,
        related_work_path=related_work_path,
        manifest_path=manifest_path,
    )
