"""Fetch unread Google Scholar Alert mail and save public paper metadata."""

from __future__ import annotations

import argparse
import base64
import json
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qs, unquote, urlencode, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]
GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"
SCHOLAR_SENDER = "scholaralerts-noreply@google.com"
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
TOKEN_RE = re.compile(r"\b(?:ya29\.[A-Za-z0-9._-]+|AIza[A-Za-z0-9_-]+)\b", re.I)


def clean_text(value: Any) -> str:
    value = re.sub(r"\s+", " ", str(value or "")).strip()
    value = EMAIL_RE.sub("[redacted]", value)
    return TOKEN_RE.sub("[redacted]", value)


def public_url(value: str) -> str:
    """Remove Scholar tracking parameters before a URL reaches the site."""

    value = clean_text(value)
    try:
        parsed = urlsplit(value)
        query = parse_qs(parsed.query)
        target = query.get("url", [""])[0]
        if target:
            parsed = urlsplit(unquote(target))
        if parsed.scheme.lower() not in {"http", "https"}:
            return ""
        blocked = {"d", "ei", "scisig", "hist", "sa", "hl", "oi", "folt", "html", "pos"}
        safe_query = [
            (key, item)
            for key, values in parse_qs(parsed.query, keep_blank_values=True).items()
            if key.lower() not in blocked
            for item in values
        ]
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(safe_query), ""))
    except ValueError:
        return value


def credentials_from_files(credentials_file: Path, token_file: Path) -> Credentials:
    creds: Credentials | None = None
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        if not credentials_file.exists():
            raise RuntimeError(f"Missing OAuth client file: {credentials_file}")
        # This branch is intended for the initial local authorization only.
        flow = InstalledAppFlow.from_client_secrets_file(str(credentials_file), SCOPES)
        creds = flow.run_local_server(port=0)
    token_file.write_text(creds.to_json(), encoding="utf-8")
    return creds


def api_get(session: requests.Session, token: str, endpoint: str, **params: Any) -> dict[str, Any]:
    response = session.get(
        f"{GMAIL_API}/{endpoint}",
        headers={"Authorization": f"Bearer {token}"},
        params=params,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def list_unread_messages(session: requests.Session, token: str, limit: int | None, query: str) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    page_token: str | None = None
    while True:
        params: dict[str, Any] = {
            "maxResults": min(100, limit - len(messages)) if limit else 100,
            "labelIds": "INBOX",
            "q": query,
        }
        if page_token:
            params["pageToken"] = page_token
        payload = api_get(session, token, "messages", **params)
        messages.extend(payload.get("messages", []))
        if limit and len(messages) >= limit:
            return messages[:limit]
        page_token = payload.get("nextPageToken")
        if not page_token:
            return messages


def decode_body(part: dict[str, Any]) -> str:
    body = part.get("body", {})
    data = body.get("data")
    if data:
        padding = "=" * (-len(data) % 4)
        return base64.urlsafe_b64decode((data + padding).encode("ascii")).decode("utf-8", errors="replace")
    for child in part.get("parts", []) or []:
        if child.get("mimeType") == "text/html":
            decoded = decode_body(child)
            if decoded:
                return decoded
    for child in part.get("parts", []) or []:
        decoded = decode_body(child)
        if decoded:
            return decoded
    return ""


def extract_papers(message: dict[str, Any]) -> list[dict[str, str]]:
    sender = ""
    for header in message.get("payload", {}).get("headers", []):
        if header.get("name", "").lower() == "from":
            sender = header.get("value", "")
            break
    if SCHOLAR_SENDER not in sender.lower() and "google scholar" not in sender.lower() and "google 学术" not in sender:
        return []

    soup = BeautifulSoup(decode_body(message.get("payload", {})), "html.parser")
    titles = soup.select("a.gse_alrt_title")
    if not titles:
        titles = soup.find_all("a", href=lambda href: href and "scholar.google" in href)
    papers: list[dict[str, str]] = []
    for title in titles:
        author = title.find_next("font")
        abstract = title.find_next(class_=lambda classes: classes and any("snippet" in c or "abstract" in c for c in classes) if isinstance(classes, list) else False)
        if abstract is None:
            sibling_text = []
            for sibling in title.next_siblings:
                if getattr(sibling, "name", None) == "a":
                    break
                if getattr(sibling, "name", None) == "font":
                    continue
                text = getattr(sibling, "strip", lambda: str(sibling))()
                if text:
                    sibling_text.append(text)
            abstract_text = " ".join(sibling_text)
        else:
            abstract_text = abstract.get_text(" ", strip=True)
        papers.append(
            {
                "title": clean_text(title.get_text(" ", strip=True)),
                "authors": clean_text(author.get_text(" ", strip=True) if author else ""),
                "abstract": clean_text(abstract_text),
                "url": public_url(title.get("href", "")),
            }
        )
    return deduplicate(papers)


def deduplicate(papers: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for paper in papers:
        title = clean_text(paper.get("title", ""))
        if not title or title.casefold() in seen:
            continue
        seen.add(title.casefold())
        result.append(
            {
                "title": title,
                "authors": clean_text(paper.get("authors", "")),
                "abstract": clean_text(paper.get("abstract", "")),
                "url": public_url(paper.get("url", "")),
            }
        )
    return result


def merge_daily_record(output: Path, payload: dict[str, Any]) -> dict[str, Any]:
    """Append today's new papers without replacing an earlier same-day run."""

    if not output.exists():
        return payload
    try:
        previous = json.loads(output.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return payload
    previous_papers = previous.get("papers", [])
    payload["papers"] = deduplicate([*previous_papers, *payload.get("papers", [])])
    payload["messages"] = int(previous.get("messages", 0) or 0) + int(payload.get("messages", 0) or 0)
    return payload


def received_date(message: dict[str, Any]) -> str:
    """Return the Gmail message date in the runner's configured local timezone."""

    timestamp = int(message.get("internalDate", "0") or 0)
    if timestamp <= 0:
        return datetime.now().strftime("%Y%m%d")
    return datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc).astimezone().strftime("%Y%m%d")


def mark_read(session: requests.Session, token: str, message_id: str) -> None:
    response = session.post(
        f"{GMAIL_API}/messages/{message_id}/modify",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"removeLabelIds": ["UNREAD"]},
        timeout=30,
    )
    response.raise_for_status()


def make_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=4,
        backoff_factor=1,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "POST"}),
        respect_retry_after_header=True,
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def process(args: argparse.Namespace) -> int:
    credentials_file = Path(args.credentials_file)
    token_file = Path(args.token_file)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    creds = credentials_from_files(credentials_file, token_file)
    session = make_session()
    if args.acknowledge_file:
        pending = json.loads(Path(args.acknowledge_file).read_text(encoding="utf-8"))
        for message_id in pending:
            mark_read(session, creds.token, message_id)
        print(f"Marked {len(pending)} durably saved messages as read.")
        return 0
    query = args.query or f"is:unread from:{SCHOLAR_SENDER}"
    if args.recover_date:
        start = datetime.strptime(args.recover_date, "%Y-%m-%d").replace(tzinfo=timezone(timedelta(hours=8)))
        end = start + timedelta(days=1)
        query = f"from:{SCHOLAR_SENDER} after:{int(start.timestamp())} before:{int(end.timestamp())}"
    messages = list_unread_messages(session, creds.token, args.max_messages, query)
    records: dict[str, dict[str, Any]] = {}
    message_ids = []
    unparsed = 0
    for message in messages:
        detail = api_get(session, creds.token, f"messages/{message['id']}", format="full")
        extracted = extract_papers(detail)
        if extracted:
            message_ids.append(message["id"])
            date = received_date(detail)
            record = records.setdefault(
                date,
                {"date": date, "source": "gmail", "messages": 0, "papers": []},
            )
            record["messages"] += 1
            record["papers"].extend(extracted)
        else:
            unparsed += 1
    if unparsed:
        raise RuntimeError(f"{unparsed} messages could not be parsed; no mail marked read. Inspect the parser before retrying.")
    for record in records.values():
        record["papers"] = deduplicate(record["papers"])
    if args.pending_file:
        Path(args.pending_file).write_text(json.dumps(message_ids), encoding="utf-8")
    if not records:
        print(f"No new Scholar papers found in {len(messages)} messages.")
        return 0

    saved_dates: list[str] = []
    saved_papers = 0
    for date, payload in sorted(records.items()):
        if not payload["papers"]:
            continue
        output = output_dir / f"{date}_google_scholar_.json"
        payload = merge_daily_record(output, payload)
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        saved_dates.append(date)
        saved_papers += len(payload["papers"])
    # Actions acknowledges only after git push; the manifest stays in RUNNER_TEMP.
    if not args.pending_file:
        for message_id in message_ids:
            mark_read(session, creds.token, message_id)
    print(f"Saved {saved_papers} unique papers across {len(saved_dates)} received dates: {', '.join(saved_dates)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch Google Scholar Alert mail")
    parser.add_argument("--credentials-file", default="credentials.json")
    parser.add_argument("--token-file", default="token.json")
    parser.add_argument("--output-dir", default="data/days")
    parser.add_argument("--max-messages", type=int)
    parser.add_argument("--pending-file", help="Private temporary IDs manifest; defer marking read")
    parser.add_argument("--acknowledge-file", help="Mark previously saved messages read after push")
    parser.add_argument("--recover-date", help="Recover read and unread mail for YYYY-MM-DD in Beijing time")
    parser.add_argument("--query", help="Gmail search query; defaults to unread Scholar alerts")
    return process(parser.parse_args())


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except requests.HTTPError as exc:
        print(f"Gmail API request failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
    except Exception as exc:
        print(f"Fatal error: {exc}", file=sys.stderr)
        raise SystemExit(1)
