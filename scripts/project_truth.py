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

import yaml

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
_WORKITEM_CUALQUIERA = re.compile(r"WI-\d+|B\d+")
_COLECTADOS = re.compile(r"([0-9]+) tests? collected")

# Los tres regex que se leian de STATE.yaml —`_TAG_STATE`, `_TOTAL` y
# `_WORKITEM_STATE`— han desaparecido. No se sustituyen por otros tres: se
# sustituyen por UNA lectura, y esa es la mitad del punto.
#
# MEDIDO en B14: seis ficheros de test leen STATE con `yaml.safe_load` y este
# lo leia entero con regex. Los dos protagonists son la MISMA clase de
# regexp sobre el mismo fichero, y YAML toma la clave DUPLICADA por la
# ultima mientras un regex se queda con la primera. Con dos
# `current_workitem` en el fichero, `yaml.safe_load` decia `B13_cerrado`, el
# regex decia `B13`, y este tool reportaba `coherente: true` con
# `contradicciones: []`. Dos lectores del mismo texto discrepando en silencio
# es la forma mas economica de falsificar la verdad del repositorio, y este
# fichero es la respuesta a «¿donde esta el proyecto?».


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


class _ClaveDuplicada(VerdadNoLegible):
    """El mismo nombre de clave dos veces en el MISMO mapa.

    YAML no protesta: se queda con la ultima y sigue. Por eso el fallo es
    invisible, y por eso se rechaza en el punto de lectura en vez de
    comprobarlo despues con un guard: un guard que busca «¿hay dos claves
    iguales?» tiene que recorrer el fichero, y un lector que las cuenta es un
    segundo lector, que es exactamente el problema.
    """

    def __init__(self, clave: str, donde: str) -> None:
        self.clave = clave
        self.donde = donde
        super().__init__(
            f"{donde} declara la clave {clave!r} DOS VECES. YAML se quedaria con la "
            f"ultima en silencio, y con dos consumidores del fichero eso significa que "
            f"pueden leer cosas distintas del mismo estado. Se rechaza en el punto de "
            f"lectura, no despues."
        )


class _SinClavesDuplicadas(yaml.SafeLoader):
    """SafeLoader que dice NO en vez de quedarse con la ultima."""


def _construye(loader: yaml.SafeLoader, node: yaml.MappingNode, deep: bool = False) -> dict:
    """Construye el mapa, negandose si una clave aparece dos veces.

    **Por que se recorre `node.value` y no el dict construido.** La primera
    version hacia `loader.construct_mapping(...)` y luego miraba
    `Mapping.items()`. No lanzaba NUNCA: `construct_mapping` ya devuelve un
    dict donde la clave repetida se colapso, luego el bucle ve una clave y no
    dos. MEDIDO: con dos `current_workitem` en el fichero, `_estado()` leia
    `B99_inventado` sin protestar.

    `node.value` son los pares (nodo_clave, nodo_valor) en CRUDO, que es donde
    sigue estando la informacion de que habia mas de una declaracion. Para
    cuando existe el dict, ya no la hay.
    """
    vistas: dict[Any, None] = {}
    for nodo_clave, _nodo_valor in node.value:
        clave = loader.construct_object(nodo_clave, deep=deep)
        if clave in vistas:
            raise _ClaveDuplicada(str(clave), "STATE.yaml")
        vistas[clave] = None
    return loader.construct_mapping(node, deep=deep)


_SinClavesDuplicadas.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construye)


def _estado() -> dict[str, Any]:
    """El estado, leído UNA vez y de una sola manera.

    Todo el que necesite un campo de STATE.yaml pasa por aquí. No es una
    medida de estilo: es lo que hace imposible que este tool y los tests que
    leen el mismo fichero puedan responder cosas distintas.
    """
    try:
        datos = yaml.load(_lee("STATE.yaml"), Loader=_SinClavesDuplicadas)
    except yaml.YAMLError as exc:
        raise VerdadNoLegible(f"STATE.yaml no se pudo leer como YAML: {exc}") from exc
    if not isinstance(datos, dict):
        raise VerdadNoLegible(
            f"STATE.yaml deberia ser un mapa en la raiz, y es {type(datos).__name__}"
        )
    return datos


def _seccion(nombre: str) -> Any:
    """La seccion de STATE, o `None` si no esta —que no es lo mismo que vacia."""
    valor = _estado().get(nombre)
    if valor is None:
        return None
    if not isinstance(valor, dict):
        raise VerdadNoLegible(
            f"STATE.yaml.{nombre} deberia ser un mapa, y es {type(valor).__name__}"
        )
    return valor


def version_activa() -> str:
    m = _VERSION.search(_lee("src/skillgraph/__init__.py"))
    if m is None:
        raise VerdadNoLegible("src/skillgraph/__init__.py no declara __version__")
    return m.group(1)


def release_declarada() -> str:
    release = _seccion("release")
    if release is None or "tag" not in release:
        raise VerdadNoLegible("STATE.yaml.release no declara `tag`")
    etiqueta = release["tag"]
    if not isinstance(etiqueta, str) or not etiqueta.startswith("v"):
        raise VerdadNoLegible(
            f"STATE.yaml.release.tag deberia ser un tag tipo vX.Y.Z, y es {etiqueta!r}"
        )
    return etiqueta[1:]


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


def _head_esta_en_la_etiqueta() -> bool:
    """True si HEAD esta exactamente en el commit del ultimo tag.

    MEDIDO al escribir B6: este script exigia SIEMPRE `<tag>.dev0`, y eso
    contradecía a `tests/test_release_governance.py::test_version_matches_git_tag`,
    que exige el SemVer PURO cuando HEAD esta en la etiqueta. Los dos
    guards son del repo y los dos se ejecutan, luego no hay version que
    los satisfaga a la vez: el estado «HEAD en el tag con la version
    publica» es INALCANZABLE por construccion.

    Los tres casos que el guard de release ya distinguishe, y que aqui se
    replican para que los dos dejen de contradecirse:

    1. HEAD en la etiqueta -> SemVer puro.
    2. HEAD posterior a la etiqueta -> `<tag>.dev0` (o superior, si ya se
       esta preparando un MINOR).
    3. Sin etiqueta -> cualquier `.devN`.
    """
    describe = subprocess.run(
        ["git", "describe", "--tags", "--abbrev=0"],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=False,
    )
    if describe.returncode != 0:
        return False
    tag = describe.stdout.strip()
    if not tag:
        return False
    head = subprocess.run(
        ["git", "rev-list", "-1", tag],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=False,
    )
    if head.returncode != 0:
        return False
    actual = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=False,
    )
    return actual.returncode == 0 and actual.stdout.strip() == head.stdout.strip()


def tests_declarados() -> int:
    tests = _seccion("tests")
    if tests is None or "total" not in tests:
        raise VerdadNoLegible("STATE.yaml.tests no declara `total`")
    total = tests["total"]
    if not isinstance(total, int) or isinstance(total, bool):
        raise VerdadNoLegible(
            f"STATE.yaml.tests.total deberia ser un entero, y es {type(total).__name__}: {total!r}"
        )
    return total


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
    # **Por que se mira el codigo de salida y no solo el numero.** MEDIDO: con
    # `src/skillgraph/__init__.py` mutilado, pytest no llega a acabar la
    # colecta, imprime «2867 tests collected, 27 errors», sale con rc=2 — y el
    # numero ese es REAL: son los tests que llego a ver. El problema es que no
    # es EL recuento, y este tool lo publicaba como si lo fuera:
    #
    #     tests: STATE declara 3284, el arbol colecta 2867
    #
    # Sin 417 tests, sin decir por que, y con la autoridad de quien conto. Un
    # recuento parcial no es un recuento: es el numero de otra cosa. La lectura
    # honesta es negarse, que es lo que hace el raise de abajo.
    #
    # El arbol real da rc=0 (MEDIDO), luego esto no cambia la respuesta de
    # ningun estado sano: solo quita la de los que no se pudieron medir.
    if proc.returncode != 0:
        parcial = _COLECTADOS.search(proc.stdout)
        raise VerdadNoLegible(
            "la colecta de tests no terminó, y su numero NO es el recuento real: "
            f"pytest salio con rc={proc.returncode}. Conteo parcial: "
            f"{parcial.group(0) if parcial else '(sin linea de conteo)'}\n"
            "Un numero de tests que no se pudo colectar no se puede comparar con el "
            "que declara el estado: no son la misma magnitud."
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
    roadmap = _seccion("roadmap")
    if roadmap is None or "current_workitem" not in roadmap:
        raise VerdadNoLegible("STATE.yaml.roadmap no declara `current_workitem`")
    workitem = roadmap["current_workitem"]
    if not isinstance(workitem, str) or not workitem:
        raise VerdadNoLegible(
            f"STATE.yaml.roadmap.current_workitem deberia ser un identificador no vacio, "
            f"y es {workitem!r}"
        )
    return workitem


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


def _contradicciones(
    v: dict[str, Any], *, head_en_la_etiqueta: bool | None = None
) -> tuple[str, ...]:
    """Cruza las cinco verdades. Cada comparacion nombra las dos caras.

    `head_en_la_etiqueta` es un PARAMETRO y no una llamada a git dentro, a
    proposito: los tests tienen que poder construir los dos casos —con
    HEAD en la etiqueta y sin HEAD— sin depender de donde este el
    checkout. La primera version de la excepcion consultaba git DENTRO de
    la funcion, y el test que la exercita dejo de ver el caso off-tag
    porque el repositorio real estaba en un tag: un guard que solo puede
    ver un caso es medio guard. `None` significa «preguntale a git».


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
    #
    # EXCEPTO cuando HEAD esta EN la etiqueta: ahi el release ya ocurrio
    # y la version correcta es el SemVer PURO. Sin esta excepcion este
    # script y `test_release_governance.py` se contradicen —los dos son
    # del repo y los dos se ejecutan— y no existe version que satisfaga a
    # los dos a la vez. Se cambio la REGLA de este script, no la del otro:
    # el guard de release ya distinguish los tres casos y este lo hacia
    # bien; el que estaba simplificado era este.
    if (
        v["tag_vcs"] is not None
        and not (
            head_en_la_etiqueta if head_en_la_etiqueta is not None else _head_esta_en_la_etiqueta()
        )
        and v["version"] != f"{v['tag_vcs']}.dev0"
    ):
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
