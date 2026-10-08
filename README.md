# DETOUR
An open-AI adventure engine. The AI isn't the destination. It's the excuse to leave.

## Run
    pip install -r requirements.txt
    ollama pull gemma3        # optional: any Gemma-family model
    python app.py             # http://localhost:5000

Env: OLLAMA_URL (default http://localhost:11434), DETOUR_MODEL (default gemma3), DETOUR_DB.
Without a running model, DETOUR falls back to a built-in procedural generator, so the app always works.
Fonts are bundled locally (static/fonts), so the UI works offline.
Location is rounded to ~1 km and only used when you allow it. Everything stays in local SQLite.

## Local (localhost)
    pip install -r requirements.txt
    python app.py            # http://localhost:5000
Location and camera work on localhost. Data lives in detour.db next to app.py.
Optional AI: `ollama pull gemma3` and keep Ollama running; otherwise the built-in generator is used.

## Render free plan
1. Push this folder to GitHub, then New > Blueprint (render.yaml is included) or New > Web Service.
2. Build: `pip install -r requirements.txt`  Start: `gunicorn app:app --bind 0.0.0.0:$PORT`
3. Optional: set OLLAMA_URL to a hosted Gemma endpoint. Render cannot run Ollama itself; without it DETOUR uses its built-in generator.
Free instances sleep after idle time and reset their disk on redeploy or restart, so the SQLite data (notes, XP) is not permanent there. Fine for a demo; use a persistent disk or a hosted database later.
