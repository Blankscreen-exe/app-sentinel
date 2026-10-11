# Recorded backup demo

A saved, offline-viewable assessment for demonstrating the tool when live Claude or the
lab/network are unavailable. It needs only the API + main database.

## Load it

```bash
docker compose exec worker python demo/load_recorded_demo.py
```

Then open `/assessments/recordeddemo0000000000000000demo`. The page shows a **RECORDED
DEMO** banner so it is never mistaken for a live run. The HTML/JSON/PDF reports work too.

Idempotent: re-running replaces the prior load. The content is a curated recording of a
real broken-mode run (anonymous read, cross-tenant, RLS-disabled findings) with rationales
mirroring a real Claude-driven assessment.
