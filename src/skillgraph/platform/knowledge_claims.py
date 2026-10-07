"""Componente CLAIMS del knowledge (WI-61, ADR-0020 fase 2).

Los 9 metodos de claims salen de `SqliteKnowledgeRepository` verbatim:
mismo contrato, misma conexion compartida via `_storage`. La fachada
delega en este componente; los mappers viven en
`knowledge_mappers.py` (fase 1).
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from skillgraph.core.errors import InvalidEntityIDError
from skillgraph.knowledge.graph import Claim, ClaimRecorded
from skillgraph.platform.claim_conflicts import (
    registro_de_escritura,
)
from skillgraph.platform.knowledge_conflicts import _vigente_en_revision
from skillgraph.platform.knowledge_mappers import (
    objeto_del_claim,
    row_to_claim as _row_to_claim,
    row_to_stored_claim as _row_to_stored_claim,
)
from skillgraph.platform.revision_registry import SqliteRevisionRegistry
from skillgraph.platform.storage import Storage, StoredClaim
from skillgraph.platform.translation import traduciendo_integridad


class SqliteClaimRepository:
    """Claims del grafo de conocimiento (clusters CLAIMS de la clase
    original). Comparte `_storage` con la fachada; `_conn` se deriva
    igual que en `SqliteKnowledgeRepository`.
    """

    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    @property
    def _conn(self) -> sqlite3.Connection:
        return self._storage._conn

    def record_claim(
        self,
        *,
        tenant_id: str,
        project_id: str,
        claim: Claim,
    ) -> ClaimRecorded:
        """Registra una Claim. Devuelve su claim_id. Idempotente por
        (subject, predicate, source, checked_at_revision).

        Usa `_atomic()` (BEGIN/COMMIT/ROLLBACK explicitos) en vez de
        `_tx()` para garantizar que un fallo a mitad de las 1+N
        sentencias no deje un `claims` orphan (sin sus
        `claim_evidence` completos). H9-LIMITACION-7 V6.

        **B25: UN objeto o el otro, nunca los dos.** La columna nueva
        `object_entity_id` lleva `''` cuando el objeto es un literal, y el
        literal lleva `''` cuando el objeto es una entidad. Es el mismo XOR que
        sostiene `Claim.__post_init__` y el CHECK de la tabla; los tres dicen la
        misma pregunta a proposito, porque si uno se apartara los otros dos
        darian verde sobre filas que la base rechazaria.

        **`json.dumps` NUNCA produce `''`**, luego el marcador no puede
        confundirse con un literal: `json.dumps("")` es `'""'`, con comillas.
        """
        if claim.object_entity is not None:
            self._exige_que_exista_la_entidad(
                tenant_id=tenant_id, project_id=project_id, entity_id=claim.object_entity.entity_id
            )
            obj_json = ""
            ref = claim.object_entity.entity_id
        else:
            obj_json = json.dumps(claim.object_literal, sort_keys=True)
            ref = ""

        # **R0: LA FRONTERA DE VERDAD.** El `with` de abajo es el unico sitio
        # donde se hace SQL de `claims`, luego es el unico donde puede aparecer
        # un `sqlite3.IntegrityError`. `traduciendo_integridad` lo convierte en
        # `IntegrityError` de DOMINIO y lo propaga intacto si no es FK.
        #
        # Con esto `knowledge_controller.py` deja de importar `sqlite3`: el
        # dominio ya no nombra tipos del adapter. Y el caso que QUEDA en el
        # dominio —decidir si lo que falta es la entidad o la fuente— es
        # logica de negocio, porque depende de lookups que el repositorio tiene
        # y el error no.
        with traduciendo_integridad(), self._storage._atomic() as cur:
            # B27: se mide QUE se va a escribir ANTES de escribir, porque un
            # `INSERT OR IGNORE` que colisiona no dice nada por si mismo. La
            # fila anterior se lee de la tupla natural —NO del `claim_id`—,
            # porque la colisiona la produce el `UNIQUE` y no la clave
            # primaria: dos `claim_id` distintos se solapan igual.
            #
            # **Y LA CONSULTA TIENE QUE SER LA MISMA TUPLA QUE EL `UNIQUE`,
            # MEDIDO, Y NO LO ERA.** `ADR-0035` metio el objeto en la
            # identidad de `claims` (migracion `0008`) y esta busqueda seguia
            # con la tupla de ANTES, sin `object_literal_json` ni
            # `object_entity_id`. Es decir: el `UNIQUE` y su pregunta no
            # decian lo mismo, y el que no lo decia era el que AVISA.
            #
            # MEDIDO con la puerta de B35 (`sg knowledge ingest-code`) sobre un
            # fichero que importa dos modulos:
            #
            #     line_count     = 8         conflicto=False
            #     function_count = 1         conflicto=False
            #     file_exists    = True      conflicto=False
            #     imports_module = 'os'      conflicto=False
            #     imports_module = 'sys'     conflicto=True   <-- FALSO
            #     defines_symbol = 'saluda'  conflicto=False
            #
            # `sys` no contradice a `os`: son dos hechos ciertos sobre el mismo
            # sujeto y el mismo predicado, que es justo el caso que `0008` vino
            # a PERMITIR. Y las filas eran las 6 correctas, luego el defecto no
            # estaba en la escritura sino en el aviso — y por eso B31 no lo
            # vio: su test miraba FILAS, y las filas estaban bien.
            #
            # Es la quinta vez que sale el mismo defecto de fondo: un guard que
            # mide la mitad de una propiedad y da verde porque esa mitad esta
            # bien. Por eso el test de B35 mide `conflictos`, y no filas.
            #
            # **Y POR QUE BUSCA POR LAS DOS COSAS, MEDIDO.** Con la consulta anterior
            # —sujeto, predicado, fuente y revision, SIN el objeto— la fila
            # previa era **ambigua**: un fichero que importa dos modulos tiene
            # DOS filas que encajan en esa tupla, y `fetchone()` devolvia una
            # cualquiera. MEDIDO por el test de B35: reingerir un fichero ya
            # ingerido devolvia `1 conflicto(s)`, y ese conflicto era entre
            # `imports_module='sys'` y `'os'`. Un aviso que sale de una fila
            # elegida al azar no es un aviso: es una moneda.
            #
            # Ahora pregunta por lo que el `UNIQUE` pregunta de verdad —la
            # clave primaria y la tupla natural COMPLETA, que desde `0008`
            # incluye el objeto—, y `ORDER BY (claim_id = ?) DESC` da prioridad
            # a la colision de clave primaria, que es la que se pierde.
            #
            # Se lee DENTRO de la transaccion y no antes, porque fuera de ella
            # la lectura y el INSERT no son atomicos y dos escritores concurrentes
            # podrian leer «no hay fila» los dos y escribir los dos.
            previo = cur.execute(
                """
                SELECT claim_id, object_literal_json, object_entity_id
                FROM claims
                WHERE tenant_id = ? AND project_id = ?
                  AND (
                        claim_id = ?
                     OR (subject_entity_id = ? AND predicate = ?
                         AND object_literal_json = ? AND object_entity_id = ?
                         AND source_id = ? AND checked_at_revision = ?)
                  )
                ORDER BY (claim_id = ?) DESC
                LIMIT 1
                """,
                (
                    tenant_id,
                    project_id,
                    claim.claim_id,
                    claim.subject_entity_id,
                    claim.predicate,
                    obj_json,
                    ref,
                    claim.source_id,
                    claim.checked_at_revision,
                    claim.claim_id,
                ),
            ).fetchone()

            # B29: la revision entra en `revision_registro` ANTES de decidir la
            # ventana, porque la ventana se compara por `seq` y el `seq` se
            # asigna al primer contacto con la revision. Sin este paso, dos
            # claims de la MISMA revision recibirian `seq` distintos y su
            # ventana seria arbitraria.
            SqliteRevisionRegistry(cur).registrar(claim.checked_at_revision)

            # B29: la SUPERSESION. Si la MISMA fuente vuelve a afirmar este
            # sujeto y este predicado en una revision POSTERIOR, y el valor
            # es otro, eso no es una contradiccion: es que el hecho CAMBIO.
            #
            # MEDIDO antes del bloque: `conflicts_for` comparaba valores sin
            # mirar el tiempo, luego un cambio se leia como una contradiccion y
            # `resolver` contestaba «gana NADIE» a algo que si tiene respuesta
            # en cada instante. Aqui lo viejo CADUCA en la revision en la que
            # aparece el nuevo, y el nuevo dice a quien reemplaza.
            #
            # **SOLO DE LA MISMA FUENTE.** Dos fuentes son dos familias: si
            # `local:a.py` y `local:b.py` dicen cosas distintas en la misma
            # revision, nadie sabe cual cambio de opinion, y enlazarlos seria
            # inventar una secuencia que nadie observo. 06-SPEC §2 habla de
            # *source family*, y eso es exactamente lo que dice este filtro.
            #
            # **Y SOLO DE UNA REVISION ESTRICTAMENTE POSTERIOR — MEDIDO QUE SIN
            # ESTO FALLABAN DOS TESTS DE B26 Y B27, Y LOS DOS CONTRA ALGO QUE
            # ESTE MISMO BLOQUE DICE.** La primera version elegía «la vigente mas
            # reciente de la misma fuente» sin mirar el ORDEN:
            #
            # - **B26 (idempotencia)**: reingerir el mismo envelope dos veces
            #   cerraba la ventana del propio claim (`valid_until_revision`
            #   `None` -> `'rev-1'`), luego la relectura devolvia un claim
            #   distinto del primero. Ingerir dos veces es idempotente por
            #   definicion, y una afirmacion no puede caducar por reingerirse.
            # - **B27 (orden estable)**: registrando `r3` antes que `r2`, `r2`
            #   supersedia a `r3` —una revision ANTERIOR cerrando a una
            #   POSTERIOR— y el conflict set dependia del orden de insercion,
            #   que es justo lo que aquel test prohibia.
            #
            # El filtro es `seq(candidata) < seq(nueva)`, y `claim_id <> ?`
            # quita el otro caso degenerado: el propio claim. MEDIDO con la
            # correccion: el test de idempotencia de B26 vuelve a verde.
            #
            # **Y EL VALOR TIENE QUE SER OTRO — MEDIDO QUE SIN ESTO FALLABA UN
            # TEST DE B27 QUE ESTE MISMO BLOQUE ROMPIO.** Un filtro por
            # «misma fuente, mismo sujeto, mismo predicado, revision
            # posterior» supersedia tambien a las **re-observaciones del mismo
            # valor**, que no son un cambio: son la misma afirmacion vista dos
            # veces. Y entonces la ventana dependia del ORDEN DE INGESTA:
            # registrando `c3(rc3)=False` antes que `c2(rc2)=False`, cada una
            # cerraba a la otra segun cual se guardara primero, y el conflict
            # set —que B27 declara estable— dependia de eso.
            #
            # Es la condicion que el propio enunciado de arriba ya decia («y el
            # valor es otro») y que el SQL no miraba: una supersesion cuenta
            # un CAMBIO, y si el valor es el mismo no hubo cambio que contar.
            # La comparacion es sobre las DOS columnas del XOR de B25, que es
            # la misma pregunta que hace `_valor_de` al detectar conflictos.
            #
            # **Y SE CIERRAN TODOS, NO SOLO EL MAS RECIENTE — MEDIDO QUE SIN
            # ESTO EL RESULTADO SEGUIA DEPENDIENDO DEL ORDEN DE INGESTA.** Una
            # fuente no sostiene dos valores a la vez: cuando afirma un valor
            # nuevo, TODAS sus afirmaciones anteriores que siguieran abiertas
            # y dijeran otra cosa pasan a historicas. Cerrar solo la mas
            # reciente dejaba abiertas las anteriores, y entonces dependia de
            # cual se hubiera guardado primero cual era «la mas reciente».
            #
            # MEDIDO con `false@rc2, false@rc3, true@rc1` de la MISMA fuente:
            # registrando en orden, `true` cerraba a `rc3`; al reves, cerraba a
            # `rc2`. Distintos conflict sets para el mismo conjunto de
            # afirmaciones.
            #
            # El enlace `supersedes_claim_id` **si** es singular y apunta al
            # mas reciente: la cadena que 06-SPEC §2 describe es una linea, y
            # recorrerla hacia atras tiene que tener un unico predecesor. Lo
            # que se cierra es una ventana; lo que se encadena es una
            # secuencia.
            supersedidos = cur.execute(
                """
                SELECT claim_id FROM claims
                WHERE subject_entity_id = ? AND predicate = ?
                  AND source_id = ? AND tenant_id = ? AND project_id = ?
                  AND valid_until_revision IS NULL
                  AND claim_id <> ?
                  AND (COALESCE(object_literal_json, '') <> COALESCE(?, '')
                       OR COALESCE(object_entity_id, '') <> COALESCE(?, ''))
                  AND (SELECT seq FROM revision_registro r
                        WHERE r.revision = claims.checked_at_revision)
                    < (SELECT seq FROM revision_registro r WHERE r.revision = ?)
                ORDER BY (SELECT seq FROM revision_registro r
                           WHERE r.revision = claims.checked_at_revision) DESC
                """,
                (
                    claim.subject_entity_id,
                    claim.predicate,
                    claim.source_id,
                    tenant_id,
                    project_id,
                    claim.claim_id,
                    obj_json,
                    ref,
                    claim.checked_at_revision,
                ),
            ).fetchall()
            # El `ORDER BY ... DESC` deja el mas reciente el primero, y ese es
            # el unico que la cadena nombra como predecesor.
            encadenado = supersedidos[0]["claim_id"] if supersedidos else None

            cur.execute(
                """
                INSERT OR IGNORE INTO claims
                    (claim_id, tenant_id, project_id, subject_entity_id,
                     predicate, object_literal_json, source_id,
                     assertion_origin,
                     extraction_method, extractor_version,
                     checked_at_revision, stale, object_entity_id,
                     valid_from_revision, valid_until_revision, supersedes_claim_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    claim.claim_id,
                    tenant_id,
                    project_id,
                    claim.subject_entity_id,
                    claim.predicate,
                    obj_json,
                    claim.source_id,
                    claim.assertion_origin,
                    claim.extraction_method,
                    claim.extractor_version,
                    claim.checked_at_revision,
                    int(claim.stale),
                    ref,
                    # B29: `valid_from_revision` se ESCRIBE tal cual lo declaro
                    # el llamante. Completarlo con `checked_at_revision`
                    # rompia la ida y vuelta del ADT —`get_claim(...) ==
                    # Claim(...)` es un contrato de B25—: el store estaba
                    # Guardando un campo que nadie habia declarado.
                    #
                    # `NULL` no es «desde siempre»: significa «desde la
                    # revision en que lo vimos», y eso lo interpreta
                    # `_vigente_en_revision`, en UN solo sitio.
                    claim.valid_from_revision,
                    claim.valid_until_revision,
                    claim.supersedes_claim_id or encadenado,
                ),
            )
            # **B35: EL AVISO LO DECIDE LA CONSTRAINT, NO UNA ADIVINANZA.**
            # `INSERT OR IGNORE` no lanza; se calla. `rowcount == 0` es la unica
            # manera de saber si la fila entro, y es la respuesta del motor, no
            # una reconstruccion de lo que la constraint haria.
            #
            # MEDIDO, Y EL MOTIVO POR EL QUE ESTA LINEA EXISTE. Antes el aviso
            # salia de comparar contra una consulta previa, y la migration
            # `0008` que B31 escribio habia puesto el objeto en la identidad
            # sin que esa consulta se enterara. MEDIDO por las dos mitades, en
            # un fichero que importa `os` y `sys`:
            #
            #     imports_module = 'os'   -> la consulta previa veia la fila
            #     imports_module = 'sys'  -> 'sys' NO contradice a 'os': son
            #                                    dos hechos ciertos
            #
            # Y MEDIDO TAMBIEN QUE EL ARREGLO DE ESA CONSULTA ERA PEOR: al
            # anadirle el objeto, `previo` solo encontraba filas con el MISMO
            # objeto, luego `previo_valor != intento_valor` era SIEMPRE falso y
            # `conflicto` se quedaba **permanentemente en `False`**. Una señal
            # muerta es peor que una falsa: la falsa molesta, la muerta deja
            # de avisar y nadie lo nota.
            #
            # DECIDIDO CON EL USUARIO, y es un cambio de contrato de un bloque
            # ya certificado: `conflicto` significa **el UNIQUE rechazo mi
            # escritura**. El `UNIQUE` es el contrato, luego el aviso lo decide
            # el `UNIQUE`. La consulta previa se queda —sirve para decir QUE
            # habia antes y cual se intento, que es lo que B27 pidio— pero ya
            # no decide si hay conflicto.
            insertado = cur.rowcount == 1

            # B29: cerrar la ventana de TODO lo que este reemplaza. Va DENTRO
            # de la misma transaccion que el INSERT, porque si cerrara fuera
            # podria quedar un instante en el que los dos estan abiertos — que
            # es justo la contradiccion que este bloque existe para evitar.
            cur.executemany(
                """
                UPDATE claims
                SET valid_until_revision = ?
                WHERE claim_id = ? AND tenant_id = ? AND project_id = ?
                """,
                [
                    (claim.checked_at_revision, f["claim_id"], tenant_id, project_id)
                    for f in supersedidos
                ],
            )
            # Attach evidence links (idempotente).
            for evidence_id in claim.evidence_ids:
                cur.execute(
                    "INSERT OR IGNORE INTO claim_evidence (claim_id, evidence_id) VALUES (?, ?)",
                    (claim.claim_id, evidence_id),
                )
        return registro_de_escritura(claim, previo, insertado=insertado)

    def _exige_que_exista_la_entidad(
        self, *, tenant_id: str, project_id: str, entity_id: str
    ) -> None:
        """B25: la referencia tiene que apuntar a algo que exista.

        **POR QUE ESTA COMPROBACION EN LUGAR DE UNA CLAVE FORANEA.** MEDIDO con
        `PRAGMA foreign_keys = ON`, que es como abre `storage.py`: declarar
        `REFERENCES entities(entity_id)` en la columna nueva rechaza TODOS los
        claims literales, porque el marcador `''` no es una entidad. La columna
        no puede llevar la FK, y la garantia se recupera aqui.

        Lo que eso cuesta, dicho: una escritura que no pase por
        `record_claim` no tiene la garantia. Se acepta porque la alternativa
        —una columna nullable con `NULL` de ausencia— obliga a quitar el
        `NOT NULL` de `object_literal_json`, y SQLite no puede: habria que
        reconstruir la tabla entera.
        """
        fila = self._conn.execute(
            "SELECT 1 FROM entities WHERE entity_id = ? AND tenant_id = ? AND project_id = ?",
            (entity_id, tenant_id, project_id),
        ).fetchone()
        if fila is None:
            raise InvalidEntityIDError(
                f"la entidad {entity_id!r} no existe en ({tenant_id}, {project_id}); "
                "un claim no puede apuntar a una entidad que no esta"
            )

    def get_claim(
        self,
        *,
        tenant_id: str,
        project_id: str,
        claim_id: str,
    ) -> Claim | None:

        row = self._conn.execute(
            "SELECT * FROM claims WHERE claim_id = ? AND tenant_id = ? AND project_id = ?",
            (claim_id, tenant_id, project_id),
        ).fetchone()
        if row is None:
            return None
        # Recoger evidence_ids del join.
        ev_rows = self._conn.execute(
            "SELECT evidence_id FROM claim_evidence WHERE claim_id = ?",
            (claim_id,),
        ).fetchall()
        return _row_to_claim(row, [r["evidence_id"] for r in ev_rows], json)

    def list_claims_for_subject(
        self,
        *,
        tenant_id: str,
        project_id: str,
        subject_entity_id: str,
    ) -> list[Claim]:
        """Lista Claims cuyo ``subject_entity_id`` coincide, con evidence_ids pre-cargados.

        WI-02b: sustituye el patron N+1 que hacia antes ``KnowledgeController.
        list_claims_for_subject`` con dos queries separadas (claims +
        claim_evidence dentro de un bucle por row). Aqui se hace una sola
        query con LEFT JOIN para que el adapter SQLite sea responsable de
        la atomicidad del join, no el caller.
        """

        rows = self._conn.execute(
            """
            SELECT c.claim_id, c.subject_entity_id, c.predicate,
                   c.object_literal_json, c.source_id,
                   c.assertion_origin, c.extraction_method, c.extractor_version,
                   c.checked_at_revision, c.stale, c.object_entity_id,
                   GROUP_CONCAT(ce.evidence_id) AS evidence_ids_csv
            FROM claims c
            LEFT JOIN claim_evidence ce ON ce.claim_id = c.claim_id
            WHERE c.tenant_id = ? AND c.project_id = ?
              AND c.subject_entity_id = ?
            GROUP BY c.claim_id
            ORDER BY c.checked_at_revision DESC
            """,
            (tenant_id, project_id, subject_entity_id),
        ).fetchall()
        out: list[Claim] = []
        for row in rows:
            ev_csv = row["evidence_ids_csv"] or ""
            ev_ids = tuple(ev_csv.split(",")) if ev_csv else ()
            object_literal, object_entity = objeto_del_claim(row, json)
            out.append(
                Claim(
                    claim_id=row["claim_id"],
                    subject_entity_id=row["subject_entity_id"],
                    predicate=row["predicate"],
                    object_literal=object_literal,
                    source_id=row["source_id"],
                    evidence_ids=ev_ids,
                    assertion_origin=row["assertion_origin"],
                    extraction_method=row["extraction_method"],
                    extractor_version=row["extractor_version"],
                    checked_at_revision=row["checked_at_revision"],
                    stale=bool(row["stale"]),
                    object_entity=object_entity,
                )
            )
        return out

    def list_claims_for_source(
        self,
        *,
        tenant_id: str,
        project_id: str,
        source_id: str,
    ) -> list[Claim]:

        rows = self._conn.execute(
            "SELECT * FROM claims WHERE source_id = ? AND tenant_id = ? AND project_id = ?",
            (source_id, tenant_id, project_id),
        ).fetchall()
        out: list[Claim] = []
        for row in rows:
            ev_rows = self._conn.execute(
                "SELECT evidence_id FROM claim_evidence WHERE claim_id = ?",
                (row["claim_id"],),
            ).fetchall()
            out.append(_row_to_claim(row, [r["evidence_id"] for r in ev_rows], json))
        return out

    def list_claims_using_evidence(self, *, evidence_id: str) -> tuple[str, ...]:
        """Tupla de claim_ids que referencian la evidence."""
        rows = self._conn.execute(
            "SELECT claim_id FROM claim_evidence WHERE evidence_id = ?",
            (evidence_id,),
        ).fetchall()
        return tuple(r["claim_id"] for r in rows)

    def mark_claims_stale(
        self,
        *,
        tenant_id: str,
        project_id: str,
        claim_ids: tuple[str, ...],
    ) -> None:
        """Bulk UPDATE: marca stale=1 en una sola transaccion."""
        if not claim_ids:
            return
        placeholders = ",".join("?" * len(claim_ids))
        with self._storage._tx() as cur:
            cur.execute(
                f"""
                UPDATE claims
                SET stale = 1
                WHERE tenant_id = ? AND project_id = ?
                  AND claim_id IN ({placeholders})
                """,
                (tenant_id, project_id, *claim_ids),
            )

    def reactivate_claims_with_revision(
        self,
        *,
        tenant_id: str,
        project_id: str,
        source_id: str,
        new_revision: str,
    ) -> tuple[str, ...]:
        """Bulk UPDATE ... RETURNING: reactiva claims con la nueva revision."""
        with self._storage._tx() as cur:
            cur.execute(
                """
                UPDATE claims
                SET stale = 0
                WHERE tenant_id = ? AND project_id = ?
                  AND source_id = ? AND checked_at_revision = ?
                  AND stale = 1
                RETURNING claim_id
                """,
                (tenant_id, project_id, source_id, new_revision),
            )
            rows = cur.fetchall()
        return tuple(r["claim_id"] for r in rows)

    def list_stale_claims(
        self,
        *,
        tenant_id: str,
        project_id: str,
    ) -> tuple[Any, ...]:
        """Lista Claims stale con LEFT JOIN pre-cargado (sin N+1)."""
        rows = self._conn.execute(
            """
            SELECT c.claim_id, c.subject_entity_id, c.predicate,
                   c.object_literal_json, c.source_id,
                   c.assertion_origin, c.extraction_method, c.extractor_version,
                   c.checked_at_revision, c.stale, c.object_entity_id,
                   GROUP_CONCAT(ce.evidence_id) AS evidence_ids_csv
            FROM claims c
            LEFT JOIN claim_evidence ce ON ce.claim_id = c.claim_id
            WHERE c.tenant_id = ? AND c.project_id = ? AND c.stale = 1
            GROUP BY c.claim_id
            ORDER BY c.checked_at_revision DESC
            """,
            (tenant_id, project_id),
        ).fetchall()
        out: list[Claim] = []
        for row in rows:
            ev_csv = row["evidence_ids_csv"] or ""
            ev_ids = tuple(ev_csv.split(",")) if ev_csv else ()
            object_literal, object_entity = objeto_del_claim(row, json)
            out.append(
                Claim(
                    claim_id=row["claim_id"],
                    subject_entity_id=row["subject_entity_id"],
                    predicate=row["predicate"],
                    object_literal=object_literal,
                    source_id=row["source_id"],
                    evidence_ids=ev_ids,
                    assertion_origin=row["assertion_origin"],
                    extraction_method=row["extraction_method"],
                    extractor_version=row["extractor_version"],
                    checked_at_revision=row["checked_at_revision"],
                    stale=bool(row["stale"]),
                    object_entity=object_entity,
                )
            )
        return tuple(out)

    def list_claims_by_predicate(
        self,
        *,
        tenant_id: str,
        project_id: str,
        predicate: str,
    ) -> tuple[StoredClaim, ...]:
        """Devuelve todos los Claims con `predicate == value` para el
        (tenant, project) dado.

        El adapter deserializa JSON y carga los evidence ids asociados.
        """

        rows = self._conn.execute(
            """
            SELECT c.*, GROUP_CONCAT(ce.evidence_id) AS evidence_ids_csv
            FROM claims c
            LEFT JOIN claim_evidence ce ON ce.claim_id = c.claim_id
            WHERE c.tenant_id = ? AND c.project_id = ? AND c.predicate = ?
            GROUP BY c.claim_id
            """,
            (tenant_id, project_id, predicate),
        ).fetchall()
        return tuple(_row_to_stored_claim(row, json) for row in rows)

    def claims_at_revision(
        self,
        *,
        tenant_id: str,
        project_id: str,
        subject_entity_id: str,
        revision: str | None,
    ) -> tuple[Claim, ...]:
        """B29: ¿qué afirmaciones de este sujeto eran CIERTAS en `revision`?

        **LA MITAD DE LA FILA QUE SI ERA CIERTA, CONVERTIDA EN CONSULTA.** La
        fila decia «no se puede preguntar qué se sabia en una revision». El
        dato existia —`checked_at_revision` en cada fila—; lo que no existia
        era la pregunta. Y la pregunta es un filtro de ventana, no un barrido:
        lo que se asks es qué afirmaciones **abrian** su ventana en ese punto.

        `revision=None` es HEAD: solo las afirmaciones que no han caducado.

        **UNA REVISION QUE ESTE STORE NUNCA HA VISTO DEVUELVE VACIO, Y NO ES
        UN ERROR.** Es la respuesta honesta: una afirmacion es algo que ESTE
        store afirmo, y de una revision que no ha visto no tiene nada que
        decir. Lo que NO se hace es devolver todas las afirmaciones «porque
        si», que es lo que haria un filtro ausente.

        Returns:
            Los claims vigentes, **ordenados de forma estable** por `claim_id`.
            B27 fijo esa propiedad para los conflict sets y aqui se sostiene
            igual: una consulta de historico cuya lista depende del plan de
            ejecucion no es una consulta de historico.
        """
        rows = self._conn.execute(
            """
            SELECT * FROM claims
            WHERE subject_entity_id = ? AND tenant_id = ? AND project_id = ?
            ORDER BY claim_id ASC
            """,
            (subject_entity_id, tenant_id, project_id),
        ).fetchall()
        vigentes = [r for r in rows if _vigente_en_revision(self._conn, r, revision)]
        return tuple(_row_to_claim(r, [], json) for r in vigentes)

    def list_claims_by_object_entity(
        self,
        *,
        tenant_id: str,
        project_id: str,
        object_entity_id: str,
    ) -> tuple[StoredClaim, ...]:
        """B25: los claims cuyo OBJETO es esa entidad. La pregunta «¿qué
        afirma sobre X que sea otra cosa?».

        **POR QUE ESTA CONSULTA ES PARTE DEL BLOQUE Y NO UNA EXTRA.** Sin ella
        la referencia a entidad se guardaría y no se podría preguntar por ella:
        sería un dato que se escribe y nunca se lee, que es peor que no
        tenerlo —porque el que lo escribió creería que sí. Es la consulta que
        B27 necesita para encontrar dos claims incompatibles que apuntan a la
        misma entidad, y la primera mitad de `changed` en B34.

        Usa `idx_claims_object_entity`, que es un indice PARCIAL sobre las
        filas con referencia: los claims literales, que son la mayoria, no
        ocupan sitio en el.

        La forma de devolver (`StoredClaim`, no `Claim`) es la de
        `list_claims_by_predicate` y la de `list_stale_claims`; se copia la
        que ya existe en el sitio, no la que seria mas comoda aqui.
        """
        rows = self._conn.execute(
            """
            SELECT c.*, GROUP_CONCAT(ce.evidence_id) AS evidence_ids_csv
            FROM claims c
            LEFT JOIN claim_evidence ce ON ce.claim_id = c.claim_id
            WHERE c.tenant_id = ? AND c.project_id = ?
              AND c.object_entity_id = ? AND c.object_entity_id <> ''
            GROUP BY c.claim_id
            ORDER BY c.checked_at_revision DESC
            """,
            (tenant_id, project_id, object_entity_id),
        ).fetchall()
        return tuple(_row_to_stored_claim(row, json) for row in rows)

    def claims_desde_commit(
        self,
        *,
        tenant_id: str,
        project_id: str,
        commit_sha: str,
    ) -> tuple[Claim, ...]:
        """B32: ¿qué afirmaciones se hicieron DESDE este commit?

        **LA CONSULTA QUE NO EXISTIA, Y QUE ES LA MITAD DE B32.** MEDIDO
        antes de escribirla: `grep git_commit_sha src/` no encuentra NINGUN
        llamador fuera de quien escribe la columna. Nadie ha hecho nunca esta
        pregunta desde el producto. La fila de B32 dice «no se puede
        responder cuándo cambió una relación»; la mitad de verdad es que la
        pregunta no tenía forma.

        El camino es `claims.source_id -> sources.git_commit_sha`, y es el
        único que hay: no se añade una columna con el SHA al claim, porque
        sería una segunda fuente de verdad para algo que la fuente YA sabe.

        **DEVUELVE `Claim`, COMO `claims_at_revision` Y NO COMO
        `claims_by_object_entity`.** Hay dos formas de fila en este fichero
        y la eleccion importa: `Claim` es el dominio, `StoredClaim` es el
        almacen. Una consulta de esta clase que viene de una fuente con SHA
        y se cruza con `claims` es la misma clase de pregunta que
        `claims_at_revision` —qué se afirmo en ESTE punto— y esa devuelve
        `Claim`. Abrir una tercera forma para lo mas nuevo es exactamente
        como aparecen dos representaciones del mismo dato.

        **POR QUÉ NO FILTRA POR VIGENCIA.** Porque la pregunta es «qué se
        afirmó DESDE este commit», no «qué es cierto ahora». Una afirmación
        cuya ventana se cerró SIGUIó afirmándose desde ese commit, y filtrarla
        por vigencia haría que un rebase de tres meses no mostrara nada de lo
        que pasó entonces. Es la misma distinción que B29 fijo entre «qué se
        sabía en la revisión» y «qué se afirmó entonces».

        Usa `idx_sources_commit`, que es PARCIAL: las fuentes sin SHA no se
        indexan porque no se buscan.

        Returns:
            Ordenado de forma estable por `claim_id`, igual que
            `claims_at_revision`: una consulta de histórico cuya lista
            depende del plan de ejecución no es una consulta de histórico.
        """
        rows = self._conn.execute(
            """
            SELECT c.*, GROUP_CONCAT(ce.evidence_id) AS evidence_ids_csv
            FROM claims c
            JOIN sources s ON s.source_id = c.source_id
            LEFT JOIN claim_evidence ce ON ce.claim_id = c.claim_id
            WHERE c.tenant_id = ? AND c.project_id = ?
              AND s.tenant_id = ? AND s.project_id = ?
              AND s.git_commit_sha = ?
            GROUP BY c.claim_id
            ORDER BY c.claim_id
            """,
            (tenant_id, project_id, tenant_id, project_id, commit_sha),
        ).fetchall()
        out: list[Claim] = []
        for row in rows:
            ev_csv = row["evidence_ids_csv"] or ""
            ev_ids = tuple(ev_csv.split(",")) if ev_csv else ()
            object_literal, object_entity = objeto_del_claim(row, json)
            out.append(
                Claim(
                    claim_id=row["claim_id"],
                    subject_entity_id=row["subject_entity_id"],
                    predicate=row["predicate"],
                    object_literal=object_literal,
                    source_id=row["source_id"],
                    evidence_ids=ev_ids,
                    extraction_method=row["extraction_method"],
                    extractor_version=row["extractor_version"],
                    assertion_origin=row["assertion_origin"],
                    checked_at_revision=row["checked_at_revision"],
                    stale=bool(row["stale"]),
                    object_entity=object_entity,
                    valid_from_revision=row["valid_from_revision"],
                    valid_until_revision=row["valid_until_revision"],
                    supersedes_claim_id=row["supersedes_claim_id"],
                )
            )
        return tuple(out)
