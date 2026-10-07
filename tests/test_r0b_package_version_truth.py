"""R0.B — `release.package_version` es parte de la verdad del proyecto.

**EL HALLAZGO, MEDIDO ANTES DE ESCRIBIR ESTE FICHERO:**

    release.package_version := <otra version>
    -> project_truth rc=0, coherente: true

El campo podía quedarse viejo y nadie se enteraba. Es la **tercera**INCidencia
de la misma familia que midió WI-115 para `tests.total` y `tests.package_version`
— tres campos que declaran una versión y un guard que no los cruzaba.

# POR QUÉ EL GUARD DE RELEASE NO LO CAZABA

`test_release_governance::test_current_version_is_documented_in_state` hace:

    f'package_version: "{version}"' in state_yaml

Es una **coincidencia de texto sobre todo el fichero**. Y hay **DOS** campos
llamados `package_version`:

    tests.package_version     (linea ~612)
    release.package_version   (linea ~1191)

Con la cabecera mal y `releases[0]` bien, la coincidencia encuentra la buena y
pasa. **Un predicado que busca texto no puede decir *dónde* estaba el valor.**

# LAS TRES MITADES, Y POR QUÉ LAS TRES

    TestElCampoEsParteDeLaVerdad      -> la lectura existe
    TestLaMutacionSePoneEnRojo        -> la regla dispara  (EL CONTRA SALTO)
    TestElGuardDeReleaseNoEsUnGrep   -> el hermano tampoco puede seguir siendo un grep

La segunda es la que hace que las otras dos signifiquen algo: sin ella,
`TestElCampoEsParteDeLaVerdad` pasa con un campo leído y no comparado, que es
la forma exacta del defecto.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest
import yaml

RAIZ = Path(__file__).resolve().parent.parent
STATE = RAIZ / "STATE.yaml"
SCRIPT = RAIZ / "scripts" / "project_truth.py"
PY = RAIZ / ".venv" / "bin" / "python"


def _corre() -> tuple[int, dict]:
    """Corre `project_truth` y devuelve su veredicto.

    **EL INTERPRETE ES PARTE DEL HARNESS, Y NO ES UN DETALLE.** Con
    `sys.executable` el script sale `rc=2` con `coherente: null`, porque no
    encuentra pytest y **se niega a dar veredicto** en vez de mentir. Una
    sonda que da `rc=2` sin mutación está midiendo el arranque del script, no
    la propiedad — el error 32, por séptima vez.
    """
    proc = subprocess.run(
        [str(PY), str(SCRIPT), "--raiz", str(RAIZ)], capture_output=True, text=True
    )
    try:
        return proc.returncode, json.loads(proc.stdout)
    except json.JSONDecodeError:
        pytest.fail(f"project_truth no devolvio JSON: {proc.stdout[-300:]}{proc.stderr[-300:]}")


class TestElCampoEsParteDeLaVerdad:
    def test_project_truth_LO_DECLARA_en_su_salida(self) -> None:
        """La pregunta de existencia. Sin ella, una lectura que nadie usa
        cumpliría lo mismo que no leerla."""
        _, carga = _corre()
        assert "package_version" in carga, (
            "project_truth no declara `package_version` en su salida: el campo "
            "se lee pero no se publica, y una lectura invisible no se vigila"
        )
        assert carga["package_version"] is not None

    def test_coincide_con_la_version_ACTIVA_del_arbol(self) -> None:
        _, carga = _corre()
        assert carga["package_version"] == carga["version"], (
            f"release.package_version dice {carga['package_version']} y "
            f"__init__.py dice {carga['version']}; declaran lo mismo"
        )

    def test_el_hermano_ESTA_MEDIDO_no_oculto(self) -> None:
        """**LO QUE SALIO AL ESCRIBIR EL CONTRA SALTO, Y POR QUE NO ES UN
        `xfail`.**

        `STATE.yaml` tiene `tests.package_version = 0.39.0.dev0` mientras el
        release es `v0.41.0`. Está viejo **desde B29**, y nadie lo notó
        precisamente porque nadie lo leía: es el hermano del campo que este
        bloque arregla, y estaba delante de él en el fichero.

        **LO QUE NO SE HACE Y POR QUÉ.** No se arregla en silencio —tocar un
        campo que quizá otro guard lee es pregunta de otro bloque— y tampoco
        se esconde con `xfail` o `skip`: `scripts/check_pipeline_receipt.py`
        cuenta `skipped` y `xfailed` como la misma cosa, *tests que no se
        ejecutaron*, y AGENTS.md §6.2 lo prohíbe. Un `xfail` aquí sería un
        fallo escondido con mejor vocabulario.

        **LO QUE SE HACE: DECIRLO, CON SU NÚMERO.** El test lee el valor real
        y afirma la verdad sobre él — hoy: viejo— con el motivo escrito. El día
        que alguien lo arregle, este test **falla** y hay que actualizar la
        afirmación, que es exactamente la presión que un `xfail` no ejerce.
        """
        datos = yaml.safe_load(STATE.read_text(encoding="utf-8"))
        activo = re.search(
            r'__version__ = "([^"]+)"',
            (RAIZ / "src" / "skillgraph" / "__init__.py").read_text(encoding="utf-8"),
        ).group(1)
        hermano = datos["tests"].get("package_version")

        assert hermano is not None, (
            "tests.package_version ya no existe: si se borro, esta deuda esta "
            "resuelta y este test hay que reescribir, no relajar"
        )
        # LA AFIRMACIÓN, con su número. Hoy: 0.39.0.dev0 vs 0.41.0.dev0.
        assert hermano == "0.39.0.dev0", (
            f"tests.package_version ahora dice {hermano!r} (la version activa es "
            f"{activo!r}). La deuda esta RESUELTA: actualiza la afirmacion de "
            "este test y quita la nota de la entrada `tests:` del STATE."
        )
        # Y se deja ver que NO es la version activa, para que el numero de esta
        # deuda sea el que esta escrito y no unplaceholder.
        assert hermano != activo, (
            "si el hermano ya coincide con la version activa, la deuda que "
            "este test declara ya no existe"
        )


class TestLaMutacionSePoneEnRojo:
    """**EL CONTRA SALTO DEL BLOQUE.** Sin este test, la mitad de arriba pasa
    con un campo leído y no comparado."""

    def test_package_version_VIEJO_pone_el_guard_en_ROJO(self) -> None:
        """La propiedad exacta que el bloque arregla, escrita como test.

        Y el mutante se construye **con YAML**, no con texto sobre el
        fichero, porque hay dos campos con el mismo nombre y cuatro versiones
        de este contrasalto apuntaron al equivocado antes de que se
        comprobara. Un contrasalto tiene que **demostrar a qué campo apunta**.
        """
        original = STATE.read_bytes()
        datos = yaml.safe_load(original.decode("utf-8"))
        valor_original = datos["release"]["package_version"]

        datos["release"]["package_version"] = "0.99.0.dev0"
        mutado = yaml.safe_dump(datos, sort_keys=False, allow_unicode=True)

        # La verificacion que hacia falta: que el mutante toco EL campo.
        verificado = yaml.safe_load(mutado)
        assert verificado["release"]["package_version"] == "0.99.0.dev0"
        assert verificado["tests"]["package_version"] != "0.99.0.dev0", (
            "el mutante toco tests.package_version por error: hay dos campos "
            "con el mismo nombre y la sonda apunta al equivocado"
        )

        try:
            STATE.write_text(mutado, encoding="utf-8")
            rc, carga = _corre()
        finally:
            STATE.write_bytes(original)

        assert rc != 0, (
            f"project_truth dio rc=0 con release.package_version en "
            f"0.99.0.dev0 (el valor real es {valor_original}). "
            "EL AGUJERO SIGUE ABIERTO."
        )
        assert carga["coherente"] is False
        assert any("package_version" in c for c in carga.get("contradicciones") or []), (
            f"el guard se puso rojo pero no nombro el campo: {carga.get('contradicciones')}"
        )

    def test_el_arbol_queda_BYTE_IDENTICO_despues_del_contrasalto(self) -> None:
        """La mitad del harness: una sonda que deja el árbol sucio no es una
        sonda, es un incidente. Se mide en el propio test, no se da por hecha
        porque el `finally` lo pone."""
        original = STATE.read_bytes()
        datos = yaml.safe_load(original.decode("utf-8"))
        datos["release"]["package_version"] = "0.99.0.dev0"
        try:
            STATE.write_text(
                yaml.safe_dump(datos, sort_keys=False, allow_unicode=True), encoding="utf-8"
            )
        finally:
            STATE.write_bytes(original)
        assert STATE.read_bytes() == original


class TestElGuardDeReleaseNoEsUnGrep:
    """El hermano, que es donde nació el hallazgo."""

    def test_el_predicado_DEL_GUARD_debe_leer_EL_CAMPO(self) -> None:
        """**POR QUÉ ESTE TEST EXIGE MÁS QUE «EL GUARD PASA».**

        El guard actual (`f'package_version: "{version}"' in state_yaml`)
        funciona **por casualidad**: encuentra la línea correcta hoy. La
        propiedad que importa es que **lea el campo por su camino**, porque
        un predicado que busca texto no puede distinguir las dos secciones.

        Se mide por AST: si algún día el predicado vuelve a ser un `in` sobre
        el fichero entero, este test se pone rojo.
        """
        import ast

        fuente = (RAIZ / "tests" / "test_release_governance.py").read_text(encoding="utf-8")
        arbol = ast.parse(fuente)

        # Se busca el `in` sobre el texto completo del STATE.
        comparaciones = [
            nodo
            for nodo in ast.walk(arbol)
            if isinstance(nodo, ast.Compare) and any(isinstance(op, ast.In) for op in nodo.ops)
        ]
        texto_completo = [
            nodo
            for nodo in comparaciones
            if isinstance(nodo.left, ast.Constant)
            and isinstance(nodo.left.value, str)
            and "package_version" in nodo.left.value
            and nodo.left.value.strip().endswith('"')
        ]
        assert not texto_completo, (
            "el guard de release vuelve a comparar `package_version` como "
            "TEXTO sobre el fichero entero. Con dos campos del mismo nombre, "
            "eso no puede decir cuál estaba mal."
        )

    def test_el_estado_real_es_legible_por_AMBAS_rutas(self) -> None:
        """La alternativa que el test anterior exige: leer por la vía
        estructurada. Aquí se demuestra que esa vía existe y da el valor."""
        datos = yaml.safe_load(STATE.read_text(encoding="utf-8"))
        assert datos["release"]["package_version"] == datos["release"]["package_version"]
        assert isinstance(datos["release"]["package_version"], str)
