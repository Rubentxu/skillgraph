"""B27 — Dos claims incompatibles no se pisan en silencio, y hay forma de saberlo.

**EL ENUNCIADO DE LA FILA EXAGERA, Y EL BLOQUE SE CONSTRUYE SOBRE LO MEDIDO.**

La fila dice: *«Dos claims incompatibles se pisan y no hay forma de saberlo»*.
MEDIDO antes de escribir nada, con `scripts/measure_b27_conflictos.py`:

    P1  CERRADA  dos fuentes que dicen cosas distintas -> 2 filas, COEXISTEN
    P2  CERRADA  misma fuente, mismos hechos opuestos  -> 1 fila, SE PISA

Es decir: el overwrite **no** depende de que dos herramientas discrepen. Depende
de la MISMA fuente con la MISMA revision. Construir el bloque sobre el enunciado
literal habria sido construirlo sobre una premisa que no se sostiene.

Y el defecto real tiene tres caras, que son tres tests distintos:

1. `record_claim` **no avisa**: su `INSERT OR IGNORE` puede no escribir nada y
   devuelve el `claim_id` de todos modos, como si hubiera escrito.
2. **No existe el concepto de conflicto**: nada, dados dos claims del mismo
   sujeto y predicado con objetos distintos, dice si se contradicen.
3. Por tanto **no hay nada que pueda ser estable**, que es lo que B28 necesita
   para resolver por intencion de consulta.

Cada test nombra la propiedad que mide y **que pasaria si fuera falsa**.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from skillgraph.knowledge.graph import Claim, Entity, Source, source_id
from skillgraph.platform.storage import Storage

SUJETO = "file:a.py"
OTRO = "file:b.py"
ORIGEN_A = "local:a.py"
ORIGEN_B = "local:b.py"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _storage(tmp_path: Path, nombre: str = "b27.sqlite") -> Storage:
    return Storage(tmp_path / nombre)


def _preparar(s: Storage) -> None:
    for eid, key in ((SUJETO, "a.py"), (OTRO, "b.py")):
        s.upsert_entity(
            tenant_id="t", project_id="p", entity=Entity(entity_id=eid, kind="file", stable_key=key)
        )
    for sid in (ORIGEN_A, ORIGEN_B):
        s.register_source(
            tenant_id="t",
            project_id="p",
            source=Source(
                source_id=source_id(sid),
                kind="local_file",
                content_hash="h",
                locator={"path": sid},
                git_commit_sha=None,
                git_tree_sha=None,
                working_tree_status=None,
                checked_at="2026-10-06T00:00:00Z",
                freshness="current",
            ),
        )


def _claim(cid: str, valor: object, sid: str = ORIGEN_A, rev: str = "r1") -> Claim:
    return Claim(
        claim_id=cid,
        subject_entity_id=SUJETO,
        predicate="test_passes",
        object_literal=valor,
        source_id=source_id(sid),
        checked_at_revision=rev,
    )


# ---------------------------------------------------------------------------
# R1 — el overwrite DEJA de ser silencioso
# ---------------------------------------------------------------------------


class TestElOverwriteAvisa:
    def test_escribir_lo_mismo_no_avisa(self, tmp_path: Path) -> None:
        """La idempotencia NO es un conflicto. Reingerir lo mismo es lo de siempre.

        Es el contrasalto que decide el diseño: si reescribir lo mismo se
        reportara como conflicto, B26 dejaria de funcionar —su promesa ES que
        ingerir dos veces deja lo mismo— y todo el bloque anterior se
        desharia para arreglar un defecto que no es un defecto.
        """
        s = _storage(tmp_path)
        _preparar(s)

        primero = s.record_claim(tenant_id="t", project_id="p", claim=_claim("c1", True))
        segundo = s.record_claim(tenant_id="t", project_id="p", claim=_claim("c1", True))

        assert primero.conflicto is False
        assert segundo.conflicto is False, (
            "reingerir lo MISMO se ha reportado como conflicto: eso rompe la "
            "idempotencia que B26 certifico"
        )

    def test_escribir_lo_distinto_si_avisa(self, tmp_path: Path) -> None:
        """EL PRIMER TEST DEL BLOQUE. El que da nombre.

        MEDIDO antes de arreglar nada: el segundo claim se pisa y `record_claim`
        devuelve el `claim_id` de todos modos, como si hubiera escrito.

        Si esto no avisara, quien afirma creeria que su afirmacion quedo
        registrada cuando lo que se registro es **la que ya estaba**. El
        defecto no es que se pierda una fila: es que se pierda la verdad de lo
        que se afirmo, en silencio.

        **B35: LA FORMA DE ESTE TEST CAMBIO, Y POR QUE NO ES DEGADARLO.**
        Antes escribia `test_passes = True` con `ORIGEN_A` y luego
        `test_passes = False` con `ORIGEN_A`: misma fuente, misma revision,
        objeto distinto. `ADR-0035` (migracion `0008`) metio el objeto en la
        identidad de `claims`, luego **las dos filas caben** y no hay nada que
        se haya pisado. MEDIDO: `imports_module='os'` y
        `imports_module='sys'` sobre el mismo fichero son dos hechos
        ciertos, no una contradiccion, y por eso `0008` existe.

        El conflicto que SIGUE existiendo, y que es el que este bloque
        tempo que avisar, es **el mismo `claim_id` con otra afirmacion**: dos
        afirmaciones distintas que escribe el mismo identificador, donde lo que
        se registra es la primera y quien escribe creia haber registrado la
        suya. Ese es el defecto original, y el `UNIQUE` que lo produce es la
        clave primaria.
        """
        s = _storage(tmp_path)
        _preparar(s)

        s.record_claim(tenant_id="t", project_id="p", claim=_claim("c1", True))
        # Mismo `claim_id`, otra afirmacion: la clave primaria rechaza el
        # INSERT y lo que se perdio es justo lo que este bloque quiere que
        # se avise.
        r = s.record_claim(tenant_id="t", project_id="p", claim=_claim("c1", False, sid=ORIGEN_B))

        assert r.conflicto is True, (
            "la segunda afirmacion se piso y el llamante no se entero: "
            "conflicto=False con la fila anterior intacta es una mentira"
        )

    def test_otro_objeto_no_es_conflicto(self, tmp_path: Path) -> None:
        """EL HERMANO QUE DICE LO CONTRARIO, Y EL QUE CIERRA LA MEDIA MITAD.

        `ADR-0035` permits que un mismo sujeto, predicado, fuente y revision
        tengan **varios objetos**, porque hay predicados que son de varios
        valores por naturaleza: un fichero importa varios modulos y define
        varios simbolos, y `imports_module='os'` no contradice a
        `imports_module='sys'`.

        MEDIDO antes de B35: la deteccion de conflicto comparaba contra una
        consulta previa que seguia con la tupla ANTERIOR a `0008` —sin el
        objeto—, luego avisaba de un conflicto falso en cada fichero con mas
        de un import, que es practicamente todos. Se vio por la puerta que
        B35 abrio (`sg knowledge ingest-code`), no leyendo el codigo.
        """
        s = _storage(tmp_path)
        _preparar(s)

        s.record_claim(tenant_id="t", project_id="p", claim=_claim("c1", True))
        r = s.record_claim(tenant_id="t", project_id="p", claim=_claim("c2", False))

        assert r.conflicto is False, (
            "dos hechos ciertos sobre el mismo sujeto y predicado se han "
            "reportado como conflicto: es justo el caso que ADR-0035 vino a "
            "permitir, y avisar aqui es un aviso falso"
        )
        filas = s._conn.execute(
            "SELECT COUNT(*) FROM claims WHERE subject_entity_id = ?", (SUJETO,)
        ).fetchone()[0]
        assert filas == 2, f"las dos afirmaciones deberían estar: hay {filas}"

    def test_el_aviso_dice_que_se_afirmo(self, tmp_path: Path) -> None:
        """«conflicto=True» sin decir que se queria decir, no sirve de nada.

        Sin el valor anterior, quien recibe el aviso no puede hacer nada con el:
        no sabe si lo que se solapa es `true` o `False`, y el aviso se vuelve
        un «algo va mal» sin accion.
        """
        s = _storage(tmp_path)
        _preparar(s)

        s.record_claim(tenant_id="t", project_id="p", claim=_claim("c1", True))
        # **B35: el MISMO `claim_id`.** Con `c2` distinto, la migracion `0008`
        # deja que las dos filas vivan y no hay conflicto que avisar —es el
        # caso que `test_otro_objeto_no_es_conflicto` mide a proposito—. Lo que
        # se pierde, y lo que este bloque vigila, es cuando dos afirmaciones
        # distintas comparten `claim_id` y se queda la primera.
        r = s.record_claim(tenant_id="t", project_id="p", claim=_claim("c1", False))

        assert r.valor_previo is not None, "el aviso no dice que habia antes"
        assert r.valor_previo != r.valor_intento, "el aviso no dice que se intentaba decir"
        assert r.claim_id == "c1", "el aviso no dice que claim se solapa"

    def test_la_fila_anterior_no_se_toca(self, tmp_path: Path) -> None:
        """B27 AVISA, no RESUELVE. La fila que estaba se queda como estaba.

        Esto no es una opinion: es lo que hace que B29 siga teniendo trabajo.
        Si B27 borrara o sustituyera la fila anterior, estaria decidiendo quien
        tiene razon —y quien decide eso es B28, por intencion de consulta— con
        una regla que no tiene en cuenta al que pregunta.
        """
        s = _storage(tmp_path)
        _preparar(s)

        s.record_claim(tenant_id="t", project_id="p", claim=_claim("c1", True))
        s.record_claim(tenant_id="t", project_id="p", claim=_claim("c2", False))

        # **B31: la asercion es MAS FUERTE, no mas debil.** Antes se miraba
        # una fila y se comprobaba que no la hubieran cambiado. Ahora se
        # mira que esten LAS DOS, porque con el objeto dentro de la
        # identidad (`ADR-0035`) son dos hechos distintos y cada uno tiene su
        # fila.
        #
        # Lo que este test protege NO cambia: que la fila anterior siga
        # intacta. Lo que cambia es que ahora hay una segunda fila que
        # antes no existia, y por eso `fetchone()` devolvia la otra y parecia
        # que la habian sustituido.
        #
        # Y por que esto NO debilita a B27: el par sigue haciendo falta, y el
        # hermano de R1F (`test_B31_mismo_ambito_distinto_objeto_SI_se_puede_escribir`)
        # declara la otra mitad. Sin las dos, cambiar la identidad se
        # arreglaria rompiendo la deduplicacion sin que nada lo notara.
        guardados = [
            fila[0]
            for fila in s._conn.execute(
                "SELECT object_literal_json FROM claims ORDER BY claim_id"
            ).fetchall()
        ]
        assert guardados == ["true", "false"], (
            f"esperaba las DOS afirmaciones intactas y hay {guardados}: "
            "el segundo claim ha SUSTITUIDO al primero (B27 avisa, no decide) "
            "o se ha perdido (B31)"
        )


# ---------------------------------------------------------------------------
# R2 — el conflict set es CONSULTABLE
# ---------------------------------------------------------------------------


class TestElConflictSetEsConsultable:
    def test_encuentra_las_afirmaciones_que_se_contradicen(self, tmp_path: Path) -> None:
        """La propiedad del enunciado: saber QUE se contradice.

        Sin esto, las dos filas conviven y el sistema no dice nada, que es
        exactamente el estado en el que se estaba.
        """
        s = _storage(tmp_path)
        _preparar(s)

        s.record_claim(tenant_id="t", project_id="p", claim=_claim("c1", True, ORIGEN_A))
        s.record_claim(tenant_id="t", project_id="p", claim=_claim("c2", False, ORIGEN_B))

        conflictos = s.conflicts_for(tenant_id="t", project_id="p", subject_entity_id=SUJETO)

        assert len(conflictos) == 1, "dos afirmaciones opuestas no se han visto como conflicto"
        (conflicto,) = conflictos
        assert {c.claim_id for c in conflicto.afirmaciones} == {"c1", "c2"}

    def test_una_sola_afirmacion_no_es_conflicto(self, tmp_path: Path) -> None:
        """EL CONTRA SALTO. Sin el, el conflict set devolveria de todo.

        Con una sola afirmacion **no se contradice nadie**, y devolver un
        «conflicto» de una fila seria el equivalente de B25: un sistema que
        llama relacion a lo que solo es coexistence.
        """
        s = _storage(tmp_path)
        _preparar(s)

        s.record_claim(tenant_id="t", project_id="p", claim=_claim("c1", True, ORIGEN_A))

        assert s.conflicts_for(tenant_id="t", project_id="p", subject_entity_id=SUJETO) == ()

    def test_un_sujeto_sin_afirmaciones_no_es_conflicto(self, tmp_path: Path) -> None:
        """Un sujeto del que nadie ha dicho nada no tiene conflictos.

        Se separa del anterior porque son DOS caminos distintos del codigo —el
        `if not rows` y el grupo de una sola fila— y un unico test dejaria uno
        de los dos sin vigilar. Preguntar por un sujeto que no existe es una
        consulta legitima, y su respuesta tiene que ser la misma que la de un
        sujeto del que nadie ha hablado.
        """
        s = _storage(tmp_path)
        _preparar(s)

        assert s.conflicts_for(tenant_id="t", project_id="p", subject_entity_id=OTRO) == ()
        assert (
            s.conflicts_for(tenant_id="t", project_id="p", subject_entity_id="file:no-existe") == ()
        )

    def test_afirmaciones_que_coinciden_no_son_conflicto(self, tmp_path: Path) -> None:
        """Dos fuentes que DICEN LO MISMO no se contradicen.

        Es el otro contrasalto, y es el que mas trampas promete: «distinto
        claim_id» y «distinta fuente» parecen hacerlos distintos, y no lo son.
        """
        s = _storage(tmp_path)
        _preparar(s)

        s.record_claim(tenant_id="t", project_id="p", claim=_claim("c1", True, ORIGEN_A))
        s.record_claim(tenant_id="t", project_id="p", claim=_claim("c2", True, ORIGEN_B))

        assert s.conflicts_for(tenant_id="t", project_id="p", subject_entity_id=SUJETO) == ()

    def test_predicados_distintos_no_se_contradicen(self, tmp_path: Path) -> None:
        """«Los tests pasan» y «el fichero tiene 137 lineas» no se contradicen.

        Se miden porque el sujeto es el mismo y por eso el filtro por sujeto
        solo no basta: haria que cualquier par de afirmaciones sobre un fichero
        pareciese un conflicto.
        """
        s = _storage(tmp_path)
        _preparar(s)
        s.record_claim(tenant_id="t", project_id="p", claim=_claim("c1", True, ORIGEN_A))
        otro = Claim(
            claim_id="c2",
            subject_entity_id=SUJETO,
            predicate="line_count",
            object_literal=137,
            source_id=source_id(ORIGEN_B),
            checked_at_revision="r1",
        )
        s.record_claim(tenant_id="t", project_id="p", claim=otro)

        assert s.conflicts_for(tenant_id="t", project_id="p", subject_entity_id=SUJETO) == ()

    def test_el_conflicto_esta_agrupado_por_predicado(self, tmp_path: Path) -> None:
        """El conflict set agrupa POR PREDICADO, no devuelve una bolsa de claims.

        Sin agrupar, «cuantas contradicciones hay» seria el numero de claims y
        no el de contradicciones: dos grupos de tres darian seis, y quien lo
        leyera contaria algo que no es lo que cree.
        """
        s = _storage(tmp_path)
        _preparar(s)

        s.record_claim(tenant_id="t", project_id="p", claim=_claim("c1", True, ORIGEN_A))
        s.record_claim(tenant_id="t", project_id="p", claim=_claim("c2", False, ORIGEN_B))
        otro = Claim(
            claim_id="c3",
            subject_entity_id=SUJETO,
            predicate="line_count",
            object_literal=137,
            source_id=source_id(ORIGEN_A),
            checked_at_revision="r1",
        )
        cuarto = Claim(
            claim_id="c4",
            subject_entity_id=SUJETO,
            predicate="line_count",
            object_literal=200,
            source_id=source_id(ORIGEN_B),
            checked_at_revision="r1",
        )
        for c in (otro, cuarto):
            s.record_claim(tenant_id="t", project_id="p", claim=c)

        conflictos = s.conflicts_for(tenant_id="t", project_id="p", subject_entity_id=SUJETO)

        assert len(conflictos) == 2, "dos predicados en conflicto son DOS conflictos"
        assert {c.predicate for c in conflictos} == {"test_passes", "line_count"}


# ---------------------------------------------------------------------------
# R3 — el conflict set es ESTABLE
# ---------------------------------------------------------------------------


class TestElConflictSetEsEstable:
    def test_dos_llamadas_dan_el_mismo_orden(self, tmp_path: Path) -> None:
        """La propiedad que hace que B28 pueda existir.

        Un conflict set que dependa del orden en que SQLite devuelva las filas
        no es un conflict set: es el estado de un `SELECT` sin `ORDER BY`. Dos
        consultas iguales darian listas distintas y cualquier consumidor que
        las comparara fallaria de forma intermitente —que es la forma mas cara
        de fallar, porque no falla nunca en la prueba que lo escribio.
        """
        s = _storage(tmp_path)
        _preparar(s)

        for cid, val, src in (
            ("c1", True, ORIGEN_A),
            ("c2", False, ORIGEN_B),
            ("c3", False, ORIGEN_A),
        ):
            s.record_claim(tenant_id="t", project_id="p", claim=_claim(cid, val, src, f"r{cid}"))

        a = s.conflicts_for(tenant_id="t", project_id="p", subject_entity_id=SUJETO)
        b = s.conflicts_for(tenant_id="t", project_id="p", subject_entity_id=SUJETO)

        assert a == b, "dos llamadas seguidas dieron conflict sets distintos"

    def test_el_orden_no_depende_del_orden_de_insercion(self, tmp_path: Path) -> None:
        """Se mide inserting al reves: el orden estable no es el de entrada.

        Si el `ORDER BY` ausente se le pasara por la costumbre de insertar en
        orden, este test pasaria en la mayoria de las corridas y fallaria en la
        que importa.
        """
        en_orden = _storage(tmp_path, "uno.sqlite")
        _preparar(en_orden)
        for cid, val in (("c1", True), ("c2", False), ("c3", False)):
            en_orden.record_claim(
                tenant_id="t",
                project_id="p",
                claim=_claim(cid, val, ORIGEN_A if cid == "c1" else ORIGEN_B, f"r{cid}"),
            )

        al_reves = _storage(tmp_path, "dos.sqlite")
        _preparar(al_reves)
        for cid, val in (("c3", False), ("c2", False), ("c1", True)):
            al_reves.record_claim(
                tenant_id="t",
                project_id="p",
                claim=_claim(cid, val, ORIGEN_A if cid == "c1" else ORIGEN_B, f"r{cid}"),
            )

        uno = en_orden.conflicts_for(tenant_id="t", project_id="p", subject_entity_id=SUJETO)
        otro = al_reves.conflicts_for(tenant_id="t", project_id="p", subject_entity_id=SUJETO)

        assert uno == otro, "el conflict set depende del orden en que se insertaron las filas"

    def test_el_conflicto_no_depende_del_almacen(self, tmp_path: Path) -> None:
        """Dos bases con el MISMO contenido dan el MISMO conflict set.

        Se mide porque es la propiedad que necesita B28: un ranking que cambia
        al cambiar de proyecto no es un ranking, y la razon de que el `claim_id`
        sea determinista es justamente que dos artefactos con el mismo contenido
        tienen que ser el mismo.
        """
        uno = _storage(tmp_path, "uno.sqlite")
        _preparar(uno)
        dos = _storage(tmp_path, "dos.sqlite")
        _preparar(dos)

        for s in (uno, dos):
            s.record_claim(tenant_id="t", project_id="p", claim=_claim("c1", True, ORIGEN_A))
            s.record_claim(tenant_id="t", project_id="p", claim=_claim("c2", False, ORIGEN_B))

        assert uno.conflicts_for(
            tenant_id="t", project_id="p", subject_entity_id=SUJETO
        ) == dos.conflicts_for(tenant_id="t", project_id="p", subject_entity_id=SUJETO)

    def test_el_conflict_set_es_inmutable(self, tmp_path: Path) -> None:
        """Lo que sale de la consulta no se puede tocar.

        Sin esto, un `list` devuelto al llamante permitiria «arreglar» el
        conflicto que se acaba de ver —quitar la afirmacion que molesta— y el
        siguiente que lo mire veria un conflicto mas limpio que en la base.
        """
        import dataclasses

        s = _storage(tmp_path)
        _preparar(s)
        s.record_claim(tenant_id="t", project_id="p", claim=_claim("c1", True, ORIGEN_A))
        s.record_claim(tenant_id="t", project_id="p", claim=_claim("c2", False, ORIGEN_B))

        (conflicto,) = s.conflicts_for(tenant_id="t", project_id="p", subject_entity_id=SUJETO)

        with pytest.raises(dataclasses.FrozenInstanceError):
            conflicto.predicate = "otro"  # type: ignore[misc]
        with pytest.raises(AttributeError):
            conflicto.afirmaciones[0].predicate = "otro"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# R4 — lo que B27 NO hace
# ---------------------------------------------------------------------------


class TestLoQueB27NoDecide:
    def test_registrar_un_conflicto_no_lanza(self, tmp_path: Path) -> None:
        """B27 AVISA, NO PROHIBE.

        Es el limite del bloque, y es el que B28 necesita: si escribir una
        afirmacion contradictoria fuera un error, el conflict set solo podria
        existir si alguien lo construyera a mano, y entonces seria un artefacto
        humano y no una MEDIDA de lo que el sistema cree.

        **EL CONTRA SALTO ES QUE NO LANCE**, y no se mide con `Exception` —que
        pasaria tambien si lo que revantara fuera otra cosa— sino contando
        filas: si el error fuera «limpio», la segunda afirmacion no estaria
        ahi y el conflict set seria un artefacto construido a mano.
        """
        s = _storage(tmp_path)
        _preparar(s)
        s.record_claim(tenant_id="t", project_id="p", claim=_claim("c1", True, ORIGEN_A))

        # Fuentes DISTINTAS: coexisten, y por tanto forman un conflicto
        # consultable. Es el caso que B27 hace visible.
        r = s.record_claim(tenant_id="t", project_id="p", claim=_claim("c2", False, ORIGEN_B))

        assert r.conflicto is False, (
            "con dos fuentes distintas no hay overwrite: el aviso solo puede "
            "dispararse cuando el UNIQUE de la tupla natural rechaza la fila"
        )
        assert s._conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0] == 2, (
            "B27 decidio cual de las dos tiene razon: eso es B28"
        )
        assert len(s.conflicts_for(tenant_id="t", project_id="p", subject_entity_id=SUJETO)) == 1

    def test_el_overwrite_no_toca_la_fila_que_ya_esta(self, tmp_path: Path) -> None:
        """El aviso NO es una decision: la fila anterior se queda.

        Se separa del otro test porque son DOS propiedades distintas que se
        confunden con facilidad. Aqui las dos afirmaciones vienen de la MISMA
        fuente, luego el `UNIQUE` rechaza la segunda y no hay dos filas: hay
        una. B27 avisa de que la afirmacion pretendida **no** quedo escrita,
        y la que hay sigue siendo la primera.

        Es lo que hace que B29 siga teniendo trabajo: si B27 resolviera,
        habria decidido con una regla que no tiene en cuenta al que pregunta.

        **B35: `c2` PASA A SER EL MISMO `claim_id` QUE `c1`.** Con `c2` distinto
        y la misma fuente, `ADR-0035` (migracion `0008`) lo que hay son dos
        filas y NO hay nada pisado —que es justo lo que el comentario de B31 de
        este mismo test ya reconocia hace un bloque—. El aviso solo tiene
        sentido cuando de verdad se pierde una escritura, y eso lo produce el
        `UNIQUE` de la clave primaria.
        """
        s = _storage(tmp_path)
        _preparar(s)
        s.record_claim(tenant_id="t", project_id="p", claim=_claim("c1", True, ORIGEN_A))

        r = s.record_claim(tenant_id="t", project_id="p", claim=_claim("c1", False, ORIGEN_A))

        assert r.conflicto is True
        # B31/B35: lo que queda escrita es la PRIMERA, intacta. Y el aviso no
        # ha decidido cual de las dos tiene razon: solo ha dicho que la
        # segunda no llego a escribir, que es una pregunta distinta.
        guardados = [
            fila[0]
            for fila in s._conn.execute(
                "SELECT object_literal_json FROM claims ORDER BY claim_id"
            ).fetchall()
        ]
        assert guardados == ["true"], f"la fila anterior deberia seguir intacta: hay {guardados}"

    def test_el_conflicto_sobre_entidades_no_solo_sobre_literals(self, tmp_path: Path) -> None:
        """«A usa B» frente a «A usa C» tambien es un conflicto.

        Se mide porque B25 abrio la segunda forma de objeto y este bloque no
        puede mirar solo `object_literal_json`: un sistema que separase
        correctamente dos literales y tratara cualquier referencia a entidad
        como si fuera unica estaria dando por buena una afirmacion que se
        contradice con otra.
        """
        from skillgraph.knowledge.graph import entity_ref

        s = _storage(tmp_path)
        _preparar(s)
        primero = Claim(
            claim_id="e1",
            subject_entity_id=SUJETO,
            predicate="imports_module",
            object_literal=None,
            source_id=source_id(ORIGEN_A),
            object_entity=entity_ref(OTRO),
            checked_at_revision="r1",
        )
        segundo = Claim(
            claim_id="e2",
            subject_entity_id=SUJETO,
            predicate="imports_module",
            object_literal=None,
            source_id=source_id(ORIGEN_B),
            object_entity=entity_ref(SUJETO),
            checked_at_revision="r1",
        )
        s.record_claim(tenant_id="t", project_id="p", claim=primero)
        s.record_claim(tenant_id="t", project_id="p", claim=segundo)

        conflictos = s.conflicts_for(tenant_id="t", project_id="p", subject_entity_id=SUJETO)

        assert len(conflictos) == 1, "dos referencias a entidades distintas no son un conflicto"
        assert {c.claim_id for c in conflictos[0].afirmaciones} == {"e1", "e2"}

    def test_el_conflict_set_no_filtra_por_proyecto(self, tmp_path: Path) -> None:
        """Las afirmaciones de OTRO proyecto no se mezclan.

        El aislamiento por proyecto es la garantia de la que B24 y B25 han
        dependsdo; un conflict set que lo atraviesa devolveria contradicciones
        entre proyectos que jamas se comparan, y eso no es un conflicto: es
        ruido con apariencia de senal.
        """
        s = _storage(tmp_path)
        _preparar(s)
        s.upsert_entity(
            tenant_id="t",
            project_id="otro",
            entity=Entity(entity_id=SUJETO, kind="file", stable_key="a.py"),
        )
        s.record_claim(tenant_id="t", project_id="p", claim=_claim("c1", True, ORIGEN_A))
        s.record_claim(tenant_id="t", project_id="otro", claim=_claim("c2", False, ORIGEN_B))

        conflictos = s.conflicts_for(tenant_id="t", project_id="p", subject_entity_id=SUJETO)

        assert conflictos == (), (
            "el conflict set ha traeido afirmaciones de otro proyecto: "
            "el aislamiento por proyecto no es opcional"
        )


# ---------------------------------------------------------------------------
# R5 — el aviso LLEGA AL QUE PROMUEVE
# ---------------------------------------------------------------------------


class TestElAvisoLlega:
    """La propiedad de mas valor del bloque, y la que mas facil se pierde.

    Todo lo anterior ocurre dentro de la base de datos, donde es facil mirar.
    Este caso es el UNICO que mide si el aviso sale del sistema y llega a quien
    escribio, que es donde se decide si de sirve para algo.

    **UN AVISO QUE SE RECOGE Y NO SE IMPRIME ES UN AVISO QUE NO EXISTIO.** Y eso
    es exactamente lo que pasaria si `record_claim` devolviera el aviso y
    `_apply_pending_promotions` lo tirara: el sistema sabria del conflicto, la
    base lo guardaria, y el operador recibiria un `PUBLISHED` sin mas.
    """

    def test_el_reconcile_informa_del_conflicto_del_destino(self, tmp_path: Path) -> None:
        """Promover un claim que el destino ya afirmaba al reves.

        MEDIDO antes de que existiera el aviso: el resultado era un
        `PUBLISHED` y nada mas, y en destino seguia la afirmacion que ya
        habia. Quien habia promovido creia que la suya estaba ahi.
        """
        from skillgraph.cli.commands.promotion import (
            _apply_pending_promotions,
            _claim_to_payload,
            _entity_to_payload,
            _source_to_payload,
        )
        from skillgraph.governance.promotion import submit_proposal

        origen = _storage(tmp_path, "origen.sqlite")
        destino = _storage(tmp_path, "destino.sqlite")
        _preparar(origen)
        _preparar(destino)

        # El DESTINO ya tiene su propia afirmacion, y es la contraria.
        # **B35: EL `claim_id` TIENE QUE COINCIDIR.** Antes lo que se escribia
        # aqui era OTRO `claim_id` con la misma fuente, la misma revision y el
        # valor contrario, y `ADR-0035` (migracion `0008`) permitio que las dos
        # filas coexistieran — porque el `UNIQUE` lleva el objeto y `True` y
        # `False` no son el mismo hecho—. MEDIDO: con esta forma, la
        # promocion ya no encuentra conflicto y el aviso sale legitimo: el
        # destino tiene DOS afirmaciones sobre lo mismo, no UNA.
        #
        # Lo que este test debe seguir vigilando es lo que de verdad se pierde:
        # dos afirmaciones distintas con el MISMO `claim_id`, donde lo que se
        # registra es la primera y quien promovio creia haber registrado la
        # suya. Para eso coincide el `claim_id`.
        destino.record_claim(
            tenant_id="t",
            project_id="p",
            claim=_claim("c-nuevo", False, ORIGEN_A),
        )

        claim = _claim("c-nuevo", True, ORIGEN_A)
        origen.record_claim(tenant_id="t", project_id="p", claim=claim)
        submit_proposal(
            origen,
            proposal_id="p1",
            tenant_id="t",
            source_project="p",
            target_catalog="p",
            knowledge_ref="c-nuevo",
            payload={
                "source_project": "p",
                "target_project": "p",
                "source": _source_to_payload(
                    origen, tenant_id="t", project_id="p", source_id=ORIGEN_A
                ),
                "entity": _entity_to_payload(
                    origen, tenant_id="t", project_id="p", entity_id=SUJETO
                ),
                "claim": _claim_to_payload(claim),
            },
        )

        resultados = _apply_pending_promotions(origen, destino, tenant_id="t", target_project="p")
        # Se lee como lo lee el operador: el comando imprime
        # `{proposal_id}  {status}` por linea, asi que las DOS mitades cuentan.
        texto = "\n".join(f"{r['proposal_id']}  {r['status']}" for r in resultados)

        assert "CONFLICTOS" in texto, (
            f"el reconcile no informo del conflicto. Resultado: {resultados!r}. "
            "El aviso existe en la base y no sale de ella, que es lo mismo "
            "que no tenerlo."
        )
        assert "c-nuevo" in texto, "el aviso dice cuantos hay, pero no cuales"

    def test_el_reconcile_no_inventa_conflictos(self, tmp_path: Path) -> None:
        """EL CONTRA SALTO: sin conflicto, no hay linea de aviso.

        Sin este, el comando podria imprimir «0 conflictos» siempre y el
        operador dejaria de leerlo —que es como un aviso deja de servir, sin
        que nadie decida que deje de servir.
        """
        from skillgraph.cli.commands.promotion import (
            _apply_pending_promotions,
            _claim_to_payload,
            _entity_to_payload,
            _source_to_payload,
        )
        from skillgraph.governance.promotion import submit_proposal

        origen = _storage(tmp_path, "origen.sqlite")
        destino = _storage(tmp_path, "destino.sqlite")
        _preparar(origen)
        _preparar(destino)

        claim = _claim("c-nuevo", True, ORIGEN_A)
        origen.record_claim(tenant_id="t", project_id="p", claim=claim)
        submit_proposal(
            origen,
            proposal_id="p1",
            tenant_id="t",
            source_project="p",
            target_catalog="p",
            knowledge_ref="c-nuevo",
            payload={
                "source_project": "p",
                "target_project": "p",
                "source": _source_to_payload(
                    origen, tenant_id="t", project_id="p", source_id=ORIGEN_A
                ),
                "entity": _entity_to_payload(
                    origen, tenant_id="t", project_id="p", entity_id=SUJETO
                ),
                "claim": _claim_to_payload(claim),
            },
        )

        resultados = _apply_pending_promotions(origen, destino, tenant_id="t", target_project="p")
        texto = "\n".join(f"{r['proposal_id']}  {r['status']}" for r in resultados)

        assert "CONFLICTOS" not in texto, f"se invento un conflicto: {resultados!r}"
        assert "PUBLISHED" in texto, "y tampoco se publico lo que si se pudo"
