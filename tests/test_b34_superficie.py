"""B34 — Una superficie de consulta, y que la usen TODAS.

**LO QUE SE MEDIO ANTES DE ESCRIBIR UNA LINEA.** De las seis consultas del
roadmap:

```
what      SI  — list_claims_for_subject
changed   SI  — claims_at_revision (B29), claims_desde_commit (B32)
conflicts SI  — conflicts_for (B27) + resolver (B28)
evidence  SI  — get_evidences_for_claim
impact    SI en Storage, NO en el Protocol — list_claims_by_object_entity (B25)
why       NO  — composicion de tres lecturas que ya existen

sg.knowledge.query   CONSULTAS = {"claims", "resource"}  -> de las seis, NINGUNA
MCP                  0 ficheros, 0 menciones
```

Cinco de las seis ya existian y la sexta era composicion. **B34 no es un
bloque de consultas: es un bloque de superficie.** Lo que faltaba no era
poder responder, sino un modelo unico que las nombre.

El gate del roadmap —«las mismas query models alimentan CLI y MCP/agent
handoff; ninguna superficie reconstruye autoridad o retrieval por su
cuenta»— es bueno, a diferencia del de B33. Y aqui hay algo que B33 no
tenia: **MCP no existe**, luego la mitad del gate «MCP/agent handoff» se
sustituye por el handoff real, que es la capability. Se declara abajo.

Las propiedades, y donde estan:

    P1  las seis son un ADT cerrado        -> TestLasSeisSonVocabularioCerrado
    P2  EL GATE: una sola superficie       -> TestUnaSolaSuperficieParaTodas
    P3  `why` es procedencia               -> TestWhyRespondeProcedencia
    P4  `impact` es la arista INVERSA      -> TestImpactEsLaAristaInversa
    P5  `what` NO jerarquiza               -> TestWhatNoResuelveNiSeResuelve
    P6  `conflicts` sin intencion          -> TestConflictosSinIntencionNoResuelven
    P7  los dos relojes siguen siendo dos  -> TestLosDosRelojesNoSeTraducen
    P8  las seis devuelven la MISMA forma  -> TestLasSeisDevuelvenLaMismaForma
    P9  vacio y ausente son cosas distintas-> TestVacioYAusenteNoSonLoMismo
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
import typing
from pathlib import Path

import pytest

from skillgraph.core.errors import ValidationError
from skillgraph.knowledge.authority import resolver
from skillgraph.knowledge.graph import Claim, Entity, EntityRef, Source, source_id
from skillgraph.knowledge.superficie import (
    CONSULTAS,
    PREGUNTA,
    Consulta,
    Procedencia,
    Respuesta,
    SuperficieConocimiento,
    pregunta,
    respuesta_a_payload,
)
from skillgraph.platform.storage import Storage

REPO = Path(__file__).resolve().parents[1]
SUJETO = "file:a.py"
OBJETO = "file:b.py"
ADY = "adr:0042"
RT = "runtime:ventana-1"


def _storage(tmp_path: Path, nombre: str = "b34.sqlite") -> Storage:
    return Storage(tmp_path / nombre)


def _poblar(s: Storage, tenant_id: str = "t", project_id: str = "p") -> None:
    """Un ADR que dice `psycopg` y un runtime que dice `sqlite3`.

    Es el par que B28 uso como ejemplo y B33 como vertical: el sujeto se
    contradice y las dos intenciones eligen distinto. Montarlo aqui permite
    que CADA pregunta se mida contra el mismo estado, y sobre todo permite
    distinguir «no hay nada» de «hay algo que no es lo que preguntabas».
    """
    s.upsert_entity(
        tenant_id=tenant_id,
        project_id=project_id,
        entity=Entity(entity_id=SUJETO, kind="file", stable_key="a.py"),
    )
    s.upsert_entity(
        tenant_id=tenant_id,
        project_id=project_id,
        entity=Entity(entity_id=OBJETO, kind="file", stable_key="b.py"),
    )
    for sid, kind, locator in (
        (ADY, "external_doc", {"producer": "adr.reader"}),
        (RT, "runtime_observation", {"producer": "telemetry.query"}),
    ):
        s.register_source(
            tenant_id=tenant_id,
            project_id=project_id,
            source=Source(
                source_id=source_id(sid),
                kind=kind,
                content_hash=f"h-{sid}",
                locator=locator,
                git_commit_sha="a" * 40 if kind == "git_commit" else None,
                git_tree_sha=None,
                working_tree_status=None,
                checked_at="2026-10-07T12:00:00Z",
                freshness="current",
                observed_from="2026-10-07T00:00:00Z" if kind == "runtime_observation" else None,
                observed_to="2026-10-07T12:00:00Z" if kind == "runtime_observation" else None,
            ),
        )
    for cid, valor, origen, sid, sujeto, objeto in (
        ("c-runtime", "sqlite3", "observed", RT, SUJETO, None),
        ("c-adr", "psycopg", "human-asserted", ADY, SUJETO, None),
        # `c-impacto` lleva `object_entity` y NO `object_literal`, y la
        # diferencia es el bloque entero: `list_claims_by_object_entity`
        # filtra por la COLUMNA de referencia, y un literal `"file:a.py"`
        # vive en `object_literal_json`. Con un literal ahi la consulta
        # devuelve CERO y `impact` parece no funcionar —cuando lo que no
        # funcionaba era el dato de prueba, no la consulta—.
        ("c-impacto", None, "human-asserted", ADY, OBJETO, EntityRef(SUJETO)),
    ):
        s.record_claim(
            tenant_id=tenant_id,
            project_id=project_id,
            claim=Claim(
                claim_id=cid,
                subject_entity_id=sujeto,
                predicate="imports_module",
                object_literal=valor,
                object_entity=objeto,
                source_id=source_id(sid),
                assertion_origin=origen,
                checked_at_revision="r1",
            ),
        )


def _superficie(s: Storage) -> SuperficieConocimiento:
    return SuperficieConocimiento(s, tenant_id="t", project_id="p")


# ---------------------------------------------------------------------------
# P1 — vocabulario cerrado
# ---------------------------------------------------------------------------


class TestLasSeisSonVocabularioCerrado:
    def test_las_seis_estan_en_el_literal(self) -> None:
        esperados = {"what", "why", "impact", "changed", "conflicts", "evidence"}
        assert set(typing.get_args(PREGUNTA)) == esperados, (
            f"el Literal declara {sorted(typing.get_args(PREGUNTA))}, "
            f"y el roadmap declara {sorted(esperados)}"
        )

    def test_el_conjunto_se_deriva_del_literal(self) -> None:
        """Regla QW-E. Un conjunto escrito a mano es una segunda fuente de
        verdad que se desincroniza en cuanto el `Literal` crece."""
        assert frozenset(typing.get_args(PREGUNTA)) == CONSULTAS

    def test_una_pregunta_valida_devuelve_el_tipo(self) -> None:
        """**El camino que faltaba, y no es trivial que falte.**

        MEDIDO: la medicion inicial daba 98 % con la linea del `return` de
        `pregunta()` sin cubrir, porque el unico test que llamaba a la
        funcion la llamaba con un valor INVALIDO. El rechazo se mido y el
        camino de acierto no.

        Se mide porque es donde vive el `cast`: un `cast` sin ejecucion
        es un `cast` que el type-checker no verifica en runtime, y un
        smart constructor que solo se ha probado fallando no sabe
        devolver.
        """
        assert pregunta("what") == "what"
        assert pregunta("why") == "why"

    def test_una_pregunta_fuera_del_vocabulario_se_rechaza(self) -> None:
        """En la FRONTERA, no al responder.

        `pregunta()` se llama al construir la `Consulta`, que es donde el
        llamante puede dar contexto; si se llamara dentro de `responder`,
        el error llegaria a quien ejecuto y no a quien pregunto.
        """
        with pytest.raises(ValidationError, match="desconocida"):
            pregunta("todo")


# ---------------------------------------------------------------------------
# P2 — EL GATE DEL BLOQUE
# ---------------------------------------------------------------------------


class TestUnaSolaSuperficieParaTodas:
    """**LA PROPIEDAD MAS IMPORTANTE DEL FICHERO.**

    El gate dice: «las mismas query models alimentan CLI y MCP/agent
    handoff; ninguna superficie reconstruye autoridad o retrieval por su
    cuenta». Eso se mide mirando que **no** hay dos caminos.

    Se mide por AST y no por busqueda de cadena porque la propiedad es
    «este fichero NO llama al retrieval», y una mencion en un docstring es
    indistinguible de una llamada si se busca con texto. Es la misma razon
    que hace que WI-92 mida por AST.
    """

    #: **TODO EL CAMINO de B34 en la CLI, no solo los seis handlers.**
    #:
    #: La primera version de este guard media `LOS_SEIS`, que son
    #: `cmd_knowledge_what` y companeros —UNA linea cada uno, un
    #: `return _responder_y_salir(args, "what")`—. MEDIDO: con la
    #: superficie sustituida por una llamada directa al repositorio DENTRO
    #: de `_responder_y_salir`, el guard daba **VERDE**.
    #:
    #: Es el mismo error que el del guard de B15 y el de WI-92, y merece
    #: quedar escrito: **un guard que mide la ENVOLTURA y no el camino
    #: sigue en verde mientras el camino este roto.** Seis funciones que
    #: solo delegan no son seis funciones que se puedan auditar; el
    #: retrieval ocurre mas abajo, en el helper.
    #:
    #: Por eso el conjunto incluye los TRES helpers. Y por eso no es «el
    #: fichero entero»: `cmd_knowledge_resolve` de B28 vive en el mismo
    #: modulo y llama al retrieval por su cuenta, y medirlo seria fallar
    #: por algo que este bloque no toco. Ese solape se mide aparte y con
    #: nombre, en `TestElSolapeConResolveDeB28`.
    EL_CAMINO = (
        "cmd_knowledge_what",
        "cmd_knowledge_why",
        "cmd_knowledge_impact",
        "cmd_knowledge_changed",
        "cmd_knowledge_conflicts",
        "cmd_knowledge_evidence",
        "_responder_y_salir",
        "_pregunta",
        "_superficie",
        "_render_respuesta",
        "_objeto_de",
    )

    def _atributos_de(self, modulo: str, funciones: tuple[str, ...] | None = None) -> set[str]:
        """Los atributos que se LLAMAN, y solo dentro de las funciones dadas.

        Por AST y no por cadena porque la propiedad es «este codigo no
        llama al retrieval»: una mencion en un docstring es
        indistinguible de una llamada si se busca con texto. Es la misma
        razon que hace que WI-92 mida por AST.
        """
        arbol = ast.parse((REPO / modulo).read_text())
        atributos: set[str] = set()
        if funciones is None:
            raices: tuple[ast.AST, ...] = (arbol,)
        else:
            # `ast.walk` NO sirve aqui, y el error es silencioso: el filtro
            # salta el nodo `FunctionDef` que no toca, pero `walk` sigue
            # descendiendo en sus HIJOS, y el atributo prohibido aparece
            # igual. Se midio: con el `continue` el guard seguia viendo
            # `conflicts_for`, que pertenece a `cmd_knowledge_resolve`, un
            # comando de B28 que este bloque no toca. Por eso se recogen
            # las FUNCIONES y se camina solo dentro de ellas.
            permitidas = set(funciones)
            # Los handlers de la CLI son FUNCIONES DE MODULO, no metodos.
            # La primera version solo miraba dentro de `ClassDef` y por eso
            # no encontraba ninguna: el guard decia «no existen» cuando lo
            # que no existia era la busqueda. Un guard que mide donde mira
            # y no lo que mide es la forma de dar verde en falso.
            raices = tuple(
                nodo
                for nodo in arbol.body
                if isinstance(nodo, ast.FunctionDef) and nodo.name in permitidas
            )
            faltan = permitidas - {n.name for n in arbol.body if isinstance(n, ast.FunctionDef)}
            assert not faltan, f"no existen los handlers {sorted(faltan)} en {modulo}"
        for raiz in raices:
            for nodo in ast.walk(raiz):
                # (a) `storage.conflicts_for(...)` — atributo sobre un
                # receptor conocido.
                if (
                    isinstance(nodo, ast.Attribute)
                    and isinstance(nodo.value, ast.Name)
                    and nodo.value.id in {"storage", "self", "superficie", "_superficie"}
                ):
                    atributos.add(nodo.attr)
                # (b) `resolver(...)` — NOMBRE SUELTO. MEDIDO: la primera
                # version del guard solo miraba atributos, y una sonda que
                # hacia `from ... import resolver as _r` y luego `_r(...)`
                # la esquivaba. Es el camino corto de la segunda superficie:
                # importar la autoracion y llamarla por su cuenta. Un guard
                # que solo mira atributos no ve la mitad de las formas de
                # meter una segunda copia, y la mitad que no ve es
                # precisamente la que se escribe sola.
                elif isinstance(nodo, ast.Name) and isinstance(nodo.ctx, ast.Load):
                    atributos.add(nodo.id)
        # (c) LAS IMPORTACIONES. MEDIDO: la sonda M2 hacia
        # `from ... import resolver as _r` y luego `_r(...)`, y con (a) y
        # (b) la sonda pasaba: el nombre en el arbol es `_r`, no
        # `resolver`. Un alias defeats la deteccion por NOMBRE, y es
        # justamente el camino corto de la segunda copia de la autoridad.
        #
        # Se mide la IMPORTACION y no el nombre, y asi el alias deja de
        # servir: si el modulo importa `resolver`, el modulo esta
        # tomando la autoridad por su cuenta diga luego como la llame.
        # Sin esto habria que declarar el hueco —como hace WI-108 con
        # `from pytest import skip`— y aqui se puede cerrar.
        for raiz in raices:
            for nodo in ast.walk(raiz):
                if isinstance(nodo, ast.ImportFrom):
                    for alias in nodo.names:
                        atributos.add(alias.name)
                elif isinstance(nodo, ast.Import):
                    for alias in nodo.names:
                        atributos.add(alias.name.split(".")[-1])
        return atributos

    def test_la_cli_no_llama_al_retrieval(self) -> None:
        """La CLI no habla con el repositorio para responder.

        Nombra el porque: si lo hiciera, habria dos caminos que responder y
        el dia que divergieran el gate seria verdad en el `ROADMAP.md` y
        falso en el codigo.
        """
        retrieval = {
            "list_claims_for_subject",
            "list_claims_by_object_entity",
            "claims_at_revision",
            "claims_desde_commit",
            "conflicts_for",
            "get_evidences_for_claim",
            "resolver",
        }
        encontrados = retrieval & self._atributos_de(
            "src/skillgraph/cli/commands/knowledge.py", self.EL_CAMINO
        )
        assert not encontrados, (
            f"la CLI reconstruye el retrieval por su cuenta: {sorted(encontrados)}. "
            "La superficie es el unico camino; la CLI solo formatea"
        )

    def test_la_capability_no_llama_al_retrieval_de_la_superficie(self) -> None:
        """Y la capability tampoco: construye la `Consulta` y pregunta.

        La excepcion declarada es `_claims`/`_recurso`, que son las dos
        consultas de B30 y NO son de la superficie. Se mide que no haya
        besides de esas dos.
        """
        retrieval = {
            "claims_at_revision",
            "claims_desde_commit",
            "conflicts_for",
            "resolver",
        }
        encontrados = retrieval & self._atributos_de("src/skillgraph/knowledge/knowledge_query.py")
        assert not encontrados, (
            f"la capability reconstruye una consulta de la superficie: {sorted(encontrados)}"
        )

    def test_las_dos_superficies_caben_en_un_mismo_metodo(self) -> None:
        """`responder` es el unico metodo publico que despacha.

        Y la comprobacion de que las preguntas se atienden TODAS sale del
        `Literal`, no de una lista escrita aqui: si `responder` dejara de
        despachar alguna, este test se pondria rojo, y es lo que evita que
        anadir una septima pregunta se olvide de cablear.
        """
        metodos = {
            nodo.name
            for nodo in ast.walk(
                ast.parse((REPO / "src/skillgraph/knowledge/superficie.py").read_text())
            )
            if isinstance(nodo, ast.FunctionDef) and nodo.name.startswith("_responde_")
        }
        assert {m.removeprefix("_responde_") for m in metodos} == CONSULTAS, (
            f"`responder` despacha {sorted(metodos)} y el Literal declara "
            f"{sorted(CONSULTAS)}. Una pregunta sin `_responde_` reventaria en "
            "runtime con un AttributeError, no con un mensaje de dominio"
        )


# ---------------------------------------------------------------------------
# P3 a P9
# ---------------------------------------------------------------------------


class TestWhyRespondeProcedencia:
    def test_por_que_dice_quien_y_de_donde(self, tmp_path: Path) -> None:
        s = _storage(tmp_path)
        try:
            _poblar(s)
            r = _superficie(s).responder(Consulta(pregunta="why", subject=SUJETO, claim_id="c-adr"))
            assert len(r.procedencia) == 1
            p = r.procedencia[0]
            assert isinstance(p, Procedencia)
            assert p.claim_id == "c-adr"
            assert p.assertion_origin == "human-asserted"
            assert p.extractor_version
            assert p.source_id == source_id(ADY)
            assert p.source_kind == "external_doc"
        finally:
            s.close()

    def test_why_sin_claim_id_no_se_construye(self) -> None:
        """Se rechaza al construir, no al responder.

        «Por que se afirmo» sin decir QUE afirmacion no es una pregunta:
        es una consulta sin sujeto. Y el mensaje lo dice, porque el nombre
        `why` sugiere que basta con el sujeto del grafo.
        """
        with pytest.raises(ValidationError, match="claim_id"):
            Consulta(pregunta="why", subject=SUJETO)

    def test_why_no_inventa_causa(self, tmp_path: Path) -> None:
        """**EL CONTRA SALTO DEL BLOQUE.**

        `why` no puede devolver nada que parezca causalidad. Se mide que
        la `Procedencia` NO tiene campo para «porque el mundo es asi»: sus
        campos son todos sobre ESTA afirmacion, y un campo `motivo` o
        `causa` seria justo la promesa que el modelo no cumple.
        """
        campos = set(Procedencia.__dataclass_fields__)
        causal = {"motivo", "causa", "razon", "porque", "explicacion", "justificacion"}
        assert not (campos & causal), (
            f"`Procedencia` ha crecido con {sorted(campos & causal)}: eso prometeria "
            "causalidad, y el sistema tiene procedencia, no causa"
        )


class TestImpactEsLaAristaInversa:
    def test_impact_no_es_lo_mismo_que_what(self, tmp_path: Path) -> None:
        """La property central, y la que un solo metodo con un parametro
        habria escondido.

        `what` del sujeto `a.py` trae las afirmaciones SOBRE `a.py`; `impact`
        de `a.py` trae las que lo MENCIONAN como objeto, que son las de
        `b.py`. Si los dos dieran lo mismo, la arista habria perdido un
        sentido en silencio.
        """
        s = _storage(tmp_path)
        try:
            _poblar(s)
            sup = _superficie(s)
            what = sup.responder(Consulta(pregunta="what", subject=SUJETO))
            impact = sup.responder(Consulta(pregunta="impact", subject=SUJETO))
            assert {c.claim_id for c in what.claims} == {"c-runtime", "c-adr"}
            assert {c.claim_id for c in impact.claims} == {"c-impacto"}
            assert not ({c.claim_id for c in what.claims} & {c.claim_id for c in impact.claims})
        finally:
            s.close()


class TestWhatNoResuelveNiSeResuelve:
    def test_what_no_devuelve_resolucion(self, tmp_path: Path) -> None:
        """`what` pregunta por lo que se AFIRMA, no por lo que es cierto.

        Poner el resolver aqui seria quitarle la eleccion al que pregunta:
        dejaria de poder ver las dos afirmaciones opuestas y tendria que
        confiar en un ranking que no pidio. Es la mitad del problema de B28
        por el otro lado.
        """
        s = _storage(tmp_path)
        try:
            _poblar(s)
            r = _superficie(s).responder(Consulta(pregunta="what", subject=SUJETO))
            assert r.resolucion is None
            assert r.conflicto is None
            assert len(r.claims) == 2, "debe devolver LAS DOS, sin elegir"
        finally:
            s.close()


class TestConflictosSinIntencionNoResuelven:
    def test_sin_intencion_devuelve_el_conflicto_sin_resolver(self, tmp_path: Path) -> None:
        """Y con intencion, resuelve.

        Sin `--intent` la respuesta es «esto se contradice», que es una
        pregunta con respuesta. Un default resolveria por la pregunta que
        nadie hizo, que es el ranking global que B28 cerro.
        """
        s = _storage(tmp_path)
        try:
            _poblar(s)
            sup = _superficie(s)
            sin = sup.responder(Consulta(pregunta="conflicts", subject=SUJETO))
            assert sin.conflicto is not None
            assert sin.resolucion is None, "sin intencion NO debe resolver"

            con = sup.responder(
                Consulta(pregunta="conflicts", subject=SUJETO, revision="actual_behavior")
            )
            assert con.resolucion is not None
            assert con.resolucion.ganadora is not None
            assert con.resolucion.ganadora.claim_id == "c-runtime"
        finally:
            s.close()

    def test_y_es_el_mismo_resolver_de_b28(self, tmp_path: Path) -> None:
        """La superficie NO reimplementa la autoridad: la llama.

        Se mide comparando contra `resolver` directamente. Un copy del
        ranking por intencion daria verde en todo lo de arriba y seria el
        defecto que B28 cerro.
        """
        s = _storage(tmp_path)
        try:
            _poblar(s)
            r = _superficie(s).responder(
                Consulta(pregunta="conflicts", subject=SUJETO, revision="actual_behavior")
            )
            conflictos = s.conflicts_for(tenant_id="t", project_id="p", subject_entity_id=SUJETO)
            esperado = resolver(conflictos[0], intencion="actual_behavior")
            assert r.resolucion is not None and esperado is not None
            assert r.resolucion.ganadora is not None
            assert r.resolucion.ganadora.claim_id == esperado.ganadora.claim_id  # type: ignore[union-attr]
        finally:
            s.close()


class TestLosDosRelojesNoSeTraducen:
    def test_commit_solo_es_de_changed(self) -> None:
        """`commit` en otra pregunta es un error de construccion.

        No un parametro que se ignora: dejarlos seria sugerir que todas las
        preguntas son historicas, que es lo que B29 cobro caro cuando
        `revision_registro.seq` se confundo con `GitHistory`.
        """
        with pytest.raises(ValidationError, match="no se pregunta por un commit"):
            Consulta(pregunta="what", subject=SUJETO, commit="a" * 40)


class TestLasSeisDevuelvenLaMismaForma:
    def test_todas_son_Respuesta(self, tmp_path: Path) -> None:
        """El punto de que haya UN tipo de respuesta.

        Si cada superficie recibiera un tipo distinto, cada una tendria que
        ramificar por la pregunta —y ese `if` es el retrieval por su cuenta
        que el gate prohibe.
        """
        s = _storage(tmp_path)
        try:
            _poblar(s)
            sup = _superficie(s)
            consultas = (
                Consulta(pregunta="what", subject=SUJETO),
                Consulta(pregunta="why", subject=SUJETO, claim_id="c-adr"),
                Consulta(pregunta="impact", subject=SUJETO),
                Consulta(pregunta="changed", subject=SUJETO, revision="r1"),
                Consulta(pregunta="conflicts", subject=SUJETO),
                Consulta(pregunta="evidence", subject=SUJETO),
            )
            for c in consultas:
                r = sup.responder(c)
                assert isinstance(r, Respuesta), f"{c.pregunta} devolvio {type(r).__name__}"
                assert r.consulta is c
        finally:
            s.close()

    def test_el_payload_lleva_el_vocabulario(self, tmp_path: Path) -> None:
        """Un `Literal` serializado es una cadena, y quien la recibe
        tendria que saber el vocabulario para validarla. Se manda la lista
        de las seis para que un agente vea el contrato sin leer el codigo.
        """
        s = _storage(tmp_path)
        try:
            _poblar(s)
            payload = respuesta_a_payload(
                _superficie(s).responder(Consulta(pregunta="what", subject=SUJETO))
            )
            assert payload["vocabulario"] == sorted(CONSULTAS)
        finally:
            s.close()


class TestVacioYAusenteNoSonLoMismo:
    def test_un_conflicto_abierto_no_es_una_respuesta_vacia(self, tmp_path: Path) -> None:
        """Un conflicto sin resolver es una RESPUESTA, no un silencio.

        Con `claims=()` y `resolucion=None`, la comprobacion ingenua de
        «vacio» diria que no hay nada, y hay un conflicto abierto esperando.
        """
        s = _storage(tmp_path)
        try:
            _poblar(s)
            r = _superficie(s).responder(Consulta(pregunta="conflicts", subject=SUJETO))
            assert r.conflicto is not None
            assert r.vacia is False
        finally:
            s.close()

    def test_un_subject_desconocido_si_es_vacio(self, tmp_path: Path) -> None:
        """Y lo contrario: sin nada, `vacia` es `True` y no hay que
        inventar un campo para decirlo."""
        s = _storage(tmp_path)
        try:
            _poblar(s)
            r = _superficie(s).responder(Consulta(pregunta="what", subject="file:no-existe.py"))
            assert r.claims == ()
            assert r.vacia is True
        finally:
            s.close()


# ---------------------------------------------------------------------------
# La superficie por la CLI DE VERDAD, y el solape con `resolve` de B28
# ---------------------------------------------------------------------------


class TestLaSuperficiePorLaCli:
    """El gate por el otro lado: la superficie no solo existe, se USA.

    **POR QUE `subprocess` Y NO LA FUNCION.** `AGENTS.md` 6.4 pide un test
    CLI que compruebe el contrato externo —exit code, salida, efectos— y
    medirlo llamando a la funcion en proceso solo mide la mitad de Python
    del camino. Lo que se rompe entre la funcion y el terminal es
    precisamente el cableado: el parser, la tabla de despacho, el formato
    de salida. Y eso no se ve desde dentro.
    """

    @staticmethod
    def _sg(data_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "skillgraph", "--data-root", str(data_root), *args],
            capture_output=True,
            text=True,
            cwd=REPO,
        )

    @pytest.fixture
    def proyecto(self, tmp_path: Path) -> Path:
        data_root = tmp_path / "datos"
        creado = self._sg(data_root, "project", "create", "demo")
        assert creado.returncode == 0, creado.stderr
        # MEDIDO: `next(rglob("*.sqlite"))` cogia el CATALOGO, no el
        # proyecto —`catalog.sqlite` esta en la raiz del data_root y se
        # encuentra antes—. El fixture poblo el catalogo y las seis
        # consultas respondieron «sin resultados», que es la forma
        # silenciosa de que un test de CLI verde mida una base vacia.
        # Se baja por la ruta EXACTA del proyecto.
        db = data_root / "tenants" / "default" / "projects" / "demo" / "project.sqlite"
        assert db.exists(), (
            f"el proyecto no esta donde se esperaba: {sorted(data_root.rglob('*.sqlite'))}"
        )
        s = Storage(db)
        try:
            _poblar(s, tenant_id="default", project_id="demo")
        finally:
            s.close()
        return data_root

    @pytest.mark.parametrize(
        ("args", "debe_contener"),
        [
            (("what", "demo", "file:a.py"), "c-runtime"),
            (("impact", "demo", "file:a.py"), "c-impacto"),
            (("evidence", "demo", "file:a.py"), "procedencia"),
            (("why", "demo", "file:a.py", "--claim-id", "c-adr"), "c-adr"),
            (("changed", "demo", "file:a.py", "--at-revision", "r1"), "c-adr"),
            (("conflicts", "demo", "file:a.py"), "c-runtime"),
        ],
    )
    def test_cada_pregunta_sale_por_la_cli(
        self, proyecto: Path, args: tuple[str, ...], debe_contener: str
    ) -> None:
        proc = self._sg(proyecto, "knowledge", *args)
        assert proc.returncode == 0, proc.stderr
        assert debe_contener in proc.stdout, (
            f"`sg knowledge {args[0]}` no devolvio {debe_contener!r}. Salida:\n{proc.stdout}"
        )

    def test_json_es_el_mismo_modelo(self, proyecto: Path) -> None:
        """La salida estructurada y la humana salen del MISMO sitio.

        Y se mide que el JSON lleva el `vocabulario` cerrado, que es lo que
        permite a un agente descubrir las preguntas sin leer el codigo.
        """
        proc = self._sg(proyecto, "knowledge", "what", "demo", "file:a.py", "--json")
        assert proc.returncode == 0, proc.stderr
        datos = json.loads(proc.stdout)
        assert datos["vocabulario"] == sorted(CONSULTAS)
        assert datos["consulta"]["pregunta"] == "what"

    def test_why_sin_claim_id_falla_por_la_cli(self, proyecto: Path) -> None:
        """El error sale con codigo de dominio, no con un Traceback.

        Es el contrato de WI-109 aplicado a la superficie: una peticion
        mal formada es un fallo del operador y tiene que traducirse.
        """
        proc = self._sg(proyecto, "knowledge", "why", "demo", "file:a.py")
        assert proc.returncode != 0
        assert "Traceback" not in proc.stderr, (
            f"un envelope mal formado sale como Traceback:\n{proc.stderr}"
        )
        assert "claim_id" in proc.stderr

    def test_impact_pinta_la_entidad_no_un_vacio(self, proyecto: Path) -> None:
        """MEDIDO ejecutando la CLI: `imports_module = ''`.

        La primera version del render imprimia `object_literal!r`, y en un
        claim cuyo objeto es una ENTIDAD ese campo vale `None`. El test
        anterior —«`c-impacto` aparece en la salida»— daba VERDE igual: el
        identificador salia, solo que el objeto era un hueco. Un `''` no
        es «sin objeto», es «el render no sabe pintar este objeto», que es
        justo la linea que hace que una persona deje de fiarse de la salida.

        Y el discriminante es el `-> file:a.py`, no el `c-impacto`.
        """
        proc = self._sg(proyecto, "knowledge", "impact", "demo", "file:a.py")
        assert proc.returncode == 0, proc.stderr
        assert "-> file:a.py" in proc.stdout, f"la entidad no se pinto como entidad:\n{proc.stdout}"
        assert "= ''" not in proc.stdout, (
            f"un objeto entidad salio como literal vacio:\n{proc.stdout}"
        )


class TestElSolapeConResolveDeB28:
    """**LA DEUDA QUE ESTE BLOQUE DEJA CON NOMBRE.**

    `sg knowledge resolve` (B28) y `sg knowledge conflicts --at-revision
    <intent>` (B34) son **la misma pregunta**: los conflictos de un sujeto y
    quien gana para una intencion. Los dos existen.

    Se declara en vez de esconderse porque la alternativa —cambiar `resolve`
    para que delegue— tiene un coste medido: `cmd_knowledge_resolve` resuelve
    **TODOS** los conflictos del sujeto, uno por uno, y tiene su propio
    render y sus tests de B28. Unificarlos es un cambio de contrato de la
    CLI que merece su propio bloque y no un arrastre dentro de este.

    Lo que este test ata es que la situacion siga SIENDO la que se declara.
    Un dia que se unifiquen, este test se pone rojo y obliga a reescribir el
    motivo — que es lo que se quiere: que la deuda no se vuelva invisible
    porque nadie volto a mirar.
    """

    def test_hay_dos_comandos_para_la_misma_pregunta(self) -> None:
        from skillgraph.cli import runner

        tabla = runner._DISPATCH
        assert ("knowledge", "resolve") in tabla
        assert ("knowledge", "conflicts") in tabla

    def test_y_el_solape_esta_declarado_en_el_codigo(self) -> None:
        """El motivo vive junto al comando, no solo en este test.

        Un test declara la situacion; el codigo declara la INTENCION. Si el
        motivo solo estuviera aqui, quien llegue al `resolve` por el `--help`
        no lo veria.
        """
        texto = (REPO / "src/skillgraph/cli/commands/knowledge.py").read_text()
        assert "cmd_knowledge_conflicts" in texto
        assert "B34" in texto


class TestLasRamasQueQuedaban:
    """Las cuatro salidas de `responder` que la medicion inicial dejo sin mirar.

    El modulo entro en 92 % —por encima del suelo del 90 %, pero por poco— y
    las cinco lineas que faltaban eran las salidas: sujeto vacio, `why` de un
    claim que no existe, `changed` por commit, y `conflicts` de un sujeto que
    no se contradice. Son caminos ALCANZABLES, no ramas defensivas: se llega
    a ellos con entradas normales, y son justo los que dicen «no hay nada»
    —que es la respuesta que mas se confunde con un fallo—.
    """

    def test_un_subject_vacio_no_se_construye(self) -> None:
        with pytest.raises(ValidationError, match="subject"):
            Consulta(pregunta="what", subject="   ")

    def test_why_de_un_claim_inexistente_es_vacio(self, tmp_path: Path) -> None:
        """No es un error: es «no hay nada que explicar».

        Y la distincion importa porque se confunden tres capas mas abajo:
        un `claim_id` equivocado y un grafo vacio darian el mismo error, y
        son dos fallos que se arreglan de dos maneras.
        """
        s = _storage(tmp_path)
        try:
            _poblar(s)
            r = _superficie(s).responder(
                Consulta(pregunta="why", subject=SUJETO, claim_id="c-no-existe")
            )
            assert r.claims == ()
            assert r.procedencia == ()
            assert r.vacia is True
        finally:
            s.close()

    def test_changed_por_commit_es_el_otro_reloj(self, tmp_path: Path) -> None:
        """Con `--commit` la respuesta viene del camino de B32.

        Y no del de B29 aunque los dos llenen `Respuesta.claims`: son dos
        consultas distintas y mezclarlas seria volver a confundir los dos
        relojes. Se mide que el camino de `--commit` existe y devuelve algo.
        """
        s = _storage(tmp_path)
        try:
            _poblar(s)
            sup = _superficie(s)
            por_commit = sup.responder(
                Consulta(pregunta="changed", subject=SUJETO, commit="a" * 40)
            )
            por_revision = sup.responder(
                Consulta(pregunta="changed", subject=SUJETO, revision="r1")
            )
            assert isinstance(por_commit, Respuesta)
            assert isinstance(por_revision, Respuesta)
            # HEAD (`revision` ausente) tambien tiene que funcionar: es el
            # caso por defecto y no es el mismo camino que una revision dada.
            head = sup.responder(Consulta(pregunta="changed", subject=SUJETO))
            assert isinstance(head, Respuesta)
        finally:
            s.close()

    def test_conflicts_de_un_sujeto_que_no_se_contradice(self, tmp_path: Path) -> None:
        """Sin conflictos tampoco hay resolucion.

        Y no es lo mismo que un conflicto sin resolver: una respuesta sin
        conflicto tiene `resolucion is None` PORQUE NO HAY, y la de un
        conflicto abierto tiene `conflicto` con contenido. El test de
        `vacia` los separa.
        """
        s = _storage(tmp_path)
        try:
            _poblar(s)
            r = _superficie(s).responder(Consulta(pregunta="conflicts", subject=OBJETO))
            assert r.conflicto is None
            assert r.resolucion is None
            assert r.vacia is True
        finally:
            s.close()
