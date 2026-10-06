"""B23 — el instrumento de la verdad puede equivocarse, y se le ve.

Cada clase de este fichero guarda un contrasalto: un caso que hace que la
propiedad pase en verde **sin medir**. Los contrasaltos no son adorno, son la
mitad del trabajo:

| propiedad | el contrasalto |
|---|---|
| R1 la raiz se usa | el arbol declara `B99`/`9.9.9.dev0`/`1 test`, distintos del repo |
| R2 la ventana se contrasta | el mensaje tiene que nombrar LAS DOS caras |
| R3 el bloque se cruza | se desalinea el ROADMAP, no STATE |
| R4 el fichero no se contradice | dos ventanas IGUALMENTE wrong y distintas entre si |
| R6 la derivacion mide | tiene que encontrar DOS ventanas, no devolver `()` |

El árbol de verdad se construye entero —con su `.git`, su estado, su ventana y
un test propio— porque MEDIDO en B23 que un sandbox de cuatro ficheros no da
una respuesta de verdad: la colecta sale `rc=5` y el verificador responde
`ilegible` POR EL MOTIVO EQUIVOCADO, que es el modo de fallo que hace que un
test que espera `ilegible` pase de mentira.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
SCRIPT = RAIZ / "scripts" / "project_truth.py"

sys.path.insert(0, str(RAIZ / "scripts"))

import project_truth  # noqa: E402  — despues de(sys.path)

# --------------------------------------------------------------------------
# El arbol de verdad
# --------------------------------------------------------------------------

#: Lo que declara el arbol de verdad. DISTINTO del repositorio real a proposito:
#: si el instrumento ignorara la raiz, devolveria los valores del repo y todos
#: los tests de R1 pasarian sin haber medido nada.
BLOQUE = "B99"
VERSION = "9.9.9.dev0"
RELEASE = "9.9.9"
TESTS = 1

STATE = f"""release:
  tag: v{RELEASE}
roadmap:
  current_workitem: {BLOQUE}
tests:
  total: {TESTS}
"""


def _roadmap(version: str, tag: str, tests: int, bloque: str = BLOQUE) -> str:
    """Un ROADMAP con su seccion de la respuesta. La ventana es lo que se mueve."""
    return (
        "# Roadmap\n\n"
        "## Dónde está el proyecto\n\n"
        f"> Bloque vivo: **{bloque}** — El árbol de la prueba\n"
        f"> Versión activa `{version}` · último tag `v{tag}` · {tests} tests · 16/16 UAT\n"
        "\n"
        "## El mapa\n\n"
        f"| Bloque | Objetivo | Resultado |\n|---|---|---|\n"
        f"| **{bloque}** | El árbol de la prueba | Se mide de verdad |\n"
    )


CURRENT = f"> **Bloque de prueba ({BLOQUE}).**\n>\n> El bloque vivo de la prueba.\n"


def _construye(base: Path, *, roadmap: str | None = None, init: str | None = None) -> Path:
    """Un proyecto completo. Sin esto el instrumento no puede responder de verdad."""
    (base / "src" / "skillgraph").mkdir(parents=True)
    (base / "tests").mkdir(parents=True)
    (base / "scripts").mkdir(parents=True)

    (base / "src" / "skillgraph" / "__init__.py").write_text(
        init if init is not None else f'__version__ = "{VERSION}"\n', encoding="utf-8"
    )
    (base / "STATE.yaml").write_text(STATE, encoding="utf-8")
    (base / "ROADMAP.md").write_text(
        roadmap if roadmap is not None else _roadmap(VERSION, RELEASE, TESTS), encoding="utf-8"
    )
    (base / "CURRENT.md").write_text(CURRENT, encoding="utf-8")
    (base / "tests" / "test_unico.py").write_text(
        "def test_unico() -> None:\n    assert True\n", encoding="utf-8"
    )
    return base


def _con_git(base: Path) -> Path:
    for cmd in (
        ["git", "init", "-q"],
        ["git", "config", "user.email", "b23@b23"],
        ["git", "config", "user.name", "b23"],
        ["git", "add", "-A"],
        ["git", "commit", "-qm", "arbol"],
        ["git", "tag", f"v{RELEASE}"],
    ):
        subprocess.run(cmd, cwd=base, capture_output=True, check=False)
    return base


def _corre(base: Path, *args: str) -> tuple[int, dict]:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--raiz", str(base), *args],
        cwd=base,
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        return proc.returncode, json.loads(proc.stdout)
    except json.JSONDecodeError:
        pytest.fail(f"la salida no es JSON (rc={proc.returncode}):\n{proc.stdout}\n{proc.stderr}")


@pytest.fixture
def arbol(tmp_path: Path) -> Path:
    """Un proyecto de verdad, con su git y su tag."""
    return _con_git(_construye(tmp_path / "arbol"))


# --------------------------------------------------------------------------
# R1 — la raiz es un parametro y se nota
# --------------------------------------------------------------------------


class TestLaRaizSeUsa:
    """MEDIDO antes de este bloque: `--raiz /tmp` salia `rc=0` con la verdad
    del repositorio REAL. Un flag que se ignora no es una opcion: es una
    afirmacion falsa sobre lo que el instrumento acaba de medir."""

    def test_el_arbol_responde_por_si_mismo(self, arbol: Path) -> None:
        rc, carga = _corre(arbol)
        assert rc == 0, f"un arbol sano deberia salir 0, dio {rc}: {carga}"
        assert carga["bloque"] == BLOQUE
        assert carga["version"] == VERSION
        assert carga["release"] == RELEASE
        assert carga["tests_declarados"] == TESTS
        assert carga["tests_reales"] == TESTS

    def test_el_veredicto_del_arbol_no_es_el_del_repo(self, arbol: Path) -> None:
        """El contrasalto de R1.

        Si el instrumento ignorara la raiz, este test pasaria sin medir. Lo que
        lo salva es que el arbol declara cosas que el repositorio real NO
        declara: `B99` no es `B22`, `9.9.9.dev0` no es `0.33.0.dev0` y `1` no
        son 3444. Un clon tal cual daria el veredicto del repo y el test
        caeria.
        """
        _, carga = _corre(arbol)
        _, real = _corre(RAIZ)
        assert carga["bloque"] != real["bloque"], "el arbol y el repo declaran el mismo bloque"
        assert carga["version"] != real["version"], "el arbol y el repo declaran la misma version"
        assert carga["tests_declarados"] != real["tests_declarados"], "las cifras coinciden"

    def test_una_raiz_inexistente_no_inventa_una_verdad(self) -> None:
        """MEDIDO: `--raiz /no/existe` salia `rc=0` con `coherente: true`."""
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--raiz", "/no/existe-este-dir-xyz"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 2, (
            f"una raiz que no existe tiene que salir con 2, dio {proc.returncode}"
        )
        carga = json.loads(proc.stdout)
        assert carga["coherente"] is False
        assert "no es un directorio" in carga["ilegible"], carga["ilegible"]

    def test_un_directorio_vacio_no_inventa_una_verdad(self, tmp_path: Path) -> None:
        """Un directorio sin estado no es un proyecto, y medirlo seria inventar."""
        vacio = tmp_path / "vacio"
        vacio.mkdir()
        rc, carga = _corre(vacio)
        assert rc == 2, f"un directorio sin STATE.yaml tiene que salir con 2, dio {rc}"
        assert "STATE.yaml" in carga["ilegible"], carga["ilegible"]

    def test_un_flag_desconocido_falla_en_voz_alta(self, arbol: Path) -> None:
        """MEDIDO: `--raiz-desconocido x` salia `rc=0` con la verdad del repo."""
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--raiz-desconocido", "x"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode != 0, "un argumento desconocido no puede salir con 0"
        assert "unrecognized" in proc.stderr or "usage:" in proc.stderr, proc.stderr[:200]


# --------------------------------------------------------------------------
# R2 — la ventana se contrasta con la verdad
# --------------------------------------------------------------------------


class TestLaVentanaSeContrasta:
    """MEDIDO antes de este bloque: la ventana publicaba `0.32.7` dos
    releases tarde y el instrumento decia `coherente: true` con seis
    contradicciones a la vista."""

    def _veredicto_de(self, tmp_path: Path, roadmap: str) -> dict:
        base = _con_git(_construye(tmp_path / "a", roadmap=roadmap))
        return _corre(base)[1]

    def test_una_version_que_miente_se_ve(self, tmp_path: Path) -> None:
        carga = self._veredicto_de(tmp_path, _roadmap("1.2.3.dev0", RELEASE, TESTS))
        assert carga["coherente"] is False
        ventana = [c for c in carga["contradicciones"] if c.startswith("ventana:")]
        assert ventana, f"una version que miente paso sin decir nada: {carga['contradicciones']}"

    def test_el_mensaje_nombra_las_dos_caras(self, tmp_path: Path) -> None:
        """El contrasalto de R2.

        Un guard que dice «falso» sin decir CUAL era la verdad deja a quien
        corrige haciendo la cuenta a mano, que es el trabajo que el guard
        existe para evitar. Si el mensaje no lleva las dos, o solo lleva la
        del fichero, el guard puede estar comparando cualquier cosa.
        """
        carga = self._veredicto_de(tmp_path, _roadmap("1.2.3.dev0", RELEASE, TESTS))
        ventana = [c for c in carga["contradicciones"] if c.startswith("ventana:")]
        assert ventana, carga["contradicciones"]
        assert any("1.2.3.dev0" in c and VERSION in c for c in ventana), (
            f"el mensaje no nombra LAS DOS versiones: {ventana}"
        )

    def test_un_tag_que_miente_se_ve(self, tmp_path: Path) -> None:
        base = _con_git(_construye(tmp_path / "a", roadmap=_roadmap(VERSION, "1.2.3", TESTS)))
        carga = _corre(base)[1]
        assert carga["coherente"] is False
        assert any("v1.2.3" in c and RELEASE in c for c in carga["contradicciones"]), carga[
            "contradicciones"
        ]

    def test_una_cifra_que_miente_se_ve(self, tmp_path: Path) -> None:
        base = _con_git(_construye(tmp_path / "a", roadmap=_roadmap(VERSION, RELEASE, 999)))
        carga = _corre(base)[1]
        assert carga["coherente"] is False
        assert any("999" in c and str(TESTS) in c for c in carga["contradicciones"]), carga[
            "contradicciones"
        ]

    def test_una_ventana_cierta_no_se_queja(self, arbol: Path) -> None:
        """La otra mitad: si todo esta bien, no hay contradiccion. Un guard que
        solo sabe poner rojo no distingue «defecto» de « functioning»."""
        _, carga = _corre(arbol)
        assert carga["coherente"] is True, carga["contradicciones"]
        # El JSON publica una lista vacia, no una tupla: `a_json()` serializa
        # el campo. Comparar contra `()` comprobaria el formato de la
        # serializacion y no la propiedad.
        assert carga["contradicciones"] == []


# --------------------------------------------------------------------------
# R3 — el bloque del ROADMAP se cruza con STATE y CURRENT
# --------------------------------------------------------------------------


class TestElBloqueSeCruza:
    """MEDIDO antes de este bloque: `bloque` se leia y se publicaba, y no se
    cruzaba con nadie. STATE y CURRENT se cruzaban ENTRE SI, luego los tres
    podian estar mal y dar `coherente: true`."""

    def test_un_bloque_que_no_es_el_de_state_se_ve(self, tmp_path: Path) -> None:
        """El contrasalto de R3: se desalinea el ROADMAP, NO STATE.

        Desalinear STATE lo cubre `test_un_workitem_desalineado_se_ve` de B0.
        Un guard que cambiara STATE seria una segunda copia de un guard que ya
        existe, y no mediria el hueco nuevo: el ROADMAP diciendo otra cosa.
        """
        base = _con_git(
            _construye(tmp_path / "a", roadmap=_roadmap(VERSION, RELEASE, TESTS, bloque="B98"))
        )
        carga = _corre(base)[1]
        assert carga["coherente"] is False
        bloques = [c for c in carga["contradicciones"] if c.startswith("bloque:")]
        assert len(bloques) == 2, f"se esperaban dos cruces de bloque, hubo {bloques}"
        assert any("B98" in c and BLOQUE in c for c in bloques), bloques

    def test_el_mensaje_nombre_las_tres_caracteristicas(self, tmp_path: Path) -> None:
        base = _con_git(
            _construye(tmp_path / "a", roadmap=_roadmap(VERSION, RELEASE, TESTS, bloque="B98"))
        )
        carga = _corre(base)[1]
        bloques = [c for c in carga["contradicciones"] if c.startswith("bloque:")]
        assert any("STATE" in c for c in bloques), bloques
        assert any("CURRENT" in c for c in bloques), bloques

    def test_el_proyecto_real_tiene_los_tres_iguales(self) -> None:
        """Control: si el repositorio real estuviera desalineado, el guard
        llevaria tiempo en rojo y este bloque no seria sobre una propiedad que
        se sostiene, sino sobre una que ya cayo."""
        proc = subprocess.run(
            [sys.executable, str(SCRIPT)], capture_output=True, text=True, check=False
        )
        carga = json.loads(proc.stdout)
        assert carga["bloque"] == carga["workitem_state"] == carga["workitem_current"], carga
        assert not [c for c in carga["contradicciones"] if c.startswith("bloque:")], carga[
            "contradicciones"
        ]


# --------------------------------------------------------------------------
# R4 — el fichero no puede contradecirse a si mismo
# --------------------------------------------------------------------------


class TestElRoadmapNoSeContradice:
    """MEDIDO antes de este bloque: dos ventanas consecutivas, `3444 tests` y
    `3431 tests`, las dos con `v0.32.7`."""

    def _dos_ventanas(self, primera: str, segunda: str) -> str:
        return (
            "# Roadmap\n\n"
            "## Dónde está el proyecto\n\n"
            f"> Bloque vivo: **{BLOQUE}** — El árbol de la prueba\n"
            f"> Versión activa `{primera}` · último tag `v{RELEASE}` · {TESTS} tests\n"
            f"> Versión activa `{segunda}` · último tag `v{RELEASE}` · {TESTS + 7} tests\n"
            "\n"
            "## El mapa\n\n"
            f"| Bloque | Objetivo | Resultado |\n|---|---|---|\n"
            f"| **{BLOQUE}** | El árbol de la prueba | Se mide de verdad |\n"
        )

    def test_dos_versiones_distintas_se_ven(self, tmp_path: Path) -> None:
        """El contrasalto de R4: las dos ventanas son IGUALMENTE wrong.

        Si las dos dijeran la version correcta y solo se contradijeran en la
        cifra, un cruce que solo mirara contra la verdad —que es una sola—
        no lo veria. Con las dos a `1.2.3.dev0`, la contradiccion entre ellas
        es lo UNICO que puede detectarla, y depende de que exista esa regla.
        """
        base = _con_git(
            _construye(tmp_path / "a", roadmap=self._dos_ventanas("1.2.3.dev0", "1.2.3.dev0"))
        )
        carga = _corre(base)[1]
        assert carga["coherente"] is False
        entre_si = [c for c in carga["contradicciones"] if "se contradice a si mismo" in c]
        assert entre_si, (
            f"dos ventanas iguales de valor y distintas no se vieron: {carga['contradicciones']}"
        )

    def test_el_mensaje_nombra_las_dos_cifras(self, tmp_path: Path) -> None:
        base = _con_git(_construye(tmp_path / "a", roadmap=self._dos_ventanas(VERSION, VERSION)))
        carga = _corre(base)[1]
        entre_si = [c for c in carga["contradicciones"] if "se contradice a si mismo" in c]
        assert any(str(TESTS) in c and str(TESTS + 7) in c for c in entre_si), entre_si

    def test_una_sola_ventana_no_se_contradice(self, tmp_path: Path) -> None:
        base = _con_git(_construye(tmp_path / "a", roadmap=_roadmap(VERSION, RELEASE, TESTS)))
        carga = _corre(base)[1]
        assert carga["coherente"] is True, carga["contradicciones"]


# --------------------------------------------------------------------------
# R6 — la derivacion mide, y el guard sabe dar rojo
# --------------------------------------------------------------------------


class TestLaDerivacionMide:
    """La regla de WI-103: un guard que solo sabe pasar no esta probado.

    Si `ventanas_del_roadmap` devolviera siempre `()`, todos los tests de R2
    y R4 pasarian sin haber leido nada — cada uno compara contra un tuple
    vacio y no encuentra contradicciones porque no hay ventanas que
    contrastar. Este test es el que impide ese mundo.
    """

    def test_encuentra_las_dos_ventanas_que_hay(self, tmp_path: Path) -> None:
        base = tmp_path / "a"
        base.mkdir()
        (base / "ROADMAP.md").write_text(
            "## Dónde está el proyecto\n\n"
            "> Bloque vivo: **B1** — x\n"
            "> Versión activa `1.0.0.dev0` · último tag `v1.0.0` · 10 tests\n"
            "> Versión activa `1.0.0.dev0` · último tag `v1.0.0` · 11 tests\n",
            encoding="utf-8",
        )
        ventanas = project_truth.ventanas_del_roadmap(base)
        assert len(ventanas) == 2, f"la derivacion devolvio {ventanas} y hay dos ventanas"
        assert [v.tests for v in ventanas] == [10, 11], ventanas

    def test_una_ventana_exige_comillas_para_la_version(self, tmp_path: Path) -> None:
        """Un numero suelto en la prosa no es la version.

        Sin la exigencia, un «16/16 UAT» o un «B22» se leeria como una
        verdad y el guard mediria algo que nadie declaro.
        """
        base = tmp_path / "a"
        base.mkdir()
        (base / "ROADMAP.md").write_text(
            "## Dónde está el proyecto\n\n"
            "> Bloque vivo: **B1** — x\n"
            "> 16/16 UAT, 22 revisores, B22 activo · 10 tests\n",
            encoding="utf-8",
        )
        ventanas = project_truth.ventanas_del_roadmap(base)
        assert len(ventanas) == 1, ventanas
        assert ventanas[0].version == "", f"se invento una version de la prosa: {ventanas[0]}"
        assert ventanas[0].tag == "", f"se invento un tag de la prosa: {ventanas[0]}"

    def test_sin_seccion_no_hay_ventanas_y_no_es_contradiccion(self, tmp_path: Path) -> None:
        """Un roadmap sin la seccion no esta mintiendo: no esta afirmando
        nada que se pueda contrastar. Un guard que exigiera la ventana
        inventaria una propiedad que el fichero no promete."""
        base = tmp_path / "a"
        base.mkdir()
        (base / "ROADMAP.md").write_text(
            "# Roadmap\n\n## Otra cosa\n\n> 10 tests\n", encoding="utf-8"
        )
        assert project_truth.ventanas_del_roadmap(base) == ()

    def test_una_cita_sin_cifras_no_es_ventana(self, tmp_path: Path) -> None:
        base = tmp_path / "a"
        base.mkdir()
        (base / "ROADMAP.md").write_text(
            "## Dónde está el proyecto\n\n"
            "> Bloque vivo: **B1** — La respuesta\n"
            "> 10 tests · 16/16 UAT\n",
            encoding="utf-8",
        )
        ventanas = project_truth.ventanas_del_roadmap(base)
        assert len(ventanas) == 1, f"solo la linea con cifras es ventana: {ventanas}"


class TestElGuardSabeDarRojo:
    """La otra mitad de WI-103: que el guard pueda fallar se comprueba
    fallando, no suponiendolo."""

    def test_el_repositorio_real_es_la_prueba_de_control(self) -> None:
        """El control: si el ROADMAP real publicase una ventana vieja, el
        instrumento tiene que decirlo. Sin esto, «`coherente: true`» en el
        repositorio real no distinguiria «no hay ventana» de «hay ventana y
        cuadra»."""
        proc = subprocess.run(
            [sys.executable, str(SCRIPT)], capture_output=True, text=True, check=False
        )
        carga = json.loads(proc.stdout)
        assert carga.get("ventanas"), "el ROADMAP real tiene que declarar su ventana"
        assert proc.returncode == 0, (
            f"el ROADMAP real deberia cuadrar y dio rc={proc.returncode}: {carga}"
        )
