"""El libro de migraciones: que se aplico a esta base, y en que orden.

B12. Antes de este modulo, «la version del esquema» era `SCHEMA_VERSION = 1`
en `platform/schema.py`, escrita con `INSERT OR IGNORE` y **leida por nadie**
dentro de `storage.py`. MEDIDO en `.pipelinek/b12_preflight.md` §6, 0 de 5
preguntas en PASS:

- la version no se movia en 73 releases;
- borrar la tabla `schema_version` entera de una base y abrirla la dejaba
  recrear en silencio, luego la version era un DEFAULT y no un hecho;
- la unica migracion que existia, `_anade_column_claims_assertion_origin`,
  era una funcion escrita a mano **para una tabla**, porque SQLite no tiene
  `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`.

Las tres son la misma forma: un patron que se declara y no se sostiene.

**EL LIBRO REGISTRA, NO GOBIERNA.** `sincroniza` ejecuta TODAS las
migraciones y anota las que faltaban. La idempotencia la garantiza cada
migracion —comprueba su precondicion y no toca nada si ya esta—, no el
numero. Un libro que decidiera que ejecutar comparando versiones se
equivocaria en el caso que de verdad duele: una base restaurada de una
copia parcial, donde el esquema esta ahead y el libro atras. Ahi el libro
diria «esto ya se hizo» y no repararia nada. Ver `sincroniza`.

**POR QUE UN ID Y NO UN ENTERO.** Un entero como clave obliga a insertar en
medio de la lista para un hotfix, y un hotfix que se aplica a una base ya
migrada y a otra que no necesita un ORDEN, no un numero que valga para
todos. El prefijo numerico conserva el orden de lectura sin hacer que ese
orden sea la identidad: `0002_...` se puede insertar entre `0001_` y
`0003_` sin que las dos bases confundan sus IDs con sus posiciones.

**POR QUE `schema_version` NO SE BORRA.** La tabla existia y hay al menos un
test que la construye a mano. Se le da un trabajo real —el entero que
responde «que version tiene este proyecto»— en vez de dejar una tabla que
parece autoritativa y no lo es. Borrarla habria sido mas limpio y habria
sido tambien un cambio de contrato que nadie habia pedido.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from skillgraph.core.errors import SchemaTooNewError

__all__ = [
    "MIGRACIONES",
    "Migracion",
    "comprueba_que_no_sea_mas_nueva",
    "migraciones_anotadas",
    "sincroniza",
    "version_de_la_base",
    "version_declarada",
]

_Aplicar = Callable[[sqlite3.Cursor], None]


@dataclass(frozen=True, slots=True)
class Migracion:
    """Una migracion, con un identificable ESTABLE y un efecto idempotente.

    `id` es la identidad, no la posicion: dos instalaciones distintas pueden
    tener las migraciones en el mismo orden y aun asi no ser la misma base.
    """

    id: str
    aplicar: _Aplicar


def _anade_assertion_origin(cur: sqlite3.Cursor) -> None:
    """`claims.assertion_origin`: la primera migracion con historia.

    SQLite no tiene `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`, asi que la
    comprobacion va primero y el error de la carrera —que es lo que daria el
    segundo proceso— se traga SOLO si la columna existe ya. Se distingue por
    el NOMBRE del error: capturar `sqlite3.OperationalError` entero se
    tragaria tambien un disco lleno. Es el `check-then-act` que B2 sufrio,
    resuelto sin volver a meterlo.
    """
    columnas = {fila[1] for fila in cur.execute("PRAGMA table_info(claims)")}
    if "assertion_origin" in columnas:
        return
    try:
        cur.execute(
            "ALTER TABLE claims ADD COLUMN assertion_origin "
            "TEXT NOT NULL DEFAULT 'observed' CHECK (assertion_origin IN ("
            "'observed','derived-deterministically','agent-inferred',"
            "'human-asserted'))"
        )
    except sqlite3.OperationalError as exc:
        if "duplicate column name" not in str(exc).lower():
            raise


def _anota_installed_packs(cur: sqlite3.Cursor) -> None:
    """`installed_packs`: la tabla que B11 anadio sin mover la version.

    El DDL ya la crea con `CREATE TABLE IF NOT EXISTS`, luego el efecto
    sobre el esquema es nulo. Lo que NO es nulo es que **existio un cambio
    de esquema sin que la version se moviera**, y por eso queda anotado. Es
    la migracion que hace honesto al numero: sin ella, `SCHEMA_VERSION`
    volveria a ser un numero que dice «nada ha cambiado» cuando si ha
    cambiado.
    """
    cur.execute("SELECT 1 FROM installed_packs LIMIT 1")


MIGRACIONES: Final[tuple[Migracion, ...]] = (
    Migracion("0001_claims_assertion_origin", _anade_assertion_origin),
    Migracion("0002_installed_packs", _anota_installed_packs),
)


def version_declarada(migraciones: tuple[Migracion, ...] = MIGRACIONES) -> int:
    """La version que este codigo declara. DERIVADA, nunca literal.

    Que se olvide de subirla deja de ser posible: no hay ningun numero que
    mantener al dia en dos sitios. Un guard por AST comprueba que
    `SCHEMA_VERSION` sale de aqui y no de un literal.
    """
    return len(migraciones)


def migraciones_anotadas(cur: sqlite3.Cursor) -> tuple[str, ...]:
    """Que migraciones dice la base que se le aplicaron."""
    filas = cur.execute(
        "SELECT migration_id FROM schema_migrations ORDER BY migration_id"
    ).fetchall()
    return tuple(fila[0] for fila in filas)


def version_de_la_base(cur: sqlite3.Cursor) -> int:
    """La version que declara la base. 0 si no declara ninguna.

    Una base anterior a B12 tiene `schema_version` con un `1` que no quiere
    decir nada; se devuelve tal cual y la comparacion de mas abajo es la que
    decide. Devolver 0 para «no declarada» y no 1 para «vacia» distingue el
    caso de una base recien creada del de una base vieja.
    """
    fila = cur.execute("SELECT MAX(version) FROM schema_version").fetchone()
    return 0 if fila is None or fila[0] is None else int(fila[0])


def comprueba_que_no_sea_mas_nueva(cur: sqlite3.Cursor) -> None:
    """Falla si la base declara un esquema mas nuevo que este codigo.

    Abrir en silencio un esquema que no se conoce es la forma barata de
    perder datos en la siguiente escritura: todo parece funcionar hasta que
    una columna que el codigo espera no esta, y para entonces la escritura
    ya habia pasado. Fallar aqui es barato; fallar alla, no.
    """
    declarada = version_de_la_base(cur)
    if declarada > version_declarada():
        raise SchemaTooNewError(
            f"la base declara el esquema {declarada} y este codigo entiende hasta "
            f"el {version_declarada()}. Actualiza skillgraph: abrirla con este codigo "
            f"puede perder escrituras."
        )


def sincroniza(cur: sqlite3.Cursor) -> tuple[str, ...]:
    """Ejecuta TODAS las migraciones y anota las que faltaban.

    **EL LIBRO REGISTRA, NO GOBIERNA.** Ejecutar una migracion ya anotada
    no es un error ni un desperdicio: cada una comprueba su estado antes de
    tocar nada, luego volver a correrla no cambia la base. La version se
    podria haber guardado de correr solo las que faltan, y parece mas
    eficiente. Se eligio lo contrario por el caso que de verdad duele:

        una base restaurada de una copia PARCIAL tiene las dos cosas rotas
        a la vez —el libro atrasado y el esquema con una columna que falta—.

    Un libro que gobierna se cree que la base esta bien porque el libro lo
    dice, y no repara nada. Un libro que registra las repara siempre. El
    coste de ejecutarlas todas son unas cuantas comprobaciones de
    precondicion por abrir, y el coste de no hacerlo es un fallo
    silencioso en la siguiente escritura, que es el que no se ve.

    **EL LIMITE DE ESTA DECISION, DICHO.** Una migracion que transforme
    datos en vez de comprobar un precondicion seria cara de correr en cada
    apertura. Cuando llegue, la respuesta es que esa migracion marque su
    propio criterio de «ya aplicada» y lo deje explicito —no que esta
    funcion vuelva a hacer de puerta sin avisar—. Hoy las dos son
    comprobaciones de precondicion, que es lo que hace que la decision
    salga gratis.

    Devuelve los identificadores **nuevos**, no los ejecutados: corrida
    dos veces sobre una base al dia devuelve la tupla vacia, que es lo que
    un guard necesita para distinguir «no habia nada que hacer» de «no se
    hizo nada».
    """
    ya = frozenset(migraciones_anotadas(cur))
    nuevas: list[str] = []
    for migracion in MIGRACIONES:
        migracion.aplicar(cur)
        if migracion.id in ya:
            continue
        cur.execute(
            "INSERT OR IGNORE INTO schema_migrations(migration_id, applied_at) "
            "VALUES (?, datetime('now'))",
            (migracion.id,),
        )
        nuevas.append(migracion.id)
    _reescribe_version_si_cambia(cur)
    return tuple(nuevas)


def _reescribe_version_si_cambia(cur: sqlite3.Cursor) -> None:
    """Deja la version declarada igual a la del codigo, sin escribir si ya lo esta.

     **ESTO ES UNA REGRESION QUE INTRODUJE Y MEDI, no una precaution
     teorica.** La primera version de `sincroniza` hacia
     `DELETE FROM schema_version` seguido de `INSERT` SIEMPRE. Antes era
     `INSERT OR IGNORE`, que tras la primera apertura es un no-op: abrir no
     escribia nada. Con la version nueva, cada apertura de cada proceso
     tomaba la transaccion de escritura, y con los ocho procesos
     concurrentes de `test_b2_real_concurrency` uno se quedaba sin su turno
     —lo que se ve es que se esperaban 8 autores distintos y havia 7—.

     Medido antes de arreglar: tres corridas del test dan 1 verde, 1 verde, 1
     ROJO. Es un fallo de concurrencia, asi que se manifesta de forma
     intermitente; el numero «rojo 1 de 3» es tan diagnostico como el
    aserto de que las ocho filas llegaron.

     El arreglo es el que corresponde a la pregunta que se estaba
     respondiendo mal: la tabla ya dice la version correcta, y reescribirlo
     no responde nada. Solo se escribe cuando la respuesta cambia, que es
     exactamente cuando se sube una base.
    """
    objetivo = version_declarada()
    actual = version_de_la_base(cur)
    if actual == objetivo:
        return
    cur.execute("DELETE FROM schema_version")
    cur.execute("INSERT INTO schema_version(version) VALUES (?)", (objetivo,))
