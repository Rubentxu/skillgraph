"""La respuesta unica a «¿donde esta el proyecto y que toca despues?».

Este modulo es el que B0 deja como **una sola respuesta machine-readable**.
No es un resumo mas: es el unico sitio del repositorio donde se cruzan las
cinco verdades que el proyecto afirma sobre si mismo.

Las cinco, y quien las posee:

| verdad | dueño | por que no puede ser de otro |
|---|---|---|
| version activa | `src/skillgraph/__init__.py` | la construye hatchling |
| release emitida | `STATE.yaml.release.tag` | es la que se aprovisiona |
| tag real | `git describe --tags` | la verdad del VCS |
| tests declarados | `STATE.yaml.tests.total` | el estado durable |
| tests reales | el arbol, via pytest | lo unico que no se puede mentir |
| workitem vivo | ROADMAP + STATE + CURRENT | tres ventanas del mismo bloque |
| roadmap | `ROADMAP.md` en la raiz | unico dueño del futuro |

**POR QUE UN SCRIPT Y NO UN TEST.** Un test verifica; un script *responde*.
El gate de B0 pide las dos cosas y confundirlas es el modo de fallo clasico:
un test que sabe si algo esta bien pero no puede decir donde esta el
proyecto, y un informe que lo dice pero nadie lo ejecuta. Aqui el script
responde Y el test lo ejecuta, asi que la respuesta no puede envejecer en
silencio: si las verdades se contradicen, el JSON sale con `coherente: false`
y el campo que falla va nombrado.

**LO QUE NO HACE.** No decide nada. No calcula semver, no deriva el bloque
siguiente, no comprueba pruebas. Solo lee y cruza. Un modulo que adivina es
un modulo del que nadie puede depender.

Sin I/O oculto mas alla del disco, el reloj y el VCS: no hay red, ni
variables de modulo mutables, ni caches compartidas entre llamadas.
`estado()` es una funcion pura sobre el arbol.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parent.parent

STATE = RAIZ / "STATE.yaml"
ROADMAP = RAIZ / "ROADMAP.md"
CURRENT = RAIZ / "CURRENT.md"
INIT = RAIZ / "src" / "skillgraph" / "__init__.py"

# El bloque vivo del roadmap, en un formato que no depende de prosa.
# Se busca la linea de la seccion «Donde esta el proyecto», NO la primera
# mencion de B0..B9: el mapa tambien los nombra a todos, y un lector que
# cogiera la primera mediria el mapa en vez de la respuesta.
_BLOQUE_VIVO = re.compile(r"^>\s*Bloque vivo:\s*\*\*(B\d+)\*\*", re.MULTILINE)
_VERSION = re.compile(r'__version__\s*=\s*"([^"]+)"')
_TAG_STATE = re.compile(r"^\s*tag:\s*v?([0-9][^\s#]*)", re.MULTILINE)
_TOTAL = re.compile(r"^\s*total:\s*([0-9]+)", re.MULTILINE)
_WORKITEM_STATE = re.compile(r"^\s*current_workitem:\s*(\S+)", re.MULTILINE)
_WORKITEM_CUALQUIERA = re.compile(r"WI-\d+|B\d+")
_COLECTADOS = re.compile(r"([0-9]+) tests? collected")


class VerdadNoLegible(RuntimeError):
    """Una de las cinco verdades no se pudo leer.

    **Por que es una excepcion y no un `None`.** Si esto devolviera `None`
    y el llamante lo tratara como «sin informacion», el JSON saldria
    `coherente: true` con un campo a cero: un guard que no puede medir y
    aun asi pasa es peor que no tener guard. Es el modo de fallo que
    WI-115 introdujo un contrasalto explicito para cazar, y aqui se
    cierra en el tipo: la ausencia de una verdad es un fallo, no un dato.
    """


def _lee(relative: str) -> str:
    ruta = RAIZ / relative
    try:
        return ruta.read_text(encoding="utf-8")
    except OSError as exc:
        raise VerdadNoLegible(f"no se pudo leer {relative}: {exc}") from exc


def version_activa() -> str:
    m = _VERSION.search(_lee("src/skillgraph/__init__.py"))
    if m is None:
        raise VerdadNoLegible("src/skillgraph/__init__.py no declara __version__")
    return m.group(1)


def release_declarada() -> str:
    m = _TAG_STATE.search(_lee("STATE.yaml"))
    if m is None:
        raise VerdadNoLegible("STATE.yaml.release no declara `tag`")
    return m.group(1)


def tag_real() -> str | None:
    """El ultimo tag del VCS, o `None` si todavia no hay ninguno.

    `None` es un valor legitimo —un repositorio recien hecho no tiene
    tags— y NO es lo mismo que «no se pudo leer». Por eso el subtipo es
    `str | None` y no `str`: confundirlos seria declarar que un clon sin
    historial tiene el estado de verdad de una release inventada.
    """
    proc = subprocess.run(
        ["git", "describe", "--tags", "--abbrev=0"],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout.strip().lstrip("v") or None


def tests_declarados() -> int:
    m = _TOTAL.search(_lee("STATE.yaml"))
    if m is None:
        raise VerdadNoLegible("STATE.yaml.tests no declara `total`")
    return int(m.group(1))


def tests_colectados() -> int:
    """El recuento real, derivado del arbol.

    **Por que un subproceso y no una importacion.** Llamar a pytest desde
    pytest sin subproceso colecta la sesion que ya esta colectando y
    contaria cada test dos veces: el numero seria cierto y estaria mal.
    Es el mismo razonamiento que el guard de WI-115, y por eso el
    subproceso va con `-p no:cacheprovider`.

    **Por que `sys.executable` y no `"python"`.** El nombre `python` del
    PATH no es necesariamente el interprete que esta corriendo la suite:
    en un repo con `uv` puede ser el del sistema, sin las dependencias del
    proyecto, y entonces el recuento no se lee. Se mide con el mismo
    interprete que ejecuta los tests, que es el unico cuya respuesta
    significa algo aqui.

    Si el patron de salida de pytest dejara de coincidir, esto **lanza**.
    Un `0` aqui seria el cero silencioso contra el que WI-115 puso un
    contrasalto: compararia un numero real contra nada y pasaria en verde.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--collect-only"],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=False,
    )
    m = _COLECTADOS.search(proc.stdout)
    if m is None:
        raise VerdadNoLegible(
            "no se pudo leer el recuento real de tests en la salida de "
            f"pytest. Ultimas lineas:\n{proc.stdout[-400:]}\n"
            f"stderr:\n{proc.stderr[-300:]}"
        )
    return int(m.group(1))


def bloque_del_roadmap() -> str:
    m = _BLOQUE_VIVO.search(_lee("ROADMAP.md"))
    if m is None:
        raise VerdadNoLegible(
            "ROADMAP.md no declara un «Bloque vivo: **Bn**» legible por "
            "máquina. Sin esa línea, el roadmap no tiene bloque actual y "
            "esta pregunta no tiene respuesta."
        )
    return m.group(1)


def workitem_de_state() -> str:
    m = _WORKITEM_STATE.search(_lee("STATE.yaml"))
    if m is None:
        raise VerdadNoLegible("STATE.yaml.roadmap no declara `current_workitem`")
    return m.group(1)


def workitem_de_current() -> str:
    """El workitem del bloque VIVO de `CURRENT.md`.

    `CURRENT.md` son bloques anidados: el vivo va arriba y los cerrados van
    en `<details>`. Recortar en el primer `<details>` es lo que separa el
    bloque vivo de los historiales; tomar la primera coincidencia del
    fichero entero daria el bloque mas antiguo si alguien reordenara las
    secciones, que es exactamente el mantenimiento que este bloque existia
    para evitar.
    """
    cabeza = _lee("CURRENT.md").split("<details>", 1)[0]
    m = _WORKITEM_CUALQUIERA.search(cabeza)
    if m is None:
        raise VerdadNoLegible("CURRENT.md no nombra un workitem en su bloque vivo")
    return m.group(0)


@dataclass(frozen=True, slots=True)
class Estado:
    """La respuesta. Inmutable, porque es una fotografia de un instante."""

    bloque: str
    objetivo: str
    version: str
    release: str
    tag_vcs: str | None
    tests_declarados: int
    tests_reales: int
    workitem_state: str
    workitem_current: str
    roadmap: str
    contradicciones: tuple[str, ...]

    @property
    def coherente(self) -> bool:
        return not self.contradicciones

    def a_json(self) -> str:
        d = asdict(self)
        d["coherente"] = self.coherente
        d["contradicciones"] = list(self.contradicciones)
        return json.dumps(d, indent=2, ensure_ascii=False, sort_keys=True)


def _objetivo_del_bloque(bloque: str) -> str:
    """La linea de objetivo del bloque vivo, leida del propio roadmap.

    Se busca la tabla del mapa, no una prosa: si someday se reescribe la
    tabla, el objetivo cambia con ella y no puede quedarse pegado como
    una copia. Si no esta, se devuelve el propio identificador —que es
    informacion verdadera— en vez de inventar una descripcion.
    """
    texto = _lee("ROADMAP.md")
    m = re.search(rf"^\|\s*\*\*{re.escape(bloque)}\*\*\s*\|([^|]*)\|", texto, re.MULTILINE)
    return m.group(1).strip() if m else bloque


def _contradicciones(v: dict[str, Any]) -> tuple[str, ...]:
    """Cruza las cinco verdades. Cada comparacion nombra las dos caras.

    El mensaje dice SIEMPRE las dos partes. Un verificador que dice
    «falso» sin decir «cual era la verdad» deja a quien corrige haciendo
    la cuenta a mano, que es el trabajo que el guard existe para evitar.
    """
    problemas: list[str] = []

    if v["tag_vcs"] is not None and v["tag_vcs"] != v["release"]:
        problemas.append(
            f"release: STATE declara v{v['release']}, el ultimo tag del VCS es v{v['tag_vcs']}"
        )

    if v["tests_declarados"] != v["tests_reales"]:
        problemas.append(
            f"tests: STATE declara {v['tests_declarados']}, el arbol colecta {v['tests_reales']}"
        )

    if v["workitem_state"] != v["workitem_current"]:
        problemas.append(
            f"workitem: STATE declara {v['workitem_state']}, CURRENT declara "
            f"{v['workitem_current']}"
        )

    # La version activa tiene que ser la del ultimo tag mas el sufijo de
    # desarrollo. Sin esta regla, `__version__` podria quedar en el tag
    # Release y el guard de WI-109 (`package_version`) pasaria mientras el
    # paquete construido lleva la version de la release ya publicada.
    if v["tag_vcs"] is not None and v["version"] != f"{v['tag_vcs']}.dev0":
        problemas.append(
            f"version: __init__.py declara {v['version']} y el ultimo tag es "
            f"v{v['tag_vcs']}; lo esperable es {v['tag_vcs']}.dev0"
        )

    return tuple(problemas)


def estado() -> Estado:
    """La respuesta. Falla si una verdad no se puede leer.

    Todas las lecturas ocurren ANTES de comparar nada. Si `tag_vcs` es
    `None` —un clon sin tags— no se inventa una release: se dice que no
    hay tag y se sigue. Si una verdad falta, esto lanza en vez de devolver
    un estado parcial, porque un estado parcial se parece mucho a un
    estado sano.
    """
    v: dict[str, Any] = {
        "bloque": bloque_del_roadmap(),
        "version": version_activa(),
        "release": release_declarada(),
        "tag_vcs": tag_real(),
        "tests_declarados": tests_declarados(),
        "tests_reales": tests_colectados(),
        "workitem_state": workitem_de_state(),
        "workitem_current": workitem_de_current(),
    }
    return Estado(
        objetivo=_objetivo_del_bloque(v["bloque"]),
        roadmap="ROADMAP.md",
        contradicciones=_contradicciones(v),
        **v,
    )


def main() -> int:
    """Imprime la respuesta. Sale 1 si el proyecto se contradice a si mismo.

    Que un `print` salga con 1 es lo que permite usarlo en CI sin un
    envoltorio: el codigo de salida ES el veredicto, no una decoracion
    al red de un log.
    """
    try:
        e = estado()
    except VerdadNoLegible as exc:
        # Un fallo de medicion no es un veredicto de «todo bien». Sale 2,
        # que es distinto del 1 de «las verdades se contradicen»: el
        # segundo caso es un defecto del repositorio y el primero, del
        # instrumento.
        print(json.dumps({"coherente": False, "ilegible": str(exc)}, indent=2))
        return 2
    print(e.a_json())
    return 0 if e.coherente else 1


if __name__ == "__main__":
    raise SystemExit(main())
