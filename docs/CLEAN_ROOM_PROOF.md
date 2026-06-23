# Clean Room Proof

**Project:** Homey Intelligence  
**Python:** `3.13.3`  
**uv:** `0.7.13`  
**Platform:** `win32`

## Exact setup

```bash
git clone <repo>
cd homey
uv sync --locked
```

The repo is pinned by:
- `pyproject.toml`
- `uv.lock`
- `.python-version`

## Exact validation commands

```bash
python --version
uv --version
pytest -q
python eval/harness.py
python stress/combined_stress_day.py
python -m uvicorn infra.integration:app --port 8000
```

## Verified outputs

- `pytest tests -q` → `144 passed`
- `python eval/harness.py` → `110/110 passed` across five families and seven dimensions
- `python stress/combined_stress_day.py` → `9/9 passed`
- API boot → both port 8000 and 8001 health checks returned `200`
- Restricted HTTP request → typed refusal with `guard_status.category=credit`

## Environment-sensitive behavior

- `python eval/harness.py` and `python stress/combined_stress_day.py` need UTF-8 output on Windows, so the repo uses `sys.stdout.reconfigure(encoding="utf-8")`.
- The evaluation harness and stress script can emit TensorFlow / FAISS startup warnings on first import.
- Retrieval can fall back to sample data until the real corpus contract is wired.
- The LLM-backed path is optional and only activates when `GROQ_API_KEY` is set.

## What is still blocked externally

- The real backend request/response contract from Nikunj.
- The production corpus source and index path for retrieval.
- Policy signoff on which broker-facing fields are allowed in production.
