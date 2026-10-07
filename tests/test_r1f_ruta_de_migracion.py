"""R1.F — la RUTA de la migracion, no solo su efecto.

**POR QUE ESTE FICHERO EXISTE, Y ES UNA DEUDA QUE EL BLOQUE ABRIO.**

`scripts/check_coverage_floors.py` dijo, al certificar:

    src/skillgraph/platform/migrations.py mide 23.81 %, por debajo de su
    suelo del 90 %

AGENTS.md 6.3 no perdona ese suelo por convenientemente忘记: un modulo que
cuelga de un subdirectorio de `src/skillgraph/` esta por encima del 90 %, y
un modulo con 23 % esta **sin probar** aunque sus pruebas lookinginden verde.
Los tests de `test_r1f_identidad_claim.py` comprueban el EFECTO —dos ambitos
coexisten, el upgrade conserva filas— pasando por la API de `Storage`, que
ademas crea la base desde cero y por tanto casi nunca entra en la rama que
falta.

**LA LISTA DE ESTOS TESTS SALE DEL ARBOL, NO DE UNA COPIA ESCRITA AHI.** Cada
test cubre una rama de `_claims_identidad_con_ambito` y de sus dos ayudantes,
que son las lineas que R1.F anadio y que nadie ejercito. Si manana la
migracion cambia, el nombre del test dice que rama dejaba de existir y el
fichero se queda pequeno a proposito: un fichero de cobertura que crece es
una migracion que nadie esta mirando.

**LO QUE NO SE MIDE AQUI Y POR QUE.** No se prueba la electrocutacion de
`comprueba_que_no_sea_mas_nueva` ni la carrera de `sincroniza`: esas ya las
cubren los tests de B12, y duplicarlas aqui seria un segundo sitio que
mantener. Este fichero cubre **lo que R1.F anadio y nadie ejecuto**.
"""

from __future__ import annotations

import sqlite3
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from skillgraph.knowledge.graph import Entity, Source, source_id
from skillgraph.platform import migrations
from skillgraph.platform.storage import Storage

SUJETO = "file:a.py"
ORIGEN = "local:a.py"


@contextmanager
def _vacia() -> Iterator[sqlite3.Connection]:
    """Una conexion cruda con SOLO el libro de migraciones.

    Sin `Storage`: aqui se quiere la conexion pelada para poder meter un DDL
    viejo a mano antes de que Corra nada.
    """
    with tempfile.TemporaryDirectory() as tmp:
        ruta = Path(tmp) / "x.sqlite"
        con = sqlite3.connect(ruta)
        try:
            con.execute(
                "CREATE TABLE schema_migrations (migration_id TEXT PRIMARY KEY, applied_at TEXT)"
            )
            con.execute("CREATE TABLE schema_version (version INTEGER PRIMARY KEY)")
            yield con
        finally:
            con.close()


def _crear_claims(con: sqlite3.Connection, ddl: str) -> None:
    con.execute(ddl)
    con.execute(
        """
        CREATE TABLE entities (
            entity_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL,
            project_id TEXT NOT NULL, kind TEXT NOT NULL,
            stable_key TEXT NOT NULL, content_json TEXT NOT NULL
        )
        """
    )
    con.execute(
        """
        CREATE TABLE sources (
            source_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL,
            project_id TEXT NOT NULL, kind TEXT NOT NULL,
            content_hash TEXT NOT NULL, locator_json TEXT NOT NULL
        )
        """
    )
    con.execute("INSERT INTO entities VALUES ('" + SUJETO + "', 'A', 'X', 'file', 'a.py', '{}')")
    con.execute(
        "INSERT INTO sources VALUES ('"
        + source_id(ORIGEN)
        + "', 'A', 'X', 'local_file', 'h', '{}')"
    )


#: El DDL de la epoca de B6: sin `assertion_origin`, sin FK, **y sin
#: `UNIQUE`**. Es el caso que hizo fallar la primera version de esta
#: migracion, y por eso tiene su propio test y no un parametro.
_DDL_SIN_UNIQUE: str = """
CREATE TABLE claims (
    claim_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL, subject_entity_id TEXT NOT NULL,
    predicate TEXT NOT NULL, object_literal_json TEXT NOT NULL,
    source_id TEXT NOT NULL, extraction_method TEXT NOT NULL,
    extractor_version TEXT NOT NULL, checked_at_revision TEXT NOT NULL,
    stale INTEGER NOT NULL DEFAULT 0
)
"""


class TestElDdlSeDerivaDelViejo:
    """**LA PREMISA DE LA MIGRACION, PROBADA COMO FUNCION PURA.**

    `_ddl_de_claims_con_ambito` no toca disco: recibe un DDL y devuelve
    otro. Eso la hace trivial de probar en los dos caminos, y es la razon de
    que la funcion exista separada del resto.
    """

    def test_sustituye_el_unique_existente_por_el_que_lleva_ambito(self) -> None:
        viejo = (
            "CREATE TABLE claims (\n"
            "    claim_id TEXT PRIMARY KEY,\n"
            "    subject_entity_id TEXT NOT NULL,\n"
            "    UNIQUE (subject_entity_id, predicate, source_id, checked_at_revision)\n"
            ")"
        )
        nuevo = migrations._ddl_de_claims_con_ambito(viejo)

        assert "tenant_id, project_id" in nuevo, nuevo
        assert "UNIQUE (subject_entity_id, predicate, source_id" not in nuevo, (
            f"el UNIQUE viejo sigue intacto: {nuevo}"
        )
        # El resto de la tabla no se toca. Es lo que impide que una
        # migracion de una constraint termine moviendo el resto del
        # esquema por sorpresa.
        assert "claim_id TEXT PRIMARY KEY" in nuevo
        assert nuevo.count("UNIQUE") == 1, f"la derivacion dejo mas de una constraint: {nuevo}"

    def test_anade_el_unique_a_una_tabla_que_no_tenia_ninguno(self) -> None:
        """El caso de B6, que reventaba con `near "UNIQUE": syntax error`."""
        nuevo = migrations._ddl_de_claims_con_ambito(_DDL_SIN_UNIQUE)

        assert "tenant_id, project_id" in nuevo, nuevo
        # Y sobre todo: QUE LO ACEPTE EL MOTOR. Una cadena que parece un
        # DDL no es un DDL; la pregunta la responde SQLite.
        with _vacia() as con:
            _crear_claims(con, nuevo)
            info = con.execute("PRAGMA table_info(claims)").fetchall()
            assert [f[1] for f in info][-1] == "stale", (
                f"la derivacion movio la ultima columna: {[f[1] for f in info]}"
            )

    def test_una_tabla_sin_cierre_falla_diciendo_que(self) -> None:
        with pytest.raises(sqlite3.IntegrityError) as exc:
            migrations._ddl_de_claims_con_ambito("CREATE TABLE claims a")
        assert "0005" in str(exc.value), f"el fallo no dice que migracion es: {exc.value}"


class TestLaRutaDeLaMigracion:
    """**CADA RAMA QUE R1.F ANADIO, EJECUTADA SOBRE UNA BASE CRUDA.**

    Las ramas que los tests del otro fichero no tocan, porque alli la base
    nace con el esquema actual y `0005` sale por su precondicion.
    """

    def test_una_base_sin_claims_no_se_reconstruye_mal(self) -> None:
        """Sin `claims` no hay nada que derivar, y el fallo lo DICE."""
        with _vacia() as con:
            with pytest.raises(sqlite3.IntegrityError) as exc:
                migrations._claims_identidad_con_ambito(con)
            assert "no hay DDL" in str(exc.value), exc.value

    def test_la_idempotencia_se_comprueba_CONTRA_EL_MOTOR(self) -> None:
        """`pragma_index_list` con `origin='u'`: solo las constraints.

        Un indice UNIQUE creado a mano tiene `origin='c'` y no cuenta, que
        es justo el caso en el que el codigo nuevo haria bien Y el metodo
        dejaria pasar una tabla sin la constraint de tabla.
        """
        with _vacia() as con:
            _crear_claims(con, _DDL_SIN_UNIQUE)
            # Un UNIQUE a mano, por indice y no por constraint de tabla.
            con.execute("CREATE UNIQUE INDEX idx_manual ON claims(tenant_id, claim_id)")
            assert migrations._el_unique_ya_lleva_ambito(con) is False, (
                "un indice UNIQUE a mano se tomo por la constraint de tabla"
            )

    def test_la_migracion_corre_sobre_una_base_vieja_sin_unique(self) -> None:
        """El recorrido entero: derivar, reconstruir, copiar y comprobar."""
        with _vacia() as con:
            _crear_claims(con, _DDL_SIN_UNIQUE)
            con.execute(
                "INSERT INTO claims VALUES "
                "('c-A','A','X','"
                + SUJETO
                + "','imports_module','\"psycopg\"','"
                + source_id(ORIGEN)
                + "','m','v','revA',0)"
            )
            migrations._claims_identidad_con_ambito(con)
            con.commit()

            fila = con.execute(
                "SELECT claim_id, tenant_id FROM claims WHERE claim_id='c-A'"
            ).fetchall()
            assert [tuple(f) for f in fila] == [("c-A", "A")], fila
            assert migrations._el_unique_ya_lleva_ambito(con) is True

    def test_la_migracion_es_idempotente_sobre_la_misma_base(self) -> None:
        with _vacia() as con:
            _crear_claims(con, _DDL_SIN_UNIQUE)
            con.execute(
                "INSERT INTO claims VALUES "
                "('c-A','A','X','"
                + SUJETO
                + "','imports_module','\"psycopg\"','"
                + source_id(ORIGEN)
                + "','m','v','revA',0)"
            )
            migrations._claims_identidad_con_ambito(con)
            migrations._claims_identidad_con_ambito(con)
            con.commit()

            filas = con.execute("SELECT claim_id FROM claims").fetchall()
            assert [f[0] for f in filas] == ["c-A"], filas


class TestLaMigracionEnUnStorageDeVerdad:
    """La misma migracion, pero entrando por la puerta que usa el producto.

    Los tests de `test_r1f_identidad_claim.py` ya la ejercitan por aqui; este
    bloque no repite sus propiedades, sino que cubre la **rama de error que
    solo aparece con el resto del esquema vivo**: una fila cuya entidad o
    fuente ya no existe.
    """

    def test_una_fila_con_referencia_rota_no_impide_migrar(self) -> None:
        """Una base con evidencia huerfana SIGUE abriendo.

        Es la situacion de la base de B6, y es la que decidio que la
        migracion derivara el DDL en vez de imponer uno fijo.

        **MEDIDO AL ESCRIBIRLO: la base ACTUAL si tiene FK**, luego con
        `Storage` no se puede ni insertar la fila huerfana —el motor la
        rechaza antes de que llegue la migracion—. Ese estado solo existe
        en una base de la epoca de B6, asi que el escenario se monta como
        lo monta `test_b6_provenance`: DDL viejo a mano y fila dentro.
        """
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "x.sqlite"
            base = sqlite3.connect(ruta)
            base.executescript(_ESQUEMA_B6)
            base.commit()
            base.close()

            # Abrirlo con `Storage` crea el resto del esquema y corre
            # `sincroniza`, que aplica `0005` sobre la tabla de B6.
            s = Storage(ruta)
            fila = s._conn.execute(
                "SELECT subject_entity_id, source_id FROM claims WHERE claim_id='c-h'"
            ).fetchone()
            assert tuple(fila) == ("e:no-existe", "s:no-existe"), fila
            assert migrations._el_unique_ya_lleva_ambito(s._conn) is True
            s._conn.close()

    def test_el_ambito_llega_hasta_la_consulta_por_revision(self) -> None:
        """La property de R1.F, por la API que el producto usa de verdad."""
        with tempfile.TemporaryDirectory() as tmp:
            s = Storage(Path(tmp) / "x.sqlite")
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
            from skillgraph.knowledge.graph import Claim

            for tenant, project, cid in (("A", "X", "c-A"), ("B", "Y", "c-B")):
                s.record_claim(
                    tenant_id=tenant,
                    project_id=project,
                    claim=Claim(
                        claim_id=cid,
                        subject_entity_id=SUJETO,
                        predicate="imports_module",
                        object_literal="psycopg",
                        source_id=source_id(ORIGEN),
                        assertion_origin="observed",
                        checked_at_revision="revA",
                    ),
                )

            for tenant, project, esperado in (("A", "X", "c-A"), ("B", "Y", "c-B")):
                vistos = {
                    c.claim_id
                    for c in s.claims_at_revision(
                        tenant_id=tenant,
                        project_id=project,
                        subject_entity_id=SUJETO,
                        revision="revA",
                    )
                }
                assert vistos == {esperado}, (
                    f"{tenant}/{project} ve {vistos} y deberia ver {{{esperado}}}"
                )
            s._conn.close()


#: El esquema de la epoca de B6 con UNA fila huerfana dentro.
#:
#: Es el unico lugar donde «`claims` sin `REFERENCES` y con una referencia
#: rota» existe de verdad: el esquema actual no lo permite, porque el motor
#: rechaza la fila al insertarla. Por eso el test monta la base a mano en vez
#: de usar `Storage` —que es justo lo que hace `test_b6_provenance`.
#:
#: La fila se llama `c-h` («huerfana») para que el fallo de una asercion
#: diga de que se trata sin tener que abrir este fichero.
_ESQUEMA_B6: str = """
CREATE TABLE schema_version (version INTEGER PRIMARY KEY);
CREATE TABLE claims (
    claim_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    subject_entity_id TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object_literal_json TEXT NOT NULL,
    source_id TEXT NOT NULL,
    extraction_method TEXT NOT NULL,
    extractor_version TEXT NOT NULL,
    checked_at_revision TEXT NOT NULL,
    stale INTEGER NOT NULL DEFAULT 0
);
INSERT INTO claims VALUES (
    'c-h', 'A', 'X', 'e:no-existe', 'line_count', '7', 's:no-existe',
    'regex_def', 'v', 'r0', 0
);
"""
