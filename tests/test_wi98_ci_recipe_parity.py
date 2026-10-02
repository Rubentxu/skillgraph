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

    def test_los_hooks_ya_no_necesitan_exclusion(self) -> None:
        """La puerta trasera de WI-99 está cerrada: `DIRECTORIOS_NO_RECETA` no existe.

        En WI-99 el pre-push ejecutaba `pytest` a pelo con el instrumento
        ciego —`cli/support.py` al 69 %, por debajo del suelo del 70 % que
        declara el propio `AGENTS.md`— y la salida fue excluir `scripts/hooks/`
        por constante, con un test que fijaba la exclusión para que no
        creciera en silencio.

        WI-100 cierra las dos cosas. El pre-push delega en `scripts/ci.sh`, y
        el pre-commit filtra por `$STAGED_PY` en vez de correr el repo
        entero. Ninguno de los dos necesita una excepción, así que la
        constante desaparece: una propiedad que hay que mantener al día no
        es una propiedad, es una suscripción.
        """
        assert not hasattr(par, "DIRECTORIOS_NO_RECETA"), (
            "DIRECTORIOS_NO_RECETA vuelve a existir. Si hace falta para cubrir "
            "un caso, el caso no cumple C4 y hay que arreglar el script, no "
            "la lista"
        )

    def test_los_hooks_entran_en_el_contrato_por_shebang(self) -> None:
        """Descubrir por extensión no basta: los hooks no tienen extensión.

        Los dos se llaman `pre-commit` y `pre-push` porque es como git los
        busca. MEDIDO en WI-100: con `rglob("*.sh")` el invariante daba
        verde sin haber mirado nunca esos dos ficheros — y ya había pasado
        al inventariarlos en WI-99. Un guard que solo descubre una sintaxis
        no vigila la otra.
        """
        informe = par.medir(ROOT)
        assert "scripts/hooks/pre-push" in informe.scripts
        assert "scripts/hooks/pre-commit" in informe.scripts

    def test_el_pre_push_cumple_por_delegar_y_el_pre_commit_por_filtrar(self) -> None:
        """Las dos salidas de C4, y ninguna es una excepcion.

        El pre-push no ejecuta pytest: pide la receta. El pre-commit ejecuta
        pytest pero sobre lo que alguien tiene a medio escribir, que es un
        filtro de evento y no un veredicto sobre el repo.
        """
        informe = par.medir(ROOT)
        assert informe.hubo_error is False, informe.error
        pre_push = informe.scripts["scripts/hooks/pre-push"]
        pre_commit = informe.scripts["scripts/hooks/pre-commit"]
        assert not par.ejecuta_pytest(pre_push), "el pre-push ejecuta pytest"
        assert "scripts/ci.sh" in par.rutas_de_script(pre_push, "#")
        assert par.ejecuta_pytest(pre_commit)
        assert par.filtra_por_ficheros(pre_commit), (
            "el pre-commit dejo de filtrar y vuelve a ser un veredicto con "
            "el instrumento equivocado"
        )
        assert par.CODIGO_RECETA_SUYA not in par.codigos_de(par.evaluar(informe))

    def test_un_path_literal_no_es_una_variable_de_paths(self) -> None:
        """Las dos formas de filtrar, y las dos se measen.

        La primera version de `filtra_por_ficheros` solo reconocia paths que
        acababan en `.py`, y por eso era CIEGA a la forma que usa de verdad
        `scripts/hooks/pre-commit`: `pytest -q $STAGED_PY`. El hook filtraba
        y el invariante no lo veia — un invariante ciego que da verde es peor
        que uno que no existe, porque ocupa el sitio del que habria avisado.
        """
        assert par.filtra_por_ficheros("run pytest -q $STAGED_PY")
        assert par.filtra_por_ficheros('run pytest -q "$STAGED_PY"')
        assert par.filtra_por_ficheros("run pytest -q tests/test_wi98_ci_recipe_parity.py")

    def test_el_valor_de_una_opcion_no_es_un_path(self) -> None:
        """La opposite: un invariante que se cumple siempre no vigila nada.

        `--cov=skillgraph` y `--cov-config="$RC"` contienen un token con `$`
        y otro con letras. Si contaran como paths, TODA invocacion de pytest
        pareceria filtrada y C4 se vaciaria de contenido sin que nadie lo
        notara. Este test es el que impide que eso pase por unnoticed.
        """
        assert not par.filtra_por_ficheros('uv run pytest -q --cov=skillgraph --cov-config="$RC"')
        assert not par.filtra_por_ficheros("mise exec -- uv run pytest --tb=short")
        assert not par.filtra_por_ficheros('python -m pytest -q -k "nombre"')
        assert not par.filtra_por_ficheros("run pytest -q -p no:cacheprovider")

    def test_un_mensaje_no_es_una_invocacion(self) -> None:
        """El falso positivo que encontro una MUTACION, no un test.

        C4 llevaba dos commits dando verde porque el pre-commit tenia una
        linea de diagnostico:

            echo "[pre-commit] smoke: pytest sobre $N_STAGED fichero(s) .py"

        y esa linea tenia las tres cosas que el invariante miraba: la
        palabra `pytest`, una variable que parece un path, y estaba en una
        orden ejecutable. Por eso el pre-commit que corria la suite entera
        se creia conforme.

        Lo encontro la mutacion M7, que degrada el hook a su forma
        anterior: el contrato seguia verde. Un guard que confunde un
        MENSAJE con una EJECUCION no mide que corre: mide que se dice.
        """
        mensaje = 'echo "[pre-commit] smoke: pytest sobre $N_STAGED fichero(s) .py staged"'
        assert par.filtra_por_ficheros(mensaje) is False
        assert par.filtra_por_ficheros('tail -30 "$_log" | grep pytest') is False
        assert par.filtra_por_ficheros("printf '%s' pytest") is False
        # Y lo que de verdad se ejecuta sigue funcionando:
        assert par.filtra_por_ficheros("if run_in_toolchain run pytest -q $STAGED_PY; then")

    def test_un_directorio_tambien_selecciona(self) -> None:
        """`pytest src/` es tan filtrado como `pytest tests/test_x.py`.

        Reconocer solo los ficheros `.py` haria que un directorio se
        contara como suite entera — y el falso verde seria el opuesto del
        que se quiere vigilar.
        """
        assert par.filtra_por_ficheros("python3 -m pytest -q src/")
        assert par.filtra_por_ficheros("uv run pytest -q scripts/check_ci_recipe_parity.py")
        assert not par.filtra_por_ficheros("uv run pytest -q --cov=skillgraph")

    def test_un_script_se_reconoce_por_extension_o_por_shebang(self) -> None:
        """Las dos vias del descubrimiento, porque hay ficheros sin extension.

        `scripts/hooks/pre-commit` se llama asi porque git lo busca asi. Con
        descubrimiento solo por extension, el invariante daba verde sin
        haberlo mirado nunca.
        """
        assert par.es_script_shell("x", ".sh")
        assert par.es_script_shell("x", ".bash")
        assert par.es_script_shell("#!/usr/bin/env sh\necho hola\n", "")
        assert par.es_script_shell("#!/bin/bash\necho hola\n", "")
        assert not par.es_script_shell("import os\n", ".py")
        assert not par.es_script_shell("", "")

    def test_el_contrato_real_no_tiene_problemas(self) -> None:
        """La prueba que importa: contra los ficheros de verdad."""
        informe = par.medir(ROOT)
        problemas = par.evaluar(informe)
        assert problemas == (), [p.mensaje for p in problemas]


# --- C5: la receta canonica CONTIENE los contratos, no solo los llama ------
#
# Invariante anadido en WI-102, al mismo modulo y al mismo fichero.
#
# MEDIDO en WI-102, con el comando canonico de verdad: se borro el bloque
# entero de la etapa `coverage-floors` de `.pipeline.kts` —la que impone los
# suelos que AGENTS.md 6.3 declara exigibles— y:
#
#   scripts/check_ci_recipe_parity.py   exit 0   («OK: ...»)
#   pytest test_wi98_ci_recipe_parity    37 passed
#   la receta, ejecutada de verdad       Pipeline finished with SUCCESS
#   menciones de 'coverage-floors'       0
#   menciones de 'VEREDICTO'             0
#
# C3 leia las etapas del script — bien hecho, es lo que evita un guard que
# vigila su propia lista— pero solo comprobaba que la lista sea LEGIBLE. Una
# lista de etapas vacia por legibilidad es tan valida como una completa, y
# una receta que ejecuta menos se ejecuta igual de bien.
#
# La forma es deliberadamente sin lista: el conjunto sale del repo
# (`scripts/check_*.py`), no de una constante. Ver la nota sobre el
# descubrimiento en `evaluar_contratos_de_la_receta`.


class TestC5LaRecetaContieneLosContratos:
    def test_un_checker_sin_enchufar_se_detecta(self) -> None:
        """El fallo medido: la etapa existe como fichero y no se ejecuta.

        C4 exigia que quien ejecuta pytest este conectado a la receta. Nadie
        exigia que la receta CONTENGA los contratos, y esa diferencia es
        justo el hueco: una etapa borrada deja de ejecutar su checker, y el
        checker es lo unico que se nota.
        """
        informe = _informe(
            checkers=("scripts/check_coverage_floors.py",),
            checkers_invocados=frozenset(),
        )
        problemas = par.evaluar(informe)
        assert par.CODIGO_CONTRATO_HUERFANO in par.codigos_de(problemas)
        assert "scripts/check_coverage_floors.py" in " ".join(p.mensaje for p in problemas)

    def test_un_checker_enchufar_no_problema(self) -> None:
        informe = _informe(
            checkers=("scripts/check_coverage_floors.py",),
            checkers_invocados=frozenset({"scripts/check_coverage_floors.py"}),
        )
        assert par.CODIGO_CONTRATO_HUERFANO not in par.codigos_de(par.evaluar(informe))

    def test_varios_sin_enchufar_se_dicen_todos(self) -> None:
        """Un guard que dice «falta un contrato» sin decir cual es un guard
        que obliga a abrir el fichero para enterarse de cual."""
        informe = _informe(
            checkers=(
                "scripts/check_coverage_floors.py",
                "scripts/check_package_build.py",
                "scripts/check_ci_recipe_parity.py",
            ),
            checkers_invocados=frozenset({"scripts/check_package_build.py"}),
        )
        problemas = par.evaluar(informe)
        assert par.CODIGO_CONTRATO_HUERFANO in par.codigos_de(problemas)
        mensaje = " ".join(p.mensaje for p in problemas)
        assert "scripts/check_coverage_floors.py" in mensaje
        assert "scripts/check_ci_recipe_parity.py" in mensaje

    def test_sin_checkers_no_hay_quejanza(self) -> None:
        """Un repo sin checkers no incumple nada: el invariante no inventa."""
        informe = _informe(checkers=(), checkers_invocados=frozenset())
        assert par.CODIGO_CONTRATO_HUERFANO not in par.codigos_de(par.evaluar(informe))


class TestC5ElLectorDeInvocaciones:
    """El lector tiene que distinguir una orden de una mención.

    Es la misma trampa que M7 de WI-100 (un `echo` de diagnostico conto como
    invocacion durante dos commits) y que M8 de WI-101 (`--verify` en un
    comentario). Un guard que busca el nombre del checker en el fichero
    entero daria verde con la etapa borrada y el nombre en un comentario
    explicativo, que es exactamente como se documenta una etapa que ya no
    esta.
    """

    def test_una_orden_real_se_reconoce(self) -> None:
        texto = (
            'val repo = System.getenv("GITHUB_WORKSPACE")\n'
            "pipeline {\n  stages {\n"
            '    stage("coverage-floors") {\n'
            '      sh("cd " + repo + " && uv run python scripts/check_coverage_floors.py")\n'
            "    }\n  }\n}\n"
        )
        assert "scripts/check_coverage_floors.py" in par.checkers_invocados_por(texto)

    def test_una_mencion_en_comentario_no_cuenta(self) -> None:
        texto = (
            'val repo = System.getenv("GITHUB_WORKSPACE")\n'
            "pipeline {\n  stages {\n"
            '    stage("lint") { sh("cd " + repo + " && uv run ruff check src tests") }\n'
            "    // La etapa coverage-floors invoca scripts/check_coverage_floors.py.\n"
            "  }\n}\n"
        )
        assert par.checkers_invocados_por(texto) == frozenset()

    def test_una_orden_partida_por_barra_inversa_se_reconoce(self) -> None:
        """La invocacion real esta partida en varias lineas. Un lector que
        solo mira linea a linea no la ve — y daria verde con el checker
        enchufado, que es el falso verde opuesto."""
        texto = (
            "pipeline {\n  stages {\n"
            '    stage("coverage-floors") {\n'
            '      sh("cd " + repo + \\\n'
            '         " && uv run python scripts/check_coverage_floors.py")\n'
            "    }\n  }\n}\n"
        )
        assert "scripts/check_coverage_floors.py" in par.checkers_invocados_por(texto)

    def test_un_checker_en_un_subdirectorio_se_reconoce(self) -> None:
        """El descubrimiento y el lector tienen que ver lo MISMO.

        `checkers_de` usa `rglob`, asi que un checker en
        `scripts/sub/check_x.py` entra en el conjunto de contratos. Un lector
        que no aceptara carpetas entre `scripts/` y `check_` lo dejaria
        huerfano para siempre, siendo un contrato que la receta ejecuta: un
        falso positivo que se propaga como si fuera verdad.

        MEDIDO en WI-102. La primera version de la regex no admitia el
        subdirectorio, y lo destapo una lectura, no un test.
        """
        texto = (
            "pipeline {\n  stages {\n"
            '    stage("contratos") {\n'
            '      sh("cd " + repo + " && uv run python scripts/sub/check_nuevo.py")\n'
            "    }\n  }\n}\n"
        )
        assert "scripts/sub/check_nuevo.py" in par.checkers_invocados_por(texto)

    def test_descubrimiento_y_lector_coinciden_en_un_repo_real(self, tmp_path: Path) -> None:
        """Compone las dos mitades —un checker de verdad, invocado de verdad—
        y exige que el evaluador no diga nada.

        Es la forma de que un cambio en cualquiera de las dos se note aqui y
        no cuando alguien meta un checker en un subdirectorio.
        """
        scripts = tmp_path / "scripts"
        (scripts / "sub").mkdir(parents=True)
        (scripts / "check_raiz.py").write_text("x", encoding="utf-8")
        (scripts / "sub" / "check_anidado.py").write_text("x", encoding="utf-8")
        texto = (
            "pipeline {\n  stages {\n"
            '    stage("c") {\n'
            '      sh("cd " + repo + " && uv run python scripts/check_raiz.py")\n'
            '      sh("cd " + repo + " && uv run python scripts/sub/check_anidado.py")\n'
            "    }\n  }\n}\n"
        )
        informe = par.InformeRunners(
            receta_canonica=".pipeline.kts",
            canonica=texto,
            raiz_repo=str(tmp_path),
            runners={},
            etapas_canonicas=par.etapas_de(texto),
            checkers=par.checkers_de(tmp_path),
            checkers_invocados=par.checkers_invocados_por(texto),
        )
        assert informe.checkers == (
            "scripts/check_raiz.py",
            "scripts/sub/check_anidado.py",
        )
        assert par.evaluar_contratos_de_la_receta(informe) == ()


class TestC5ElDescubrimiento:
    def test_un_checker_nuevo_entra_sin_tocar_el_guard(self, tmp_path: Path) -> None:
        """La forma es sin lista: un checker nuevo se vigila el dia que se
        escribe, no el dia que alguien se acuerde de anadirlo a la lista.

        Es el caso inverso al de WI-99, y hoy es invisible: escribir un
        checker nuevo y no enchufarlo en la receta deja un guard que no
        guarda nada, con la misma forma exacta que un guard real.
        """
        scripts = tmp_path / "scripts"
        scripts.mkdir()
        (scripts / "check_coverage_floors.py").write_text("x", encoding="utf-8")
        nuevo = scripts / "check_un_contrato_nuevo.py"
        nuevo.write_text("x", encoding="utf-8")

        assert par.checkers_de(tmp_path) == (
            "scripts/check_coverage_floors.py",
            "scripts/check_un_contrato_nuevo.py",
        )

    def test_un_fichero_que_no_es_checker_no_entra(self, tmp_path: Path) -> None:
        """La convencion es `check_*.py`, y es una convencion declarada.

        Un `helpers.py` en `scripts/` no es un contrato exigible por el
        nombre que tiene, y meterlo en el invariante obligaria a enchufa-
        rlo en la receta, que es lo que hace inutil el invariante cuando
        se ensancha con cosas que no son contratos.
        """
        scripts = tmp_path / "scripts"
        scripts.mkdir()
        (scripts / "checkers.py").write_text("x", encoding="utf-8")
        (scripts / "helpers.py").write_text("x", encoding="utf-8")
        (scripts / "check_uno.sh").write_text("x", encoding="utf-8")
        assert par.checkers_de(tmp_path) == ()


class TestC5ContraElRepoReal:
    def test_todo_checker_del_repo_lo_invoca_la_receta(self) -> None:
        """La afirmación del bloque, contra los ficheros de verdad.

        `TestFicherosReales::test_el_contrato_real_no_tiene_problemas` ya
        pasa por aqui, pero este test dice la propiedad en voz alta y falla
        con el nombre del checker huerfano, en vez de con un codigo.
        """
        informe = par.medir(ROOT)
        huerfanos = [c for c in informe.checkers if c not in informe.checkers_invocados]
        assert informe.checkers, "no se ha descubierto ningun checker: el invariante no vigila nada"
        assert not huerfanos, f"la receta canonica no ejecuta: {huerfanos}"
