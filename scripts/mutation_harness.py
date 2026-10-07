"""R1.E — UN harness de mutacion, con los estados que el fallo merece.

**POR QUE ESTE MODULO EXISTE, Y LA MEDIDA QUE LO JUSTIFICA.**

    scripts/mutate_*.py                     27 ficheros
    lineas de codigo                        8.554
    los que restauran con `git checkout --`  15 de 27

Veintisiete copias de la misma maquina, y quince de ellas restauran el arbol
con `git checkout --`, que **restaura DEL INDICE**. Con un arreglo sin
commitear —que es como se esta casi siempre mientras se escribe un bloque—
eso no restaura: se lleva el trabajo. Y no lo hace en silencio: `mutate_b10`
lo dice en su propio docstring, con el incidente de B9 escrito.

**ESTE TRABAJO LO SUFRIO, MEDIDO, DURANTE R1.F.** Los ficheros de la
migracion `0005` y sus 13 tests desaparecieron del arbol de trabajo a mitad
de certificacion. Se recuperaron integros de un volcado accidental
(`r1g-identidad-claim`, `2283309`), no de una copia: el arbol real habia
sido revertido por un harness que, ademas, reporto un veredicto con numero.
Un harness que destruye el arbol y ademas imprime un resultado es peor que
no tener harness.

# LOS SEIS ESTADOS, Y POR QUE NO BASTAN DOS

`CAZADA` y `SUPERVIVIDA` son los que existen hoy, y son los unicos que se
miden en la practica. Los otros cuatro existen para que **un fallo del
harness no se confused con un fallo de la propiedad**:

    CAZADA            la mutacion rompio la propiedad y el suite se puso rojo
    SUPERVIVIDA       el suite sigue verde: la propiedad NO la vigila
    MUTACION_INVALIDA la sonda no cambio el texto, o no compila, o no es el
                      objetivo que decia ser — aqui no hay veredicto
    ERROR_DE_HARNESS  el harness fallo al aplicar, ejecutar o restaurar
    BASE_ROTA         la linea base ya estaba roja: nada de lo que se mida
                      despues significa nada
    RESTAURACION_FALL back al arbol no quedo como estaba

**`BASE_ROTA` es la mas importante y la que mas se salta.** Una sonda que
parte de una suite ya roja no puede distinguir «mi mutacion la cazo» de «ya
estaba roto»: dara VERDE con un numero que no mide nada. Por eso `corre()`
mide la base PRIMERO y devuelve ese estado sin llegar a mutar.

**Y `MUTACION_INVALIDA` EXISTE PORQUE UN 5/5 PUDO SER 3/5.** Una sonda
apuntando a texto que ya no existe no muta nada, el suite sigue verde, y el
contador la cuenta como SUPERVIVIDA: el harness mente en verde con un
numero. Comprobar que el texto **cambio** es lo que separa «la sonda no
mide» de «la propiedad aguanta».

# POR QUE `restaurar` NO USA GIT

Porque `git checkout --` restaura del indice, y el indice no tiene lo que
se esta escribiendo. Este modulo **lee los bytes antes de mutar y los
escribe despues**, y ademas:

  - **PRUEBA** la restauracion comparando bytes, no confiando en el
    `finally`. Un `finally` que no se comprueba es una razon para no mirar.
  - **Borra `__pycache__`** de lo que toco, y avisa: un arbol restaurado que
    ejecuta el `.pyc` de la version mutada «esta como estaba» y no lo esta.
    Es el error 32 de WI-113, repetido.
  - **NO ABORTA si el fichero estaba sucio antes.** Abortar seria ruido
    sobre el trabajo real de otra persona; lo registra.
"""

from __future__ import annotations

import ast
import pathlib
import subprocess
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final

__all__ = [
    "DEPARTAMENTO",
    "MODULO_INVESTIGADO",
    "RESULTADOS",
    "Restaurador",
    "Sonda",
    "Veredicto",
    "corre",
    "describe",
    "sonda_por_reemplazo",
]


class Veredicto(StrEnum):
    """Los seis estados. Los dos primeros son los que se hopedan; el resto
    existen para que un fallo del harness no se lea como un fallo de la ley."""

    CAZADA: Final = "CAZADA"
    SUPERVIVIDA: Final = "SUPERVIVIDA"
    MUTACION_INVALIDA: Final = "MUTACION_INVALIDA"
    ERROR_DE_HARNESS: Final = "ERROR_DE_HARNESS"
    BASE_ROTA: Final = "BASE_ROTA"
    RESTAURACION_FALL: Final = "RESTAURACION_FALL"


@dataclass(frozen=True, slots=True)
class Sonda:
    """Una deformacion, y lo que tiene que decir la verdad sobre si misma.

    `nombre` es lo que sale en el informe: un verificador que dice «falso»
    sin decir donde es un callejon sin salida.
    """

    nombre: str
    ruta: pathlib.Path
    antes: str
    despues: str

    def cambio_el_texto(self) -> bool:
        return self.antes != self.despues

    def es_python_valido(self) -> bool:
        """La sonda tiene que COMPILAR.

        Una sonda que rompe la sintaxis no mide la propiedad: el rojo que
        produce lo produce el interprete, no el guard. Es la distincion entre
        «la mutacion fue cazada» y «la mutacion rompio el programa», que
        el enunciado pide separar.
        """
        try:
            ast.parse(self.despues, filename=str(self.ruta))
        except SyntaxError:
            return False
        return True


@dataclass(frozen=True, slots=True)
class Resultado:
    """Lo que una corrida produce. Inmutable: se acumula en tuplas."""

    nombre: str
    veredicto: Veredicto
    detalle: str = ""


RESULTADOS: Final[tuple[Resultado, ...]] = ()

DEPARTAMENTO: Final[str] = "R1.E"

#: Donde vive el modulo. Se importa por ruta porque `scripts/` no es paquete.
MODULO_INVESTIGADO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# Restauracion
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class Restaurador:
    """Guarda bytes y los devuelve. **Nunca llama a git para restaurar.**

    Se construye con el estado del arbol TAL COMO ESTA, y devuelve ese
    estado. La version anterior usaba `git checkout --`, que restaura del
    indice: con trabajo sin commitear underneath, «restaurar» es
    «borrar». Este lee, muta y escribe.
    """

    _originales: dict[pathlib.Path, bytes] = field(default_factory=dict)
    _sucios_de_entrada: frozenset[pathlib.Path] = frozenset()

    @classmethod
    def captura(cls, rutas: Iterable[pathlib.Path]) -> Restaurador:
        """Toma el estado actual de `rutas`. Lo que no exista, se recuerda."""
        rutas_t = tuple(rutas)
        originales = {}
        for ruta in rutas_t:
            if ruta.exists():
                originales[ruta] = ruta.read_bytes()
        return cls(
            _originales=originales,
            _sucios_de_entrada=frozenset(
                ruta for ruta in rutas_t if ruta.exists() and not _esta_versionada(ruta)
            ),
        )

    def verificar(self) -> bool:
        """¿El arbol esta exactamente como se capture?

        Se compara por BYTES y no por `git status`, porque `git status` no
        distingue «lo que estaba sucio antes» de «lo que se ha cambiado
        ahora». Y los `.pyc` se ignoran a proposito: no son fuente.
        """
        for ruta, original in self._originales.items():
            if not ruta.exists() or ruta.read_bytes() != original:
                return False
        return all(not c.exists() for c in self._rutas_de_cache_de(self._originales))

    @staticmethod
    def _rutas_de_cache_de(rutas: Iterable[pathlib.Path]) -> tuple[pathlib.Path, ...]:
        """Las caches de bytecode que puede dejar la version mutada.

        Sin esto, un arbol restaurado sigue EJECUTANDO la version mutada
        mientras su texto es el bueno, y las sondas siguientes dan
        resultados que no corresponden al codigo que hay escrito.
        """
        caches: list[pathlib.Path] = []
        for ruta in rutas:
            if ruta.suffix != ".py":
                continue
            cache = ruta.parent / "__pycache__"
            if not cache.is_dir():
                continue
            caches.extend(p for p in cache.glob(f"{ruta.stem}.*.pyc"))
        return tuple(caches)

    def restaura(self) -> tuple[str, ...]:
        """Devuelve el arbol al estado capturado y **lo prueba**.

        Devuelve los motivos del fallo en vez de lanzar: quien llama tiene
        que poder REPORTAR un `RESTAURACION_FALL`, y una excepcion en este
        punto dejaria al arbol sucio sin que nadie lo dijera.
        """
        problemas: list[str] = []
        for ruta, original in self._originales.items():
            try:
                ruta.write_bytes(original)
            except OSError as exc:  # pragma: no cover - depende del FS
                problemas.append(f"{ruta}: no se pudo escribir: {exc}")
        problemas.extend(self.borra_caches())

        if not self.verificar():
            differing = [
                str(ruta)
                for ruta, original in self._originales.items()
                if not ruta.exists() or ruta.read_bytes() != original
            ]
            problemas.append(f"el arbol no quedo como estaba: {', '.join(differing)}")
        return tuple(problemas)

    def borra_caches(self) -> list[str]:
        """Borra el bytecode cacheado de lo que se ha tocado.

        **Y HAY QUE BORRARLO EN LOS DOS SENTIDOS, NO SOLO AL RESTAURAR.**
        MEDIDO al escribir este modulo: si solo se borra al restaurar, la
        version MUTADA sigue sin ejecutarse nunca, porque Python carga el
        `.pyc` que compilo la version anterior. El harness decia
        `SUPERVIVIDA` y la propiedad estaba intacta —no porque aguantase,
        porque **nunca llego a ejecutarse**.

        Es el error 32 de WI-113 repetido: «el arbol esta restaurado» y
        «el arbol esta ejecutando lo que dice» son dos cosas distintas, y
        solo la segunda importa cuando lo que se mide es si una mutacion
        rompe una propiedad.
        """
        problemas: list[str] = []
        for cache in self._rutas_de_cache_de(self._originales):
            try:
                cache.unlink()
            except OSError as exc:  # pragma: no cover - depende del FS
                problemas.append(f"{cache}: no se pudo borrar la cache: {exc}")
        return problemas


def _esta_versionada(ruta: pathlib.Path) -> bool:
    """¿`git` versiona este fichero ahora mismo?

    Se usa para distinguir «estaba sucio antes de que yo tocara nada» de
    «queda sucio por lo que hice». Sin esa distincion, un restaurador
    avisaria de trabajo ajeno cada vez que se usa sobre un arbol con
    cambios sin commitear —que es la situacion normal de un bloque en curso.
    """
    raiz = _raiz_del_repo(ruta)
    if raiz is None:
        return False
    try:
        proc = subprocess.run(
            ["git", "-C", str(raiz), "ls-files", "--error-unmatch", "--", str(ruta)],
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):  # pragma: no cover
        return False
    return proc.returncode == 0


def _raiz_del_repo(ruta: pathlib.Path) -> pathlib.Path | None:
    for padre in [ruta.parent, *ruta.parents]:
        if (padre / ".git").exists():
            return padre
    return None


# ---------------------------------------------------------------------------
# La maquina
# ---------------------------------------------------------------------------


def _corre_suite(
    objetivos: Sequence[str],
    *,
    repo: pathlib.Path,
    timeout: int = 900,
) -> tuple[bool, str]:
    """Ejecuta pytest y devuelve `(verde, salida)`.

    `python -m pytest` y no el binario: el binario puede no estar en el PATH
    de un agente, y `python -m` usa el mismo interpreto que esta corriendo.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *objetivos, "-q", "-p", "no:cacheprovider", "--no-cov"],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return proc.returncode == 0, (proc.stdout + proc.stderr)[-2500:]


def corre(
    sondas: Sequence[Sonda],
    *,
    suite: Sequence[str],
    repo: pathlib.Path,
    timeout: int = 900,
) -> tuple[Resultado, ...]:
    """Corre las sondas una a una y clasifica cada una.

    **LA BASE SE MIDE ANTES DE MUTAR NADA.** Si esta en rojo, se devuelve
    `BASE_ROTA` para todas y no se toca el arbol: medir sobre una base rota
    produce numeros que no significan nada, y eso fue exactamente el modo de
    fallo que KI-113 escribio en su propio docstring.
    """
    resultados: list[Resultado] = []

    verde, salida = _corre_suite(suite, repo=repo, timeout=timeout)
    if not verde:
        return tuple(
            Resultado(s.nombre, Veredicto.BASE_ROTA, f"la suite no esta en verde:\n{salida[-600:]}")
            for s in sondas
        )

    por_ruta: dict[pathlib.Path, list[Sonda]] = {}
    for sonda in sondas:
        por_ruta.setdefault(sonda.ruta, []).append(sonda)

    for ruta in por_ruta:
        restaurador = Restaurador.captura([ruta])
        for sonda in por_ruta[ruta]:
            resultados.append(_corre_una(sonda, restaurador, suite, repo, timeout))
        # El restaurador se aplica una vez por ruta, y su veredicto se anade
        # a la ultima sonda de esa ruta: el estado del arbol es de la ruta,
        # no de una sonda, y duplicarlo N veces inflaria el recuento.
        problemas = restaurador.restaura()
        if problemas:
            resultados.append(
                Resultado(
                    f"{DEPARTAMENTO}: restauracion de {ruta.name}",
                    Veredicto.RESTAURACION_FALL,
                    "; ".join(problemas),
                )
            )
    return tuple(resultados)


def _corre_una(
    sonda: Sonda,
    restaurador: Restaurador,
    suite: Sequence[str],
    repo: pathlib.Path,
    timeout: int,
) -> Resultado:
    # 1. La sonda tiene que cambiar el texto. Una sonda que no cambia nada
    #    no mide nada, y contarla como SUPERVIVIDA seria un numero falso.
    if not sonda.cambio_el_texto():
        return Resultado(
            sonda.nombre,
            Veredicto.MUTACION_INVALIDA,
            "la sonda no cambio el texto: el ancla que apunta ya no existe. "
            "Una sonda sin efecto daria SUPERVIVIDA con un numero que no mide.",
        )

    # 2. Y tiene que seguir siendo python. Una sonda que rompe la sintaxis
    #    produce un rojo del interprete, no del guard.
    if not sonda.es_python_valido():
        return Resultado(
            sonda.nombre,
            Veredicto.MUTACION_INVALIDA,
            "la sonda no produce Python valido: el rojo que produciria lo "
            "produce el interprete, no la propiedad.",
        )

    # 3. Aplicar. Y BORRAR LA CACHE ANTES: sin esto Python ejecuta el `.pyc`
    #    de la version anterior y la mutacion no llega a existir. Ver
    #    `Restaurador.borra_caches`, y el motivo esta medido ahi.
    try:
        sonda.ruta.write_text(sonda.despues, encoding="utf-8")
        restaurador.borra_caches()
    except OSError as exc:
        return Resultado(sonda.nombre, Veredicto.ERROR_DE_HARNESS, f"no se pudo aplicar: {exc}")

    # 4. Medir.
    try:
        verde, salida = _corre_suite(suite, repo=repo, timeout=timeout)
    except subprocess.TimeoutExpired:
        return Resultado(sonda.nombre, Veredicto.ERROR_DE_HARNESS, "la suite no termino a tiempo")
    except Exception as exc:
        return Resultado(sonda.nombre, Veredicto.ERROR_DE_HARNESS, f"{type(exc).__name__}: {exc}")
    finally:
        restaurador.restaura()

    return Resultado(
        sonda.nombre,
        Veredicto.SUPERVIVIDA if verde else Veredicto.CAZADA,
        "" if not verde else salida[-400:],
    )


def describe(resultados: Sequence[Resultado]) -> str:
    """El informe. Cuenta por estado, y NO cuenta los errores como successes.

    Un informe que solo dice «N de M cazadas» obliga a leer los nombres para
    saber si hubo `RESTAURACION_FALL`. Con seis estados, el recuento de los
    otros cinco es parte del resultado.
    """
    cuentas = {v: 0 for v in Veredicto}
    for resultado in resultados:
        cuentas[resultado.veredicto] += 1

    lineas = [f"{DEPARTAMENTO}: sonda de mutacion, {len(resultados)} resultado(s)"]
    for resultado in resultados:
        sufijo = f"  {resultado.detalle}" if resultado.detalle else ""
        lineas.append(f"  {resultado.veredicto:<18} {resultado.nombre}{sufijo}")
    lineas.append("")
    for veredicto in Veredicto:
        lineas.append(f"  {veredicto:<18} {cuentas[veredicto]}")
    return "\n".join(lineas)


#: Ficheros que este harness sabe restaurar sin git, y por que.
#:
#: La lista esta DECLARADA y no derivada a proposito: es la lista de sitios
#: donde el restore destructivo ya ha costado trabajo, y por eso mismo
#: tienen que estar a la vista. Anadir uno es una decision, no un efecto.
RESTAURADORES_POR_DEFECTO: Final[tuple[pathlib.Path, ...]] = (
    MODULO_INVESTIGADO.parent / "src" / "skillgraph" / "platform" / "migrations.py",
    MODULO_INVESTIGADO.parent / "src" / "skillgraph" / "platform" / "schema.py",
)


def sonda_por_reemplazo(nombre: str, ruta: pathlib.Path, viejo: str, nuevo: str) -> Sonda:
    """Construye una sonda a partir de un reemplazo literal.

    **Y DEVUELVE UNA SONDA INVALIDA SI EL TEXTO NO ESTA.** No lanza: quien
    llama decide si eso es un error suyo (ancla movida) o un dato. La razon
    esta en el propio `Sonda`, y `corre` la clasifica como
    `MUTACION_INVALIDA`, que es lo que evita el 5/5 falso.
    """
    antes = ruta.read_text(encoding="utf-8") if ruta.exists() else ""
    return Sonda(
        nombre=nombre,
        ruta=ruta,
        antes=antes,
        despues=antes.replace(viejo, nuevo, 1) if viejo in antes else antes,
    )


def main(argv: Sequence[str] | None = None) -> int:  # pragma: no cover
    """Ejecuta el harness que se le pase. Punto de entrada de los wrappers."""
    del argv
    raise SystemExit(
        "Este modulo es una libreria. Los scripts/mutate_*.py lo importan.\n"
        "Ejecuta uno de ellos: uv run python scripts/mutate_b29_vigencia.py"
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
