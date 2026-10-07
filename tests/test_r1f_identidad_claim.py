"""R1.F — la identidad de un `claim` incluye el ambito, o no incluye nada.

**LO QUE SE MEDIO ANTES DE ESCRIBIR UNA LINEA** (`.pipelinek/wi_r1f_measure.py`,
sobre el arbol real, no sobre este fichero):

    A/X escribe c-A            -> OK
    B/Y escribe c-B            -> OK (coexiste)
    A/X ve 1 claim(s): ['c-A']
    B/Y ve 0 claim(s): []      <-- lo que acaba de escribir, no lo ve

Y lo que hace el defecto todavía mas caro que perder una fila:

    record_claim B/Y -> ClaimRecorded(conflicto=False, valor_previo=None, ...)
    FILAS EN LA TABLA claims: [('c-A', 'A', 'X')]

**EL `UNIQUE` DE LA TABLA NO LLEVA AMBITO, Y `record_claim` NO DICE NADA.**

    UNIQUE (subject_entity_id, predicate, source_id, checked_at_revision)

La columna `tenant_id` esta en la tabla y en el `WHERE` de todas las lecturas,
pero no en la constraint. Con `INSERT OR IGNORE`, la escritura de B/Y choca
con la fila de A/X y **se descarta en silencio**, mientras el metodo devuelve
`conflicto=False`. Eso son dosproperties rotas a la vez, y solo una es visible:

  1. **AISLAMIENTO**: el dato de un tenant puede pisar al de otro.
  2. **VERDAD DEL RETORNO**: `conflicto=False` afirma «no habia nada ahi»,
     y habia. Un guard que dice la verdad sobre un estado que no guardo.

**POR QUE UNA TABLA «GLOBAL» NO SIRVE, Y NO ES UNA CUESTION DE ESTILO.** Dos
proyectos del mismo tenant, o dos tenants, observan los mismos ficheros con
los mismos SHA y los mismos predicados. La identidad natural de la afirmacion
—«este fichero, en esta revision, segun esta fuente, decia esto»— es
**identica** entre ambos ambitos, y por eso colisionan. El ambito no es
decoracion de la identidad: es parte de lo que la afirmacion afirma, porque
una afirmacion sin saber **quien** la sostiene no es una afirmacion.

# LO QUE ESTA COMPRUEBA CADA PIEZA

    P1  dos ambitos coexisten          -> TestDosAmbitosCoexisten
    P2  cada uno ve LO SUYO            -> TestCadaAmbitoVeLoSuyo
    P3  el retorno NO miente           -> TestElRetornoNoMiente
    P4  la constraint REAL lo dice     -> TestLaConstraintRealLoDice
    P5  CONTRA SALTO                   -> TestElContrasaltoMataLaFuga

P5 es la que hace que las otras cuatro midan algo. Una migracion que anadiera
las columnas pero dejara el `UNIQUE` viejo seguiria en verde en P1..P4 para
un unico ambito, porque con un solo tenant/proyecto no hay colision posible.
"""

from __future__ import annotations

import pathlib
import sqlite3
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from skillgraph.knowledge.graph import Claim, Entity, Source, source_id
from skillgraph.platform.migrations import MIGRACIONES, version_declarada
from skillgraph.platform.storage import Storage

SUJETO = "file:a.py"
ORIGEN = "local:a.py"

#: La tupla natural de la afirmacion —mismo fichero, misma revision, misma
#: fuente— es DELIBERADAMENTE IDENTICA entre los dos ambitos del contrasalto.
#: Es lo que hace la fuga posible: si la identidad no lleva ambito, las dos
#: filas son la MISMA fila.


@contextmanager
def _ambos_ambitos() -> Iterator[Storage]:
    """Un storage con el sujeto y la fuente declarados en A/X y en B/Y."""
    with tempfile.TemporaryDirectory() as tmp:
        s = Storage(pathlib.Path(tmp) / "x.sqlite")
        for tenant, project in (("A", "X"), ("B", "Y")):
            s.upsert_entity(
                tenant_id=tenant,
                project_id=project,
                entity=Entity(entity_id=SUJETO, kind="file", stable_key="a.py"),
            )
            s.register_source(
                tenant_id=tenant,
                project_id=project,
                source=Source(
                    source_id=source_id(ORIGEN),
                    kind="local_file",
                    content_hash="h",
                    locator={},
                    git_commit_sha=None,
                    git_tree_sha=None,
                    working_tree_status=None,
                    checked_at="2026-10-07T00:00:00Z",
                    freshness="current",
                ),
            )
        yield s


def _claim(cid: str) -> Claim:
    return Claim(
        claim_id=cid,
        subject_entity_id=SUJETO,
        predicate="imports_module",
        object_literal="psycopg",
        source_id=source_id(ORIGEN),
        assertion_origin="observed",
        checked_at_revision="revA",
    )


def _visibles(s: Storage, tenant: str, project: str) -> set[str]:
    return {
        c.claim_id
        for c in s.claims_at_revision(
            tenant_id=tenant,
            project_id=project,
            subject_entity_id=SUJETO,
            revision="revA",
        )
    }


def _filas_crudas(s: Storage) -> list[tuple[str, str, str]]:
    return [
        tuple(r)  # type: ignore[misc]
        for r in s._conn.execute(
            "SELECT claim_id, tenant_id, project_id FROM claims ORDER BY claim_id"
        ).fetchall()
    ]


# ---------------------------------------------------------------------------
# P1 + P2 — la propiedad que el enunciado declara como contrasalto
# ---------------------------------------------------------------------------


class TestDosAmbitosCoexisten:
    """**EL CONTRASALTO DEL ENUNCIADO, EJECUTADO.**

    > tenant=A project=X claim=foo / tenant=B project=Y claim=foo
    > -> ambas afirmaciones coexisten
    """

    def test_las_dos_escrituras_dejan_dos_filas(self) -> None:
        with _ambos_ambitos() as s:
            s.record_claim(tenant_id="A", project_id="X", claim=_claim("c-A"))
            s.record_claim(tenant_id="B", project_id="Y", claim=_claim("c-B"))

            filas = _filas_crudas(s)
            assert len(filas) == 2, (
                "B/Y escribio y su fila NO esta. El UNIQUE "
                "(subject, predicate, source, revision) no lleva ambito, luego "
                f"INSERT OR IGNORE la descarta. Filas: {filas}"
            )

    def test_cada_ambito_ve_SOLO_lo_suyo(self) -> None:
        with _ambos_ambitos() as s:
            s.record_claim(tenant_id="A", project_id="X", claim=_claim("c-A"))
            s.record_claim(tenant_id="B", project_id="Y", claim=_claim("c-B"))

            assert _visibles(s, "A", "X") == {"c-A"}, "A/X ha perdido su propia afirmacion"
            assert _visibles(s, "B", "Y") == {"c-B"}, (
                "B/Y no ve la afirmacion que acaba de escribir"
            )

    def test_ninguna_puede_caducar_a_la_otra(self) -> None:
        """La segunda mitad del contrasalto: no solo coexistir, no MOLESTARSE.

        Un `UNIQUE` mal puesto no se manifiesta solo como fila perdida: se
        manifiesta como una afirmacion que **cierra la ventana** de la otra,
        que es la fuga silenciosa que B29 construyo y que este ambito rompe.
        """
        with _ambos_ambitos() as s:
            s.record_claim(tenant_id="A", project_id="X", claim=_claim("c-A"))
            s.record_claim(tenant_id="B", project_id="Y", claim=_claim("c-B"))

            # c-A sigue vigente en su ambito: nadie en B/Y puede haberlo
            # caducado. `claims_at_revision('revA')` solo devuelve lo vigente,
            # luego que c-A aparezca es la prueba de que nadie lo cerro.
            assert "c-A" in _visibles(s, "A", "X"), (
                "c-A fue caducado por una escritura de otro ambito"
            )
            filas_a = s._conn.execute(
                "SELECT valid_until_revision FROM claims WHERE claim_id = ?",
                ("c-A",),
            ).fetchall()
            assert filas_a[0][0] is None, (
                f"c-A quedo con valid_until_revision={filas_a[0][0]!r}: "
                "otra ambito modifico una afirmacion que no es suya"
            )


# ---------------------------------------------------------------------------
# P3 — el retorno dice la verdad
# ---------------------------------------------------------------------------


class TestElRetornoNoMiente:
    """`conflicto=False` afirma «no habia nada ahi». Con la fuga, miente.

    Esta pieza sola ya seria un bug: un metodo que devuelve «escrito» sin haber
    escrito nada convierte un error de aislamiento en un exito silencioso.
    """

    def test_una_escritura_descartada_NO_se_reportsa_como_exitosa(self) -> None:
        with _ambos_ambitos() as s:
            s.record_claim(tenant_id="A", project_id="X", claim=_claim("c-A"))
            registro = s.record_claim(tenant_id="B", project_id="Y", claim=_claim("c-B"))

            existe = s._conn.execute("SELECT 1 FROM claims WHERE claim_id = ?", ("c-B",)).fetchone()
            if registro.conflicto is False and existe is None:
                pytest.fail(
                    "record_claim devolvio conflicto=False y la fila NO existe: "
                    "el retorno afirma una escritura que no ocurrio. O la "
                    "migracion no esta, o el UNIQUE sigue sin ambito."
                )


# ---------------------------------------------------------------------------
# P4 — la constraint real, leida de la base, no del codigo
# ---------------------------------------------------------------------------


class TestLaConstraintRealLoDice:
    """**LA PROPIEDAD ES DE LA BASE, Y SE LEE DE LA BASE.**

    Un test que mirara el DDL de `schema.py` mediria el texto; la constraint
    que decide es la que SQLite tiene en el fichero. Por eso se reconstruye
    una base **migrada desde cero** y se le pregunta al motor con escrituras
    CRUDAS, saltandonos `record_claim`.

    Y son **las dos direcciones**, porque una constraint correcta tiene dos
    caras y una defectuosa tambien:

      - el MISMO ambito, misma tupla natural -> **rechaza** (la repeticion)
      - OTRO ambito, misma tupla natural     -> **acepta**  (otro ambito)

    Preguntar solo por la primera daria verde al `UNIQUE` viejo: rechaza las
    dos, y la segunda es precisamente la fuga.
    """

    @staticmethod
    def _insert_crudo(s: Storage, *, cid: str, tenant: str, project: str) -> None:
        s._conn.execute(
            """
            INSERT INTO claims (
                claim_id, tenant_id, project_id, subject_entity_id,
                predicate, object_literal_json, source_id,
                extraction_method, extractor_version, checked_at_revision
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cid,
                tenant,
                project,
                SUJETO,
                "imports_module",
                '"otro"',
                source_id(ORIGEN),
                "m",
                "v",
                "revA",
            ),
        )
        s._conn.commit()

    def test_otro_ambito_CON_LA_MISMA_TUPLA_NATURAL_SI_SE_PUEDE_ESCRIBIR(self) -> None:
        """La cara del defecto: con el `UNIQUE` viejo, el motor RECHAZA."""
        with _ambos_ambitos() as s:
            s.record_claim(tenant_id="A", project_id="X", claim=_claim("c-A"))
            try:
                self._insert_crudo(s, cid="c-crudo", tenant="B", project="Y")
            except sqlite3.IntegrityError as exc:
                pytest.fail(
                    "SQLite rechazo una afirmacion de OTRO ambito con "
                    "integralidad violada: "
                    f"{exc}. El UNIQUE (subject, predicate, source, revision) "
                    "no lleva tenant_id/project_id, luego dos tenants que "
                    "observan el mismo fichero se pisan entre si."
                )

    def test_el_mismo_ambito_con_la_misma_tupla_SI_se_rechaza(self) -> None:
        """La otra cara: sin esta, «arreglar» el UNIQUE seria borrar la deduplicacion."""
        with _ambos_ambitos() as s:
            s.record_claim(tenant_id="A", project_id="X", claim=_claim("c-A"))
            with pytest.raises(sqlite3.IntegrityError):
                self._insert_crudo(s, cid="c-repetida", tenant="A", project="X")

    def test_la_migracion_que_lo_arrecla_esta_declarada(self) -> None:
        """La constraint se crea en una migracion; sin declararla no viaja."""
        nombres = [m.id for m in MIGRACIONES]
        assert any("ambito" in n or "identidad" in n for n in nombres), (
            f"ninguna migracion declara el ambito de la identidad: {nombres}"
        )

    def test_la_version_declarada_no_esta_por_detras_del_arbol(self) -> None:
        """La cifra sale del ARBOL de migraciones, nunca de una copia del test."""
        with _ambos_ambitos() as s:
            filas = s._conn.execute("SELECT version FROM schema_version").fetchall()
            aplicada = max(f[0] for f in filas)
        assert aplicada == version_declarada(), (
            f"el arbol declara {version_declarada()} y la base quedo en "
            f"{aplicada}: una migracion existe en el codigo y no viaja"
        )


# ---------------------------------------------------------------------------
# P5 — la migracion sobre una base QUE YA TIENE DATOS
# ---------------------------------------------------------------------------


class TestElUpgradeNoPierdeEvidencia:
    """**UNA BASE NUEVA NO PRUEBA UNA MIGRACION.**

    Con el `schema.py` ya arreglado, una base recien creada nace con la
    constraint correcta y todo pasa: el defecto soloafecta a las bases que
    **ya existian**, que es justo donde esta la evidencia de los demas. Por
    eso este bloque construye una base con el DDL VIEJO de verdad —la misma
    `UNIQUE` sin ambito que habia antes de R1.F— y deja filas dentro.

    Y hay un segundo motivo, que es el que hace la prueba util: al reconstruir
    la tabla, cualquier columna que se olvidara **perderia datos en silencio**.
    Un `INSERT ... SELECT` con la lista de columnas escrita a mano desde 0001
    se dejaria fuera `object_entity_id`, `valid_from_revision` o
    `supersedes_claim_id` sin que nada fallara. Por eso el `COUNT` se compara
    y no basta con que la apertura funcione.
    """

    @staticmethod
    def _base_vieja(tmp: str) -> Path:
        """Una base creada con la constraint VIEJA y con una fila dentro."""
        ruta = Path(tmp) / "vieja.sqlite"
        s = Storage(ruta)
        # El resto del esquema sirve tal cual; solo `claims` vuelve a su
        # declaracion anterior, que es lo que una base migrada tiene.
        s._conn.execute("DROP TABLE claims")
        s._conn.execute(_DDL_CLAIMS_SIN_AMBITO)
        for tenant, project in (("A", "X"), ("B", "Y")):
            s.upsert_entity(
                tenant_id=tenant,
                project_id=project,
                entity=Entity(entity_id=SUJETO, kind="file", stable_key="a.py"),
            )
            s.register_source(
                tenant_id=tenant,
                project_id=project,
                source=Source(
                    source_id=source_id(ORIGEN),
                    kind="local_file",
                    content_hash="h",
                    locator={},
                    git_commit_sha=None,
                    git_tree_sha=None,
                    working_tree_status=None,
                    checked_at="2026-10-07T00:00:00Z",
                    freshness="current",
                ),
            )
        s._conn.execute(
            """
            INSERT INTO claims (
                claim_id, tenant_id, project_id, subject_entity_id, predicate,
                object_literal_json, source_id, extraction_method,
                extractor_version, checked_at_revision
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "c-A",
                "A",
                "X",
                SUJETO,
                "imports_module",
                '"psycopg"',
                source_id(ORIGEN),
                "m",
                "v",
                "revA",
            ),
        )
        s._conn.execute("UPDATE schema_version SET version=4")
        s._conn.commit()
        s._conn.close()
        return ruta

    def test_la_base_que_ya_existia_migra_sin_perder_una_fila(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ruta = self._base_vieja(tmp)

            # Abrir con el codigo nuevo es lo que dispara `sincroniza`.
            nuevo = Storage(ruta)

            filas = nuevo._conn.execute(
                "SELECT claim_id, tenant_id, project_id FROM claims ORDER BY claim_id"
            ).fetchall()
            assert [tuple(f) for f in filas] == [("c-A", "A", "X")], (
                f"la migracion cambio lo que habia: {filas}. Reconstruir una "
                "tabla pierde datos en silencio si se olvida una columna."
            )
            nuevo._conn.close()

    def test_tras_migrar_el_otro_ambito_puede_escribir_su_tupla(self) -> None:
        """La mitad que importa del upgrade: antes no cabia, ahora si."""
        with tempfile.TemporaryDirectory() as tmp:
            ruta = self._base_vieja(tmp)
            nuevo = Storage(ruta)
            nuevo._conn.execute(
                """
                INSERT INTO claims (
                    claim_id, tenant_id, project_id, subject_entity_id, predicate,
                    object_literal_json, source_id, extraction_method,
                    extractor_version, checked_at_revision
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "c-B",
                    "B",
                    "Y",
                    SUJETO,
                    "imports_module",
                    '"psycopg"',
                    source_id(ORIGEN),
                    "m",
                    "v",
                    "revA",
                ),
            )
            nuevo._conn.commit()
            filas = nuevo._conn.execute("SELECT claim_id FROM claims ORDER BY claim_id").fetchall()
            assert [f[0] for f in filas] == ["c-A", "c-B"], (
                f"tras migrar, dos ambitos con la misma tupla natural NO coexisten: {filas}"
            )
            nuevo._conn.close()

    def test_migrar_dos_veces_no_reescribe_las_filas(self) -> None:
        """La idempotencia, MEDIDA por algo que reconstruir cambia de verdad.

        **EL `rowid` NO SIRVE, Y ESTO SE MIDIO ANTES DE FIJAR ESTA PIEZA.**
        Una reconstruccion que copia correctamente deja las mismas filas, luego
        «las filas siguen ahi» no la delata. Y el `rowid` tampoco: con una
        sola fila, la copia la reinserta en el hueco 1 y el `rowid` vuelve a
        ser 1. MEDIDO con la migracion sin su deteccion de idempotencia:

            rootpage 70 -> 55   (SI cambia: la tabla se reconstruyo)
            rowid      1 ->  1   (NO cambia: no delata nada)

        El `rootpage` es la pagina donde SQLite guarda la tabla: si el
        fichero cambia, la tabla cambio. Sin esta pieza, una migracion que
        reconstruyese el grafo entero en cada apertura pasaria todos los
        demas tests del bloque —los datos sobreviven, luego parece correcta—
        y lo que estaria haciendo es reescribir la base cada vez que alguien
        abre el proyecto.
        """
        with tempfile.TemporaryDirectory() as tmp:
            ruta = self._base_vieja(tmp)

            primera = Storage(ruta)
            root_inicial = primera._conn.execute(
                "SELECT rootpage FROM sqlite_master WHERE name='claims'"
            ).fetchone()[0]
            primera._conn.close()

            segunda = Storage(ruta)
            root_final = segunda._conn.execute(
                "SELECT rootpage FROM sqlite_master WHERE name='claims'"
            ).fetchone()[0]
            assert root_inicial == root_final, (
                f"la tabla `claims` cambio de pagina al reabrir ({root_inicial}"
                f" -> {root_final}): la migracion reconstruye en cada "
                "apertura. Las filas siguen ahi, luego parece correcta; lo "
                "que hace es reescribir la base entera cada vez que se abre."
            )
            segunda._conn.close()

    def test_los_valores_de_las_columnas_nuevas_sobreviven(self) -> None:
        """**CUBRE LA COLUMNA OLVIDADA, Y LA CUENTA DE FILAS NO.**

        El `COUNT` solo detecta perder FILAS. Una columna olvidada en el
        `INSERT ... SELECT` puede perder el VALOR de una columna y dejar el
        numero de filas intacto, luego el conteo pasa y la evidencia se ha
        ido. Por eso se mira el valor.

        `valid_from_revision` y `supersedes_claim_id` son las columnas de
        B29: son las que un `SELECT` escrito a mano desde 0001 dejaria fuera
        sin avisar, porque las filas siguen estando.
        """
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "valores.sqlite"
            s = Storage(ruta)
            s._conn.execute("DROP TABLE claims")
            s._conn.execute(_DDL_CLAIMS_SIN_AMBITO)
            for tenant, project in (("A", "X"),):
                s.upsert_entity(
                    tenant_id=tenant,
                    project_id=project,
                    entity=Entity(entity_id=SUJETO, kind="file", stable_key="a.py"),
                )
                s.register_source(
                    tenant_id=tenant,
                    project_id=project,
                    source=Source(
                        source_id=source_id(ORIGEN),
                        kind="local_file",
                        content_hash="h",
                        locator={},
                        git_commit_sha=None,
                        git_tree_sha=None,
                        working_tree_status=None,
                        checked_at="2026-10-07T00:00:00Z",
                        freshness="current",
                    ),
                )
            s._conn.execute(
                """
                INSERT INTO claims (
                    claim_id, tenant_id, project_id, subject_entity_id,
                    predicate, object_literal_json, source_id,
                    extraction_method, extractor_version, checked_at_revision,
                    valid_from_revision, valid_until_revision,
                    supersedes_claim_id, stale
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                # c-A caduca porque c-B la reemplaza. Los TRES valores de
                # B29 y el `stale` de B27 viajan aqui.
                (
                    "c-A",
                    "A",
                    "X",
                    SUJETO,
                    "imports_module",
                    '"psycopg"',
                    source_id(ORIGEN),
                    "m",
                    "v",
                    "rev0",
                    "rev0",
                    "rev1",
                    "c-B",
                    1,
                ),
            )
            s._conn.execute("UPDATE schema_version SET version=4")
            s._conn.commit()
            s._conn.close()

            nuevo = Storage(ruta)
            fila = nuevo._conn.execute(
                "SELECT valid_from_revision, valid_until_revision, "
                "supersedes_claim_id, stale FROM claims WHERE claim_id='c-A'"
            ).fetchone()
            assert tuple(fila) == ("rev0", "rev1", "c-B", 1), (
                "la migracion perdio VALORES de columnas que no son la clave: "
                f"{tuple(fila)}. El conteo de filas no lo ve, porque la fila "
                "sigue ahi: lo que se ha ido son las ventanas de B29 y la "
                "cadena de supersesion."
            )
            nuevo._conn.close()


class TestUnaBaseNuevaYUnaMigrada_DicenLoMismo:
    """**LA DIVERGENCIA ENTRE LOS DOS CAMINOS, QUE NO SE VE EN NINGUN OTRO
    TEST DEL BLOQUE.**

    Hay dos formas de que una base naciera con la identidad buena: la
    migracion `0005` y el `CREATE TABLE` de `schema.py`. Si divergen, cada
    base recien creada tiene una identidad distinta de cada base migrada, y
    **todo lo demas de este fichero pasa**: los tests abren bases por los dos
    caminos, cada uno ve lo suyo, y ninguno los compara.

    Por eso la propiedad es la COMPARACION y no la correccion de uno de los
    dos. Se leen las dos constraints al motor y se exige que sean la misma.
    """

    @staticmethod
    def _columnas_del_unique(s: Storage) -> frozenset[str]:
        filas = s._conn.execute(
            "SELECT name FROM pragma_index_list('claims') WHERE origin = 'u' AND \"unique\" = 1"
        ).fetchall()
        columnas: set[str] = set()
        for (nombre,) in filas:
            assert isinstance(nombre, str) and nombre.replace("_", "").isalnum()
            columnas |= {f[2] for f in s._conn.execute(f"PRAGMA index_info('{nombre}')").fetchall()}
        return frozenset(columnas)

    def test_los_dos_caminos_declaran_la_MISMA_identidad(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            # Camino 1: base NUEVA, la que produce `schema.py`.
            nueva = Storage(Path(tmp) / "nueva.sqlite")

            # Camino 2: base VIEJA migrada por `0005`.
            ruta_vieja = Path(tmp) / "vieja.sqlite"
            viejo = Storage(ruta_vieja)
            viejo._conn.execute("DROP TABLE claims")
            viejo._conn.execute(_DDL_CLAIMS_SIN_AMBITO)
            viejo._conn.execute("UPDATE schema_version SET version=4")
            viejo._conn.commit()
            viejo._conn.close()
            migrada = Storage(ruta_vieja)

            identity_nueva = self._columnas_del_unique(nueva)
            identity_migrada = self._columnas_del_unique(migrada)

            assert identity_nueva == identity_migrada, (
                "una base nueva y una migrada NO tienen la misma identidad: "
                f"nueva={sorted(identity_nueva)} migrada={sorted(identity_migrada)}. "
                "Arreglar solo uno de los dos deja el defecto en el otro, y "
                "cada test de este fichero solo ve el suyo."
            )
            nueva._conn.close()
            migrada._conn.close()


#: El DDL de `claims` TAL COMO ESTABA antes de R1.F.
#:
#: Va en el test y no en un fixture compartido porque **es el estado
#: historico**: si alguien lo cambiara para que "el caso viejo" dejara de
#: estar roto, el test seguiria en verde y habria dejado de medir la
#: migracion. Es una copia literal de la constraint de `0001`..`0004`.
_DDL_CLAIMS_SIN_AMBITO: str = """
CREATE TABLE claims (
    claim_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    subject_entity_id TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object_literal_json TEXT NOT NULL,
    source_id TEXT NOT NULL,
    assertion_origin TEXT NOT NULL DEFAULT 'observed',
    extraction_method TEXT NOT NULL,
    extractor_version TEXT NOT NULL,
    checked_at_revision TEXT NOT NULL,
    stale INTEGER NOT NULL DEFAULT 0,
    object_entity_id TEXT NOT NULL DEFAULT '',
    valid_from_revision TEXT,
    valid_until_revision TEXT,
    supersedes_claim_id TEXT,
    UNIQUE (subject_entity_id, predicate, source_id, checked_at_revision)
)
"""
