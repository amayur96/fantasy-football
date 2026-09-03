.PHONY: setup sync sync-refresh server web dev test reset-draft

setup:
	uv sync
	npm --prefix web install

sync:
	uv run python -m ffdraft.sync

sync-refresh:
	uv run python -m ffdraft.sync --refresh

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
