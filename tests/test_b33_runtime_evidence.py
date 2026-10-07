"""B33 — Runtime evidence vertical: lo que se VIO deja de disfrazarse de documento.

**LO QUE ESTE FICHERO MIDE Y POR QUE NO ES «UNA FUNCION MAS».** El gate que
el roadmap escribe para B33 —«un claim runtime que contradice un ADR abre
conflicto; `actual_behavior` prefiere runtime e `intended_architecture`
prefiere la decisión aceptada»— **ya se cumplía antes de escribir nada**,
porque es el ejemplo con el que B28 certificó su propio bloque: su
`_el_conflicto_del_bloque` se llama `c-runtime` contra `c-adr`.

Medido sobre un store de verdad, antes de escribir una línea de B33:

```
fuentes:  adr:0001           kind=external_doc   c-adr       "psycopg"  human-asserted
          runtime:ventana-1  kind=external_doc   c-runtime  "sqlite3"  observed
conflicts_for        -> 1 conflicto: [c-adr, c-runtime]
resolver actual_behavior   -> c-runtime
resolver intended_behavior -> c-adr
```

Es decir: **el gate de B33 mide el resolver de B28**. Un guard que lo
reutilizara se pondría en verde sin que existiera una sola línea de B33, y
esta clase (`TestElGateDelRoadmapYaLoCumpliaB28`) ata que no se pueda
declarar el bloque cerrado con el test de otro.

Las propiedades que sí son de B33, y dónde están:

    P1  el kind de runtime existe y es del Literal   -> TestElKindDeRuntimeExiste
    P2  lo que se vio se registra como runtime      -> TestLaObservacionDeRuntimeNoEsUnDocumento
    P3  la ventana se persiste y se relee de DISCO   -> TestLaVentanaAguantaElIdaYVuelta
    P4  `hasta=None` es ventana ABIERTA, no sin dato -> TestUnaVentanaSinHastaEstaAbierta
    P5  cerrar un periodo que no empezo es imposible -> TestNoSeCierraUnPeriodoQueNoEmpezo
    P6  una ventana sobre un kind de contenido        -> TestUnaVentanaSobreUnCommitEsCategoriaEquivocada
    P7  una base VIEJA recibe las columnas            -> TestUnaBaseViejaRecibeLaVentana
    P8  la vertical entera                            -> TestLaVerticalEntera
    P9  la capability NO lee el reloj (AGENTS 1.3)    -> TestLaCapabilityNoLeeElReloj
    P10 la capability NO escribe en el store          -> TestLaCapabilityNoEscribe
    P11 ventana de runtime y ventana de vigencia      -> TestLosDosRelojesSiguenSiendoDistintos
    P12 la consulta por ventana tiene indice          -> TestLaVentanaSeConsultaConIndice

**P7 es la que casi se lleva el bloque.** La primera versión puso el índice
`idx_sources_ventana` también en `schema.py`, junto al `CREATE TABLE`. Sobre
una base NUEVA funciona; sobre una base VIEJA —que ya tiene `sources` sin las
columnas— el `CREATE TABLE IF NOT EXISTS` es un no-op y el `CREATE INDEX`
siguiente revienta con `no such column: observed_from` ANTES de que corra
ninguna migración. Lo caza `TestUnaBaseViejaSeAbre`, de B25. El índice
quedó solo en la migración `0007`, y el motivo está escrito en `schema.py`
junto al sitio donde NO está, que es donde alguien lo volvería a poner.
"""

from __future__ import annotations

import ast
import inspect
import re
import sqlite3
import typing
from pathlib import Path

import pytest

from skillgraph.core.errors import EnvelopeInvalido, InvalidSourceError, ValidationError
from skillgraph.core.runtime_types import SOURCE_KINDS, SourceKind
from skillgraph.knowledge.graph import Claim, Entity, Source, source_id
from skillgraph.knowledge.observation import (
    Observation,
    ObservationEnvelope,
    normalizar,
)
from skillgraph.knowledge.observation_ingestion import ingerir
from skillgraph.knowledge.telemetry_query import (
    KIND_RUNTIME,
    TELEMETRY_QUERY,
    LectorTelemetria,
    TelemetryQueryCapability,
    Ventana,
)
from skillgraph.platform.ports.capabilities import CapabilityRequest, CapabilitySpec
from skillgraph.platform.storage import Storage

SUJETO = "servicio:checkout"
ADY = "adr:0042"


# ---------------------------------------------------------------------------
# Los ayudantes. Un lector que NO sabe nada de Chronos, a proposito.
# ---------------------------------------------------------------------------


class DobleDePrueba:
    """Un lector que devuelve lo que se le pone. CERO Chronos, y su nombre lo
    declara: es un **doble**, no un adaptador.

    Existe para que el test de la vertical no dependa de una herramienta
    externa. El puerto real es `LectorTelemetria`, y que este lo cumpla se
    mide con `isinstance` en `test_el_doble_cumple_el_puerto`.
    """

    def __init__(self, observaciones: tuple[Observation, ...] = ()) -> None:
        self.observaciones_a_devolver = observaciones
        self.llamadas: list[tuple[str, Ventana]] = []

    def observaciones(self, *, sujeto: str, ventana: Ventana) -> tuple[Observation, ...]:
        self.llamadas.append((sujeto, ventana))
        return self.observaciones_a_devolver


def _observacion(valor: object = "sqlite3") -> Observation:
    return Observation(predicate="imports_module", object_literal=valor)


def _peticion(ventana: Ventana, *, observado_en: str = "2026-10-07T12:00:00Z") -> CapabilityRequest:
    return CapabilityRequest(
        spec=CapabilitySpec(type_name=TELEMETRY_QUERY, summary="t"),
        subject=SUJETO,
        arguments={
            "ventana": {"desde": ventana.desde, "hasta": ventana.hasta},
            "observed_at": observado_en,
        },
    )


def _storage(tmp_path: Path, nombre: str = "b33.sqlite") -> Storage:
    return Storage(tmp_path / nombre)


def _source(**cambios: object) -> Source:
    base: dict[str, object] = {
        "source_id": source_id("runtime:v1"),
        "kind": KIND_RUNTIME,
        "content_hash": "h",
        "locator": {"adapter": "prueba"},
        "git_commit_sha": None,
        "git_tree_sha": None,
        "working_tree_status": None,
        "checked_at": "2026-10-07T12:00:00Z",
        "freshness": "current",
    }
    base.update(cambios)
    return Source(**base)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# P1 — el kind existe, y el conjunto se deriva del Literal
# ---------------------------------------------------------------------------


class TestElKindDeRuntimeExiste:
    def test_el_valor_esta_en_el_literal(self) -> None:
        assert KIND_RUNTIME in typing.get_args(SourceKind), (
            f"{KIND_RUNTIME!r} no esta en SourceKind {typing.get_args(SourceKind)}. "
            "Sin el, una observacion de runtime solo puede registrarse como "
            "external_doc, que no es lo que es"
        )

    def test_el_conjunto_se_deriva_del_literal_y_no_al_reves(self) -> None:
        """Regla QW-E, la misma que `ASSERTION_ORIGINS` y `QUERY_INTENTS`.

        Un conjunto escrito a mano es una segunda fuente de verdad que se
        desincroniza en cuanto alguien anade un valor al `Literal`, y la
        validacion rechaza el valor nuevo mientras el tipo lo acepta. B25
        sufrio exactamente esa divergencia.
        """
        assert frozenset(typing.get_args(SourceKind)) == SOURCE_KINDS, (
            "SOURCE_KINDS no se deriva de SourceKind. Si estan separados, "
            "SOURCE_KINDS es una segunda fuente de verdad"
        )


# ---------------------------------------------------------------------------
# P2 — LA PROPIEDAD DE B33: lo que se vio no es un documento
# ---------------------------------------------------------------------------


class TestLaObservacionDeRuntimeNoEsUnDocumento:
    """La property central del bloque, y la que no hacia falta un resolver.

    MEDIDO antes de arreglarlo: el unico modo de registrar una observacion
    de runtime era declararla `external_doc`, y entonces un ADR y una
    ventana de telemetria salian de la MISMA consulta con el MISMO kind:

        adr:0001           kind=external_doc
        runtime:ventana-1  kind=external_doc     <- indistinguibles
    """

    def test_un_envelope_sin_kind_sigue_siendo_external_doc(self) -> None:
        """**El que NO debe cambiar.** `None` significa exactamente lo que
        significaba antes de B33.

        Sin esta asercion, un bloque que declarase el kind nuevo podria
        romper a todo adaptador existente sin que ningun test seMovies: el
        fallo aparece en la ingesta de otro bloque, tres capas mas abajo.
        """
        env = ObservationEnvelope(
            producer=CapabilitySpec(type_name="sg.otro", summary="s"),
            adapter="otro",
            source_id=source_id("doc:1"),
            subject=SUJETO,
            observed_at="2026-10-07T12:00:00Z",
            revision="r1",
            observations=(_observacion(),),
        )
        assert normalizar(env).source.kind == "external_doc"

    def test_un_envelope_que_declara_runtime_se_normaliza_como_runtime(self) -> None:
        env = ObservationEnvelope(
            producer=CapabilitySpec(type_name=TELEMETRY_QUERY, summary="s"),
            adapter="chronos",
            source_id=source_id("runtime:v1"),
            subject=SUJETO,
            observed_at="2026-10-07T12:00:00Z",
            revision="r1",
            observations=(_observacion(),),
            kind=KIND_RUNTIME,
            observed_from="2026-10-07T00:00:00Z",
            observed_to="2026-10-07T12:00:00Z",
        )
        ingesta = normalizar(env)
        assert ingesta.source.kind == KIND_RUNTIME
        assert ingesta.source.observed_from == "2026-10-07T00:00:00Z"
        assert ingesta.source.observed_to == "2026-10-07T12:00:00Z"

    def test_el_claim_sale_observed_todavia(self) -> None:
        """La mecanica de B26 no se toca: lo que cambia es DE DONDE sale, no
        COMO se declara. Un cambio aqui seria un segundo reloj epistemico."""
        env = ObservationEnvelope(
            producer=CapabilitySpec(type_name=TELEMETRY_QUERY, summary="s"),
            adapter="chronos",
            source_id=source_id("runtime:v1"),
            subject=SUJETO,
            observed_at="2026-10-07T12:00:00Z",
            revision="r1",
            observations=(_observacion(),),
            kind=KIND_RUNTIME,
            observed_from="2026-10-07T00:00:00Z",
        )
        assert normalizar(env).claims[0].assertion_origin == "observed"

    def test_un_kind_inventado_no_llega_a_la_base(self) -> None:
        """Se rechaza EN EL ENVELOPE, no en `Source`.

        `Source.__post_init__` tambien lo rechazaria, pero con un mensaje
        que habla de `Source` cuando el que escribio el dato estaba
        construyendo un envelope: el error señala el sitio equivocado.
        """
        with pytest.raises(EnvelopeInvalido):
            ObservationEnvelope(
                producer=CapabilitySpec(type_name=TELEMETRY_QUERY, summary="s"),
                adapter="x",
                source_id=source_id("runtime:v2"),
                subject=SUJETO,
                observed_at="2026-10-07T12:00:00Z",
                revision="r1",
                observations=(_observacion(),),
                kind="telemetria_v2",  # type: ignore[arg-type]
            )


# ---------------------------------------------------------------------------
# P3 y P4 — la ventana persiste, y `None` significa ABIERTA
# ---------------------------------------------------------------------------


class TestLaEntradaMalformadaSeNombra:
    """Las cuatro formas en que una peticion puede venir rota.

    **POR QUE SON CUATRO Y NO UNA.** La suberficie de `arguments` es un
    `dict` libre: `ventana` puede faltar, puede no ser un mapping, puede ser
    un mapping sin `desde`, y `hasta` puede venir con una cadena vacia. Son
    cuatro Prefectos distintos con cuatro mensajes distintos, y un solo
    `if` los trataria igual — que es justo el defecto que
    `KnowledgeQueryCapability._consulta_de` ya evita en el modulo de al lado
    con el motivo escrito: «no se que preguntar» y «no hay nada» se
    confunden tres capas mas abajo.

    Se miden los cuatro porque la cobertura los dejo sin mirar al entrar el
    modulo nuevo (91 %, justo sobre el suelo del 90). Cerrarlos es subir el
    modulo, que es lo que se hace; bajar el suelo no.
    """

    def _cap(self) -> TelemetryQueryCapability:
        return TelemetryQueryCapability(
            _Lector_que_devuelve((_observacion(),)), source_id="runtime:v1", revision="r1"
        )

    def _peticion_sin(self, argumentos: dict[str, object]) -> CapabilityRequest:
        return CapabilityRequest(
            spec=CapabilitySpec(type_name=TELEMETRY_QUERY, summary="t"),
            subject=SUJETO,
            arguments=argumentos,
        )

    def test_ventana_ausente_lo_dice(self) -> None:
        with pytest.raises(ValidationError, match=r"arguments\['ventana'\]"):
            self._cap().invoke(self._peticion_sin({"observed_at": "2026-10-07T12:00:00Z"}))

    def test_ventana_que_no_es_mapping_lo_dice(self) -> None:
        """Un `str` donde se esperaba un mapping.

        Y el mensaje enseña **lo que recibio**, no solo que no vale: quien lo
        lea necesita ver el `str` para entender que su cliente serializa mal.
        """
        with pytest.raises(ValidationError, match="'una ventana'"):
            self._cap().invoke(
                self._peticion_sin(
                    {"ventana": "una ventana", "observed_at": "2026-10-07T12:00:00Z"}
                )
            )

    def test_ventana_sin_desde_lo_dice(self) -> None:
        """Distinto del mensaje de «no hay ventana», y tiene que serlo: una
        ventana sin `desde` es media ventana, y tratarla como si faltara
        entera haria que el que la pide corrigiera el sitio equivocado."""
        with pytest.raises(ValidationError, match="sin principio"):
            self._cap().invoke(
                self._peticion_sin(
                    {
                        "ventana": {"hasta": "2026-10-07T12:00:00Z"},
                        "observed_at": "2026-10-07T12:00:00Z",
                    }
                )
            )

    def test_hasta_vacio_se_rechaza_en_la_ventana(self) -> None:
        """`hasta=""` es peor que no dar `hasta`.

        `None` significa «la ventana sigue abierta», que es una
        declaracion; `""` parece lo mismo y significa que no se sabe nada.
        """
        with pytest.raises(ValidationError, match="no se cierra"):
            Ventana(desde="2026-10-07T00:00:00Z", hasta="   ")

    def test_observed_at_vacio_lo_dice(self) -> None:
        """Y este mensaje explica el POR QUE, no solo el QUE.

        «La capability no lee el reloj» es lo que hace que un `observed_at`
        vacio sea un fallo y no un detalle: sin el, la idempotencia se
        romperia sola, y quien lo omite tiene que saber que hay que pasarlo.
        """
        with pytest.raises(ValidationError, match="NO lee el reloj"):
            self._cap().invoke(self._peticion_sin({"ventana": {"desde": "2026-10-07T00:00:00Z"}}))


class TestLaVentanaAguantaElIdaYVuelta:
    def test_la_ventana_se_relee_de_disco(self, tmp_path: Path) -> None:
        """El guarda mira lo que sale de la BASE, no el objeto.

        Un dataclass puede tener el campo y no persistirlo, y el test
        seguiría verde mirándolo en memoria: es el mismo error que el de
        WI-113, donde `frozen=True` congelaba el enlace y no el valor.
        """
        s = _storage(tmp_path)
        try:
            s.register_source(
                tenant_id="t",
                project_id="p",
                source=_source(
                    observed_from="2026-10-07T00:00:00Z", observed_to="2026-10-07T12:00:00Z"
                ),
            )
            leido = s.get_source(tenant_id="t", project_id="p", source_id=source_id("runtime:v1"))
            assert leido is not None
            assert leido.observed_from == "2026-10-07T00:00:00Z"
            assert leido.observed_to == "2026-10-07T12:00:00Z"
            assert leido.kind == KIND_RUNTIME
        finally:
            s.close()


class TestUnaVentanaSinHastaEstaAbierta:
    def test_ventana_sin_hasta_dice_abierta(self) -> None:
        assert Ventana(desde="2026-10-07T00:00:00Z").abierta is True

    def test_ventana_cerrada_no_dice_abierta(self) -> None:
        v = Ventana(desde="2026-10-07T00:00:00Z", hasta="2026-10-07T12:00:00Z")
        assert v.abierta is False

    def test_el_source_persistido_conserva_el_hasta_a_none(self, tmp_path: Path) -> None:
        """`observed_to=None` se guarda como NULL, y se relee como None.

        Y **no** como cadena vacia: un `''` y un `None` son la misma
        falsehood en SQL, y leerlos igual es como se pierde la diferencia
        entre «sigue abierta» y «no dice nada».
        """
        s = _storage(tmp_path)
        try:
            s.register_source(
                tenant_id="t", project_id="p", source=_source(observed_from="2026-10-07T00:00:00Z")
            )
            leido = s.get_source(tenant_id="t", project_id="p", source_id=source_id("runtime:v1"))
            assert leido is not None
            assert leido.observed_to is None
            assert leido.observed_from == "2026-10-07T00:00:00Z"
        finally:
            s.close()

    def test_ventana_sin_desde_se_rechaza(self) -> None:
        """Una ventana sin principio no es una ventana.

        Y el mensaje dice WHY: porque aquí la tentación de mandar `desde=0`
        o `desde=""` es real, y ambas producen una consulta que parece
        funcionar y devuelve la historia entera sin que nadie lo pidiera.
        """
        with pytest.raises(ValidationError, match="sin principio"):
            Ventana(desde="")


# ---------------------------------------------------------------------------
# P5 y P6 — las dos invariantes de la ventana
# ---------------------------------------------------------------------------


class TestNoSeCierraUnPeriodoQueNoEmpezo:
    def test_observed_to_sin_observed_from_se_rechaza(self) -> None:
        """Imposible, no incompleto.

        La diferencia importa porque «incompleto» y «imposible» piden
        arreglos distintos —rellenar el hueco contra lo que hay, frente a
        quitar el final— y un solo `if` los trataría igual.
        """
        with pytest.raises(InvalidSourceError, match="no empezo"):
            _source(observed_to="2026-10-07T12:00:00Z")

    def test_el_envelope_lo_rechaza_tambien(self) -> None:
        """Se rechaza en la frontera Y en el ADT.

        En el envelope para que un adaptador no pueda registrar un
        envelope imposible; en `Source` para que nadie lo construya a mano.
        """
        with pytest.raises(EnvelopeInvalido, match="no empezo"):
            ObservationEnvelope(
                producer=CapabilitySpec(type_name=TELEMETRY_QUERY, summary="s"),
                adapter="x",
                source_id=source_id("runtime:v3"),
                subject=SUJETO,
                observed_at="2026-10-07T12:00:00Z",
                revision="r1",
                observations=(_observacion(),),
                observed_to="2026-10-07T12:00:00Z",
            )


class TestUnaVentanaSobreUnCommitEsCategoriaEquivocada:
    """Un periodo describe algo que OCURRIO, y lo único que ocurre es lo que
    se vio funcionando. Ponerlo sobre un `git_commit` dice «el commit existió
    entre estas dos fechas», que no es una afirmación sobre el commit: es una
    afirmación sobre una duración, y un instante no tiene duración."""

    def test_se_rechaza_sobre_un_commit(self) -> None:
        with pytest.raises(InvalidSourceError, match="runtime_observation"):
            _source(
                kind="git_commit",
                git_commit_sha="a" * 40,
                observed_from="2026-10-07T00:00:00Z",
                observed_to="2026-10-07T12:00:00Z",
            )

    def test_se_rechaza_sobre_un_documento(self) -> None:
        with pytest.raises(InvalidSourceError, match="runtime_observation"):
            _source(
                kind="external_doc",
                observed_from="2026-10-07T00:00:00Z",
            )

    def test_un_runtime_sin_ventana_si_se_puede(self) -> None:
        """La regla es de UNA DIRECCION y por eso se mide.

        `runtime_observation` sin ventana es una observación puntual, que es
        una cosa real: se miró un instante y eso es todo lo que se sabe. Si
        la regla fuera «ventana o nada», ese caso —legítimo— no tendria
        donde vivir y acabaria en `external_doc`, que es peor.
        """
        assert _source().observed_from is None


# ---------------------------------------------------------------------------
# P7 — la base VIEJA. La property que casi se lleva el bloque
# ---------------------------------------------------------------------------

#: El DDL de `sources` TAL COMO ESTABA antes de B33. Se aplica SOBRE el DDL
#: real, quitando las dos columnas, y no se escribe entero a mano.
#:
#: **POR QUE NO UN DDL COMPLETO ESCRITO A MANO.** Una base vieja fabricada
#: con solo las tablas que un test necesita rompe `sincroniza` con `no such
#: table: claims` —que es como lo midio B25—, y escribir aqui el esquema
#: entero lo convertiria en una SEGUNDA COPIA del esquema que hay que
#: actualizar cada vez que el esquema cambia. Se deriva del real, luego no
#: hay nada que mantener sincronizado.
#:
#: Y se aplica por AST-lite —un regex sobre el bloque `CREATE TABLE`— y no
#: por `str.replace` de un fragmento escrito a mano: el primer intento uso
#: una constante que copiaba el DDL, y dejo un `);` colgando al quitar el
#: `CREATE TABLE` sin su cierre. Un `replace` que no encuentra el texto se
#: lleva por delante medio esquema y no dice nada.
DDL_SOURCES_SIN_VENTANA = re.compile(r"CREATE TABLE IF NOT EXISTS sources \(.*?\n\);", re.DOTALL)


def _base_vieja(tmp_path: Path, nombre: str = "vieja.sqlite") -> Path:
    """Una base con el esquema COMPLETO de su epoca, sin las columnas de B33."""
    from skillgraph.platform import schema as schema_mod

    ruta = tmp_path / nombre
    ddl_viejo, cuantos = DDL_SOURCES_SIN_VENTANA.subn(_DDL_SOURCES_ANTIGUO, schema_mod.SCHEMA_SQL)
    assert cuantos == 1, (
        f"el DDL de `sources` no aparece una vez en el esquema, aparece {cuantos}. "
        "Si el esquema cambio de forma, esta base ya no es una base VIEJA: es una "
        "base con el esquema de hoy y el test no mediria nada"
    )
    conn = sqlite3.connect(ruta)
    conn.executescript(ddl_viejo)
    conn.commit()
    conn.close()
    return ruta


#: El DDL de `sources` antes de B33: las mismas once columnas, sin ventana.
_DDL_SOURCES_ANTIGUO = """CREATE TABLE IF NOT EXISTS sources (
    source_id        TEXT PRIMARY KEY,
    tenant_id        TEXT NOT NULL,
    project_id       TEXT NOT NULL,
    kind             TEXT NOT NULL,
    content_hash     TEXT NOT NULL,
    locator_json     TEXT NOT NULL,
    git_commit_sha   TEXT,
    git_tree_sha     TEXT,
    working_tree_status_json TEXT,
    checked_at       TEXT NOT NULL,
    freshness        TEXT NOT NULL DEFAULT 'fresh'
);"""


class TestUnaBaseViejaRecibeLaVentana:
    def test_una_base_vieja_se_abre_y_tiene_las_columnas(self, tmp_path: Path) -> None:
        ruta = _base_vieja(tmp_path)
        s = Storage(ruta)
        try:
            columnas = {f[1] for f in s._conn.execute("PRAGMA table_info(sources)").fetchall()}
            assert {"observed_from", "observed_to"} <= columnas, (
                f"la migracion 0007 no llego a una base vieja: {sorted(columnas)}"
            )
        finally:
            s.close()

    def test_una_base_vieja_acepta_una_fuente_con_ventana(self, tmp_path: Path) -> None:
        """La property de verdad: no solo que se abra, sino que **escriba**.

        Una migracion que añade las columnas pero rompe el INSERT pasa
        `test_una_base_vieja_se_abre_y_tiene_las_columnas` en verde, y por
        eso esta segunda existe.
        """
        s = Storage(_base_vieja(tmp_path))
        try:
            s.register_source(
                tenant_id="t",
                project_id="p",
                source=_source(
                    observed_from="2026-10-07T00:00:00Z", observed_to="2026-10-07T12:00:00Z"
                ),
            )
            leido = s.get_source(tenant_id="t", project_id="p", source_id=source_id("runtime:v1"))
            assert leido is not None and leido.observed_from == "2026-10-07T00:00:00Z"
        finally:
            s.close()

    def test_una_base_vieja_conserva_las_filas_que_ya_tenia(self, tmp_path: Path) -> None:
        """`ADD COLUMN` no debe perder nada.

        Es la razon por la que `0007` usa `ALTER TABLE ADD COLUMN` y no la
        reconstruccion que uso `0005`: aqui las columnas son nuevas y no
        participan de ninguna constraint, luego `ADD COLUMN` alcanza.
        """
        ruta = _base_vieja(tmp_path)
        previo = sqlite3.connect(ruta)
        previo.execute(
            "INSERT INTO sources (source_id, tenant_id, project_id, kind, content_hash,"
            " locator_json, git_commit_sha, git_tree_sha, working_tree_status_json,"
            " checked_at, freshness) VALUES ('x','t','p','external_doc','h','{}',NULL,NULL,"
            "NULL,'2026-01-01T00:00:00Z','fresh')"
        )
        previo.commit()
        previo.close()

        s = Storage(ruta)
        try:
            fila = s._conn.execute(
                "SELECT observed_from, observed_to FROM sources WHERE source_id = 'x'"
            ).fetchone()
            # `sqlite3.Row` no compara igual que una tupla, y comparar el
            # objeto entero daría verde aunque las columnas vinieran con
            # cualquier cosa: hay que mirar los VALORES.
            assert tuple(fila) == (None, None), (
                f"una fuente vieja deberia leer las dos columnas a NULL, y lee {tuple(fila)}"
            )
        finally:
            s.close()


# ---------------------------------------------------------------------------
# P8, P9, P10 — la vertical
# ---------------------------------------------------------------------------


class TestLaVerticalEntera:
    def test_el_doble_cumple_el_puerto(self) -> None:
        """El `Protocol` se comprueba con `isinstance`, no se declara:
        un `Protocol` sin `runtime_checkable` no se puede comprobar en
        runtime y el guard tendria que leer el codigo, que es medir la
        convencion y no la propiedad."""
        assert isinstance(DobleDePrueba(), LectorTelemetria)

    def test_la_capability_produce_un_envelope_de_runtime_con_ventana(self) -> None:
        ventana = Ventana(desde="2026-10-07T00:00:00Z", hasta="2026-10-07T12:00:00Z")
        lector = _Lector_que_devuelve((_observacion(),))
        cap = TelemetryQueryCapability(lector, source_id="runtime:v1", revision="r1")

        resultado = cap.invoke(_peticion(ventana))

        env = resultado.payload["envelope"]
        assert env["kind"] == KIND_RUNTIME
        assert env["observed_from"] == "2026-10-07T00:00:00Z"
        assert env["observed_to"] == "2026-10-07T12:00:00Z"
        assert env["subject"] == SUJETO
        assert env["adapter"] == "TelemetryQueryCapability"

    def test_la_ventana_llega_al_lector(self) -> None:
        """La ventana no se come la capability: se la pasa a quien sabe.

        Si la tradujera por su cuenta, habria dos definiciones de `[desde,
        hasta)` y la que ganase dependeria de quien preguntase.
        """
        ventana = Ventana(desde="2026-10-07T00:00:00Z", hasta="2026-10-07T12:00:00Z")
        lector = _Lector_que_devuelve((_observacion(),))
        TelemetryQueryCapability(lector, source_id="runtime:v1", revision="r1").invoke(
            _peticion(ventana)
        )
        assert lector.visto is not None
        assert lector.visto.desde == ventana.desde
        assert lector.visto.hasta == ventana.hasta

    def test_una_ventana_vacia_falla_diciendo_que_no_hubo_observaciones(self) -> None:
        """El mensaje dice «no hubo nada», no «el envelope se rompió».

        Quien lo lee necesita distinguir las dos: una es «pregunta mal
        hecha» y la otra es «el instrumento fallo», y se arreglan distinto.
        """
        cap = TelemetryQueryCapability(
            _Lector_que_devuelve(()), source_id="runtime:v1", revision="r1"
        )
        with pytest.raises(ValidationError, match=r"ninguna\s+observacion"):
            cap.invoke(_peticion(Ventana(desde="2026-10-07T00:00:00Z")))

    def test_la_vertical_llega_hasta_la_base(self, tmp_path: Path) -> None:
        """La property de punta a punta, y la que NO mide el resolver.

        Ejecuta el camino entero —capability, envelope, `normalizar`,
        `ingerir`— y lee de DISCO. Un test que se parase en el envelope
        mediría que el envelope tiene el campo, no que el campo llega.
        """
        ventana = Ventana(desde="2026-10-07T00:00:00Z", hasta="2026-10-07T12:00:00Z")
        cap = TelemetryQueryCapability(
            _Lector_que_devuelve((_observacion("sqlite3"),)),
            source_id="runtime:v1",
            revision="r1",
        )
        payload = cap.invoke(_peticion(ventana)).payload["envelope"]

        s = _storage(tmp_path)
        try:
            env = _envelope_de(payload)
            ingesta = ingerir(s, tenant_id="t", project_id="p", env=env)
            leido = s.get_source(tenant_id="t", project_id="p", source_id=source_id("runtime:v1"))
            assert leido is not None
            assert leido.kind == KIND_RUNTIME
            assert (leido.observed_from, leido.observed_to) == (
                "2026-10-07T00:00:00Z",
                "2026-10-07T12:00:00Z",
            )
            assert ingesta.claims[0].assertion_origin == "observed"
        finally:
            s.close()


class TestLaCapabilityNoLeeElReloj:
    """AGENTS 1.3: las funciones puras no leen el reloj. Y aqui no es theory.

    El envelope que sale es una FRONTERA (B26). Si la capability leyera el
    reloj, dos invocaciones seguidas de la misma ventana darían dos
    envelopes distintos, y el `claim_id` —que sale del contenido— cambiaría
    con ellos: la idempotencia se rompería sola, sin que nada lo indicara.
    """

    def test_dos_invocaciones_dan_el_mismo_envelope(self) -> None:
        ventana = Ventana(desde="2026-10-07T00:00:00Z", hasta="2026-10-07T12:00:00Z")
        cap = TelemetryQueryCapability(
            _Lector_que_devuelve((_observacion(),)), source_id="runtime:v1", revision="r1"
        )
        peticion = _peticion(ventana)
        primero = cap.invoke(peticion).payload["envelope"]
        segundo = cap.invoke(peticion).payload["envelope"]
        assert primero == segundo, (
            "la capability lee el reloj: dos preguntas por la misma ventana "
            "produjeron envelopes distintos, y el claim_id deriva del contenido"
        )

    def test_el_instante_lo_declara_quien_pregunta(self) -> None:
        """Si lo dedujera, con una ventana ABIERTA no tendria de donde.

        «Hasta ahora» es un instante que la capability no puede saber sin
        leer el reloj, luego tiene que entrar por `arguments`. Y el error
        lo dice, porque si no el que pregunta no sabria que hay que
        pasarlo.
        """
        cap = TelemetryQueryCapability(
            _Lector_que_devuelve((_observacion(),)), source_id="runtime:v1", revision="r1"
        )
        peticion = CapabilityRequest(
            spec=CapabilitySpec(type_name=TELEMETRY_QUERY, summary="t"),
            subject=SUJETO,
            arguments={"ventana": {"desde": "2026-10-07T00:00:00Z"}},
        )
        with pytest.raises(ValidationError, match="observed_at"):
            cap.invoke(peticion)


class TestLaCapabilityNoEscribe:
    """No escribe en el store, y el motivo es `ADR-0027`: un adaptador que
    escribe deja de ser un adaptador y se convierte en la razón por la que
    hay que confiar en él."""

    def test_invoke_no_toca_la_base(self, tmp_path: Path) -> None:
        s = _storage(tmp_path)
        try:
            cap = TelemetryQueryCapability(
                _Lector_que_devuelve((_observacion(),)),
                source_id="runtime:v1",
                revision="r1",
            )
            antes = s._conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
            cap.invoke(_peticion(Ventana(desde="2026-10-07T00:00:00Z")))
            despues = s._conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
            assert antes == despues == 0, (
                f"la capability escribio en la base: {antes} -> {despues} fuentes"
            )
        finally:
            s.close()


# ---------------------------------------------------------------------------
# P11 — los dos relojes siguen siendo dos relojes
# ---------------------------------------------------------------------------


class TestLosDosRelojesSiguenSiendoDistintos:
    """La ventana de runtime (un PERIODO) y la ventana de vigencia (una
    REVISION) no se mezclan.

    Es la misma frontera que B32 dibujo entre `revision_registro.seq` y
    `GitHistory`, y por el mismo motivo: un solo reloj contestando dos
    preguntas contesta bien una y mal la otra. Una afirmacion de runtime
    sigueicky teniendo `checked_at_revision`, y eso no la convierte en una
    afirmacion de B29.
    """

    def test_una_fuente_de_runtime_no_trae_ventanas_de_vigencia(self) -> None:
        campos = set(Source.__dataclass_fields__)
        assert "valid_from_revision" not in campos, (
            "Source ha crecido con la ventana de vigencia de B29: son dos relojes "
            "y la vigencia vive en Claim"
        )

    def test_el_claim_de_runtime_no_gana_una_ventana_de_vigencia(self) -> None:
        env = ObservationEnvelope(
            producer=CapabilitySpec(type_name=TELEMETRY_QUERY, summary="s"),
            adapter="chronos",
            source_id=source_id("runtime:v1"),
            subject=SUJETO,
            observed_at="2026-10-07T12:00:00Z",
            revision="r1",
            observations=(_observacion(),),
            kind=KIND_RUNTIME,
            observed_from="2026-10-07T00:00:00Z",
            observed_to="2026-10-07T12:00:00Z",
        )
        claim = normalizar(env).claims[0]
        assert claim.checked_at_revision == "r1"
        assert claim.valid_from_revision is None
        assert claim.valid_until_revision is None


# ---------------------------------------------------------------------------
# P12 — la consulta por ventana tiene indice
# ---------------------------------------------------------------------------


class TestLaVentanaSeConsultaConIndice:
    def test_el_indice_existe_en_una_base_migrada(self, tmp_path: Path) -> None:
        s = _storage(tmp_path)
        try:
            indices = {f[1] for f in s._conn.execute("PRAGMA index_list(sources)").fetchall()}
            assert "idx_sources_ventana" in indices, (
                f"la consulta por ventana no tiene indice: {sorted(indices)}"
            )
        finally:
            s.close()

    def test_el_indice_es_parcial(self, tmp_path: Path) -> None:
        """Y es PARCIAL por el mismo motivo que el de B32.

        `observed_from` es NULL en toda fuente que no es de runtime —los
        ADR, los commits, los archivos—, y esas se consultan por otras
        columnas. Un indice completo guardaría muchos NULL que no se
        buscan nunca: más grande para no guardarlos de más.
        """
        s = _storage(tmp_path)
        try:
            sql = s._conn.execute(
                "SELECT sql FROM sqlite_master WHERE name = 'idx_sources_ventana'"
            ).fetchone()[0]
            assert "observed_from IS NOT NULL" in sql, (
                f"el indice no es parcial y va a guardar los NULL de las fuentes "
                f"que no son de runtime: {sql}"
            )
        finally:
            s.close()


# ---------------------------------------------------------------------------
# El contrasalto del bloque: el gate del roadmap YA LO CUMPLIA B28
# ---------------------------------------------------------------------------


class TestElGateDelRoadmapYaLoCumpliaB28:
    """**POR QUE ESTA CLASE Y POR QUE ES LA MAS IMPORTANTE DEL FICHERO.**

    El gate que B33 escribe el roadmap es «un claim runtime que contradice
    un ADR abre conflicto; `actual_behavior` prefiere runtime e
    `intended_architecture` prefiere la decisión aceptada». Este test lo
    monta **sin una sola línea de B33**: dos `Source` de B26, dos `Claim`,
    y el resolver de B28. Pasa.

    Es decir: el gate del roadmap **no mide el bloque**. Mide el resolver,
    que B28 ya certified. Si alguien cierra B33 con ese gate —lo que sería
    lo natural, porque es el gate que está escrito— lo cerrará sin haber
    escrito nada, y el fallo no se verá en ninguna cifra.

    Lo que este test ata es que la afirmación siga siendo CIERTA, y que
    quien lo lea sepa que por eso el bloque necesita OTRO gate: el que
    mide la vertical (`TestLaVerticalEntera`), no el que mide el resolver.
    """

    def test_el_conflicto_se_abre_sin_una_linea_de_b33(self, tmp_path: Path) -> None:
        from skillgraph.knowledge.authority import resolver

        s = _storage(tmp_path)
        try:
            s.upsert_entity(
                tenant_id="t",
                project_id="p",
                entity=Entity(entity_id=SUJETO, kind="observed", stable_key=SUJETO),
            )
            # LAS DOS SON `external_doc`: es lo que se podia hacer sin B33.
            for sid, locator in (
                (ADY, {"producer": "adr.reader"}),
                ("runtime:ventana-1", {"producer": "telemetry.query"}),
            ):
                s.register_source(
                    tenant_id="t",
                    project_id="p",
                    source=Source(
                        source_id=source_id(sid),
                        kind="external_doc",
                        content_hash=f"h-{sid}",
                        locator=locator,
                        git_commit_sha=None,
                        git_tree_sha=None,
                        working_tree_status=None,
                        checked_at="2026-10-07T00:00:00Z",
                        freshness="current",
                    ),
                )
            for cid, valor, origen, sid in (
                ("c-runtime", "sqlite3", "observed", "runtime:ventana-1"),
                ("c-adr", "psycopg", "human-asserted", ADY),
            ):
                s.record_claim(
                    tenant_id="t",
                    project_id="p",
                    claim=Claim(
                        claim_id=cid,
                        subject_entity_id=SUJETO,
                        predicate="imports_module",
                        object_literal=valor,
                        source_id=source_id(sid),
                        assertion_origin=origen,
                        checked_at_revision="r1",
                    ),
                )

            conflictos = s.conflicts_for(tenant_id="t", project_id="p", subject_entity_id=SUJETO)
            assert len(conflictos) == 1, "el conflicto del gate deberia abrirse"
            actual = resolver(conflictos[0], intencion="actual_behavior")
            intencion = resolver(conflictos[0], intencion="intended_behavior")
            assert actual.ganadora is not None and actual.ganadora.claim_id == "c-runtime"
            assert intencion.ganadora is not None and intencion.ganadora.claim_id == "c-adr"
        finally:
            s.close()

    def test_y_aun_así_no_se_puede_cerrar_b33_con_eso(self, tmp_path: Path) -> None:
        """El mismo store, y la COMPARACION que el gate del roadmap no hace.

        Las dos fuentes siguen siendo `external_doc` —porque este test no
        usa B33—, y por eso la ventana que_runtime_ observó no se puede
        preguntar por ninguna columna. El gate dice «prefiere runtime»;
        esto dice **cómo se sabe cuál era**.

        Es la razón por la que el gate de B33 hay que sustituirlo y no basta
        con ejecutarlo.
        """
        s = _storage(tmp_path)
        try:
            s.register_source(
                tenant_id="t",
                project_id="p",
                source=Source(
                    source_id=source_id("runtime:ventana-1"),
                    kind="external_doc",
                    content_hash="h",
                    locator={"producer": "telemetry.query"},
                    git_commit_sha=None,
                    git_tree_sha=None,
                    working_tree_status=None,
                    checked_at="2026-10-07T00:00:00Z",
                    freshness="current",
                ),
            )
            columnas = {f[1] for f in s._conn.execute("PRAGMA table_info(sources)").fetchall()}
            assert "observed_from" in columnas, (
                "la columna no existe: esta prueba corre en un arbol SIN B33"
            )
        finally:
            s.close()


# ---------------------------------------------------------------------------
# Los guardas de estructura: el bloque no puede crecer a lo oculto
# ---------------------------------------------------------------------------


class TestLaCapacidadNoImportaAdaptadores:
    """`TestElNucleoNoImportaAdapters` de B30 vigila el nucleo. Esta vigila
    al bloque: la capability declara un **puerto** y no una herramienta.

    Se mide por AST y no por `import` en el modulo porque la propiedad es
    «este fichero NO nombra Chronos ni OTel», y una mencion en un docstring
    es indistinguible de un import si se busca con cadena.
    """

    def test_no_importa_ninguna_herramienta_externa(self) -> None:
        from skillgraph.knowledge import telemetry_query as mod

        arbol = ast.parse(Path(inspect.getfile(mod)).read_text())
        externos = ("chronos", "opentelemetry", "otel", "requests", "httpx", "urllib")
        culpables: list[str] = []
        for nodo in ast.walk(arbol):
            nombres: list[str] = []
            if isinstance(nodo, ast.Import):
                nombres = [a.name for a in nodo.names]
            elif isinstance(nodo, ast.ImportFrom) and nodo.module:
                nombres = [nodo.module]
            for nombre in nombres:
                if any(e in nombre.lower() for e in externos):
                    culpables.append(f"linea {nodo.lineno}: {nombre}")
        assert not culpables, (
            f"la capability importa herramientas externas: {culpables}. El adaptador "
            "que sabe es el despliegue, y lo recibe por el Protocol"
        )

    def test_el_lector_es_un_protocol(self) -> None:
        """Y no una clase con metodos.

        Una clase concreta seria el camino corto a que un adapter se
        confunda con un puerto, que es lo que dice el docstring de
        `KnowledgeQueryCapability` y lo que `ADR-0027` rechaza.
        """
        assert hasattr(LectorTelemetria, "_is_protocol")
        assert LectorTelemetria._is_protocol is True


# ---------------------------------------------------------------------------
# Ayudares que los tests de arriba usan y que conviene tener al final
# ---------------------------------------------------------------------------


class _Lector_que_devuelve:
    """El doble mas simple posible: devuelve lo que le construyeron.

    Se declara aqui y no arriba porque los tests que lo usan se leen mejor
    cuando esta cerca, y un `__all__` de helpers al principio del fichero
    hace que se lea como parte de la superficie publica cuando no lo es.
    """

    def __init__(self, observaciones: tuple[Observation, ...]) -> None:
        self._observaciones = observaciones
        self.visto: Ventana | None = None

    def observaciones(self, *, sujeto: str, ventana: Ventana) -> tuple[Observation, ...]:
        self.visto = ventana
        return self._observaciones


def _envelope_de(payload: dict[str, object]) -> ObservationEnvelope:
    """El `dict` del payload -> el envelope, para poder ingerirlo.

    Se reconstruye con el **constructor** y no con `ObservationEnvelope(**payload)`
    a pelo, porque el payload trae el `producer` como dict y el dataclass
    quiere un `CapabilitySpec`. Es el desajuste que produce serializar y
    deserializar un contrato con dos tipos, y por eso la asercion de que la
    ida y la vuelta coinciden vive en `test_ida_y_vuelta_del_payload`.
    """
    productor = payload["producer"]
    assert isinstance(productor, dict)
    observaciones = payload["observations"]
    assert isinstance(observaciones, (list, tuple)), (
        f"el payload deberia traer las observaciones como coleccion, y trae "
        f"{type(observaciones).__name__}"
    )
    return ObservationEnvelope(
        producer=CapabilitySpec(
            type_name=str(productor["type_name"]), summary=str(productor["summary"])
        ),
        adapter=str(payload["adapter"]),
        source_id=source_id(str(payload["source_id"])),
        subject=str(payload["subject"]),
        observed_at=str(payload["observed_at"]),
        revision=str(payload["revision"]),
        observations=tuple(
            Observation(
                predicate=str(o["predicate"]),
                object_literal=o["object_literal"],
            )
            for o in observaciones
            if isinstance(o, dict)
        ),
        kind=payload["kind"],  # type: ignore[arg-type]
        observed_from=payload["observed_from"],  # type: ignore[arg-type]
        observed_to=payload["observed_to"],  # type: ignore[arg-type]
    )


class TestLaIdaYVueltaDelPayload:
    """El payload y el envelope dicen lo mismo.

    `envelope_a_payload` usa `asdict` precisamente para esto, y la razon
    de que sea un test y no una costumbre: un campo anadido al envelope y
    olvidado en la serializacion es un dato que sale del sistema sin que
    nadie lo note, y no hay ningun otro sitio donde se note.
    """

    def test_ida_y_vuelta(self) -> None:
        ventana = Ventana(desde="2026-10-07T00:00:00Z", hasta="2026-10-07T12:00:00Z")
        cap = TelemetryQueryCapability(
            _Lector_que_devuelve((_observacion("sqlite3"),)),
            source_id="runtime:v1",
            revision="r1",
        )
        payload = cap.invoke(_peticion(ventana)).payload["envelope"]
        assert isinstance(payload, dict)
        env = _envelope_de(payload)

        assert env.kind == KIND_RUNTIME
        assert env.observed_from == ventana.desde
        assert env.observed_to == ventana.hasta
        assert env.source_id == source_id("runtime:v1")
        assert env.observations[0].object_literal == "sqlite3"

    def test_el_payload_no_omite_la_ventana(self) -> None:
        """Contraejemplo al de arriba, y el que de verdad distingue.

        Comparar el envelope entero daría verde aunque la ventana se
        perdiera, porque el resto de los campos volvería igual. Lo que
        separa los dos casos es la clave concreta.
        """
        ventana = Ventana(desde="2026-10-07T00:00:00Z")
        cap = TelemetryQueryCapability(
            _Lector_que_devuelve((_observacion(),)), source_id="runtime:v1", revision="r1"
        )
        payload = cap.invoke(_peticion(ventana)).payload["envelope"]
        assert isinstance(payload, dict)
        assert "observed_from" in payload, (
            "el payload pierde observed_from: la ventana se queda en la base de datos "
            "y desaparece del lado de quien la pidió"
        )
        assert payload["observed_from"] == "2026-10-07T00:00:00Z"
