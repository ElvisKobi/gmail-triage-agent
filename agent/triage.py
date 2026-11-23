"""
Gmail triage agent — triage step.

Run manually:
    python -m agent.triage    (triages emails since the last saved run; run from the project folder)

Normally called from summarize.py as run_triage(since), which passes the
start of the time window so triage and summary look at the same emails.

Every email gets an Agent/<Category> label. Receipts and promotions are also marked read
and archived; everything else stays in the inbox. Nothing is ever deleted.
"""

import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv()

from services.gmail_client import get_gmail_service, get_or_create_label, fetch_since, label_mark_read_and_archive, add_label
from agent.classifier import classify_batch
from services.state import load_last_run

BATCH_SIZE = 15  # emails classified per Gemini call

# Every category gets a label. Only ARCHIVE_CATEGORIES leave the inbox.
CATEGORY_LABELS = {
    "important": "Agent/Important",
    "needs_reply": "Agent/Needs Reply",
    "delivery": "Agent/Delivery",
    "other": "Agent/Other",
    "receipt": "Agent/Receipt",
    "promotion": "Agent/Promotion",
}
ARCHIVE_CATEGORIES = {"receipt", "promotion"}      # labeled, marked read, archived
# Everything else is labeled, marked read, and stays in the inbox.
# The Agent/* labels (and the briefing) replace "unread" as the to-do signal.
# To keep a category unread, add it here, e.g. {"needs_reply"}.
STAY_UNREAD_CATEGORIES = set()


def run_triage(since: int | None = None):
    """Classifies inbox emails that arrived after `since` (Unix seconds).
    Archives receipts and promotions; keeps everything else in the inbox.
    If `since` is None, uses the last saved run time from state.json."""
    if since is None:
        since = load_last_run()

    service = get_gmail_service()
    label_ids = {cat: get_or_create_label(service, name) for cat, name in CATEGORY_LABELS.items()}

    total_reviewed = 0
    total_archived = 0
    counts = {}
    needs_reply = []   # handed to drafter.py by summarize.py
    processed = []     # every email + its category, handed to the spoken briefing

    for page in fetch_since(service, since, page_size=100):
        for i in range(0, len(page), BATCH_SIZE):
            batch = page[i:i + BATCH_SIZE]
            decisions = classify_batch(batch)

            for email in batch:
                total_reviewed += 1
                decision = decisions[email["id"]]
                category = decision["category"]
                counts[category] = counts.get(category, 0) + 1

                print(f"[{category.upper()}] {email['subject']!r} from {email['sender']} — {decision['reason']}")
                processed.append({**email, "category": category})
                if category == "needs_reply":
                    needs_reply.append(email)

                if category in ARCHIVE_CATEGORIES:
                    label_mark_read_and_archive(service, email["id"], label_ids[category])
                    total_archived += 1
                else:
                    add_label(service, email["id"], label_ids[category],
                              mark_read=category not in STAY_UNREAD_CATEGORIES)

            print(f"  ...progress: {total_reviewed} reviewed, {total_archived} archived so far\n")

    print(f"Done. Reviewed {total_reviewed}, archived {total_archived}. By category: {counts}")
    return {"reviewed": total_reviewed, "archived": total_archived,
            "counts": counts, "needs_reply": needs_reply, "emails": processed}


if __name__ == "__main__":
    run_triage()
