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

import ast
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
SCRIPT = RAIZ / "scripts" / "project_truth.py"

sys.path.insert(0, str(RAIZ / "scripts"))

import project_truth  # noqa: E402

#: Las cinco verdades y el fichero del que sale cada una. Se copian tal cual
#: al sandbox del contraargumento: el JSON de la rama ilegible tiene que salir
#: de verdad, no de una carga escrita aqui, porque un guard que compara contra
#: su propia copia es el error de WI-106 aplicado a un test.
LOS_FICHEROS_DE_LA_VERDAD = (
    "STATE.yaml",
    "ROADMAP.md",
    "CURRENT.md",
    "src/skillgraph/__init__.py",
)


def _ilegible(carga: dict) -> str | None:
    """La causa de la respuesta ilegible, o `None` si la respuesta es normal.

    `main()` tiene DOS salidas y las dos son JSON valido. La de `Estado` trae
    `bloque`; la de `VerdadNoLegible` trae `coherente: false` e `ilegible`, y
    ninguna de las cinco verdades. Son dos contratos, no uno con un campo a
    veces ausente: por eso se distinguen por la clave que las separa y no por
    un `if not carga.get(...)` que las trataria igual.
    """
    if "ilegible" not in carga:
        return None
    return str(carga["ilegible"])


def _mensaje_de_instrumento(causa: str) -> str:
    """El fallo de un guard de este fichero cuando el instrumento no pudo leer.

    MEDIDO en B20-2: la respuesta ilegible es un JSON valido SIN `bloque`, y
    este fichero hacia `carga["bloque"]` directamente. Resultado: un
    `KeyError: 'bloque'` —que dice QUE fallo y no POR QUE— en el test que
    precisamente existe para explicar por que el proyecto no esta bien. La
    causa estaba a mano, en la misma carga, en la clave `ilegible`.

    Y el peor sitio para perderla es este: la rama ilegible sale cuando una
    de las cinco verdades esta rota, y entonces el guard se ejecuta precisamente
    cuando su explicacion es lo unico que hay.
    """
    return (
        "project_truth.py NO PUDO LEER una de las cinco verdades, asi que no "
        "emitio respuesta. Esto no es «el proyecto se contradice» —eso sale "
        "con `coherente: false` y la lista de contradicciones—: es el "
        "instrumento el que fallo, y la causa dice cual de las cinco:\n"
        f"  {causa}\n\n"
        "Se arregla en el fichero que nombra arriba, no aqui. Si sale "
        "`no se pudo leer <fichero>`, ese fichero no existe o no se puede "
        "abrir; si sale sobre el recuento, pytest no pudo colectar."
    )


def _sandbox_roto(destino: Path) -> Path:
    """Un arbol donde `__init__.py` existe pero ya no declara `__version__`.

    Se copia el arbol MINIMO que el script lee, con el propio script dentro,
    para que su `RAIZ` —que se deriva de `__file__`— sea el sandbox y no el
    repositorio. Un clon entero haria la prueba lenta y, sobre todo, haria que
    un fallo de la prueba se confunda con un fallo del repo.
    """
    for relativo in LOS_FICHEROS_DE_LA_VERDAD:
        destino_fichero = destino / relativo
        destino_fichero.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(RAIZ / relativo, destino_fichero)
    (destino / "scripts").mkdir(parents=True, exist_ok=True)
    shutil.copy2(SCRIPT, destino / "scripts" / SCRIPT.name)
    (destino / "src" / "skillgraph" / "__init__.py").write_text(
        "# el fichero existe pero ya no declara la version\n", encoding="utf-8"
    )
    return destino


def _respuesta_de(sandbox: Path) -> tuple[int, dict]:
    """La respuesta REAL del script, ejecutada en el sandbox."""
    proc = subprocess.run(
        [sys.executable, str(sandbox / "scripts" / SCRIPT.name)],
        cwd=sandbox,
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode, json.loads(proc.stdout)


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
        carga = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:  # pragma: no cover - ver abajo
        pytest.fail(
            "project_truth.py no emitio JSON legible. La respuesta unica a "
            "'¿donde esta el proyecto?' tiene que ser machine-readable; si "
            f"el script imprimio otra cosa, o rompe el contrato:\n{proc.stdout[-500:]}\n"
            f"stderr:\n{proc.stderr[-300:]}\n"
            f"JSONDecodeError: {exc}"
        )
    ilegi = _ilegible(carga)
    if ilegi is not None:
        pytest.fail(_mensaje_de_instrumento(ilegi))
    return proc.returncode, carga


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


class TestLaVerdadIlegibleSeDice:
    """La segunda forma de la respuesta, que hasta B20-2 nadie miraba.

    `main()` no tiene una salida, tiene DOS, y las dos salen como JSON
    valido. La segunda —`ilegible`— es la que aparece cuando una verdad esta
    rota, o sea justo cuando el guard tiene algo que decir.

    Estos tests no reimplementan la rama: **ejecutan el script de verdad** en
    un arbol donde una verdad esta rota, y comprueban que la respuesta llega
    con la causa puesta y que el guard la nombra en vez de reventar.
    """

    def test_la_rama_ilegible_sale_de_verdad_y_trae_la_causa(self) -> None:
        """Que exista la rama, con su forma propia y su causa dentro.

        Sin esto, un `project_truth.py` que dejara de tener segunda salida
        pasaria todos los tests de este fichero: la respuesta normal trae
        `bloque` y no menciona `ilegible` nunca.
        """
        with tempfile.TemporaryDirectory(prefix="b0_ilegible_") as tmp:
            rc, carga = _respuesta_de(_sandbox_roto(Path(tmp)))

        assert rc == 2, f"una verdad ilegible tiene que salir con 2, dio {rc}"
        assert carga.get("coherente") is False, (
            "una verdad ilegible NO es una verdad sana con un campo a menos: "
            f"la respuesta fue {carga}"
        )
        assert "bloque" not in carga, (
            "la rama ilegible no puede fingir tener las cinco verdades: si "
            f"trajera `bloque`, seria indistinguible de la sana. Trae: {carga}"
        )

    def test_el_guard_nombra_la_causa_y_no_revienta(self) -> None:
        """La propiedad, tal cual: el fallo dice POR QUE, no solo QUE.

        Este es el test que faltaba. Antes de B20-2 el guard hacia
        `carga["bloque"]` sobre esta respuesta y salia un `KeyError: 'bloque'`:
        el test que existe para explicar el problema era el que no lo
        explicaba.
        """
        with tempfile.TemporaryDirectory(prefix="b0_ilegible_") as tmp:
            _, carga = _respuesta_de(_sandbox_roto(Path(tmp)))

        # Se pasa por la MISMA politica que usa `_ejecuta`, no por una copia:
        # si la politica dejara de mirar `ilegible`, esto pasaria en verde.
        causa = _ilegible(carga)
        assert causa is not None, f"la respuesta ilegible no trae la causa: {carga}"
        assert "__version__" in causa, (
            "la causa no dice QUE verdad se rompio, y sin eso quien corrige "
            f"tiene que abrir el script a adivinar. Decia: {causa!r}"
        )

    def test_el_mensaje_distingue_instrumento_de_proyecto(self) -> None:
        """Que se separen las DOS formas de estar mal, en el mensaje.

        Un unico mensaje para las dos convertiria «tu repositorio esta mal» y
        «mi instrumento no pudo leer tu repositorio» en la misma frase, que es
        el error de B19 con otro envoltorio: una accion que se deduce de un
        veredicto que no distingue de quien es el problema.
        """
        ilegi = "src/skillgraph/__init__.py no declara __version__"
        mensaje = _mensaje_de_instrumento(ilegi)

        assert ilegi in mensaje, "el mensaje no repite la causa que le pasan"
        assert "NO PUDO LEER" in mensaje, (
            "el mensaje no dice que es un fallo del instrumento, luego el "
            "lector lo toma como un fallo del proyecto"
        )
        assert "contradiccion" in mensaje.lower(), (
            "el mensaje tiene que decir por que NO es lo otro: sin eso, quien "
            "lea tiene que adivinar si hay que arreglar el repo o el guard"
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
        problemas = project_truth._contradicciones(base, head_en_la_etiqueta=False)
        assert any("version" in p for p in problemas), (
            f"una version que no deriva del tag paso sin decir nada: {problemas}"
        )

    def test_con_head_en_la_etiqueta_el_semver_puro_no_es_contradiccion(self) -> None:
        """La otra mitad del caso, y la que B6 hizo hacer falta.

        MEDIDO al liberar v0.26.0: este guard exigia SIEMPRE
        `<tag>.dev0`, y `test_release_governance.py` exigia el SemVer PURO
        cuando HEAD esta en la etiqueta. Los dos son del repo y los dos se
        ejecutan, luego el estado «HEAD en el tag con la version publica»
        era INALCANZABLE por construccion — ninguna version satisfacia a
        los dos guards a la vez.

        Se corrigio la REGLA de este guard, no la del otro: el de release
        ya distinguia los tres casos (en etiqueta / posterior / sin
        etiqueta) y este lo habia simplificado. Corregir el mas simple
        era lo que hacia; cambiar el mas preciso habria sido tirar
        information real para salir del paso.

        Y el parametro se expone para que este test pueda construir los
        dos casos sin depender de donde este el checkout: un guard que
        solo sabe ver uno de sus dos estados es medio guard.
        """
        base = {
            "bloque": "B6",
            "version": "0.26.0",
            "release": "0.26.0",
            "tag_vcs": "0.26.0",
            "tests_declarados": 3053,
            "tests_reales": 3053,
            "workitem_state": "B6",
            "workitem_current": "B6",
        }
        problemas = project_truth._contradicciones(base, head_en_la_etiqueta=True)
        assert not any("version" in p for p in problemas), (
            f"con HEAD en la etiqueta, el SemVer puro dio contraste: {problemas}"
        )

    def test_la_excepcion_no_desactiva_el_guard_entre_releases(self) -> None:
        """La excepcion es para HEAD EN la etiqueta, y solo para ahi.

        Si aceptase el SemVer puro en cualquier momento, el guard de WI-109
        —«el paquete construido no lleva la version de una release ya
        publicada»— dejaria de comprobar nada, que es el fallo que la
        regla wrote para evitar.
        """
        base = {
            "bloque": "B6",
            "version": "0.26.0",
            "release": "0.26.0",
            "tag_vcs": "0.26.0",
            "tests_declarados": 3053,
            "tests_reales": 3053,
            "workitem_state": "B6",
            "workitem_current": "B6",
        }
        problemas = project_truth._contradicciones(base, head_en_la_etiqueta=False)
        assert any("version" in p for p in problemas), (
            f"fuera de la etiqueta el SemVer puro paso sin decir nada: {problemas}"
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


#: Extensiones con las que un literal de cadena es una RUTA a un fichero.
#: Sin esta lista, `tmp_path / "plan.md"` y `RAIZ / "ROADMAP.md"` serian la
#: misma cosa, y solo uno de los dos es una dependencia del repo. Lo que los
#: separa no es la forma: es que uno esta en el arbol y el otro lo crea el
#: propio test al correr.
EXTENSIONES_DE_FICHERO = frozenset(
    {
        ".cfg",
        ".ini",
        ".json",
        ".kts",
        ".md",
        ".py",
        ".sh",
        ".sql",
        ".toml",
        ".txt",
        ".yaml",
        ".yml",
    }
)


def _partes_de_ruta(nodo: ast.AST) -> tuple[tuple[str, ...], bool]:
    """Las constantes de una cadena de `/`, y si hay alguna parte opaca.

    `RAIZ / "scripts" / "x.py"` da `("scripts", "x.py")` y una parte opaca,
    porque `RAIZ` es un `Name` y no una constante. La parte opaca no se
    descarta: se **declara**, porque quien lee tiene que saber que la
    resolucion es parcial y que por eso la comprobacion se hace probando
    bases, en vez de adivinando una.
    """
    if isinstance(nodo, ast.BinOp) and isinstance(nodo.op, ast.Div):
        izq, izq_opaca = _partes_de_ruta(nodo.left)
        der, der_opaca = _partes_de_ruta(nodo.right)
        return (*izq, *der), izq_opaca or der_opaca
    if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Name):
        if nodo.func.id == "Path" and len(nodo.args) == 1 and not nodo.keywords:
            # `Path("tests") / "fixtures" / "x.py"`: el `Call` de `Path`
            # aporta su unico argumento. Sin esta rama se pierde el primer
            # segmento y el fichero no llega a resolverse nunca.
            return _partes_de_ruta(nodo.args[0])
        return (), True
    if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
        return (nodo.value,), False
    return (), True


def _ficheros_versionados(raiz: Path) -> frozenset[str]:
    """Lo que git tiene, segun git, relativo a `raiz`.

    Se pregunta al **indice**, no a `HEAD`: el indice es lo que git va a
    grabar en el proximo commit, y un fichero a medio anadir es justo el
    caso que este guard tiene que ver rojo.

    Y se pregunta a git en vez de deducirlo del arbol: un `.gitignore` puede
    excluir directorios enteros sin que se note mirando la lista de ficheros.
    """
    proc = subprocess.run(
        ["git", "ls-files"],
        capture_output=True,
        text=True,
        check=False,
        cwd=raiz,
    )
    if proc.returncode != 0:  # pragma: no cover - solo sin git
        raise RuntimeError(
            f"no se pudo preguntar a git por lo versionado en {raiz}: {proc.stderr.strip()}"
        )
    return frozenset(linea for linea in proc.stdout.splitlines() if linea)


def _relativa(raiz: Path, ruta: Path) -> str | None:
    """`ruta` relativa a `raiz`, o `None` si se sale de `raiz`."""
    try:
        return ruta.resolve().relative_to(raiz.resolve()).as_posix()
    except ValueError:
        # Se sale del arbol: un `..` que sube por encima de la raiz no puede
        # ser una dependencia del repo, y fingir que lo seria inventarse un
        # problema que no existe.
        return None


def _dependencias_no_versionadas(raiz: Path) -> tuple[tuple[str, int, str], ...]:
    """Ficheros que un test nombra, que existen, y que git no lleva.

    La propiedad en una frase: **si un test resuelve una ruta a un fichero que
    esta en el arbol, ese fichero tiene que estar en git.** Y en ese orden,
    que es el orden en que se decide: primero se resuelve la ruta y se
    comprueba que el fichero existe, y solo entonces se pregunta a git.

    MEDIDO al escribir esto. La primera version de este guard no resolvia
    rutas: recorria el texto linea a linea buscando un directorio prohibido y
    preguntaba si ese *directorio* tenia algo versionado. Dos agujeros, y los
    dos importan:

    - **Un solo fichero versionado lo desactiva entero.** La pregunta era
      «¿hay algo de git bajo `.pipelinek/`?», no «¿esta en git el fichero que
      este test necesita?». Bastaba un `.gitkeep` para que todos los que de
      verdad estaban rotos pasaran.
    - **No sabia ver rojo.** Su unico contrasalto era `assert lista_no_vacia`,
      que no puede fallar salvo que alguien borre la lista.

    Por eso la pregunta se hace **por fichero** y sobre el **arbol**, y el
    conjunto de rutas sale de las cadenas de `/` del AST. Mencionar un nombre
    de fichero en un docstring no es depender de el porque un docstring no es
    un operando de `/`: la distincion sale de la estructura, no de una
    heuristica sobre el texto. Es la misma frontera que cerro WI-108, donde un
    guard que buscaba con regex contaba su propia documentacion.

    **LIMITE DECLARADO.** Solo se ven las rutas montadas con `/` sobre
    literales. Un `subprocess.run([sys.executable, "scripts/x.py"])` escrito
    como literal suelto, o una ruta dentro de un f-string, se escapan. Se
    declara en vez de dejarlo para que lo descubra el primero que lopea.
    """
    versionados = _ficheros_versionados(raiz)
    hallazgos: list[tuple[str, int, str]] = []
    for test in sorted((raiz / "tests").rglob("*.py")):
        arbol = ast.parse(test.read_text(encoding="utf-8"), filename=str(test))
        for nodo in ast.walk(arbol):
            if not (isinstance(nodo, ast.BinOp) and isinstance(nodo.op, ast.Div)):
                continue
            partes, _opaca = _partes_de_ruta(nodo)
            if not partes or not partes[-1].endswith(tuple(EXTENSIONES_DE_FICHERO)):
                continue
            if any(Path(parte).is_absolute() for parte in partes):
                continue
            for base in (raiz, test.parent):
                destino = base.joinpath(*partes)
                # La clave se busca **relativa a la raiz**, siempre, sea cual
                # sea la base que haya resuelto. MEDIDO al escribir esto: con
                # la ruta relativa a `base`, `tests/fixtures/x.py` se
                # comparaba contra el indice de git como `fixtures/x.py`, que
                # ahi no existe, y salia culpable un fichero que si viajaba.
                # Las ocho falsas de la primera corrida eran esta linea.
                relativa = _relativa(raiz, destino)
                if relativa is None or not destino.is_file():
                    continue
                if relativa not in versionados:
                    hallazgos.append((str(test.relative_to(raiz)), nodo.lineno, relativa))
                break
    return tuple(dict.fromkeys(hallazgos))


class TestLoQueLosTestsUsanTambienViaja:
    """Un test que depende de un fichero que no viaja, no es un test.

    MEDIDO en B8, y no es hipotetico. Los cinco tests de
    `test_b2_real_concurrency.py` lanzan un hijo como proceso aparte, y ese
    hijo vivia en `.pipelinek/` — que esta en `.gitignore`. El modulo de
    tests estaba versionado; su hijo no.

    Las dos consecuencias, y las dos son malas:

    - En un clon limpio, los cinco tests fallan con `FileNotFoundError`.
    - Pasan aqui, en la maquina donde se escribieron, porque el fichero
      esta en disco aunque no este en git.

    No habia guard, y el contrato de build (WI-97) construye un sdist que si
    incluye `tests/`: un sdist con los tests dentro y sin su hijo no se parece
    a nada que se pueda detectar sin ejecutar los tests dentro.

    **Por que aqui y no en un modulo propio.** Es una contradiccion del repo
    consigo mismo —«el repo afirma tener estos tests» contra «los tests no se
    pueden ejecutar»— y este fichero es el que existe para que la verdad sea
    una.
    """

    def test_ningun_test_depende_de_un_fichero_que_no_viaja(self) -> None:
        culpables = _dependencias_no_versionadas(RAIZ)
        assert not culpables, (
            "estos tests dependen de ficheros que estan en disco pero NO en "
            "git, luego fallan en un clon limpio:\n  "
            + "\n  ".join(f"{f}:{n} -> {r}" for f, n, r in culpables)
            + "\n\nSe arregla anadiendo el fichero al proximo commit, no "
            "anadiendo su path a una lista de excepciones."
        )


class TestElGuardDeLoQueViajaSeSabeVer:
    """Contra-saltos, sobre un repo de mentira construido en `tmp_path`.

    El guard no se puede comprobar contra el repo real: aqui todo esta
    versionado, y un detector de algo que no esta pasaria en verde igual si
    detectara que si. La unica forma de saber que el detector detecta es
    construir el defecto, y por eso cada contrasalto monta su propio
    `git init`.
    """

    @staticmethod
    def _repo(tmp_path: Path, hijo_versionado: bool) -> Path:
        """Repo minimo con un test que depende de un hijo, y con el hijo.

        Monta ademas un segundo test que depende de un fichero que SI viaja:
        sin el, un detector que solo supiera dar rojo tambien pasaria el
        contrasalto de mas abajo.
        """
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        (tmp_path / ".gitignore").write_text(".pipelinek/\n", encoding="utf-8")
        (tmp_path / ".pipelinek").mkdir()
        (tmp_path / ".pipelinek" / "hijo.py").write_text("PASA = True\n", encoding="utf-8")
        (tmp_path / "scripts").mkdir()
        (tmp_path / "scripts" / "ayuda.py").write_text("PASA = True\n", encoding="utf-8")
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "fixtures").mkdir()
        (tmp_path / "tests" / "fixtures" / "ayuda.py").write_text("PASA = True\n", encoding="utf-8")
        (tmp_path / "tests" / "test_algo.py").write_text(
            '"""El hijo vivia en .pipelinek, que esta ignorado."""\n'
            "from __future__ import annotations\n"
            "from pathlib import Path\n"
            "RAIZ = Path(__file__).resolve().parent.parent\n"
            'CHILD = RAIZ / ".pipelinek" / "hijo.py"\n',
            encoding="utf-8",
        )
        (tmp_path / "tests" / "test_ayuda.py").write_text(
            '"""Un docstring que menciona scripts/ayuda.py sin depender de el."""\n'
            "from __future__ import annotations\n"
            "from pathlib import Path\n"
            "RAIZ = Path(__file__).resolve().parent.parent\n"
            'AYUDA = RAIZ / "scripts" / "ayuda.py"\n'
            # Esta resuelve contra `Path(__file__).parent`, no contra la raiz:
            # es la base que se try-broke en la primera corrida, y sin esta
            # linea el contrasalto de abajo no la tocaria.
            'AYUDA_2 = Path(__file__).parent / "fixtures" / "ayuda.py"\n',
            encoding="utf-8",
        )
        if hijo_versionado:
            subprocess.run(["git", "add", "-f", ".pipelinek/hijo.py"], cwd=tmp_path, check=True)
        subprocess.run(
            ["git", "add", ".gitignore", "scripts/ayuda.py", "tests/fixtures/ayuda.py"],
            cwd=tmp_path,
            check=True,
        )
        return tmp_path

    def test_ve_rojo_cuando_el_hijo_que_el_test_necesita_no_viaja(self, tmp_path: Path) -> None:
        """La direccion que importa: el defecto se ve.

        Sin esto, la ausencia de hallazgos del test de arriba seria
        indistinguible de un detector que no detecta nada.
        """
        culpables = _dependencias_no_versionadas(self._repo(tmp_path, hijo_versionado=False))
        assert [ruta for _, _, ruta in culpables] == [".pipelinek/hijo.py"], (
            f"el hijo sin versionar no se ve: {culpables}"
        )
        assert culpables[0][0] == "tests/test_algo.py"

    def test_no_ve_rojo_cuando_el_hijo_si_viaja(self, tmp_path: Path) -> None:
        """La direccion que la primera version de este guard no tenia.

        Anadir `.pipelinek/hijo.py` al indice **deja de ser un defecto**, y es
        el comportamiento correcto: lo que se prohibe es depender de algo que
        no viaja, no depender de `.pipelinek`.

        Esta es la sonda que mata el agujero del `.gitkeep`: un guard que
        decide por directorio pondria este caso en rojo, y este caso esta
        bien. Si lo que se quisiera fuera «`.pipelinek` no se usa nunca», la
        regla seria otra y habria que escribirla.
        """
        assert _dependencias_no_versionadas(self._repo(tmp_path, hijo_versionado=True)) == ()

    def test_una_dependencia_que_si_viaja_no_se_confunde_con_una_que_no(
        self, tmp_path: Path
    ) -> None:
        """El mismo repo, con las dos rutas: solo se nombra la rota.

        Si el detector confundiera «nombrar un fichero versionado» con
        «depender de uno sin versionar», este test veria dos hallazgos.
        """
        rutas = [
            ruta
            for _, _, ruta in _dependencias_no_versionadas(
                self._repo(tmp_path, hijo_versionado=False)
            )
        ]
        assert "scripts/ayuda.py" not in rutas, (
            f"un fichero que SI viaja salio como culpable: {rutas}"
        )
        assert "tests/fixtures/ayuda.py" not in rutas, (
            "un fichero que SI viaja y se resuelve contra `Path(__file__).parent` "
            f"salio como culpable: {rutas}"
        )
