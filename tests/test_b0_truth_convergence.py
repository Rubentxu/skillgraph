"""B0 — el gate: una sola verdad del proyecto, y que no vuelva a romperse.

`AGENTS.md` declara cinco cosas sobre el propio repositorio que tienen que
ser ciertas **a la vez**: la version activa, la release emitida, la cifra de
tests, el bloque de trabajo vivo y el roadmap. Antes de B0 se mediron y
resultaron contradictorias entre si, con dos workitems de diferencia entre
`STATE.yaml` y `CURRENT.md` y una cifra de tests que ya habia roto una
certificacion entera en WI-109.

Este fichero no *resume* esas cinco verdades: las **cruza**. Y el cruce no
esta escrito aqui, esta en `scripts/project_truth.py`, que es la respuesta
machine-readable unica a «¿donde esta el proyecto y que toca despues?».

**POR QUE EL GUARD USA EL SCRIPT Y NO REIMPLEMENTA EL CRUCE.** Un guard que
calcula lo mismo por su cuenta tiene dos copias de la misma regla, y se
divergen el dia que una se actualiza y la otra no: el guard pasa en verde
midiendo algo que ya no es lo que el proyecto responde. Es el error de
WI-106 aplicado a una comparacion. Este fichero ejecuta el unico cruce que
existe y verifica su veredicto.

**LO QUE ESTE GUARD NO COMPRUEBA, declarado y no disimulado.** Que la prosa
de `CURRENT.md` describa bien el bloque. `project_truth.py` comprueba que
`CURRENT.md` **nombra** el bloque vivo, no que lo describa con acierto: esa
es la misma frontera que declaro WI-104 con las citas, y ensancharla hacia
la prosa seria inventarse un problema.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
SCRIPT = RAIZ / "scripts" / "project_truth.py"

sys.path.insert(0, str(RAIZ / "scripts"))

import project_truth  # noqa: E402


def _ejecuta() -> tuple[int, dict]:
    """Corre el script como lo correria un humano, y devuelve su veredicto.

    Se ejecuta como **subproceso** y no llamando a `main()` en proceso: lo
    que se vigila es el contrato de salida —el JSON y el codigo— que es lo
    que CI y una persona consumen. Si el guard llamara a `main()` y le
    leyera el `dict`, estaria verificando la funcion interna y no la
    respuesta, que es justo lo que el gate de B0 promete.
    """
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        return proc.returncode, json.loads(proc.stdout)
    except json.JSONDecodeError as exc:  # pragma: no cover - ver abajo
        pytest.fail(
            "project_truth.py no emitio JSON legible. La respuesta unica a "
            "'¿donde esta el proyecto?' tiene que ser machine-readable; si "
            f"el script imprimio otra cosa, o rompe el contrato:\n{proc.stdout[-500:]}\n"
            f"stderr:\n{proc.stderr[-300:]}\n"
            f"JSONDecodeError: {exc}"
        )


class TestLaVerdadEsUnica:
    """El gate. Lo que B0 prometio, comprobado sobre el arbol de hoy."""

    def test_el_proyecto_no_se_contradice_a_si_mismo(self) -> None:
        """La propiedad del gate, tal cual: las cinco, a la vez.

        El mensaje nombra CADA contradiccion con sus dos caras, porque un
        verificador que dice «falso» sin decir «cual era la verdad» deja a
        quien corrige haciendo la cuenta a mano, que es el trabajo que el
        guard existe para evitar.
        """
        codigo, carga = _ejecuta()
        assert carga.get("coherente") is True, (
            "el proyecto se contradice a si mismo:\n"
            + "\n".join(f"  - {c}" for c in carga.get("contradicciones", []))
            + "\n\nUna contradiccion se arregla en su dueno, no aqui: "
            "`scripts/project_truth.py` nombra cual es el campo y el valor "
            "de cada lado."
        )
        assert codigo == 0, (
            f"coherente y aun asi sale {codigo}: el codigo de salida es el veredicto"
        )

    def test_la_respuesta_sale_completa_y_no_vacia(self) -> None:
        """Lo que se compara contra algo tiene que existir.

        Sin esto, un `project_truth.py` que devolviera todos los campos a
        `None` y ninguna contradiccion pasaria el test de arriba en verde:
        no habria nada que comparar y nada que fallar. Es el contrasalto
        del cero silencioso, aqui sobre el JSON en vez de sobre pytest.
        """
        _, carga = _ejecuta()
        for campo in (
            "bloque",
            "objetivo",
            "version",
            "release",
            "tests_declarados",
            "tests_reales",
            "workitem_state",
            "workitem_current",
            "roadmap",
        ):
            valor = carga.get(campo)
            assert valor not in (None, ""), f"la respuesta no trae `{campo}`: {carga}"
        assert carga["tests_declarados"] > 0, "tests declarados en cero o negativo"
        assert carga["tests_reales"] > 0, "tests reales en cero o negativo"

    def test_el_roadmap_de_la_raiz_es_el_que_se_consulta(self) -> None:
        """Que la respuesta apunte al roadmap, y no a un documento historico.

        Sin este contrasalto, un `project_truth.py` que leyera
        `docs/blueprint/plan/ROADMAP.md` —el roadmap del blueprint v1— seria
        indistinguible de uno correcto: los dos devuelven texto. Este test
        ata la respuesta al fichero que B0 declara autoridad unica.
        """
        _, carga = _ejecuta()
        assert carga["roadmap"] == "ROADMAP.md"
        assert (RAIZ / carga["roadmap"]).is_file()

    def test_el_bloque_vivo_esta_entre_los_diez_del_roadmap(self) -> None:
        """Que el bloque nombrado sea uno real del mapa, no una etiqueta al azar.

        `B0`..`B9` se leen del propio `ROADMAP.md` por AST-ish: se busca
        la tabla. Asi el conjunto sale del roadmap y no de una lista
        escrita aqui —que seria la fuente de verdad que hay que mantener a
        mano, la trampa de `DIRECTORIAS_NO_RECETA` en WI-99.
        """
        texto = (RAIZ / "ROADMAP.md").read_text(encoding="utf-8")
        declarados = {
            linea.split("**")[1]
            for linea in texto.splitlines()
            if linea.startswith("| **B") and "**" in linea
        }
        assert declarados, "la tabla del mapa no declara ningun bloque B*"
        _, carga = _ejecuta()
        assert carga["bloque"] in declarados, (
            f"la respuesta dice que el bloque vivo es {carga['bloque']}, que "
            f"no esta en la tabla del roadmap ({sorted(declarados)})"
        )

    def test_no_hay_una_segunda_autoridad_del_roadmap(self) -> None:
        """Que el roadmap que NO es de la raiz diga que no lo es.

        `docs/blueprint/plan/ROADMAP.md` es el roadmap del blueprint v1 y
        durante años se leyo como si fuera el del proyecto vivo. Moverlo
        habria roto las citas de la evidencia historica —que es
        provenance—, asi que se degrada **en su sitio**: tiene que
        declararse historico en su propia primera linea.

        El criterio es una declaracion de estado de historico, no la
        ausencia de la palabra «roadmap»: el fichero se llama ROADMAP.md
        y no va a dejar de llamarse asi.
        """
        cabecera = (RAIZ / "docs" / "blueprint" / "plan" / "ROADMAP.md").read_text(
            encoding="utf-8"
        )[:2000]
        assert "HIST" in cabecera.upper(), (
            "docs/blueprint/plan/ROADMAP.md vuelve a leerse como el roadmap "
            "del proyecto. Es el roadmap del blueprint v1, ya terminado: "
            "tiene que declarar que es historico en su primera linea."
        )
        assert "ROADMAP.md" in cabecera, (
            "el roadmap historico tiene que senalar cual es el vivo, o el "
            "lector se queda con dos y sin saber cual"
        )


class TestLaRespuestaSePuedeRomper:
    """Contrasaltos: un guard que solo sabe pasar no esta probado.

    Cada test degrada UNA verdad del script, en memoria, y exige que el
    cruce la note. Sin esto, una comparacion que dejara de ejecutarse
    pasaria en verde con la misma autoridad que una que funciona.
    """

    def test_una_cifra_de_tests_falsa_se_ve(self) -> None:
        """La propiedad de WI-115, vista desde el otro lado.

        Se llama a `_contradicciones` con las cifras intercambiadas. Si el
        cruce no mirase `tests`, devolveria la lista vacia y este test
        pasaria sin haber medido nada.
        """
        base = {
            "bloque": "B0",
            "version": "0.22.5.dev0",
            "release": "0.22.5",
            "tag_vcs": "0.22.5",
            "tests_declarados": 2844,
            "tests_reales": 2844,
            "workitem_state": "B0",
            "workitem_current": "B0",
        }
        limpio = project_truth._contradicciones(base)
        assert limpio == (), f"la base deberia ser coherente, dio: {limpio}"

        base["tests_declarados"] = 9999
        problemas = project_truth._contradicciones(base)
        assert problemas, "una cifra de tests que miente paso sin decir nada"
        assert any("9999" in p and "2844" in p for p in problemas), (
            f"la contradiccion no nombra las DOS cifras: {problemas}"
        )

    def test_un_workitem_desalineado_se_ve(self) -> None:
        """La desincronizacion que se midio al abrir B0, sin internet.

        `STATE.yaml` decia WI-96 y `CURRENT.md` decia WI-115, diecinueve
        workitems de diferencia, y nada lo notaba. El cruce tiene que
        nombrarlos a los dos.
        """
        base = {
            "bloque": "B0",
            "version": "0.22.5.dev0",
            "release": "0.22.5",
            "tag_vcs": "0.22.5",
            "tests_declarados": 2844,
            "tests_reales": 2844,
            "workitem_state": "WI-96",
            "workitem_current": "WI-115",
        }
        problemas = project_truth._contradicciones(base)
        assert any("WI-96" in p and "WI-115" in p for p in problemas), (
            f"una desalineacion de workitem paso sin decir nada: {problemas}"
        )

    def test_un_tag_que_no_es_el_declarado_se_ve(self) -> None:
        """La release declarada y el tag del VCS tienen que ser el mismo.

        `release.tag` describe la ultima release **real**; si el VCS dice
        otra cosa, una de las dos miente sobre lo que se aprovisiona.
        """
        base = {
            "bloque": "B0",
            "version": "0.22.5.dev0",
            "release": "0.22.5",
            "tag_vcs": "0.23.0",
            "tests_declarados": 2844,
            "tests_reales": 2844,
            "workitem_state": "B0",
            "workitem_current": "B0",
        }
        problemas = project_truth._contradicciones(base)
        assert any("0.22.5" in p and "0.23.0" in p for p in problemas), (
            f"una release que no coincide con el tag paso sin decir nada: {problemas}"
        )

    def test_una_version_que_no_deriva_del_tag_se_ve(self) -> None:
        """`__version__` tiene que ser `<tag>.dev0` entre releases.

        Sin esta regla, `__version__` podria quedar clavada en el numero de
        una release ya publicada y el paquete construido se publicaria
        otra vez con la misma version.
        """
        base = {
            "bloque": "B0",
            "version": "0.22.5",
            "release": "0.22.5",
            "tag_vcs": "0.22.5",
            "tests_declarados": 2844,
            "tests_reales": 2844,
            "workitem_state": "B0",
            "workitem_current": "B0",
        }
        problemas = project_truth._contradicciones(base)
        assert any("version" in p for p in problemas), (
            f"una version que no deriva del tag paso sin decir nada: {problemas}"
        )


class TestLaRespuestaNoSeFabrica:
    """Que la respuesta venga del arbol, y no de una copia del test.

    Esta clase existe porque un guard que compara contra si mismo es el
    error de WI-106, y porque aqui la copia seria facilisima de escribir:
    basta con poner en el test los numeros de hoy y comparar contra ellos.
    """

    def test_las_lecturas_vienen_del_arbol(self) -> None:
        """Cada verdad se lee del fichero que la posee, y se comprueba.

        No se compara el valor con una constante escrita aqui: se verifica
        que la funcion de lectura devuelve exactamente lo que hay en el
        fichero. Si alguien cambiara la verdad sin cambiar el lector, este
        test lo veria.
        """
        assert (
            project_truth.version_activa()
            == project_truth._lee("src/skillgraph/__init__.py")
            .split('__version__ = "')[1]
            .split('"')[0]
        )
        assert (
            project_truth.bloque_del_roadmap()
            == project_truth._lee("ROADMAP.md").split("Bloque vivo: **")[1].split("**")[0]
        )
        assert project_truth.workitem_de_state() in project_truth._lee("STATE.yaml")

    def test_una_verdad_ilegible_es_un_fallo_y_no_un_verde(self) -> None:
        """El modo de fallo que WI-115 dio un contrasalto y aqui se cierra.

        Si una verdad no se puede leer, el script tiene que **decirlo**, no
        devolver un estado vacio que pareceria sano. Se comprueba sobre el
        tipo, no sobre el arbol real: un repo sin `ROADMAP.md` no es el
        caso que se quiere cazar aqui, es el caso de B0 entero.
        """
        assert issubclass(project_truth.VerdadNoLegible, RuntimeError)
        with pytest.raises(project_truth.VerdadNoLegible):
            project_truth._lee("no/existe/este/fichero.md")

    def test_el_codigo_de_salida_distingue_medir_de_contradecirse(self) -> None:
        """Tres veredictos, no dos.

        0 coherente · 1 contradiccion · 2 no se pudo medir. El tercero
        existe porque un instrumento roto que devuelve 0 es indistinguible
        de un instrumento roto que devuelve «todo bien»: es el error 32
        de WI-113, la sonda que apuntaba a un texto que ya no existia y se
        contaba como victoria.
        """
        codigo, carga = _ejecuta()
        assert codigo in (0, 1, 2), f"codigo de salida inesperado: {codigo}"
        if codigo == 2:
            assert "ilegible" in carga, "el fallo de medicion tiene que decir QUE no pudo leer"
        if codigo == 1:
            assert carga.get("contradicciones"), "salir con 1 sin nombrar contradiccion"
        if codigo == 0:
            assert carga.get("coherente") is True
