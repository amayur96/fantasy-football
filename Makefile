.PHONY: setup sync sync-refresh server web dev test reset-draft user requirements

setup:
	uv sync
	npm --prefix web install

sync:
	PYTHONPATH=server uv run python -m ffdraft.sync

sync-refresh:
	PYTHONPATH=server uv run python -m ffdraft.sync --refresh

server:
	uv run uvicorn ffdraft.main:app --reload --port 8000 --app-dir server

web:
	npm --prefix web run dev

dev:
	$(MAKE) -j2 server web

test:
	uv run pytest -q

reset-draft:
	rm -f data/draft_state.json

# Regenerate the pinned deps Render installs; run after changing pyproject.toml
requirements:
	uv export --no-dev --no-emit-project --no-hashes --format requirements-txt -o requirements.txt

# make user CMD="add arjun"   (list | add <name> | passwd <name> | rm <name>)
user:
	PYTHONPATH=server uv run python -m ffdraft.users $(CMD)
