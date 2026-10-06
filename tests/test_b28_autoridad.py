"""B28 — la autoridad se decide POR INTENCION, y se puede explicar.

**LO QUE ESTE FICHERO MIDE Y POR QUE NO ES «UNA FUNCION MAS».** La fila de B28
dice que resolver un conflicto «es un ranking global». MEDIDO, no hay ranking:
no hay nada. Lo que hay es `AssertionOrigin` con cuatro valores cuyo docstring
dice, en sus propias palabras, que **no son un ranking** —son «quien afirma»—
y el orden entre ellos depende de la pregunta:

    ¿que devolvio produccion?        observed > derived-deterministically
    ¿que dependencia esta permitida?  human-asserted > derived-deterministically

La tentacion esta ARMADA, y por eso la propiedad que se mide en
`TestLaResolucionDependeDeLaPregunta` no es «se elige alguien» sino **«el mismo
conflicto, con dos intenciones, elige afirmaciones DISTINTAS»**.

# LAS CINCO MEDIDAS DEL INSTRUMENTO, Y DONDE ESTAN AQUI

    P1  intencion es vocabulario cerrado -> TestLaIntencionEsVocabularioCerrado
    P2  resuelve distinto por intencion  -> TestLaResolucionDependeDeLaPregunta
    P3  la resolucion es explicable       -> TestLaResolucionSeExplica
    P4  el agente no cierra el conflicto  -> TestElAgenteNoCierraElConflicto
    P5  determinista (CONTRA SALTO)      -> TestLaResolucionEsDeterminista
    +   sin I/O oculto (AGENTS 1.3)      -> TestElResolverNoTocaDiscoNiReloj

P5 es la que hace que las otras cuatro midan algo: un resolver que devolviera
TODAS las afirmaciones cerraria P2 y P3 sin resolver nada.
"""

from __future__ import annotations

import ast
import inspect
import os
import subprocess
import sys
import typing
from pathlib import Path

import pytest

from skillgraph.core.errors import (
    AuthorityProfileInvalido,
    PerfilIncoherenteError,
    UnknownQueryIntentError,
)
from skillgraph.knowledge.authority import (
    MOTIVOS_DESCARTE,
    PERFILES_POR_DEFECTO,
    QUERY_INTENTS,
    AuthorityProfile,
    resolver,
)
from skillgraph.knowledge.graph import Claim, Conflicto

SUJETO = "file:a.py"

#: Las siete intenciones del «ADT inicial» de 05-SPEC §3. Se escriben aqui a
#: proposito: el guard mide que las siete EXISTEN, y que `QUERY_INTENTS` esta
#: derivado del `Literal` en vez de escrito a mano.
LAS_SIETE = (
    "actual_behavior",
    "intended_behavior",
    "structural_fact",
    "historical_fact",
    "risk_assessment",
    "change_impact",
    "explanation",
)


def _claim(cid: str, valor: object, origen: str, rev: str = "r1") -> Claim:
    """Una afirmacion con su `assertion_origin`, que es el eje que se rankea."""
    return Claim(
        claim_id=cid,
        subject_entity_id=SUJETO,
        predicate="imports_module",
        object_literal=valor,
        source_id=f"local:{cid}",
        assertion_origin=origen,
        checked_at_revision=rev,
    )


def _conflicto(*afirmaciones: Claim) -> Conflicto:
    return Conflicto(
        subject_entity_id=SUJETO,
        predicate="imports_module",
        afirmaciones=tuple(sorted(afirmaciones, key=lambda c: c.claim_id)),
    )


def _el_conflicto_del_bloque() -> Conflicto:
    """El conflicto que la spec usa de ejemplo: observado contra decidido.

    MEDIDO que hacen falta dos fuentes distintas para que coexistan: el
    `UNIQUE` de `claims` lleva `source_id` dentro. Aqui los `source_id`
    derivan del `claim_id`, luego no colisionan.
    """
    return _conflicto(
        _claim("c-runtime", "sqlite3", "observed"),
        _claim("c-adr", "psycopg", "human-asserted"),
    )


# ---------------------------------------------------------------------------
# P1 — la intencion es un ADT, no un prompt libre
# ---------------------------------------------------------------------------


class TestLaIntencionEsVocabularioCerrado:
    def test_las_siete_de_la_spec_existen(self) -> None:
        assert set(LAS_SIETE) <= QUERY_INTENTS

    def test_el_conjunto_se_deriva_del_literal_y_no_se_escribe_a_mano(self) -> None:
        """Regla QW-E, la misma que `SOURCE_KINDS` y `ASSERTION_ORIGINS`.

        Un conjunto escrito a mano seria una segunda fuente de verdad: el dia
        que el `Literal` gane un valor, la validacion rechazaria el valor nuevo
        mientras el tipo lo acepta. B25 sufrio exactamente eso.
        """
        from skillgraph.knowledge.authority import QueryIntent

        assert frozenset(typing.get_args(QueryIntent)) == QUERY_INTENTS

    def test_una_intencion_inventada_sale_como_error_de_dominio(self) -> None:
        """`AGENTS.md` 1.2: nunca un `ValueError` de camino abierto.

        Y no solo el tipo: tambien el `code`, que es lo que la CLI traduce a
        exit code (WI-109). Un error sin `code` propio comparte traduccion con
        otro y deja de distinguirse.
        """
        from skillgraph.core.errors import SkillGraphError
        from skillgraph.knowledge.authority import query_intent

        with pytest.raises(SkillGraphError) as exc:
            query_intent("que_on_va_a_preguntar")
        assert isinstance(exc.value, UnknownQueryIntentError)
        assert exc.value.code == "sg_unknown_query_intent"

    def test_una_intencion_valida_se_acepta(self) -> None:
        from skillgraph.knowledge.authority import query_intent

        assert query_intent("actual_behavior") == "actual_behavior"

    def test_la_lista_de_la_spec_y_el_literal_no_se_divergen(self) -> None:
        """Si mañana el Literal crece, esta lista lo delata.

        No es un guard de «no cambies»: es un guard de «si cambias, mira lo
        que estas diciendo que son las siete». El comentario del modulo lo
        explica mejor que este nombre.
        """
        from skillgraph.knowledge.authority import QueryIntent

        declarados = set(typing.get_args(QueryIntent))
        assert declarados == set(LAS_SIETE) or declarados > set(LAS_SIETE)
        assert declarados >= set(LAS_SIETE)


# ---------------------------------------------------------------------------
# El perfil: un ranking POR INTENCION, y no uno global
# ---------------------------------------------------------------------------


class TestElPerfilDeclaraSuRanking:
    def test_una_preferencia_vacia_no_es_un_perfil(self) -> None:
        with pytest.raises(AuthorityProfileInvalido) as exc:
            AuthorityProfile(name="vacio", intencion="actual_behavior", preferencia=())
        assert exc.value.code == "sg_authority_profile_invalido"

    def test_un_origen_que_no_existe_no_pasa(self) -> None:
        with pytest.raises(AuthorityProfileInvalido):
            AuthorityProfile(
                name="inventado",
                intencion="actual_behavior",
                preferencia=("observed", "el-que-manda"),  # type: ignore[arg-type]
            )

    def test_un_origen_repetido_no_pasa(self) -> None:
        """Repetir un origen hace que el orden deje de signifcar algo."""
        with pytest.raises(AuthorityProfileInvalido):
            AuthorityProfile(
                name="repetido",
                intencion="actual_behavior",
                preferencia=("observed", "observed"),
            )

    def test_hay_un_perfil_para_cada_intencion(self) -> None:
        for intencion in LAS_SIETE:
            assert intencion in PERFILES_POR_DEFECTO, f"sin perfil para {intencion}"

    def test_los_perfiles_por_defecto_NO_son_el_mismo(self) -> None:
        """EL CONTRA SALTO DE «NO HAY RANKING GLOBAL».

        Si los siete perfiles tuvieran la misma preferencia, B28 habria
        metido un ranking global con un envoltorio de nombres, y todas las
        pruebas de arriba pasarian: habria intencion, habria perfil y habria
        ganador. Lo unico que se comprueba aqui es que **se diferencian**.
        """
        preferencias = {p.name: p.preferencia for p in PERFILES_POR_DEFECTO.values()}
        assert len(set(preferencias.values())) > 1, (
            "los siete perfiles declaran la MISMA preferencia: eso es un ranking "
            "global con nombres distintos"
        )

    def test_el_ejemplo_A_de_la_spec(self) -> None:
        """«¿Que status devolvio produccion?» -> manda lo observado."""
        p = PERFILES_POR_DEFECTO["actual_behavior"]
        assert p.preferencia.index("observed") < p.preferencia.index("human-asserted")

    def test_el_ejemplo_B_de_la_spec(self) -> None:
        """«¿Que dependencia esta permitida?» -> manda lo decidido.

        **Y ESTE ES EL CONTRA SALTO DEL CONTRA SALTO.** No basta con que los
        perfiles sean distintos: tienen que ser distintos **en el sentido que
        la spec explica**, y en direcciones opuestas. Un perfil que pusiera
        `human-asserted` el primero en todas habria \"diferenciado\" los siete
        y estaria tan mal como un ranking global.
        """
        p = PERFILES_POR_DEFECTO["intended_behavior"]
        assert p.preferencia.index("human-asserted") < p.preferencia.index("observed")

    def test_la_preferencia_es_inmutable(self) -> None:
        """`AGENTS.md` 1.1: una tupla, no una lista."""
        p = PERFILES_POR_DEFECTO["actual_behavior"]
        assert isinstance(p.preferencia, tuple)


# ---------------------------------------------------------------------------
# P2 — la propiedad del bloque
# ---------------------------------------------------------------------------


class TestLaResolucionDependeDeLaPregunta:
    def test_el_mismo_conflicto_resuelve_distinto(self) -> None:
        c = _el_conflicto_del_bloque()
        comportamiento = resolver(c, intencion="actual_behavior")
        arquitectura = resolver(c, intencion="intended_behavior")

        gano_a = tuple(x.claim_id for x in comportamiento.elegidas)
        gano_b = tuple(x.claim_id for x in arquitectura.elegidas)

        assert gano_a == ("c-runtime",)
        assert gano_b == ("c-adr",)
        assert gano_a != gano_b

    def test_cada_una_de_las_siete_intenciones_responde(self) -> None:
        """Y ninguna se queda sin respuesta por defecto."""
        c = _el_conflicto_del_bloque()
        for intencion in LAS_SIETE:
            r = resolver(c, intencion=intencion)
            assert r.intencion == intencion
            assert r.perfil, f"{intencion} resolvio sin decir que politica uso"

    def test_un_perfil_propio_cambia_la_respuesta(self) -> None:
        """El punto de extension: quien llama puede llevar SU politica.

        Sin esto, `AuthorityProfile` seria un enum con nombres y el bloque
        seria un ranking global con francs de lemmas.
        """
        c = _el_conflicto_del_bloque()
        r = resolver(
            c,
            intencion="actual_behavior",
            perfil=AuthorityProfile(
                name="el-mio",
                intencion="actual_behavior",
                preferencia=("human-asserted", "observed"),
            ),
        )
        assert tuple(x.claim_id for x in r.elegidas) == ("c-adr",)
        assert r.perfil == "el-mio"

    def test_el_perfil_tiene_que_contestar_a_la_pregunta_que_se_le_hace(self) -> None:
        """Un perfil de `intended_behavior` no puede responder a
        `actual_behavior`. Usarlo igual seria responder a una pregunta con la
        politica de otra — el defecto exacto que este bloque existe para evitar.
        """
        c = _el_conflicto_del_bloque()
        perfil_ajeno = AuthorityProfile(
            name="ajeno",
            intencion="intended_behavior",
            preferencia=("human-asserted", "observed"),
        )
        with pytest.raises(PerfilIncoherenteError) as exc:
            resolver(c, intencion="actual_behavior", perfil=perfil_ajeno)
        assert exc.value.code == "sg_perfil_autoridad_incoerente"

    def test_una_sola_afirmacion_no_es_un_ganador_con_trampa(self) -> None:
        """Un unico claim: se elige, y no hay descartadas que explicar."""
        r = resolver(
            _conflicto(_claim("c-sola", "sqlite3", "observed")), intencion="actual_behavior"
        )
        assert tuple(x.claim_id for x in r.elegidas) == ("c-sola",)
        assert r.descartadas == ()


# ---------------------------------------------------------------------------
# P3 — la resolucion es explicable (spec §8)
# ---------------------------------------------------------------------------


class TestLaResolucionSeExplica:
    def test_contesta_que_policy_uso(self) -> None:
        r = resolver(_el_conflicto_del_bloque(), intencion="actual_behavior")
        assert r.perfil == PERFILES_POR_DEFECTO["actual_behavior"].name
        assert r.intencion == "actual_behavior"

    def test_contesta_que_eligio_y_que_descarto(self) -> None:
        """Y que las dos mitades **particionan** las afirmaciones.

        Sin la particion, un resolver podria poner la misma afirmacion en las
        dos listas y seguir «explicando»: la explicacion que se contradice no
        es una explicacion.
        """
        r = resolver(_el_conflicto_del_bloque(), intencion="actual_behavior")
        elegidas = {x.claim_id for x in r.elegidas}
        descartadas = {d.afirmacion.claim_id for d in r.descartadas}
        assert elegidas == {"c-runtime"}
        assert descartadas == {"c-adr"}
        assert elegidas & descartadas == set()

    def test_cada_descarte_dice_por_que_y_con_un_motivo_cerrado(self) -> None:
        """`AGENTS.md` 1.2 aplicado a una explicación: vocabulario cerrado.

        Un motivo que es un string libre obliga a quien lo lee a adivinar, que
        es justo lo contrario de explicar.
        """
        r = resolver(_el_conflicto_del_bloque(), intencion="actual_behavior")
        motivos = [d.motivo for d in r.descartadas]
        assert motivos == ["origen_no_preferido"]
        assert set(motivos) <= MOTIVOS_DESCARTE

    def test_ganadora_devuelve_la_unica_o_none(self) -> None:
        r = resolver(_el_conflicto_del_bloque(), intencion="actual_behavior")
        assert r.ganadora is not None
        assert r.ganadora.claim_id == "c-runtime"
        assert r.sin_resolver is False

    def test_la_resolution_es_inmutable(self) -> None:
        """`AGENTS.md` 1.1: frozen y con tuplas."""
        import dataclasses

        r = resolver(_el_conflicto_del_bloque(), intencion="actual_behavior")
        assert isinstance(r.elegidas, tuple)
        assert isinstance(r.descartadas, tuple)
        with pytest.raises(dataclasses.FrozenInstanceError):
            r.intencion = "explanation"  # type: ignore[misc]

    def test_la_ganadora_no_miente_si_hay_empate(self) -> None:
        """Dos afirmaciones del MISMO origen no se pueden desempatar.

        Elegir una seria arbitrario, y un resolver que elige arbitrariamente
        es un resolver que no sabe. Dice `sin_resolver` y no escoge.
        """
        c = _conflicto(
            _claim("c-a", "sqlite3", "observed"),
            _claim("c-b", "psycopg", "observed"),
        )
        r = resolver(c, intencion="actual_behavior")
        assert r.sin_resolver is True
        assert r.ganadora is None
        assert len(r.elegidas) == 2


# ---------------------------------------------------------------------------
# P4 — el guard de inferencia de agente (spec §7)
# ---------------------------------------------------------------------------


class TestElAgenteNoCierraElConflicto:
    def test_un_agente_no_gana_por_defecto(self) -> None:
        c = _conflicto(
            _claim("c-humano", "psycopg", "human-asserted"),
            _claim("c-agente", "sqlite3", "agent-inferred"),
        )
        r = resolver(c, intencion="actual_behavior")
        assert tuple(x.claim_id for x in r.elegidas) == ("c-humano",)
        motivos = {d.afirmacion.claim_id: d.motivo for d in r.descartadas}
        assert motivos["c-agente"] == "cerrado_por_agente_no_permitido"

    def test_el_guard_no_depende_del_orden_de_la_tupla(self) -> None:
        """POR QUE ES UN GUARD Y NO UNA POSICION EN LA LISTA.

        Si bastara con que `agent-inferred` fuera el ultimo de la preferencia,
        el guard se romperia **reordenando una lista** — que es el cambio mas
        barato que puede hacer quien no sabe lo que hace. Y en el perfil
        equivocado, el agente ganaria.

        Aqui se prueba justo eso: un perfil que pone al agente PRIMERO, y el
        agente sigue sin ganar.
        """
        c = _conflicto(
            _claim("c-humano", "psycopg", "human-asserted"),
            _claim("c-agente", "sqlite3", "agent-inferred"),
        )
        r = resolver(
            c,
            intencion="actual_behavior",
            perfil=AuthorityProfile(
                name="agente-primero",
                intencion="actual_behavior",
                preferencia=("agent-inferred", "observed", "human-asserted"),
            ),
        )
        assert all(x.assertion_origin != "agent-inferred" for x in r.elegidas)

    def test_si_solo_hay_agentes_no_hay_ganadora(self) -> None:
        """Y el motivo es el del guard, no «no encontrado»."""
        c = _conflicto(
            _claim("c-agente-1", "sqlite3", "agent-inferred"),
            _claim("c-agente-2", "psycopg", "agent-inferred"),
        )
        r = resolver(c, intencion="actual_behavior")
        assert r.elegidas == ()
        assert r.ganadora is None
        assert r.sin_resolver is True
        assert {d.motivo for d in r.descartadas} == {"cerrado_por_agente_no_permitido"}

    def test_el_opt_in_es_explicito_y_auditable(self) -> None:
        """Se puede permitir, pero hay que DECIRLO.

        Un flag con default `False` es auditable: quien lo pone en `True` deja
        una linea que dice que en ESTA politica un agente puede cerrar.
        """
        c = _conflicto(
            _claim("c-humano", "psycopg", "human-asserted"),
            _claim("c-agente", "sqlite3", "agent-inferred"),
        )
        r = resolver(
            c,
            intencion="actual_behavior",
            perfil=AuthorityProfile(
                name="con-agente",
                intencion="actual_behavior",
                preferencia=("agent-inferred", "observed"),
                permitir_inferencia_de_agente=True,
            ),
        )
        assert tuple(x.claim_id for x in r.elegidas) == ("c-agente",)

    def test_ningun_perfil_por_defecto_lo_permite(self) -> None:
        """El opt-in es de quien escribe la politica, no del modulo."""
        for nombre, p in PERFILES_POR_DEFECTO.items():
            assert p.permitir_inferencia_de_agente is False, nombre


# ---------------------------------------------------------------------------
# P5 — el CONTRA SALTO: determinista y sin depender del orden
# ---------------------------------------------------------------------------


class TestLaResolucionEsDeterminista:
    def test_dos_llamadas_dan_lo_mismo(self) -> None:
        c = _el_conflicto_del_bloque()
        assert (
            resolver(c, intencion="actual_behavior").firma
            == resolver(c, intencion="actual_behavior").firma
        )

    def test_el_orden_de_entrada_no_cambia_la_respuesta(self) -> None:
        """B27 garantiza `afirmaciones` ordenado; B28 no puede depender de eso.

        Si dependiera, basta reordenar la tupla para que responda distinto, y
        eso es un resolver que no sabe. Se mide invirtiendo la entrada.

        **Y SE COMPARA LA `firma`, NO LA `Resolution`.** La `Resolution` lleva
        `conflicto` —la entrada— dentro, y dos entradas con las afirmaciones
        en distinto orden son dos objetos distintos por `__eq__` aunque
        decidan identico. Compararlos seria medir el eco en vez de la
        decision, que es justo la confusion que P5 existe para cazar.
        """
        c = _el_conflicto_del_bloque()
        invertido = Conflicto(
            subject_entity_id=c.subject_entity_id,
            predicate=c.predicate,
            afirmaciones=tuple(reversed(c.afirmaciones)),
        )
        assert (
            resolver(invertido, intencion="actual_behavior").firma
            == resolver(c, intencion="actual_behavior").firma
        )

    def test_la_consulta_real_no_depende_del_orden_de_sqlite(self) -> None:
        """La mitad que no se puede simular: leer de verdad dos veces.

        Invertir la tupla en memoria prueba el resolver. Esto prueba que lo
        que llega desde `conflicts_for` —que B27 ordeno— llega igual, y que el
        resolver no reordena por su cuenta de forma distinta.
        """
        import tempfile

        from skillgraph.knowledge.graph import Entity, Source, source_id
        from skillgraph.platform.storage import Storage

        with tempfile.TemporaryDirectory() as tmp:
            s = Storage(Path(tmp) / "x.sqlite")
            s.upsert_entity(
                tenant_id="t",
                project_id="p",
                entity=Entity(entity_id=SUJETO, kind="file", stable_key="a.py"),
            )
            for sid in ("local:runtime.log", "local:adr-0042.md"):
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
                        checked_at="2026-10-06T00:00:00Z",
                        freshness="current",
                    ),
                )
            s.record_claim(
                tenant_id="t",
                project_id="p",
                claim=Claim(
                    claim_id="c-runtime",
                    subject_entity_id=SUJETO,
                    predicate="imports_module",
                    object_literal="sqlite3",
                    source_id="local:runtime.log",
                    assertion_origin="observed",
                ),
            )
            s.record_claim(
                tenant_id="t",
                project_id="p",
                claim=Claim(
                    claim_id="c-adr",
                    subject_entity_id=SUJETO,
                    predicate="imports_module",
                    object_literal="psycopg",
                    source_id="local:adr-0042.md",
                    assertion_origin="human-asserted",
                ),
            )
            uno = s.conflicts_for(tenant_id="t", project_id="p", subject_entity_id=SUJETO)
            dos = s.conflicts_for(tenant_id="t", project_id="p", subject_entity_id=SUJETO)
            s.close()

        assert uno == dos
        assert (
            resolver(uno[0], intencion="actual_behavior").firma
            == resolver(dos[0], intencion="actual_behavior").firma
        )


# ---------------------------------------------------------------------------
# Sin I/O oculto (AGENTS.md 1.3)
# ---------------------------------------------------------------------------


class TestElResolverNoTocaDiscoNiReloj:
    def test_el_modulo_no_importa_la_plataforma(self) -> None:
        """La politica es PURA: sin `Storage`, sin reloj, sin disco.

        Por AST y no por lectura: la propiedad es «este modulo no depende de
        la plataforma», y leer los imports cuenta la forma en vez de medir la
        dependencia — que es justo la confusion de WI-112 con el docstring de
        `now_iso`.
        """
        mod = ast.parse(Path(inspect.getfile(resolver)).read_text(encoding="utf-8"))
        importados = set()
        for nodo in ast.walk(mod):
            if isinstance(nodo, ast.Import):
                importados |= {a.name for a in nodo.names}
            elif isinstance(nodo, ast.ImportFrom) and nodo.module:
                importados.add(nodo.module)
        prohibidos = {"skillgraph.platform", "sqlite3", "pathlib", "os", "datetime"}
        assert not (importados & prohibidos), sorted(importados & prohibidos)

    def test_no_se_llama_al_reloj(self) -> None:
        """El reloj se inyecta (AGENTS.md 1.4); aqui ni se lee."""
        texto = Path(inspect.getfile(resolver)).read_text(encoding="utf-8")
        assert "now(" not in texto


# ---------------------------------------------------------------------------
# La superficie: el modulo se declara, o no existe (B10)
# ---------------------------------------------------------------------------


class TestLaSuperficieDeclaraLoQueB28Aade:
    """B10: una superficie que no se declara no es una superficie.

    **Y POR QUE ESTE GUARD MIRA LA SUPERFICIE DE LA CLI Y NO LA DEL NUCLE.**
    Lo que B28 anade al nucleo son **tres errores**, y esos si entran en
    `core-surface.json`. Los ADTs —`QueryIntent`, `AuthorityProfile`,
    `Resolution`— **no**, y no por olvido: viven en `knowledge/`, y declararlos
    en `skillgraph.core` invertiria la dependencia. Un modulo que conoce a
    quien lo importa.

    Lo que si es superficie publica de B28 es el comando, y ese es el que se
    vigila aqui.
    """

    def test_el_subcomando_esta_declarado(self) -> None:
        import json

        raiz = Path(__file__).resolve().parent.parent
        superficie = json.loads((raiz / "surfaces" / "cli-surface.json").read_text("utf-8"))
        assert "resolve" in superficie["subcomandos"]["knowledge"]

    def test_el_handler_esta_en_el_all_del_runner(self) -> None:
        """ADR-0018 declara `runner.__all__` estable: sin esto, ADR-0018
        declara una superficie que no es la real."""
        import json

        raiz = Path(__file__).resolve().parent.parent
        superficie = json.loads((raiz / "surfaces" / "cli-surface.json").read_text("utf-8"))
        assert "cmd_knowledge_resolve" in superficie["runner_all"]

    def test_los_tres_errores_nuevos_estan_en_la_superficie_del_nucleo(self) -> None:
        """Los errores si son de `core/`, y un error sin declarar no existe
        como contrato: el `code` es la clave con la que la CLI traduce a exit
        code (WI-109), y una traduccion que no esta declarada no esta firmada.
        """
        import json

        raiz = Path(__file__).resolve().parent.parent
        superficie = json.loads((raiz / "surfaces" / "core-surface.json").read_text("utf-8"))
        for nombre in (
            "UnknownQueryIntentError",
            "AuthorityProfileInvalido",
            "PerfilIncoherenteError",
        ):
            assert nombre in superficie["superficie"], nombre


# ---------------------------------------------------------------------------
# La CLI: quien pregunta, y le contestan (AGENTS.md 6.4)
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


def _proyecto_con_conflicto(tmp_path: Path) -> tuple[Path, Path]:
    """Un proyecto real, con un conflicto real escrito en su base."""
    data_root = tmp_path / "sg-data"
    assert _run_cli("init", cwd=tmp_path, data_root=data_root).returncode == 0
    r = _run_cli("project", "create", "demo", cwd=tmp_path, data_root=data_root)
    assert r.returncode == 0, r.stderr

    from skillgraph.cli.support import ProjectResolver
    from skillgraph.knowledge.graph import Entity, Source, source_id
    from skillgraph.platform.storage import Storage

    encontrado = ProjectResolver(data_root=data_root).with_default_root().lookup("demo")
    proyecto, err = encontrado
    assert err is None, err
    db = Path(proyecto["db_path"])
    s = Storage(db)
    s.upsert_entity(
        tenant_id="default",
        project_id="demo",
        entity=Entity(entity_id=SUJETO, kind="file", stable_key="a.py"),
    )
    for sid in ("local:runtime.log", "local:adr-0042.md"):
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
                checked_at="2026-10-06T00:00:00Z",
                freshness="current",
            ),
        )
    s.record_claim(
        tenant_id="default",
        project_id="demo",
        claim=Claim(
            claim_id="c-runtime",
            subject_entity_id=SUJETO,
            predicate="imports_module",
            object_literal="sqlite3",
            source_id="local:runtime.log",
            assertion_origin="observed",
        ),
    )
    s.record_claim(
        tenant_id="default",
        project_id="demo",
        claim=Claim(
            claim_id="c-adr",
            subject_entity_id=SUJETO,
            predicate="imports_module",
            object_literal="psycopg",
            source_id="local:adr-0042.md",
            assertion_origin="human-asserted",
        ),
    )
    s.close()
    return tmp_path, data_root


class TestLaCliPreguntaYLeContestan:
    def test_la_misma_pregunta_da_una_respuesta(self, tmp_path: Path) -> None:
        cwd, data_root = _proyecto_con_conflicto(tmp_path)
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
        assert "c-runtime" in r.stdout
        assert "c-adr" in r.stdout
        assert "actual_behavior" in r.stdout

    def test_cambiar_de_pregunta_cambia_la_respuesta(self, tmp_path: Path) -> None:
        """El contrato de B28 por fuera: dos flags, dos Winners distintos."""
        cwd, data_root = _proyecto_con_conflicto(tmp_path)
        a = _run_cli(
            "knowledge",
            "resolve",
            "demo",
            SUJETO,
            "--intent",
            "actual_behavior",
            cwd=cwd,
            data_root=data_root,
        )
        b = _run_cli(
            "knowledge",
            "resolve",
            "demo",
            SUJETO,
            "--intent",
            "intended_behavior",
            cwd=cwd,
            data_root=data_root,
        )
        assert a.returncode == 0 and b.returncode == 0
        primera = [ln for ln in a.stdout.splitlines() if "gana" in ln]
        segunda = [ln for ln in b.stdout.splitlines() if "gana" in ln]
        assert primera and segunda and primera[0] != segunda[0]

    def test_una_intencion_inventada_no_sale_como_traceback(self, tmp_path: Path) -> None:
        """WI-109: la entrada del usuario mal formada no escapa como traceback."""
        cwd, data_root = _proyecto_con_conflicto(tmp_path)
        r = _run_cli(
            "knowledge",
            "resolve",
            "demo",
            SUJETO,
            "--intent",
            "por_donde_te_he_visto",
            cwd=cwd,
            data_root=data_root,
        )
        assert r.returncode != 0
        assert "Traceback" not in r.stderr
        assert "sg_unknown_query_intent" in r.stderr

    def test_un_sujeto_sin_conflicto_no_inventa_uno(self, tmp_path: Path) -> None:
        cwd, data_root = _proyecto_con_conflicto(tmp_path)
        r = _run_cli(
            "knowledge",
            "resolve",
            "demo",
            "file:no-existe.py",
            "--intent",
            "actual_behavior",
            cwd=cwd,
            data_root=data_root,
        )
        assert r.returncode == 0, r.stderr
        assert "sin conflicto" in r.stdout
