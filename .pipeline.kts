// .pipeline.kts — skillgraph (Python, hatchling + uv)
// Ejecuta verificación real: sync dependencias + pytest.
//
// IMPORTANTE 1 — rutas absolutas obligatorias:
//   El motor v0.39.0 NO define `$REPO_ROOT` ni resuelve el cwd del
//   script. Toda variable de shell llega vacía, así que
//   `sh("ls $REPO_ROOT/pyproject.toml")` se ejecutaba contra
//   `/pyproject.toml` y fallaba con "No existe el fichero".
//   AGENTS.md ya lo advertía ("usar rutas absolutas dentro de sh(...)");
//   el script no cumplía su propia norma y por eso el pipeline
//   reportaba FAILURE o, peor, un SUCCESS cacheado que no verificaba
//   nada. WI-45 lo corrige.
//
// IMPORTANTE 2 — sh() + pipe pierde el exit code:
//   `sh("cmd 2>&1 | tail -N")` retorna el exit code de `tail` (0),
//   no el del comando. Workaround: `${PIPESTATUS[0]}` + `test`.
//   OJO: en este DSL el `$` debe ir ESCAPADO (`\${...}`) o Kotlin lo
//   interpreta como string template y la compilacion falla con
//   "Unresolved reference 'PIPESTATUS'".

pipeline {
    stages {
        stage("discover-repo") {
            sh("ls -la /var/mnt/DiscoChino2-fast/Proyectos/python/skillgraph/pyproject.toml /var/mnt/DiscoChino2-fast/Proyectos/python/skillgraph/AGENTS.md | head -3")
            sh("head -5 /var/mnt/DiscoChino2-fast/Proyectos/python/skillgraph/pyproject.toml")
        }

        stage("sync-deps") {
            // uv sync --dev: instala deps desde uv.lock; idempotente.
            sh("cd /var/mnt/DiscoChino2-fast/Proyectos/python/skillgraph && uv sync --dev 2>&1 | tail -5; test \${PIPESTATUS[0]} -eq 0")
        }

        stage("unit-tests") {
            // pytest en todos los tests. Tiempo medido: ~131s en frío, ~750s en suite completa.
            sh("cd /var/mnt/DiscoChino2-fast/Proyectos/python/skillgraph && uv run pytest --no-header -q 2>&1 | tail -10; test \${PIPESTATUS[0]} -eq 0")
        }

        stage("lint") {
            sh("cd /var/mnt/DiscoChino2-fast/Proyectos/python/skillgraph && uv run ruff check src tests 2>&1 | tail -5; test \${PIPESTATUS[0]} -eq 0")
        }

        stage("evidence") {
            sh("ls -la /var/mnt/DiscoChino2-fast/Proyectos/python/skillgraph/.pipelinek/db.sqlite")
            sh("test -d /var/mnt/DiscoChino2-fast/Proyectos/python/skillgraph/.pipelinek/control/last-run && echo 'last-run present'")
            sh("test -d /var/mnt/DiscoChino2-fast/Proyectos/python/skillgraph/.pipelinek/control/workspace && echo 'workspace tracking present'")
        }
    }
}
