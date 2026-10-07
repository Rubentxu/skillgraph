"""B26 — una herramienta externa aporta conocimiento sin escribir en el store.

**EL PRIMER TEST DE ESTE FICHERO ES EL QUE ENCONTRÓ EL BLOQUE.** No esta aqui
por cobertura: la promocion serializa y deserializa a mano, y cuando B25
metio una segunda forma de objeto en `Claim`, ese camino dejo de funcionar sin
que ningun test lo dijera.

MEDIDO antes de escribir nada, sobre una base real:

    payload del claim: {'claim_id': 'c1', ..., 'object_literal': None, ...}
    ¿arrastra object_entity? False
    reconstruido: InvalidClaimObjectError

Es decir: un claim cuyo objeto es una entidad no se puede promover, y el
fallo sale en el proyecto DESTINO, que es el que nadie mira.

Cada test nombra la propiedad que mide y **qué pasaria si fuera falsa**.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from skillgraph.core.errors import SkillGraphError
from skillgraph.knowledge.graph import Claim, Entity, Source, entity_ref, source_id
from skillgraph.knowledge.observation import (
    VERSION_ENVELOPE,
    EnvelopeInvalido,
    Observation,
    ObservationEnvelope,
    ObservationIngesta,
    normalizar,
)

# R1.C: `ingerir` es el EFECTO (escribe en un Storage), no el modelo. Vive
# fuera del modulo puro a proposito, y el contrato es el mismo.
from skillgraph.knowledge.observation_ingestion import (
    ingerir,
)
from skillgraph.platform.ports.capabilities import CapabilitySpec
from skillgraph.platform.storage import Storage

ORIGEN = "file:src/foo.py"
DESTINO = "file:src/bar.py"
REVISION = "rev-1"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _storage(tmp_path: Path, nombre: str = "b26.sqlite") -> Storage:
    return Storage(tmp_path / nombre)


def _preparar(s: Storage, proyecto: str = "p") -> None:
    s.upsert_entity(
        tenant_id="t",
        project_id=proyecto,
        entity=Entity(entity_id=ORIGEN, kind="file", stable_key="src/foo.py"),
    )
    s.upsert_entity(
        tenant_id="t",
        project_id=proyecto,
        entity=Entity(entity_id=DESTINO, kind="file", stable_key="src/bar.py"),
    )
    s.register_source(
        tenant_id="t",
        project_id=proyecto,
        source=Source(
            source_id="local:src/foo.py",
            kind="local_file",
            content_hash="h",
            locator={"path": "src/foo.py"},
            git_commit_sha=None,
            git_tree_sha=None,
            working_tree_status=None,
            checked_at="2026-10-06T00:00:00Z",
            freshness="current",
        ),
    )


def _envelope(*, con_entidad: bool = False) -> ObservationEnvelope:
    observacion = (
        Observation(predicate="imports_module", object_entity=entity_ref(DESTINO))
        if con_entidad
        else Observation(predicate="line_count", object_literal=137)
    )
    return ObservationEnvelope(
        producer=CapabilitySpec(type_name="cognicode.code", version="1.0"),
        adapter="cognicode",
        source_id=source_id("local:src/foo.py"),
        subject=ORIGEN,
        observed_at="2026-10-06T10:00:00Z",
        revision=REVISION,
        observations=(observacion,),
    )


# ---------------------------------------------------------------------------
# R1 — una forma declarada, no un dict
# ---------------------------------------------------------------------------


class TestLaFormaEsDeclarada:
    def test_existe_y_dice_su_version(self) -> None:
        """El envelope se nombra y se versiona.

        Sin version no se puede rechazar lo viejo, y el fallo aparece en el
        dato en vez de en la frontera.
        """
        assert VERSION_ENVELOPE == "sg.observation/1"
        assert _envelope().version == VERSION_ENVELOPE

    def test_una_observacion_admite_las_dos_formas_de_objeto(self) -> None:
        """R1 con R5 dentro: literal **o** entidad.

        Si solo admitiera una, la segunda seria un caso especial y habria que
        volver a la pregunta de B25.
        """
        con_texto = Observation(predicate="line_count", object_literal=137)
        con_entidad = Observation(predicate="imports_module", object_entity=entity_ref(DESTINO))

        assert con_texto.object_literal == 137 and con_texto.object_entity is None
        assert con_entidad.object_literal is None and con_entidad.object_entity is not None

    def test_una_observacion_no_puede_no_decir_nada(self) -> None:
        """El contrasalto: sin objeto, una observacion no observa nada.

        Si esto pasara, se podria construir un envelope que dice mucho y no
        afirma nada, y la ingesta lo escribiria sin quejarse.
        """
        with pytest.raises(EnvelopeInvalido):
            Observation(predicate="line_count")

    def test_el_envelope_es_inmutable(self) -> None:
        """El envelope cruza una frontera: no puede cambiarse de camino.

        Se mide con `dataclasses.FrozenInstanceError` y no con `Exception`: un
        `Exception` cualquiera pasaria tambien si lo que revienta fuese otra
        cosa, y el nombre del error es justo lo que dice que la causa es la
        inmutabilidad y no un fallo de ventana.
        """
        import dataclasses

        env = _envelope()
        with pytest.raises(dataclasses.FrozenInstanceError):
            env.observed_at = "otro"  # type: ignore[misc]

    def test_el_envelope_no_puede_sin_observaciones(self) -> None:
        """Un envelope vacio se ingiere como no-op y PARECE que funciono.

        Es el contrasalto mas caro de los cuatro: sin esta comprobacion, una
        herramienta que no sabe observar nada devuelve un envelope vacio, la
        ingesta termina sin error, y el llamante cree que registro lo que le
        pidieron. El fallo no esta en ninguna fila: esta en que no hay ninguna,
        y por eso no lo puede delatar un `assert` sobre el numero de filas.

        El mensaje dice que paso, porque «no-op» sin explicar por qué no-op
        deja al llamante sin saber si reintentar o arreglar la herramienta.
        """
        from dataclasses import replace

        with pytest.raises(EnvelopeInvalido) as exc:
            replace(_envelope(), observations=())

        assert "observaciones" in str(exc.value)

    @pytest.mark.parametrize(
        ("campo", "valor", "por_que"),
        [
            ("adapter", "  ", "sin adapter no se sabe quien observo"),
            ("observed_at", "", "sin instante la ingesta tendria que leer el reloj"),
            ("revision", "", "sin revision el claim_id no sale del contenido"),
        ],
    )
    def test_el_envelope_no_puede_traer_un_campo_vacio(
        self, campo: str, valor: str, por_que: str
    ) -> None:
        """Los tres campos que el normalizador necesita y no puede inventar.

        Se parametrizan porque es la MISMA propiedad con tres caras: el
        envelope entra incompleto. Y cada una tiene una consecuencia distinta
        si se acepta —el reloj se cuela, el id deja de ser derivable del
        contenido, o la procedencia se pierde— asi que un parametro con el
        motivo al lado mide mas que tres asserts con el mismo texto.
        """
        from dataclasses import replace

        with pytest.raises(EnvelopeInvalido):
            replace(_envelope(), **{campo: valor})

    def test_el_mensaje_dice_que_campo_falta(self) -> None:
        """«Envelope invalido» sin decir cual de los cinco falla obliga a
        leer el codigo para saber que se rompio.

        Se mide sobre `observed_at` porque es el caso cuyo mensaje explica el
        PORQUE: sin el, alguien podria «arreglarlo» poniendo un reloj dentro
        del normalizador, que es exactamente lo que rompe la idempotencia.
        """
        from dataclasses import replace

        with pytest.raises(EnvelopeInvalido) as exc:
            replace(_envelope(), observed_at="")

        mensaje = str(exc.value)
        assert "observed_at" in mensaje
        assert "reloj" in mensaje, "el mensaje debe advertir del daño, no solo del síntoma"


# ---------------------------------------------------------------------------
# R2 — la ingesta es idempotente
# ---------------------------------------------------------------------------


class TestLaIngestaEsIdempotente:
    def test_ingerir_dos_veces_deja_las_mismas_filas(self, tmp_path: Path) -> None:
        """La propiedad central del bloque, medida contando filas.

        Si la segunda vez duplicara, quien la llama creeria que se registro una
        vez y tendria dos afirmaciones sobre lo mismo.
        """
        s = _storage(tmp_path)
        _preparar(s)

        primera = ingerir(s, tenant_id="t", project_id="p", env=_envelope())
        filas_1 = s._conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0]
        segunda = ingerir(s, tenant_id="t", project_id="p", env=_envelope())
        filas_2 = s._conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0]

        assert filas_1 == filas_2 == 1
        assert primera.claim_ids == segunda.claim_ids

    def test_releer_despues_de_ingerir_dos_veces_da_el_mismo_claim(self, tmp_path: Path) -> None:
        """No basta con que no crezca el numero: el contenido tiene que ser el mismo."""
        s = _storage(tmp_path)
        _preparar(s)
        env = _envelope(con_entidad=True)

        ingerir(s, tenant_id="t", project_id="p", env=env)
        (cid,) = s._conn.execute("SELECT claim_id FROM claims").fetchone()
        primer = s.get_claim(tenant_id="t", project_id="p", claim_id=cid)

        ingerir(s, tenant_id="t", project_id="p", env=env)
        segundo = s.get_claim(tenant_id="t", project_id="p", claim_id=cid)

        assert primer == segundo


# ---------------------------------------------------------------------------
# R3 — el normalizador es puro
# ---------------------------------------------------------------------------


class TestElNormalizadorEsPuro:
    def test_dos_normalizaciones_dan_el_mismo_claim_id(self) -> None:
        """La propiedad que mas daño haria si se rompiera.

        El `claim_id` se deriva del contenido, luego dos llamadas seguidas con
        el mismo envelope tienen que dar el MISMO id. Y lo mas importante:
        esto se mide **sin tocar el reloj**, porque si `normalizar` lo leyera,
        el id cambiaria solo y el test no lo notaria a menos que comparara.
        """
        a = normalizar(_envelope())
        b = normalizar(_envelope())

        assert [c.claim_id for c in a.claims] == [c.claim_id for c in b.claims]

    def test_normalizar_no_necesita_una_base(self) -> None:
        """Se mide con el path de la base apuntando a un sitio que no existe.

        Es la forma de demostrar que no toca disco sin tener que monkeypatchear
        el modulo entero.
        """
        env = _envelope()

        ingesta = normalizar(env)

        assert isinstance(ingesta, ObservationIngesta)
        assert ingesta.claims, "normalizar devolvio una ingesta vacia"

    def test_no_muta_el_envelope(self) -> None:
        """La entrada no se toca. Es una frontera: el que la paso puede
        seguir usándola."""
        env = _envelope()
        instantanea = (env.observed_at, env.revision, len(env.observations))

        normalizar(env)

        assert (env.observed_at, env.revision, len(env.observations)) == instantanea


# ---------------------------------------------------------------------------
# R4 — la versión se rechaza en la frontera
# ---------------------------------------------------------------------------


class TestLaPuertaDeLaVersion:
    def test_una_version_desconocida_sale_como_error_del_dominio(self) -> None:
        """Un envelope de otra epoca falla aqui, no en el dato.

        Si saliera como `KeyError` o `AttributeError`, quien lo produjera
        veria una traza en vez de un mensaje que dice qué versión se esperaba.
        """
        from dataclasses import replace

        env = _envelope()
        futuro = replace(env, version="sg.observation/99")

        with pytest.raises(SkillGraphError) as exc:
            normalizar(futuro)
        assert VERSION_ENVELOPE in str(exc.value)

    def test_una_version_vacia_no_pasa(self) -> None:
        """El contrasalto: si aceptara cualquier cadena, la puerta es decorativa."""
        from dataclasses import replace

        env = replace(_envelope(), version="lo que sea")

        with pytest.raises(SkillGraphError):
            normalizar(env)


# ---------------------------------------------------------------------------
# R5 — el camino que YA existe soporta todas las formas
# ---------------------------------------------------------------------------


class TestElCaminoQueYaExistia:
    def test_el_payload_de_promocion_arrastra_la_entidad(self) -> None:
        """LA PRUEBA QUE ENCONTRO EL BUG. La que dio nombre al bloque.

        `_claim_to_payload` decidía qué campos viajan de un proyecto a otro.
        Cuando B25 añadió la segunda forma de objeto, esa funcion siguio
        copiando solo la primera, y la promoción dejó de funcionar para esos
        claims sin que nada lo dijera.
        """
        from skillgraph.cli.commands.promotion import _claim_to_payload

        claim = Claim(
            claim_id="c-b26",
            subject_entity_id=ORIGEN,
            predicate="imports_module",
            object_literal=None,
            source_id="local:src/foo.py",
            object_entity=entity_ref(DESTINO),
        )
        payload = _claim_to_payload(claim)

        assert payload.get("object_entity_id") == DESTINO, (
            "la referencia a entidad no viaja al proyecto destino"
        )

    def test_promover_un_claim_con_entidad_lo_conserva(self, tmp_path: Path) -> None:
        """Y no basta con que el payload la lleve: tiene que LLEGAR.

        El fallo original salia en el destino, que es el que nadie mira. Esta
        es la prueba que lo habría delatado.
        """
        from skillgraph.cli.commands.promotion import (
            _claim_to_payload,
            _default_claim_importer,
        )

        origen = _storage(tmp_path, "origen.sqlite")
        destino = _storage(tmp_path, "destino.sqlite")
        _preparar(origen, "origen")
        _preparar(destino, "destino")

        claim = Claim(
            claim_id="c-promovido",
            subject_entity_id=ORIGEN,
            predicate="imports_module",
            object_literal=None,
            source_id="local:src/foo.py",
            object_entity=entity_ref(DESTINO),
        )
        origen.record_claim(tenant_id="t", project_id="origen", claim=claim)

        from skillgraph.cli.commands.promotion import _entity_to_payload, _source_to_payload

        aplicar = _default_claim_importer(destino, tenant_id="t", target_project="destino")
        aplicar(
            {
                "source_project": "origen",
                "target_project": "destino",
                "source": _source_to_payload(
                    origen, tenant_id="t", project_id="origen", source_id=claim.source_id
                ),
                "entity": _entity_to_payload(
                    origen,
                    tenant_id="t",
                    project_id="origen",
                    entity_id=claim.subject_entity_id,
                ),
                "claim": _claim_to_payload(claim),
            }
        )

        jj = destino.get_claim(tenant_id="t", project_id="destino", claim_id="c-promovido")
        assert jj is not None
        assert jj.object_entity is not None, "el claim llega al destino sin su referencia a entidad"
        assert jj.object_entity.entity_id == DESTINO


# ---------------------------------------------------------------------------
# Lo que el bloque NO cierra
# ---------------------------------------------------------------------------


class TestLoQueNoSeCierra:
    def test_ingerir_no_borra_lo_que_ya_dijo_una_version_distinta(self, tmp_path: Path) -> None:
        """La idempotencia NO es «dejar una fila».

        Una herramienta que cambia lo que dice, sin cambiar de versión, deja
        **dos** afirmaciones: las dos son válidas y borrar la anterior sería
        destruir historia para parecer consistente. Lo que las resolverá es
        B29 (ventanas de vigencia), no este bloque.
        """
        s = _storage(tmp_path)
        _preparar(s)

        from dataclasses import replace

        ingerir(s, tenant_id="t", project_id="p", env=_envelope())
        otro = replace(_envelope(), revision="rev-2")
        Observations = Observation(predicate="line_count", object_literal=200)
        ingerir(s, tenant_id="t", project_id="p", env=replace(otro, observations=(Observations,)))

        filas = s._conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0]
        assert filas == 2, "la ingesta esta borrando historia en vez de versionar"

    def test_la_herramienta_externa_no_toca_el_store(self, tmp_path: Path) -> None:
        """La propiedad del ENUNCIADO: aportar sin escribir en el store.

        Se mide por lo que el envelope puede hacer: construirlo entero sin
        tener ninguna base a mano.
        """
        with tempfile.TemporaryDirectory() as vacio:
            env = _envelope(con_entidad=True)
            ingesta = normalizar(env)

            assert ingesta.source.source_id == "local:src/foo.py"
            assert ingesta.entity.entity_id == ORIGEN
            assert not list(Path(vacio).iterdir())
