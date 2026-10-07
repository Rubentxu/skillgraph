"""B25 — un hecho entre dos entidades se puede expresar.

Cada test nombra la propiedad que mide y **qué pasaría si fuera falsa**. Un
test que solo comprueba que algo no revienta mide que no ha reventado, que es
otra cosa.

La pieza que hay que mirar con atención es
`test_un_literal_que_looks_como_una_entidad_sigue_siendo_un_literal`: es la
que impide que R2 se cumpla por accidente de formato. Una implementación que
metiera la referencia dentro del JSON con una etiqueta pasaría los demás tests
y fallaría ese.

MEDIDO al escribir este fichero: 4/4 preguntas ABIERTAS en
`scripts/measure_b25_relaciones.py`.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from skillgraph.core.errors import (
    InvalidClaimObjectError,
    UnknownClaimPredicateError,
)
from skillgraph.core.runtime_types import CLAIM_PREDICATES, PredicadoDePack
from skillgraph.knowledge.graph import (
    Claim,
    Entity,
    EntityRef,
    Source,
    entity_id,
    entity_ref,
    predicado_de_pack,
    source_id,
)
from skillgraph.platform.storage import Storage

ORIGEN = "file:src/foo.py"
DESTINO = "file:src/bar.py"
PREDICADO_DE_PACK = "acme.git.has_remote"


def _storage(tmp_path: Path) -> Storage:
    return Storage(tmp_path / "b25.sqlite")


def _preparar(s: Storage, *, con_destino: bool = True) -> None:
    """Deja origen —y destino— registrados. Sin ellos, la FK del sujeto muerde."""
    s.upsert_entity(
        tenant_id="t",
        project_id="p",
        entity=Entity(entity_id=ORIGEN, kind="file", stable_key="src/foo.py"),
    )
    if con_destino:
        s.upsert_entity(
            tenant_id="t",
            project_id="p",
            entity=Entity(entity_id=DESTINO, kind="file", stable_key="src/bar.py"),
        )
    s.register_source(
        tenant_id="t",
        project_id="p",
        source=Source(
            source_id="local:src/foo.py",
            kind="local_file",
            content_hash="abc",
            locator={"path": "src/foo.py"},
            git_commit_sha=None,
            git_tree_sha=None,
            working_tree_status=None,
            checked_at="2026-10-06T00:00:00Z",
            freshness="current",
        ),
    )


def _claim(**cambios: object) -> Claim:
    base: dict[str, object] = {
        "claim_id": "clm-b25",
        "subject_entity_id": ORIGEN,
        "predicate": "imports_module",
        "object_literal": None,
        "source_id": "local:src/foo.py",
        "checked_at_revision": "r1",
    }
    base.update(cambios)
    return Claim(**base)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# R1 — el objeto puede ser otra entidad, y el sistema LO SABE
# ---------------------------------------------------------------------------


class TestElObjetoPuedeSerUnaEntidad:
    """La pregunta no es «¿lo acepta?» sino «¿lo diferencia?»."""

    def test_una_referencia_es_un_tipo_y_no_una_cadena(self) -> None:
        """El objeto entidad se distingue del objeto texto por SU TIPO.

        Si esto pasara con `Any`, entonces el claim guardaría dos cadenas y el
        sistema no sabría cuál apunta a algo — que es el defecto medido.
        """
        como_entidad = _claim(object_entity=entity_ref(DESTINO))
        como_texto = _claim(claim_id="clm-texto", object_literal=DESTINO)

        assert isinstance(como_entidad.object_entity, EntityRef)
        assert como_entidad.object_entity.entity_id == DESTINO
        # Y la diferencia NO es accidental: son de tipos distintos y no iguales.
        assert como_entidad != como_texto

    def test_hace_ida_y_vuelta_por_la_base_y_vuelve_igual(self, tmp_path: Path) -> None:
        """Entra, sale de disco, y conserva el TIPO — no solo el valor.

        Un round-trip que vuelve como `str` habría perdido justamente lo que
        B25 came to añadir, y un `==` no lo notaría: `EntityRef` no es igual a
        la cadena que lleva dentro.
        """
        s = _storage(tmp_path)
        _preparar(s)
        original = _claim(object_entity=entity_ref(DESTINO))

        s.record_claim(tenant_id="t", project_id="p", claim=original)
        leido = s.get_claim(tenant_id="t", project_id="p", claim_id=original.claim_id)

        assert leido is not None
        assert isinstance(leido.object_entity, EntityRef)
        assert leido.object_entity.entity_id == DESTINO
        assert leido == original

    def test_se_puede_preguntar_que_apunta_a_una_entidad(self, tmp_path: Path) -> None:
        """La consulta que B27 y B34 van a necesitar, y que hoy no existe.

        Sin esto, la referencia se guardaría y no se podría preguntar por ella:
        sería un dato que se escribe y nunca se lee, que es peor que no
        tenerlo.
        """
        s = _storage(tmp_path)
        _preparar(s)
        s.record_claim(
            tenant_id="t", project_id="p", claim=_claim(object_entity=entity_ref(DESTINO))
        )
        s.upsert_entity(
            tenant_id="t",
            project_id="p",
            entity=Entity(entity_id="file:src/tercer.py", kind="file", stable_key="src/tercer.py"),
        )
        s.record_claim(
            tenant_id="t",
            project_id="p",
            claim=_claim(
                claim_id="clm-otro",
                object_entity=entity_ref("file:src/tercer.py"),
            ),
        )
        s.record_claim(
            tenant_id="t", project_id="p", claim=_claim(claim_id="clm-lit", object_literal=137)
        )

        apuntan = s.list_claims_by_object_entity(
            tenant_id="t", project_id="p", object_entity_id=DESTINO
        )

        assert [c.claim_id for c in apuntan] == ["clm-b25"]

    def test_el_constructor_de_ref_rechaza_lo_que_no_es_una_entidad(self) -> None:
        """`entity_ref` valida el formato heredando el smart constructor.

        Si aceptara cualquier cadena, entonces «referencia a entidad» sería
        indistinguible de «texto» otra vez, y estaríamos en el punto de partida
        habiéndonos gastado un tipo.
        """
        from skillgraph.core.errors import InvalidEntityIDError

        with pytest.raises(InvalidEntityIDError):
            entity_ref("no-tiene-los-dos-puntos")


# ---------------------------------------------------------------------------
# R2 — un literal y una referencia no se pueden confundir
# ---------------------------------------------------------------------------


class TestExactamenteUno:
    """La invariante se sostiene en DOS capas, y se mide en las dos."""

    def test_python_rechaza_los_dos_objetos_a_la_vez(self) -> None:
        with pytest.raises(InvalidClaimObjectError):
            _claim(object_literal=137, object_entity=entity_ref(DESTINO))

    def test_python_rechaza_no_tener_ninguno(self) -> None:
        with pytest.raises(InvalidClaimObjectError):
            _claim(object_literal=None, object_entity=None)

    def test_la_base_rechaza_una_fila_con_los_dos(self, tmp_path: Path) -> None:
        """La invariante la sostiene la BASE, no solo Python.

        Es la diferencia entre una regla que se cumple cuando el proceso
        correcto la mira y una que se cumple siempre. Se escribe la fila a
        mano, saltándose el ADT, porque si se usara `record_claim` la prueba
        no distinguiría las dos capas.
        """
        s = _storage(tmp_path)
        _preparar(s)
        with pytest.raises(sqlite3.IntegrityError):
            s._conn.execute(
                "INSERT INTO claims (claim_id, tenant_id, project_id,"
                " subject_entity_id, predicate, object_literal_json, source_id,"
                " assertion_origin, extraction_method, extractor_version,"
                " checked_at_revision, stale, object_entity_id)"
                " VALUES ('x','t','p',?,'line_count','137','local:src/foo.py',"
                "'observed','static_analysis','v1','r1',0,?)",
                (ORIGEN, DESTINO),
            )

    def test_la_base_rechaza_una_fila_sin_ninguno(self, tmp_path: Path) -> None:
        s = _storage(tmp_path)
        _preparar(s)
        with pytest.raises(sqlite3.IntegrityError):
            s._conn.execute(
                "INSERT INTO claims (claim_id, tenant_id, project_id,"
                " subject_entity_id, predicate, object_literal_json, source_id,"
                " assertion_origin, extraction_method, extractor_version,"
                " checked_at_revision, stale, object_entity_id)"
                " VALUES ('x','t','p',?,'line_count','','local:src/foo.py',"
                "'observed','static_analysis','v1','r1',0,'')",
                (ORIGEN,),
            )

    def test_un_literal_que_parece_una_entidad_sigue_siendo_un_literal(
        self,
        tmp_path: Path,
    ) -> None:
        """LA PRUEBA QUE IMPIDE QUE R2 SE CUMPLA POR ACCIDENTE DE FORMATO.

        Una implementación que metiera la referencia dentro del JSON con una
        etiqueta `{"$entity": ...}` pasaría todos los tests anteriores y
        fallaría este: aquí la cadena tiene EXACTAMENTE la forma de un
        `EntityID`, y aun así es un texto, porque nadie ha dicho que sea una
        entidad.
        """
        s = _storage(tmp_path)
        _preparar(s)
        looks_like = _claim(claim_id="clm-parecido", object_literal=DESTINO)

        s.record_claim(tenant_id="t", project_id="p", claim=looks_like)
        leido = s.get_claim(tenant_id="t", project_id="p", claim_id="clm-parecido")

        assert leido is not None
        assert leido.object_entity is None
        assert leido.object_literal == DESTINO

    def test_la_referencia_apunta_a_una_entidad_que_existe(self, tmp_path: Path) -> None:
        """La integridad se recupera en Python, porque la columna no lleva FK.

        MEDIDO: con `PRAGMA foreign_keys = ON`, declarar
        `REFERENCES entities(entity_id)` en la columna **rechaza todos los
        claims literales**, porque el marcador `''` no es una entidad. Es decir:
        la columna no puede llevar la FK, y lo que se pueda perder se recupera
        en el borde de escritura. Si esto no lo rechazara, el grafo aceptaría
        relaciones hacia entidades que no existen y B27 no podría fiarse.
        """
        s = _storage(tmp_path)
        _preparar(s, con_destino=False)

        from skillgraph.core.errors import InvalidEntityIDError

        with pytest.raises(InvalidEntityIDError):
            s.record_claim(
                tenant_id="t",
                project_id="p",
                claim=_claim(object_entity=entity_ref(DESTINO)),
            )


# ---------------------------------------------------------------------------
# R3 — un pack añade un predicado sin tocar el núcleo
# ---------------------------------------------------------------------------


class TestElPredicadoDelPack:
    def test_un_predicado_con_namespace_se_acepta(self, tmp_path: Path) -> None:
        s = _storage(tmp_path)
        _preparar(s)
        claim = _claim(
            claim_id="clm-pack", object_literal=True, predicate=predicado_de_pack(PREDICADO_DE_PACK)
        )

        s.record_claim(tenant_id="t", project_id="p", claim=claim)
        leido = s.get_claim(tenant_id="t", project_id="p", claim_id="clm-pack")

        assert leido is not None
        assert leido.predicate == PREDICADO_DE_PACK

    def test_los_predicados_del_nucleo_no_crecen(self) -> None:
        """La promesa es «sin tocar el núcleo». Si el conjunto creciera, sería
        mentira: habría que editar el fichero mismo que la promesa dice no
        tocar."""
        assert len(CLAIM_PREDICATES) == 7
        assert PREDICADO_DE_PACK not in CLAIM_PREDICATES

    def test_sin_namespace_se_sigue_rechazando(self) -> None:
        """El contrasalto del criterio abierto.

        Si aceptara cualquier cadena, entonces `CLAIM_PREDICATES` sería una
        Formalidad y el único test que depende del rechazo
        (`test_claim_unknown_predicate_raises`) se pondría en rojo.
        """
        with pytest.raises(UnknownClaimPredicateError):
            _claim(predicate="not_a_real_predicate")

    def test_el_constructor_de_pack_rechaza_lo_sin_punto(self) -> None:
        with pytest.raises(UnknownClaimPredicateError):
            predicado_de_pack("not_a_real_predicate")

    def test_el_tipo_es_nominal(self) -> None:
        """`PredicadoDePack` es un tipo propio, no un `str` disfrazado.

        `AGENTS.md` §2.2: los strings que vienen de fuera con semántica propia
        son `NewType`. Con `Any` el type-checker no podría distingir un
        predicado del núcleo de uno del pack.
        """
        assert PredicadoDePack("acme.git.has_remote") == PREDICADO_DE_PACK


# ---------------------------------------------------------------------------
# R4 — nada de lo anterior rompe lo que ya funcionaba
# ---------------------------------------------------------------------------


class TestLoDeAntesSigueIgual:
    def test_un_literal_se_serializa_byte_a_byte_igual(self, tmp_path: Path) -> None:
        """El formato del literal no cambia NI UN BYTE.

        Si cambiara, cada fila ya escrita y cada hash que alguien calculó
        quedarían mal, y no habría forma de saberlo sin leerlos todos.
        """
        s = _storage(tmp_path)
        _preparar(s)
        s.record_claim(
            tenant_id="t",
            project_id="p",
            claim=_claim(claim_id="clm-lit", object_literal={"b": 2, "a": 1}),
        )

        fila = s._conn.execute(
            "SELECT object_literal_json FROM claims WHERE claim_id = ?", ("clm-lit",)
        ).fetchone()

        assert fila[0] == json.dumps({"b": 2, "a": 1}, sort_keys=True)

    def test_una_base_vieja_se_abre_y_sigue_funcionando(self, tmp_path: Path) -> None:
        """Una base creada con el esquema ANTERIOR se abre y se lee.

        Se construye a mano con el esquema viejo, para no abrir la puerta de
        atrás de «la migración se aplicó sola porque la base es nueva».
        """
        ruta = tmp_path / "vieja.sqlite"
        conn = sqlite3.connect(ruta)
        conn.executescript(
            """
            CREATE TABLE entities (entity_id TEXT PRIMARY KEY, tenant_id TEXT,
                project_id TEXT, kind TEXT, stable_key TEXT);
            CREATE TABLE sources (source_id TEXT PRIMARY KEY, tenant_id TEXT,
                project_id TEXT, kind TEXT, content_hash TEXT, locator_json TEXT,
                git_commit_sha TEXT, git_tree_sha TEXT, working_tree_status_json TEXT,
                checked_at TEXT, freshness TEXT);
            CREATE TABLE claims (claim_id TEXT PRIMARY KEY, tenant_id TEXT,
                project_id TEXT, subject_entity_id TEXT REFERENCES entities(entity_id),
                predicate TEXT NOT NULL, object_literal_json TEXT NOT NULL,
                source_id TEXT REFERENCES sources(source_id),
                assertion_origin TEXT NOT NULL DEFAULT 'observed',
                extraction_method TEXT NOT NULL, extractor_version TEXT NOT NULL,
                checked_at_revision TEXT NOT NULL, stale INTEGER NOT NULL DEFAULT 0);
            """
        )
        conn.commit()
        conn.close()

        s = Storage(ruta)  # abre y migra
        _preparar(s)
        s.record_claim(
            tenant_id="t", project_id="p", claim=_claim(claim_id="clm-vieja", object_literal=42)
        )
        leido = s.get_claim(tenant_id="t", project_id="p", claim_id="clm-vieja")

        assert leido is not None
        assert leido.object_literal == 42

    def test_la_fila_nueva_y_la_base_migrada_dicen_lo_mismo(self, tmp_path: Path) -> None:
        """El DDL de `schema.py` y la migración tienen que decir lo mismo.

        Si divergieran, habría dos formas de tener «la misma base» según cuándo
        se creara, y el que llegara tarde descubriría que su migración no era
        la que él creía.

        **Se comparan COLUMNAS E ÍNDICES, y no solo columnas.** El índice de
        B25 lo crea la migración y no el DDL —porque un `CREATE INDEX` sobre
        una columna ausente revienta `executescript` al abrir una base vieja—,
        así que comparar solo columnas dejaría pasar dos situations distintas
        sin que nada se notara: la base nueva sin índice, que es justo la que
        no tiene migraciones que correr.
        """
        nueva = _storage(tmp_path / "nueva")
        migrada = _storage(tmp_path / "migrada")

        cols_nuevas = [f[1] for f in nueva._conn.execute("PRAGMA table_info(claims)")]
        cols_migradas = [f[1] for f in migrada._conn.execute("PRAGMA table_info(claims)")]
        assert cols_nuevas == cols_migradas
        assert "object_entity_id" in cols_nuevas

        def _indices(s: Storage) -> set[str]:
            return {
                f[0]
                for f in s._conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='claims'"
                )
            }

        assert "idx_claims_object_entity" in _indices(nueva)
        assert _indices(nueva) == _indices(migrada)

    def test_los_siete_predicados_siguen_valiendo(self, tmp_path: Path) -> None:
        """Abrir el vocabulario no rompe los que ya estaban dentro."""
        s = _storage(tmp_path)
        _preparar(s)
        for pred in sorted(CLAIM_PREDICATES):
            s.record_claim(
                tenant_id="t",
                project_id="p",
                claim=_claim(
                    claim_id=f"clm-{pred}",
                    predicate=pred,
                    object_literal=True,
                ),
            )
        leidos = s.list_claims_by_predicate(tenant_id="t", project_id="p", predicate="line_count")
        assert [c.claim_id for c in leidos] == ["clm-line_count"]

    def test_entity_id_y_source_id_siguen_siendo_intactos(self) -> None:
        """Los smart constructors que ya existían no se han movido."""
        assert entity_id("file:a.py") == "file:a.py"
        assert source_id("local:a.py") == "local:a.py"
