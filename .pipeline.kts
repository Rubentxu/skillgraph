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
            // UNA sola corrida hace los dos trabajos: tests Y cobertura.
            //
            // Antes (WI-93): `uv run pytest` a pelo, ~110s. La cobertura
            // se media a mano con `scripts/coverage.sh` porque su autor
            // escribio que "la instrumentacion de subproceso multiplica
            // el tiempo de suite". Esa premisa NUNCA se habia medido.
            //
            // MEDIDO 2026-10-02 (WI-93): `scripts/coverage.sh` tarda
            // 203s de wall clock frente a los ~110s de pytest a pelo.
            // No multiplica: cuesta +93s (~1.85x el stage). La premisa
            // era una hipotesis sin dato y el dato la desmiente.
            //
            // Por que UNA corrida y no dos: correr pytest dos veces
            // (una para tests, otra para cobertura) costaria 110+203s.
            // La receta ya ejecuta pytest con `--cov`, asi que su
            // salida sirve para las dos cosas.
            //
            // La instrumentacion de subproceso NO es opcional: sin el
            // hook .pth, el CLI que la suite lanza por subproceso
            // mide 65.86 % en vez de 94 % (ver cabecera de
            // scripts/coverage.sh). Con el hook, la medicion es real.
            sh("cd /var/mnt/DiscoChino2-fast/Proyectos/python/skillgraph && bash scripts/coverage.sh 2>&1 | tail -12; test \${PIPESTATUS[0]} -eq 0")
        }

        stage("coverage-floors") {
            // El segundo contrato declarado: AGENTS.md §6.3 pone suelos
            // POR MODULO (core >=90 %, CLI >=70 %, paths.py >=60 %).
            // `coverage report` solo admite un umbral global, asi que
            // ese contrato no lo comprobaba NINGUNA herramienta.
            // Este stage lo hace exigible en cada commit.
            sh("cd /var/mnt/DiscoChino2-fast/Proyectos/python/skillgraph && uv run python scripts/check_coverage_floors.py 2>&1 | tail -20; test \${PIPESTATUS[0]} -eq 0")
        }

        stage("package-build") {
            // El TERCER contrato declarado, y el ultimo eslabon de la cadena
            // de release: git -> __version__ -> pyproject -> wheel.
            //
            // Hasta WI-97 ese eslabon no se ejecutaba nunca. Cero tests
            // referenciaban hatchling, `uv build` o `entry_points`, y ningun
            // stage construia el paquete. Toda la regla de SemVer de
            // AGENTS.md §12 media un numero sobre un artefacto que nadie
            // habia visto nacer.
            //
            // MEDIDO: `uv build` tarda 1.7 s. No es un stage caro; es el mas
            // barato de los que miden algo. Construye a un temporal, nunca a
            // `dist/`, para no ensuciar `git status --porcelain`.
            sh("cd /var/mnt/DiscoChino2-fast/Proyectos/python/skillgraph && uv run python scripts/check_package_build.py 2>&1 | tail -20; test \${PIPESTATUS[0]} -eq 0")
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
