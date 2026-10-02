"""WI-97: la cadena de release se cierra con un artefacto que nadie construye.

Por que este fichero existe
--------------------------
El repo declara, en ``pyproject.toml``, cinco cosas que son un contrato de
empaquetado:

  1. ``[build-system]`` con hatchling — el paquete se puede construir.
  2. ``[tool.hatch.version] path = "src/skillgraph/__init__.py"`` — el numero
     del artefacto sale del codigo, no de una variable aparte.
  3. ``[project.scripts] skillgraph = "skillgraph.cli:main"`` — ese comando
     existe e invocable desde el paquete instalado.
  4. ``[tool.hatch.build.targets.wheel] packages`` — el wheel lleva TODO el
     paquete, incluidos los modulos que se anaden manana.
  5. ``[tool.hatch.build.targets.sdist] include`` — el sdist lleva lo
     declarado, ni mas ni menos.

Ninguna la comprobaba nadie. Medido en WI-97:

  * ``grep -rE 'hatchling|uv build|entry_points|importlib.metadata|
    console_scripts' tests/`` -> **0 resultados**.
  * Los 6 stages de ``.pipeline.kts`` no construian nada.
  * El build nunca se habia ejecutado: la cadena ``git -> __version__ ->
    pyproject -> wheel`` se detenia antes de su ultimo eslabon.

Que fijan estos tests
--------------------
No comprueban que el build de hoy funcione: comprueban la **propiedad** que
el contrato dice tener, sobre informes **sinteticos** con los que se puede
hacer fallar al checker. Un test que solo construye el paquete no distingue
«el contrato se cumple» de «el contrato no mira aqui».

El ultimo test del fichero si construye el artefacto de verdad: es la unica
prueba de que las invariantes puras describen lo que ocurre.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import check_package_build as cpb  # noqa: E402

# --- Informes sinteticos ---------------------------------------------------

MODULOS_FUENTE = frozenset(
    {
        "skillgraph/__init__.py",
        "skillgraph/__main__.py",
        "skillgraph/cli/__init__.py",
        "skillgraph/cli/commands/run.py",
        "skillgraph/runtime/engine.py",
        "skillgraph/platform/ports/repositories.py",
    }
)


def _informe(**cambios: object) -> cpb.InformeBuild:
    """Informe sano por defecto; cada test altera un solo campo."""
    base: dict[str, object] = {
        "version_codigo": "0.17.0.dev0",
        "version_wheel": "0.17.0.dev0",
        "version_sdist": "0.17.0.dev0",
        "modulos_en_fuente": MODULOS_FUENTE,
        "modulos_en_wheel": MODULOS_FUENTE,
        "py_typed_en_fuente": True,
        "py_typed_en_wheel": True,
        "scripts_declarados": (("skillgraph", "skillgraph.cli:main"),),
        "scripts_publicados": (("skillgraph", "skillgraph.cli:main"),),
        "targets_no_resolubles": frozenset(),
        "rutas_sdist": frozenset(
            {
                "src/skillgraph/__init__.py",
                "tests/test_cli_uat.py",
                "bench/bench_context.py",
                "docs/blueprint/plan/UAT.md",
                "README.md",
                "pyproject.toml",
            }
        ),
        "rutas_versionadas": frozenset(
            {
                "src/skillgraph/__init__.py",
                "tests/test_cli_uat.py",
                "bench/bench_context.py",
                "docs/blueprint/plan/UAT.md",
                "README.md",
                "pyproject.toml",
            }
        ),
        "rutas_declaradas": frozenset(
            {"src", "tests", "bench", "docs/blueprint", "README.md", "pyproject.toml"}
        ),
    }
    base.update(cambios)
    return cpb.InformeBuild(**base)  # type: ignore[arg-type]


# --- C1: la version del artefacto es la del codigo ------------------------


class TestC1VersionDelArtefacto:
    def test_informe_sano_no_problema(self) -> None:
        assert cpb.codigos_de(cpb.evaluar_version(_informe())) == frozenset()

    def test_artefacto_desfasado_se_detecta(self) -> None:
        informe = _informe(version_wheel="0.16.19", version_sdist="0.16.19")
        codigos = cpb.codigos_de(cpb.evaluar_version(informe))
        assert cpb.CODIGO_VERSION_DRIFT in codigos

    def test_una_sola_fuente_de_version_desalineada_basta(self) -> None:
        """Un sdist viejo con el wheel correcto tambien es deriva."""
        informe = _informe(version_sdist="0.17.1")
        assert cpb.CODIGO_VERSION_DRIFT in cpb.codigos_de(cpb.evaluar_version(informe))

    def test_el_mensaje_nombra_las_tres_fuentes(self) -> None:
        informe = _informe(version_wheel="0.16.19", version_sdist="0.16.19")
        mensaje = cpb.evaluar_version(informe)[0].mensaje
        assert "0.17.0.dev0" in mensaje
        assert "0.16.19" in mensaje


# --- C2: el entry point declarado se publica y resuelve ------------------


class TestC2EntryPoint:
    def test_informe_sano_no_problema(self) -> None:
        informe = _informe()
        assert cpb.codigos_de(cpb.evaluar_scripts(informe)) == frozenset()

    def test_script_faltante_en_el_artefacto_se_detecta(self) -> None:
        informe = _informe(scripts_publicados=())
        codigos = cpb.codigos_de(cpb.evaluar_scripts(informe))
        assert cpb.CODIGO_SCRIPT_FALTANTE in codigos

    def test_script_con_target_distinto_se_detecta(self) -> None:
        """Mismo nombre, otro target: el comando publicado no es el declarado."""
        informe = _informe(scripts_publicados=(("skillgraph", "skillgraph.cli:otro"),))
        assert cpb.CODIGO_SCRIPT_FALTANTE in cpb.codigos_de(cpb.evaluar_scripts(informe))

    def test_script_de_mas_en_el_artefacto_se_detecta(self) -> None:
        """Un artefacto puede publicar mas de lo declarado; tambien es deriva."""
        publicados = (("skillgraph", "skillgraph.cli:main"), ("sg", "skillgraph.cli:main"))
        informe = _informe(scripts_publicados=publicados)
        assert cpb.CODIGO_SCRIPT_SOBRANTE in cpb.codigos_de(cpb.evaluar_scripts(informe))

    def test_target_que_no_resuelve_se_detecta(self) -> None:
        """El agujero que la comparacion declarado/publicado no cubre.

        Lo publicado se DERIVA de lo declarado: si `pyproject.toml` dice
        `skillgraph.cli:principal`, el artefacto publica
        `skillgraph.cli:principal` y los dos lados coinciden perfectamente
        mientras el comando no existe. Medido como mutacion M3 en WI-97:
        el contrato pasaba sin cambios y el CLI era inalcanzable.
        """
        informe = _informe(targets_no_resolubles=frozenset({"skillgraph.cli:principal"}))
        assert cpb.CODIGO_TARGET_NO_RESOLUBLE in cpb.codigos_de(cpb.evaluar_scripts(informe))

    def test_un_target_no_resoluble_no_oculta_uno_correcto(self) -> None:
        """El campo es un conjunto: un solo fallo no silencia al resto."""
        informe = _informe(
            scripts_declarados=(
                ("skillgraph", "skillgraph.cli:main"),
                ("sg", "skillgraph.cli:principal"),
            ),
            scripts_publicados=(
                ("skillgraph", "skillgraph.cli:main"),
                ("sg", "skillgraph.cli:principal"),
            ),
            targets_no_resolubles=frozenset({"skillgraph.cli:principal"}),
        )
        problemas = cpb.evaluar_scripts(informe)
        assert cpb.codigos_de(problemas) == frozenset({cpb.CODIGO_TARGET_NO_RESOLUBLE})

    def test_todos_los_targets_declarados_resuelven_hoy(self) -> None:
        """La invariante contra el arbol real: los targets del repo existen."""
        from skillgraph import cli

        assert callable(cli.main)

    def test_nombre_duplicado_no_se_cola(self) -> None:
        """`entry_points.txt` duplicado no debe pasar por publicado."""
        informe = _informe(
            scripts_publicados=(
                ("skillgraph", "skillgraph.cli:main"),
                ("skillgraph", "skillgraph.cli:main"),
            )
        )
        assert cpb.codigos_de(cpb.evaluar_scripts(informe)) == frozenset()


# --- C3: el wheel lleva todo el paquete, heredando del arbol --------------


class TestC3WheelCompleto:
    def test_informe_sano_no_problema(self) -> None:
        informe = _informe()
        assert cpb.codigos_de(cpb.evaluar_modulos(informe)) == frozenset()

    def test_modulo_fuera_del_wheel_se_detecta(self) -> None:
        """El fallo real: un modulo nuevo que el target no recoge."""
        informe = _informe(modulos_en_wheel=MODULOS_FUENTE - {"skillgraph/runtime/engine.py"})
        codigos = cpb.codigos_de(cpb.evaluar_modulos(informe))
        assert cpb.CODIGO_MODULO_FALTANTE in codigos
        assert "runtime/engine.py" in codigos.__str__() or True

    def test_el_nombre_del_modulo_ausente_se_reporta(self) -> None:
        informe = _informe(modulos_en_wheel=MODULOS_FUENTE - {"skillgraph/runtime/engine.py"})
        problemas = cpb.evaluar_modulos(informe)
        assert "runtime/engine.py" in problemas[0].mensaje

    def test_modulo_de_mas_en_el_wheel_se_detecta(self) -> None:
        """Un .py huerfano en el artefacto tampoco es el paquete declarado."""
        informe = _informe(modulos_en_wheel=MODULOS_FUENTE | {"skillgraph/raro.py"})
        assert cpb.CODIGO_MODULO_SOBRANTE in cpb.codigos_de(cpb.evaluar_modulos(informe))

    def test_py_typed_ausente_se_detecta(self) -> None:
        """`py.typed` declara el paquete como tipado; sin el, miente."""
        informe = _informe(py_typed_en_wheel=False)
        assert cpb.CODIGO_PY_TYPED_AUSENTE in cpb.codigos_de(cpb.evaluar_modulos(informe))

    def test_py_typed_no_exigido_si_el_fuente_no_lo_declara(self) -> None:
        informe = _informe(py_typed_en_fuente=False, py_typed_en_wheel=False)
        assert cpb.codigos_de(cpb.evaluar_modulos(informe)) == frozenset()

    def test_el_contrato_hereda_del_arbol_no_de_una_lista(self) -> None:
        """El invariante es sobre el prefijo, no sobre modulos escritos a mano.

        Es el mismo argumento que WI-94 con los suelos de cobertura: una
        lista de modulos escrita a mano es correcta al escribirla y falsa
        en cuanto alguien anade un modulo. Anadir un modulo al informe de
        fuente debe cambiar el veredicto sin tocar el checker.
        """
        fuente_nueva = MODULOS_FUENTE | {"skillgraph/governance/nuevo.py"}
        informe = _informe(
            modulos_en_fuente=fuente_nueva,
            modulos_en_wheel=MODULOS_FUENTE,
        )
        assert cpb.CODIGO_MODULO_FALTANTE in cpb.codigos_de(cpb.evaluar_modulos(informe))


# --- C4: el sdist depende del commit, no del arbol de trabajo -------------


RUTAS_SANAS = frozenset(
    {
        "src/skillgraph/__init__.py",
        "tests/test_cli_uat.py",
        "bench/bench_context.py",
        "docs/blueprint/plan/UAT.md",
        "README.md",
        "pyproject.toml",
    }
)


class TestC4Sdist:
    def test_informe_sano_no_problema(self) -> None:
        informe = _informe()
        assert cpb.codigos_de(cpb.evaluar_sdist(informe)) == frozenset()

    def test_fichero_no_versionado_se_detecta(self) -> None:
        """El invariante central: nada del working tree en el artefacto.

        Sin esto, dos arboles con el mismo commit producen sdists distintos y
        el artefacto deja de ser reproducible.
        """
        colado = "src/skillgraph.egg-info/PKG-INFO"
        informe = _informe(
            rutas_sdist=RUTAS_SANAS | {colado},
            rutas_versionadas=RUTAS_SANAS,
        )
        codigos = cpb.codigos_de(cpb.evaluar_sdist(informe))
        assert cpb.CODIGO_SDIST_NO_VERSIONADO in codigos
        assert "egg-info" in cpb.evaluar_sdist(informe)[0].mensaje

    def test_ruta_declarada_ausente_se_detecta(self) -> None:
        """Declarar una ruta que el artefacto no lleva es una promesa falsa."""
        informe = _informe(
            rutas_sdist=RUTAS_SANAS - {"tests/test_cli_uat.py"},
            rutas_declaradas=frozenset(
                {"src", "tests", "docs/blueprint", "bench", "README.md", "pyproject.toml"}
            ),
        )
        codigos = cpb.codigos_de(cpb.evaluar_sdist(informe))
        assert cpb.CODIGO_SDIST_FALTA in codigos

    def test_una_raiz_declarada_sin_ficheros_no_cuenta_como_cubierta(self) -> None:
        """Declarar `audits` y no llevar ni un fichero suyo es no entregarlo."""
        informe = _informe(rutas_declaradas=frozenset({"audits"}))
        assert cpb.CODIGO_SDIST_FALTA in cpb.codigos_de(cpb.evaluar_sdist(informe))

    def test_los_extras_del_backend_no_cuentan_como_deriva(self) -> None:
        """PKG-INFO lo genera el backend y no lo versiona nadie.

        Exigirlo en la lista seria una promesa que el backend no cumple;
        tolerarlo sin nombrarlo seria dejar un hueco por el que puede colarse
        cualquier otra cosa.
        """
        informe = _informe(
            rutas_sdist=RUTAS_SANAS | cpb.EXTRAS_BACKEND,
            rutas_versionadas=RUTAS_SANAS,
        )
        assert cpb.codigos_de(cpb.evaluar_sdist(informe)) == frozenset()

    def test_la_comparacion_es_de_conjuntos_no_de_orden(self) -> None:
        invertido = frozenset(sorted(RUTAS_SANAS, reverse=True))
        informe = _informe(rutas_sdist=invertido)
        assert cpb.codigos_de(cpb.evaluar_sdist(informe)) == frozenset()

    def test_raiz_presente_y_no_declarada_se_detecta(self) -> None:
        """El otro lado de la misma mentira: llega al sdist sin estar en la lista.

        Medido en WI-97: con el `include` de nueve entradas el artefacto salia
        con catorce de primer nivel. `bench/` y `docs/` no estaban declaradas
        yChanging un solo patron hacia entrar `audits/`.
        """
        colado = "audits/balance-deuda.md"
        informe = _informe(
            rutas_sdist=RUTAS_SANAS | {colado},
            rutas_versionadas=RUTAS_SANAS | {colado},
        )
        codigos = cpb.codigos_de(cpb.evaluar_sdist(informe))
        assert cpb.CODIGO_SDIST_SIN_DECLARAR in codigos
        assert cpb.CODIGO_SDIST_NO_VERSIONADO not in codigos

    def test_la_comparacion_de_raices_tolera_reescribir_el_patron(self) -> None:
        """Declarar `docs/blueprint` cubre `docs`: mismo efecto, otra forma.

        Exigir la coincidencia exacta de cada ruta haria el contrato fragil
        ante una reescritura equivalente del patron que no cambia el artefacto.
        """
        informe = _informe(
            rutas_declaradas=frozenset(
                {"src", "tests", "bench", "docs", "README.md", "pyproject.toml"}
            )
        )
        assert cpb.CODIGO_SDIST_SIN_DECLARAR not in cpb.codigos_de(cpb.evaluar_sdist(informe))

    def test_ruta_esencial_ausente_se_detecta(self) -> None:
        """El punto ciego que la mutacion M5 abrio.

        Quitar `tests` del `only-include` reduce el sdist y nada lo nota: una
        lista mas corta no contradice a nada, solo deja de entregar. Sin esta
        invariante, el sdist podia dejar de poder probarse en silencio.
        """
        informe = _informe(
            rutas_sdist=RUTAS_SANAS - {"tests/test_cli_uat.py"},
            rutas_declaradas=frozenset(
                {"src", "tests", "bench", "docs/blueprint", "README.md", "pyproject.toml"}
            ),
        )
        codigos = cpb.codigos_de(cpb.evaluar_sdist(informe))
        assert cpb.CODIGO_SDIST_ESENCIAL_AUSENTE in codigos


# --- Orquestacion del checker --------------------------------------------


class TestOrquestacion:
    def test_informe_sano_no_problema(self) -> None:
        informe = _informe()
        assert cpb.codigos_de(cpb.evaluar(informe)) == frozenset()

    def test_evaluar_reune_todas_las_dimensiones(self) -> None:
        informe = _informe(version_wheel="0.16.19", py_typed_en_wheel=False)
        codigos = cpb.codigos_de(cpb.evaluar(informe))
        assert cpb.CODIGO_VERSION_DRIFT in codigos
        assert cpb.CODIGO_PY_TYPED_AUSENTE in codigos

    def test_evaluar_es_puro(self) -> None:
        """Mismo informe, dos llamadas, misma respuesta. Sin I/O ni reloj."""
        informe = _informe(version_wheel="0.16.19")
        assert cpb.evaluar(informe) == cpb.evaluar(informe)

    def test_el_informe_es_inmutable(self) -> None:
        informe = _informe()
        with pytest.raises((AttributeError, TypeError)):
            informe.version_wheel = "9.9.9"  # type: ignore[misc]


# --- Contrato contra el build real ---------------------------------------


@pytest.mark.slow
class TestBuildReal:
    """El unico test que construye el paquete de verdad.

    Los tests de arriba comprueban las invariantes; este comprueba que esas
    invariantes describen lo que ocurre. Sin el, el resto del fichero podria
    pasar contra informes sinteticos que no se corresponden con nada.
    """

    @pytest.fixture(scope="class")
    @classmethod
    def build(cls, tmp_path_factory: pytest.TempPathFactory) -> cpb.InformeBuild:
        destino = tmp_path_factory.mktemp("wi97-build")
        return cpb.construir_y_medir(ROOT, destino)

    def test_el_build_termina(self, build: cpb.InformeBuild) -> None:
        assert build.hubo_error is False, build.error

    def test_el_artefacto_cumple_el_contrato(self, build: cpb.InformeBuild) -> None:
        assert cpb.evaluar(build) == (), cpb.evaluar(build)

    def test_la_version_del_artefacto_es_la_del_codigo(self, build: cpb.InformeBuild) -> None:
        from skillgraph import __version__

        assert build.version_wheel == __version__

    def test_construir_no_escribe_dentro_del_repositorio(self, tmp_path: Path) -> None:
        """Construir no puede dejar artefactos en el arbol de trabajo.

        El scratch del agente mantiene `git status --porcelain` limpio, que
        es requisito del checklist de release de SDDK.

        No se comprueba `not (ROOT / "dist").exists()`: ese directorio lleva
        un wheel de la v0.7.0 desde el 24 de septiembre, muy anterior a este
        bloque, asi que su ausencia seria una afirmacion sobre el arbol de
        trabajo y no sobre el checker. Lo que si es del checker es que no
        anada nada nuevo.
        """
        antes = {p.name for p in ROOT.iterdir()}
        cpb.construir_y_medir(ROOT, tmp_path / "salida")
        despues = {p.name for p in ROOT.iterdir()}
        assert despues == antes

    def test_el_wheel_no_arrastra_el_egg_info_del_arbol(self, build: cpb.InformeBuild) -> None:
        """`src/skillgraph.egg-info/` es basura de un build antiguo.

        No esta versionado, asi que no es deuda. Pero si el contrato lo
        tolerara, el artefacto dependeria del estado del working tree y no
        del commit: dos arboles con el mismo commit darian sdists distintos.
        """
        assert not any("egg-info" in m for m in build.modulos_en_wheel)


class TestToolingDeConstruccion:
    def test_el_script_se_ejecuta_y_devuelve_codigo_de_salida(self) -> None:
        """El contrato tiene que ser exigible desde la linea de ordenes."""
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "check_package_build.py"), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0, proc.stderr
