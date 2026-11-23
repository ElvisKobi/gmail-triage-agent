"""
assistant.py — the voice ENTRY POINT and the brain of the conversation.
Loop: you tap any key and speak -> listener turns it into text -> this file
works out which command you meant -> asks Gmail / reads the briefing -> speaker answers.

Run:
    python assistant.py

Commands it understands (keyword matching, no AI needed):
    "brief me"                       -> reads the latest briefing.txt
    "anything to reply to?"          -> emails labeled Agent/Needs Reply, still in inbox
    "any important emails today?"    -> emails labeled Agent/Important from the last day
    "goodbye" / "stop"               -> exits
"""

import msvcrt   # Windows built-in: single keypress, no Enter needed
import os
import re
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from agent.summarizer import USER_NAME

from dotenv import load_dotenv
load_dotenv()

from voice.speaker import say
from voice.listener import listen
from services.gmail_client import get_gmail_service, fetch_labeled

BRIEFING_PATH = "data/briefing.txt"   # written for the ears by summarize.py


# ---------- understanding what you said ----------

def detect_command(text: str) -> str:
    t = text.lower()
    if any(w in t for w in ["goodbye", "stop", "quit", "exit"]):
        return "quit"
    if any(w in t for w in ["reply", "respond", "answer"]):
        return "needs_reply"
    if "important" in t:
        return "important"
    if any(w in t for w in ["brief", "summary", "summarize", "digest"]):
        return "brief"
    return "unknown"


# ---------- doing the work ----------

def _sender_name(sender: str) -> str:
    """'Uber <noreply@uber.com>' -> 'Uber'"""
    name = re.sub(r"<.*?>", "", sender).replace('"', "").strip()
    return name or sender


def _speak_email_list(emails: list[dict], what: str):
    if not emails:
        say(f"You have no {what}.")
        return
    count = len(emails)
    say(f"You have {count} {what}{'s' if count > 1 else ''}.")
    for i, e in enumerate(emails[:5], start=1):
        say(f"{i}. From {_sender_name(e['sender'])}: {e['subject']}.")
    if count > 5:
        say(f"And {count - 5} more. Check Gmail for the rest.")


def handle_brief():
    if not os.path.exists(BRIEFING_PATH):
        say("I don't have a briefing yet. Run summarize first.")
        return
    with open(BRIEFING_PATH, encoding="utf-8") as f:
        say(f.read())


def handle_needs_reply(service):
    emails = fetch_labeled(service, "Agent/Needs Reply")
    _speak_email_list(emails, "email to reply to")


def handle_important(service):
    emails = fetch_labeled(service, "Agent/Important", newer_than_days=1)
    _speak_email_list(emails, "important email from today")


# ---------- the conversation loop ----------

def main():
    service = get_gmail_service()
    say(f"Hi {USER_NAME} . Tap any key and talk to me.")

    while True:
        print("\nTap any key to talk (q to quit)...")
        key = msvcrt.getwch().lower()
        if key == "q":
            break

        heard = listen()
        print(f"You: {heard or '(nothing heard)'}")
        if not heard:
            say("I didn't catch that. Try again.")
            continue

        command = detect_command(heard)
        if command == "quit":
            break
        elif command == "brief":
            handle_brief()
        elif command == "needs_reply":
            handle_needs_reply(service)
        elif command == "important":
            handle_important(service)
        else:
            say("I can brief you, tell you what needs a reply, or what's important today.")

    say("Goodbye, Boss")


if __name__ == "__main__":
    main()
