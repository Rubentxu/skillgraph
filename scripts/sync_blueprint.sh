#!/usr/bin/env bash
# scripts/sync_blueprint.sh
#
# Sincroniza el snapshot versionado docs/blueprint/ con el origen
# external/blueprint-v1/ (gitignored).
#
# Politica: ver docs/blueprint/SYNC.md.
#
# Uso:
#   bash scripts/sync_blueprint.sh            # sincroniza
#   bash scripts/sync_blueprint.sh --check    # solo verifica si hay drift
#   bash scripts/sync_blueprint.sh --force    # sincroniza sin preguntar
#
# Exit codes:
#   0  sin cambios (o --check sin drift)
#   1  drift detectado (--check) o argumento invalido
#   2  error de I/O (origen no existe, no se puede escribir)
#
# El script es idempotente: ejecutarlo dos veces seguidas produce
# el mismo resultado que ejecutarlo una vez.

set -euo pipefail

# ---------------------------------------------------------------------------
# Ubicacion del repo (asume script en <repo>/scripts/sync_blueprint.sh)
# ---------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORIGIN="$REPO_ROOT/external/blueprint-v1"
SNAPSHOT="$REPO_ROOT/docs/blueprint"
SHA_FILE="$SNAPSHOT/SOURCE_SHA"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

die() { echo "ERROR: $*" >&2; exit 2; }
info() { echo "==> $*"; }

# Calcula el SHA agregado (orden estable, solo *.md) de los archivos
# sincronizables del origen. Es estable bajo reordenamientos y es
# suficientemente fuerte: si el origen cambia, el SHA cambia.
compute_origin_sha() {
    if [[ ! -d "$ORIGIN" ]]; then
        die "Origen no existe: $ORIGIN"
    fi

    # Hash por archivo ordenado lexicograficamente, luego concat.
    (
        cd "$ORIGIN"
        find . -type f -name '*.md' | LC_ALL=C sort | while read -r f; do
            sha256sum "$f"
        done
    ) | sha256sum | awk '{print $1}'
}

# Verifica que el snapshot existe. Si no, lo inicializa vacio.
ensure_snapshot() {
    if [[ ! -d "$SNAPSHOT" ]]; then
        mkdir -p "$SNAPSHOT/adr" "$SNAPSHOT/plan" "$SNAPSHOT/references"
        info "Snapshot inicializado en $SNAPSHOT"
    fi
}

# Sincroniza los archivos del origen al snapshot.
sync_files() {
    cp "$ORIGIN"/*.md "$SNAPSHOT/" || true
    cp "$ORIGIN/adr/"*.md "$SNAPSHOT/adr/" || true
    cp "$ORIGIN/plan/"*.md "$SNAPSHOT/plan/" || true
    cp "$ORIGIN/references/"*.md "$SNAPSHOT/references/" || true
}

# ---------------------------------------------------------------------------
# Modo --check
# ---------------------------------------------------------------------------

mode_check() {
    [[ -f "$SHA_FILE" ]] || { echo "drift: source_sha no registrado aun"; exit 1; }
    current_sha="$(compute_origin_sha)"
    recorded_sha="$(cat "$SHA_FILE")"
    if [[ "$current_sha" == "$recorded_sha" ]]; then
        echo "blueprint: sin drift (sha=${current_sha:0:12}...)"
        exit 0
    fi
    echo "drift detectado:"
    echo "  registrado: ${recorded_sha:0:12}..."
    echo "  origen:     ${current_sha:0:12}..."
    exit 1
}

# ---------------------------------------------------------------------------
# Modo normal
# ---------------------------------------------------------------------------

MODE="sync"
[[ "${1:-}" == "--check" ]] && MODE="check"
[[ "${1:-}" == "--force" ]] && MODE="force"

if [[ "$MODE" == "check" ]]; then
    mode_check
fi

ensure_snapshot
ORIGIN_SHA="$(compute_origin_sha)"

if [[ -f "$SHA_FILE" ]]; then
    RECORDED_SHA="$(cat "$SHA_FILE")"
    if [[ "$ORIGIN_SHA" == "$RECORDED_SHA" ]] && [[ "$MODE" != "force" ]]; then
        info "Snapshot al dia (sha=${ORIGIN_SHA:0:12}...). Nada que hacer."
        exit 0
    fi
    if [[ "$MODE" != "force" ]]; then
        info "Drift detectado (recorded=${RECORDED_SHA:0:12}..., origin=${ORIGIN_SHA:0:12}...)."
        read -r -p "Re-sincronizar? [y/N] " ans
        [[ "$ans" =~ ^[Yy]$ ]] || { echo "abort."; exit 1; }
    fi
fi

info "Sincronizando $ORIGIN -> $SNAPSHOT"
sync_files
echo "$ORIGIN_SHA" > "$SHA_FILE"
info "Snapshot actualizado. SHA registrado: ${ORIGIN_SHA:0:12}..."
info ""
info "Proximo paso: revisar cambios y commitear con"
info "  git add docs/blueprint/"
info "  git commit -m 'docs(blueprint): sync con external/blueprint-v1 <sha>'"
