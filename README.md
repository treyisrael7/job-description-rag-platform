# InterviewOS

Upload a job description PDF and your resume, then practice interview questions with feedback grounded in the actual role requirements. InterviewOS focuses on one core loop: generate role-specific questions, answer them, and get cited feedback that uses the JD and resume instead of generic advice.

Built with Next.js, FastAPI, PostgreSQL + pgvector, and OpenAI. Local dev uses a file-based upload folder; production can use S3.

## Getting started

Copy `.env.example` to `.env`, then add your `OPENAI_API_KEY` (you’ll need it for ingestion and Q&A). The default auth path is a frictionless portfolio demo: `DEMO_MODE_ENABLED=true` and `NEXT_PUBLIC_AUTH_MODE=demo`, which creates an anonymous browser session without login. Clerk is optional; set `NEXT_PUBLIC_AUTH_MODE=clerk`, then add `CLERK_JWKS_URL` and `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` only if you want real sign-in.

Then:

```bash
make up
```

Web runs at http://localhost:3000, API at http://localhost:8000. If you’re using pgAdmin, it’s on port 5050.

Run migrations with `make db-migrate` (or `cd apps/api && alembic upgrade head` if you’re running things locally).

## What it does

**Job descriptions** – Parses JD PDFs, chunks the role requirements, and stores embeddings so interview questions and feedback can cite the source material.

**Interview practice** – Upload one resume on the dashboard and reuse it across JDs. The system generates behavioral and role-specific questions, then evaluates your answers using evidence from the JD and your resume.

**Ask** – A supporting cited Q&A path for checking details in the JD or resume when preparing.

## Testing with real PDFs

There are PowerShell scripts in `scripts/` for upload, retrieval, reingest, chunk stats, and Q&A. Edit `scripts/test-upload.ps1` to point `$pdfPath` at a JD, run it, then use `scripts/test-retrieve.ps1` after ingestion finishes. `scripts/test-ask.ps1` runs the full Q&A flow with citations.

## API access

`/health` is public. In default demo mode, protected routes use an anonymous sandbox session automatically. If you opt into Clerk with `NEXT_PUBLIC_AUTH_MODE=clerk`, protected routes use a Clerk Bearer token instead. Example:

```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"document_id":"uuid","question":"What is the salary range?"}'
```

Document flow: `POST /documents/presign` → PUT to the URL → `POST /documents/confirm` → `POST /documents/{id}/ingest`.

## Rate limits

| Route | Limit |
|-------|-------|
| POST /ask | 10/hour |
| POST /documents/ingest | 3/day |
| POST /documents/presign | 10/day |
| POST /documents/confirm | 20/day |

Demo guardrails also cap user text before any LLM call: `MAX_ASK_QUESTION_CHARS`, `MAX_RESUME_QUESTION_CHARS`, and `MAX_INTERVIEW_ANSWER_CHARS`.

Anonymous demo sessions are stored in browser local storage and map to separate sandbox users. Clearing browser storage starts a fresh demo workspace.

## Tests

Backend: `cd apps/api && pytest -v` (Postgres + migrations required). Or `make test` / `make test-docker`.

Frontend: `cd apps/web && npm run test` (or `npm run test:web` from the root).
