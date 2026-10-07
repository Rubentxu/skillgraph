"""La respuesta unica a «¿donde esta el proyecto y que toca despues?».

Este modulo es el que B0 deja como **una sola respuesta machine-readable**.
No es un resumo mas: es el unico sitio del repositorio donde se cruzan las
cinco verdades que el proyecto afirma sobre si mismo.

Las seis, y quien las posee:

| verdad | dueño | por que no puede ser de otro |
|---|---|---|
| version activa | `src/skillgraph/__init__.py` | la construye hatchling |
| release emitida | `STATE.yaml.release.tag` | es la que se aprovisiona |
| tag real | `git describe --tags` | la verdad del VCS |
| tests declarados | `STATE.yaml.tests.total` | el estado durable |
| tests reales | el arbol, via pytest | lo unico que no se puede mentir |
| workitem vivo | ROADMAP + STATE + CURRENT | tres ventanas del mismo bloque |
| roadmap | `ROADMAP.md` en la raiz | unico dueño del futuro |
| ventana | ROADMAP, seccion «Donde esta el proyecto» | es la respuesta que el propio ROADMAP declara ser esta |

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

**LA RAIZ ES UN PARAMETRO, NO UNA CONSTANTE (B23).** Antes de B23 este modulo
tenia `RAIZ = Path(__file__).resolve().parent.parent` y de ahi derivaba las
cuatro rutas. MEDIDO lo que costaba:

    $ project_truth.py --raiz /tmp          rc=0, imprime la verdad del REPO
    $ project_truth.py --raiz /no/existe    rc=0, imprime la verdad del REPO
    $ cd /otro/arbol && project_truth.py    rc=0, imprime la verdad del REPO

No era una ergonomic que faltara: era un instrumento que **afirmaba haber
medido lo que no media**, con la autoridad de quien responde «¿donde esta el
proyecto?». Y hacia falta para otra cosa: `tests/test_b14_truth_single_reader.py`
deformaba el arbol REAL para poder medir, porque cualquier sandbox devolvia una
respuesta que no era de verdad. Con la raiz por parametro, un sandbox puede
contener lo que el instrumento necesita para responder de verdad.

Por eso la raiz viaja como PARAMETRO en los once lectores y las constantes de
modulo **no existen**: la unica forma de leer es pasar la raiz. Un
`set_raiz()` que reescribiera una constante global seria el estado global
mutable que `AGENTS.md` 1.4 prohibe, y aqui ademas se pisarian dos lectores
con raices distintas.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

#: La raiz por defecto: el repositorio donde vive este script. NO es una
#: constante de lectura —cada lector lleva su `raiz`— sino el valor que
#: `main()` usa cuando el operador no dice otra cosa. Que sea un default y no
#: un parametro obligatorio es lo que mantiene la llamada de siempre
#: (`project_truth.py` a pelo) dando la misma respuesta que antes.
RAIZ_POR_DEFECTO = Path(__file__).resolve().parent.parent

# El bloque vivo del roadmap, en un formato que no depende de prosa.
# Se busca la linea de la seccion «Donde esta el proyecto», NO la primera
# mencion de B0..B9: el mapa tambien los nombra a todos, y un lector que
# cogiera la primera mediria el mapa en vez de la respuesta.
_BLOQUE_VIVO = re.compile(r"^>\s*Bloque vivo:\s*\*\*(B\d+)\*\*", re.MULTILINE)
_VERSION = re.compile(r'__version__\s*=\s*"([^"]+)"')
_WORKITEM_CUALQUIERA = re.compile(r"WI-\d+|B\d+")
_COLECTADOS = re.compile(r"([0-9]+) tests? collected")

# La VENTANA: la seccion que el propio ROADMAP declara que es «la respuesta a
# ¿donde esta el proyecto y que toca despues?». MEDIDO en B23 que esa seccion
# publica dos lineas que se contradicen —`3444 tests` y `3431 tests`, y las dos
# con `v0.32.7` cuando el release ya era v0.33.0— y que el instrumento, que si
# cruza las otras seis verdades, no miraba ninguna: decia `coherente: true`
# con seis contradicciones a la vista.
#
# Se recorta POR SECCION y no por el fichero entero, por el mismo motivo que
# `workitem_de_current` recorta en `<details>`: la primera coincidencia del
# fichero entero mide el bloque mas antiguo el dia que alguien reordene.
_SECCION_PROYECTO = re.compile(
    r"^##\s+D[oó]nde est[aá] el proyecto\s*$(.*?)(?=^##\s|\Z)",
    re.MULTILINE | re.DOTALL,
)
# Una ventana es una linea de cita `>` que declara una cifra de tests. Las que
# no la tienen no son ventana: son prosa del bloque.
_LINEA_VENTANA = re.compile(r"^>.*$", re.MULTILINE)
# Version y tag solo cuentan dentro de comillas invertidas: `0.32.7.dev0`. Un
# numero suelto en la prosa no es la version, y un regex que lo cogiera
# mediria un numero de telefono como si fuera una verdad.
_VERSION_VENTANA = re.compile(r"`(\d+\.\d+\.\d+(?:\.dev\d+)?)`")
_TAG_VENTANA = re.compile(r"(?:tag|Tag)\s+`v(\d+\.\d+\.\d+)`")
_TESTS_VENTANA = re.compile(r"([0-9]+)\s+tests?\b")

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


def _lee(raiz: Path, relative: str) -> str:
    ruta = raiz / relative
    try:
        return ruta.read_text(encoding="utf-8")
    except OSError as exc:
        raise VerdadNoLegible(f"no se pudo leer {relative}: {exc}") from exc


def _exige_raiz(raiz: Path) -> Path:
    """La raiz tiene que existir y tener estado, o esto NO MIDE NADA.

    **Por que un raise y no un default silencioso.** MEDIDO en B23: antes de
    este bloque, `project_truth.py --raiz /no/existe` salia con `rc=0` y
    `coherente: true` imprimiendo la verdad del repositorio real. Un
    instrumento que no puede leer y aun asi afirma estar bien es peor que uno
    que no existe: es el modo de fallo que WI-115 puso un contrasalto para
    cazar, y aqui se cierra en el tipo. La ausencia de una verdad es un fallo,
    no un dato.
    """
    if not raiz.is_dir():
        raise VerdadNoLegible(f"la raiz {raiz} no es un directorio")
    if not (raiz / "STATE.yaml").is_file():
        raise VerdadNoLegible(
            f"la raiz {raiz} no parece un proyecto: no hay STATE.yaml. Sin estado "
            "durable no hay nada que cruzar, y medir de todas formas seria "
            "inventarse una verdad."
        )
    return raiz


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


def _estado(raiz: Path) -> dict[str, Any]:
    """El estado, leído UNA vez y de una sola manera.

    Todo el que necesite un campo de STATE.yaml pasa por aquí. No es una
    medida de estilo: es lo que hace imposible que este tool y los tests que
    leen el mismo fichero puedan responder cosas distintas.
    """
    try:
        datos = yaml.load(_lee(raiz, "STATE.yaml"), Loader=_SinClavesDuplicadas)
    except yaml.YAMLError as exc:
        raise VerdadNoLegible(f"STATE.yaml no se pudo leer como YAML: {exc}") from exc
    if not isinstance(datos, dict):
        raise VerdadNoLegible(
            f"STATE.yaml deberia ser un mapa en la raiz, y es {type(datos).__name__}"
        )
    return datos


def _seccion(raiz: Path, nombre: str) -> Any:
    """La seccion de STATE, o `None` si no esta —que no es lo mismo que vacia."""
    valor = _estado(raiz).get(nombre)
    if valor is None:
        return None
    if not isinstance(valor, dict):
        raise VerdadNoLegible(
            f"STATE.yaml.{nombre} deberia ser un mapa, y es {type(valor).__name__}"
        )
    return valor


def version_activa(raiz: Path) -> str:
    m = _VERSION.search(_lee(raiz, "src/skillgraph/__init__.py"))
    if m is None:
        raise VerdadNoLegible("src/skillgraph/__init__.py no declara __version__")
    return m.group(1)


def release_declarada(raiz: Path) -> str:
    release = _seccion(raiz, "release")
    if release is None or "tag" not in release:
        raise VerdadNoLegible("STATE.yaml.release no declara `tag`")
    etiqueta = release["tag"]
    if not isinstance(etiqueta, str) or not etiqueta.startswith("v"):
        raise VerdadNoLegible(
            f"STATE.yaml.release.tag deberia ser un tag tipo vX.Y.Z, y es {etiqueta!r}"
        )
    return etiqueta[1:]


def package_version_declarada(raiz: Path) -> str | None:
    """La version activa que declara `STATE.yaml.release`, o `None`.

    **EL AGUJERO QUE CIERRA, MEDIDO ANTES DE ESCRIBIR ESTA LINEA.**

    `project_truth.py` cruzaba la version activa con el ultimo tag, pero
    **`release.package_version` no era parte de la verdad**: nadie la leia.
    Y no es una lectura mas —es la que el guard de release
    (`test_release_governance::test_current_version_is_documented_in_state`)
    afirma contrastar con `__version__`, y su predicado es una **coincidencia
    de texto**: `f'package_version: "{version}"' in state_yaml`, que encuentra
    la linea que sea en todo el fichero.

    MEDIDO con el contrasalto que describe el hallazgo:

        release.package_version := 0.40.0.dev0   (la version anterior)
        -> project_truth rc=0, coherente: true

    O sea: el campo puede quedarse viejo y **nadie se entera**. Es la misma
    clase que WI-115 midio para `tests.total` y `tests.package_version`, y
    aqui es el **tercer** miembro de esa familia.

    **POR QUE DEVUELVE `None` Y NO STR.** Un repositorio recien hecho puede no
    declararla, y eso es distinto de declararla mal: lo primero es una
    ausencia tolerable, lo segundo una contradiccion. Confundirlas seria
    inventar un fallo donde no lo hay, que es el error espejo del de WI-113
    (`empate_en_la_jerarquia`).
    """
    release = _seccion(raiz, "release")
    if release is None:
        return None
    valor = release.get("package_version")
    if valor is None:
        return None
    if not isinstance(valor, str):
        raise VerdadNoLegible(
            f"STATE.yaml.release.package_version deberia ser un string, y es {type(valor).__name__}"
        )
    return valor


def tag_real(raiz: Path) -> str | None:
    """El ultimo tag del VCS, o `None` si todavia no hay ninguno.

    `None` es un valor legitimo —un repositorio recien hecho no tiene
    tags— y NO es lo mismo que «no se pudo leer». Por eso el subtipo es
    `str | None` y no `str`: confundirlos seria declarar que un clon sin
    historial tiene el estado de verdad de una release inventada.
    """
    proc = subprocess.run(
        ["git", "describe", "--tags", "--abbrev=0"],
        cwd=raiz,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout.strip().lstrip("v") or None


def _head_esta_en_la_etiqueta(raiz: Path) -> bool:
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
        cwd=raiz,
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
        cwd=raiz,
        capture_output=True,
        text=True,
        check=False,
    )
    if head.returncode != 0:
        return False
    actual = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=raiz,
        capture_output=True,
        text=True,
        check=False,
    )
    return actual.returncode == 0 and actual.stdout.strip() == head.stdout.strip()


def total_declarado(raiz: Path) -> int:
    """El total que declara `STATE.yaml`.

    **POR QUE NO SE LLAMA `tests_declarados` (B23).** `pytest` colecta
    cualquier funcion cuyo nombre empieza por `test`, y estos dos lectores se
    llamaban `tests_declarados` y `tests_colectados`. MEDIDO: con pytest
    apuntado a `scripts/`, los dos salian como DOS TESTS MAS que «pasaban»
    porque devuelven un entero y no una asercion. `testpaths = ["tests"]` lo
    escondia en la suite normal, pero el hook de smoke del repo apunta a lo
    staged, y ahi se coletaban de verdad.

    Un lector que se hace pasar por un test es peor que un lector lento:
    cuenta como veredicto y no mide nada. Las CLAVES del JSON —`tests_declarados`
    y `tests_reales`— si se conservan: son el contrato de salida de
    `measure_b9_gate_1_0.py` y de media docena de tests.
    """
    tests = _seccion(raiz, "tests")
    if tests is None or "total" not in tests:
        raise VerdadNoLegible("STATE.yaml.tests no declara `total`")
    total = tests["total"]
    if not isinstance(total, int) or isinstance(total, bool):
        raise VerdadNoLegible(
            f"STATE.yaml.tests.total deberia ser un entero, y es {type(total).__name__}: {total!r}"
        )
    return total


def total_colectado(raiz: Path) -> int:
    """El recuento real, derivado del arbol.

    **Por que se llama asi y no `tests_colectados`:** ver
    `total_declarado`. Un lector que se hace pasar por un test cuenta como
    veredicto y no mide nada.

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
        cwd=raiz,
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


def bloque_del_roadmap(raiz: Path) -> str:
    m = _BLOQUE_VIVO.search(_lee(raiz, "ROADMAP.md"))
    if m is None:
        raise VerdadNoLegible(
            "ROADMAP.md no declara un «Bloque vivo: **Bn**» legible por "
            "máquina. Sin esa línea, el roadmap no tiene bloque actual y "
            "esta pregunta no tiene respuesta."
        )
    return m.group(1)


@dataclass(frozen=True, slots=True)
class Ventana:
    """Una linea de la respuesta del ROADMAP, descompuesta.

    Inmutable porque es una fotografia de un instante, como `Estado`: dos
    ventanas del mismo fichero describen el mismo instante, y si una pudiera
    cambiarse sola, el cruce entre ellas no mediria nada.

    `linea` guarda el texto ENTERO para que el mensaje pueda citar lo que el
    fichero dice, no una reconstruccion de lo que el regex entendio: un
    verificador que nombra la paraphrasis de un defecto y no el defecto se
    deja a quien corrige el trabajo de reconocerlo.
    """

    linea: str
    version: str
    tag: str
    tests: int | None


def ventanas_del_roadmap(raiz: Path) -> tuple[Ventana, ...]:
    """Las ventanas que declara el ROADMAP. Puede no declarar ninguna.

    **Por que el RECUENTO puede ser cero y no es una contradiccion.** Una
    seccion que no publica ventana no esta mintiendo: no esta afirmando nada
    que este instrumento pueda contrastar. Un guard que exigiera una ventana
    inventaria una propiedad que el fichero no promete, y el dia que el
    formato cambiara dira «falso» sin que haya un defecto.

    **Por que se recorta por SECCION y no por el fichero entero.** Es el
    mismo razonamiento que `workitem_de_current` recorta en `<details>`: la
    primera coincidencia del fichero entero mide el bloque mas antiguo el dia
    que alguien reordene las secciones, y el bloque mas antiguo no es la
    respuesta. La seccion tiene nombre estable y es la que el propio ROADMAP
    declara como «la respuesta a ¿donde esta el proyecto y que toca
    despues?».

    **Por que version y tag exigen comillas invertidas.** Un numero suelto en
    la prosa no es la version. Sin las comillas, un «B22» o un «16/16 UAT» se
    leeria como una verdad, y el guard estaria midiendo algo que nadie
    declaro.
    """
    texto = _lee(raiz, "ROADMAP.md")
    seccion = _SECCION_PROYECTO.search(texto)
    if seccion is None:
        return ()
    ventanas: list[Ventana] = []
    for linea in _LINEA_VENTANA.findall(seccion.group(1)):
        if _TESTS_VENTANA.search(linea) is None:
            continue  # Una cita de la seccion que no publica cifras no es ventana.
        version = _VERSION_VENTANA.search(linea)
        tag = _TAG_VENTANA.search(linea)
        tests = _TESTS_VENTANA.search(linea)
        ventanas.append(
            Ventana(
                linea=linea.strip(),
                version=version.group(1) if version else "",
                tag=tag.group(1) if tag else "",
                tests=int(tests.group(1)) if tests else None,
            )
        )
    return tuple(ventanas)


def workitem_de_state(raiz: Path) -> str:
    roadmap = _seccion(raiz, "roadmap")
    if roadmap is None or "current_workitem" not in roadmap:
        raise VerdadNoLegible("STATE.yaml.roadmap no declara `current_workitem`")
    workitem = roadmap["current_workitem"]
    if not isinstance(workitem, str) or not workitem:
        raise VerdadNoLegible(
            f"STATE.yaml.roadmap.current_workitem deberia ser un identificador no vacio, "
            f"y es {workitem!r}"
        )
    return workitem


def workitem_de_current(raiz: Path) -> str:
    """El workitem del bloque VIVO de `CURRENT.md`.

    `CURRENT.md` son bloques anidados: el vivo va arriba y los cerrados van
    en `<details>`. Recortar en el primer `<details>` es lo que separa el
    bloque vivo de los historiales; tomar la primera coincidencia del
    fichero entero daria el bloque mas antiguo si alguien reordenara las
    secciones, que es exactamente el mantenimiento que este bloque existia
    para evitar.
    """
    cabeza = _lee(raiz, "CURRENT.md").split("<details>", 1)[0]
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
    #: **R0.B.** La version activa que declara `STATE.yaml.release`. Antes no
    #: era parte de la verdad y por eso el contrasalto de B29 daba verde con
    #: el campo en la version anterior. `None` = no la declara (tolerable);
    #: declararla distinta de `version` = contradiccion.
    package_version: str | None
    release: str
    tag_vcs: str | None
    tests_declarados: int
    tests_reales: int
    workitem_state: str
    workitem_current: str
    roadmap: str
    ventanas: tuple[Ventana, ...] = ()
    contradicciones: tuple[str, ...] = ()

    @property
    def coherente(self) -> bool:
        return not self.contradicciones

    def a_json(self) -> str:
        d = asdict(self)
        d["coherente"] = self.coherente
        d["contradicciones"] = list(self.contradicciones)
        return json.dumps(d, indent=2, ensure_ascii=False, sort_keys=True)


def _objetivo_del_bloque(raiz: Path, bloque: str) -> str:
    """La linea de objetivo del bloque vivo, leida del propio roadmap.

    Se busca la tabla del mapa, no una prosa: si someday se reescribe la
    tabla, el objetivo cambia con ella y no puede quedarse pegado como
    una copia. Si no esta, se devuelve el propio identificador —que es
    informacion verdadera— en vez de inventar una descripcion.
    """
    texto = _lee(raiz, "ROADMAP.md")
    m = re.search(rf"^\|\s*\*\*{re.escape(bloque)}\*\*\s*\|([^|]*)\|", texto, re.MULTILINE)
    return m.group(1).strip() if m else bloque


def _contradicciones_de_la_ventana(v: dict[str, Any], ventanas: tuple[Ventana, ...]) -> list[str]:
    """Cada ventana contra la verdad. Una funcion, una pregunta.

    MEDIDO en B23: sin esto, `project_truth.py` cruzaba `release`, `tests`,
    `workitem` y `version` —todas bien— y no cruzaba NADA de la ventana que
    el propio ROADMAP declara ser «la respuesta a ¿donde esta el proyecto?».
    El resultado era `coherente: true` con seis contradicciones a la vista, y
    dos releases de desfase en el fichero.

    La regla es «una linea que declara una verdad, se contrasta con esa
    verdad». Una ventana que no declara version no se queixa de la version: no
    esta afirmando nada sobre ella.
    """
    problemas: list[str] = []
    for ventana in ventanas:
        if ventana.version and ventana.version != v["version"]:
            problemas.append(
                f"ventana: el ROADMAP publica la version {ventana.version!r}, "
                f"la verdad es {v['version']!r} — {ventana.linea!r}"
            )
        if ventana.tag and ventana.tag != v["release"]:
            problemas.append(
                f"ventana: el ROADMAP publica el tag v{ventana.tag!r}, "
                f"la release es v{v['release']!r} — {ventana.linea!r}"
            )
        if ventana.tests is not None and ventana.tests != v["tests_declarados"]:
            problemas.append(
                f"ventana: el ROADMAP publica {ventana.tests} tests, "
                f"el estado declara {v['tests_declarados']} — {ventana.linea!r}"
            )
    return problemas


def _ventanas_entre_si(ventanas: tuple[Ventana, ...]) -> list[str]:
    """Las ventanas unas contra otras. El fichero no puede contradecirse.

    MEDIDO en B23: `ROADMAP.md` publicaba dos ventanas consecutivas —una con
    `3444 tests` y otra con `3431 tests`, las dos con `v0.32.7`—, y el
    defecto no es que mentieran: es que **se contradijian entre si** mientras
    el fichero es la respuesta. Por eso esta regla mira ventana contra
    ventana y no solo contra la verdad: dos ventanas que sean las dos
    igualmente wrong y distintas entre si son todavia un defecto, y un cruce
    que solo mirara la verdad no lo veria — la verdad es una sola.
    """
    if len(ventanas) < 2:
        return []
    problemas: list[str] = []
    primera = ventanas[0]
    for otra in ventanas[1:]:
        if primera.version and otra.version and primera.version != otra.version:
            problemas.append(
                f"ventana: el ROADMAP publica dos versiones distintas, "
                f"{primera.version!r} y {otra.version!r} — el fichero se "
                f"contradice a si mismo"
            )
        if primera.tag and otra.tag and primera.tag != otra.tag:
            problemas.append(
                f"ventana: el ROADMAP publica dos tags distintos, "
                f"v{primera.tag!r} y v{otra.tag!r} — el fichero se contradice a si mismo"
            )
        if primera.tests is not None and otra.tests is not None and primera.tests != otra.tests:
            problemas.append(
                f"ventana: el ROADMAP publica dos cifras distintas, "
                f"{primera.tests} y {otra.tests} tests — el fichero se contradice a si mismo"
            )
    return problemas


def _contradicciones(
    v: dict[str, Any],
    *,
    head_en_la_etiqueta: bool | None = None,
    raiz: Path | None = None,
    ventanas: tuple[Ventana, ...] = (),
) -> tuple[str, ...]:
    """Cruza las siete verdades. Cada comparacion nombra las dos caras.

    `head_en_la_etiqueta` es un PARAMETRO y no una llamada a git dentro, a
    proposito: los tests tienen que poder construir los dos casos —con
    HEAD en la etiqueta y sin HEAD— sin depender de donde este el
    checkout. La primera version de la excepcion consultaba git DENTRO de
    la funcion, y el test que la exercita dejo de ver el caso off-tag
    porque el repositorio real estaba en un tag: un guard que solo puede
    ver un caso es medio guard. `None` significa «preguntale a git».

    `raiz` es la raiz que se le pregunta. `None` significa «la de por
    defecto», que es lo que necesitan los tests que cruzan un dict
    literal: ellos no miden ningun arbol, y su unico git posible seria el
    de un repositorio que no es el suyo. MEDIDO en B23: sin este
    parametro, preguntar a git sin raiz era preguntar al repositorio que
    este script tiene debajo, que no es necesariamente el que se esta
    midiendo.

    `ventanas` es PARAMETRO y no clave del dict, por el mismo motivo que
    `head_en_la_etiqueta`: los tests que cruzan un literal de ocho claves
    siguen midiendo lo que media, y el camino real —`estado()`— pasa
    SIEMPRE las ventanas. Un defecto que se puede dejar sin mirar no es un
    defecto que este guard.

    El mensaje dice SIEMPRE las dos partes. Un verificador que dice
    «falso» sin decir «cual era la verdad» deja a quien corrige haciendo
    la cuenta a mano, que es el trabajo que el guard existe para evitar.
    """
    problemas: list[str] = []
    donde = raiz if raiz is not None else RAIZ_POR_DEFECTO
    problemas.extend(_contradicciones_de_la_ventana(v, ventanas))
    problemas.extend(_ventanas_entre_si(ventanas))

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

    # El `bloque` del ROADMAP contra los otros dos. MEDIDO en B23: el bloque
    # se LEIA y se PUBLICABA, y no se cruzaba con nadie. STATE y CURRENT se
    # cruzaban ENTRE SI, luego los tres podian estar mal y dar
    # `coherente: true`: el ROADMAP decia B99 mientras STATE y CURRENT decian
    # B22 los dos, y nada lo notaba. Un identificador que se publica sin
    # cruzarse es una afirmacion sin contraparte.
    if v["bloque"] != v["workitem_state"]:
        problemas.append(
            f"bloque: el ROADMAP declara {v['bloque']}, STATE declara {v['workitem_state']}"
        )

    if v["bloque"] != v["workitem_current"]:
        problemas.append(
            f"bloque: el ROADMAP declara {v['bloque']}, CURRENT declara {v['workitem_current']}"
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
            head_en_la_etiqueta
            if head_en_la_etiqueta is not None
            else _head_esta_en_la_etiqueta(donde)
        )
        and v["version"] != f"{v['tag_vcs']}.dev0"
    ):
        problemas.append(
            f"version: __init__.py declara {v['version']} y el ultimo tag es "
            f"v{v['tag_vcs']}; lo esperable es {v['tag_vcs']}.dev0"
        )

    # **R0.B: `release.package_version` POR FIN ES PARTE DE LA VERDAD.**
    #
    # Antes no se leia, y por eso el contrasalto de B29 —«ponla en la version
    # anterior y mira»— daba `coherente: true`. La regla es la MISMA que la
    # de arriba, y se aplica sobre el campo que la declara:
    #
    #     version activa == tag + .dev0   (o el SemVer puro si HEAD esta EN la
    #                                     tag, que es el caso 2 del guard)
    #
    # **Y POR QUE NO BASTABA CON QUE EL GUARD DE RELEASE LO MIRARA.** Ese guard
    # compara `f'package_version: "{version}"' in state_yaml`, que es una
    # **coincidencia de texto sobre todo el fichero**: encuentra la linea que
    # sea. Con la cabecera mal y `releases[0]` bien, pasa. Un predicado que
    # busca un texto no puede distinguir *donde* estaba el valor; hace falta
    # leer el campo por su camino.
    #
    # **Y LA RELACION ESTA MODELADA, NO ES UNA COMPARACION INGENUA.** En
    # desarrollo `package = 0.41.0.dev0` mientras `latest_tag = 0.41.0` es lo
    # NORMAL, no una contradiccion: es la relacion «el arbol va mas alla que la
    # etiqueta y por eso lleva `.dev0`». Aqui se dice con `head_en_la_etiqueta`,
    # la misma booleana que ya desambigua el caso 2. Sin ella, o este bloque
    # se contradiria con `test_version_matches_git_tag`, que los dos son del
    # repo y los dos se ejecutan.
    paquete_declarado = v.get("package_version")
    if paquete_declarado is not None and paquete_declarado != v["version"]:
        problemas.append(
            f"package_version: STATE.release declara {paquete_declarado} y "
            f"__init__.py declara {v['version']}; declaran la version ACTIVA "
            "del arbol y tienen que ser la misma"
        )

    return tuple(problemas)


def estado(raiz: Path) -> Estado:
    """La respuesta. Falla si una verdad no se puede leer.

    Todas las lecturas ocurren ANTES de comparar nada. Si `tag_vcs` es
    `None` —un clon sin tags— no se inventa una release: se dice que no
    hay tag y se sigue. Si una verdad falta, esto lanza en vez de devolver
    un estado parcial, porque un estado parcial se parece mucho a un
    estado sano.
    """
    raiz = _exige_raiz(raiz)
    # El ROADMAP se lee UNA vez y se reparte. Leerlo dos veces —una para el
    # bloque, otra para las ventanas— es la misma trampa que B14 cerro en
    # STATE.yaml: dos lectores del mismo fichero pueden discrepar en
    # silencio, y aqui discreparia sobre la misma verdad.
    ventanas = ventanas_del_roadmap(raiz)
    v: dict[str, Any] = {
        "bloque": bloque_del_roadmap(raiz),
        "version": version_activa(raiz),
        # R0.B: `release.package_version` entra en la verdad. Antes no se
        # leia y por eso el contrasalto de B29 daba `coherente: true` con el
        # campo en la version anterior. Ver `package_version_declarada`.
        "package_version": package_version_declarada(raiz),
        "release": release_declarada(raiz),
        "tag_vcs": tag_real(raiz),
        "tests_declarados": total_declarado(raiz),
        "tests_reales": total_colectado(raiz),
        "workitem_state": workitem_de_state(raiz),
        "workitem_current": workitem_de_current(raiz),
    }
    return Estado(
        objetivo=_objetivo_del_bloque(raiz, v["bloque"]),
        roadmap="ROADMAP.md",
        ventanas=ventanas,
        contradicciones=_contradicciones(v, raiz=raiz, ventanas=ventanas),
        **v,
    )


def _argumentos(argv: list[str] | None = None) -> argparse.Namespace:
    """La linea de ordenes. `argparse` de verdad, no un `sys.argv` ignorado.

    MEDIDO en B23, y es el motivo de que esto exista: antes de B23 este script
    no leia `sys.argv` en ninguna parte, y `project_truth.py --raiz /tmp
    --inventado lo-que-sea` salia con `rc=0` imprimiendo la verdad del
    repositorio real. Un flag que se ignora en silencio no es una opcion: es
    una afirmacion falsa sobre lo que el instrumento acaba de medir, con la
    autoridad de quien responde «¿donde esta el proyecto?». Con `argparse`, un
    argumento desconocido sale con 2 y dice cual es.
    """
    parser = argparse.ArgumentParser(
        prog="project_truth.py",
        description="La respuesta unica a '¿donde esta el proyecto y que toca despues?'.",
    )
    parser.add_argument(
        "--raiz",
        type=Path,
        default=None,
        metavar="RUTA",
        help=(
            "la raiz del proyecto que se mide. Por defecto, el repositorio donde vive este script."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Imprime la respuesta. Sale 1 si el proyecto se contradice a si mismo.

    Que un `print` salga con 1 es lo que permite usarlo en CI sin un
    envoltorio: el codigo de salida ES el veredicto, no una decoracion
    al red de un log.
    """
    args = _argumentos(argv)
    raiz = args.raiz if args.raiz is not None else RAIZ_POR_DEFECTO
    try:
        e = estado(raiz)
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
