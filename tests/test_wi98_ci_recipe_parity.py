"""WI-98: el runner remoto ejecuta OTRA receta, y el guard sólo busca cadenas.

Por qué este fichero existe
---------------------------
`AGENTS.md` («Compatibilidad con otros runners») dice, en una línea:

    GitHub Actions, GitLab CI, Jenkins o cualquier otro runner remoto **debe**
    invocar el mismo `.pipeline.kts` desde el mismo checkout.

Medido en WI-98, esa línea describe algo que no ocurre:

  * `.github/workflows/ci.yml` **no invoca** `.pipeline.kts`. De los siete
    stages canónicos reproduce **uno** (`lint`); `unit-tests` lo hace con otra
    receta y `coverage-floors`, `package-build`, `discover-repo` y `evidence`
    no existen en el remoto.
  * Los nueve tests de `tests/test_hooks_system.py::TestCIWorkflow` no
    comparan nada: comprueban que el fichero **contenga cadenas**. Uno de
    ellos acepta `assert "pytest" in content or "test" in content.lower()`,
    que un fichero con la palabra «test» en un comentario satisfaría.
  * **Ningún test del repo compara `ci.yml` con `.pipeline.kts`.**

Y la divergencia no es de estilo. Con el **mismo instrumento**
(`check_coverage_floors.py`, criterio de recuentos):

    modulo                       canonica    remota
    cli/commands/runs.py           87.96 %    39 %
    cli/commands/run.py            96.09 %    81 %
    cli/support.py                 85.71 %    69 %   <- incumple el suelo del 70 %

El runner remoto puede dar **verde** un paquete que no cumple el suelo que
el propio AGENTS.md §6.3 declara, porque no ejecuta el checker y su medición
no ve lo que el canónico ve.

Qué fijan estos tests
--------------------
El invariante es **una propiedad**: *todo runner remoto declarado invoca la
receta canónica*. No es «el fichero menciona pytest», que es lo que había.

Los tests de arriba comprueban la propiedad con informes sintéticos; los de
abajo la comprueban contra los ficheros reales del repo.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import check_ci_recipe_parity as par  # noqa: E402

WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
PIPELINE = ROOT / ".pipeline.kts"

# --- Informes sinteticos ---------------------------------------------------

#: Un workflow sano: invoca la receta canónica y no la reimplementa.
WORKFLOW_SANO = """
name: ci
on:
  push:
    branches: [main]
jobs:
  canonical:
    steps:
      - uses: actions/checkout@v4
      - name: Install mise
        uses: jdx/mise-action@v2
      - name: Verificacion canonica
        run: mise exec -- pipelinek run --rerun .pipeline.kts
"""

#: El workflow que el repo tenia antes de WI-98: su propia receta.
WORKFLOW_A_PELO = """
name: ci
on:
  push:
    branches: [main]
jobs:
  lint-and-test:
    steps:
      - uses: actions/checkout@v4
      - run: mise run lint
      - run: mise run format --check
      - run: mise exec -- uv run pytest --cov=skillgraph -q
"""

#: Una receta canónica portable: resuelve la raíz por entorno o por cwd.
CANONICA_PORTABLE = (
    'val repo = System.getenv("GITHUB_WORKSPACE") ?: System.getProperty("user.dir")\n'
    "pipeline {\n    stages {\n"
    '        stage("discover-repo") { sh("ls " + repo + "/pyproject.toml") }\n'
    '        stage("unit-tests") { sh("cd " + repo + " && bash scripts/coverage.sh") }\n'
    '        stage("lint") { sh("cd " + repo + " && uv run ruff check src tests") }\n'
    "    }\n}\n"
)


def _informe(**cambios: object) -> par.InformeRunners:
    base: dict[str, object] = {
        "receta_canonica": ".pipeline.kts",
        "canonica": CANONICA_PORTABLE,
        "runners": {
            ".github/workflows/ci.yml": WORKFLOW_SANO,
        },
        "etapas_canonicas": par.etapas_de(CANONICA_PORTABLE),
    }
    base.update(cambios)
    return par.InformeRunners(**base)  # type: ignore[arg-type]


# --- C1: todo runner remoto invoca la receta canonica ---------------------


class TestC1InvocaLaRecetaCanonica:
    def test_informe_sano_no_problema(self) -> None:
        assert par.codigos_de(par.evaluar(_informe())) == frozenset()

    def test_workflow_que_reimplementa_la_receta_se_detecta(self) -> None:
        """El fallo real: el remoto decide que tests y lint le bastan."""
        informe = _informe(runners={".github/workflows/ci.yml": WORKFLOW_A_PELO})
        assert par.CODIGO_RECETA_PROPIA in par.codigos_de(par.evaluar(informe))

    def test_el_nombre_del_runner_se_reporta(self) -> None:
        """Un diagnostico sin decir QUE archivo falló obliga a buscarlo a mano."""
        informe = _informe(runners={".github/workflows/ci.yml": WORKFLOW_A_PELO})
        mensajes = " ".join(p.mensaje for p in par.evaluar(informe))
        assert ".github/workflows/ci.yml" in mensajes

    def test_varios_runners_en_par_deben_pasar_todos(self) -> None:
        """Un runner conforme no tapa a uno que no lo esta.

        Sin esto, un segundo runner mal escrito pasaria siempre que el
        primero este bien: basta con que uno de los dos lo este.
        """
        runners = {
            ".github/workflows/ci.yml": WORKFLOW_SANO,
            ".gitlab-ci.yml": WORKFLOW_A_PELO,
        }
        informe = _informe(runners=runners)
        problemas = par.evaluar(informe)
        assert par.CODIGO_RECETA_PROPIA in par.codigos_de(problemas)
        assert ".gitlab-ci.yml" in " ".join(p.mensaje for p in problemas)

    def test_sin_runners_no_hay_problema(self) -> None:
        """Un repo sin CI remoto no viola la regla: no la puede violar."""
        assert par.codigos_de(par.evaluar(_informe(runners={}))) == frozenset()


# --- C2: la receta canonica tiene que ser ejecutable donde se invoque -----


class TestC2CanonicalPortable:
    def test_ruta_absoluta_a_maquina_se_detecta(self) -> None:
        """10 rutas a /var/mnt/... hacen la regla INEJECUTABLE en un runner.

        No es que el remoto incumpla la regla: es que la regla no podria
        cumplirse ni con el mejor workflow. Una promesa que no se puede
        cumplir no es un contrato.
        """
        inexistente = "/home/runner/work/skillgraph/skillgraph/pyproject.toml"
        script = f'pipeline {{ stages {{ stage("x") {{ sh("ls {inexistente}") }} }} }}\n'
        informe = _informe(canonica=script)
        assert par.CODIGO_RUTA_ABSOLUTA in par.codigos_de(par.evaluar(informe))

    def test_resolucion_por_entorno_o_cwd_no_se_detecta(self) -> None:
        """`GITHUB_WORKSPACE` con fallback a `user.dir` es portable."""
        script = (
            'val repo = System.getenv("GITHUB_WORKSPACE") ?: System.getProperty("user.dir")\n'
            'pipeline { stages { stage("x") { sh("ls " + repo + "/pyproject.toml") } } }\n'
        )
        informe = _informe(canonica=script)
        assert par.CODIGO_RUTA_ABSOLUTA not in par.codigos_de(par.evaluar(informe))

    def test_informe_sano_tiene_la_canonica_real(self) -> None:
        """Contra el repo de verdad, no contra un sintético."""
        informe = par.medir(ROOT)
        assert informe.hubo_error is False, informe.error
        assert par.codigos_de(par.evaluar(informe)) == frozenset(), par.evaluar(informe)


# --- C3: las etapas canonicas se declaran, no se adivinan ----------------


class TestC3EtapasCanonicas:
    def test_un_script_sin_etapas_no_verifica_nada(self) -> None:
        """Un guard que no puede leer su fuente no puede afirmar nada.

        Y lo contrario de eso es peor: un informe con cero etapas parece un
        repo sin pipeline, que es un diagnóstico distinto del real.
        """
        informe = _informe(etapas_canonicas=())
        assert par.CODIGO_ETAPA_DESCONOCIDA in par.codigos_de(par.evaluar(informe))

    def test_la_lectura_hereda_del_script_y_no_de_una_lista(self) -> None:
        """Las etapas salen de `.pipeline.kts`, no de una constante aparte.

        Si el guard llevara su propia lista, añadir una etapa al pipeline la
        haría invisible para el guard: exactamente el fallo que este bloque
        cierra, repetido un nivel más abajo.
        """
        etapas = par.etapas_de(
            'pipeline { stages { stage("uno") { sh("true") } stage("dos") { sh("true") } } }'
        )
        assert etapas == ("uno", "dos")

    def test_una_etapa_nueva_entra_en_el_contrato_sin_tocar_el_guard(self) -> None:
        """La propiedad se sostiene cambiando el script, no el checker."""
        script = (
            'val repo = System.getProperty("user.dir")\n'
            "pipeline { stages {\n"
            '  stage("discover-repo") { sh("ls " + repo) }\n'
            '  stage("nueva") { sh("cd " + repo + " && true") }\n'
            "} }\n"
        )
        etapas = par.etapas_de(script)
        assert "nueva" in etapas
        informe = _informe(canonica=script, etapas_canonicas=etapas)
        assert par.CODIGO_ETAPA_DESCONOCIDA not in par.codigos_de(par.evaluar(informe))

    def test_lectura_de_etapas_de_un_script_mal_formado(self) -> None:
        """Un script que no se puede leer es un fallo, no un informe vacío.

        Fabricar un informe con cero etapas haría que «no hay etapas» se
        confundiera con «no hay problema».
        """
        assert par.etapas_de("esto no es un script") == ()


# --- Contrato contra los ficheros reales ---------------------------------


class TestFicherosReales:
    def test_la_receta_local_documentada_no_cambia_al_portabilizar(self) -> None:
        """Portar el script no puede alterar el comando canónico.

        `AGENTS.md` fija la forma del comando local (`--rerun`, `--db`,
        `--control-root`). Si al hacerlo portable hubiera que cambiarlo, la
        regla de AGENTS.md y el script dirian cosas distintas.
        """
        texto = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        assert "pipelinek run --rerun" in texto
        assert "--db .pipelinek/db.sqlite" in texto
        assert "--control-root .pipelinek/control" in texto

    def test_el_script_canonico_existe_y_declara_etapas(self) -> None:
        etapas = par.etapas_de(PIPELINE.read_text(encoding="utf-8"))
        assert etapas, "no se ha podido leer ninguna etapa de .pipeline.kts"
