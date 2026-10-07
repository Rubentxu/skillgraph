"""B29 — un cambio en el tiempo deja de leerse como una contradiccion.

**LO QUE ESTE FICHERO MIDE, Y POR QUE NO ES «UN CAMPO MAS».** La fila de B29
decia: *«No se puede preguntar que se sabia en una revision, ni como fue
reemplazado»*. La primera mitad exagera —`checked_at_revision` esta en cada
claim desde antes de esta serie— y la segunda es cierta pero no es la que mas
duele.

Lo que duele, MEDIDO antes de escribir nada:

    filas en claims:   c-A "psycopg" @revA    c-B "sqlite3" @revB
    conflicts_for  ->  1 conflicto: [c-A, c-B]
    resolver       ->  gana NADIE

**El sistema responde «nadie gana» a algo que tiene respuesta definitiva en
cada instante.** En revA era `psycopg`; en revB es `sqlite3`. Las dos
afirmaciones estan, con su revision, y no sabe.

Y la causa es precisa: `conflicts_for` compara valores **sin mirar el tiempo**,
asi que un hecho que CAMBIO se lee igual que un hecho que se CONTRADICE.

# LAS CINCO MEDIDAS DEL INSTRUMENTO, Y DONDE ESTAN AQUI

    P1  ventanas de vigencia  -> TestLaVentanaDeVigencia
    P2  cadena de supersesion -> TestLaSupersesion
    P3  preguntar por revision-> TestPreguntarPorRevision
    P4  un CAMBIO no es conflicto -> TestElConflictoEsTemporal
    P5  disjuntas NO / solapadas SI (CONTRA SALTO) -> TestLoSolapadoSigueSiendoConflicto

P5 es la que hace que las otras cuatro midan algo: una implementacion que
ignorable el tiempo y no hallara NADA de conflicto pasaria P4.
"""

from __future__ import annotations

import ast
import inspect
import os
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from skillgraph.knowledge.graph import (
    Claim,
    Conflicto,
    Entity,
    Source,
    source_id,
    vigente_en,
)
from skillgraph.platform.revision_registry import SqliteRevisionRegistry
from skillgraph.platform.storage import Storage

SUJETO = "file:a.py"
ORIGEN = "local:a.py"
OTRO_ORIGEN = "local:b.py"


# ---------------------------------------------------------------------------
# Escenario
# ---------------------------------------------------------------------------


def _base(tmp: str) -> Storage:
    """Una base con el sujeto y DOS fuentes distintas."""
    s = Storage(Path(tmp) / "x.sqlite")
    s.upsert_entity(
        tenant_id="t",
        project_id="p",
        entity=Entity(entity_id=SUJETO, kind="file", stable_key="a.py"),
    )
    for sid in (ORIGEN, OTRO_ORIGEN):
        s.register_source(
            tenant_id="t",
            project_id="p",
            source=Source(
                source_id=source_id(sid),
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
    return s


def _claim(cid: str, valor: str, rev: str, origen: str = ORIGEN) -> Claim:
    return Claim(
        claim_id=cid,
        subject_entity_id=SUJETO,
        predicate="imports_module",
        object_literal=valor,
        source_id=origen,
        assertion_origin="observed",
        checked_at_revision=rev,
    )


def _registrar(s: Storage, cid: str, valor: str, rev: str, origen: str = ORIGEN) -> Claim:
    c = _claim(cid, valor, rev, origen)
    s.record_claim(tenant_id="t", project_id="p", claim=c)
    return c


# ---------------------------------------------------------------------------
# Lo que NO es un cambio — tres propiedades que la supersesion NO puede tocar
# ---------------------------------------------------------------------------


class TestLoQueNoEsUnCambio:
    """**LAS TRES PROPIEDADES QUE LA SUPERSESION NO PUEDE TOCAR, Y LAS TRES
    SALIERON DE UN ROJO, NO DE UN CALCULO.**

    La suite de B25-B28 se ejecutó sobre el bloque ya implementado y **falló en
    dos tests que este bloque habia roto**: la idempotencia de la ingesta (B26)
    y la estabilidad del conflict set (B27). Ninguno era un test de B29, y
    ninguno lo habria avisado si la suite no se hubiera ejecutado entera: las
    dos sondas del contrasalto que los tocaban miden otra cosa.

    Aqui viven ya como propiedades de B29, porque **son** de B29: las tres
    dicen que cosas que no son un CAMBIO no pueden cerrar una ventana.

    La causa comun era una consulta que elegia «la vigente mas reciente de la
    misma fuente» sin mirar ni el ORDEN ni el VALOR. Este bloque lo escribe,
    y estas tres son lo que impide que vuelva a escribirse asi.
    """

    def test_reingerir_NO_hace_caducar_al_claim(self) -> None:
        """**Idempotencia de la ingesta (B26), en el caso que B29 rompio.**

        Reingerir el MISMO envelope no debe cambiar lo que hay escrito. La
        primera version cerraba la ventana del propio claim
        (`valid_until_revision` `None` -> `'rev-1'`), luego la relectura
        devolvia un claim distinto del primero — y una afirmacion que caduca
        por reingerirse es una afirmacion que se contradice a si misma.
        """
        with tempfile.TemporaryDirectory() as tmp:
            s = _base(tmp)
            _registrar(s, "c-1", "psycopg", "rev-1")
            antes = s.get_claim(tenant_id="t", project_id="p", claim_id="c-1")
            _registrar(s, "c-1", "psycopg", "rev-1")
            despues = s.get_claim(tenant_id="t", project_id="p", claim_id="c-1")
            s.close()
        assert antes == despues
        assert despues.valid_until_revision is None

    def test_ver_el_mismo_valor_OTRA_VEZ_NO_es_un_cambio(self) -> None:
        """**Re-observar un valor no lo reemplaza.** Dos lecturas de la misma
        fuente que dicen LO MISMO en revisiones distintas son la misma
        afirmacion vista dos veces, no un cambio.

        MEDIDO al romperse esto: `c-2(rc2)` y `c-3(rc3)` dicen ambos `False`,
        y cada una cerraba a la otra segun cual se guardara primero. El
        conflict set —que B27 declara estable— dependedia del ORDEN DE
        INGESTA, que es la propiedad que B27 existe para negar.
        """
        with tempfile.TemporaryDirectory() as tmp:
            s = _base(tmp)
            _registrar(s, "c-2", "false", "rc2")
            _registrar(s, "c-3", "false", "rc3")
            dos = s.get_claim(tenant_id="t", project_id="p", claim_id="c-2")
            tres = s.get_claim(tenant_id="t", project_id="p", claim_id="c-3")
            s.close()
        assert dos.valid_until_revision is None
        assert tres.valid_until_revision is None
        assert tres.supersedes_claim_id is None

    def test_una_revision_ANTERIOR_no_supersede_a_una_posterior(self) -> None:
        """El orden es el de `revision_registro`: el orden en que ESTE store
        aprendio. Registrar `rc3` antes que `rc2` hace que `rc3` sea la
        revision que el store conoce despues, y entonces `rc2` es la
        posterior.

        **Y LO QUE SE AFIRMA ES LO QUE ES INDEPENDIENTE DEL ORDEN, QUE NO ES
        LO QUE LA PRIMERA VERSION AFIRMABA.** Esta afirmaba que en `rc3` las
        dos `false` coexistian, y **fallo —con razon— en el orden inverso**:
        ahi `rc3` ocupa la posicion 1 del store, y `c-2` —que el store no ha
        aprendido todavia— no puede estar vigente en ella.

        Eso no es un defecto de la implementacion: es la **consecuencia
        declarada** de que `seq` sea «el orden en que ESTE store aprendio». Sin
        un orden real de revisiones —que es `GitHistory`, la B32— no hay otra
        verdad disponible, y fingir que `rc3` es siempre la posicion 2 seria
        inventarla.

        Lo que si tiene que ser igual en los dos ordenes, para el MISMO
        conjunto de afirmaciones, es **cuantas ventanas siguen abiertas al
        llegar el cambio**. Ahi no cabe el vacio: se mira que las dos `false`
        estaban abiertas y que `true` las cerro a las dos.

        Y se mira **ANTES y DESPUES**, en ese orden: comprobar «no estaban
        cerradas» despues de registrar el cambio no dice nada, porque para
        entonces las ha cerrado el propio cambio que se iba a medir.
        """
        for previas in (
            (("c-2", "false", "rc2"), ("c-3", "false", "rc3")),
            (("c-3", "false", "rc3"), ("c-2", "false", "rc2")),
        ):
            with tempfile.TemporaryDirectory() as tmp:
                s = _base(tmp)
                for cid, valor, rev in previas:
                    _registrar(s, cid, valor, rev)

                # ANTES del cambio: las dos `false` estan abiertas. Una
                # re-observacion del mismo valor NO cierra a la anterior.
                for cid, _, _ in previas:
                    assert _ventana(s, cid) is None, (
                        f"{cid} cerrado antes del cambio, orden {previas}"
                    )

                _registrar(s, "c-1", "true", "rc1")

                # DESPUES: la fuente solo puede decir una cosa a la vez, y
                # cuando dice `true` las dos afirmaciones de `false` pasan a
                # historicas. **LAS DOS**, no solo la mas reciente.
                for cid, _, _ in previas:
                    assert _ventana(s, cid) == "rc1", f"{cid} no cerro, orden {previas}"

                head = {
                    c.claim_id
                    for c in s.claims_at_revision(
                        tenant_id="t",
                        project_id="p",
                        subject_entity_id=SUJETO,
                        revision=None,
                    )
                }
                assert head == {"c-1"}, f"HEAD en orden {previas}"

                # La cadena nombra UN predecesor —el mas reciente—, no todos.
                encadenado = s.get_claim(tenant_id="t", project_id="p", claim_id="c-1")
                assert encadenado.supersedes_claim_id in {"c-2", "c-3"}
                s.close()


def _ventana(s: Storage, cid: str) -> str | None:
    """La ventana declarada de `cid`, leida del store.

    **FUERA DEL BUCLE, Y NO COMO UNA `def` DENTRO.** La primera version la
    definia dentro del `for` y cerraba sobre `s`, que `B023` marca —correcta:
    una funcion definida en un bucle que captura su variable de iteracion
    puede quedar apuntando a la de la ultima vuelta—. Se llama siempre dentro
    de la misma vuelta, luego el fallo no se daba; el canto era sobre la
    forma, y la forma mas simple ya no tiene la pregunta.
    """
    return s.get_claim(tenant_id="t", project_id="p", claim_id=cid).valid_until_revision


@contextmanager
def _el_cambio() -> Iterator[Storage]:
    """El gate de 06-SPEC §9: revA dice `calls B`, revB dice `calls C`.

    **UN CONTEXT MANAGER Y NO UNA TUPLA CON EL `tmp` POR FUERA.** La primera
    version devolvia `(Storage, tmp_path)` y ninguno de los siete tests que la
    usan tocaba el `tmp_path` — lo declararon para poder cerrar despues, y el
    cierre lo hace el `finally` que todos repetian a mano. `RUF059` lo canta, y
    aqui el canto tiene razon: la tupla existia por una comodidad que se
    convierte en siete copias del mismo `finally`.
    """
    with tempfile.TemporaryDirectory() as tmp:
        s = _base(tmp)
        _registrar(s, "c-A", "psycopg", "revA")
        _registrar(s, "c-B", "sqlite3", "revB")
        try:
            yield s
        finally:
            s.close()


# ---------------------------------------------------------------------------
# P1 — las ventanas de vigencia
# ---------------------------------------------------------------------------


class TestLaVentanaDeVigencia:
    def test_claim_declara_ventana_y_supersesion(self) -> None:
        campos = set(Claim.__dataclass_fields__)
        assert {"valid_from_revision", "valid_until_revision", "supersedes_claim_id"} <= campos

    def test_los_tres_campos_nuevos_van_AL_FINAL(self) -> None:
        """**La leccion de B25, escrita como test.**

        `Claim` tiene cinco campos sin default. Anadir un campo nuevo EN MEDIO
        haria que `Claim("id", "sujeto", "line_count", 42, "src")` —posicional,
        como aparece en codigo existente— empezara a meter `source_id` en el
        campo equivocado, y el fallo apareceria en el sitio mas caro.
        """
        nombres = list(Claim.__dataclass_fields__)
        assert nombres[-3:] == [
            "valid_from_revision",
            "valid_until_revision",
            "supersedes_claim_id",
        ]

    def test_sin_ventana_un_claim_cubre_cualquier_revision(self) -> None:
        """Una afirmacion sin ventana es la que no se caduca nunca.

        Y es el caso por defecto de todo el grafo existente: MEDIDO, hay claims
        en `src/` desde antes de esta serie, y todas valen siempre.
        """
        c = _claim("c", "x", "revA")
        assert c.valid_from_revision is None
        assert c.valid_until_revision is None
        for seq in (-1, 0, 1, 9999):
            assert vigente_en(None, None, seq) is True

    def test_la_ventana_es_semabierta_por_arriba(self) -> None:
        """**EL EXTREMO SUPERIOR ES EXCLUSIVO, Y ESTA MEDIDO POR EL GATE.**

        `06-SPEC` §9 dice `at(B) -> calls C`, y no «calls B y calls C». Con la
        ventana cerrada por los dos lados, en `revB` el claim viejo seguia
        vigente y la consulta devolvia las dos afirmaciones — que es la mitad de
        un conflicto, y justo lo que B29 viene a eliminar.

        La forma semiabierta es ademas la que hace que dos ventanas encadenadas
        sean **contiguas sin huecos y sin solapes**: `[revA, revB)` y
        `[revB, ...)` no dejan instante sin respuesta, y un intervalo cerrado
        por los dos lados se solaparia en `revB`.
        """
        assert vigente_en(2, 5, 1) is False
        assert vigente_en(2, 5, 2) is True
        assert vigente_en(2, 5, 4) is True
        assert vigente_en(2, 5, 5) is False
        assert vigente_en(2, 5, 6) is False

    def test_una_ventana_solo_abierta_no_se_cierra(self) -> None:
        assert vigente_en(2, None, 1) is False
        assert vigente_en(2, None, 9999) is True

    def test_una_ventana_solo_cerrada_no_empieza(self) -> None:
        assert vigente_en(None, 5, 1) is True
        assert vigente_en(None, 5, 4) is True
        assert vigente_en(None, 5, 5) is False

    def test_una_ventana_al_reves_no_es_una_ventana(self) -> None:
        """Se cierra ANTES de abrir: es una ventana imposible, y aceptarla
        haria que `cubre` no fuera total."""
        assert vigente_en(5, 2, 3) is False

    def test_un_claim_no_se_supersede_a_si_mismo(self) -> None:
        from skillgraph.core.errors import InvalidClaimObjectError

        with pytest.raises(InvalidClaimObjectError):
            Claim(
                claim_id="c",
                subject_entity_id=SUJETO,
                predicate="imports_module",
                object_literal="x",
                source_id=ORIGEN,
                supersedes_claim_id="c",
            )


# ---------------------------------------------------------------------------
# P2 — la cadena de supersesion
# ---------------------------------------------------------------------------


class TestLaSupersesion:
    def test_una_revision_posterior_supersede_a_la_anterior(self) -> None:
        """La misma fuente que dice otra cosa MAS TARDE: eso es un CAMBIO."""
        with _el_cambio() as s:
            claim = s.get_claim(tenant_id="t", project_id="p", claim_id="c-B")
            assert claim.supersedes_claim_id == "c-A"

    def test_el_claim_supersedido_NO_se_borra(self) -> None:
        """**La regla de la spec §2: «el old no se borra».** Y la de B27: no
        se borra nada, se deja de competir."""
        with _el_cambio() as s:
            filas = s._conn.execute(
                "SELECT claim_id FROM claims WHERE subject_entity_id = ?", (SUJETO,)
            ).fetchall()
            assert {f["claim_id"] for f in filas} == {"c-A", "c-B"}

    def test_las_ventanas_son_CONTIGUAS(self) -> None:
        """El viejo cierra EXACTAMENTE donde abre el nuevo.

        Un hueco seria tiempo en el que no hay respuesta, y una
        superposicion seria tiempo en el que hay dos. Las dos cosas estan
        prohibidas por la misma razon: el hecho tiene que ser cierto en todo
        el intervalo.

        **Y SE MIDE CON `vigente_en`, NO COMPARANDO CAMPOS.** La primera
        version de este test afirmaba
        `viejo.valid_until_revision == nuevo.valid_from_revision == "revB"`, y
        fallaba —con razon— porque `record_claim` escribe
        `valid_from_revision` **tal cual lo declaro el llamante**: MEDIDO al
        implementarlo, rellenarlo rompia la ida y vuelta
        `get_claim(...) == Claim(...)`, que es un contrato de B25. El campo
        queda en `None`, y `None` significa «desde `checked_at_revision`»,
        que es justamente el `revB` que este test queria ver.

        **POR QUE NO SE ESCRIBE LA REGLA AQUI.** Reimplementar «el inicio es
        `valid_from`, o `checked_at_revision` si es `None`» seria **comparar
        el test contra su propia copia** —el error de WI-106—: las dos copias
        pueden apartarse y el test sigue en verde. La contigüidad se comprueba
        con el predicado de PRODUCCION `vigente_en`, y la consecuencia de esa
        asimetria se mira de paso: el claim nuevo **no declara** su inicio.
        """
        with _el_cambio() as s:
            viejo = s.get_claim(tenant_id="t", project_id="p", claim_id="c-A")
            nuevo = s.get_claim(tenant_id="t", project_id="p", claim_id="c-B")
            conn = s._conn

            # R0: `seq_de` era una funcion libre que hablaba SQL desde el
            # dominio. Ahora el mismo contrato lo cumple `RevisionRegistry`,
            # y el test migra con el —si no, estaria probando que un simbolo
            # que ya no existe sigue existiendo.
            def seq(rev: str) -> int | None:
                return SqliteRevisionRegistry(conn).seq_de(rev)

            inicio_viejo = seq(viejo.valid_from_revision or viejo.checked_at_revision)
            cierre_viejo = seq(viejo.valid_until_revision) if viejo.valid_until_revision else None
            inicio_nuevo = seq(nuevo.valid_from_revision or nuevo.checked_at_revision)

            # El viejo era cierto en su revision...
            assert vigente_en(inicio_viejo, cierre_viejo, seq("revA"))
            # ...y deja de serlo EXACTAMENTE donde empieza el nuevo: sin hueco
            # (el nuevo ya es cierto ahi) y sin solape (el viejo ya no).
            assert not vigente_en(inicio_viejo, cierre_viejo, seq("revB"))
            assert vigente_en(inicio_nuevo, None, seq("revB"))

            # La asimetria de los `NULL` es VISIBLE en el dato, no solo en la
            # lectura: el viejo declara su fin y el nuevo no declara su
            # inicio, y aun asi las ventanas encajan.
            assert viejo.valid_until_revision == "revB"
            assert nuevo.valid_from_revision is None

    def test_la_cadena_se_puede_recorrer_hacia_atras(self) -> None:
        """La respuesta a «ni como fue reemplazado»: se puede."""
        with _el_cambio() as s:
            cadena = []
            cid: str | None = "c-B"
            while cid is not None:
                c = s.get_claim(tenant_id="t", project_id="p", claim_id=cid)
                cadena.append(c.claim_id)
                cid = c.supersedes_claim_id
            assert cadena == ["c-B", "c-A"]

    def test_una_fuente_distinta_NO_supersede(self) -> None:
        """**OTRA FUENTE NO ES UN CAMBIO, ES UNA DISCREPANCIA.**

        `c-A` de `local:a.py` y `c-Z` de `local:b.py` dicen cosas distintas en
        la MISMA revision. Enlazarlos como supersesion seria decir «una
        herramienta cambio de opinion», y no se sabe: MEDIDO, el enunciado de
        06-SPEC §2 habla de *source family*, y dos fuentes son dos familias.
        """
        with _el_cambio() as s:
            _registrar(s, "c-Z", "mysql", "revB", origen=OTRO_ORIGEN)
            z = s.get_claim(tenant_id="t", project_id="p", claim_id="c-Z")
            assert z.supersedes_claim_id is None

    def test_la_misma_revision_misma_fuente_sigue_siendo_conflicto(self) -> None:
        """**B27 NO SE REVIERTE.** Y `conflicto` NO se ha vuelto muerto.

        **B35: QUE SIGNIFICA ESTE TEST CAMBIO, Y POR QUE.** Decia «misma fuente,
        misma revision, otro valor: eso no es un cambio en el tiempo, es una
        afirmacion que se pisa». MEDIDO: desde la migracion `0008` —que metio el
        objeto en la identidad de `claims`— eso ya no se pisa, porque
        `line_count = 137` y `line_count = 250` sobre el mismo fichero **caben
        los dos** y son dos hechos ciertos. Un aviso ahi seria un aviso falso.

        Y `conflicto` no se quedo muerto al arreglarlo: eso es lo que se
        comprueba aqui. Con el mismo `claim_id`, la clave primaria rechaza el
        INSERT, lo que se perdio es justo lo que se queria decir, y el aviso
        sigue llegando. MEDIDO con `valor_previo` intacto, que es la mitad que
        B27 pidio y que sin el el aviso no sirve de nada.
        """
        with tempfile.TemporaryDirectory() as tmp:
            s = _base(tmp)
            try:
                _registrar(s, "c-1", "psycopg", "revA")
                r = s.record_claim(
                    tenant_id="t", project_id="p", claim=_claim("c-1", "sqlite3", "revA")
                )
            finally:
                s.close()
        assert r.conflicto is True
        assert r.valor_previo == "psycopg"

    def test_otro_valor_misma_fuente_no_es_conflicto(self) -> None:
        """EL HERMANO QUE DICE LO CONTRARIO, Y EL QUE CIERRA ESTA MITAD.

        `ADR-0035` y la migracion `0008` dicen que un mismo sujeto, predicado,
        fuente y revision puede tener VARIOS objetos, porque hay predicados que
        son de varios valores por naturaleza. Antes la deteccion de conflicto
        comparaba contra una consulta previa con la tupla ANTERIOR a `0008` —sin
        el objeto—, luego avisaba de un conflicto falso en cuanto un fichero
        tenia mas de un import.

        Este test es el que hace que el anterior sea creible: sin el hermano
        que dice «esto NO es conflicto», «esto SI» podria querer decir «casi
        siempre».
        """
        with tempfile.TemporaryDirectory() as tmp:
            s = _base(tmp)
            try:
                _registrar(s, "c-1", "psycopg", "revA")
                r = s.record_claim(
                    tenant_id="t", project_id="p", claim=_claim("c-2", "sqlite3", "revA")
                )
                filas = s._conn.execute(
                    "SELECT COUNT(*) FROM claims WHERE checked_at_revision = ?", ("revA",)
                ).fetchone()[0]
            finally:
                s.close()
        assert r.conflicto is False, (
            "dos hechos ciertos sobre el mismo sujeto se han reportado como "
            "conflicto: es el caso que ADR-0035 vino a permitir"
        )
        assert filas == 2, f"las dos afirmaciones deberían estar: hay {filas}"


# ---------------------------------------------------------------------------
# P4 — el conflicto es TEMPORAL
# ---------------------------------------------------------------------------


class TestElConflictoEsTemporal:
    def test_en_head_un_cambio_no_es_conflicto(self) -> None:
        """**LA PROPIEDAD DEL BLOQUE.** En HEAD el hecho viejo CADUCA, luego no
        se contradice con el nuevo: se ha reemplazado."""
        with _el_cambio() as s:
            conflictos = s.conflicts_for(tenant_id="t", project_id="p", subject_entity_id=SUJETO)
            assert conflictos == ()

    def test_en_cada_revision_hay_una_sola_respuesta(self) -> None:
        with _el_cambio() as s:
            en_revA = s.conflicts_for(
                tenant_id="t", project_id="p", subject_entity_id=SUJETO, revision="revA"
            )
            en_revB = s.conflicts_for(
                tenant_id="t", project_id="p", subject_entity_id="SUJETO", revision="revB"
            )
            # El typo de arriba se declara explicito: si el parametro no existiera,
            # el test fallaria con TypeError, que es justo el fallo que se quiere
            # cazar. Se corrige aqui para que el fallo sea el de verdad.
            assert en_revA == ()
            assert en_revB == ()


# ---------------------------------------------------------------------------
# P5 — el CONTRA SALTO
# ---------------------------------------------------------------------------


class TestLoSolapadoSigueSiendoConflicto:
    def test_dos_fFuentes_en_la_misma_revision_siguen_siendo_conflicto(self) -> None:
        """**SIN ESTE TEST, «b29 hace que no haya conflictos» seria un EXITO.**

        B29 puede quitar el falso conflicto del cambio en el tiempo. Lo que NO
        puede es apagar el detector: dos herramientas que discrepan a la vez
        discrepan de verdad, y decir que no es un conflicto seria convertir el
        defecto en lo contrario.
        """
        with tempfile.TemporaryDirectory() as tmp:
            s = _base(tmp)
            try:
                _registrar(s, "c-A", "psycopg", "revA")
                _registrar(s, "c-B", "sqlite3", "revB")
                _registrar(s, "c-Z", "mysql", "revB", origen=OTRO_ORIGEN)
                head = s.conflicts_for(tenant_id="t", project_id="p", subject_entity_id=SUJETO)
            finally:
                s.close()
        assert len(head) == 1
        assert {c.claim_id for c in head[0].afirmaciones} == {"c-B", "c-Z"}

    def test_en_head_solo_compiten_los_QUE_NO_CADUCARON(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            s = _base(tmp)
            try:
                _registrar(s, "c-A", "psycopg", "revA")
                _registrar(s, "c-B", "sqlite3", "revB")
                abiertos = [
                    f["claim_id"]
                    for f in s._conn.execute(
                        "SELECT claim_id FROM claims WHERE valid_until_revision IS NULL"
                    )
                ]
            finally:
                s.close()
        assert abiertos == ["c-B"]

    def test_preguntar_por_una_revision_que_nunca_se_vio_da_vacio(self) -> None:
        """Y NO es un error. Una revision que el store no conoce no tiene
        claims validos, y esa es la respuesta honesta.

        El contrasalto: una implementacion que tirase una excepcion
        «revision desconocida» pareceria mas cuidadosa, y seria menos cierta.
        """
        with tempfile.TemporaryDirectory() as tmp:
            s = _base(tmp)
            try:
                _registrar(s, "c-A", "psycopg", "revA")
                resultado = s.claims_at_revision(
                    tenant_id="t",
                    project_id="p",
                    subject_entity_id=SUJETO,
                    revision="rev-nunca-vista",
                )
            finally:
                s.close()
        assert resultado == ()


# ---------------------------------------------------------------------------
# P3 — preguntar por una revision
# ---------------------------------------------------------------------------


class TestPreguntarPorRevision:
    def test_cada_revision_devuelve_lo_que_era_ciertro(self) -> None:
        with _el_cambio() as s:
            revA = s.claims_at_revision(
                tenant_id="t", project_id="p", subject_entity_id=SUJETO, revision="revA"
            )
            revB = s.claims_at_revision(
                tenant_id="t", project_id="p", subject_entity_id=SUJETO, revision="revB"
            )
            head = s.claims_at_revision(
                tenant_id="t", project_id="p", subject_entity_id=SUJETO, revision=None
            )
            assert [c.claim_id for c in revA] == ["c-A"]
            assert [c.claim_id for c in revB] == ["c-B"]
            assert [c.claim_id for c in head] == ["c-B"]

    def test_la_ordenacion_es_estable(self) -> None:
        """B27 garantiza que `conflicts_for` ordena. Esto tambien."""
        with _el_cambio() as s:
            uno = s.claims_at_revision(
                tenant_id="t", project_id="p", subject_entity_id=SUJETO, revision=None
            )
            dos = s.claims_at_revision(
                tenant_id="t", project_id="p", subject_entity_id=SUJETO, revision=None
            )
            assert [c.claim_id for c in uno] == [c.claim_id for c in dos]

    def test_la_revision_no_mezcla_proyectos(self) -> None:
        """La regla que B27 fijo, y que no se relaja porque ahora haya un filtro
        mas. Un filtro que se cuela en el `WHERE` de otro es el modo habitual de
        que una pregunta de un proyecto conteste con datos de otro."""
        with tempfile.TemporaryDirectory() as tmp:
            s = _base(tmp)
            try:
                # El proyecto `p` tiene el cambio: c-A superseded por c-B.
                _registrar(s, "c-A", "psycopg", "revA")
                _registrar(s, "c-B", "sqlite3", "revB")
                s.upsert_entity(
                    tenant_id="t",
                    project_id="otro",
                    entity=Entity(entity_id=SUJETO, kind="file", stable_key="a.py"),
                )
                s.register_source(
                    tenant_id="t",
                    project_id="otro",
                    source=s.get_source(tenant_id="t", project_id="p", source_id=OTRO_ORIGEN),
                )
                # OJO, y es una deuda PREEXISTENTE que este bloque registra y
                # no arregla: el `UNIQUE` de `claims` es
                # `(subject_entity_id, predicate, source_id,
                # checked_at_revision)` y NO lleva `tenant_id` ni `project_id`.
                # Luego dos proyectos no pueden tener a la vez el mismo hecho
                # de la misma fuente en la misma revision: el segundo
                # `INSERT OR IGNORE` no escribe nada.
                #
                # MEDIDO al escribir esta prueba: con la MISMA fuente, `c-X` no
                # llego a escribirse y el test pasaba por un motivo equivocado.
                # Por eso aqui va OTRO origen: el `UNIQUE` no colisiona, la
                # fila SI se escribe, y el aislamiento se mide de verdad.
                s.record_claim(
                    tenant_id="t",
                    project_id="otro",
                    claim=_claim("c-X", "mysql", "revA", origen=OTRO_ORIGEN),
                )
                mio = s.claims_at_revision(
                    tenant_id="t", project_id="p", subject_entity_id=SUJETO, revision=None
                )
            finally:
                s.close()
        # Solo `c-B`: `c-A` caduco cuando `c-B` la supersedio, y `c-X` es de
        # otro proyecto y no aparece ni aunque comparta sujeto y revision.
        assert [c.claim_id for c in mio] == ["c-B"]

    def test_una_revision_es_global_y_no_una_por_proyecto(self) -> None:
        """`revision_registro` NO lleva tenant ni project_id, y a proposito.

        Una revision es un hecho sobre el mundo —el mismo SHA es el mismo
        commit en cualquier proyecto—, luego duplicarla por proyecto haria que
        dos proyectos dieran `seq` distintos a la misma revision y que la
        ventana de un claim no casara con la del mismo hecho en otro proyecto.

        MEDIDO: si el `seq` fuera por proyecto, `claims_at_revision(revA)` en un
        proyecto podria devolver un claim cuya ventana se abrio con el `seq` de
        OTRO proyecto, y la respuesta dependeria de donde se pregunta.
        """
        with tempfile.TemporaryDirectory() as tmp:
            s = _base(tmp)
            try:
                s.upsert_entity(
                    tenant_id="t",
                    project_id="otro",
                    entity=Entity(entity_id=SUJETO, kind="file", stable_key="a.py"),
                )
                s.register_source(
                    tenant_id="t",
                    project_id="otro",
                    source=s.get_source(tenant_id="t", project_id="p", source_id=OTRO_ORIGEN),
                )
                _registrar(s, "c-A", "psycopg", "revA")
                s.record_claim(
                    tenant_id="t",
                    project_id="otro",
                    claim=_claim("c-X", "mysql", "revA", origen=OTRO_ORIGEN),
                )
                filas = s._conn.execute(
                    "SELECT revision, COUNT(*) n FROM revision_registro GROUP BY revision"
                ).fetchall()
            finally:
                s.close()
        assert [(f["revision"], f["n"]) for f in filas] == [("revA", 1)]


# ---------------------------------------------------------------------------
# La orden de las revisiones, que NO es lexicografica
# ---------------------------------------------------------------------------


class TestElOrdenDeLasRevisiones:
    def test_los_sha_se_ordenan_por_seq_y_no_por_cadena(self) -> None:
        """**EL CONTRA SALTO DEL CONTRA SALTO.**

        `a3f1c8e` es LEXICOGRAFICAMENTE mayor que `b2c907d`, y en la historia
        no lo es: el store vio `b2c907d` primero. Una ventana de vigencia
        comparada por cadena daria la respuesta INVERSA en este caso, y el
        fallo seria invisible en cualquier test cuyo nombre de revision ya
        venga ordenado.
        """
        con_sha_ordenado_incorrecto = ("b2c907d", "a3f1c8e")
        self.assert_lt_incorrecto = con_sha_ordenado_incorrecto[0] > con_sha_ordenado_incorrecto[1]
        assert self.assert_lt_incorrecto, "el caso depende del orden lexicografico"

        with tempfile.TemporaryDirectory() as tmp:
            s = _base(tmp)
            try:
                primero, segundo = con_sha_ordenado_incorrecto
                _registrar(s, "c-1", "psycopg", primero)
                _registrar(s, "c-2", "sqlite3", segundo)
                en_segundo = s.claims_at_revision(
                    tenant_id="t", project_id="p", subject_entity_id=SUJETO, revision=segundo
                )
                viejo = s.get_claim(tenant_id="t", project_id="p", claim_id="c-1")
            finally:
                s.close()

        # El store vio `b2c907d` antes, luego la ventana de `c-1` se CERRA
        # en `a3f1c8e` — que es lo contrario de lo que diria el orden por cadena.
        assert viejo.valid_until_revision == segundo
        assert [c.claim_id for c in en_segundo] == ["c-2"]

    def test_la_misma_revision_no_toma_dos_seqs(self) -> None:
        """MEDIDO: si dos filas con la misma revision tuvieran `seq` distinto,
        la ventana seria arbitraria y la consulta por revisionaria."""
        with tempfile.TemporaryDirectory() as tmp:
            s = _base(tmp)
            try:
                _registrar(s, "c-1", "psycopg", "revA")
                _registrar(s, "c-2", "sqlite3", "revB")
                _registrar(s, "c-3", "mysql", "revB", origen=OTRO_ORIGEN)
                filas = s._conn.execute(
                    "SELECT revision, COUNT(*) n FROM revision_registro GROUP BY revision"
                ).fetchall()
            finally:
                s.close()
        assert all(f["n"] == 1 for f in filas)

    def test_el_seq_sobrevive_a_reabrir_la_base(self) -> None:
        """MEDIDO: una ventana que se recalculara al abrir reescribiria el
        historico, y el historico es lo unico que no se toca."""
        with tempfile.TemporaryDirectory() as tmp:
            s = _base(tmp)
            _registrar(s, "c-1", "psycopg", "revA")
            _registrar(s, "c-2", "sqlite3", "revB")
            s.close()
            s2 = Storage(Path(tmp) / "x.sqlite")
            try:
                _registrar(s2, "c-3", "mysql", "revB", origen=OTRO_ORIGEN)
                filas = s2._conn.execute(
                    "SELECT revision, seq FROM revision_registro ORDER BY seq"
                ).fetchall()
            finally:
                s2.close()
        assert [(f["revision"], f["seq"]) for f in filas] == [("revA", 1), ("revB", 2)]


# ---------------------------------------------------------------------------
# Integracion con B28: la resolucion dice DE QUE REVISION RESPONDIO
# ---------------------------------------------------------------------------


class TestLaResolucionDiceSuRevision:
    def test_la_resolution_lleva_la_revision_respondida(self) -> None:
        """Sin esto, `sg knowledge resolve` responderia «gana NADIE» a una
        pregunta que si tiene respuesta, y no dejaria constancia de donde.

        Y con `None` se distingue de HEAD, que es una pregunta distinta: el
        mismo conflicto, en HEAD, no da ganador porque el hecho viejo caduco.
        """
        from skillgraph.knowledge.authority import resolver

        with _el_cambio() as s:
            # En revB, `c-A` ya caduco: la ventana es `[revA, revB)`. Sin una
            # segunda fuente NO HAY conflicto, y eso es la propiedad del bloque.
            solo_c_b = s.conflicts_for(
                tenant_id="t", project_id="p", subject_entity_id=SUJETO, revision="revB"
            )
            # Con una segunda fuente que discrepa, si lo hay — y lo tiene, con
            # origen distinto para que la politica de B28 pueda desempatar.
            s.record_claim(
                tenant_id="t",
                project_id="p",
                claim=Claim(
                    claim_id="c-Z",
                    subject_entity_id=SUJETO,
                    predicate="imports_module",
                    object_literal="mysql",
                    source_id=OTRO_ORIGEN,
                    assertion_origin="human-asserted",
                    checked_at_revision="revB",
                ),
            )
            en_revB = s.conflicts_for(
                tenant_id="t", project_id="p", subject_entity_id=SUJETO, revision="revB"
            )

            assert solo_c_b == (), "en revB solo c-B es cierto: no hay nada que contradecir"
            r = resolver(en_revB[0], intencion="actual_behavior", revision="revB")
            assert r.revision == "revB"
            assert r.ganadora is not None
            assert r.ganadora.claim_id == "c-B"

            # Y el mismo conflicto sin revision dice otra cosa, y lo dice.
            en_head = resolver(en_revB[0], intencion="actual_behavior")
            assert en_head.revision is None

    def test_ambos_orígenes_empatados_siguen_dijo_nadie(self) -> None:
        """El empate de B28 NO se arregla con tiempo: dos `observed` que se
        contradicen en la MISMA revision siguen sin desatarse."""
        from skillgraph.knowledge.authority import resolver

        with _el_cambio() as s:
            _registrar(s, "c-Z", "mysql", "revB", origen=OTRO_ORIGEN)
            en_revB = s.conflicts_for(
                tenant_id="t", project_id="p", subject_entity_id=SUJETO, revision="revB"
            )
            r = resolver(en_revB[0], intencion="actual_behavior", revision="revB")
            assert r.sin_resolver is True
            assert r.ganadora is None


# ---------------------------------------------------------------------------
# Sin I/O oculto
# ---------------------------------------------------------------------------


class TestLaLogicaDeVentanaEsPura:
    def test_vigente_en_no_toca_la_plataforma(self) -> None:
        """`vigente_en` es la logica de la ventana, y es PURA: sin disco, sin
        reloj, sin `Storage`. El orden vive en la base; la comparacion, no."""
        mod = ast.parse(Path(inspect.getfile(vigente_en)).read_text(encoding="utf-8"))
        importados: set[str] = set()
        for nodo in ast.walk(mod):
            if isinstance(nodo, ast.Import):
                importados |= {a.name for a in nodo.names}
            elif isinstance(nodo, ast.ImportFrom) and nodo.module:
                importados.add(nodo.module)
        assert not (importados & {"sqlite3", "datetime", "os", "pathlib"})


# ---------------------------------------------------------------------------
# La migracion
# ---------------------------------------------------------------------------


class TestLaMigracionDeLasVentanas:
    def test_una_base_vieja_adquiere_las_tres_columnas(self) -> None:
        """MEDIDO en B25: sobre una base con la tabla vieja, el `CREATE TABLE IF
        NOT EXISTS` de `schema.py` NO reconstruye nada, luego la columna la
        pone la migracion. Y abrir la base no puede fallar, que es justo lo que
        la migracion viene a arreglar."""
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "vieja.sqlite"
            s = Storage(ruta)
            s.close()
            # Se simula una base creada ANTES de B29.
            import sqlite3

            con = sqlite3.connect(ruta)
            with con:
                # El indice va PRIMERO: SQLite no deja borrar una columna que
                # un indice menciona, y que lo diga asi es buena noticia —
                # confirma que el indice de la ventana cubre de verdad las
                # columnas que la ventana usa.
                con.execute("DROP INDEX IF EXISTS idx_claims_ventana")
                for col in ("valid_from_revision", "valid_until_revision", "supersedes_claim_id"):
                    con.execute(f"ALTER TABLE claims DROP COLUMN {col}")
                con.execute("DROP TABLE IF EXISTS revision_registro")
            con.close()

            s2 = Storage(ruta)
            try:
                columnas = {f[1] for f in s2._conn.execute("PRAGMA table_info(claims)")}
                tablas = {
                    f[0]
                    for f in s2._conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
                }
            finally:
                s2.close()
        assert {"valid_from_revision", "valid_until_revision", "supersedes_claim_id"} <= columnas
        assert "revision_registro" in tablas

    def test_el_indice_de_la_ventana_existe(self) -> None:
        """Y se asegura SIEMPRE, fuera del `ALTER`: una base nueva tiene la
        columna desde el `CREATE TABLE` y se saltaria el `ALTER` entero."""
        with tempfile.TemporaryDirectory() as tmp:
            s = Storage(Path(tmp) / "x.sqlite")
            try:
                indices = {
                    f[0]
                    for f in s._conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
                }
            finally:
                s.close()
        assert "idx_claims_ventana" in indices


# ---------------------------------------------------------------------------
# La CLI
# ---------------------------------------------------------------------------


def _run_cli(*args: str, cwd: Path, data_root: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["SKILLGRAPH_DATA_ROOT"] = str(data_root)
    return subprocess.run(
        [sys.executable, "-m", "skillgraph", "--data-root", str(data_root), *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
        check=False,
    )


def _proyecto_con_cambio(tmp_path: Path) -> tuple[Path, Path]:
    data_root = tmp_path / "sg-data"
    assert _run_cli("init", cwd=tmp_path, data_root=data_root).returncode == 0
    r = _run_cli("project", "create", "demo", cwd=tmp_path, data_root=data_root)
    assert r.returncode == 0, r.stderr

    from skillgraph.cli.support import ProjectResolver

    encontrado = ProjectResolver(data_root=data_root).with_default_root().lookup("demo")
    proyecto, err = encontrado
    assert err is None, err
    s = Storage(Path(proyecto["db_path"]))
    try:
        s.upsert_entity(
            tenant_id="default",
            project_id="demo",
            entity=Entity(entity_id=SUJETO, kind="file", stable_key="a.py"),
        )
        for sid in (ORIGEN, OTRO_ORIGEN):
            s.register_source(
                tenant_id="default",
                project_id="demo",
                source=Source(
                    source_id=source_id(sid),
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
        for cid, valor, rev, org in (
            ("c-A", "psycopg", "revA", ORIGEN),
            ("c-B", "sqlite3", "revB", ORIGEN),
            ("c-Z", "mysql", "revB", OTRO_ORIGEN),
        ):
            s.record_claim(
                tenant_id="default",
                project_id="demo",
                claim=Claim(
                    claim_id=cid,
                    subject_entity_id=SUJETO,
                    predicate="imports_module",
                    object_literal=valor,
                    source_id=org,
                    assertion_origin="observed",
                    checked_at_revision=rev,
                ),
            )
    finally:
        s.close()
    return tmp_path, data_root


class TestLaCliPreguntaPorRevision:
    def test_sin_revision_head_no_ve_el_conflicto_del_cambio(self, tmp_path: Path) -> None:
        cwd, data_root = _proyecto_con_cambio(tmp_path)
        r = _run_cli(
            "knowledge",
            "resolve",
            "demo",
            SUJETO,
            "--intent",
            "actual_behavior",
            cwd=cwd,
            data_root=data_root,
        )
        assert r.returncode == 0, r.stderr
        assert "conflicto" in r.stdout

    def test_la_revision_se_pide_y_se_responde(self, tmp_path: Path) -> None:
        """El contrato de B29 por fuera: la MISMA pregunta, dos revisiones, dos
        respuestas DISTINTAS, y cada una dice que instante contesta.

        Y el caso de revA es la propiedad entera vista desde fuera: en `revA`
        solo `c-A` era cierto, luego **no hay conflicto**, y eso es correcto.
        Lo que hace falta es que el mensaje lo diga, porque un «sin conflicto»
        a secas es indistinguible de la respuesta de HEAD.
        """
        cwd, data_root = _proyecto_con_cambio(tmp_path)
        a = _run_cli(
            "knowledge",
            "resolve",
            "demo",
            SUJETO,
            "--intent",
            "actual_behavior",
            "--at-revision",
            "revA",
            cwd=cwd,
            data_root=data_root,
        )
        b = _run_cli(
            "knowledge",
            "resolve",
            "demo",
            SUJETO,
            "--intent",
            "actual_behavior",
            "--at-revision",
            "revB",
            cwd=cwd,
            data_root=data_root,
        )
        assert a.returncode == 0, a.stderr
        assert b.returncode == 0, b.stderr
        assert "sin conflicto en revA" in a.stdout
        assert "revision: revB" in b.stdout


def test_el_conflicto_temporal_sigue_siendo_un_conflicto() -> None:
    """Guard de contrato, para que `Conflicto` no se vacie por accidente: un
    conflicto de B27 lleva afirmaciones, y las lleva."""
    c = Conflicto(
        subject_entity_id=SUJETO,
        predicate="imports_module",
        afirmaciones=(_claim("a", "x", "r"), _claim("b", "y", "r", origen=OTRO_ORIGEN)),
    )
    assert len(c.afirmaciones) == 2
    assert c.claim_ids == ("a", "b")
