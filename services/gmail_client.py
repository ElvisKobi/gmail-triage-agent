"""
Gmail API client: handles OAuth login and the Gmail actions the agent needs
(fetch new emails since the last run, apply a label, mark as read, archive).
"""

import os
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
TOKEN_PATH = "token.json"
CREDENTIALS_PATH = "credentials.json"
LABEL_NAME = "Screened/Spam-Ads"  # shows as nested label "Screened > Spam-Ads" in Gmail


def get_gmail_service():
    """Handles the OAuth flow. First run opens a browser to log in;
    after that, a cached token.json is reused until it expires."""
    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_PATH):
                raise FileNotFoundError(
                    f"Missing {CREDENTIALS_PATH}. See README.md for how to get this "
                    "from Google Cloud Console."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_PATH, "w") as token_file:
            token_file.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def get_or_create_label(service, label_name=LABEL_NAME):
    """Returns the label ID, creating the label if it doesn't exist yet."""
    labels = service.users().labels().list(userId="me").execute().get("labels", [])
    for label in labels:
        if label["name"] == label_name:
            return label["id"]

    new_label = service.users().labels().create(
        userId="me",
        body={
            "name": label_name,
            "labelListVisibility": "labelShow",
            "messageListVisibility": "show",
        },
    ).execute()
    return new_label["id"]


def _get_email(service, message_id) -> dict:
    """Fetches one message's metadata and returns
    {id, subject, sender, snippet, labels}. Shared by every fetch function.
    `labels` lets rules check things like CATEGORY_PROMOTIONS without asking the AI."""
    msg = service.users().messages().get(
        userId="me", id=message_id, format="metadata",
        metadataHeaders=["Subject", "From"],
    ).execute()
    headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
    return {
        "id": msg["id"],
        "subject": headers.get("Subject", "(no subject)"),
        "sender": headers.get("From", "(unknown sender)"),
        "snippet": msg.get("snippet", ""),
        "labels": msg.get("labelIds", []),
    }


def _paged_fetch(service, page_size=100, **list_kwargs):
    """Generator: pages through messages().list() and yields batches of parsed emails."""
    page_token = None
    while True:
        results = service.users().messages().list(
            userId="me", maxResults=page_size, pageToken=page_token, **list_kwargs
        ).execute()
        message_refs = results.get("messages", [])
        if not message_refs:
            break

        yield [_get_email(service, ref["id"]) for ref in message_refs]

        page_token = results.get("nextPageToken")
        if not page_token:
            break


def fetch_since(service, after_timestamp: int, page_size=100):
    """Yields batches of ALL inbox emails (read or unread) that arrived after
    `after_timestamp` (Unix seconds). This is what the daily run uses."""
    query = f"in:inbox after:{after_timestamp}"
    yield from _paged_fetch(service, page_size, q=query)


def fetch_all_unread(service, page_size=100):
    """Yields batches of ALL unread inbox emails (the whole backlog).
    Kept for one-off cleanups; the daily run uses fetch_since() instead."""
    yield from _paged_fetch(service, page_size, labelIds=["INBOX", "UNREAD"])


def fetch_labeled(service, label_name: str, newer_than_days: int | None = None) -> list[dict]:
    """Returns inbox emails that carry `label_name` (e.g. "Agent/Needs Reply"),
    optionally only those from the last N days. Used by the voice assistant."""
    label_id = get_or_create_label(service, label_name)
    query = f"newer_than:{newer_than_days}d" if newer_than_days else None
    emails = []
    for batch in _paged_fetch(service, labelIds=["INBOX", label_id], q=query):
        emails.extend(batch)
    return emails


def add_label(service, message_id, label_id, mark_read=False):
    """Tags a message with a label and leaves it in the inbox.
    If mark_read=True, also marks it read."""
    body = {"addLabelIds": [label_id]}
    if mark_read:
        body["removeLabelIds"] = ["UNREAD"]
    service.users().messages().modify(userId="me", id=message_id, body=body).execute()


def label_mark_read_and_archive(service, message_id, label_id):
    """Applies the label, marks the message as read, and archives it (removes from INBOX)."""
    service.users().messages().modify(
        userId="me",
        id=message_id,
        body={
            "addLabelIds": [label_id],
            "removeLabelIds": ["UNREAD", "INBOX"],
        },
    ).execute()
