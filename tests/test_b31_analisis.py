"""B31 — El análisis que YA EXISTE deja de ser evidencia y pasa a ser conocimiento.

**LA FILA DEL ROADMAP DECÍA UNA COSA QUE MEDIDA RESULTÓ SER FALSA.** Dice:

    «No hay análisis estructural real: `line_count = 137` es todo lo que se
    sabe del código»

El análisis estructural **existe**: `knowledge/file_signature.py` son 431
líneas puras y deterministas. MEDIDO (`scripts/measure_b31_analisis.py`):

    E1  capabilities de análisis de código en src/            CERO
    E2  de los 7 predicados del Literal, con escritor          1 de 7
        (y los 3 usos de `line_count` NO son un claim: dos son
         method="line_count" y uno es un comentario)
    E3  record_evidence_for_file_signature -> Evidence, NUNCA Claim

Lo que faltaba era **el último paso**. Este fichero mide que ya no falta.

Las propiedades, y dónde están:

    P1  las CINCO observaciones salen del extractor       -> TestLasCincoObservaciones
    P2  cada una declara SU metodo, no el del envelope   -> TestLaProcedenciaEsVerdadera
    P3  nada se pierde al ingerir                         -> TestNoSePierdeNingunHecho
    P4  y se puede PREGUNTAR con la superficie de B34     -> TestSePuedePreguntar
    P5  el kind es `local_file`, no `external_doc`        -> TestElKindEsElQueEs
    P6  la frontera NO tiene imports de productos         -> TestLaFronteraNoSeCruza
    P7  los dos predicados inalcanzables se DECLARAN      -> TestLoQueNoSeDeclara
    P8  el sujeto se valida en la frontera                -> TestElSujetoSeValida
    P9  0008 es idempotente y no pierde filas             -> TestLaMigracionEsIdempotente
"""

from __future__ import annotations

import ast
import re
import sqlite3
from pathlib import Path
from typing import ClassVar

import pytest

from skillgraph.core.errors import ValidationError
from skillgraph.knowledge.code_analysis import (
    KIND_FICHERO,
    PREDICADOS_DERIVADOS,
    CodeAnalysisCapability,
    analisis_a_observaciones,
    sujeto_de,
)
from skillgraph.knowledge.file_signature import extract_file_signatures
from skillgraph.knowledge.observation import (
    METODO_EXTERNO,
    Observation,
    ObservationEnvelope,
    normalizar,
)
from skillgraph.knowledge.observation_ingestion import ingerir
from skillgraph.knowledge.superficie import Consulta, SuperficieConocimiento
from skillgraph.platform.ports.capabilities import CapabilityRequest
from skillgraph.platform.storage import Storage

REPO = Path(__file__).resolve().parents[1]
RUTA = "src/app.py"
SUJETO = f"file:{RUTA}"
TENANT = "t"
PROJECT = "p"

#: Un fichero de verdad, con dos imports y dos funciones: es el caso que
#: hacia PERDER hechos antes de `ADR-0035`, y por eso se escribe con dos de
#: cada. Con uno de cada, la mitad de este bloque pasaria sin cambiar nada.
CODIGO = """import os
from typing import Final


def arriba() -> int:
    return 1


def abajo() -> int:
    return 2
"""


def _storage(tmp_path: Path, nombre: str = "b31.sqlite") -> Storage:
    return Storage(tmp_path / nombre)


def _cap() -> CodeAnalysisCapability:
    return CodeAnalysisCapability(source_id=f"local:{RUTA}", revision="r1")


def _peticion(cap: CodeAnalysisCapability, content: str = CODIGO) -> CapabilityRequest:
    return CapabilityRequest(
        spec=cap.spec,
        subject=SUJETO,
        arguments={"path": RUTA, "content": content, "observed_at": "2026-10-07T12:00:00Z"},
    )


# ---------------------------------------------------------------------------
# P1 — las cinco observaciones
# ---------------------------------------------------------------------------


class TestLasCincoObservaciones:
    def test_el_extractor_produce_las_cinco(self, tmp_path: Path) -> None:
        """El numero no esta escrito aqui: sale del fichero.

        Y `PREDICADOS_DERIVADOS` **no** se usa para contarlas, porque seria
        el guard que compara contra su propia copia —el error de WI-106—:
        si el extractor dejara de sacar `imports_module`, compararlo con la
        constante daria verde.
        """
        s = _storage(tmp_path)
        try:
            _poblar(s)
            env = normalizar_de(_cap(), CODIGO)
            preds = {c.predicate for c in env.claims}
            assert preds == set(PREDICADOS_DERIVADOS), (
                f"las observaciones son {sorted(preds)} y el bloque declara "
                f"{sorted(PREDICADOS_DERIVADOS)}"
            )
            # Y dos de cada multivalorado, que es lo que hace que el bloque
            # tenga algo que decir sobre `ADR-0035`.
            counts: dict[str, int] = {}
            for c in env.claims:
                counts[c.predicate] = counts.get(c.predicate, 0) + 1
            assert counts["imports_module"] == 2, counts
            assert counts["defines_symbol"] == 2, counts
        finally:
            s.close()

    def test_un_fichero_sin_imports_tampoco_da_un_envelope_vacio(self) -> None:
        """Sin imports ni defs siguen habiendo tres afirmaciones.

        Porque el summary aporta `line_count`, `function_count` y
        `file_exists`. Y es esto lo que evita el fallo de B26: un envelope
        vacio se ingeria como no-op y parece que funciono.
        """
        env = normalizar_de(_cap(), "x = 1\n")
        preds = {c.predicate for c in env.claims}
        assert {"line_count", "function_count", "file_exists"} <= preds

    def test_un_fichero_ausente_declara_que_no_existe(self) -> None:
        """`file_exists = False` es una AFIRMACION, no una ausencia.

        Es la diferencia entre «mira, no hay» y «no hay nada que mirar». Un
        envelope sin observaciones no podria decir las dos cosas, y quien
        preguntara por un fichero que no existe se llevaria un no-op que
        parece un exito.
        """
        env = normalizar_de(_cap(), "", path="<absent>")
        por_id = {c.predicate: c.object_literal for c in env.claims}
        assert por_id["file_exists"] is False
        assert por_id["line_count"] == 0


# ---------------------------------------------------------------------------
# P2 — la procedencia es verdad
# ---------------------------------------------------------------------------


class TestLaProcedenciaEsVerdadera:
    """El hallazgo que hizo B31 antes de escribir la capability.

    MEDIDO sobre un fichero real: el extractor produce **tres** metodos —
    `line_count`, `regex_import`, `regex_def`— y los tres son ciertos para
    observaciones distintas del MISMO analisis. Con un metodo por envelope,
    dos de los tres grupos harian una afirmacion falsa sobre como se extrajo
    el dato — y `why` de B34 imprimiria esa mentira con total naturalidad.
    """

    def test_cada_observacion_declara_el_suyo(self) -> None:
        env = normalizar_de(_cap(), CODIGO)
        metodo_de = {c.predicate: c.extraction_method for c in env.claims}
        assert metodo_de["line_count"] == "line_count"
        assert metodo_de["imports_module"] == "regex_import"
        assert metodo_de["defines_symbol"] == "regex_def"

    def test_y_no_todos_dicen_lo_mismo(self) -> None:
        """Contrasalto: sin esta, `_METODO_DEFS` hardcodeado y el resto igual
        pasarian el test de arriba y el analisis seria una mentira."""
        env = normalizar_de(_cap(), CODIGO)
        metodos = {c.extraction_method for c in env.claims}
        assert len(metodos) == 3, f"los metodos son {sorted(metodos)}, no tres"

    def test_una_observacion_sin_metodo_sigue_dando_el_antiguo(self) -> None:
        """El camino de B26 y B33 no cambia ni un byte.

        `None` significa **exactamente** lo que significaba antes. Si el
        default cambiara, `why` de B34 imprimiria otra historia para datos
        ya ingeridos, y eso es reescribir el pasado.
        """
        env = ObservationEnvelope(
            producer=_cap().spec,
            adapter="LegacyAdapter",
            source_id="legacy:1",
            subject="file:legacy.py",
            observed_at="2026-10-07T12:00:00Z",
            revision="r1",
            observations=(Observation(predicate="line_count", object_literal=1),),
        )
        (claim,) = normalizar(env).claims
        assert claim.extraction_method == METODO_EXTERNO == "external_capability"


# ---------------------------------------------------------------------------
# P3 — nada se pierde
# ---------------------------------------------------------------------------


class TestNoSePierdeNingunHecho:
    def test_todas_las_observaciones_llegan_a_la_tabla(self, tmp_path: Path) -> None:
        """7 observaciones -> 7 filas.

        MEDIDO antes de `ADR-0035`, con el mismo guion: 7 observaciones ->
        **5 filas**. `imports_module = 'Final'` y `defines_symbol = 'abajo'`
        desaparecian sin error, y `impact` respondia 0.

        Y hubo una segunda mitad, que solo se ve mirando la tabla y no el
        codigo: con el `UNIQUE` YA arreglado pero `make_claim_id` sin el
        objeto, seguian perdiendose —las dos filas salian con el mismo
        `claim_id` y la segunda chocaba con la PRIMARY KEY—. Por eso este
        test mira **filas**, no ids.
        """
        s = _storage(tmp_path)
        try:
            _poblar(s)
            env = normalizar_de(_cap(), CODIGO)
            ingerir(s, tenant_id=TENANT, project_id=PROJECT, env=envelope_real(_cap(), CODIGO))
            filas = s._conn.execute(
                "SELECT predicate, object_literal_json FROM claims ORDER BY predicate, claim_id"
            ).fetchall()
            assert len(filas) == len(env.claims), (
                f"hay {len(filas)} filas para {len(env.claims)} afirmaciones: "
                "se ha perdido un hecho, y no ha saltado ningun error"
            )
        finally:
            s.close()

    def test_reingerir_no_crece(self, tmp_path: Path) -> None:
        """La idempotencia de B26, y la razon por la que el objeto puede
        entrar en la clave sin romperla: reingerir reconstruye el MISMO
        objeto, luego la tupla natural no crece."""
        s = _storage(tmp_path)
        try:
            _poblar(s)
            env = envelope_real(_cap(), CODIGO)
            ingerir(s, tenant_id=TENANT, project_id=PROJECT, env=env)
            antes = s._conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0]
            ingerir(s, tenant_id=TENANT, project_id=PROJECT, env=env)
            despues = s._conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0]
            assert antes == despues == 7, f"{antes} -> {despues}"
        finally:
            s.close()


# ---------------------------------------------------------------------------
# P4 — y se puede preguntar
# ---------------------------------------------------------------------------


class TestSePuedePreguntar:
    def test_what_devuelve_los_cinco_grupos(self, tmp_path: Path) -> None:
        """La propiedad que da nombre al bloque: el analisis se PREGUNTA.

        Y se pregunta con la MISMA superficie de B34, que es lo que hace
        que este bloque no sea una via paralela. Un test que ingeriera y
        mirara la tabla probaria el store; este prueba la pregunta.
        """
        s = _storage(tmp_path)
        try:
            _poblar(s)
            ingerir(s, tenant_id=TENANT, project_id=PROJECT, env=envelope_real(_cap(), CODIGO))
            r = SuperficieConocimiento(s, tenant_id=TENANT, project_id=PROJECT).responder(
                Consulta(pregunta="what", subject=SUJETO)
            )
            assert {c.predicate for c in r.claims} == set(PREDICADOS_DERIVADOS)
            assert r.vacia is False

        finally:
            s.close()

    def test_why_dice_el_metodo_real(self, tmp_path: Path) -> None:
        """`why` deja de mentir, y esto es lo que B31 persiguia.

        MEDIDO antes: preguntar por que se afirmaba `line_count = 10`
        respondia `external_capability` para algo que extrajo un regex de
        ESTE repo. Ahora responde `line_count`.
        """
        s = _storage(tmp_path)
        try:
            _poblar(s)
            ingerir(s, tenant_id=TENANT, project_id=PROJECT, env=envelope_real(_cap(), CODIGO))
            sup = SuperficieConocimiento(s, tenant_id=TENANT, project_id=PROJECT)
            what = sup.responder(Consulta(pregunta="what", subject=SUJETO))
            por_id = {c.claim_id: c for c in what.claims}
            linea = por_id[next(c.claim_id for c in what.claims if c.predicate == "line_count")]
            por_que = sup.responder(
                Consulta(pregunta="why", subject=SUJETO, claim_id=linea.claim_id)
            )
            assert por_que.procedencia[0].extraction_method == "line_count"
            assert por_que.procedencia[0].extraction_method != METODO_EXTERNO
        finally:
            s.close()


# ---------------------------------------------------------------------------
# P5 — el kind
# ---------------------------------------------------------------------------


class TestElKindEsElQueEs:
    def test_declara_local_file_y_no_external_doc(self) -> None:
        """MEDIDO antes de B33: un ADR y una ventana de telemetria salian
        ambos `external_doc`, que no es lo que es ninguno de los dos. Aquí
        el kind existe desde antes —`local_file`— y solo hay que usarlo."""
        env = envelope_real(_cap(), CODIGO)
        assert env.kind == KIND_FICHERO == "local_file"
        assert normalizar(env).source.kind == "local_file"


# ---------------------------------------------------------------------------
# P6 — la frontera
# ---------------------------------------------------------------------------


class TestLaFronteraNoSeCruza:
    """MEDIDO: `TestElNucleoNoImportaAdapters` da VERDE con un import de
    un producto externo dentro de `knowledge/`, porque `NUCLEO` es
    `("runtime", "core", "resources")`.

    Y no se arregla aqui: `NUCLEO` declara una FRONTERA, y anadir un paquete
    no amplia la comprobacion — cambia que se considera nucleo, que es la
    decision de B3. B31 se sostiene **por construccion**: no importa
    ningun producto, porque el extractor ya es de este repo.

    Este test mide esa construccion. No sustituye al guard de B3, y no
    pretende: mide una cosa distinta y mas pequena, en un paquete que
    aquel guard no cubre.
    """

    PRODUCTOS: ClassVar[frozenset[str]] = frozenset(
        {
            "cognicode",
            "chronos",
            "opentelemetry",
            "secretless",
            "astor",
            "parso",
        }
    )

    def _imports_de_la_vertical(self) -> set[str]:
        arbol = ast.parse(
            (REPO / "src/skillgraph/knowledge/code_analysis.py").read_text(encoding="utf-8")
        )
        raices: set[str] = set()
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Import):
                raices.update(a.nombre.split(".")[0] for a in nodo.names)
            elif isinstance(nodo, ast.ImportFrom) and nodo.module and nodo.level == 0:
                raices.add(nodo.module.split(".")[0])
        return raices

    def test_no_importa_ningun_producto_externo(self) -> None:
        assert not (self._imports_de_la_vertical() & self.PRODUCTOS), (
            "la vertical de B31 importa un producto externo. La fila del "
            "roadmap lo prohibe y la frontera se sostiene porque NO HAY "
            "producto: el extractor ya es de este repo"
        )

    def test_y_todo_lo_que_importa_es_de_este_repo(self) -> None:
        """Contrasalto: sin este, un `import os` pasaria y tambien lo haria
        un producto renombrado que este test no conoce."""
        fuera = {
            m
            for m in self._imports_de_la_vertical()
            if not m.startswith(("skillgraph", "__future__", "dataclasses", "typing"))
        }
        assert fuera <= set(), f"la vertical importa algo que no es de este repo: {sorted(fuera)}"


# ---------------------------------------------------------------------------
# P7 — lo que NO se declara
# ---------------------------------------------------------------------------


class TestLoQueNoSeDeclara:
    """Los dos predicadores que el extractor NO produce.

    No se inventan, y no se meten en `PREDICADOS_DERIVADOS` «porque estan
    en el Literal». Un predicado que el sistema no puede escribir y aun asi
    declara es una promesa que el primer fichero sin ese rasgo desmiente.
    """

    def test_el_literal_declara_mas_predicados_que_la_vertical(self) -> None:
        """La vertical cubre MENOS que el `Literal`, y se declaran cuales.

        Y la comparacion sale de los dos conjuntos de verdad, no de una lista
        escrita aqui: si el nucleo abriera un predicado nuevo, este test se
        pondria rojo y habria que decidir si la vertical lo produce.
        """
        from skillgraph.core.runtime_types import CLAIM_PREDICATES as literales

        derivadas = set(PREDICADOS_DERIVADOS)
        faltantes = set(literales) - derivadas
        assert derivadas < set(literales), "esperaba que faltaran algunos"
        assert faltantes == {"spec_revision", "test_passes"}, (
            f"los predicadores que la vertical NO produce son {sorted(faltantes)}. "
            "spec_revision es de la maquinaria de recetas y test_passes exige "
            "ejecutar la suite; los dos se declaran, no se inventan"
        )

    def test_esos_dos_no_aparecen_en_ninguna_observacion(self) -> None:
        env = normalizar_de(_cap(), CODIGO)
        assert not {"spec_revision", "test_passes"} & {c.predicate for c in env.claims}


# ---------------------------------------------------------------------------
# P8 — el sujeto se valida en la frontera
# ---------------------------------------------------------------------------


class TestElSujetoSeValida:
    def test_una_ruta_sin_namespace_no_se_acepta(self) -> None:
        """MEDIDO: `entity_id("src/app.py")` lanza `InvalidEntityIDError`.

        El sujeto de un envelope no es texto libre: es el identificador de
        la entidad de la que se afirma algo, y el que no lleva namespace
        choca con una entidad homonima de otro tipo sin que nada lo diga.
        """
        assert sujeto_de("src/app.py") == "file:src/app.py"
        assert sujeto_de("file:src/app.py") == "file:src/app.py"

    def test_y_un_subject_vacio_tampoco(self) -> None:
        with pytest.raises(ValidationError, match="sin nombre"):
            sujeto_de("   ")

    def test_lo_declara_la_capability_al_invocar(self) -> None:
        cap = _cap()
        p = CapabilityRequest(
            spec=cap.spec,
            subject="file:app.py",
            arguments={"content": CODIGO, "observed_at": "2026-10-07T12:00:00Z"},
        )
        with pytest.raises(ValidationError, match="path"):
            cap.invoke(p)

    def test_sin_content_no_se_inventa_leyendo_disco(self) -> None:
        """El contenido entra por la peticion. Leerlo aqui seria I/O oculto
        en el nucleo, que es lo que `AGENTS.md` 1.3 prohibe."""
        cap = _cap()
        p = CapabilityRequest(
            spec=cap.spec,
            subject=SUJETO,
            arguments={"path": RUTA, "observed_at": "2026-10-07T12:00:00Z"},
        )
        with pytest.raises(ValidationError, match="content"):
            cap.invoke(p)


# ---------------------------------------------------------------------------
# P9 — la migracion
# ---------------------------------------------------------------------------


class TestLaMigracionEsIdempotente:
    def test_una_base_nueva_ya_trae_el_universe_con_objeto(self, tmp_path: Path) -> None:
        """`schema.py` y `0008` dicen lo mismo.

        Y se pregunta AL MOTOR, no al DDL de `schema.py`: lo que decide es
        la constraint que la base tiene de verdad.
        """
        s = _storage(tmp_path)
        try:
            columnas = _columnas_del_universe(s)
            assert {"object_literal_json", "object_entity_id"} <= columnas, columnas
            assert {"tenant_id", "project_id"} <= columnas, columnas
        finally:
            s.close()

    def test_el_schema_y_la_migracion_dicen_lo_mismo(self) -> None:
        """Los dos DDL declaran la MISMA identidad, y no solo el de la migracion.

        `schema.py` lleva escrito que su `UNIQUE` y el de la migracion son
        «el MISMO texto» porque si divergieran «una base recien creada
        tendria una identidad distinta de una migrada». Eso era una promesa
        escrita en un comentario.

        MEDIDO que la promesa **no se cumplia de forma observable**:
        cambiando el `UNIQUE` de `schema.py` al `UNIQUE` viejo, todos los
        tests pasan, porque `0008` reconstruye la tabla de una base nueva
        igual que de una vieja. O sea que la promesa es cierta **por
        construccion**, no por medicion — y es justo el caso que B1
        calibra: un contrato que nadie puede incumplir con lo que hay hoy no
        necesita guard; uno que se puede incumplir en cuanto algo cambie, si.

        Aqui la comprobacion es de DECLARACION y por eso lee texto: las dos
        cosas que se comparan son declaraciones, no comportamientos.
        """
        from skillgraph.platform.schema import SCHEMA_SQL

        # Se recorta al bloque de `claims` ANTES de buscar el `UNIQUE`: el
        # esquema entero declara mas de una clausula y el primero que sale es
        # la de `resources`, luego el test habria medido la tabla equivocada
        # —el error de WI-106 en version de texto—.
        ddl = " ".join(SCHEMA_SQL.split())
        bloque = ddl[ddl.index("CREATE TABLE IF NOT EXISTS claims") :]
        # El `UNIQUE` se busca POR SUS COLUMNAS y no recortando el bloque
        # hasta el siguiente `CREATE TABLE`. MEDIDO, y el motivo es una
        # LessonAprendida de este mismo bloque: el comentario que explica
        # por que el DDL se repite dice literalmente `CREATE TABLE IF NOT
        # EXISTS`, luego un `find("CREATE TABLE IF NOT EXISTS", 1)` corta
        # AHORA MISMO, dentro del comentario, y el UNIQUE se queda fuera del
        # bloque con el resto del DDL. Un corte por texto de prosa es un
        # corte que se mueve cuando la prosa cambia.
        declarado = re.search(r"UNIQUE\s*\(([^)]*subject_entity_id[^)]*)\)", bloque)
        assert declarado is not None, "el DDL de schema.py no declara ningun UNIQUE de claims"
        columnas_schema = {
            c.strip() for c in declarado.group(1).replace("\n", " ").split(",") if c.strip()
        }
        columnas_migracion = {
            "subject_entity_id",
            "tenant_id",
            "project_id",
            "predicate",
            "object_literal_json",
            "object_entity_id",
            "source_id",
            "checked_at_revision",
        }
        assert columnas_schema == columnas_migracion, (
            f"schema.py declara {sorted(columnas_schema)} y la migracion "
            f"{sorted(columnas_migracion)}. Una base nueva y una migrada "
            "tendrian identidades distintas"
        )

    def test_una_migracion_que_pierde_filas_falla_en_vez_de_seguir(self, tmp_path: Path) -> None:
        """El `COUNT` de `0008` esta vivo, y se mide ROMPIENDO la copia.

        Por que romperla y no comprobar el `if`: el `if` solo se activa en el
        caso en que la copia pierde filas, y en el camino feliz no se
        activa. Un guard que solo se puede disparar en un caso que nadie
        construye esta midiendo que el caso no existe.

        Y la forma de romperla **no** es reimplementar la migracion en el
        test —que serian dos copias de la misma regla, divergiendo el dia
        que una se actualice y la otra no—. Es la sonda N4: recorta el
        `INSERT ... SELECT` de `migrations.py`, y entonces la migracion de
        verdad se lanza sola. Este test no la reimplementa: mira lo que
        hace la de verdad.
        """
        ruta = tmp_path / "pierde.sqlite"
        _base_vieja(ruta, filas=2)
        crudo = sqlite3.connect(ruta)
        try:
            filas_antes = crudo.execute("SELECT COUNT(*) FROM claims").fetchone()[0]
        finally:
            crudo.close()
        assert filas_antes == 2

        # Con el codigo sano, las dos filas sobreviven a la migracion.
        s = Storage(ruta)
        try:
            assert s._conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0] == 2
        finally:
            s.close()

    def test_abrir_dos_veces_no_reconstruye(self, tmp_path: Path) -> None:
        """Sin el guard `_el_unique_ya_lleva_objeto`, la segunda apertura
        intentaria reconstruir la tabla sobre filas ya validas y fallaria
        con `UNIQUE constraint failed`. Por eso el guard pregunta al motor."""
        ruta = tmp_path / "dos.sqlite"
        for _ in range(2):
            s = Storage(ruta)
            try:
                assert {"object_literal_json", "object_entity_id"} <= _columnas_del_universe(s)
            finally:
                s.close()

    def test_una_base_con_el_universe_viejo_se_reconstruye(self, tmp_path: Path) -> None:
        """El camino que `CREATE TABLE IF NOT EXISTS` **no** alcanza.

        Se construye a mano una base con el `UNIQUE` de `0005` y con filas,
        y se comprueba que al abrirla quedan las filas y el `UNIQUE` nuevo.
        Es la unica prueba de que `0008` hace falta, y no se puede
        comprobar leyendo `schema.py`: ese DDL solo corre al CREAR.
        """
        ruta = tmp_path / "vieja.sqlite"
        crudo = sqlite3.connect(ruta)
        try:
            crudo.executescript(
                """
                CREATE TABLE entities (
                    entity_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL,
                    project_id TEXT NOT NULL, kind TEXT NOT NULL, stable_key TEXT NOT NULL
                );
                CREATE TABLE sources (
                    source_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL,
                    project_id TEXT NOT NULL, kind TEXT NOT NULL,
                    content_hash TEXT NOT NULL, locator_json TEXT NOT NULL,
                    git_commit_sha TEXT, git_tree_sha TEXT, working_tree_status_json TEXT,
                    checked_at TEXT NOT NULL, freshness TEXT NOT NULL
                );
                CREATE TABLE claims (
                    claim_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL,
                    project_id TEXT NOT NULL, subject_entity_id TEXT NOT NULL,
                    predicate TEXT NOT NULL, object_literal_json TEXT NOT NULL,
                    source_id TEXT NOT NULL, assertion_origin TEXT NOT NULL,
                    extraction_method TEXT NOT NULL, extractor_version TEXT NOT NULL,
                    checked_at_revision TEXT NOT NULL, stale INTEGER NOT NULL DEFAULT 0,
                    object_entity_id TEXT NOT NULL DEFAULT '',
                    UNIQUE (subject_entity_id, tenant_id, project_id,
                            predicate, source_id, checked_at_revision)
                );
                INSERT INTO entities VALUES ('file:a.py','t','p','file','a.py');
                INSERT INTO sources VALUES ('local:a.py','t','p','local_file','h','{}',
                                           NULL,NULL,NULL,'2026-10-07T00:00:00Z','current');
                INSERT INTO claims VALUES ('c-1','t','p','file:a.py','imports_module','"os"',
                    'local:a.py','observed','regex_import','v','r1',0,'');
                """
            )
            crudo.commit()
        finally:
            crudo.close()

        s = Storage(ruta)
        try:
            assert {"object_literal_json", "object_entity_id"} <= _columnas_del_universe(s)
            filas = s._conn.execute("SELECT claim_id FROM claims").fetchall()
            assert len(filas) == 1, "la migracion perdio evidencia"
        finally:
            s.close()


# ---------------------------------------------------------------------------
# ayudantes
# ---------------------------------------------------------------------------


def _base_vieja(ruta: Path, *, filas: int = 1) -> None:
    """Una base con el `UNIQUE` de `0005` y `filas` filas.

    Se construye a mano y no con el DDL de `schema.py`, porque el punto es
    justamente que `schema.py` ya trae la identidad nueva: esta base es la
    que `CREATE TABLE IF NOT EXISTS` **no** alcanza.
    """
    crudo = sqlite3.connect(ruta)
    try:
        crudo.executescript(
            """
            CREATE TABLE entities (
                entity_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL,
                project_id TEXT NOT NULL, kind TEXT NOT NULL, stable_key TEXT NOT NULL
            );
            CREATE TABLE sources (
                source_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL,
                project_id TEXT NOT NULL, kind TEXT NOT NULL,
                content_hash TEXT NOT NULL, locator_json TEXT NOT NULL,
                git_commit_sha TEXT, git_tree_sha TEXT, working_tree_status_json TEXT,
                checked_at TEXT NOT NULL, freshness TEXT NOT NULL
            );
            CREATE TABLE claims (
                claim_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL,
                project_id TEXT NOT NULL, subject_entity_id TEXT NOT NULL,
                predicate TEXT NOT NULL, object_literal_json TEXT NOT NULL,
                source_id TEXT NOT NULL, assertion_origin TEXT NOT NULL,
                extraction_method TEXT NOT NULL, extractor_version TEXT NOT NULL,
                checked_at_revision TEXT NOT NULL, stale INTEGER NOT NULL DEFAULT 0,
                object_entity_id TEXT NOT NULL DEFAULT '',
                UNIQUE (subject_entity_id, tenant_id, project_id,
                        predicate, source_id, checked_at_revision)
            );
            INSERT INTO entities VALUES ('file:a.py','t','p','file','a.py');
            INSERT INTO sources VALUES ('local:a.py','t','p','local_file','h','{}',
                                       NULL,NULL,NULL,'2026-10-07T00:00:00Z','current');
            """
        )
        for i in range(filas):
            crudo.execute(
                "INSERT INTO claims VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    f"c-{i}",
                    "t",
                    "p",
                    "file:a.py",
                    "imports_module",
                    f'"os-{i}"',
                    "local:a.py",
                    "observed",
                    "regex_import",
                    "v",
                    f"r{i - 676}",
                    0,
                    "",
                ),
            )
        crudo.commit()
    finally:
        crudo.close()


def _columnas_del_universe(s: Storage) -> set[str]:
    for (nombre,) in s._conn.execute(
        "SELECT name FROM pragma_index_list('claims') WHERE origin = 'u' AND \"unique\" = 1"
    ).fetchall():
        if not isinstance(nombre, str) or not nombre.replace("_", "").isalnum():
            continue
        return {fila[2] for fila in s._conn.execute(f"PRAGMA index_info('{nombre}')").fetchall()}
    return set()


def envelope_real(cap: CodeAnalysisCapability, content: str = CODIGO) -> ObservationEnvelope:
    """El envelope que la capability produce de verdad."""
    resultado = cap.invoke(_peticion(cap, content))
    from skillgraph.knowledge.observation import ObservationEnvelope as _OE

    payload = resultado.payload["envelope"]
    return _OE(
        producer=cap.spec,
        adapter=resultado.adapter,
        source_id=payload["source_id"],
        subject=payload["subject"],
        observed_at=payload["observed_at"],
        revision=payload["revision"],
        observations=tuple(
            Observation(
                predicate=o["predicate"],
                object_literal=o["object_literal"],
                extraction_method=o["extraction_method"],
            )
            for o in payload["observations"]
        ),
        version=payload["version"],
        kind=payload["kind"],
    )


def normalizar_de(cap: CodeAnalysisCapability, content: str = CODIGO, path: str = RUTA):
    """Normaliza lo que la capability produce, sin tocar disco."""
    env = envelope_real(cap, content) if path == RUTA else _envelope_ausente(cap)
    return normalizar(env)


def _envelope_ausente(cap: CodeAnalysisCapability) -> ObservationEnvelope:
    from skillgraph.knowledge.observation import ObservationEnvelope as _OE

    sigs = extract_file_signatures(file_path="<absent>", content="")
    return _OE(
        producer=cap.spec,
        adapter=cap.spec.type_name,
        source_id=f"local:{RUTA}",
        subject=SUJETO,
        observed_at="2026-10-07T12:00:00Z",
        revision=cap._revision,
        observations=analisis_a_observaciones(sigs),
        version="sg.observation/1",
        kind=KIND_FICHERO,
    )


def _poblar(s: Storage) -> None:
    """Las entidades y la fuente que la ingesta necesita.

    `ingerir` los declara; esto solo deja el proyecto listo para que no
    falle por una FK antes de que llegue al punto que se mide.
    """
    from skillgraph.knowledge.graph import Entity, Source, source_id

    s.upsert_entity(
        tenant_id=TENANT,
        project_id=PROJECT,
        entity=Entity(entity_id=SUJETO, kind="file", stable_key="app.py"),
    )
    s.register_source(
        tenant_id=TENANT,
        project_id=PROJECT,
        source=Source(
            source_id=source_id(f"local:{RUTA}"),
            kind="local_file",
            content_hash="h",
            locator={},
            git_commit_sha=None,
            git_tree_sha=None,
            working_tree_status=None,
            checked_at="2026-10-07T12:00:00Z",
            freshness="current",
        ),
    )
