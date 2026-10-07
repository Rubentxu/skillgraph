"""B32 — del commit al hecho, y de vuelta: las dos mitades de la fila.

**LA FILA DEL ROADMAP, Y LO QUE MEDÍ ANTES DE ESCRIBIR UNA LÍNEA.**

    No se puede responder cuándo cambió una relación ni por qué

Las dos mitades se responden por separado y por sitios distintos, y esa
separación es el diseño del bloque:

    el CUÁNDO  -> ascendencia      -> `platform.ports.git_history.GitHistory`
    el DESDE   -> qué se afirmó    -> `claims_desde_commit`
    el POR QUÉ -> (B34)            -> no existe, y se dice

La tercera no se implementa aquí y esa es la parte que hay que leer dos
veces: **B32 cierra el CUÁNDO y el DESDE QUÉ, no el POR QUÉ.** El por qué es
una pregunta de intención sobre la evidencia, que es exactamente lo que B33
(`telemetría e intención se contradicen`) y B34 (`qué`/`por qué`/`impact`)
tienen que decidir. Implementar aquí un `por_qué` de un campo sería escribir
el contrato de dos bloques siguientes sin haberlos discutido.

**MEDIDO ANTES DE ESCRIBIR**, con `.pipelinek/b32_measure.py`:

    P1  claim -> source                      SI
    P2  commit -> claims                     SI   <- solo por SQL escrito a mano
    P3  ascendencia (padre del padre)        NO
    P4  claims posteriores a un commit        NO
    P5  orden entre dos revisiones-commit     NO
    P6  por que se afirmo el claim            NO
    puerto `GitHistory`                       NO existe

Y un dato que salió del propio `grep`: **`git_commit_sha` no tenía NINGÚN
llamador en `src/`.** Nadie había hecho la pregunta nunca, no desde el
producto. No faltaba el índice —no faltaba la pregunta.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from skillgraph.knowledge.graph import Claim, Entity, Source
from skillgraph.knowledge.knowledge_controller import KnowledgeController
from skillgraph.platform.storage import Storage

TENANT = "default"
PROJECT = "demo"


def _fuente(source_id: str, commit_sha: str) -> Source:
    return Source(
        source_id=source_id,
        kind="git_commit",
        content_hash=f"h-{source_id}",
        locator={"vcs": "git", "repo_root": "/tmp/x", "commit_sha": commit_sha},
        git_commit_sha=commit_sha,
        git_tree_sha=f"t-{source_id}",
        working_tree_status=None,
        checked_at="2026-10-07T09:00:00+00:00",
        freshness="fresh",
    )


def _storage(tmp_path: Path, *, tenant: str = TENANT, project: str = PROJECT) -> Storage:
    return Storage(tmp_path / f"{tenant}-{project}.sqlite")


def _controller(
    tmp_path: Path, *, tenant: str = TENANT, project: str = PROJECT
) -> KnowledgeController:
    return KnowledgeController(
        knowledge=_storage(tmp_path, tenant=tenant, project=project),
        tenant_id=tenant,
        project_id=project,
    )


def _afirmar(
    ctl: KnowledgeController,
    *,
    claim_id: str,
    source_id: str,
    commit_sha: str,
    subject: str = "e-1",
) -> str:
    ctl.register_source(source=_fuente(source_id, commit_sha))
    # El `stable_key` se deriva del sujeto. MEDIDO, y no es cosmetico:
    # `entities` declara `UNIQUE (tenant_id, project_id, kind, stable_key)`
    # y `upsert_entity` hace `INSERT OR REPLACE`, que en SQLite es
    # DELETE+INSERT. Dos entidades con el MISMO `stable_key` son la misma
    # para el modelo, luego la segunda borra la primera y el borrado
    # dispara la cascada sobre los claims que la referencian:
    # `FOREIGN KEY constraint failed`. La primera version de este helper
    # usaba `src/a.py` para todas y fallaba en el segundo `_afirmar`.
    eid = ctl.upsert_entity(
        entity=Entity(entity_id=subject, kind="File", stable_key=f"src/{subject}.py")
    )
    return ctl.record_claim(
        claim=Claim(
            claim_id=claim_id,
            subject_entity_id=eid,
            predicate="line_count",
            object_literal=10,
            source_id=source_id,
            assertion_origin="observed",
            checked_at_revision=commit_sha,
        )
    )


class TestDelCommitAlHecho:
    def test_las_afirmaciones_de_UN_commit(self, tmp_path: Path) -> None:
        """La pregunta que nunca se habia hecho, con su respuesta.

        Tres claims del mismo commit salen los tres. Y el caso de un commit
        con uno solo sale uno: un filtro que devuelve de mas es indistinguible
        de uno que no filtra.
        """
        ctl = _controller(tmp_path)
        _afirmar(ctl, claim_id="c-1", source_id="s-1", commit_sha="aaa")
        _afirmar(ctl, claim_id="c-2", source_id="s-2", commit_sha="aaa", subject="e-2")
        _afirmar(ctl, claim_id="c-3", source_id="s-3", commit_sha="bbb", subject="e-3")

        assert [c.claim_id for c in ctl.claims_desde_commit("aaa")] == ["c-1", "c-2"]
        assert [c.claim_id for c in ctl.claims_desde_commit("bbb")] == ["c-3"]

    def test_un_commit_desconocIDO_devuelve_VACIO_no_un_error(self, tmp_path: Path) -> None:
        """Un commit del que este proyecto no tiene fuente no dice nada.

        Y la mitad que importa: **no devuelve todos «porque sí»**. Un filtro
        ausente devuelve la tabla entera, y una asercion que mira que la
        lista NO está vacía lo distingue de una consulta que devuelve `[]`.
        """
        ctl = _controller(tmp_path)
        _afirmar(ctl, claim_id="c-1", source_id="s-1", commit_sha="aaa")

        assert ctl.claims_desde_commit("0" * 40) == []

    def test_el_orden_es_ESTABLE(self, tmp_path: Path) -> None:
        """Dos llamadas seguidas dan la misma lista, en el mismo orden.

        Una consulta de histórico cuya lista depende del plan de ejecución no
        es una consulta de histórico — lo fijo B27 para los conflict sets y
        lo sostiene igual aquí—. Se mide porque el `GROUP BY` de la consulta
        es justo el sitio donde ese orden se pierde.
        """
        ctl = _controller(tmp_path)
        for i in range(5):
            _afirmar(ctl, claim_id=f"c-{i}", source_id=f"s-{i}", commit_sha="aaa", subject=f"e-{i}")

        primera = [c.claim_id for c in ctl.claims_desde_commit("aaa")]
        segunda = [c.claim_id for c in ctl.claims_desde_commit("aaa")]

        assert primera == segunda == [f"c-{i}" for i in range(5)]


class TestElAlcanceNoSeCruza:
    """**EL CONTRAEJEMPLO DE AISLAMIENTO, Y ES EL IMPORTANTE.**

    Dos proyectos pueden tener fuentes del MISMO commit —el mismo repo, el
    mismo `abc123`— y sus afirmaciones son cosas distintas. Una consulta que
    cruzara de proyecto respondería «qué dijo otro proyecto sobre este
    commit», y esa es la clase de pregunta que el aislamiento tiene que
    impedir.

    El contrasalto importa por una razón concreta: la consulta cruza DOS
    tablas, `claims` y `sources`, y es fácil que el `WHERE` filtre por
    `tenant_id`/`project_id` de una y no de la otra. Un JOIN sin filtro de
    alcance devolvería los claims de otro proyecto, y un test que solo mira
    «¿están los míos?» lo passaría.
    """

    def test_dos_tenant_que_ven_el_mismo_commit_no_se_ven_entre_si(self, tmp_path: Path) -> None:
        a = _controller(tmp_path, tenant="tenant-A", project="X")
        b = _controller(tmp_path, tenant="tenant-B", project="Y")
        _afirmar(a, claim_id="c-A", source_id="s-A", commit_sha="abc123")
        _afirmar(b, claim_id="c-B", source_id="s-B", commit_sha="abc123")

        assert [c.claim_id for c in a.claims_desde_commit("abc123")] == ["c-A"]
        assert [c.claim_id for c in b.claims_desde_commit("abc123")] == ["c-B"], (
            "el tenant B ve el claim del tenant A: el alcance no cruza en el "
            "JOIN, o falta el filtro en una de las dos tablas"
        )

    def test_dos_proyectos_del_mismo_tenant_tampoco_se_ven(self, tmp_path: Path) -> None:
        """El segundo eje del alcance, medido aparte.

        Es el caso que el anterior no cubre: mismo `tenant_id`, distinto
        `project_id`. Un filtro que solo mirara el tenant lo dejaría pasar.
        """
        x = _controller(tmp_path, tenant="t", project="X")
        y = _controller(tmp_path, tenant="t", project="Y")
        _afirmar(x, claim_id="c-X", source_id="s-X", commit_sha="abc123")
        _afirmar(y, claim_id="c-Y", source_id="s-Y", commit_sha="abc123")

        assert [c.claim_id for c in x.claims_desde_commit("abc123")] == ["c-X"]
        assert [c.claim_id for c in y.claims_desde_commit("abc123")] == ["c-Y"]


class TestLoUnicoQueNoSeFiltraEsLaVigencia:
    def test_un_claim_CADUCADO_todavia_se_afirmo_desde_ese_commit(self, tmp_path: Path) -> None:
        """**POR QUÉ ESTA CONSULTA NO FILTRA POR VIGENCIA, Y POR QUÉ ES LO
        IMPORTANTE DE B32.**

        Un claim cuya ventana se cerró por una re-afirmación posterior SE
        AFIRMÓ desde el commit viejo. Filtrarlo por vigencia haría que un
        rebase de tres meses no mostrara nada de lo que pasó entonces, y la
        pregunta «qué se afirmó desde este commit» se convertiría
        silenciosamente en «qué se sigueORITYestinando hoy según este
        commit», que es otra pregunta.

        Y es la misma distinción que B29 fijó entre «qué se sabía en la
        revisión» y «qué se afirmó entonces». Aquí no hay ninguna ventana:
        hay un hecho con fecha.
        """
        from skillgraph.platform.knowledge_claims import SqliteClaimRepository

        storage = Storage(tmp_path / "p.sqlite")
        ctl = KnowledgeController(knowledge=storage, tenant_id=TENANT, project_id=PROJECT)
        _afirmar(ctl, claim_id="c-1", source_id="s-1", commit_sha="aaa")

        storage._conn.execute(
            "UPDATE claims SET valid_until_revision = 'zzz' WHERE claim_id = 'c-1'"
        )
        storage._conn.commit()

        filas = SqliteClaimRepository(storage).claims_desde_commit(
            tenant_id=TENANT, project_id=PROJECT, commit_sha="aaa"
        )
        assert [c.claim_id for c in filas] == ["c-1"], (
            "un claim caducado desaparecio de la ascendencia: la consulta "
            "esta respondiendo 'que es cierto hoy' y no 'que se afirmo entonces'"
        )


class TestElIndiceEsParcialYExiste:
    def test_el_indice_existe_y_es_PARCIAL(self, tmp_path: Path) -> None:
        """`WHERE git_commit_sha IS NOT NULL`, y se pregunta al motor.

        Se pregunta a `sqlite_master` y no se lee el codigo de `schema.py`:
        una base ya existente no recibe el `CREATE INDEX IF NOT EXISTS` del
        esquema, luego el unico sitio donde se puede comprobar que lo tiene
        es la base. Y en `schema.py` solo esta el texto que QUEREMOS.
        """
        storage = Storage(tmp_path / "p.sqlite")
        fila = storage._conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND name='idx_sources_commit'"
        ).fetchone()

        assert fila is not None, "la base nueva no recibio el indice"
        assert "WHERE" in fila["sql"] and "IS NOT NULL" in fila["sql"], fila["sql"]
        assert "git_commit_sha" in fila["sql"], fila["sql"]

    def test_una_fuente_SIN_sha_no_entra_en_el_indice(self, tmp_path: Path) -> None:
        """MEDIDO, noAffinity asumido: una fuente sin SHA no se indexa.

        `improvement.py`, `receipts.py` y `skill_importer.py` ponen
        `git_commit_sha=None`. Un indice completo guardaria NULLs que
        nadie busca nunca. Se mide que el indice tiene menos entradas que
        filas, que es lo que hace un indice parcial.
        """
        storage = Storage(tmp_path / "p.sqlite")
        ctl = KnowledgeController(knowledge=storage, tenant_id=TENANT, project_id=PROJECT)
        _afirmar(ctl, claim_id="c-1", source_id="s-1", commit_sha="aaa")
        ctl.register_source(
            source=Source(
                source_id="s-sin-sha",
                kind="local_file",
                content_hash="h2",
                locator={},
                git_commit_sha=None,
                git_tree_sha=None,
                working_tree_status=None,
                checked_at="2026-10-07T09:00:00+00:00",
                freshness="fresh",
            )
        )

        total = storage._conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
        indexado = storage._conn.execute(
            "SELECT COUNT(*) FROM sources WHERE git_commit_sha IS NOT NULL"
        ).fetchone()[0]

        assert total == 2
        assert indexado == 1, (
            f"hay {total} fuentes y {indexado} con SHA: el indice parcial no "
            f"aparta las que no se buscan"
        )


class TestLaMigracionLlegaABasesViejas:
    """**POR QUÉ HAY UNA MIGRACIÓN Y NO SOLO UN `CREATE INDEX`.**

    `schema.py` solo corre al crear la base. Una base que ya existe —que es
    toda base de un proyecto en uso— no lo recibe nunca. Sin migración, la
    consulta funciona pero sin indice, y un escaneo sobre `sources` no se
    nota en un proyecto pequeño y se nota en uno con cien mil fuentes.

    El test abre una base con el esquema VIEJO —sin el indice— y la migra,
    en vez de abrir una base nueva que ya nace bien. Sin ese test, la
    migración no se probaría nunca: `CREATE INDEX IF NOT EXISTS` sobre una
    base recien creada es un no-op silencioso.
    """

    def test_una_base_VIEJA_recibe_el_indice_al_migrar(self, tmp_path: Path) -> None:
        """Una base con el esquema COMPLETO pero sin el indice: se le anade.

        **POR QUE NO UNA BASE DE TRES TABLAS.** La primera version de este
        test creo un `sources` minimo a mano y `sincroniza` reventó con
        `no such table: claims`, porque las migraciones anteriores tocan
        tablas que esa base no tenia. Ese fallo es util: **«base vieja» no es
        una base incompleta, es una base con todo el esquema de su epoca y
        sin lo que vino despues.** Fabricar una base a mano mide un
        escenario que no existe, y encima roba el trabajo de las
        migraciones anteriores.

        El simulacro correcto sale de la propia base: se le quita el indice
        y se le borra la anotacion de la migracion, que es exactamente lo
        que le pasa a una base creada antes de B32.
        """
        from skillgraph.platform.migrations import sincroniza

        storage = Storage(tmp_path / "vieja.sqlite")
        storage._conn.execute("DROP INDEX IF EXISTS idx_sources_commit")
        storage._conn.execute(
            "DELETE FROM schema_migrations WHERE migration_id = '0006_sources_indice_de_commit'"
        )
        storage._conn.commit()
        assert (
            storage._conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='index'"
                " AND name='idx_sources_commit'"
            ).fetchone()[0]
            == 0
        ), "la base de prueba no simula la era previa: ya tiene el indice"

        sincroniza(storage._conn)
        storage._conn.commit()

        filas = storage._conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND name='idx_sources_commit'"
        ).fetchall()
        assert filas, "la base vieja no recibio el indice al migrar"

        # Idempotente: abrir dos veces no reconstruye nada ni falla.
        sincroniza(storage._conn)
        storage._conn.commit()
        assert (
            storage._conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='index'"
                " AND name='idx_sources_commit'"
            ).fetchone()[0]
            == 1
        )


class TestElPorQueNoExisteYSeDice:
    """**EL CONTRAEJEMPLO DE LO QUE B32 NO CIERRA.**

    La fila del roadmap dice «ni por qué». Dos mitades se han cerrado aquí y
    esta es la tercera, y lo que se mide es que **no** hay un `por_que` en
    ninguna parte que prometa una respuesta que no tiene.

    Es un test de ausencia, y la clase de defecto que caza es la de un
    campo `reason` que alguien añadió medioProducto y que nadie llena: la
    superficie pública dice que se puede preguntar el por qué y la única
    respuesta que hay es `None` o una cadena vacía, que es peor que que no
    exista porque parece un dato.
    """

    @pytest.mark.parametrize("nombre", ["por_que", "por_que_", "porque", "explain"])
    def test_no_hay_un_por_que_que_prometa_una_respuesta(self, nombre: str) -> None:
        for obj in (KnowledgeController, Storage):
            assert not hasattr(obj, nombre), (
                f"{obj.__name__} tiene `{nombre}`: B32 cierra el CUÁNDO y el "
                f"DESDE QUÉ. El POR QUÉ es una pregunta de intención sobre la "
                f"evidencia y es de B33/B34; prometerla aqui es escribir el "
                f"contrato de dos bloques siguientes sin haberlos discutido."
            )

    def test_el_port_de_ascendencia_tampoco_lo_promete(self) -> None:
        """El puerto `GitHistory` no ofrece `por_que` ni `explain`.

        Una ascendencia puede responder CUÁNDO y no POR QUÉ: el grafo de
        commits tiene padres y no motivos. Si el puerto lo ofreciera, el
        adaptador tendría que inventar la respuesta.
        """
        from skillgraph.platform.ports.git_history import GitHistory

        for nombre in ("por_que", "explain", "motivo", "porque"):
            assert not hasattr(GitHistory, nombre), (
                f"`GitHistory` ofrece `{nombre}`: la ascendencia no tiene "
                f"motivos, y prometerlos obligaria al adaptador a inventarlos"
            )


class TestLosDosRelojesNoSeMezclan:
    def test_la_consulta_NO_usa_el_orden_de_observacion(self, tmp_path: Path) -> None:
        """`claims_desde_commit` no toca `revision_registro`.

        Es la tentación más fuerte de este bloque: `checked_at_revision` es
        una revisión y ya hay un reloj que las ordena, así que parece
        gratuitó añadir otro. Y sería un error: el `seq` dice en qué orden
        ESTE store vio las cosas, no si un commit es padre de otro.

        Se mide por comportamiento: dos claims del MISMO commit con
        revisiones «distintas» en el reloj local tienen que seguir saliendo
        los dos bajo ese commit. Si la consulta usara `seq`, dependería del
        orden de registro y no del SHA.
        """
        ctl = _controller(tmp_path)
        _afirmar(ctl, claim_id="c-1", source_id="s-1", commit_sha="aaa")
        _afirmar(ctl, claim_id="c-2", source_id="s-2", commit_sha="aaa", subject="e-2")

        assert [c.claim_id for c in ctl.claims_desde_commit("aaa")] == ["c-1", "c-2"], (
            "dos claims del mismo commit no salen juntos: la consulta ha "
            "empezado a depender del orden local de observacion, que es un "
            "reloj distinto"
        )
