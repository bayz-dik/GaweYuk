# ONEJOB MVP

A runnable vertical slice of a unified career intelligence system. It merges equivalent opportunities across platforms, evaluates fit and trust, applies user policies, and suggests evidence-backed application answers.

## Run in Termux / Linux

```bash
python -m pip install -r requirements.txt
python -m onejob.cli jobs
uvicorn onejob.api:app --host 0.0.0.0 --port 8000
```

Open `http://127.0.0.1:8000`.

## CLI

```bash
python -m onejob.cli jobs
python -m onejob.cli job <ONEJOB_ID>
python -m onejob.cli answer --job <ONEJOB_ID> --question "What is your expected salary?"
```

## What the MVP proves

- Jobs from separate platforms can become one canonical opportunity.
- Matching is explainable, not a single opaque number.
- Hard user policies can stop an otherwise strong match.
- Suspicious payment requests can hard-block a listing.
- Application answers come from Career Twin facts; unknown personal facts are not invented.

Live collectors, persistent storage, authentication, ATS connectors, browser-assisted apply, semantic embeddings, and temporal TrustGraph are the next layers rather than being faked in this MVP.
