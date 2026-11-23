"""
Sorts a BATCH of emails into one of six categories (Elvis's rules):

    important    - job alerts from platforms he subscribed to (LinkedIn, Indeed, Teal, ...)
    needs_reply  - employers replying about applications; real people writing to him
    delivery     - when a package will arrive / has shipped (wins over any coupon inside)
    receipt      - order/payment receipts with no delivery info   -> archived
    promotion    - ads, coupons, newsletters                       -> archived
    other        - anything else worth keeping (security alerts, account notices)

Layer 1: hard rules decide the obvious ones with no AI call.
Layer 2: Gemini decides the gray zone, using the written rules in the prompt.
Anything missing or unparseable fails safe to "other" (kept in inbox).
"""

import json
from services.gemini_utils import generate

CATEGORIES = {"important", "needs_reply", "delivery", "receipt", "promotion", "other"}

# Senders that are always promotions, bypassing the AI entirely.
# Add a domain here any time you notice the AI being inconsistent about a sender.
ALWAYS_PROMOTION_DOMAINS = ["codepen.io", "nextdoor.com"]

# If a Gmail-Promotions email mentions any of these, it might be a delivery update,
# so it goes to the AI instead of being auto-archived.
DELIVERY_WORDS = [
    "shipped", "ship", "delivered", "delivery", "out for delivery",
    "arriving", "on its way", "on the way", "tracking", "package",
]

BATCH_PROMPT = """You are sorting {count} emails for Elvis into exactly one category each.

CATEGORIES (use these exact names):
- important: job alerts from job platforms he subscribed to (LinkedIn, Indeed, Teal, \
Handshake, etc.), and automated updates about his job applications \
(e.g. "application received", "not selected").
- needs_reply: an employer or recruiter writing about a job application where a response \
is expected (interview invite, scheduling, a question), OR a real person writing to him \
personally. Seeing his name ("Elvis, ...") is NOT enough - marketing emails use his name too. \
Automated/no-reply senders are never needs_reply.
- delivery: tells him when a package shipped, will arrive, or was delivered. \
If an email has delivery info AND a coupon, delivery WINS.
- receipt: order or payment confirmation with NO shipping/delivery date.
- promotion: ads, coupons, sales, newsletters, marketing.
- other: anything else worth keeping (security alerts, account or document notices, bills).

EMAILS:
{email_list}

Respond with ONLY a JSON array, one object per email, using the exact id given:
[{{"id": "...", "category": "<one of the six>", "reason": "one short sentence"}}, ...]
"""


def _is_always_promotion_sender(sender: str) -> bool:
    sender_lower = sender.lower()
    return any(domain in sender_lower for domain in ALWAYS_PROMOTION_DOMAINS)


def _is_plain_gmail_promotion(email: dict) -> bool:
    """Gmail filed it under Promotions AND it says nothing about shipping/delivery."""
    if "CATEGORY_PROMOTIONS" not in email.get("labels", []):
        return False
    text = f"{email['subject']} {email['snippet']}".lower()
    return not any(word in text for word in DELIVERY_WORDS)


def _format_emails(emails: list[dict]) -> str:
    return "\n".join(
        f'- id: {e["id"]} | Subject: {e["subject"]} | From: {e["sender"]} | Preview: {e["snippet"]}'
        for e in emails
    )


def classify_batch(emails: list[dict]) -> dict:
    """emails: list of {id, subject, sender, snippet, labels}.
    Returns {email_id: {"category": ..., "reason": ...}} for every email."""
    decisions = {}
    for_ai = []

    # Layer 1: hard rules
    for email in emails:
        if _is_always_promotion_sender(email["sender"]):
            decisions[email["id"]] = {"category": "promotion", "reason": "Sender on always-promotion list"}
        elif _is_plain_gmail_promotion(email):
            decisions[email["id"]] = {"category": "promotion", "reason": "Gmail Promotions tab, no delivery info"}
        else:
            for_ai.append(email)

    # Layer 2: AI for the gray zone
    if for_ai:
        prompt = BATCH_PROMPT.format(count=len(for_ai), email_list=_format_emails(for_ai))
        raw_text = generate(prompt).strip()
        if raw_text.startswith("```"):
            raw_text = raw_text.strip("`").removeprefix("json").strip()

        try:
            for d in json.loads(raw_text):
                if d.get("id") and d.get("category") in CATEGORIES:
                    decisions[d["id"]] = {"category": d["category"], "reason": d.get("reason", "")}
        except (json.JSONDecodeError, TypeError) as e:
            print(f"  [classifier] WARNING: could not parse Gemini's reply ({e}); "
                  f"{len(for_ai)} emails default to 'other'")

    # Fail safe: anything still undecided is kept
    for email in emails:
        decisions.setdefault(email["id"], {"category": "other", "reason": "No valid decision - kept as safe default"})

    return decisions
