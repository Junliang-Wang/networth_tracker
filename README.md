# networth

Local-first, snapshot-based net worth tracker. Runs entirely on your machine, no cloud, one SQLite "vault".
Built with **FastAPI + Jinja2 + HTMX**; charts via Chart.js; data in `data/networth.sqlite`.

## Quick start (using `uv`)

1. **Install uv** (if you haven't): https://docs.astral.sh/uv/#installation
2. Open a terminal in this folder and run:
   ```bash
   uv sync
   uv run uvicorn app.main:app --reload
   ```
3. Open http://localhost:8000

## Project layout

```
networth/
  app/            # FastAPI app
    routes/       # Routers
    templates/    # Jinja templates
    static/       # CSS/JS
  data/           # Your SQLite "vault" lives here
  analysis/       # Notebooks/scripts (optional)
  tests/          # pytest
  pyproject.toml  # uv project file
```

## Notes

- **Snapshots**: one row per account per date; FX rates are locked per snapshot.
- **Liabilities** entered as positive balances; app subtracts category from net worth.
- **Rolling 12-month change** shown on dashboard.
