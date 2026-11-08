.PHONY: setup test lint collect demo web build schema
setup:            ## Installation complète (Python + Node)
	python3 -m venv .venv && .venv/bin/pip install -e ".[dev]" && pnpm install
test:             ## Tous les tests
	.venv/bin/pytest && pnpm -r test
lint:
	.venv/bin/ruff check collector && pnpm -r typecheck
collect:          ## Collecte réelle locale (petit budget)
	.venv/bin/python -m collector run --max-details 20
demo:             ## Régénère le jeu de démonstration FICTIF de la PWA
	.venv/bin/python -m collector demo
schema:
	.venv/bin/python -m collector schema
web:              ## PWA en développement (données de démo, ou VITE_DATA_URL)
	pnpm dev
build:
	pnpm build
