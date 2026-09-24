#!/usr/bin/env bash
# scripts/audit_bundle.sh — genera un bundle reproducible de
# SkillGraph sobre un SHA certificado para auditoría independiente.
#
# Uso:
#   bash scripts/audit_bundle.sh <commit-sha>
#
# Ejemplo:
#   bash scripts/audit_bundle.sh 2ae1bca5d82f59ae257ed300d621368268e7d8a4
#
# Salidas en:
#   ${JCODE_SCRATCH_DIR}/skillgraph-${SHORT_SHA}/     <- árbol clonado (.git)
#   ${JCODE_SCRATCH_DIR}/skillgraph-${SHORT_SHA}-audit-bundle.tar.gz
#
# Variables de entorno (todas opcionales):
#   REPO_ROOT    : ruta absoluta al repo fuente (auto-detectada).
#   JCODE_SCRATCH_DIR : directorio de salida (default ~/.jcode_scratch/).
#
# Notas:
#   - Usa `git clone` (no `git archive` sin .git) porque las UATs
#     necesitan `git rev-parse HEAD` y sin metadatos fallan.
#   - Excluye `.venv` y `__pycache__` del bundle final.
#   - CERO modificaciones al repo original (`git clone --no-local`).

set -euo pipefail

if [ "$#" -ne 1 ]; then
    echo "Uso: bash scripts/audit_bundle.sh <commit-sha>" >&2
    echo "Ej:  bash scripts/audit_bundle.sh 2ae1bca5d82f59ae257ed300d621368268e7d8a4" >&2
    exit 2
fi

SHA="$1"
SHORT_SHA="${SHA:0:7}"

# REPO_ROOT: por defecto, se deduce del path de este script (caller-side).
if [ -z "${REPO_ROOT:-}" ]; then
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
    REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
fi

# Verificación de sanidade.
if [ ! -d "$REPO_ROOT/.git" ]; then
    echo "[audit_bundle] ERROR: REPO_ROOT no contiene .git: $REPO_ROOT" >&2
    echo "             Exporta REPO_ROOT=/ruta/al/repo o ejecuta desde su raíz." >&2
    exit 5
fi

SCRATCH="${JCODE_SCRATCH_DIR:-$HOME/.jcode_scratch/skillgraph-audit-$SHORT_SHA}"
mkdir -p "$SCRATCH"

if [ -d "$SCRATCH/skillgraph-$SHORT_SHA" ]; then
    echo "[audit_bundle] ERROR: scratch dir del clon ya existe: $SCRATCH/skillgraph-$SHORT_SHA" >&2
    echo "             Elimínalo o usa otro JCODE_SCRATCH_DIR." >&2
    exit 3
fi

cd "$SCRATCH"
echo "[audit_bundle] clonando ${SHA} desde ${REPO_ROOT}..."
git clone --no-local --branch main "$REPO_ROOT" "skillgraph-$SHORT_SHA"

cd "skillgraph-$SHORT_SHA"

HEAD_LOCAL=$(git rev-parse HEAD)
if [ "$HEAD_LOCAL" != "$SHA" ]; then
    echo "[audit_bundle] ERROR: HEAD del clon es $HEAD_LOCAL, no $SHA" >&2
    exit 4
fi

echo "[audit_bundle] HEAD verificado: $HEAD_LOCAL"
echo "[audit_bundle] tags que apuntan a HEAD:"
git tag --points-at HEAD | sed 's/^/  - /'

echo "[audit_bundle] sincronizando entorno..."
if command -v uv >/dev/null 2>&1; then
    uv sync --quiet
else
    echo "[audit_bundle] ERROR: uv no instalado; instalalo desde https://github.com/astral-sh/uv" >&2
    exit 6
fi

echo "[audit_bundle] ejecutando bash scripts/ci.sh..."
bash scripts/ci.sh 2>&1 | tee ci-output-cleanroom.txt

echo "[audit_bundle] ejecutando uat_audit..."
uv run python tests/uat_audit.py 2>&1 | tee uat-audit-cleanroom.txt

echo ""
echo "[audit_bundle] resultados en ${SCRATCH}/skillgraph-${SHORT_SHA}/:"
echo "  - ci-output-cleanroom.txt"
echo "  - uat-audit-cleanroom.txt"
echo ""

cd "$SCRATCH"
echo "[audit_bundle] construyendo bundle reproducible..."
tar --exclude="skillgraph-$SHORT_SHA/.venv" \
    --exclude="skillgraph-$SHORT_SHA/**/__pycache__" \
    -czf "skillgraph-$SHORT_SHA-audit-bundle.tar.gz" \
    "skillgraph-$SHORT_SHA/"

echo "[audit_bundle] bundle: $SCRATCH/skillgraph-$SHORT_SHA-audit-bundle.tar.gz"
echo "[audit_bundle] SHA certificado: $SHA"
echo "[audit_bundle] veredicto reproducible:"
grep -E "(passed|FAIL|PASS=)" ci-output-cleanroom.txt uat-audit-cleanroom.txt 2>/dev/null | tail -5 || true
