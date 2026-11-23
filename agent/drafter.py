"""
drafter.py — the GHOSTWRITER.
For each "needs_reply" email: reads the full email, studies how Elvis writes
(from his Sent folder), writes a reply in his style, and saves it to Gmail
Drafts inside the original conversation.

It NEVER sends anything. This file only ever calls drafts().create().
Elvis reviews every draft in Gmail and presses Send himself.
"""

import base64
import html
import os
import re
from email.mime.text import MIMEText

from services.gemini_utils import generate

STYLE_EXAMPLE_COUNT = 8   # how many of Elvis's sent emails to learn his style from
MAX_BODY_CHARS = 4000     # keep long emails from blowing up the prompt

DRAFT_PROMPT = """You are writing an email reply AS Elvis, in his own voice.

HOW ELVIS WRITES — real emails he sent. Match his word choice, sentence length,
sentence structure, greetings, sign-offs and tone. Do NOT make it more formal or
polished than he writes.
{style_examples}

THE EMAIL TO REPLY TO:
From: {sender}
Subject: {subject}

{body}

RULES:
- Write only the reply body (no subject line, no "Here is a draft").
- Never invent facts, dates, times, numbers or commitments. Where Elvis must fill
  something in, leave a clear placeholder like [YOUR AVAILABILITY] or [CONFIRM DATE].
- Keep it about as long as Elvis's own emails usually are.
"""


# ---------- reading full emails ----------

def _decode(data: str) -> str:
    return base64.urlsafe_b64decode(data.encode()).decode("utf-8", errors="replace")


def _find_text(payload: dict) -> str:
    """Walks a (possibly nested) MIME payload; prefers plain text, falls back to HTML."""
    mime = payload.get("mimeType", "")
    data = payload.get("body", {}).get("data")
    if mime == "text/plain" and data:
        return _decode(data)
    plain, html_text = "", ""
    for part in payload.get("parts", []):
        text = _find_text(part)
        if part.get("mimeType") == "text/plain" and text:
            plain = plain or text
        elif text:
            html_text = html_text or text
    if plain:
        return plain
    if mime == "text/html" and data:
        html_text = _decode(data)
    if html_text:
        text = re.sub(r"<(script|style).*?</\1>", " ", html_text, flags=re.S | re.I)
        return html.unescape(re.sub(r"<[^>]+>", " ", text))
    return ""


def _strip_quoted(text: str) -> str:
    """Removes the quoted older conversation ('On ... wrote:' and '>' lines)."""
    text = re.split(r"\n\s*On .+wrote:", text, maxsplit=1)[0]
    lines = [l for l in text.splitlines() if not l.strip().startswith(">")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def get_full_email(service, message_id: str) -> dict:
    """Full message: body text plus the headers needed to reply in the same thread."""
    msg = service.users().messages().get(userId="me", id=message_id, format="full").execute()
    headers = {h["name"].lower(): h["value"] for h in msg["payload"].get("headers", [])}
    return {
        "id": msg["id"],
        "thread_id": msg["threadId"],
        "subject": headers.get("subject", ""),
        "sender": headers.get("from", ""),
        "reply_to": headers.get("reply-to") or headers.get("from", ""),
        "message_id_header": headers.get("message-id", ""),
        "body": _strip_quoted(_find_text(msg["payload"]))[:MAX_BODY_CHARS],
    }


# ---------- learning Elvis's style ----------

STYLE_FILE = "data/style_examples.txt"   # Elvis's own emails, separated by lines of ---


def _style_from_file() -> list[str]:
    """Reads Elvis's hand-picked emails from style_examples.txt, if it exists."""
    if not os.path.exists(STYLE_FILE):
        return []
    with open(STYLE_FILE, encoding="utf-8") as f:
        parts = re.split(r"^\s*-{3,}\s*$", f.read(), flags=re.M)
    return [p.strip() for p in parts if p.strip()]


def get_style_examples(service, count=STYLE_EXAMPLE_COUNT) -> str:
    """Emails Elvis actually wrote. Prefers style_examples.txt (instant, and covers
    emails he sent from Yahoo); falls back to his Gmail Sent folder."""
    from_file = _style_from_file()
    if from_file:
        return "\n\n".join(f"--- Example {i} ---\n{e}" for i, e in enumerate(from_file[:count], 1))

    refs = service.users().messages().list(
        userId="me", labelIds=["SENT"], maxResults=count * 3
    ).execute().get("messages", [])

    examples = []
    for ref in refs:
        body = get_full_email(service, ref["id"])["body"]
        if 20 <= len(body) <= 1500:          # skip empty and very long ones
            examples.append(body)
        if len(examples) >= count:
            break

    if not examples:
        return "(no sent emails found — write simply and naturally)"
    return "\n\n".join(f"--- Example {i} ---\n{e}" for i, e in enumerate(examples, 1))


# ---------- saving drafts ----------

def _threads_with_drafts(service) -> set:
    """Thread IDs that already have a draft, so we never draft the same email twice."""
    drafts = service.users().drafts().list(userId="me").execute().get("drafts", [])
    return {d["message"]["threadId"] for d in drafts}


def save_draft(service, original: dict, reply_body: str):
    """Saves the reply as a Gmail draft in the same conversation. Does NOT send."""
    subject = original["subject"]
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"

    mime = MIMEText(reply_body)
    mime["To"] = original["reply_to"]
    mime["Subject"] = subject
    if original["message_id_header"]:
        mime["In-Reply-To"] = original["message_id_header"]
        mime["References"] = original["message_id_header"]

    raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()
    service.users().drafts().create(
        userId="me",
        body={"message": {"raw": raw, "threadId": original["thread_id"]}},
    ).execute()


# ---------- the whole job ----------

def draft_replies(service, emails: list[dict]) -> int:
    """emails: the needs_reply emails from triage. Returns how many drafts were created."""
    if not emails:
        return 0

    already_drafted = _threads_with_drafts(service)
    style = None   # fetched once, only if there's something to draft
    created = 0

    for e in emails:
        full = get_full_email(service, e["id"])
        if full["thread_id"] in already_drafted:
            print(f"  [drafter] skip (draft exists): {full['subject']!r}")
            continue

        if style is None:
            style = get_style_examples(service)

        prompt = DRAFT_PROMPT.format(
            style_examples=style, sender=full["sender"],
            subject=full["subject"], body=full["body"] or "(empty body)",
        )
        reply = generate(prompt).strip()
        save_draft(service, full, reply)
        already_drafted.add(full["thread_id"])
        created += 1
        print(f"  [drafter] draft saved: {full['subject']!r}")

    return created
