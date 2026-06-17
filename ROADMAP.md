# Roadmap

This roadmap keeps the project pointed toward production-grade data engineering and backend extraction work.

## Near Term

- Add Alembic migrations for database schema evolution.
- Add a `docker-compose.yml` profile with Postgres and a persistent volume.
- Add optional Playwright integration tests behind a `browser` pytest marker.
- Add request/run correlation IDs to API responses and structured logs.

## Observability

- Export Prometheus metrics for queue depth, task duration, success rate, and failure reasons.
- Add OpenTelemetry traces around API submission, queue leasing, extraction, and persistence.
- Add a `/metrics` endpoint for deployment environments that scrape service metrics.

## Extraction Engine

- Add per-domain concurrency limits.
- Add robots.txt policy hooks for compliant scraping workflows.
- Add selector fallback chains for pages with multiple layouts.
- Add storage adapters for Postgres and object storage exports.

## API Productization

- Add pagination for run and item listing endpoints.
- Add API-key authentication for deployed environments.
- Add an admin endpoint for requeueing dead tasks.
- Add example Postman or HTTPie collections for API demos.

