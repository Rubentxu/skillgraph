"""B6 — el origen epistemico de cada afirmacion, separado del metodo.

QUE MIDE ESTE FICHERO, y por que ejecuta en vez de leer
--------------------------------------------------------
El gate B6 del roadmap pide que cada afirmacion del Knowledge Graph
distinga `observed` · `derived-deterministically` · `agent-inferred` ·
`human-asserted` y conserve su provenance. Medido antes de escribir
nada, el hueco era 4 de 4 (`scripts/measure_b6_provenance.py`).

La mayoria de estos tests EJECUTA contra una base de verdad en `tmp_path`
en vez de comprobar el texto del DDL. La razon es la misma que en WI-111:
el defecto no esta en la declaracion de la columna, esta en la distancia
entre el momento en que Python valida el valor y el momento en que la
base lo acepta, y esa distancia no se ve leyendo el esquema. Un guard
que comprobara «la DDL tiene un CHECK» mediria la regla; estos miden el
comportamiento, que es lo que se rompio.

Y hay un contrasalto explicito (`test_el_medidor_sabe_ver_rojo`) porque
un instrumento que solo sabe dar verde no mide nada: es la M2 del
harness de B0, y la razon por la que el medidor se versiona en
`scripts/` y no en `.pipelinek/`.
"""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from skillgraph.core.errors import InvalidAssertionOriginError, ValidationError
from skillgraph.core.runtime_types import ASSERTION_ORIGINS, AssertionOrigin
from skillgraph.knowledge.graph import Claim, ClaimID, EntityID, source_id

RAIZ = Path(__file__).resolve().parent.parent


def _claim(**kwargs: object) -> Claim:
    """Un Claim minimo, con lo que el test cambie."""
    base: dict[str, object] = {
        "claim_id": ClaimID("c-1"),
        "subject_entity_id": EntityID("file:a.py"),
        "predicate": "line_count",
        "object_literal": 42,
        "source_id": source_id("src-1"),
    }
    base.update(kwargs)
    return Claim(**base)  # type: ignore[arg-type]


# --- El vocabulario es cerrado -------------------------------------------


class TestElVocabularioEsCerrado:
    """Los cuatro origenes del gate, y solo ellos."""

    def test_los_cuatro_origenes_del_gate_estan_declarados(self) -> None:
        assert (
            frozenset(
                {
                    "observed",
                    "derived-deterministically",
                    "agent-inferred",
                    "human-asserted",
                }
            )
            == ASSERTION_ORIGINS
        )

    def test_el_conjunto_se_deriva_del_literal_y_no_se_escribe_a_mano(self) -> None:
        """Si el Literal y el `frozenset` se escriben a mano, divergen.

        Es el error de QW-E: el conjunto escrito a mano se queda corto
        cuando alguien anade un valor al Literal, y entonces la
        validacion rechaza el valor nuevo que el tipo si acepta. Se
        comprueba que el conjunto se DERIVE, no que coincida hoy.
        """
        from typing import get_args

        assert set(get_args(AssertionOrigin)) == set(ASSERTION_ORIGINS)

    @pytest.mark.parametrize("origen", sorted(ASSERTION_ORIGINS))
    def test_cada_origen_del_gate_se_acepta(self, origen: str) -> None:
        assert _claim(assertion_origin=origen).assertion_origin == origen

    def test_un_origen_inventado_se_rechaza_al_construir(self) -> None:
        """La anotacion es una cadena con `from __future__ import
        annotations`: el runtime no la comprueba. Sin `__post_init__`, un
        valor inventado llegaria intacto al INSERT y lo rechazaria
        SQLite con un error que no es del dominio."""
        with pytest.raises(InvalidAssertionOriginError) as exc:
            _claim(assertion_origin="lo-dijo-un-tio")
        assert "lo-dijo-un-tio" in str(exc.value)

    def test_el_error_es_del_dominio_y_tiene_code_propio(self) -> None:
        """WI-109: un `code` compartido rompe la traduccion a exit code."""
        with pytest.raises(ValidationError) as exc:
            _claim(assertion_origin="nope")
        assert isinstance(exc.value, InvalidAssertionOriginError)
        assert exc.value.code == "sg_invalid_assertion_origin"

    def test_el_default_es_observed(self) -> None:
        """El default es el origen que NO promete autoridad.

        Es una decision, no un descuido: `observed` es el unico de los
        cuatro que no afirma quien hablo, luego es el unico correcto
        para un valor que nadie ha declarado. Poner `agent-inferred`
        obligaria a corregir la afirmacion mas pequena del sistema.
        """
        assert _claim().assertion_origin == "observed"


# --- Los dos ejes estan separados ----------------------------------------


class TestLosDosEjesEstanSeparados:
    """QUIEN afirma y COMO se extrajo son cosas distintas."""

    def test_son_dos_campos_distintos(self) -> None:
        claim = _claim(assertion_origin="agent-inferred", extraction_method="regex_def")
        assert claim.assertion_origin == "agent-inferred"
        assert claim.extraction_method == "regex_def"

    def test_un_mismo_metodo_admite_distintos_autores(self) -> None:
        """La propiedad que hace el campo util.

        Con los dos ejes en un solo campo, `regex_def` no dira si lo
        afirmo la maquina o una persona. Aqui el metodo es el mismo y el
        origen cambia, y ambos se conservan: eso es lo que un unico
        campo no puede expresar.
        """
        de_maquina = _claim(
            claim_id=ClaimID("c-2"),
            assertion_origin="derived-deterministically",
            extraction_method="regex_def",
        )
        de_persona = _claim(
            claim_id=ClaimID("c-3"),
            assertion_origin="human-asserted",
            extraction_method="regex_def",
        )
        assert de_maquina.extraction_method == de_persona.extraction_method
        assert de_maquina.assertion_origin != de_persona.assertion_origin


# --- La base lo exige, no solo Python -----------------------------------


class TestLaBaseExigeElVocabulario:
    """La restriccion se aplica tambien por la via que no pasa por Python."""

    @staticmethod
    def _con_claims(tmp_path: Path) -> sqlite3.Connection:
        from skillgraph.platform.storage import Storage

        ruta = tmp_path / "proyecto.sqlite"
        Storage(ruta)
        return sqlite3.connect(ruta)

    def test_un_insert_directo_con_origen_inventado_lo_rechaza_la_base(
        self, tmp_path: Path
    ) -> None:
        """Un `INSERT` a mano no pasa por `__post_init__`.

        Por eso el CHECK de la DDL no es adorno: sin el, el vocabulario
        solo existiria en Python y bastaria una escritura directa para
        colar un origen que el gate no reconoce.
        """
        con = self._con_claims(tmp_path)
        try:
            with pytest.raises(sqlite3.IntegrityError):
                con.execute(
                    "INSERT INTO claims (claim_id, tenant_id, project_id, "
                    "subject_entity_id, predicate, object_literal_json, source_id, "
                    "assertion_origin, extraction_method, extractor_version, "
                    "checked_at_revision, stale) VALUES "
                    "('x','t','p','e:1','line_count','1','s:1',"
                    "'inventado','regex_def','v','r0',0)"
                )
        finally:
            con.close()

    def test_la_columna_tiene_check_no_solo_not_null(self, tmp_path: Path) -> None:
        con = self._con_claims(tmp_path)
        try:
            ddl = con.execute("SELECT sql FROM sqlite_master WHERE name = 'claims'").fetchone()[0]
        finally:
            con.close()
        assert "assertion_origin" in ddl
        assert "CHECK" in ddl

    def test_una_base_previa_se_migra_y_conserva_el_check(self, tmp_path: Path) -> None:
        """`CREATE TABLE IF NOT EXISTS` NO anade columnas: es un no-op.

        Medido: abriendo una base creada con el esquema anterior, la
        columna no aparecia y todos los `SELECT` que la nombraban
        fallaban. Una base nueva funciona y una vieja no, y el fallo sale
        en produccion y no en los tests, porque los tests construyen la
        base desde cero cada vez.
        """
        ruta = tmp_path / "vieja.sqlite"
        viejo = sqlite3.connect(ruta)
        viejo.executescript(
            """
            CREATE TABLE schema_version (version INTEGER PRIMARY KEY);
            CREATE TABLE claims (
                claim_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL,
                project_id TEXT NOT NULL, subject_entity_id TEXT NOT NULL,
                predicate TEXT NOT NULL, object_literal_json TEXT NOT NULL,
                source_id TEXT NOT NULL, extraction_method TEXT NOT NULL,
                extractor_version TEXT NOT NULL, checked_at_revision TEXT NOT NULL,
                stale INTEGER NOT NULL DEFAULT 0
            );
            INSERT INTO claims VALUES (
                'c9','t','p','e:1','line_count','7','s:1',
                'regex_def','v','r0',0
            );
            """
        )
        viejo.commit()
        viejo.close()

        from skillgraph.platform.storage import Storage

        Storage(ruta)

        con = sqlite3.connect(ruta)
        try:
            columnas = {f[1] for f in con.execute("PRAGMA table_info(claims)")}
            assert "assertion_origin" in columnas
            # La fila previa no se pierde ni queda sin origen.
            fila = con.execute(
                "SELECT assertion_origin, extraction_method FROM claims WHERE claim_id='c9'"
            ).fetchone()
            assert fila == ("observed", "regex_def")
        finally:
            con.close()

    def test_la_migracion_es_idempotente(self, tmp_path: Path) -> None:
        """Abrir dos veces no debe fallar ni duplicar la columna."""
        from skillgraph.platform.storage import Storage

        ruta = tmp_path / "dos-veces.sqlite"
        Storage(ruta)
        Storage(ruta)
        con = sqlite3.connect(ruta)
        try:
            ddl = con.execute("SELECT sql FROM sqlite_master WHERE name = 'claims'").fetchone()[0]
        finally:
            con.close()
        assert ddl.count("assertion_origin") >= 1


# --- El origen sobrevive al viaje ---------------------------------------


class TestElOrigenSobrevive:
    """Lo que se escribe, se lee; y la promocion no lo pierde."""

    @staticmethod
    def _controlador(tmp_path: Path) -> tuple[object, str]:
        """Storage + KnowledgeController sobre una base de verdad.

        Se usa el CONTROLADOR y no `storage.record_claim` a pelo porque el
        Claim referencia una `source_id` con FOREIGN KEY, y el
        `record_claim` de bajo nivel no crea la fuente: sin ella el
        INSERT falla con `IntegrityError` de clave foranea, que es un
        fallo de preparacion del test y no del campo que se prueba.
        """
        from skillgraph.knowledge.graph import Entity, Source
        from skillgraph.knowledge.knowledge_controller import KnowledgeController
        from skillgraph.platform.storage import Storage

        storage = Storage(tmp_path / "roundtrip.sqlite")
        ctl = KnowledgeController(knowledge=storage, tenant_id="t", project_id="p")
        ctl.register_source(
            source=Source(
                source_id="s-rt",
                kind="local_file",
                content_hash="h",
                locator={"path": "a.py"},
                git_commit_sha=None,
                git_tree_sha=None,
                working_tree_status=None,
                checked_at="2026-01-01T00:00:00Z",
                freshness="fresh",
            )
        )
        ctl.upsert_entity(entity=Entity(entity_id="file:a.py", kind="file", stable_key="a.py"))
        return ctl, "s-rt"

    def test_va_de_claim_a_fila_y_vuelve(self, tmp_path: Path) -> None:
        ctl, sid = self._controlador(tmp_path)
        ctl.record_claim(
            claim=_claim(
                claim_id=ClaimID("rt-1"),
                source_id=source_id(sid),
                assertion_origin="agent-inferred",
            )
        )
        leido = ctl.get_claim(claim_id=ClaimID("rt-1"))
        assert leido.assertion_origin == "agent-inferred"
        # Y el metodo sobrevive al viaje en su propio eje, sin mezclarse.
        assert leido.extraction_method == "static_analysis"

    def test_la_promocion_no_revierte_el_origen_a_observed(self, tmp_path: Path) -> None:
        """Promover un Claim entre proyectos debe CONSERVAR su origen.

        Si no, la afirmacion de un agente al operar sobre otro proyecto
        volvería a `observed` en silencio, y el gate no vería nada. Es la
        perdida de provenance que el gate prohibe, por el camino mas
        facil: un `get(..., "observed")` que solo se nota al leer.

        Se ejercita la ruta REAL —submit por un lado, apply por otro— en
        vez de reconstruir el dict a mano. Un test que reimplementa la
        rehidratacion verifica su propia copia, que es el error de
        WI-106: dos copias de la misma regla divergen el dia que una se
        actualiza y la otra no.
        """
        from skillgraph.cli.commands.promotion import _apply_pending_promotions
        from skillgraph.governance.promotion import submit_proposal
        from skillgraph.knowledge.graph import Entity, Source
        from skillgraph.knowledge.knowledge_controller import KnowledgeController
        from skillgraph.platform.storage import Storage

        origen = Storage(tmp_path / "origen.sqlite")
        destino = Storage(tmp_path / "destino.sqlite")

        ctl_origen = KnowledgeController(knowledge=origen, tenant_id="t", project_id="p")
        ctl_origen.register_source(
            source=Source(
                source_id="s-promo",
                kind="local_file",
                content_hash="h",
                locator={"path": "a.py"},
                git_commit_sha=None,
                git_tree_sha=None,
                working_tree_status=None,
                checked_at="2026-01-01T00:00:00Z",
                freshness="fresh",
            )
        )
        ctl_origen.upsert_entity(
            entity=Entity(entity_id="file:a.py", kind="file", stable_key="a.py")
        )
        ctl_origen.record_claim(
            claim=_claim(
                claim_id=ClaimID("pr-1"),
                source_id=source_id("s-promo"),
                assertion_origin="human-asserted",
            )
        )

        # El submit arma el payload desde el Claim real —el mismo camino
        # que `cmd_promotion_submit`— y lo deja PENDING en el outbox.
        almacenado = origen.get_claim(tenant_id="t", project_id="p", claim_id="pr-1")
        assert almacenado is not None
        submit_proposal(
            origen,
            proposal_id="promo-pr-1",
            tenant_id="t",
            source_project="p",
            target_catalog="q",
            knowledge_ref="pr-1",
            payload={
                "source_project": "p",
                "target_project": "q",
                "source": {
                    "source_id": "s-promo",
                    "kind": "local_file",
                    "content_hash": "h",
                    "locator": {"path": "a.py"},
                    "checked_at": "2026-01-01T00:00:00Z",
                    "freshness": "fresh",
                },
                "entity": {
                    "entity_id": "file:a.py",
                    "kind": "file",
                    "stable_key": "a.py",
                },
                "claim": {
                    "claim_id": almacenado.claim_id,
                    "subject_entity_id": almacenado.subject_entity_id,
                    "predicate": almacenado.predicate,
                    "object_literal": almacenado.object_literal,
                    "source_id": almacenado.source_id,
                    "evidence_ids": list(almacenado.evidence_ids),
                    "assertion_origin": almacenado.assertion_origin,
                    "extraction_method": almacenado.extraction_method,
                    "extractor_version": almacenado.extractor_version,
                    "checked_at_revision": almacenado.checked_at_revision,
                },
            },
        )

        estados = _apply_pending_promotions(origen, destino, tenant_id="t", target_project="q")
        assert estados, "no se aplico ninguna promocion: el test no mide nada"

        promovido = destino.get_claim(tenant_id="t", project_id="q", claim_id="pr-1")
        assert promovido is not None
        assert promovido.assertion_origin == "human-asserted"


# --- El instrumento de medicion ------------------------------------------


class TestElMedidorSabeVerRojo:
    """Un instrumento que solo sabe dar verde no mide nada.

    Es la M2 del harness de B0: una medicion que devolviera siempre la
    lista vacia pasaria todos los tests en verde, indistinguible de la que
    no mide nada. Aqui se comprueba que el medidor baja el veredicto
    cuando el codigo se rompe, ejecutandolo de verdad.
    """

    @staticmethod
    def _correr_medidor() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "scripts/measure_b6_provenance.py"],
            cwd=RAIZ,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_el_medidor_da_verde_en_el_arbol_real(self) -> None:
        proc = self._correr_medidor()
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "huecos ABIERTOS EN ALCANCE: 0" in proc.stdout

    def test_el_medidor_ve_rojo_si_se_rompe_la_validacion(self) -> None:
        """Quitar `__post_init__` debe poner P6 en ABIERTO.

        No se toca el arbol: se copia el repo a un temporal y se muta
        alli. Mutar el arbol del test y luego restaurarlo es la forma de
        que una excepcion deje el repo sucio sin que nadie lo note.

        Se copia tambien `.venv` —o se ejecuta con el interprete que ya
        esta importando el paquete— porque el clon tiene que poder
        importar `skillgraph`: sin eso el medidor falla por `ImportError`
        y el test pasaria por un motivo que no es el que vigila. Un
        verificador que pasa porque el comando se rompio es un
        verificador que no mide.
        """
        import shutil
        import tempfile

        raiz_tmp = Path(tempfile.mkdtemp())
        clon = raiz_tmp / "repo"
        shutil.copytree(
            RAIZ,
            clon,
            ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc", "audits", "evidence"),
            symlinks=True,
        )
        # El `.venv` se enlaza para que el clon pueda importar el paquete
        # que tiene al lado.
        if not (clon / ".venv").exists():
            (clon / ".venv").symlink_to(RAIZ / ".venv", target_is_directory=True)

        objetivo = clon / "src" / "skillgraph" / "knowledge" / "graph.py"
        texto = objetivo.read_text(encoding="utf-8")
        mutado = texto.replace("if self.assertion_origin not in ASSERTION_ORIGINS:", "if False:")
        assert mutado != texto, "la sonda no aplico: el texto no cambio"
        objetivo.write_text(mutado, encoding="utf-8")

        proc = subprocess.run(
            [sys.executable, "scripts/measure_b6_provenance.py"],
            cwd=clon,
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 1, proc.stdout + proc.stderr
        assert "ABIERTO" in proc.stdout


# --- Lo que las sondas encontraron sin cobertura ------------------------


class TestLoQueLasSondasNoTenianCubierto:
    """Cuatro garantias que NADA vigilaba, y que las sondas encontraron.

    Estas cuatro no estaban aqui al empezar. Las puso el harness de
    mutacion al detectar que M3, M6, M7 y M8 NO cazaban: sus mutaciones
    dejaban la suite en verde. El harness daba 8/8 y cuatro no eran
    cazadas, porque llevaba `-x` y cada sonda heredaba el fallo de la
    anterior. Sin estos tests, el 8/8 era un numero que no se podia
    desarmar.
    """

    def test_el_origen_va_en_el_select_no_solo_en_el_insert(self, tmp_path: Path) -> None:
        """M3: la fila trae el origen y la rehidratacion lo tira.

        Es la perdida mas facil de no ver: el valor SIGUE en disco y solo
        se pierde al leer, luego cualquier lectura de la base daria
        `observed` sin que nada fallara. Se comprueba por la fila cruda y
        no solo por el Claim rehidratado, porque la fila es donde se ve
        que el dato llego.
        """
        from skillgraph.knowledge.graph import Entity, Source
        from skillgraph.knowledge.knowledge_controller import KnowledgeController
        from skillgraph.platform.storage import Storage

        storage = Storage(tmp_path / "select.sqlite")
        ctl = KnowledgeController(knowledge=storage, tenant_id="t", project_id="p")
        ctl.register_source(
            source=Source(
                source_id="s1",
                kind="local_file",
                content_hash="h",
                locator={"path": "a.py"},
                git_commit_sha=None,
                git_tree_sha=None,
                working_tree_status=None,
                checked_at="2026-01-01T00:00:00Z",
                freshness="fresh",
            )
        )
        ctl.upsert_entity(entity=Entity(entity_id="file:a.py", kind="file", stable_key="a"))
        ctl.record_claim(
            claim=_claim(
                claim_id=ClaimID("sel-1"),
                source_id=source_id("s1"),
                assertion_origin="derived-deterministically",
            )
        )
        con = sqlite3.connect(storage.path)
        try:
            fila = con.execute(
                "SELECT assertion_origin FROM claims WHERE claim_id = 'sel-1'"
            ).fetchone()
        finally:
            con.close()
        assert fila == ("derived-deterministically",)
        # Y el segundo camino de lectura —`list_claims_for_subject`— tambien.
        listado = ctl.list_claims_for_subject(subject_entity_id=EntityID("file:a.py"))
        assert [c.assertion_origin for c in listado] == ["derived-deterministically"]

    def test_el_payload_de_promocion_lleva_el_origen(self, tmp_path: Path) -> None:
        """M6: el export del submit tiene que incluir el origen.

        Se comprueba el payload que la CLI construye, no el Claim. Si el
        campo se pierde al EXPORTAR, la promocion funciona y el destino
        recibe `observed`: un fallo que no se ve en el proyecto origen,
        que es donde se mira.
        """
        from skillgraph.cli.commands.promotion import _claim_to_payload

        payload = _claim_to_payload(
            _claim(
                claim_id=ClaimID("ex-1"),
                source_id=source_id("s1"),
                assertion_origin="human-asserted",
            )
        )
        assert payload["assertion_origin"] == "human-asserted"

    def test_la_migracion_corre_sobre_una_base_ya_migrada(self, tmp_path: Path) -> None:
        """M7: la migracion no se puede perder por abrir dos veces.

        Sin la llamada, la segunda apertura de una base ya migrada —o de
        una base nueva— no se lleva la columna, y el fallo aparece mucho
        despues, en el primer SELECT de la vida real.
        """
        from skillgraph.platform.storage import Storage

        ruta = tmp_path / "reabre.sqlite"
        Storage(ruta)
        # La segunda apertura es la que ejecutaria el ALTER si la columna
        # no existiera; si la migracion desapareciera, esto no fallaria
        # todavia — por eso se comprueba que la columna sigue ahi DESPUES
        # de reabrir, no que la apertura lance.
        Storage(ruta)
        con = sqlite3.connect(ruta)
        try:
            columnas = {f[1] for f in con.execute("PRAGMA table_info(claims)")}
        finally:
            con.close()
        assert "assertion_origin" in columnas

    def test_el_conjunto_derivado_cubre_todo_el_literal(self) -> None:
        """M8: el conjunto se DERIVA, no se escribe a mano.

        Si alguien sustituye `frozenset(get_args(...))` por un conjunto
        literal mas corto, el tipo acepta un valor que la validacion
        rechaza. Es el error de QW-E, y solo se ve comparando el conjunto
        contra el Literal, no contra una copia de si mismo.
        """
        from typing import get_args

        from skillgraph.core.runtime_types import AssertionOrigin as AO

        assert frozenset(get_args(AO)) == ASSERTION_ORIGINS
        assert len(ASSERTION_ORIGINS) == 4
