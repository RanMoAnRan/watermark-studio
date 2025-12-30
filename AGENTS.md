# Repository Guidelines

## Project Structure & Module Organization
- `app.py`: Flask application entrypoint.
- `templates/`: Jinja2 HTML templates (rendered by Flask).
- `static/`: static assets (CSS/JS/images) served by Flask.
- Local-only: `.venv/` (virtualenv) and `.idea/` (IDE settings) should not be committed.

## Build, Test, and Development Commands
This repo is a small Flask app; there is no separate “build” step.

- Create/activate a virtualenv: `python -m venv .venv` then `source .venv/bin/activate`
- Install dependencies: `pip install -r requirements.txt`
- Run locally (simple): `python app.py`
- Run via Flask CLI (debug): `flask --app app run --debug`

## Coding Style & Naming Conventions
- Python: 4-space indentation, PEP 8 conventions.
- Naming: modules/functions `snake_case`, classes `PascalCase`, constants `UPPER_SNAKE_CASE`.
- Flask routes: keep handlers small; move non-web logic into separate modules as the app grows (e.g., `services/`, `models/`).
- Templates/assets: prefer `templates/<page>.html` and `static/{css,js,img}/...`.

## Testing Guidelines
No testing framework is configured yet.

- Recommended: add `pytest` and a `tests/` folder; name tests `test_<feature>.py`.
- Run (once added): `python -m pytest`

## Commit & Pull Request Guidelines
No Git history is present in this directory, so there are no existing commit conventions to follow.

- If you initialize Git, prefer Conventional Commits (e.g., `feat: add home page`, `fix: handle missing template`).
- PRs: include a short description, how to run/verify (`python app.py`), and screenshots for template/CSS changes.

## Security & Configuration Tips
- Don’t commit secrets; use environment variables (consider a local `.env` that is gitignored).
- Avoid running Flask with `--debug` outside local development.
