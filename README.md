# Price Intelligence Platform

Production-grade async extraction service for price intelligence, catalog monitoring, and structured web data collection.

## What It Demonstrates

- FastAPI service layer with typed request and response schemas.
- Async HTTP extraction through `httpx.AsyncClient`.
- Controlled Playwright browser pool for JavaScript-heavy targets.
- SQLite-backed durable task queue and persistent run history using SQLAlchemy async ORM.
- Pydantic configuration schemas for strict target validation.
- Retry budgets, proxy rotation hooks, session/user-agent rotation, and safe missing-selector handling.
- Structured JSON logs, health endpoint, worker process, Docker image, and test suite.

## Repository Layout

```text
price-intelligence-platform/
├── src/price_intel/
│   ├── api/                 # FastAPI routers and dependency wiring
│   ├── database.py          # Async engine/session/bootstrap
│   ├── extractors.py        # HTTP and browser extraction engines
│   ├── logging.py           # JSON logging
│   ├── main.py              # FastAPI app factory
│   ├── orm.py               # SQLAlchemy persistence models
│   ├── proxies.py           # Proxy and identity rotation helpers
│   ├── queue.py             # SQLite-backed durable queue
│   ├── schemas.py           # Pydantic API/config schemas
│   ├── service.py           # Extraction orchestration service
│   └── worker.py            # Long-running worker loop
├── tests/
├── configs/
├── Dockerfile
├── pyproject.toml
└── .env.example
```

## Local Setup

```bash
python -m venv .venv
. .venv/Scripts/activate  # Windows PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -e ".[dev]"
playwright install chromium
copy .env.example .env
```

Run the API:

```bash
uvicorn price_intel.main:app --reload
```

Run a worker:

```bash
price-intel-worker
```

Run tests:

```bash
pytest
ruff check .
mypy src
```

## Example Request

```bash
curl -X POST http://localhost:8000/runs \
  -H "Content-Type: application/json" \
  -d @configs/example_request.json
```

Check status:

```bash
curl http://localhost:8000/runs/<run_id>
curl http://localhost:8000/runs/<run_id>/items
```

## Docker

```bash
docker build -t price-intel .
docker run --rm -p 8000:8000 --env-file .env price-intel
```

## GitHub Deployment

Create a new public repository named `price-intelligence-platform` under `tayyabnasir01112-debug`, then push:

```bash
git init
git add .
git commit -m "Build async price intelligence platform"
git branch -M main
git remote add origin https://github.com/tayyabnasir01112-debug/price-intelligence-platform.git
git push -u origin main
```

If using a PAT, give it only `repo` scope for a private repository or `public_repo` for a public repository. Prefer authenticating through GitHub CLI or your system credential manager rather than placing tokens in commands.

