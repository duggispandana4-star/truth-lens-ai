# Truth Lens

Truth Lens is a local-first fact-checking demonstration. It accepts a claim or
an article URL, searches Google News RSS for related news articles without an
API key, optionally searches Google's Fact Check Tools API for published
fact-check reviews, and saves analyses in SQLite. It does not claim to
determine truth with perfect accuracy.

## Requirements

- Python 3.10 or newer
- A browser
- Optional: a Google Fact Check Tools API key

## Run on Windows

From this folder, in PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

No key is needed for the default related-news search. To also enable published
fact-check search, add a Google Cloud API key to `.env` as
`GOOGLE_FACT_CHECK_API_KEY=...` and enable the Fact Check Tools API for that
key.

Start the server:

```powershell
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000. API documentation is available at
http://127.0.0.1:8000/docs.

## Analysis and evidence

Without a key, the app searches the public Google News RSS feed and links to
the articles it returns. News coverage is not a fact-check: the result remains
**Inconclusive**, and Truth Lens does not infer a verdict from headlines.
When the optional Google Fact Check Tools API is configured, the app displays
the review publisher, review date, exact rating supplied by that publisher,
and links returned by the API. Its broad result label is derived
conservatively from those ratings; unfamiliar or conflicting ratings remain
inconclusive. Reviews are not independent confirmation of a claim, and a lack
of returned reviews is not evidence that a claim is true or false.

Article URLs are limited to public HTTP(S) pages on standard ports. Requests
are made without following redirects; private, loopback, reserved, and
non-public IP addresses are rejected. Authentication, paywalls, and
JavaScript-only content are not bypassed. If retrieval fails, paste the
article text instead.

## Data and privacy

Analyses are stored in the local SQLite database (`truth_lens.db` by default).
This student demo has no user accounts, so its history is shared by people
using the same local instance. Submitted claims are sent to Google News for
the no-key search and to Google's Fact Check Tools API only when a key is
configured. Do not submit confidential or sensitive information.

## Tests

```powershell
pytest
```
