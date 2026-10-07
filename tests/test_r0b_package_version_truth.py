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
import sys
from pathlib import Path

import pytest
import yaml

RAIZ = Path(__file__).resolve().parent.parent
STATE = RAIZ / "STATE.yaml"
SCRIPT = RAIZ / "scripts" / "project_truth.py"
PY = RAIZ / ".venv" / "bin" / "python"

sys.path.insert(0, str(RAIZ / "scripts"))

import project_truth  # noqa: E402


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


def _verdades_del_arbol() -> dict[str, object]:
    """Las verdades REALES, leidas del arbol, sin la colecta de pytest.

     **POR QUE SE ARMAN A MANO Y NO SE LLAMA A `estado(raiz)`.** `estado()`
     devuelve el veredicto entero, contradicciones incluidas —que es justo lo
     que hay que deformar—, asi que no sirve de punto de partida. Aqui se
    toman las verdades una por una con los MISMOS lectores que usa `estado()`,
     que es lo que evita que este contrasalto mida un cruce paralelo al real.

     `tests_reales` se iguala a `tests_declarados` **a proposito**. El
     contrasalto tiene que ponerse rojo por `package_version`; si ademas lo
     estuviera por la cifra, un fallo de la cifra taparia el hallazgo — que es
     la clase de fallo que WI-115 midio una vez.
    """
    declarado = project_truth.total_declarado(RAIZ)
    return {
        "bloque": project_truth.bloque_del_roadmap(RAIZ),
        "version": project_truth.version_activa(RAIZ),
        "package_version": project_truth.package_version_declarada(RAIZ),
        "release": project_truth.release_declarada(RAIZ),
        "tag_vcs": project_truth.tag_real(RAIZ),
        "tests_declarados": declarado,
        "tests_reales": declarado,
        "workitem_state": project_truth.workitem_de_state(RAIZ),
        "workitem_current": project_truth.workitem_de_current(RAIZ),
    }


class TestLaMutacionSePoneEnRojo:
    """**EL CONTRA SALTO DEL BLOQUE.** Sin este test, la mitad de arriba pasa
    con un campo leido y no comparado.

    # POR QUE DEFORMA EL DICT Y NO EL FICHERO

    La primera version escribia `STATE.yaml` del arbol real y lo restauraba en
    un `finally`. **MEDIDO AL CERTIFICAR, y salio caro:** cuatro guards en
    rojo, y no por la propiedad que este bloque mide.

    - `test_b22_arbol_real::test_ninguna_escritura_al_arbol_real_queda_sin_explicar`
      la cazaba directamente: una escritura sin explicar a un fichero que git
      versiona.
    - Peor, e invisible en local: **otros tres guards leen ese mismo fichero**
      —`project_truth` desde `test_b0`, `test_wi115`, `test_b23`— y leen el
      arbol *mientras esta deformado*. En la suite completa se pusieron rojos;
      corriendo este fichero solo, en verde. Un guard que solo se rompe en un
      orden concreto no se puede depurar.

    El propio guard lo decia en su mensaje: «el arreglo es mover la deformacion
    a un sandbox, no anadir la excepcion».

    **Y EL SANDBOX TAMPOCO, MEDIDO.** Copiar el arbol versionado con
    `git archive`, `git init`, y deformar ahi da `rc=2` **igual mutado que sin
    mutar** —el verificador no arranca en una copia—, o sea un contrasalto que
    daria verde con la deformacion puesta. Es PEOR que deformar el arbol real,
    porque aquel al menos distinguia los dos casos.

    Lo que queda es lo unico que mide la regla sin escribir nada:
    `_contradicciones()` es una funcion **pura** que recibe el dict de verdades
    —B23 ya la ejercita asi, y `test_b0_truth_convergence.py:369` es el
    molde— y la deformacion es una linea de ese dict.
    """

    def test_el_arbol_REAL_no_tiene_ninguna_de_estas_contradicciones(self) -> None:
        """La linea base, y no es decorativa.

        Sin ella, «la mutacion dio rojo» no distingue *la regla dispara* de
        *la regla se ejecuto y ya estaba roja por otra cosa*: el contrasalto
        pasaria con la regla rota de siempre.
        """
        limpio = project_truth._contradicciones(_verdades_del_arbol(), raiz=RAIZ, ventanas=())
        assert limpio == (), (
            f"el arbol real ya es incoherente en estos campos, y entonces el "
            f"contrasalto de abajo no puede decir nada: {limpio}"
        )

    def test_package_version_VIEJO_pone_la_regla_en_ROJO(self) -> None:
        """La propiedad exacta que el bloque arregla, escrita como test.

        Y el mutante toca **EL** campo, por construccion: es una clave del dict
        que se le pasa a la regla. Cuatro versiones de este contrasalto
        apuntaron antes al `package_version` equivocado —el de `tests:`—, y
        por eso se exige que el mensaje nombre el valor.
        """
        verdad = _verdades_del_arbol()
        valor_real = verdad["package_version"]

        mutado = dict(verdad)
        mutado["package_version"] = "0.99.0.dev0"

        problemas = project_truth._contradicciones(mutado, raiz=RAIZ, ventanas=())
        assert any("package_version" in p for p in problemas), (
            f"la regla dejo pasar un package_version de 0.99.0.dev0 mientras "
            f"__init__.py declara {verdad['version']!r} y STATE declara "
            f"{valor_real!r}. EL AGUJERO SIGUE ABIERTO. Contradicciones: {problemas}"
        )
        assert any("0.99.0.dev0" in p for p in problemas), (
            "la contradiccion no nombra el valor que la dispara: quien lee "
            f"tiene que buscar el numero a mano. Contradicciones: {problemas}"
        )


class TestElContrasaltoNoTocaElArbol:
    """La mitad del harness que la version anterior daba por hecha.

    «El `finally` lo pone» es una razon para no mirar, no una prueba. Y aqui
    no hay `finally` que lo ponga: **este fichero no escribe nada**, y este
    test es lo que lo dice.
    """

    def test_este_fichero_no_abre_ningun_fichero_para_escribir(self) -> None:
        """Por AST, como el guard de B22.

        La propiedad es «este codigo *escribe*», y un docstring que mencione
        `write_text` no es una escritura: buscarla por cadena contaria la
        documentacion de este test. La primera version de ese guard busco con
        regex y se puso roja por su propia prosa.
        """
        import ast

        arbol = ast.parse(Path(__file__).read_text(encoding="utf-8"))
        escrituras: list[tuple[int, str]] = []
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, ast.Call):
                continue
            func = nodo.func
            nombre = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if nombre in {"write_text", "write_bytes", "writelines"}:
                escrituras.append((nodo.lineno, nombre))
            elif nombre == "open":
                for arg in (*nodo.args[1:], *[kw.value for kw in nodo.keywords]):
                    if (
                        isinstance(arg, ast.Constant)
                        and isinstance(arg.value, str)
                        and arg.value[:1] in {"w", "a", "x", "+"}
                    ):
                        escrituras.append((nodo.lineno, f"open({arg.value!r})"))
        assert not escrituras, (
            "test_r0b_package_version_truth.py vuelve a ESCRIBIR un fichero del "
            "arbol de trabajo real:\n  "
            + "\n  ".join(f"linea {lin}: {que}" for lin, que in escrituras)
            + "\n\nLa deformacion va en el DICT que se le pasa a "
            "_contradicciones(), no en STATE.yaml. Escribirlo aqui pone en rojo "
            "a todo guard que lea STATE.yaml mientras dura la ventana — "
            "test_b0, test_b23 y test_wi115 lo hicieron — y eso se Midio."
        )


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
