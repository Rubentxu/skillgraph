"""`DulwichGitHistory`: la ascendencia real, con `dulwich` como unico lector.

# POR QUÉ ESTE ADAPTADOR ES TAN PEQUEÑO Y LA FRONTERA ESTÁ EN EL PUERTO

Todo lo que hay aquí es traducir `dulwich` al dataclass `Commit` del puerto.
Ni una decisión, ni un default, ni una consulta a la base de datos. Eso es lo
que hace que el puerto seaagoable de probar sin git y que la Implementación
sea trivial de cambiar a otra biblioteca.

Lo que **no** está aquí, deliberadamente:

  - **No se cachea nada.** Un `Commit` construido es un valor pequeño y un
    repo con 100k commits no se recorre entero en el uso normal. Un caché
    sería estado mutable compartido entre instancias del adaptador, que es
    justo lo que AGENTS 1.4 prohíbe sin una interfaz con invalidación.
  - **No se capturan excepciones de git.** Un repositorio corrupto o un
    objeto que falta en disco lanza desde `dulwich`, y se propaga. El puerto
    declara que `None` significa «no lo tiene», no «no se pudo leer», y
    tragarse las dos cosas sería exactamente la mentira que el docstring
    del puerto prohíbe.

# LA CAPA DE SEGURIDAD, Y POR QUÉ NO ESTÁ EN EL PUERTO

`es_ancestro` y `ancestros_de` recorren el grafo, y un grafo de commits es un
DAG: no tiene ciclos por construcción, pero **un clon superficial sí es finito
y truncado**, y un `ref` mal escrito puede apuntar a una rama infinita. Un
recorrido sin tope no termina nunca.

Por eso `ancestros_de` recibe `limite`, y la implementación **usa un tope
interno cuando el llamante no pasa ninguno**. El valor por defecto está en
este fichero y no en el puerto porque es una decisión de ESTA implementación,
no del contrato: otro backend puede tener otro tope o ninguno.
"""

from __future__ import annotations

from pathlib import Path
from types import TracebackType

from skillgraph.core.errors import DulwichNotAvailableError
from skillgraph.platform.ports.git_history import Commit, CommitSha, GitHistory

#: Cuantos niveles se recorren cuando el llamante no dice. Es un tope de
#: seguridad, no una decision de producto: un `es_ancestro` que tiene que
#: bajar diez mil niveles casi siempre va a responder `False` igual, y un
#: recorrido sin tope sobre un clon superficial no termina.
PROFUNDIDAD_POR_DEFECTO = 10_000


def _repo_de(repo_root: Path):  # type: ignore[no-untyped-def]
    try:
        from dulwich.repo import Repo
    except ImportError as exc:  # pragma: no cover - dulwich es dependencia principal
        raise DulwichNotAvailableError(
            "dulwich no esta instalado; instala con `uv pip install skillgraph[git]`"
        ) from exc
    return Repo(str(repo_root))


def _sha(b: bytes) -> CommitSha:
    return b.decode("ascii")


def _iso(epoch: int) -> str:
    from datetime import UTC, datetime

    return datetime.fromtimestamp(epoch, tz=UTC).isoformat()


class DulwichGitHistory(GitHistory):
    """La ascendencia de un repositorio local, leida con `dulwich`.

    **POR QUÉ ES UN `contextmanager` Y NO UNA CLASE CON `__del__`.** Un
    `Repo` de dulwich toma un file handle del `.git` y hay que cerrarlo. La
    forma de no dejar un descriptor abierto es no tener un objeto con
    ciclo de vida implícito: se usa `with DulwichGitHistory(...) as h:`, y
    salir del bloque cierra. Un `__del__` no se ejecuta en el GC de CPython
    de forma determinista, y un `Repo` sin cerrar deja el índice bloqueado
    en Windows.

    El contexto ESTA en el contrato de uso, no en el Protocol: el Protocol
    declara lo que responde, no cómo se toma el repo. Un backend que hable
    con una API HTTP no tiene un repo que cerrar, y no por eso deja de
    cumplir el puerto.
    """

    def __init__(self, repo_root: Path, repo=None) -> None:  # type: ignore[no-untyped-def]
        self._repo_root = Path(repo_root)
        self._repo = repo if repo is not None else _repo_de(self._repo_root)

    # --- ciclo de vida -------------------------------------------------

    def close(self) -> None:
        if self._repo is not None:
            self._repo.close()
            self._repo = None

    def __enter__(self) -> DulwichGitHistory:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    # --- el puerto -----------------------------------------------------

    def commit(self, sha: CommitSha) -> Commit | None:
        if self._repo is None:
            raise DulwichNotAvailableError("el historial esta cerrado")
        try:
            c = self._repo[sha.encode("ascii")]
        except KeyError:
            # El sha no esta en este repo. Ver el docstring de `commit` en
            # el puerto: es `None` y no es error, y NO se distingue entre
            # «de otro repositorio», «reescrito» y «clon superficial».
            return None
        return Commit(
            sha=_sha(c.id),
            parents=tuple(_sha(p) for p in c.parents),
            authored_at=_iso(c.author_time) if c.author_time else "",
        )

    def existe(self, sha: CommitSha) -> bool:
        return self.commit(sha) is not None

    def es_ancestro(self, ancestro: CommitSha, descendiente: CommitSha) -> bool:
        if ancestro == descendiente:
            return self.existe(ancestro)
        _, vistos = self._recorrer(descendiente, limite=PROFUNDIDAD_POR_DEFECTO)
        return ancestro in vistos

    def ancestros_de(self, sha: CommitSha, *, limite: int | None = None) -> tuple[CommitSha, ...]:
        orden, _ = self._recorrer(sha, limite=limite)
        return orden

    # --- recorrido -----------------------------------------------------

    def _recorrer(
        self, sha: CommitSha, *, limite: int | None
    ) -> tuple[tuple[CommitSha, ...], frozenset[CommitSha]]:
        """(orden por cercanía en profundidad, conjunto de los visitados).

        **EL ORDEN QUE SE DEVUELVE, Y POR QUÉ ES EL QUE ES.** Anchura
        —nivel a nivel— y no profundidad, porque en profundidad el orden
        depende de cuál de los dos padres se visita primero, y eso solo lo
        decide el orden del tuple `parents`. En anchura, el primer elemento
        siempre es el propio commit y el segundo es un padre, y el orden de
        los dos padres solo decide el orden entre ellos, que sí es un hecho
        del grafo.

        El conjunto de visitados es lo que hace `es_ancestro` una sola vez en
        vez de un `commit()` por nivel: sin el, la comprobación sería O(n)
        llamadas al repo por pregunta.

        **EL CORTE ES POR ELEMENTOS, Y NO POR NIVEL — MEDIDO, NO ELEGIDO.**
        La primera versión comprobaba `len(orden) < tope` solo al principio
        de cada vuelta, y en anchura una vuelta añade el frente entero: un
        merge con dos padres devolvía 3 elementos con `limite=2`. Eso no es
        un tope, es una promesa que el número no cumple.

        Y el motivo de que sea por elementos y no por niveles es que es lo
        que quien llama espera: `limite=N` se lee como «dame N» y como
        `tupla[:N]`, y un tope por niveles devuelve o de menos o de mas según
        la forma del grafo.
        """
        tope = PROFUNDIDAD_POR_DEFECTO if limite is None else limite
        orden: list[CommitSha] = []
        vistos: set[CommitSha] = set()
        frontera = [sha]
        while frontera and len(orden) < tope:
            siguiente: list[CommitSha] = []
            for actual in frontera:
                if len(orden) >= tope:
                    break
                if actual in vistos:
                    continue
                vistos.add(actual)
                orden.append(actual)
                c = self.commit(actual)
                if c is None:
                    continue
                siguiente.extend(c.parents)
            frontera = siguiente
        return tuple(orden), frozenset(vistos)
