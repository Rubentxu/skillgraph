"""Fixtures y configuración compartida para la suite de SkillGraph.

Reglas de la estrategia de tests (external/blueprint-v1/plan/ESTRATEGIA-DE-TESTS.md):
- Fixtures sin credenciales, red ni proveedor LLM.
- Aislamiento: cada test que toque el sistema de archivos recibe un
  `tmp_path` propio (pytest lo inyecta automáticamente). Aquí solo
  exponemos fábricas deterministas.
"""

from __future__ import annotations

import hashlib
import os
import pathlib
import sqlite3
import subprocess
from collections.abc import Iterator
from contextlib import suppress
from pathlib import Path
from typing import Any

import pytest

from skillgraph.platform.storage import Storage

RAIZ = Path(__file__).resolve().parent.parent

# ===========================================================================
# B22 — la suite no puede cambiar el contenido del arbol de trabajo REAL
# ===========================================================================
#
# Por que esto vive en conftest y no en un modulo de guard
# -------------------------------------------------------
# Porque la propiedad es sobre la CORRIDA COMPLETA, y un guard suelto solo
# ve los tests que se legone al pedir. Aqui se instrumenta la sesion entera,
# que es la unica ventana en la que la rotura se produjo: MEDIDO, durante la
# corrida completa `src/skillgraph/__init__.py` estuvo 1214 de ~197000
# lecturas con `__version__ = "7.7.7"` en vez de `0.32.7.dev0`, y ese fue el
# contenido que `measure_b9_gate_1_0.py` leyo como su baseline —con lo que
# su predicado de reproducibilidad revento y el gate entero perdio su
# informe. MEDIDO, 25 escrituras que cambian contenido de un fichero
# versionado, en tres ficheros de test.
#
# «Escribir» y «cambiar» NO son lo mismo
# --------------------------------------
# Un `finally` que restaura los bytes originales ESCRIBE y NO CAMBIA: es el
# mecanismo correcto de un test que deforma y restaura, y contarlo como
# infraccion haria que este guard pidiera prohibiting exactly lo que la
# property exige. Se comparan los bytes antes y despues. MEDIDO: el propio
# `finally` de `measure_b9_gate_1_0.py` y el de `test_b15` escriben dos
# ficheros versionados y NO los cambian; contarlos habria pedido que se
# prohibiera restaurar, que es lo unico que permite medir.
#
# Por que «versionado por git» y no «dentro del arbol»
# --------------------------------------------------
# El arbol tambien contiene lo que no es fuente —coberturas paralelas,
# artefactos de la receta, temporales—, y ahi los cambios no rompen a nadie.
# Lo que rompe es que un fichero que git versiona tenga otro contenido
# mientras un instrumento lo esta leyendo. La lista la dice `git ls-files`:
# escrita a mano se queda vieja en silencio.
#
# LIMITES DECLARADOS, y no sonjecture
# - Una escritura hecha por un SUBPROCESO no pasa por estos envoltorios.
# - Se envuelven `write_text`, `write_bytes` y `os.utime`. Nada mas.
_ESCRITURAS_AL_ARBOL_REAL: list[str] = []
# Contador de TODAS las escrituras a ficheros versionados, cambian o no el
# contenido. Existe para el contrasalto del guard: si el envoltorio dejara de
# estar puesto —porque alguien refactoriza y el parche ya no aplica— la lista
# de infracciones se vacia y el guard pasaria en VERDE sin haber mirado nada.
# Un guard que solo sabe dar verde no mide. Este numero es lo que demuestra
# que el instrumento estaba vivo durante la corrida.
_ESCRITURAS_OBSERVADAS: list[str] = []
# Los ficheros de test que LLEGARON A EJECUTARSE en esta sesion. Lo necesita
# el guard por una razon medida: «esta declaracion no se uso» y «el modulo
# de esa declaracion no corrio» son dos cosas distintas, y confundirlas
# obliga a que el guard solo puedaicloudarse corriendo la suite entera.
_MODULOS_EJECUTADOS: set[str] = set()


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    """Anota que ficheros de test han llegado a ejecutarse de verdad.

    Se cuenta en el reporte, que es donde se sabe que el test CORRIO, y no
    en la colecta, que solo dice que se llego a mirar. Un modulo que se
    colecta y no se ejecuta —por un `skip`, o porque se filtra— no puede
    usarse para juzgar si su declaracion de excepcion sigue viva.
    """
    if report.when == "call":
        _MODULOS_EJECUTADOS.add(Path(report.nodeid.split("::", 1)[0]).name)


def _ficheros_versionados() -> frozenset[Path]:
    """Lo que git versiona, resuelto. Lo dice git, no una lista de aqui."""
    proc = subprocess.run(
        ["git", "-C", str(RAIZ), "ls-files", "-z"], capture_output=True, check=False
    )
    if proc.returncode != 0:
        # Sin git no hay criterio derivable: se registra y el guard lo dira,
        # en vez de fingir que el arbol esta limpio.
        _ESCRITURAS_AL_ARBOL_REAL.append(
            f"no se pudo leer `git ls-files` (rc={proc.returncode}): la propiedad "
            "necesita saber que ficheros versiona git"
        )
        return frozenset()
    return frozenset(
        (RAIZ / rel.decode("utf-8")).resolve() for rel in proc.stdout.split(b"\0") if rel
    )


def _marco_del_escritor() -> str:
    """Quien esta escribiendo, leido de la traza viva.

    ``_marco_del_escritor`` se evalua como ARGUMENTO de quien registra, asi
    que el registro todavia no esta en la pila: el ultimo frame util es el
    que precede al envoltorio.
    """
    import traceback

    pila = traceback.extract_stack()
    # Los dos ultimos frames son el envoltorio y esta misma funcion.
    for marco in reversed(pila[:-2]):
        if marco.filename == __file__:
            continue
        return f"{Path(marco.filename).name}:{marco.lineno} {marco.name}"
    return "<desconocido>"


@pytest.fixture(autouse=True, scope="session")
def _vigila_el_arbol_real() -> Iterator[None]:
    """Envolve las escrituras para registrar las que cambian un versionado.

    Se envuelve en la sesion y no por test porque la propiedad es sobre TODA
    la corrida: un escritor en un test es un escritor en la sesion. El
    envoltorio se devuelve a su sitio en el teardown aunque la sesion
    reviente, y una excepcion dentro del instrumentador NUNCA propaga: un
    guard que rompe la corrida que lo certify es peor que no tener guard.
    """
    versionados = _ficheros_versionados()
    originales = {
        "write_text": pathlib.Path.write_text,
        "write_bytes": pathlib.Path.write_bytes,
        "utime": os.utime,
    }

    def envuelve(superficie: str) -> None:
        original = originales[superficie]

        def envoltorio(self, *args: Any, **kwargs: Any):
            try:
                antes = (
                    hashlib.sha256(Path(os.fsdecode(self)).resolve().read_bytes()).hexdigest()
                    if superficie != "utime"
                    else None
                )
            except (OSError, TypeError, ValueError):
                antes = None
            resultado = original(self, *args, **kwargs)
            try:
                destino = args[0] if superficie == "utime" else self
                resuelto = Path(os.fsdecode(destino)).resolve()
                if resuelto in versionados:
                    despues = (
                        hashlib.sha256(resuelto.read_bytes()).hexdigest()
                        if resuelto.exists()
                        else None
                    )
                    relativo = resuelto.relative_to(RAIZ)
                    marco = _marco_del_escritor()
                    _ESCRITURAS_OBSERVADAS.append(f"{superficie} {relativo} <- {marco}")
                    if antes != despues:
                        _ESCRITURAS_AL_ARBOL_REAL.append(f"{superficie} {relativo} <- {marco}")
            except Exception:
                pass
            return resultado

        if superficie == "utime":
            os.utime = envoltorio  # type: ignore[assignment]
        else:
            setattr(pathlib.Path, superficie, envoltorio)

    try:
        for superficie in originales:
            envuelve(superficie)
        yield
    finally:
        pathlib.Path.write_text = originales["write_text"]  # type: ignore[method-assign]
        pathlib.Path.write_bytes = originales["write_bytes"]  # type: ignore[method-assign]
        os.utime = originales["utime"]  # type: ignore[assignment]


def pytest_collection_modifyitems(config: pytest.Config, items: list[Any]) -> None:
    """Manda el guard de B22 AL FINAL de la sesion, de forma determinista.

    Sin esto el guard solo veria las escrituras que le preceden, y un test
    colocado antes que el escritor pasaria en verde midiendo la mitad de la
    ventana. Moverlo por nombre —no por «el ultimo que se colecto», que
    cambia con el orden de import— es lo que hace que la medicion sea la
    misma en cada corrida.

    **Y SI NO ENCUENTRA SU OBJETIVO, FALLA — pero solo si el modulo se
    colecto.** MEDIDO: la primera version llevo el nombre del fichero escrito
    a mano en la constante del guard, y ese nombre no era el del fichero.
    `endswith` no devolvia nada, el hook movia cero items, el guard se
    quedaba donde estaba —en cabeza— y daba verde con diecinueve
    infracciones ya registradas a sus espaldas. El hook no fallo: hizo
    exactamente lo que se le pidio, sobre un nombre que no existia. Un guard
    que no se programa a si mismo en silencio es peor que no tener guard,
    porque ademas ocupa el hueco del que lo haria bien.

    Y el criterio de «fallar» es «el modulo se colecto y su test no
    aparece», NO «el test no aparece»: sin ese matiz, correr cualquier
    subconjunto que no incluya el fichero del guard —`pytest
    tests/test_b14_...`— acababa en INTERNALERROR, y un hook que rompe las
    corridas parciales no lo ejecuta nadie en local, que es justo cuando hace
    falta.
    """
    from tests.test_b22_arbol_real import TEST_DEL_GUARD

    modulo_del_guard, clase_del_guard, _test = TEST_DEL_GUARD.split("::", 2)
    cola = [i for i in items if i.nodeid.endswith(TEST_DEL_GUARD)]
    if cola:
        resto = [i for i in items if not i.nodeid.endswith(TEST_DEL_GUARD)]
        items[:] = [*resto, *cola]
        return
    # El criterio de «fallar» es «alguien de la CLASE del guard se colecto y el
    # guard no esta». MEDIDO: la primera version de esto miraba el FICHERO, y
    # con el harness de B22 salio un 4/4 FALSO: cada sonda «caia» por un
    # INTERNALERROR de este hook, no por su asercion. Correr un solo test del
    # fichero colecta el fichero entero y no colecta la clase del guard, luego
    # la condicion se cumplia y el hook reventaba. Cuatro sondas-contadas-
    # como-caidas que no midieron nada, que es la forma exacta que B18 probo
    # con el heredoc y que este harness existe para cazar.
    de_la_clase = [
        i
        for i in items
        if i.nodeid.split("::", 1)[0].endswith(modulo_del_guard)
        and f"::{clase_del_guard}::" in i.nodeid
    ]
    if not de_la_clase:
        # Nadie de la clase del guard esta en esta corrida: no hay nada que
        # programar, y la lista se devuelve intacta y sin ruido.
        return
    raise RuntimeError(
        "se colectaron tests de la clase del guard de B22 pero el guard no "
        f"aparece con ese nombre, y por lo tanto no se puede mover al final: "
        f"{TEST_DEL_GUARD!r}\n"
        "Si se ha renombrado el test o la clase, actualiza TEST_DEL_GUARD en "
        "tests/test_b22_arbol_real.py. Un hook que no encuentra su objetivo no "
        "puede callarse: en silencio devuelve la coleccion intacta y el guard "
        "se queda donde esta."
    )


@pytest.fixture
def fixtures_dir() -> Path:
    """Raíz de fixtures versionadas: `tests/fixtures/`."""
    return Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def tmp_data_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Directorio de datos aislado y variable de inyección para el núcleo.

    Cada test recibe un `tmp_path` único (pytest) y el helper fija las
    variables de entorno que el núcleo debe respetar durante este test
    (skillgraph todavía no las lee; el contrato se introduce en e1-1).
    """
    root = tmp_path / "skillgraph-data"
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("SKILLGRAPH_DATA_ROOT", str(root))
    yield root
    # monkeypatch restaura las variables automáticamente al salir del test.


@pytest.fixture(autouse=True)
def storage_cleanup(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Cierra todo ``Storage`` creado durante el test, sin opt-in por módulo.

    ``Storage`` expone ``close()`` y context manager (WI-15 / v0.15.0), pero
    muchos tests históricos construyen la instancia en helpers o fixtures
    locales y nunca la cierran. Cada uno deja una ``sqlite3.Connection``
    abierta, que CPython reporta como ``ResourceWarning: unclosed database``
    cuando el GC la reclama.

    Antes de WI-40 el cleanup era opt-in (``storage_cleanup`` como fixture
    normal) y solo lo adoptaban 6 ficheros; los ~154 creators restantes
    fugaban. Al ser ``autouse=True`` el cierre pasa a ser una invariante
    de la suite en vez de una disciplina por fichero.

    El cierre ocurre en orden inverso al de construcción para respetar
    dependencias de teardown. No necesita proteccion extra: `Storage.close()`
    ya es idempotente y suprime `sqlite3.ProgrammingError`, asi que una
    instancia que el test cerro con `with` no rompe el teardown.

    No se introduce un ``__del__`` en producción: la propiedad de la
    conexión sigue siendo del que la abre (AGENTS.md §8, R2).
    """
    created: list[Storage] = []
    original_init = Storage.__init__

    def tracked_init(storage: Storage, path: str | Path) -> None:
        original_init(storage, path)
        created.append(storage)

    monkeypatch.setattr(Storage, "__init__", tracked_init)
    yield
    for storage in reversed(created):
        storage.close()


@pytest.fixture(autouse=True)
def sqlite_cleanup(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Cierra las conexiones ``sqlite3`` crudas creadas durante el test.

    Complementa a `storage_cleanup`, que solo ve las instancias de
    ``Storage``. Quedan conexiones sueltas por dos motivos:

    1. Tests que abren la conexión directamente (``sqlite3.connect``) para
       inspeccionar o sembrar la base: helpers de verificación de CLI,
       ``EventLog`` sobre ``:memory:`` y aserciones de importer.
    2. ``with sqlite3.connect(path) as conn`` NO cierra la conexión: el
       context manager de ``sqlite3`` solo confirma la transacción. Quien
       aplica el idiom de los context managers espera un cierre que no existe.

    El fixture envuelve ``sqlite3.connect`` y cierra en teardown, en orden
    inverso, todo lo que el test dejó abierto. Es la misma invariante que
    `storage_cleanup`, pero para la clase de fuga que aquel no puede ver.

    Se instrumenta el punto de creación en vez de parchear los ~10 sitios
    uno a uno porque: (a) ``with sqlite3.connect`` es un error sistémico, no
    un descuido puntual, y corregirlo a mano no cierra la clase de fuga; y
    (b) la suite no tiene fixtures ``module``/``session`` que reutilicen una
    conexión entre tests, así que cerrar al final de cada test nunca pisa
    recursos compartidos.
    """
    created: list[sqlite3.Connection] = []
    original_connect = sqlite3.connect

    def tracked_connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        conn = original_connect(*args, **kwargs)
        created.append(conn)
        return conn

    monkeypatch.setattr(sqlite3, "connect", tracked_connect)
    yield
    for conn in reversed(created):
        # Una conexión ya cerrada o en estado inválido no debe enmascarar el
        # resultado real del test: el cleanup nunca es el motivo del fallo.
        with suppress(sqlite3.Error):
            conn.close()
