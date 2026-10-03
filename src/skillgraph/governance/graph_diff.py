"""B5 — el diff como representacion COMPARABLE y SEMANTICA de un cambio.

El roadmap lo pide asi: *«que toda evolucion estructural significativa
tenga una representacion comparable, y que el diff sea semantico. No un
diff de YAML»*, y la secuencia del gate es
``Proposal -> Diff -> Policy -> Decision -> Evidence -> Apply``.

LO QUE HABIA, MEDIDO. `scripts/measure_b5_graph_diff.py` daba 6 de 6
preguntas abiertas, y la que resume el bloque era una linea:

    GraphExpansionProposal.operations: tuple[object, ...]

Un saco de operaciones sin tipar. Las tres clases existen y el
comentario del propio codigo dice «PatchOp es ADT cerrado», pero no hay
ningun `PatchOp` que las una, y la anotacion no las nombra: `object`
admite cualquier valor, luego no restringe nada. Sin representacion del
cambio, el `Diff` no es una etapa del gate: no esta.

POR QUE EL DIFF SE CALCULA Y NO SE LEE. Lo que se hace aqui es comparar
el plan que HAY con lo que la propuesta PROPONE. La consecuencia que lo
sostiene —y la unica forma de que esto no sea decoracion— es que la
propuesta puede MENTIR: si declara unas capacidades y sus operaciones
producen otras, el diff lo ve. Un diff que devolviera lo que la
propuesta declara seria un eco con mejor tipografia, y un gate que
comprueba ecos no mira nada. Por eso `GraphDiff` lleva DOS conjuntos de
capacidades, el declarado y el derivado, y la diferencia entre ellos es
informacion y no un descuido.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, TypeAlias

from skillgraph.core.errors import ValidationError

if TYPE_CHECKING:
    from skillgraph.governance.graph_expansion import (
        AddNode,
        AddTransition,
        GraphExpansionProposal,
        RemoveTransition,
    )
    from skillgraph.resources.workflow import WorkflowPlan

# ---------------------------------------------------------------------------
# ADT: el sujeto y la clase del cambio
# ---------------------------------------------------------------------------

#: Vocabulario del ROADMAP, no elegido aqui. El roadmap escribe la
#: enumeracion —«+ node, - node, ~ relation, ~ capability, ~ policy,
#: ~ budget, ~ priority, ~ evidence requirement»— y este `Literal` la
#: hace cerrada: anadir un valor es un cambio de contrato.
ChangeSubject: TypeAlias = Literal[
    "node",
    "relation",
    "capability",
    "policy",
    "budget",
    "priority",
    "evidence_requirement",
]

#: `+`, `-` y `~` del roadmap, con nombre. Un `~` aqui NO es un cambio
#: cualquiera: `removed` es una baja y `changed` es una alteracion, y el
#: gate los trata distinto porque retirar un nodo y editarlo no tienen el
#: mismo coste de reversibilidad.
ChangeKind: TypeAlias = Literal["added", "removed", "changed"]


# ---------------------------------------------------------------------------
# El parche, tipado
# ---------------------------------------------------------------------------

#: Union cerrada de las operaciones de parche. Es la pieza que faltaba:
#: las tres clases ya existian, lo que no existia era el nombre que las
#: reune, y sin el `operations: tuple[object, ...]` no restringia nada.
#:
#: `RemoveNode` NO esta, y no por olvido: el invariante I1 prohibits
#: borrar un nodo, luego una operacion que lo permitiera declararia una
#: capacidad que `apply_expansion` rechaza. El conjunto lo vigila un
#: test que lo DERIVA del arbol, para que anadir una operacion sin
#: actualizar la union se ponga rojo.
PatchOp: TypeAlias = "AddNode | AddTransition | RemoveTransition"

#: Los nombres de las clases de la union, para que el guard pueda
#: cruzarlos contra el arbol sin tener que importar el modulo.
PATCH_OP_CLASSES: frozenset[str] = frozenset({"AddNode", "AddTransition", "RemoveTransition"})


def es_patch_op(valor: object) -> bool:
    """¿Es `valor` una operacion de parche de la union cerrada?

    EXISTS, no solo ANOTADO. Un `isinstance` contra una anotacion
    Implicita no se puede hacer sin resolver el tipo en runtime, y sin
    esta comprobacion el `diff_graph` tendria que fiarse de la
    anotacion para no leer atributos de un dict.
    """
    from skillgraph.governance.graph_expansion import (
        AddNode,
        AddTransition,
        RemoveTransition,
    )

    return isinstance(valor, AddNode | AddTransition | RemoveTransition)


# ---------------------------------------------------------------------------
# Un cambio
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GraphChange:
    """Un cambio del grafo, nombrado por su EFECTO y no por su texto.

    `detail` es prosa y existe para que un humano lo lea. Lo que el gate
    lee es `subject` + `kind` + `target`: los tres son cerrados o
    acotados, y sin ellos un cambio no se puede decidir.
    """

    subject: ChangeSubject
    kind: ChangeKind
    target: str
    detail: str


# ---------------------------------------------------------------------------
# El diff
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GraphDiff:
    """La representacion COMPARABLE de un cambio estructural.

    Cada campo responde a una de las siete preguntas del roadmap:

    ===========================  =====================================
    Campo                        Pregunta
    ===========================  =====================================
    ``changes``                  ¿que cambia?
    ``reason``                   ¿por que?
    ``evidence``                 ¿que evidencia lo justifica?
    ``added_cost``               ¿que coste anade?
    ``required_capabilities``    ¿que capacidades exige?  (DERIVADO)
    ``declared_capabilities``    ¿que capacidades declara? (lo que dice)
    ``invalidated_nodes``        ¿que nodos invalida?
    ``reversible``               ¿es reversible?
    ``base_revision``            ¿sobre que revision se calculo?
    ``base_fingerprint``          ¿sobre que ESTADO se calculo?
    ===========================  =====================================

    **POR QUE HAY UNA HUELLA Y NO SOLO UNA REVISION.** La primera
    version solo llevaba `base_revision`, y se rompio de una forma que
    solo se ve ejecutando: con un parche VACIO, el diff sale vacio sea
    cual sea el plan, luego un diff calculado sobre un grafo se
    aceptaba como si fuera el de otro. La revision no distingue porque
    dos estados pueden compartir revision —un mismo `r1` antes y
    despues de un apply—.

    Sin la huella, R6 no se puede cumplir: el gate no tiene forma de
    decir «este diff es de ESTA aplicacion», y *conectar != contener*
    (WI-102) se queda en buena intencion. La huella es lo que ata el
    diff al estado, y por eso se calcula sobre una serializacion
    ESTABLE del plan: si dos planes dan la misma huella, son el mismo
    estado para los fines del diff, y si dan distinta, el diff es de
    otro.

    **POR QUE DOS CONJUNTOS DE CAPACIDADES.** `required_capabilities` es
    lo que las operaciones producen, DERIVADO del plan. Lo que la
    propuesta dice va a `declared_capabilities`. Que sean distintos no
    es un defecto del diff: es el hallazgo. Un gate que solo mirase la
    declaracion estaria validando la intencion del autor, que es
    justamente lo que un gate no debe hacer.
    """

    changes: tuple[GraphChange, ...]
    reason: str
    evidence: tuple[str, ...]
    added_cost: int
    required_capabilities: tuple[str, ...]
    declared_capabilities: tuple[str, ...]
    invalidated_nodes: tuple[str, ...]
    reversible: bool
    base_revision: str
    base_fingerprint: str

    # -- Las preguntas, como metodos -------------------------------------
    #
    # No como propiedades calculadas: un `diff.respuestas()` que
    # componga las siete es donde se lee si el diff las contesta todas,
    # y hace imposible olvidar una al escribir el codigo de decision.

    def respuestas(self) -> dict[str, object]:
        """Las siete preguntas del roadmap, con su respuesta."""
        discrepancia = sorted(set(self.declared_capabilities) ^ set(self.required_capabilities))
        return {
            "que_cambia": self.changes,
            "por_que": self.reason,
            "que_evidencia_lo_justifica": self.evidence,
            "que_coste_anade": self.added_cost,
            "que_capacidades_exige": self.required_capabilities,
            "que_capacidades_declara": self.declared_capabilities,
            "discrepancia_de_capacidades": discrepancia,
            "que_nodos_invalida": self.invalidated_nodes,
            "si_es_reversible": self.reversible,
        }

    def es_coherente(self) -> bool:
        """¿Lo que la propuesta DECLARA es lo que su parche PRODUCE?

        Esto no es un accessor. Es la pregunta que hace que el diff sea
        un diff y no un eco, y por eso tiene nombre propio.
        """
        return set(self.declared_capabilities) == set(self.required_capabilities)

    def to_dict(self) -> dict[str, object]:
        """Serializacion ESTABLE.

        El orden lo fija el literal del diccionario, no el hash de un
        set: dos escrituras del mismo diff tienen que dar el mismo
        texto, o dos aplicaciones de la misma propuesta no se podrian
        comparar. Es el error de B3 (`tuple(set)`) aplicado aqui a
        proposito.
        """
        return {
            "base_revision": self.base_revision,
            "base_fingerprint": self.base_fingerprint,
            "changes": [
                {
                    "subject": c.subject,
                    "kind": c.kind,
                    "target": c.target,
                    "detail": c.detail,
                }
                for c in self.changes
            ],
            "reason": self.reason,
            "evidence": list(self.evidence),
            "added_cost": self.added_cost,
            "required_capabilities": sorted(self.required_capabilities),
            "declared_capabilities": sorted(self.declared_capabilities),
            "invalidated_nodes": sorted(self.invalidated_nodes),
            "reversible": self.reversible,
        }


# ---------------------------------------------------------------------------
# El calculo
# ---------------------------------------------------------------------------


def _nodos_del_plan(plan: WorkflowPlan) -> tuple[str, ...]:
    return tuple(sorted(n.name for n in plan.nodes))


def _aristas_del_plan(plan: WorkflowPlan) -> tuple[tuple[str, str, str], ...]:
    """`(from, outcome, to)` ordenado.

    Ordenado por construccion, no con `sorted()` al construir el diff: el
    plan puede traer las transiciones en cualquier orden y dos planes
    iguales deben dar el mismo diff.
    """
    return tuple(sorted((t.source, t.outcome, t.target) for t in plan.transitions))


def _capacidades_de(plan: WorkflowPlan) -> frozenset[str]:
    return frozenset(c for n in plan.nodes for c in n.capabilities)


def huella_del_plan(plan: WorkflowPlan) -> str:
    """SHA-256 de una serializacion ESTABLE del plan.

    ESTABLE de verdad, no "casi": los nodos y las transiciones se
    ORDENAN antes de serializar, porque un `WorkflowPlan` es un valor y
    dos planes con el mismo contenido pueden traer los nodos en otro
    orden. Sin ordenar, la huella dependeria del orden de construccion y
    dos grafos iguales darian distinto — que es el error de B3
    (`tuple(set)`, ocho ordenes distintos en ocho corridas) aplicado a
    algo de lo que ahora depende un gate.

    Se usa `sort_keys=True` y sin espacios, para que el texto no dependa
    del ancho de linea ni de como este escrito el diccionario.
    """
    nodos = sorted(
        (
            {
                "name": n.name,
                "kind": n.kind,
                "capabilities": sorted(n.capabilities),
            }
            for n in plan.nodes
        ),
        key=lambda d: d["name"],
    )
    carga = {
        "nodes": nodos,
        "transitions": [list(t) for t in _aristas_del_plan(plan)],
    }
    texto = json.dumps(carga, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def diff_graph(
    plan: WorkflowPlan,
    proposal: GraphExpansionProposal,
) -> GraphDiff:
    """Compara el plan que HAY con lo que la propuesta PROPONE.

    El resultado es un `GraphDiff` que responde a las siete preguntas del
    roadmap. No muta nada, no lee disco y no depende del reloj: es una
    funcion pura sobre dos valores (AGENTS 1.3).
    """
    from skillgraph.governance.graph_expansion import (
        AddNode,
        AddTransition,
        RemoveTransition,
    )

    nodos_actual = set(_nodos_del_plan(plan))
    aristas_actual = set(_aristas_del_plan(plan))
    capacidades_actual = _capacidades_de(plan)

    cambios: list[GraphChange] = []
    nodos_propuestos: set[str] = set()
    aristas_propuestas: set[tuple[str, str, str]] = set()
    capacidades_requeridas: set[str] = set()
    nodos_invalidados: set[str] = set()

    for operacion in proposal.operations:
        if not es_patch_op(operacion):
            raise ValidationError(
                f"operacion de parche no valida: {operacion!r} "
                f"({type(operacion).__name__}). La union PatchOp es "
                f"cerrada y solo admite "
                f"{sorted(PATCH_OP_CLASSES)}: una operacion fuera de la "
                f"union no se puede comparar, luego no se puede decidir."
            )
        if isinstance(operacion, AddNode):
            nombre = operacion.node.name
            nodos_propuestos.add(nombre)
            capacidades_requeridas.update(operacion.node.capabilities)
            if nombre in nodos_actual:
                # El nodo ya existe: re-declararlo cambia sus
                # capacidades, y eso es un `~`, no un `+`.
                if set(operacion.node.capabilities) - capacidades_actual:
                    cambios.append(
                        GraphChange(
                            subject="capability",
                            kind="changed",
                            target=nombre,
                            detail=(
                                f"el nodo {nombre} ya existe y esta propuesta le anade capacidades"
                            ),
                        )
                    )
                continue
            cambios.append(
                GraphChange(
                    subject="node",
                    kind="added",
                    target=nombre,
                    detail=f"nuevo nodo {nombre} de kind {operacion.node.kind}",
                )
            )
        elif isinstance(operacion, AddTransition):
            t = operacion.transition
            clave = (t.source, t.outcome, t.target)
            aristas_propuestas.add(clave)
            if clave in aristas_actual:
                continue
            cambios.append(
                GraphChange(
                    subject="relation",
                    kind="added",
                    target=f"{t.source} --{t.outcome}--> {t.target}",
                    detail=(f"nueva transicion {t.source} --{t.outcome}--> {t.target}"),
                )
            )
        elif isinstance(operacion, RemoveTransition):
            # Quitar una relacion invalida el nodo de origen: deja de
            # tener por donde llegar. Es la unica invalidacion que este
            # diff deduce, y se deduce de la operacion, no se declara.
            nodos_invalidados.add(operacion.from_node)
            cambios.append(
                GraphChange(
                    subject="relation",
                    kind="removed",
                    target=f"{operacion.from_node} --{operacion.outcome}--> ?",
                    detail=(
                        f"retira la transicion de {operacion.from_node} "
                        f"con outcome {operacion.outcome}"
                    ),
                )
            )

    # Los nodos y aristas que ESTAN y la propuesta no menciona no se
    # tocan: un diff describe el cambio, no re-lista el mundo entero.
    # Un diff que listara todo el grafo seria comparable, pero dejaria
    # de ser legible: el ojo busca lo que cambia.
    #
    # Lo que SI se anade es el coste: el tamano del cambio es lo que la
    # cuarta pregunta pide, y sale del propio diff.
    coste = len(cambios)

    return GraphDiff(
        changes=tuple(cambios),
        reason=proposal.problem_observed,
        evidence=tuple(proposal.evidence),
        added_cost=coste,
        required_capabilities=tuple(sorted(capacidades_requeridas)),
        declared_capabilities=tuple(sorted(proposal.capabilities_needed)),
        invalidated_nodes=tuple(sorted(nodos_invalidados)),
        reversible=bool(proposal.rollback_plan),
        base_revision=proposal.base_revision,
        base_fingerprint=huella_del_plan(plan),
    )


def el_diff_corresponde(
    diff: GraphDiff,
    proposal: GraphExpansionProposal,
    plan: WorkflowPlan,
) -> str | None:
    """¿Es este diff el de ESTA aplicacion? `None` si lo es.

    Tres cosas tienen que cuadrar, y las tres son comprobables sin
    preguntar a nadie:

      1. la REVISION — el diff se calculo sobre otra base
      2. el PARCHE — el diff no describe las operaciones de esta
         propuesta
      3. el ESTADO — el diff se calculo sobre otro plan

    La segunda es la que importa. Un diff calculado sobre el plan
    correcto pero de OTRA propuesta es un diff valido y equivocado, y es
    justo el caso que un gate tiene que cazar: si no, basta con
    recalcular el diff una vez y reutilizarlo para siempre.

    Se recalcula el diff aqui y se compara. Es lo caro que es de
    correcto: recalcular es una funcion pura sobre dos valores, y
    comparar el resultado es la unica forma de saber que el diff que
    trae el llamante es el que la policy deberia mirar. Aceptar un
    diff «parecido» seria aceptar un diff que nadie ha comprobado.
    """
    if diff.base_revision != proposal.base_revision:
        return (
            f"B5: el diff se calculo sobre la revision "
            f"{diff.base_revision!r} y la propuesta declara "
            f"{proposal.base_revision!r}. Un diff de otra revision no "
            f"describe este cambio."
        )

    huella_esperada = huella_del_plan(plan)
    if diff.base_fingerprint != huella_esperada:
        return (
            f"B5: el diff se calculo sobre otro ESTADO del grafo. Este "
            f"plan tiene la huella {huella_esperada[:12]}… y el diff trae "
            f"{diff.base_fingerprint[:12]}…. La revision no basta: dos "
            f"estados pueden compartir revision, y sin la huella un diff "
            f"de otro grafo pasaria por suyo."
        )

    esperado = diff_graph(plan, proposal)
    if diff != esperado:
        return (
            f"B5: el diff no corresponde a esta aplicacion. Trae "
            f"{len(diff.changes)} cambios y el parche de esta propuesta "
            f"sobre este plan produce {len(esperado.changes)}. Un diff que "
            f"no se puede reproducir aqui no es unaStage del gate, es un "
            f"parametro."
        )
    return None
