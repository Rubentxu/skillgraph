#!/usr/bin/env bash
# scripts/ci.sh — gate de CI minimo para SkillGraph.
#
# Cumple external/blueprint-v1/plan/ESTRATEGIA-DE-TESTS.md §7:
#   - Formato y analisis estatico (ruff format --check, ruff check).
#   - Tests unitarios (pytest).
#   - Tests de contratos (incluidos en pytest).
#   - Tests de SQLite (incluidos en pytest).
#   - Validacion de ejemplos Markdown/YAML (incluidos en pytest).
#   - UAT deterministas seleccionados (test_cli_uat, test_cli_run_uat).
#
# Salida:
#   exit 0 -> todo OK
#   exit !=0 -> primer gate que falla; imprime que fallo.
#
# Uso:
#   bash scripts/ci.sh
#
# Este script es lo que GitHub Actions (o cualquier runner CI)
# invocaria como paso unico. Los logs son cortos y el primer
# fallo aborta; la bateria completa se ejecuta solo si los
# gates estaticos pasan.

set -euo pipefail

cd "$(dirname "$0")/.."

echo "=== ci: formato ==="
uv run ruff format --check src tests

echo "=== ci: lint ==="
uv run ruff check src tests

echo "=== ci: tests ==="
uv run pytest --tb=short

echo "=== ci: OK ==="
