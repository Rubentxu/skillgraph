// .pipeline.kts — skillgraph (Python, hatchling + uv)
//
// Ejecuta verificación real: sync dependencias + pytest + los tres
// contratos exigibles del repo.
//
// IMPORTANTE 1 — la raiz se RESUELVE, no se escribe (WI-98):
//   El motor v0.39.0 NO define `$REPO_ROOT` ni resuelve el cwd del
//   script: el `sh()` corre en un workspace del motor, no en el repo.
//   Por eso toda ruta pasa por `repo`, que se resuelve en Kotlin a
//   `GITHUB_WORKSPACE` si el runner la define y al `user.dir` del
//   proceso (el repo, cuando se invoca desde su raiz) si no.
//
//   Antes (WI-45) esto se resolvia escribiendo diez rutas absolutas a
//   `/var/mnt/DiscoChino2-fast/...`. Eso arreglaba el symptom local y
//   hacia la receta INEJECUTABLE en cualquier otra maquina, de modo que
//   la regla de AGENTS.md («el runner remoto debe invocar el mismo
//   .pipeline.kts») no podia cumplirse ni con el mejor workflow.
//   MEDIDO: el motor si propaga el entorno a los `sh()` — un
//   `GITHUB_WORKSPACE` exportado llega intacto al shell — asi que la
//   resolucion es una linea, no un truco.
//
// IMPORTANTE 2 — sh() + pipe pierde el exit code:
//   `sh("cmd 2>&1 | tail -N")` retorna el exit code de `tail` (0),
//   no el del comando. Workaround: `${PIPESTATUS[0]}` + `test`.
//   OJO: en este DSL el `$` debe ir ESCAPADO (`\${...}`) o Kotlin lo
//   interpreta como string template y la compilacion falla con
//   "Unresolved reference 'PIPESTATUS'".

// La raiz del repositorio. Ver IMPORTANTE 1.
val repo = System.getenv("GITHUB_WORKSPACE") ?: System.getProperty("user.dir")

pipeline {
    stages {
        stage("discover-repo") {
            sh("ls -la " + repo + "/pyproject.toml " + repo + "/AGENTS.md | head -3")
            sh("head -5 " + repo + "/pyproject.toml")
        }

        stage("sync-deps") {
            // uv sync --dev: instala deps desde uv.lock; idempotente.
            sh("cd " + repo + " && uv sync --dev 2>&1 | tail -5; test \${PIPESTATUS[0]} -eq 0")
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
            sh("cd " + repo + " && bash scripts/coverage.sh 2>&1 | tail -12; test \${PIPESTATUS[0]} -eq 0")
        }

        stage("coverage-floors") {
            // El segundo contrato declarado: AGENTS.md §6.3 pone suelos
            // POR MODULO (core >=90 %, CLI >=70 %, paths.py >=60 %).
            // `coverage report` solo admite un umbral global, asi que
            // ese contrato no lo comprobaba NINGUNA herramienta.
            // Este stage lo hace exigible en cada commit.
            sh("cd " + repo + " && uv run python scripts/check_coverage_floors.py 2>&1 | tail -20; test \${PIPESTATUS[0]} -eq 0")
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
            sh("cd " + repo + " && uv run python scripts/check_package_build.py 2>&1 | tail -20; test \${PIPESTATUS[0]} -eq 0")
        }

        stage("public-surfaces") {
            // El QUINTO contrato declarado (B10), y el que cierra dos de
            // las seis propiedades que B9 dejo OPEN por falta de
            // certificacion: `resource/controller API estable` y
            // `CLI estable`.
            //
            // Sin el, ambas se cerraban en veinte segundos escribiendo un
            // fichero: se declaraba un `__all__` y se hacia `touch`. Los
            // predicados de B9 miraban la EXISTENCIA del snapshot, no su
            // contenido, y un `touch` los ponia en verde con el gate de
            // 1.0 exactamente igual de lejos.
            //
            // Este stage EJECUTA la comparacion contra el arbol. Las dos
            // superficies se generan con `--actualizar`, y por eso el
            // fichero nunca se escribe a mano: lo escribe el codigo que
            // sabe lo que hay.
            sh("cd " + repo + " && uv run python scripts/check_public_surfaces.py 2>&1 | tail -20; test \${PIPESTATUS[0]} -eq 0")
        }

        stage("ci-parity") {
            // El CUARTO contrato declarado (WI-98), y el que vigila a los
            // otros tres: comprueba que todo runner remoto invoque esta
            // misma receta y que esta receta se pueda ejecutar fuera de
            // esta maquina.
            //
            // Sin el, la regla de AGENTS.md («el runner remoto debe
            // invocar el mismo .pipeline.kts») era una declaracion sin
            // verificador: .github/workflows/ci.yml ejecutaba su propia
            // receta y de los siete stages de aqui reproducia UNO.
            sh("cd " + repo + " && uv run python scripts/check_ci_recipe_parity.py 2>&1 | tail -20; test \${PIPESTATUS[0]} -eq 0")
        }

        stage("lint") {
            sh("cd " + repo + " && uv run ruff check src tests 2>&1 | tail -5; test \${PIPESTATUS[0]} -eq 0")
        }

        stage("evidence") {
            // El QUINTO contrato declarado (WI-105): AGENTS.md («CI Local
            // Obligatorio») enumera SEIS criterios de exito que un run
            // «debe cumplir», y hasta aqui no los comprobaba NINGUNA
            // herramienta. Esta etapa era el unico sitio de la receta que
            // tocaba `.pipelinek/`, y sus tres comandos no podian fallar:
            // los tres operandos los crea el motor ANTES de la etapa.
            //
            // MEDIDO contra el journal real: 15 runs, 3 de ellos
            // `RunFinished/failure`, y los tres comandos imprimian
            // «present» en los quince.
            //
            // Lo que no se puede era distinguir un `SUCCESS` de una
            // verificacion real de uno cacheado: los dos dicen
            // `Pipeline finished with SUCCESS`. Ese es el criterio 2, y
            // AGENTS.md lo describe porque sin `--rerun` el motor
            // reutiliza el veredicto previo. Aqui se mide.
            //
            // POR QUE VERIFICA SU PROPIO RUN, Y NO EL ANTERIOR. B24:
            // antes verificaba el ultimo run TERMINADO, y suena sensato
            // porque cuando esta etapa corre el run en curso aun no tiene
            // `RunFinished`. Es un TRINQUETE: si el anterior fallo de
            // verdad, este se juzga con ese fallo y falla; y el siguiente se
            // juzga con ESTE, que termino en `failure` porque su etapa
            // `evidence` fallo. MEDIDO en este repo: tras el fallo real de
            // `v0.34.0` —tres reds de estado— cuatro runs seguidos con la
            // suite en verde y las ocho etapas de codigo en `success`
            // terminaron en `failure`, todos aqui. La exculpacion minima de
            // WI-110 no lo arregla: perdona el `StepFailed` de
            // `evidence/sh-0`, nunca el VEREDICTO del run.
            //
            // Ahora el verificador elige el run EN CURSO —el suyo— y mide lo
            // que ya existe: sus `StepStarted`, sus `EchoOutputCaptured` y
            // sus `StepFailed`. El veredicto final no se verifica aqui porque
            // todavia no se ha emitido, y no se finge que si: esa
            // certificacion puntual es el mismo script con `--run-id`.
            //
            // MEDIDO al cambiarlo: `informes()` devolvia 5 informes para 2
            // runs, porque un `defaultdict` usado como conjunto no crea la
            // clave con `in` y el `continue` por payload vacio pasaba antes de
            // registrarla. Un run cuyo primer evento va vacio se anadia una
            // vez POR CADA evento suyo, y la eleccion se hace sobre esa lista.
            // Contasalto de 4 sondas, 4/4 cazadas
            // (`.pipelinek/b24_trinquete_mutate.py`).
            sh("cd " + repo + " && uv run python scripts/check_pipeline_receipt.py --db .pipelinek/db.sqlite --control-root .pipelinek/control 2>&1 | tail -20; test \${PIPESTATUS[0]} -eq 0")
        }
    }
}
