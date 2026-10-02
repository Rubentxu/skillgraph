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

WI-99 añadió C4 al mismo guard, con la misma forma: *quien ejecuta pytest
está conectado a la receta canónica* —o es un fragmento que ella invoca, o
delega en ella. Sin ese invariante, `scripts/audit_bundle.sh` seguía
produciendo la evidencia de auditoría con un instrumento que mide la mitad,
y el repo entero podía dar verde con esa evidencia dentro.

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

#: El workflow que el repo tenía antes de WI-98: su propia receta.
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

#: El caso que el guard de cadenas no distingue: la receta canonica
#: aparece, pero solo en un COMENTARIO que explica que se usa.
#:
#: Es el `.github/workflows/ci.yml` real de este repo tras WI-98, y es la
#: trampa en la que cae un guard que busca la cadena en el fichero entero:
#: encuentra `.pipeline.kts` en el comentario y da el visto bueno a un
#: workflow que no ejecuta la receta. MEDIDO en WI-98: las cinco
#: mutaciones dieron rc=0 por esto.
WORKFLOW_RECETA_EN_COMENTARIO = """
name: ci
# Este workflow SI invoca .pipeline.kts, lo veriais en el paso de abajo.
on:
  push:
    branches: [main]
jobs:
  lint-and-test:
    steps:
      - uses: actions/checkout@v4
      - run: mise run lint
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
        "raiz_repo": "/home/alguien/work/skillgraph",
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

    def test_receta_mencionada_solo_en_un_comentario_no_cumple(self) -> None:
        """La cadena tiene que estar en un paso que se EJECUTA.

        Es la diferencia entre este guard y los nueve que sustituye. Un
        guard que busca `.pipeline.kts` en el fichero entero encuentra la
        cadena en el comentario que explica que se usa, y da el visto
        bueno a un workflow que ejecuta otra cosa.

        MEDIDO en WI-98: las cinco mutaciones de este contrato dieron
        `rc=0` por esto. El defecto no era de los tests, era del diseño del
        invariante: «contiene la cadena» no es «ejecuta la receta».
        """
        informe = _informe(runners={".github/workflows/ci.yml": WORKFLOW_RECETA_EN_COMENTARIO})
        assert par.CODIGO_RECETA_PROPIA in par.codigos_de(par.evaluar(informe))

    def test_el_parser_ignora_comentarios_y_bloques_escalares(self) -> None:
        """El parser es la base del invariante: se prueba aparte.

        La ultima aserción es la que mas importa: `echo "## ..."` **sí** se
        incluye. Un `##` dentro de una cadena no es un comentario, y un
        parser que lo tratara como tal truncaría el paso por la mitad.
        """
        pasos = par.pasos_ejecutables(
            """
jobs:
  a:
    steps:
      # run: esto es un comentario
      - run: |
          echo "## esto va dentro de una cadena"
          echo uno
      - run: >
          echo dos
          echo tres
      - run: echo cuatro
      - name: otro paso
        run: echo cinco
"""
        )
        assert "echo uno" in pasos
        assert "echo dos" in pasos and "echo tres" in pasos
        assert "echo cuatro" in pasos and "echo cinco" in pasos
        assert not any("esto es un comentario" in p for p in pasos)
        assert 'echo "## esto va dentro de una cadena"' in pasos
        assert "otro paso" not in pasos

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
    def test_ruta_de_este_arbol_se_detecta(self) -> None:
        """10 rutas a /var/mnt/... hacen la regla INEJECUTABLE en un runner.

        No es que el remoto incumpla la regla: es que la regla no podria
        cumplirse ni con el mejor workflow. Una promesa que no se puede
        cumplir no es un contrato.
        """
        raiz = "/var/mnt/DiscoChino2-fast/Proyectos/python/skillgraph"
        script = (
            f'val repo = "{raiz}"\n'
            'pipeline { stages { stage("x") { sh("ls " + repo + "/pyproject.toml") } } }\n'
        )
        informe = _informe(canonica=script, raiz_repo=raiz)
        assert par.CODIGO_RUTA_ABSOLUTA in par.codigos_de(par.evaluar(informe))

    def test_resolucion_por_entorno_o_cwd_no_se_detecta(self) -> None:
        """`GITHUB_WORKSPACE` con fallback a `user.dir` es portable."""
        script = (
            'val repo = System.getenv("GITHUB_WORKSPACE") ?: System.getProperty("user.dir")\n'
            'pipeline { stages { stage("x") { sh("ls " + repo + "/pyproject.toml") } } }\n'
        )
        informe = _informe(canonica=script)
        assert par.CODIGO_RUTA_ABSOLUTA not in par.codigos_de(par.evaluar(informe))

    def test_un_script_que_no_resuelve_la_raiz_se_detecta(self) -> None:
        """Sin resolucion, sus rutas solo pueden ser el cwd del motor.

        El cwd del motor es un workspace suyo, no el repo. Un script que no
        lee ni el entorno ni `user.dir` no tiene manera de saber donde esta
        el checkout, aunque no lleve ninguna ruta absoluta.
        """
        script = 'pipeline { stages { stage("x") { sh("ls pyproject.toml") } } }\n'
        informe = _informe(canonica=script)
        assert par.CODIGO_RUTA_ABSOLUTA in par.codigos_de(par.evaluar(informe))

    def test_la_raiz_todotavia_siendo_una_val_se_detecta(self) -> None:
        """El invariante no se puede esquivar cambiando de sintaxis.

        La primera version buscaba rutas absolutas DENTRO de `sh(...)`, y no
        veía nada cuando la ruta estaba en una `val` de Kotlin — que es
        justo donde se mueve uno para arreglar el problema. Un invariante
        que solo mira una sintaxis concreta se esquiva cambiando de
        sintaxis.
        """
        raiz = "/home/alguien/work/skillgraph"
        script = (
            f'val repo = System.getProperty("user.dir")\n'
            f'val cache = "{raiz}/.cache"\n'
            'pipeline { stages { stage("x") { sh("ls " + repo) } } }\n'
        )
        informe = _informe(canonica=script, raiz_repo=raiz)
        assert par.CODIGO_RUTA_ABSOLUTA in par.codigos_de(par.evaluar(informe))

    def test_una_raiz_ajena_no_es_deriva(self) -> None:
        """`/usr/bin/uv` no ata el script a ninguna maquina."""
        script = (
            'val repo = System.getProperty("user.dir")\n'
            'pipeline { stages { stage("x") { sh("/usr/bin/env true " + repo) } } }\n'
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


# --- C4: quien ejecuta pytest esta conectado a la receta canonica ---------
#
# Invariante anadido en WI-99, al mismo modulo y en el mismo fichero de tests
# a proposito: el guard es `check_ci_recipe_parity.py`, y duplicar su helper
# `_informe()` en un segundo fichero seria la forma de que los dos midieran
# cosas distintas sin que nada lo note. C1, C2, C3 y C4 son cuatro caras del
# mismo contrato: «la verificacion se hace una vez, con un solo instrumento».

#: El `scripts/ci.sh` de ANTES de WI-99: su propia receta. Es el contraejemplo
#: real, no uno inventado para el test.
SCRIPT_RECETA_SUYA = """#!/usr/bin/env bash
set -uo pipefail
uv run ruff format --check src tests
uv run ruff check src tests
uv run pytest --tb=short
"""

#: El `scripts/ci.sh` de DESPUES: delega, y solo ejecuta pytest en `--quick`,
#: que esta escrito como no certificante.
SCRIPT_DELEGA = """#!/usr/bin/env bash
set -uo pipefail
if [ "${1:-}" = "--quick" ]; then
    uv run pytest --tb=short
    exit 0
fi
mise exec -- pipelinek run --rerun \\
    --db .pipelinek/db.sqlite \\
    --control-root .pipelinek/control \\
    .pipeline.kts
exit $?
"""

#: Un fragmento de la receta: ejecuta pytest y la receta canónica lo invoca.
SCRIPT_FRAGMENTO = """#!/usr/bin/env bash
set -uo pipefail
uv run pytest -q --cov=skillgraph --cov-config="$RC"
"""


class TestC4UnaSolaReceta:
    def test_una_receta_que_se_hace_la_suya_se_detecta(self) -> None:
        """El fallo real de WI-99, con el fichero real como contraejemplo.

        No era imprecisión: `scripts/audit_bundle.sh` —que existe para dar
        evidencia reproducible a una auditoría independiente— llamaba a este
        script, así que la evidencia versionada se producía con un
        instrumento que no ve el CLI ejecutado por subproceso
        (`cli/commands/runs.py`: 39 % frente al 87,96 % de la instrumentada)
        y sin ejecutar ninguno de los cuatro contratos exigibles.
        """
        informe = _informe(scripts={"scripts/ci.sh": SCRIPT_RECETA_SUYA})
        problemas = par.evaluar(informe)
        assert par.CODIGO_RECETA_SUYA in par.codigos_de(problemas)
        assert "scripts/ci.sh" in " ".join(p.mensaje for p in problemas)

    def test_un_fragmento_de_la_receta_no_problema(self) -> None:
        """`scripts/coverage.sh` ejecuta pytest y NO delega: es correcto.

        La property es disyuntiva a proposito. Si exigieramos «nadie ejecuta
        pytest salvo `.pipeline.kts`», el propio archivo que produce la
        medición de cobertura seria una infraccion, y la unica salida seria
        una lista de excepciones que el guard mantiene — la trampa que este
        bloque ya cerro dos veces.
        """
        informe = _informe(
            scripts={"scripts/coverage.sh": SCRIPT_FRAGMENTO},
            fragmentos=frozenset({"scripts/coverage.sh"}),
        )
        assert par.CODIGO_RECETA_SUYA not in par.codigos_de(par.evaluar(informe))

    def test_un_script_que_delega_no_problema(self) -> None:
        """Delegar es la otra mitad de la property, y es la que se corrigio."""
        informe = _informe(scripts={"scripts/ci.sh": SCRIPT_DELEGA})
        assert par.CODIGO_RECETA_SUYA not in par.codigos_de(par.evaluar(informe))

    def test_pytest_solo_en_un_comentario_no_problema(self) -> None:
        """Un guard que busca una cadena no comprueba la propiedad.

        Es la misma trampa que C1 evita buscando pasos en vez de ficheros
        entero, aplicada al shell. Sin esto, un script que documenta «esto no
        es pytest, es documentación» pasaria por conforme.
        """
        script = "#!/usr/bin/env bash\n# no usamos pytest aqui, mire V-1\ntrue\n"
        informe = _informe(scripts={"scripts/verify.sh": script})
        assert par.CODIGO_RECETA_SUYA not in par.codigos_de(par.evaluar(informe))

    def test_una_delegacion_partida_en_varias_lineas_se_reconoce(self) -> None:
        """La invocación real está partida con barras invertidas.

        Es la forma que usa el propio `scripts/ci.sh`. Un invariante que
        buscara `pipelinek` y `.pipeline.kts` en la MISMA línea concluiría
        que ese script no delega, que es justo lo contrario de lo que hace:
        el defecto estaría en el invariante, no en el repo.
        """
        assert par.delega_en_canonica(SCRIPT_DELEGA)
        assert ".pipeline.kts" in " ".join(par.logicas_de(SCRIPT_DELEGA, "#"))

    def test_una_url_no_es_un_comentario(self) -> None:
        """`https://` lleva `//` dentro de una cadena.

        Si el parser partiera por el primer `//`, la linea de la receta
        canonica que documenta la instalación de mise se truncaría por la
        mitad y el invariante leería media orden. Y a la inversa: `#` en
        shell sí es comentario aunque la orden tenga una URL delante.
        """
        linea = "curl -sSf https://mise.run | sh # instalar"
        # Marca de Kotlin: el `//` de la URL no abre comentario, el `#` tampoco.
        assert par.logicas_de(linea, "//") == (linea,)
        # Marca de shell: el `#` abre comentario, la URL sigue intacta.
        assert par.logicas_de(linea, "#") == ("curl -sSf https://mise.run | sh",)

    def test_los_fragmentos_se_leen_de_la_receta_y_no_de_una_lista(self) -> None:
        """Si el guard llevara su propia lista, un fragmento nuevo sería invisible.

        Es la lección de C3 un nivel más abajo, y por eso `fragmentos` se
        rellena con `scripts_invocados_por(canonica)`.
        """
        assert par.scripts_invocados_por(CANONICA_PORTABLE) == frozenset({"scripts/coverage.sh"})
        canonica_real = PIPELINE.read_text(encoding="utf-8")
        assert "scripts/coverage.sh" in par.scripts_invocados_por(canonica_real)

    def test_un_contrato_python_no_es_un_fragmento_de_shell(self) -> None:
        """`scripts/check_coverage_floors.py` no es un script de shell.

        Contarlo como tal haría que un `checker.py` que algún día lanzara
        pytest pareciera un fragmento de la receta, cuando en realidad es
        una recipe propia disfrazada de contrato.
        """
        canonica = (
            'val repo = System.getProperty("user.dir")\n'
            'pipeline { stages { stage("x") { sh("cd " + repo + '
            '" && uv run python scripts/check_coverage_floors.py") } } }\n'
        )
        assert par.scripts_invocados_por(canonica) == frozenset()

    def test_un_script_nuevo_entra_en_el_contrato_sin_tocar_el_guard(self) -> None:
        """Se descubre por extensión, no por una lista de nombres."""
        informe = par.medir(ROOT)
        assert informe.hubo_error is False, informe.error
        assert "scripts/coverage.sh" in informe.scripts
        assert "scripts/ci.sh" in informe.scripts

    def test_la_exclusion_de_los_hooks_es_explicita_y_real(self) -> None:
        """`scripts/hooks/pre-push` ejecuta pytest a pelo y no entra en C4.

        Se comprueba que la exclusión EXISTE y que lo que excluye es
        exactamente lo que dice: si algún día `DIRECTORIOS_NO_RECETA`
        creciera para tapar `scripts/ci.sh`, este test seguiría verde y el
        guard no miraría nada. Fijar la exclusión es la forma de que dejar
        de ser un acuerdo.
        """
        informe = par.medir(ROOT)
        assert "scripts/hooks/pre-push" not in informe.scripts
        assert not any(s.startswith("scripts/hooks/") for s in informe.scripts)
        pre_push = ROOT / "scripts" / "hooks" / "pre-push"
        assert par.ejecuta_pytest(pre_push.read_text(encoding="utf-8"))
        assert par.DIRECTORIOS_NO_RECETA == ("scripts/hooks",)

    def test_el_contrato_real_no_tiene_problemas(self) -> None:
        """La prueba que importa: contra los ficheros de verdad."""
        informe = par.medir(ROOT)
        problemas = par.evaluar(informe)
        assert problemas == (), [p.mensaje for p in problemas]
