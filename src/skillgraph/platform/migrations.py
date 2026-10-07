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

import re
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


def _anade_object_entity_id(cur: sqlite3.Cursor) -> None:
    """`claims.object_entity_id`: el objeto pasa a poder ser una entidad (B25).

    Misma forma que `0001`, y por las mismas razones: `PRAGMA table_info`
    primero, y tragarse el error de la carrera SOLO si el error es el de columna
    duplicada —capturar `sqlite3.OperationalError` entero se tragaria tambien un
    disco lleno.

    **LO QUE ESTA MIGRACION NO HACE, Y ES LO IMPORTANTE.** SQLite **no
    revalida los CHECK sobre filas que ya estan**. El CHECK de «exactamente
    uno» protege las escrituras que vengan despues, y deja intactas las de
    antes: una base con datos previos tiene una restriccion parcial, fuerte
    hacia delante y blanda hacia atras. Reconstruir la tabla para cerrar el
    hueco era la alternativa, y es la operacion mas arriesgada que existe
    sobre una base con datos. Se elige la restriccion parcial y se dice, en vez
    de elegir la arriesgada y no decirlo.

    **EL `DEFAULT ''` NO ES COSMETICO.** Una columna `NOT NULL` anadida a una
    tabla con filas necesita un default, y el marcador tiene que ser un valor
    que `json.dumps` no produzca nunca: `''` cumple eso porque `json.dumps("")`
    es `'""'`.
    """
    columnas = {fila[1] for fila in cur.execute("PRAGMA table_info(claims)")}
    if "object_entity_id" not in columnas:
        try:
            cur.execute(
                "ALTER TABLE claims ADD COLUMN object_entity_id TEXT NOT NULL DEFAULT '' "
                "CHECK ((object_literal_json = '') <> (object_entity_id = ''))"
            )
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                raise

    # El indice se asegura SIEMPRE, y fuera del `if`, a proposito: hay dos
    # caminos que lo necesitan y solo uno pasa por el `ALTER`. Una base nueva
    # tiene la columna desde el `CREATE TABLE` y se saltaria el `ALTER` entero;
    # si el `CREATE INDEX` estuviera dentro, esa base se quedaria sin indice
    # para siempre, sin que nada fallara.
    #
    # Y no esta en `schema.py` porque ese DDL corre con `CREATE TABLE IF NOT
    # EXISTS`: sobre una base con la tabla vieja no la reconstruye, y un indice
    # sobre una columna que no existe revienta `executescript` entero — con lo
    # cual ABRIR la base falla, que es justo lo que la migracion viene a
    # arreglar. MEDIDO antes de decidirlo asi.
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_claims_object_entity "
        "ON claims(object_entity_id) WHERE object_entity_id <> ''"
    )


def _anade_ventanas_de_vigencia(cur: sqlite3.Cursor) -> None:
    """`0004` — B29: ventana de vigencia, supersesion y orden de revisiones.

    Misma forma que `0003`, y por las mismas dos razones: `PRAGMA table_info`
    primero, y tragarse el error de la carrera **solo** si es el de columna
    duplicada —capturar `sqlite3.OperationalError` entero se tragaria tambien
    un disco lleno.

    **LAS COLUMNAS VAN SIN DEFAULT, Y PORQUE.** Anadir una columna `NOT NULL` a
    una tabla con filas obliga a un default, y el default de
    `valid_from_revision` fecharia en el pasado toda afirmacion que existia
    antes de B29. Anulables y sin default: `NULL` es «no caduca», que es lo
    cierto de todo el grafo preexistente.

    **EL INDICE SE ASEGURA SIEMPRE, FUERA DEL `if`.** Hay dos caminos que lo
    necesitan y solo uno pasa por el `ALTER`: una base nueva tiene las columnas
    desde el `CREATE TABLE` y se saltaria el `ALTER` entero, y si el indice
    estuviera dentro se quedaria sin indice para siempre sin que nada fallara.

    Y no esta en `schema.py` porque ese DDL corre con `CREATE TABLE IF NOT
    EXISTS`: sobre una base con la tabla vieja no reconstruye nada, y un indice
    sobre una columna que no existe revienta `executescript` entero — con lo
    cual ABRIR la base falla, que es justo lo que la migracion viene a
    arreglar. MEDIDO en B25.
    """
    columnas = {fila[1] for fila in cur.execute("PRAGMA table_info(claims)")}
    for nombre in ("valid_from_revision", "valid_until_revision", "supersedes_claim_id"):
        if nombre not in columnas:
            try:
                cur.execute(f"ALTER TABLE claims ADD COLUMN {nombre} TEXT")
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise

    # La ventana se consulta por `(sujeto, revision)`, y el filtro es un
    # rango sobre dos columnas: sin indice, `claims_at_revision` es un escaneo
    # por sujeto en cada llamada, y B34 la va a llamar por cada verbo.
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_claims_ventana "
        "ON claims(subject_entity_id, valid_from_revision, valid_until_revision)"
    )


def _ddl_de_claims_con_ambito(ddl_previo: str) -> str:
    """El DDL de la tabla `claims` previa, con el ambito en su `UNIQUE`.

    **Y POR QUE SE DERIVA DE LA TABLA VIEJA Y NO ES UN DDL FIJO. ESTO SE
    MEDIO, Y FUE UN DEFECTO REAL DE LA PRIMERA VERSION.**

    La primera version traia un `CREATE TABLE claims` fijo, copiado del de
    `schema.py`. Con una base creada por el codigo actual daba igual, y con
    una base VIEJA reventaba:

        tests/test_b6_provenance.py::test_una_base_previa_se_migra_...
        -> sqlite3.IntegrityError: FOREIGN KEY constraint failed

    Porque ese DDL fijo lleva `REFERENCES entities(entity_id)` y
    `REFERENCES sources(source_id)`, y una base de la epoca de B6 tiene
    `claims` **sin** esas FK y con filas (`e:1`, `s:1`) que no existen en
    ninguna tabla. Reconstruir con FKs las convierte, de golpe, en filas
    huerfanas y el motor las rechaza.

    **UNA MIGRACION NO PUEDE ENDURECER UNA BASE VIEJA.** Anadir integridad
    que la base no tenia no es un arreglo: es un cambio de contrato aplicado
    sin avisar, y lo paga quien abria su proyecto un martes. Lo que la
    migracion declara es UN cambio —el ambito entra en la identidad— y por
    eso toca UN pedazo del DDL y deja el resto igual de como estaba.

    Se regex-reemplaza la clausula `UNIQUE` porque es la UNICA que cambia. Si
    la tabla previa no tuviera ninguna (una base de antes de B25), se anade
    al final; si la tiene, se sustituye en su sitio, conservando el orden de
    columnas que ya servia a los indices existentes.

    **Y EL CASO DE «NO HAY `UNIQUE`» TUVO SU PROPIO DEFECTO, MEDIDO.** La
    primera version hacia `ddl.rstrip() + ",\\n UNIQUE(...)"`, y el DDL de B6
    termina en `stale INTEGER NOT NULL DEFAULT 0\n            )`: la coma ya
    estaba puesta por el autor. Anadir otra deja `... DEFAULT 0\n ),` y
    SQLite responde `near "UNIQUE": syntax error`. Se decide mirando si el
    cuerpo ya termina en coma, porque el `UNIQUE` de tabla es una restriccion
    MAS de la lista de columnas: si no hay ninguna mas, no puede haber coma
    justo despues de la anterior.
    """
    _UNIQUE = r"UNIQUE\s*\([^)]*\)"
    if re.search(_UNIQUE, ddl_previo, flags=re.IGNORECASE):
        return re.sub(
            _UNIQUE,
            "UNIQUE (subject_entity_id, tenant_id, project_id,\n"
            "            predicate, source_id, checked_at_revision)",
            ddl_previo,
            count=1,
            flags=re.IGNORECASE,
        )
    cuerpo = ddl_previo.rstrip().rstrip(";")
    cierre = cuerpo.rfind(")")
    if cierre == -1:
        raise sqlite3.IntegrityError(
            f"0005: el DDL de `claims` no tiene el cierre esperable: {cuerpo!r}"
        )
    cabeza, cola = cuerpo[:cierre], cuerpo[cierre:]
    # La coma la pone el DDL previo si venia con ella. Un `CREATE TABLE`
    # cierra sus columnas con coma cuando le sigue OTRA restriccion de tabla,
    # y sin coma cuando la ultima columna es la ultima cosa — y ahi es
    # exactamente donde hay que ponerla para colgarle un `UNIQUE` debajo.
    separador = "" if cabeza.rstrip().endswith(",") else ","
    return (
        cabeza.rstrip()
        + separador
        + (
            "\n    -- R1.F: el ambito entra en la identidad.\n"
            "    UNIQUE (subject_entity_id, tenant_id, project_id,\n"
            "            predicate, source_id, checked_at_revision)\n"
        )
        + cola
    )


def _claims_identidad_con_ambito(cur: sqlite3.Cursor) -> None:
    """`0005` — R1.F: la identidad de un `claim` LLEVA el ambito.

    **LO QUE SE MEDIO ANTES DE ESCRIBIR ESTA FUNCION**
    (`.pipelinek/wi_r1f_measure.py`, sobre el arbol real):

        A/X escribe c-A -> OK;  B/Y escribe c-B -> OK (dice coexiste)
        A/X ve ['c-A'];          B/Y ve []            <-- no ve lo suyo
        FILAS EN LA TABLA claims: [('c-A', 'A', 'X')]

    La escritura de B/Y **no existia**, y `record_claim` habia devuelto
    `ClaimRecorded(conflicto=False)`. Dos propiedades rotas con un solo
    cambio de codigo:

      1. AISLAMIENTO — el `UNIQUE` era
         `(subject_entity_id, predicate, source_id, checked_at_revision)`,
         sin ambito. Dos tenants que observan el mismo fichero en la misma
         revision desde la misma fuente **tienen la misma tupla natural**, y
         con `INSERT OR IGNORE` la segunda se descarta en silencio.
      2. VERDAD DEL RETORNO — `conflicto=False` afirma «no habia nada ahi».

    **POR QUE RECONSTRUIR LA TABLA Y NO ANADIR UN INDICE.** SQLite no tiene
    `ALTER TABLE ... DROP CONSTRAINT`, luego la unica via para cambiar un
    `UNIQUE` de tabla es reconstruirla. Un indice UNIQUE nuevo **no** serviria:
    el viejo seguiria ahi y seguiria rechazando. Y el orden importa: crear el
    indice antes de soltar la tabla deja las dos constraints vivas y el
    `INSERT` durante la copia falla; por eso el `DROP` va primero y el
    `CREATE TABLE ... nuevo` + copia van dentro de la misma transaccion que
    el `sincroniza` de la migracion.

    **POR QUE NO SE PIERDE NADA, Y COMO SE COMPRUEBA.** El `INSERT ... SELECT`
    copia **todas** las columnas por nombre, y las de B25/B29 existen desde
    `0003`/`0004`, luego no hay columnas que seinventen. Lo que si se
    comprueba es el `COUNT`: si la copia deja filas, la migracion **falla**
    en vez de seguir. Una migracion que pierde evidencia en silencio es peor
    que una que se niega a correr, porque la segunda deja el fallo a la vista
    y la primera lo esconde hasta que alguien pregunta por un dato que no
    aparece.

    **EL DDL NUEVO SE DERIVA DEL VIEJO, NO SE ESCRIBE.** Ver
    `_ddl_de_claims_con_ambito`: la primera version traia un `CREATE TABLE`
    fijo y reventaba con las bases de la epoca de B6, que no tienen las FK
    que ese DDL declara. Una migracion no puede endurecer una base vieja.

    **LA REPETICION DENTRO DE UN MISMO AMBITO SIGUE SIENDO UN ERROR.** Con el
    ambito en la clave, `A/X` sigue sin poder escribir dos veces la misma tupla
    natural: eso es deduplicacion, no fuga. Por eso el `UNIQUE` nuevo lleva
    AMBAS caras y no sustituye una por otra.
    """
    # Si el UNIQUE ya lleva el ambito, no hay nada que reconstruir. Se pregunta
    # al motor y no al texto: lo que decide es lo que SQLite tiene abierto.
    if _el_unique_ya_lleva_ambito(cur):
        return

    columnas_antes = [fila[1] for fila in cur.execute("PRAGMA table_info(claims)")]
    fila_ddl = cur.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'claims'"
    ).fetchone()
    if fila_ddl is None or not fila_ddl[0]:
        raise sqlite3.IntegrityError(
            "0005: no hay DDL de `claims` que derivar. Sin el no se puede "
            "cambiar su UNIQUE sin inventar el resto de la tabla."
        )

    cur.execute("ALTER TABLE claims RENAME TO claims_pre_0005")
    cur.execute(_ddl_de_claims_con_ambito(fila_ddl[0]))

    columnas = ", ".join(f'"{c}"' for c in columnas_antes)
    cur.execute(f"INSERT INTO claims ({columnas}) SELECT {columnas} FROM claims_pre_0005")

    cuantos_antes = cur.execute("SELECT COUNT(*) FROM claims_pre_0005").fetchone()[0]
    cuantos_despues = cur.execute("SELECT COUNT(*) FROM claims").fetchone()[0]
    if cuantos_antes != cuantos_despues:
        raise sqlite3.IntegrityError(
            "0005: la copia de claims cambio el numero de filas "
            f"({cuantos_antes} -> {cuantos_despues}). Se revierte en vez de "
            "seguir: perder evidencia en silencio es peor que no migrar."
        )

    cur.execute("DROP TABLE claims_pre_0005")


def _el_unique_ya_lleva_ambito(cur: sqlite3.Cursor) -> bool:
    """¿La constraint UNIQUE de `claims` incluye ya tenant y project?

    **SE PREGUNTA AL MOTOR, POR DOS MOTIVOS QUE IMPORTAN JUNTOS.** Por
    idempotencia —sin esto, abrir dos veces la misma base reconstruiria la
    tabla cada vez— y por honestidad: leer el DDL de `schema.py` mediria el
    texto que *queremos*, no la constraint que una base ya migrada tiene de
    verdad. Un guard que compara su codigo consigo mismo dice «todo bien»
    sobre una base que no se ha arreglado nunca.

    `pragma_index_list` con `origin='u'` son los indices que nacen de una
    constraint de tabla, y `pragma_index_info` dice que columnas la forman.
    Un indice UNIQUE creado a mano tiene `origin='c'`, y ese no cuenta: aqui
    lo que decide es la constraint de la declaracion de la tabla.
    """
    filas = cur.execute(
        "SELECT name FROM pragma_index_list('claims') WHERE origin = 'u' AND \"unique\" = 1"
    ).fetchall()
    for (nombre,) in filas:
        # `PRAGMA` no acepta un identificador parametrizado y el nombre sale
        # de la propia base. Se filtra igual: solo pasa un identificador
        # simple, y cualquier otra cosa cae por el `continue`.
        if not isinstance(nombre, str) or not nombre.replace("_", "").isalnum():
            continue
        columnas = {fila[2] for fila in cur.execute(f"PRAGMA index_info('{nombre}')").fetchall()}
        if {"tenant_id", "project_id"} <= columnas:
            return True
    return False


def _indice_de_commit(cur: sqlite3.Cursor) -> None:
    """B32: el indice que hace posible «qué se afirmó desde este commit».

    **POR QUE UNA MIGRACION Y NO SOLO `schema.py`.** `CREATE INDEX IF NOT
    EXISTS` en `schema.py` solo corre al crear la base. Una base que ya
    existe —que es toda base de un proyecto en uso— no lo recibe nunca,
    luego añadirlo solo al esquema arregla las bases nuevas y deja rotas las
    viejas. Es el mismo motivo por el que `0005` reconstruye `claims`: el
    esquema nuevo no alcanza a lo que ya existe.

    **Y POR QUE ES PARCIAL.** `git_commit_sha` es NULL en toda fuente que no
    viene de git —`improvement.py`, `receipts.py` y `skill_importer.py` la
    ponen a None—, luego un indice completo guardaria many NULLs que no se
    buscan nunca. El `WHERE ... IS NOT NULL` los deja fuera: el indice sale
    mas pequeno y la consulta sigue siendo la misma.

    Idempotente por el `IF NOT EXISTS`, que es lo que permite abrir la base
    dos veces sin que la segunda toque nada.
    """
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_sources_commit "
        "ON sources(tenant_id, project_id, git_commit_sha) "
        "WHERE git_commit_sha IS NOT NULL"
    )


def _ventana_de_runtime(cur: sqlite3.Cursor) -> None:
    """B33 / `ADR-0034`: la ventana que una fuente de runtime observa.

    **POR QUE UNA MIGRACION Y NO SOLO `schema.py`.** El mismo motivo que
    escribio `0006`, y es el que hace que esto no sea opcional: `CREATE TABLE
    IF NOT EXISTS` en `schema.py` solo corre al CREAR la base, luego toda
    base de un proyecto en uso —que es toda base— se queda sin las columnas
    para siempre. Anadirlo solo al esquema deja-arregladas las bases nuevas
    y rotas las viejas, que es el modo de fallo mas caro porque parece que
    funciono.

    **POR QUE `ALTER TABLE ADD COLUMN` Y NO RECONSTRUIR COMO HIZO `0005`.**
    `0005` reconstruyo `claims` porque cambiar su `UNIQUE` exige recrear la
    tabla. Aqui las columnas son nuevas y no participant de ninguna
    constraint, luego `ADD COLUMN` alcanza: es mas barato, no pierde filas, y
    las que ya estan se quedan con `NULL` en las dos — que es exactamente lo
    que deben decir, porque toda fuente anterior a B33 no observa ningun
    periodo.

    **POR QUE EL INDICE ES PARCIAL.** Igual que en `0006`: `observed_from` es
    NULL en toda fuente que no es de runtime, y esas se consultan por otras
    columnas. Un indice completo guardaria many NULLs que no se buscan nunca.

    Idempotente: las columnas se comprueban antes de anadirlas y el indice
    lleva su `IF NOT EXISTS`, luego abrir la base dos veces no hace nada la
    segunda vez. Eso no es elegancia —es lo que permite que aplicar la
    migracion no sea una operacion que haya que auditar—.
    """
    existentes = {fila[1] for fila in cur.execute("PRAGMA table_info(sources)").fetchall()}
    for columna in ("observed_from", "observed_to"):
        if columna not in existentes:
            cur.execute(f"ALTER TABLE sources ADD COLUMN {columna} TEXT")
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_sources_ventana "
        "ON sources(tenant_id, project_id, observed_from) "
        "WHERE observed_from IS NOT NULL"
    )


MIGRACIONES: Final[tuple[Migracion, ...]] = (
    Migracion("0001_claims_assertion_origin", _anade_assertion_origin),
    Migracion("0002_installed_packs", _anota_installed_packs),
    Migracion("0003_claims_object_entity_id", _anade_object_entity_id),
    Migracion("0004_claims_ventanas_de_vigencia", _anade_ventanas_de_vigencia),
    Migracion("0005_claims_identidad_con_ambito", _claims_identidad_con_ambito),
    Migracion("0006_sources_indice_de_commit", _indice_de_commit),
    Migracion("0007_sources_ventana_de_runtime", _ventana_de_runtime),
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

    **LO QUE FALTA AUN, Y MEDIDO EN B16: LA CARRERA ENTRE EL `SELECT` Y EL
    `INSERT`.** Lo de arriba quita la escritura incondicional, pero deja un
    `SELECT` seguido de un `INSERT`: leer y despues escribir. Con ocho
    procesos abriendo la MISMA base nueva a la vez, los ocho leen
    `MAX(version) == 0`, los ocho decide que hay que subir, y los ocho
    insertan. `version` es la PRIMARY KEY —de hecho es la rowid—, luego el
    segundo INSERT que llega se lleva un

        sqlite3.IntegrityError: UNIQUE constraint failed: schema_version.version

    y el proceso **muere antes de escribir un solo evento**. MEDIDO con el
    interprete correcto: 1 hijo muerto de 30, y 4 corridas rojas de 20 del
    `test_b2_real_concurrency`, que el gate de 1.0 leia como
    «1 de 5 corridas con fallos».

    El `timeout` que arreglo el `PRAGMA journal_mode` en B2 no puede
    arreglar esto, y por eso conviene decir por que: el `timeout` hace que
    un escritor **espere** a que el otro suelte. Aqui no hay dos escritores
    peleandose por el mismo lock —cada uno espera su turno y entra—; lo
    que hay es una **LECTURA seguida de una escritura** que ninguna
    espera arregla, porque entre la una y la otra cabe otra proceso. Es
    un *check-then-act*, y contra eso la unica respuesta es que la
    escritura sea atomica e idempotente por si misma.

    Y esa respuesta ya estaba en este mismo archivo, quince lineas mas
    arriba: las migraciones se anotan con `INSERT OR IGNORE INTO
    schema_migrations`, que es exactamente la forma correcta, y la version
    no la tenia. Se le da la misma forma:

    - `OR IGNORE` porque dos procesos que suben a la MISMA version estan
      diciendo lo mismo, no el uno la verdad y el otro una mentira. La
      fila que gana es la misma que hubiera ganado la otra.
    - Una sola sentencia, porque el `DELETE` que precedia era justo la
      ventana: abrir la ventana y luego escribir es dar la oportunidad.
    - Y por lo demas la tabla deja de perder su historia. `version` es la
      rowid y `version_de_la_base` lee `MAX(version)`, luego la tabla es
      un REGISTRO de versiones y no una fila: el `DELETE` no la mantenia al
      dia, la aplanaba. Con el `OR IGNORE` se conserva, que es lo que un
      registro quiere decir.
    """
    objetivo = version_declarada()
    actual = version_de_la_base(cur)
    if actual == objetivo:
        return
    # MEDIDO: si aqui volviera un `INSERT` a secas, volveria el
    # `IntegrityError` de arriba. `OR IGNORE` es lo que hace que dos
    # procesos que suben a la misma version converjan en silencio.
    cur.execute("INSERT OR IGNORE INTO schema_version(version) VALUES (?)", (objetivo,))
