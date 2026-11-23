"""
summarizer.py — the BRIEFING WRITER.

Two outputs:
  1. A written digest (digest.md) — for reading.  [summarize_chunk / combine_summaries]
  2. A spoken briefing (briefing.txt) — for the voice assistant to say out loud,
     written like a person talking, in Elvis's category order.  [write_spoken_briefing]

Calls go through gemini_utils.generate(), which paces requests and retries on errors.
"""

from datetime import datetime
from services.gemini_utils import generate

# ---------- written digest ----------

CHUNK_PROMPT = """Below is a list of {count} emails (subject, sender, preview). \
Summarize them as a short digest: group similar emails together (by sender or topic), \
call out anything that looks time-sensitive or like it needs a personal reply, and skip \
routine noise briefly. Keep it concise — bullet points, not a paragraph per email.

{email_list}
"""

COMBINE_PROMPT = """Below are {count} partial digests, each summarizing a chunk of a \
person's unread email backlog. Combine them into ONE final digest: merge duplicate \
categories across chunks, keep an overall count per category, and put anything \
time-sensitive or needing a personal reply in its own section at the top.

{partial_digests}
"""

USER_NAME = "Boss"
def _format_emails(emails: list[dict]) -> str:
    return "\n".join(
        f"- Subject: {e['subject']} | From: {e['sender']} | Preview: {e['snippet']}"
        for e in emails
    )


def summarize_chunk(emails: list[dict]) -> str:
    """Summarizes one chunk (e.g. 40 emails) into a short digest."""
    prompt = CHUNK_PROMPT.format(count=len(emails), email_list=_format_emails(emails))
    return generate(prompt)


def combine_summaries(chunk_summaries: list[str]) -> str:
    """Combines multiple chunk digests into one final digest."""
    if len(chunk_summaries) == 1:
        return chunk_summaries[0]
    joined = "\n\n---\n\n".join(
        f"Chunk {i+1}:\n{summary}" for i, summary in enumerate(chunk_summaries)
    )
    prompt = COMBINE_PROMPT.format(count=len(chunk_summaries), partial_digests=joined)
    return generate(prompt)


# ---------- spoken briefing ----------

SPOKEN_ORDER = ["needs_reply", "important", "delivery", "other"]
user_name = USER_NAME
SPOKEN_PROMPT = """You are Elvis's personal assistant, telling him about his new email \
out loud. It is {time_of_day}. Write what you will SAY to him.

STYLE:
- Talk like a friendly person, not a document. Plain sentences only: no headings,
  bullets, symbols, markdown, or email addresses.
- Start with exactly this greeting: "Good {time_of_day}, {user_name}."
- Cover things in this order and skip any group that is empty:
  1. Emails that need a reply. Say what each one wants. {draft_note}
  2. Important emails (job alerts: give the count and the platform, not every job).
  3. Deliveries: say what is arriving and WHEN, if a date appears in the preview.
  4. Anything else worth knowing, briefly.
- End with one short line about what was cleared away: {archived_note}
- Keep it under 120 words. Never invent details that aren't in the emails.

EMAILS, already sorted by category:
{grouped}
"""


def _time_of_day() -> str:
    hour = datetime.now().hour
    return "morning" if hour < 12 else "afternoon" if hour < 17 else "evening"


def write_spoken_briefing(emails: list[dict], drafted: int, counts: dict) -> str:
    """emails: triage results, each {subject, sender, snippet, category}.
    Returns a short, conversational briefing meant to be read aloud."""
    kept = [e for e in emails if e["category"] in SPOKEN_ORDER]
    if not kept:
        return f"Good {_time_of_day()}, {USER_NAME}. Nothing new worth your attention since the last check."

    groups = []
    for cat in SPOKEN_ORDER:
        items = [e for e in kept if e["category"] == cat]
        if items:
            groups.append(f"[{cat}]\n" + _format_emails(items))

    receipts, promos = counts.get("receipt", 0), counts.get("promotion", 0)
    archived_note = (
        f"{receipts} receipt(s) and {promos} promotion(s) were archived."
        if receipts or promos else "nothing needed clearing."
    )
    draft_note = (
        f"Mention that {drafted} reply draft(s) are waiting in Gmail for him to review."
        if drafted else ""
    )

    prompt = SPOKEN_PROMPT.format(
        time_of_day=_time_of_day(), grouped="\n\n".join(groups),
        draft_note=draft_note, archived_note=archived_note,
    )
    return generate(prompt).strip()