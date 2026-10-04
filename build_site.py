"""Build the public JSON catalog from daily paper files.

The importer accepts the historical Markdown files produced by the original
desktop script and the JSON files produced by the Actions-friendly script.
Only paper metadata is written to ``data/catalog.json``; OAuth files and raw
email messages are never copied into the public site.
"""

from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qs, unquote, urlencode, urlsplit, urlunsplit

from bs4 import BeautifulSoup, NavigableString


DATE_FILE_RE = re.compile(r"^(?P<date>\d{8}).*google_scholar.*\.(?:md|json)$", re.I)
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
SECRET_RE = re.compile(
    r"\b(?:ya29\.[A-Za-z0-9._-]+|AIza[A-Za-z0-9_-]+)\b", re.I
)


def redact(value: str) -> str:
    """Remove accidental private tokens from legacy snippets."""

    value = EMAIL_RE.sub("[redacted]", value)
    return SECRET_RE.sub("[redacted]", value)


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    value = re.sub(r"\s+", " ", str(value)).strip()
    return redact(value)


def public_url(value: str) -> str:
    """Turn a Google Scholar tracking URL into a stable paper URL."""

    value = html.unescape(clean_text(value))
    try:
        parsed = urlsplit(value)
        query = parse_qs(parsed.query)
        target = query.get("url", [""])[0]
        if target:
            value = unquote(target)
            parsed = urlsplit(value)
        if parsed.scheme.lower() not in {"http", "https"}:
            return ""
        # Tracking parameters are not needed to open the paper and can expose
        # an account-specific Scholar history identifier.
        safe_query = [
            (key, item)
            for key, values in parse_qs(parsed.query, keep_blank_values=True).items()
            if key.lower() not in {"d", "ei", "scisig", "hist", "sa", "hl", "oi", "folt", "html", "pos"}
            for item in values
        ]
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(safe_query), ""))
    except ValueError:
        return value


def parse_count(text: str, label: str) -> int:
    match = re.search(rf"{re.escape(label)}\s*:\s*(\d+)", text, re.I)
    return int(match.group(1)) if match else 0


def parse_legacy_markdown(path: Path, date: str) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(text, "html.parser")
    titles = list(soup.select("a.gse_alrt_title"))
    papers: list[dict[str, str]] = []
    for index, title_node in enumerate(titles):
        author_node = title_node.find_next("font")
        if author_node is None:
            author = ""
        else:
            author = clean_text(author_node.get_text(" ", strip=True))

        abstract_parts: list[str] = []
        started = False
        next_title = titles[index + 1] if index + 1 < len(titles) else None
        for sibling in title_node.next_siblings:
            if sibling is author_node:
                started = True
                continue
            if sibling is next_title:
                break
            if started and isinstance(sibling, NavigableString):
                part = clean_text(sibling)
                if part:
                    abstract_parts.append(part)
        papers.append(
            {
                "title": clean_text(title_node.get_text(" ", strip=True)),
                "authors": author,
                "abstract": clean_text(" ".join(abstract_parts)),
                "url": public_url(title_node.get("href", "")),
            }
        )

    return {
        "id": path.stem,
        "date": date,
        "source": "historical-import",
        "messages": parse_count(text, "Unread messages"),
        "papers": deduplicate_papers(papers),
    }


def load_json(path: Path, date: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    papers = []
    for paper in payload.get("papers", []):
        papers.append(
            {
                "title": clean_text(paper.get("title")),
                "authors": clean_text(paper.get("authors")),
                "abstract": clean_text(paper.get("abstract")),
                "url": public_url(paper.get("url", "")),
            }
        )
    return {
        "id": path.stem,
        "date": date,
        "source": payload.get("source", "gmail"),
        "messages": int(payload.get("messages", 0) or 0),
        "papers": deduplicate_papers(papers),
    }


def deduplicate_papers(papers: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for paper in papers:
        title = clean_text(paper.get("title", ""))
        if not title:
            continue
        key = title.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(
            {
                "title": title,
                "authors": clean_text(paper.get("authors", "")),
                "abstract": clean_text(paper.get("abstract", "")),
                "url": public_url(paper.get("url", "")),
            }
        )
    return result


def discover(input_dir: Path) -> list[dict[str, Any]]:
    records = []
    input_dir.mkdir(parents=True, exist_ok=True)
    for path in sorted(input_dir.iterdir()):
        if not path.is_file():
            continue
        match = DATE_FILE_RE.match(path.name)
        if not match:
            continue
        date = match.group("date")
        if path.suffix.lower() == ".json":
            record = load_json(path, date)
        else:
            record = parse_legacy_markdown(path, date)
        # Keep the filename as a stable public identifier while avoiding raw
        # file contents in the site.
        record["id"] = path.stem
        record["filename"] = path.name
        records.append(record)
    records.sort(key=lambda item: (item["date"], item["id"]), reverse=True)
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the public paper catalog")
    parser.add_argument("--input-dir", type=Path, default=Path("data/days"))
    parser.add_argument("--output", type=Path, default=Path("data/catalog.json"))
    parser.add_argument(
        "--legacy-dir",
        type=Path,
        help="Optional local folder containing historical Markdown files",
    )
    args = parser.parse_args()

    args.input_dir.mkdir(parents=True, exist_ok=True)
    if args.legacy_dir:
        for source in sorted(args.legacy_dir.glob("*.md")):
            if DATE_FILE_RE.match(source.name):
                target = args.input_dir / f"{source.stem}.json"
                target.write_text(
                    json.dumps(parse_legacy_markdown(source, DATE_FILE_RE.match(source.name).group("date")), ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

    records = discover(args.input_dir)
    catalog = {
        "record_count": len(records),
        "paper_count": sum(len(record["papers"]) for record in records),
        "days": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Built catalog: {len(records)} daily files, {catalog['paper_count']} papers")


if __name__ == "__main__":
    main()
