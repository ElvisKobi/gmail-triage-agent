"""
Summarize workflow — the DAILY JOB and main entry point.

Run:
    python summarize.py

What it does:
    1. Sorts + labels emails that arrived since the last run (archives receipts/ads).
    2. Drafts replies to "needs_reply" emails (saved to Gmail Drafts, never sent).
    3. Writes the SPOKEN briefing (briefing.txt) that the voice assistant reads aloud.
    4. Writes the WRITTEN digest (digest.md) of what's left in the inbox.
    5. Records this run's start time, only if everything above succeeded.
"""

import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv()

import os
import time
from datetime import datetime

from services.gmail_client import get_gmail_service, fetch_since
from agent.summarizer import summarize_chunk, combine_summaries, write_spoken_briefing
from agent.triage import run_triage
from services.state import load_last_run, save_last_run
from agent.drafter import draft_replies

CHUNK_SIZE = 40
BRIEFING_PATH = "data/briefing.txt"
DIGEST_PATH = "data/digest.md"


def run_summary():
    os.makedirs("data", exist_ok=True)
    run_started = int(time.time())   # capture at START
    since = load_last_run()
    print(f"Reading emails since {datetime.fromtimestamp(since):%Y-%m-%d %H:%M}\n")

    print("Step 1/4: Sorting and labeling new emails...\n")
    triage = run_triage(since)

    service = get_gmail_service()

    print("\nStep 2/4: Drafting replies (saved to Gmail Drafts, never sent)...\n")
    drafted = draft_replies(service, triage["needs_reply"])
    print(f"  {drafted} draft(s) created.")

    print("\nStep 3/4: Writing the spoken briefing...\n")
    briefing = write_spoken_briefing(triage["emails"], drafted, triage["counts"])
    with open(BRIEFING_PATH, "w", encoding="utf-8") as f:
        f.write(briefing)
    print(briefing)

    print("\nStep 4/4: Writing the written digest...\n")
    chunk_summaries = []
    total_emails = 0
    for batch in fetch_since(service, since, page_size=100):
        for i in range(0, len(batch), CHUNK_SIZE):
            chunk = batch[i:i + CHUNK_SIZE]
            total_emails += len(chunk)
            chunk_summaries.append(summarize_chunk(chunk))

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    if chunk_summaries:
        body = f"({total_emails} new emails summarized)\n\n{combine_summaries(chunk_summaries)}"
    else:
        body = "No new emails since the last run."
    with open(DIGEST_PATH, "w", encoding="utf-8") as f:
        f.write(f"# Email Digest — {timestamp}\n\n{body}\n")

    save_last_run(run_started)       # save at END, only if we got here
    print(f"\nSaved {BRIEFING_PATH} and {DIGEST_PATH}.")


if __name__ == "__main__":
    run_summary()
