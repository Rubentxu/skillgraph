"""Puerto de ascendencia de commits: el otro reloj, y por qué hace falta otro.

# LA MEDIDA QUE ABRE ESTE FICHERO

`.pipelinek/b32_measure.py` sobre una base real, con un claim real:

    P1  claim -> source (el commit del que vino)      SI
    P2  commit -> claims (al reves)                   SI
    P3  ascendencia de un commit (padre del padre)    NO
    P4  claims que nacieron DESPUES de un commit      NO
    P5  orden entre dos revisiones-commit             NO
    P6  por que se afirmo el claim                    NO

Lo que hay es un **PUNTO** —el commit en el que se vio el hecho— y no una
**CADENA**. La fila de B32 en el roadmap dice «no se puede responder cuándo
cambió una relación ni por qué», y la medición confirma las dos mitades: no
se puede responder el CUÁNDO porque no hay ascendencia, y no se puede
responder el POR QUÉ porque no hay nada que lo diga.

`P2` sale hoy por SQL escrito a mano contra `sources.git_commit_sha`, y sin
índice: `sources` solo tiene `idx_sources_project`. Funciona y es lento, que
es la forma que tiene un hueco de aparecer antes de que nadie lo mire.

# POR QUÉ NO SE REPARA EN `RevisionRegistry`

Porque `RevisionRegistry` ya declara lo contrario, y con la frase puesta:

> `seq` es el orden en que ESTE store aprendió de las revisiones. No es
> ascendencia de git —comparar SHAs es lexicográfico y arbitrario
> (`rev10 < rev9`)—.

Es un reloj **monótono de un almacén**. No sabe si A es padre de B, solo que A
se vio antes que B. Meter ascendencia ahí sería destruir la propiedad que lo
hace exacto —«son más y es exacto»— para hacerlo responder a una pregunta que
no puede responder bien.

Los dos relojes conviven y no se mezclan:

    RevisionRegistry  ->  orden de observacion local (un store, monótono)
    GitHistory        ->  ascendencia real de commits (varios stores, un grafo)

Y hay una asimetría que hay que decir: `seq` es un entero y **totalmente
ordenado**; la ascendencia es un **grafo parcial**, y dos commits de ramas
distintas NO tienen orden entre ellos. Un puerto que prometiera «el orden»
entre dos commits mentiría la mitad de las veces. Por eso el contrato de aquí
no ofrece `ordena(a, b) -> int`, sino `es_ancestro(a, b) -> bool`, que sí se
puede responder siempre.

# LA IDENTIDAD, Y POR QUÉ EL SHA Y NO OTRA COSA

El roadmap dice «con el SHA como identidad», y el SHA tiene una propiedad que
las alternativas no tienen: **es el contenido**. Un SHA no se reasigna, no se
puede mover a otro sitio y colisiona con otro commit solo si el contenido es
el mismo. Un contador de revisión no tiene nada de eso, y un nombre de rama se
mueve debajo de uno.

Y de ahí sale una consecuencia que hay que decidir de antemano: **un commit
reescrito cambia de SHA**, luego una referencia guardada al SHA viejo apunta a
un commit que ya no existe. Eso no se arregla, se DECLARA: `existe(sha)` es
una pregunta con respuesta `False`, no un error, porque el grafo de commits
cambia de forma underneath con `git rebase`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

#: Un SHA completo, 40 hex. Es un `str` y no un tipo nominal a proposito: el
#: dato entra de fuera (de `dulwich`, de una base, de una CLI) y un
#: `NewType` sin constructor seriallo no validaria nada, que es la ilusion de
#: seguridad que AGENTS 2.2 dice evitar.
CommitSha = str


@dataclass(frozen=True, slots=True)
class Commit:
    """Un nodo del grafo de commits.

    Inmutable y con `slots`: es un valor que se compara y se pasa, no un
    objeto que se muta mientras se recorre el grafo. Un `Commit` con la
    lista de padres mutable haría que «el mismo commit» pudiera tener dos
    padre, que es exactamente lo que git garantiza que no pasa.
    """

    sha: CommitSha
    parents: tuple[CommitSha, ...]
    authored_at: str = ""

    def es_merge(self) -> bool:
        """Mas de un padre. El caso de los dos padres es de donde sale el
        orden parcial que el contrato no puede resolver."""
        return len(self.parents) > 1


@runtime_checkable
class GitHistory(Protocol):
    """Ascendencia real de commits, con el SHA como identidad.

    **LO QUE NO ES.** No es el orden de aprendizaje de un almacén — eso es
    `RevisionRegistry`, y su docstring lo dice con estas palabras—. Este
    puerto responde preguntas sobre el GRAFO de commits, y el grafo no es
    un reloj: es parcial.

    Sin disco, sin red y sin reloj desde el punto de vista de quien lo usa:
    quien habla `dulwich` es la implementación.
    """

    def commit(self, sha: CommitSha) -> Commit | None:
        """El commit, o `None` si este historial no lo tiene.

        **`None` NO es un error y no es «no ha pasado todavía».** Es
        «este repositorio no tiene ese commit», que tiene tres causas que el
        puerto NO puede distinguir y no debe fingir que distingue: el sha es
        de otro repositorio, el commit se reescribió, o el historial es
        parcial (un clon superficial). La primera es un error de quien
        llama y las otras dos son hechos normales; distinguirlas es trabajo de
        la implementación, no del contrato.
        """
        ...

    def existe(self, sha: CommitSha) -> bool:
        """Si el historial tiene ese commit.

        Es `commit(sha) is not None` con un nombre que dice lo que quien
        llama quiere saber. Se declara aparte porque es la pregunta que se
        hace en un bucle sobre muchas referencias guardadas, y ahí lo que se
        necesita es el booleano sin construir el dataclass.
        """
        ...

    def es_ancestro(self, ancestro: CommitSha, descendiente: CommitSha) -> bool:
        """Si `ancestro` está en la historia de `descendiente`.

        **LA PREGUNTA QUE ESTE PUERTO EXISTE PARA CONTESTAR.**

        `False` significa «no se puede demostrar que lo sea», y eso incluye
        tres cosas que NO son lo mismo:

          - son ramas distintas (no hay relación de ancestro);
          - `ancestro` es posterior a `descendiente` (es al revés);
          - alguno de los dos no está en este historial.

        Fusionarlas es correcto porque **las tres se responden igual en la
        pregunta del roadmap**: «¿este hecho estaba antes que aquel?». Un
        `False` que no distingue «son ramas» de «no lo sé» sería peor que un
        error, porque el operador lo leería como «el hecho es posterior»,
        que es una afirmación distinta.

        Y es simétrica en falso: `es_ancestro(a, a)` es `True` para un
        commit que existe. La implementación lo resuelve en la raíz del
        recorrido, y se declara aquí para que quien implemente no tenga que
        decidirlo.
        """
        ...

    def ancestros_de(self, sha: CommitSha, *, limite: int | None = None) -> tuple[CommitSha, ...]:
        """Los ancestros alcanzables desde `sha`, en orden de cercanía.

        **POR QUÉ ES UN CONJUNTO Y NO UNA CADENA ORDENADA.** Porque no se
        puede. En una historia lineal sí, pero en cuanto hay un merge hay
        dos caminos de longitudes distintas y «el segundo ancestro» no
        significa nada. El orden que se puede garantizar es el de
        **cercanía en profundidad**, y por eso el nombre dice `ancestros_de` y
        no `cadena`.

        `limite` corta la profundidad y existe para que un historial enorme
        no se recorra entero cuando la pregunta es «¿estaba antes que este
        otro?». Un `limite` de 1 pregunta exactamente eso: ¿soy su padre?.

        Devuelve la tupla incluyendo el propio `sha`, que es lo que hace
        `es_ancestro` trivialmente correcto: un commit es ancestro de sí
        mismo y eso se declara en el contrato en vez de decidirse en cada
        implementación.
        """
        ...
