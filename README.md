# Gmail Triage Agent

A personal email agent that runs every day at 5 PM. It sorts new Gmail into
categories, archives the noise, drafts replies in my own writing style, and
gives me a spoken briefing I can talk to — with speech recognition and the
voice running fully offline on my laptop.

## What it does

- **Reads only new mail** since the last successful run (never re-processes old mail).
- **Sorts every email** into one of six categories — *Needs Reply, Important,
  Delivery, Other, Receipt, Promotion* — using a hybrid of hard rules and an LLM.
- **Labels everything** (`Agent/...`), marks it read, and archives receipts and
  promotions. Nothing is ever deleted.
- **Drafts replies** to emails that need one, in my style, saved to Gmail Drafts
  inside the original thread. **It never sends** — I review and send myself.
- **Briefs me out loud**: a short, conversational summary I can ask for by voice.

## Design decisions

- **Hard rules first, LLM for the gray zone.** Known senders and Gmail Promotions
  without delivery info are decided by code, with no API call. Only ambiguous
  emails go to Gemini, with my category definitions written into the prompt.
  This fixed inconsistent verdicts (the same shipping email labeled "keep" one
  run and "ad" the next) and cut API usage.
- **At-least-once processing.** The run's *start* time is saved only after the
  whole run succeeds. An email arriving mid-run may be seen twice, but never zero times.
- **Human in the loop for sending.** The drafter only ever creates drafts, and it
  leaves placeholders like `[YOUR AVAILABILITY]` instead of inventing facts.
- **Code decides *what* to say, the LLM decides *how*.** The briefing's content,
  order and counts come from triage data; Gemini only turns them into natural speech.
- **Privacy for voice.** Speech-to-text (Whisper) and text-to-speech (Piper) run
  locally; my voice never leaves the laptop.
- **Model fallback for outages.** Gemini calls go through an ordered list of models.
  If one is overloaded (HTTP 503) after retries, the agent switches to the next and
  skips the failed model for the rest of the run. During a multi-hour outage that hit
  every full Flash model, the agent kept working on Flash-Lite, and because state is
  only saved after a successful run, no emails were lost while it was down.
- **Only call the LLM when there's work.** Quiet days (nothing new, or only emails the
  hard rules can decide) make zero API calls.

## How the files fit together

```
gmail_triage_agent/
├── summarize.py        entry point: the daily job
├── assistant.py        entry point: voice
├── run_daily.bat       launcher for Task Scheduler
├── agent/              the brain: triage.py, classifier.py, drafter.py, summarizer.py
├── services/           connections: gmail_client.py, gemini_utils.py, state.py
├── voice/              ears and mouth: listener.py, speaker.py
├── tools/              one-off helpers: list_models.py, check_models.py
├── data/               files the agent creates (not committed)
├── logs/               run logs (not committed)
└── voices/             downloaded Piper voice (not committed)
```

Flow of the daily job:
`run_daily.bat → summarize.py → services/state.py → agent/triage.py (+ classifier, gmail_client, gemini_utils) → agent/drafter.py → agent/summarizer.py → data/briefing.txt + data/digest.md`

Flow of the voice assistant:
`assistant.py → voice/listener.py → command → services/gmail_client.py or data/briefing.txt → voice/speaker.py`

| File | Role |
|---|---|
| `summarize.py` | **Daily job / entry point.** Runs sort → draft → briefing → digest, then saves the run time. |
| `agent/triage.py` | **Triage.** Gets a category for each new email, applies labels, marks read, archives. |
| `agent/classifier.py` | **Decision-maker.** Category definitions, hard rules, and the classification prompt. |
| `agent/drafter.py` | **Ghostwriter.** Reads the full email, learns my style, saves a threaded draft. Never sends. |
| `agent/summarizer.py` | **Briefing writer.** Spoken briefing (`data/briefing.txt`) and written digest (`data/digest.md`). |
| `services/gmail_client.py` | **Gmail connection.** Login, fetching, labels, archiving. Makes no decisions. |
| `services/gemini_utils.py` | **Gemini connection.** Sends prompts; handles pacing, retries, and the ordered model fallback list (`MODELS`). |
| `services/state.py` | **Memory of time.** Saves/loads when the last successful run started. |
| `assistant.py` | **Voice entry point.** Tap-to-talk loop: listen → understand → act → speak. |
| `voice/listener.py` | **Ears.** Records the mic and transcribes locally with Whisper. |
| `voice/speaker.py` | **Mouth.** Offline neural voice (Piper), with the Windows voice as fallback. |
| `tools/list_models.py` | **Diagnostic (manual).** Lists which Gemini models the API key can see. |
| `tools/check_models.py` | **Diagnostic (manual).** Sends a tiny test to each model and reports OK / 503 / 404 / 429, to decide the order of `MODELS` during an outage. |
| `run_daily.bat` | **Launcher** for Windows Task Scheduler; writes output to `logs/agent.log`. |

## Setup

1. `python -m venv .venv` then `.venv\Scripts\python.exe -m pip install -r requirements.txt`
2. Create a Google Cloud project, enable the Gmail API, download the OAuth client as
   `credentials.json` into this folder.
3. Create `.env` with `GEMINI_API_KEY=...`
4. (Optional) Download the voice:
   `.venv\Scripts\python.exe -m piper.download_voices en_US-lessac-medium --data-dir voices`
5. (Optional) Put 5–8 of your own emails in `data/style_examples.txt`, separated by `---` lines.
6. Run once: `.venv\Scripts\python.exe summarize.py` (opens a browser to log in the first time).
7. Talk to it: `.venv\Scripts\python.exe assistant.py` — tap any key, speak, tap again.
8. Schedule `run_daily.bat` daily in Windows Task Scheduler.

If runs start failing with 503 errors, run `.venv\Scripts\python.exe tools\check_models.py`
and put the models marked OK first in `MODELS` in `services/gemini_utils.py`.

## Tech

Python · Gmail API · Google Gemini · faster-whisper · Piper TTS · Windows Task Scheduler
