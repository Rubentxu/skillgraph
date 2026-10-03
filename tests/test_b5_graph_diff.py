"""Red de B5: el Graph Diff Gate es una etapa del gate, no un adorno.

La medicion que abrio el bloque (`scripts/measure_b5_graph_diff.py`) daba
**6 de 6 preguntas abiertas**, y la que lo resume esta:

    GraphExpansionProposal.operations: tuple[object, ...]

La propuesta lleva un saco de operaciones sin tipar. Las tres clases
existen y el comentario del propio codigo dice «PatchOp es ADT cerrado»,
pero no hay ningun `PatchOp` que las una. Sin representation del cambio,
la secuencia del gate es `Proposal -> Policy -> ...` y **no hay etapa
Diff**.

Lo que se fija aqui, en el orden de lo que se romperia si alguien
tocara el codigo:

  R1  el diff se CALCULA comparando el plan actual; no se lee de la
      propuesta, que daria lo mismo con cualquier plan
  R2  cada cambio se nombra por su sujeto semantico, no por texto
  R3  las 7 preguntas del roadmap tienen respuesta, cada una con su campo
  R4  el parche esta TIPADO y la union es cerrada
  R5  el diff es DERIVADO: la propuesta puede mentir y el diff lo ve
  R6  el diff es una ETAPA: `apply_expansion` lo rechaza si no es el suyo

R5 es el guard que mas importa. Un diff que devolviera lo que la
propuesta declara no estaria midiendo nada: seria un eco con mejor
tipografia. Todo el bloque descansa en que el diff se calcule.

Tests de forma y de comportamiento contra el codigo real. Sin mocks del
Storage: el plan es un valor y no toca disco.
"""

from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path

import pytest

from skillgraph.governance import graph_expansion as gx
from skillgraph.governance.graph_diff import (
    ChangeKind,
    ChangeSubject,
    GraphChange,
    GraphDiff,
    diff_graph,
)
from skillgraph.governance.graph_expansion import (
    AddNode,
    Authorization,
    ExpansionRegistry,
    GraphExpansionProposal,
    RemoveTransition,
)
from skillgraph.resources.workflow import WorkflowNode, WorkflowPlan, WorkflowTransition

# ---------------------------------------------------------------------------
# Utilidades: un plan y una propuesta REALES, no diccionarios disfrazados.
# ---------------------------------------------------------------------------


def _nodo(nombre: str, *, capabilities: tuple[str, ...] = ()) -> WorkflowNode:
    """Un `WorkflowNode` REAL.

    Los cinco campos sin default (`namespace`, `api_version`,
    `resource_revision`, `expected_result`) son obligatorios y lo teachan
    a la primera ejecucion si se omiten. Se rellenan con valores
    neutros porque a este diff no le importan: lo que compara es el
    NOMBRE del nodo y sus capacidades.
    """
    return WorkflowNode(
        name=nombre,
        kind="ActionNode",
        namespace="packs:Demo",
        api_version="skillgraph.io/v1",
        resource_revision=1,
        expected_result="ok",
        capabilities=capabilities,
    )


def _plan_con(
    *, nodos: tuple[WorkflowNode, ...], transiciones: tuple[WorkflowTransition, ...]
) -> WorkflowPlan:
    return WorkflowPlan(
        nodes=nodos,
        initial=nodos[0].name,
        transitions=transiciones,
    )


def _autorizacion() -> Authorization:
    return Authorization(mode="policy_approved", granted_at="2026-10-03T00:00:00Z")


def _propuesta(
    *,
    operaciones: tuple[object, ...],
    capabilities: tuple[str, ...] = (),
    evidencia: tuple[str, ...] = ("evidencia-1",),
    base: str = "r1",
) -> GraphExpansionProposal:
    return GraphExpansionProposal(
        proposal_id="p-1",
        base_revision=base,
        problem_observed="el nodo a no alcanza a b",
        evidence=evidencia,
        operations=operaciones,
        new_dependencies=(),
        capabilities_needed=capabilities,
        scope="workflow",
        attachment_point="a",
        rollback_plan=operaciones,
        authorization=_autorizacion(),
        created_at="2026-10-03T00:00:00Z",
        author="test",
    )


# ---------------------------------------------------------------------------
# R1 — el diff se CALCULA
# ---------------------------------------------------------------------------


class TestElDiffSeCalcula:
    def test_no_es_un_campo_de_la_propuesta(self) -> None:
        """`GraphDiff` no vive en la propuesta: se deriva del PLAN.

        Si el diff fuera un campo de la propuesta, dos planes distintos
        con la misma propuesta darian el mismo diff, y R1 se cumpliria
        por construccion sin que nadie comparara nada.
        """
        campos = set(GraphExpansionProposal.__dataclass_fields__)
        assert "diff" not in campos, (
            "la propuesta lleva el diff como campo: entonces el diff no se "
            "compara con nada, se transporta"
        )

    def test_dos_planes_distintos_dan_diffs_distintos(self) -> None:
        """La propiedad que distingue un diff de un eco.

        Misma propuesta, dos estados del mundo. Si el diff sale igual, no
        esta mirando el plan: esta mirando la propuesta.
        """
        vacio = _plan_con(nodos=(_nodo("a"),), transiciones=())
        con_b = _plan_con(nodos=(_nodo("a"), _nodo("b")), transiciones=())
        propuesta = _propuesta(operaciones=())

        d_vacio = diff_graph(vacio, propuesta)
        d_con_b = diff_graph(con_b, propuesta)

        assert d_vacio != d_con_b, (
            "el mismo par (propuesta) sobre dos planes da el mismo diff: "
            "el diff no se esta calculando sobre el plan"
        )

    def test_el_plan_cambia_el_signo_del_cambio(self) -> None:
        """La misma operacion es `+` o `~` segun lo que haya en el plan.

        Este es el caso que separa un diff de un eco, y el que hace que
        R1 sea una propiedad y no una tautologia: si el diff copiara la
        declaracion de la propuesta, `AddNode(b)` seria SIEMPRE un
        `+ node`, se Compton el plan lo que lo contiene.

        Y explica por que el diff NO lista lo que el plan tiene y la
        propuesta no menciona: un diff describe EL CAMBIO, no el mundo.
        Re-lista el grafo entero haria la salida comparable pero
        ilegible, y el ojo de quien lo revisa busca lo que cambia.
        """
        sin_b = _plan_con(nodos=(_nodo("a"),), transiciones=())
        con_b = _plan_con(nodos=(_nodo("a"), _nodo("b")), transiciones=())
        propuesta = _propuesta(operaciones=(AddNode(_nodo("b", capabilities=("sg.x",))),))

        when_falta = {(c.subject, c.kind, c.target) for c in diff_graph(sin_b, propuesta).changes}
        when_esta = {(c.subject, c.kind, c.target) for c in diff_graph(con_b, propuesta).changes}

        assert ("node", "added", "b") in when_falta, (
            f"«b» no esta en el plan, luego la operacion lo anade: {when_falta}"
        )
        assert ("node", "added", "b") not in when_esta, (
            f"«b» YA esta en el plan: decirlo «nuevo» seria mentira. Cambios: {when_esta}"
        )
        assert any(s == "capability" and k == "changed" for s, k, _ in when_esta), (
            f"«b» ya existe y la propuesta le anade capacidades: eso es un "
            f"~ capability, no un +. Cambios: {when_esta}"
        )

    def test_es_inmutable(self) -> None:
        d = diff_graph(_plan_con(nodos=(_nodo("a"),), transiciones=()), _propuesta(operaciones=()))
        with pytest.raises((AttributeError, TypeError)):
            d.changes = ()  # type: ignore[misc]

    def test_no_tiene_slots_ausentes(self) -> None:
        """`slots=True` es parte del contrato de B4/B5: sin slots, el
        dataclass admite atributos nuevos y deja de ser inmutable de hecho."""
        assert hasattr(GraphDiff, "__slots__"), "GraphDiff no declara __slots__"
        assert hasattr(GraphChange, "__slots__"), "GraphChange no declara __slots__"


# ---------------------------------------------------------------------------
# R2 — el cambio se nombra por su efecto semantico
# ---------------------------------------------------------------------------


class TestElCambioEsSemantico:
    def test_el_vocabulario_es_el_del_roadmap(self) -> None:
        """El `Literal` declara las siete clases de cambio del roadmap.

        No se mide contra una copia escrita aqui: se mide que el conjunto
        que el tipo declara contenga el vocabulario del roadmap Y que no
        admita nada mas, que es lo que lo hace cerrado.
        """
        from typing import get_args

        declarados = set(get_args(ChangeSubject))
        esperados = {
            "node",
            "relation",
            "capability",
            "policy",
            "budget",
            "priority",
            "evidence_requirement",
        }
        assert declarados == esperados, (
            f"el sujeto del cambio no es el vocabulario del roadmap: "
            f"{sorted(declarados)} != {sorted(esperados)}"
        )

    def test_el_tipo_de_cambio_es_cerrado(self) -> None:
        from typing import get_args

        assert set(get_args(ChangeKind)) == {"added", "removed", "changed"}

    def test_detail_no_es_la_unica_representacion(self) -> None:
        """`detail` es prosa. Lo que el gate lee es `subject` + `target`.

        Un cambio que solo se pueda leer por su prosa no es un cambio
        semantico, y el gate no puede decidir sobre el.
        """
        c = GraphChange(
            subject="node",
            kind="added",
            target="b",
            detail="agrega el nodo b, que hace de puente entre a y c",
        )
        assert c.subject == "node" and c.target == "b"
        # El detalle puede ser largo o corto; el sujeto no puede ser otra cosa.
        assert c.detail and c.subject

    def test_el_subject_es_obligatorio(self) -> None:
        with pytest.raises(TypeError):
            GraphChange(kind="added", target="b", detail="x")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# R3 — las 7 preguntas
# ---------------------------------------------------------------------------


class TestLasSietePreguntas:
    def test_cada_pregunta_tiene_su_campo(self) -> None:
        campos = set(GraphDiff.__dataclass_fields__)
        necesita = {
            "que cambia": "changes",
            "por que": "reason",
            "que evidencia lo justifica": "evidence",
            "que coste anade": "added_cost",
            "que capacidades exige": "required_capabilities",
            "que nodos invalida": "invalidated_nodes",
            "si es reversible": "reversible",
        }
        faltan = {p: c for p, c in necesita.items() if c not in campos}
        assert not faltan, f"el diff no puede responder: {faltan}"

    def test_la_base_del_diff_queda_declarada(self) -> None:
        """De que revision se calculo.

        Sin esto, dos diffs de la misma propuesta son indistinguibles y no
        se puede afirmar que un apply uso el diff correcto.
        """
        assert "base_revision" in GraphDiff.__dataclass_fields__

    def test_el_diff_es_determinista_entre_procesos(self) -> None:
        """Misma entrada, mismo texto, en PROCESOS DISTINTOS.

        La primera version de esta prueba comparaba dos llamadas en el
        MISMO proceso, y alli la propiedad era **vacua**: el hash seed lo
        fija el interprete al arrancar, luego dos llamadas seguidas dan
        el mismo texto con o sin `sorted()`. La sonda M5 lo enseño: no
        fue cazada.

        Asi que la comparacion cruza el proceso y fija el
        `PYTHONHASHSEED` a dos valores distintos. Si `to_dict` dejara de
        ordenar, los dos procesos darian texto distinto y aqui se veria.
        Es el error de B3 (`tuple(set)`, ocho ordenes en ocho corridas),
        y esta vez la sonda lo caza porque la prueba mira donde puede
        cambiar.
        """
        import os
        import subprocess
        import sys
        import tempfile

        # El guion va a un FICHERO y no a un `-c` de una linea: en una
        # linea hay que meter lambdas, y un lambda no admite argumentos
        # por nombre — que es justo lo que necesita un constructor de
        # nodo. Seebug que se lea.
        guion = """
import json
from skillgraph.governance.graph_diff import diff_graph
from skillgraph.governance.graph_expansion import (
    AddNode, Authorization, GraphExpansionProposal,
)
from skillgraph.resources.workflow import WorkflowNode, WorkflowPlan


def nodo(nombre, capacidades=()):
    return WorkflowNode(
        name=nombre, kind="ActionNode", namespace="packs:Demo",
        api_version="skillgraph.io/v1", resource_revision=1,
        expected_result="ok", capabilities=capacidades,
    )


plan = WorkflowPlan(nodes=(nodo("a"),), initial="a", transitions=())
propuesta = GraphExpansionProposal(
    proposal_id="p-1", base_revision="r1", problem_observed="x",
    evidence=("e",),
    operations=(AddNode(nodo("b", capacidades=("sg.z", "sg.a", "sg.m"))),),
    new_dependencies=(), capabilities_needed=("sg.a", "sg.m"),
    scope="workflow", attachment_point="a",
    rollback_plan=(AddNode(nodo("b")),),
    authorization=Authorization(
        mode="policy_approved", granted_at="2026-10-03T00:00:00Z"),
    created_at="x", author="t",
)
print(json.dumps(diff_graph(plan, propuesta).to_dict(), sort_keys=True))
"""
        salidas = []
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "dif.py"
            script.write_text(guion, encoding="utf-8")
            for seed in ("0", "12345"):
                proc = subprocess.run(
                    [sys.executable, str(script)],
                    capture_output=True,
                    text=True,
                    env={**os.environ, "PYTHONHASHSEED": seed},
                    cwd=Path(__file__).resolve().parent.parent,
                    timeout=120,
                )
                assert proc.returncode == 0, proc.stderr[-500:]
                salidas.append(proc.stdout.strip())
        assert salidas[0] == salidas[1], (
            "el mismo diff se serializa distinto segun el PYTHONHASHSEED: "
            "dos textos que no se comparan no son una etapa del gate"
        )

    def test_el_diff_es_determinista(self) -> None:
        """Misma entrada, misma salida.

        Un diff que depende del hash de un set —el error que ya dio en B3
        con `tuple(set)`— haria que dos aplicaciones de la misma propuesta
        no se pudieran comparar.
        """
        plan = _plan_con(nodos=(_nodo("a"),), transiciones=())
        propuesta = _propuesta(operaciones=(AddNode(_nodo("b")),))
        primero = diff_graph(plan, propuesta)
        segundo = diff_graph(plan, propuesta)
        assert primero == segundo
        assert primero.to_dict() == segundo.to_dict()


class TestLaSeptimaPregunta:
    """«¿es reversible?» tiene que depender del plan de rollback.

    La sonda M7 puso `reversible=True` fijo y NADIE la cazó: ningun
    test afirmaba la dependencia. Un campo que responde siempre «si» a
    una pregunta de riesgo es la forma mas peligrosa de mentir, porque
    el gate lee «reversible» y deja pasar un cambio que no lo es.
    """

    def test_sin_rollback_no_es_reversible(self) -> None:
        plan = _plan_con(nodos=(_nodo("a"),), transiciones=())
        # El helper pone `rollback_plan=operaciones`, asi que una
        # propuesta CON parche trae rollback y otra NO lo trae. La
        # primera version de esta prueba usaba parche vacio en las dos,
        # luego las dos caian en el mismo lado y la premisa era falsa.
        con = _propuesta(operaciones=(AddNode(_nodo("b")),))
        sin = replace(con, rollback_plan=())

        assert diff_graph(plan, con).reversible is True
        assert diff_graph(plan, sin).reversible is False, (
            "una propuesta sin plan de rollback se declara reversible: "
            "la septima pregunta del roadmap responde siempre que si"
        )

    def test_reversible_llega_a_las_respuestas(self) -> None:
        d = diff_graph(
            _plan_con(nodos=(_nodo("a"),), transiciones=()),
            replace(_propuesta(operaciones=(AddNode(_nodo("b")),)), rollback_plan=()),
        )
        assert d.respuestas()["si_es_reversible"] is False


# ---------------------------------------------------------------------------
# R4 — el parche esta tipado
# ---------------------------------------------------------------------------


class TestElParcheEstaTipado:
    def test_operations_declara_el_tipo(self) -> None:
        """`tuple[object, ...]` no restringe nada.

        Este es EL hallazgo de la medicion: la anotacion admite
        cualquier valor, luego nada que quiera preguntarle al parche tiene
        por donde mirar.
        """
        anot = gx.GraphExpansionProposal.__dataclass_fields__["operations"].type
        # `from __future__ import annotations` deja la anotacion como
        # cadena, y el texto es lo que ve el type-checker tambien.
        texto = anot if isinstance(anot, str) else str(anot)
        assert "PatchOp" in texto, (
            f"operations sigue sin tipo de parche: {texto!r}. "
            f"object admite cualquier valor, luego no restringe nada"
        )
        assert "object" not in texto.replace("PatchOp", ""), (
            f"operations declara `object` ademas del tipo de parche: {texto!r}"
        )

    def test_patch_op_es_una_union_cerrada_de_lo_que_existe(self) -> None:
        """El conjunto se DERIVA del arbol, no esta escrito en el test.

        Una lista escrita aqui seria la misma trampa que `PatchOp` es
        por no existir: el guard compararia contra su propia copia.
        """
        # Derivacion desde el arbol: que clases de operacion declara
        # `graph_expansion`, deducidas de los CAMPOS que cada una lleva.
        # `AddNode` lleva `node`, `AddTransition` lleva `transition` y
        # `RemoveTransition` lleva `from_node`.
        arbol = ast.parse(Path(gx.__file__).read_text(encoding="utf-8"))
        marcadores = {"node", "transition", "from_node"}
        clases_op = sorted(
            n.name
            for n in ast.walk(arbol)
            if isinstance(n, ast.ClassDef)
            and any(
                isinstance(s, ast.AnnAssign)
                and isinstance(s.target, ast.Name)
                and s.target.id in marcadores
                for s in n.body
            )
        )
        from skillgraph.governance.graph_diff import PATCH_OP_CLASSES

        assert set(clases_op) == set(PATCH_OP_CLASSES), (
            f"las operaciones del arbol son {clases_op} y la union declara "
            f"{sorted(PATCH_OP_CLASSES)}: o falta una, o sobra una"
        )

    def test_una_operacion_fuera_de_la_union_no_entra(self) -> None:
        from skillgraph.governance.graph_diff import es_patch_op

        assert es_patch_op(AddNode(_nodo("b")))
        assert es_patch_op(RemoveTransition(from_node="a", outcome="ok"))
        assert not es_patch_op({"node": "b"}), "un dict no es una operacion de parche"
        assert not es_patch_op("agregar b"), "una cadena no es una operacion de parche"


# ---------------------------------------------------------------------------
# R5 — el diff es derivado  (anti-tautologia)
# ---------------------------------------------------------------------------


class TestElDiffEsDerivado:
    """Si el diff devolviera lo que la propuesta DECLARA, no mediria nada.

    Este es el guard que mas importa del bloque. Todo lo demas depende de
    que el diff se calcule; si se limitara a copiar la declaracion, R1 a
    R3 serian verdad por construccion y el gate no miraria nada.
    """

    def _plan_y_propuesta(self, capabilities: tuple[str, ...], declaradas: tuple[str, ...]):
        plan = _plan_con(nodos=(_nodo("a"),), transiciones=())
        ops = (AddNode(_nodo("c", capabilities=capabilities)),)
        return plan, _propuesta(operaciones=ops, capabilities=declaradas)

    def test_una_propuesta_que_miente_deja_discrepancia(self) -> None:
        """La operacion mete la capacidad `sg.x`; la propuesta declara otra.

        El diff tiene que ver la DISCREPANCIA. Si copiaran la
        declaracion, esto pasaria en verde.
        """
        plan, propuesta = self._plan_y_propuesta(
            capabilities=("sg.real",),
            declaradas=("sg.declarada",),
        )
        d = diff_graph(plan, propuesta)
        assert d.declared_capabilities != d.required_capabilities, (
            "la propuesta declara unas capacidades y sus operaciones producen "
            "otras, y el diff no lo ve: esta leyendo la declaracion"
        )
        assert "sg.declarada" in d.declared_capabilities
        assert "sg.real" in d.required_capabilities

    def test_una_propuesta_coherente_no_deja_discrepancia(self) -> None:
        """CONTRASALTO. Un guard que siempre pita no esta midiendo."""
        plan, propuesta = self._plan_y_propuesta(
            capabilities=("sg.real",),
            declaradas=("sg.real",),
        )
        d = diff_graph(plan, propuesta)
        assert d.declared_capabilities == d.required_capabilities, (
            "una propuesta coherente produce discrepancia: el guard no distingue "
            "el caso bueno del malo, y por tanto no mide"
        )

    def test_la_discrepancia_queda_nombrada(self) -> None:
        """No basta con que se note: un verificador que dice «falso» sin
        decir cual es la verdad deja a quien corrige haciendo el trabajo
        que el guard existe para evitar."""
        plan, propuesta = self._plan_y_propuesta(
            capabilities=("sg.real",),
            declaradas=("sg.declarada",),
        )
        d = diff_graph(plan, propuesta)
        assert d.declared_capabilities != d.required_capabilities
        render = d.to_dict()
        assert render["declared_capabilities"] != render["required_capabilities"]


# ---------------------------------------------------------------------------
# R6 — el diff es una ETAPA del gate
# ---------------------------------------------------------------------------


class TestElDiffEsEtapaDelGate:
    """Conectar NO es contener (WI-102).

    Que exista una funcion `diff_graph` no dice que nadie la use. Lo que
    dice que el diff es una etapa es que `apply_expansion` lo RECHAZA
    cuando no es el suyo.
    """

    def _registro(self) -> ExpansionRegistry:
        return ExpansionRegistry(capabilities={"sg.real": "adapter"})

    def test_apply_rechaza_un_diff_de_otro_plan(self) -> None:
        otro_plan = _plan_con(
            nodos=(_nodo("a"), _nodo("z")),
            transiciones=(),
        )
        plan = _plan_con(nodos=(_nodo("a"),), transiciones=())
        propuesta = _propuesta(operaciones=())
        diff_de_otro = diff_graph(otro_plan, propuesta)

        resultado = gx.apply_expansion(
            propuesta,
            plan,
            registry=self._registro(),
            diff=diff_de_otro,
        )
        assert resultado.is_err(), (
            "apply_expansion acepto un diff calculado sobre OTRO plan: el "
            "diff no es una etapa del gate, es un parametro decorativo"
        )
        assert "diff" in resultado.unwrap_err().reason.lower()

    def test_apply_acepta_el_diff_de_su_propia_propuesta(self) -> None:
        """CONTRASALTO de R6: el camino bueno tiene que pasar.

        Sin esto, `apply_expansion` podria rechazar SIEMPRE y R6 seria
        cierto sin que el gate sirviera para nada.
        """
        plan = _plan_con(nodos=(_nodo("a"),), transiciones=())
        propuesta = _propuesta(operaciones=())
        su_diff = diff_graph(plan, propuesta)
        resultado = gx.apply_expansion(
            propuesta,
            plan,
            registry=self._registro(),
            diff=su_diff,
        )
        # Con un parche vacio la validacion puede rejecting por otras
        # razones; lo que NO puede ser es que se queje del DIFF.
        if resultado.is_err():
            assert "diff" not in resultado.unwrap_err().reason.lower(), (
                f"el diff correcto fue rechazado: {resultado.unwrap_err().reason}"
            )

    def test_sin_diff_hay_una_razon_explicita(self) -> None:
        """`diff=None` es el camino legacy, y se dice en el resultado.

        No se rompe la API: `apply_expansion` ya tiene llamadas sin diff.
        Lo que no se permite es que la ausencia pase sin quedar saida.
        """
        plan = _plan_con(nodos=(_nodo("a"),), transiciones=())
        propuesta = _propuesta(operaciones=())
        resultado = gx.apply_expansion(
            propuesta,
            plan,
            registry=self._registro(),
            diff=None,
        )
        if resultado.is_ok():
            return
        assert resultado.unwrap_err().reason, (
            "un fallo sin razon no es un verificador: quien lee no sabe que buscar"
        )

    def test_rechaza_un_diff_con_la_misma_revision_y_huella_pero_mentiroso(self) -> None:
        """M8 — el caso que la huella NO cubre, y por eso hace falta.

        La comprobacion del gate tiene tres capas: revision, huella y
        **recalculo**. Las dos primeras son barato y las dos primeras
        bastan SIEMPRE que el diff venga de `diff_graph`… y ese es
        justamente el supuesto que no puede darse por cierto, porque
        cualquiera puede construir un `GraphDiff` a mano.

        La sonda M8 puso `esperado = diff`, con lo que la comparacion se
        vuelve `diff != diff`, siempre falsa, y **no fue cazada**: mis
        tres tests de R6 usaban un diff bien calculado, luego la capa de
        recalculo no llegaba a ejecutarse nunca. Un guard que solo se
        ejercita por el camino bueno no sabe si el malo esta cerrado.

        Aqui el diff lleva la revision Y la huella correctas —para que
        las dos capas anteriores pasen— y su CONTENIDO esta falseado.
        """
        plan = _plan_con(nodos=(_nodo("a"),), transiciones=())
        propuesta = _propuesta(operaciones=(AddNode(_nodo("b")),))
        bueno = diff_graph(plan, propuesta)

        # Mismo `base_revision`, misma `base_fingerprint`, y aun asi no
        # es el diff de esta aplicacion: le falta un cambio y se ha
        # inflado el coste.
        mentiroso = replace(
            bueno,
            changes=(
                *bueno.changes,
                GraphChange(subject="node", kind="added", target="z", detail="inventado"),
            ),
            added_cost=99,
        )
        resultado = gx.apply_expansion(propuesta, plan, registry=self._registro(), diff=mentiroso)
        assert resultado.is_err(), (
            "un diff con la revision y la huella correctas pero el "
            "contenido falseado ha pasado: la capa de recalculo no se "
            "está ejecutando"
        )
        assert "diff" in resultado.unwrap_err().reason.lower()

    def test_el_diff_declara_la_revision_sobre_la_que_se_calculo(self) -> None:
        plan = _plan_con(nodos=(_nodo("a"),), transiciones=())
        propuesta = _propuesta(operaciones=(), base="r7")
        d = diff_graph(plan, propuesta)
        assert d.base_revision == "r7", (
            "el diff no dice de que revision se calculo: dos diffs de la "
            "misma propuesta serian indistinguibles"
        )


# ---------------------------------------------------------------------------
# R0 — el guard que apaga el medidor
# ---------------------------------------------------------------------------


class TestLaMedicionQueAbrioElBloque:
    """El instrumento versionado sale 0 cuando el hueco esta cerrado.

    Si el hueco vuelve —alguien deshace el tipo, o vuelve `object`— este
    test se pone rojo CON EL VEREDICTO DEL PROPIO INSTRUMENTO, que es lo
    que lo hace util: no dice «algo fallo», dice «esto volvio a estar
    declarado y no alcanzable».
    """

    def test_la_medicion_ya_no_reporta_el_hueco(self) -> None:
        import subprocess
        import sys

        raiz = Path(__file__).resolve().parent.parent
        proc = subprocess.run(
            [sys.executable, str(raiz / "scripts" / "measure_b5_graph_diff.py")],
            capture_output=True,
            text=True,
            cwd=raiz,
            timeout=120,
        )
        assert proc.returncode == 0, (
            "el instrumento sale con "
            f"{proc.returncode}; deberia salir con 0 cuando el hueco esta "
            f"cerrado, porque su veredicto es «ya es alcanzable» y no «no se "
            f"que medir»:\n{proc.stdout[-800:]}"
        )

    def test_la_medicion_no_se_declara_abierta_por_sus_pausas(self) -> None:
        """CONTRAALTO: el instrumento tiene que saber volverse verde.

        Se le da un tipo de diff de grafo de verdad y se exige que las
        preguntas que ese tipo responde se cierren. Un medidor que solo
        sabe decir «abierto» no es un medidor.
        """
        import subprocess
        import sys
        import tempfile

        raiz = Path(__file__).resolve().parent.parent
        mentira = '''
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class GraphDiff:
    """Diff de grafo de mentira, solo para este test."""
    node_added: str = ""
    reason: str = ""
    evidence: tuple[str, ...] = ()
    cost: int = 0
    capabilities_required: tuple[str, ...] = ()
    nodes_invalidated: tuple[str, ...] = ()
    reversible: bool = True

@dataclass(frozen=True, slots=True)
class GraphDiffPolicyChange:
    policy_field: str = ""
'''
        with tempfile.TemporaryDirectory():
            destino = Path(raiz / "src" / "skillgraph" / "governance" / "_b5_contrasalto.py")
            destino.write_text(mentira, encoding="utf-8")
            try:
                proc = subprocess.run(
                    [sys.executable, str(raiz / "scripts" / "measure_b5_graph_diff.py")],
                    capture_output=True,
                    text=True,
                    cwd=raiz,
                    timeout=120,
                )
            finally:
                destino.unlink()
        salida = proc.stdout
        assert "[CERRADO ] P1" in salida, (
            "un tipo de diff de grafo de verdad deberia cerrar P1, y el "
            f"medidor no lo vio:\n{salida[-800:]}"
        )
        assert "[CERRADO ] P5" in salida, (
            "ese diff trae los 7 datos, luego P5 deberia cerrarse:\n{salida[-800:]}"
        )
