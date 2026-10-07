"""Subcomandos `sg knowledge` (WI-54 corte 5, ADR-0018).

Quinto corte del estrangulamiento H-02: los 5 handlers
`cmd_knowledge_*` salen de `cli/runner.py` verbatim.
`_open_known_project` es compartida (3 usos fuera del cluster) y vive
en `cli.support`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from skillgraph.cli.support import EXIT_OK, exit_para, resolve_project
from skillgraph.core.errors import ParseError, SkillGraphError
from skillgraph.core.recipe import ContextRecipe
from skillgraph.knowledge.assembly import registro_de_conocimiento
from skillgraph.knowledge.authority import Resolution
from skillgraph.knowledge.code_analysis import CODE_ANALYSIS, KIND_FICHERO
from skillgraph.knowledge.context_controller import (
    ContextController,
    OutcomeTracer,
)
from skillgraph.knowledge.graph import Source, source_id
from skillgraph.knowledge.knowledge_controller import KnowledgeController
from skillgraph.knowledge.observation import envelope_de_payload
from skillgraph.knowledge.observation_ingestion import ingerir
from skillgraph.platform.paths import DEFAULT_TENANT, resolve_data_root
from skillgraph.platform.ports.capabilities import CapabilityRequest
from skillgraph.platform.storage import Storage
from skillgraph.runtime.engine import now_iso


@contextmanager
def _open_known_project(
    args: argparse.Namespace,
    project: str,
) -> Iterator[tuple[str, str, Storage]]:
    """Valida el proyecto y posee el Storage durante el bloque `with`.

    Raises:
        FileNotFoundError: si el proyecto no esta registrado en el
            catalog (con mensaje legible para el operador).
    """
    p, err = resolve_project(args, project)
    if err is not None:
        data_root = resolve_data_root(args.data_root)
        raise FileNotFoundError(
            f"proyecto {project!r} no encontrado en el catalog "
            f"(tenant={DEFAULT_TENANT!r}, data_root={data_root}); "
            f"crealo primero con 'sg project create <name>'"
        )
    storage = Storage(Path(p["db_path"]))
    try:
        yield p["tenant_id"], project, storage
    finally:
        storage.close()


def cmd_knowledge_stale(args: argparse.Namespace) -> int:
    """Lista Claims stale del proyecto."""

    with _open_known_project(args, args.project) as (tenant_id, project_id, storage):
        ctl = KnowledgeController(knowledge=storage, tenant_id=tenant_id, project_id=project_id)
        stale = ctl.list_stale_claims()
        print(f"stale claims ({len(stale)}):")
        for c in stale:
            print(f"  - {c.claim_id}  {c.predicate}={c.object_literal} stale=true")
        return EXIT_OK


def cmd_knowledge_invalidate(args: argparse.Namespace) -> int:
    """Invalida Claims dependientes de un source."""

    with _open_known_project(args, args.project) as (tenant_id, project_id, storage):
        ctl = KnowledgeController(knowledge=storage, tenant_id=tenant_id, project_id=project_id)
        invalidated = ctl.invalidate_from_source(
            source_id=args.source,
            max_hops=args.max_hops,
        )
        print(f"invalidated {len(invalidated)} claim(s) from source={args.source}")
        for cid in invalidated:
            print(f"  - {cid}")
        return EXIT_OK


def cmd_knowledge_refresh(args: argparse.Namespace) -> int:
    """Re-valida Claims contra nueva revision."""

    with _open_known_project(args, args.project) as (tenant_id, project_id, storage):
        ctl = KnowledgeController(knowledge=storage, tenant_id=tenant_id, project_id=project_id)
        reactivated = ctl.refresh_source(
            source_id=args.source,
            new_revision=args.revision,
        )
        print(f"reactivated {len(reactivated)} claim(s)")
        for cid in reactivated:
            print(f"  - {cid}")
        return EXIT_OK


def cmd_knowledge_compile(args: argparse.Namespace) -> int:
    """Compila un handoff desde una receta inline."""

    from skillgraph.knowledge.knowledge_controller import KnowledgeController

    with _open_known_project(args, args.project) as (tenant_id, project_id, storage):
        ctl = KnowledgeController(knowledge=storage, tenant_id=tenant_id, project_id=project_id)
        # WI-109: la recipe es ENTRADA DE USUARIO y va como JSON literal.
        # Este `json.loads` estaba fuera del `try`, y `JSONDecodeError` no
        # es `SkillGraphError`, asi que un `{` mal cerrado salia como
        # Traceback con rc=1 de Python en vez de como error de dominio.
        try:
            recipe_raw = (
                json.loads(args.recipe)
                if args.recipe.startswith("{")
                else {
                    "obligatory": [{"kind": "source", "value": args.recipe}],
                    "freshness_policy": "strict" if args.strict else "best_effort",
                    "token_budget": args.token_budget,
                    "overflow_strategy": args.overflow,
                }
            )
        except json.JSONDecodeError as exc:
            # Conversion inmediata a un error de dominio tipado: la
            # frontera con `json` no es nuestra, pero el significado si.
            raise ParseError(
                f"recipe JSON invalido: {exc}. Pasa un source_id o un JSON literal completo."
            ) from exc
        recipe = ContextRecipe.from_dict(recipe_ref=args.recipe, raw=recipe_raw)
        ctx = ContextController(knowledge=ctl)
        try:
            handoff = ctx.compile_handoff(
                recipe=recipe,
                run_id=args.run or "cli-run",
                node_execution_id=args.node or "cli-node",
                source_revision=args.revision or "HEAD",
            )
        except SkillGraphError as exc:
            # WI-109: el `code` decide el exit code. Estas tres ramas
            # devolvian EXIT_DOMAIN las tres, y la ultima la alcanzaba
            # todo lo demas: no distinguian nada, solo parecían hacerlo.
            print(f"ERROR ({exc.code}): {exc}", file=sys.stderr)
            return exit_para(exc)
        print(json.dumps(handoff.to_dict(), indent=2, ensure_ascii=False))
        print(f"--- context_hash: {handoff.context_hash}")
        return EXIT_OK


def cmd_knowledge_trace(args: argparse.Namespace) -> int:
    """Extrae un OutcomeTrace desde un run."""
    import json

    from skillgraph.knowledge.knowledge_controller import KnowledgeController

    with _open_known_project(args, args.project) as (tenant_id, project_id, storage):
        ctl = KnowledgeController(knowledge=storage, tenant_id=tenant_id, project_id=project_id)
        trace = OutcomeTracer.from_run(
            knowledge=ctl,
            run_id=args.run,
            trace_name=args.name or f"trace-{args.run}",
        )
        print(
            json.dumps(
                {
                    "trace_id": trace.trace_id,
                    "kind": trace.kind,
                    "name": trace.name,
                    "project_id": trace.project_id,
                    "created_at": trace.created_at,
                    "claim_refs": list(trace.claim_refs),
                    "evidence_refs": list(trace.evidence_refs),
                },
                indent=2,
            )
        )
        return EXIT_OK


# ---------------------------------------------------------------------------
# B28 — «¿qué creo, y por qué?»
# ---------------------------------------------------------------------------


def cmd_knowledge_resolve(args: argparse.Namespace) -> int:
    """Resuelve los conflictos de un sujeto PARA UNA INTENCION.

    **POR QUE ESTE SUBCOMANDO ES EL ENTREGABLE Y NO UN ADONO.** Sin el, la
    politica de B28 seria un eje que nadie rellena — MEDIDO en B6 que
    `extraction_method` era un `str` al que no escribia NADIE en `src/`, y por
    eso no podia ser donde viviera el origen. Un bloque que anade capacidad y
    no la deja preguntar es el mismo defecto con mas codigo.

    **Y POR QUE EL `--intent` ES OBLIGATORIO Y NO UN DEFAULT.** Es lo unico que
    separa dos respuestas distintas sobre el mismo conflicto. Poner un valor
    por defecto seria exactement el ranking global que la fila del roadmap
    acusa: la respuesta «correcta» sin preguntar. Sin `--intent` no hay
    pregunta, y sin pregunta no hay respuesta honesta.
    """
    from skillgraph.knowledge.authority import resolver

    with _open_known_project(args, args.project) as (tenant_id, project_id, storage):
        conflictos = storage.conflicts_for(
            tenant_id=tenant_id,
            project_id=project_id,
            subject_entity_id=args.subject,
            revision=args.at_revision,
        )
        if not conflictos:
            # B29: el mensaje dice DE QUE REVISION. Un «sin conflicto» a secas
            # para `--at-revision revA` es indistinguible de la respuesta de
            # HEAD, y son dos preguntas distintas: en revA no se contradice
            # nadie porque el hecho viejo era el unico cierto, no porque el
            # sistema no sepa.
            cuando = args.at_revision if args.at_revision is not None else "HEAD"
            print(
                f"{args.subject}: sin conflicto en {cuando}. "
                "Nadie se contradice, y no hay nada que resolver."
            )
            return EXIT_OK

        # Cada conflicto se resuelve CON SU PROPIA respuesta. Un sujeto con dos
        # predicados que se contradicen tiene dos respuestas, y escolher una
        # seria el mismo error de authority por el otro lado.
        resoluciones = [
            resolver(conflicto, intencion=args.intent, revision=args.at_revision)
            for conflicto in conflictos
        ]

    if args.json:
        print(
            json.dumps(
                [_como_dict(r) for r in resoluciones],
                indent=2,
                ensure_ascii=False,
            )
        )
        return EXIT_OK

    for r in resoluciones:
        for ln in _render(r):
            print(ln)
    return EXIT_OK


def _como_dict(r: Resolution) -> dict[str, object]:
    """La resolucion en JSON: la MISMA informacion que `_render` imprime.

    **POR QUE NO SE REIMPLEMENTA LA LOGICA.** Un `--json` que cuenta otra
    historia que el texto es un camino a dos verdades, y el dia que cambien
    una, el otro dira la cosa contraria sin avisar. Se deriva del mismo
    objeto.
    """
    return {
        "subject_entity_id": r.conflicto.subject_entity_id,
        "predicate": r.conflicto.predicate,
        "query_intent": r.intencion,
        "profile": r.perfil,
        "revision": r.revision,
        "winner": (
            {
                "claim_id": r.ganadora.claim_id,
                "object_literal": r.ganadora.object_literal,
                "assertion_origin": r.ganadora.assertion_origin,
            }
            if r.ganadora is not None
            else None
        ),
        "unresolved": r.sin_resolver,
        "discarded": [
            {
                "claim_id": d.afirmacion.claim_id,
                "object_literal": d.afirmacion.object_literal,
                "assertion_origin": d.afirmacion.assertion_origin,
                "motivo": d.motivo,
            }
            for d in r.descartadas
        ],
    }


def _render(r: Resolution) -> list[str]:
    """La resolucion explicada, como texto.

    **POR QUE NO ES JSON POR DEFECTO.** El campo `perfil` y los `motivo` de
    descarte existen para que un humano entienda por que gano una y perdio la
    otra; un `json.dumps` lo esconde detras de una coma. `--json` lo da
    cuando lo que se quiere es el dato, no la lectura.
    """
    # B29: la linea dice DE QUE REVISION se responde. Sin ella, un «gana
    # NADIE» no se puede distinguir de una pregunta hecha en el instante
    # equivocado — y esa es exactamente la confusion que el bloque cierra.
    cuando = r.revision if r.revision is not None else "HEAD"
    out = [
        f"conflicto: {r.conflicto.subject_entity_id} {r.conflicto.predicate}",
        f"  pregunta:   {r.intencion}  (politica: {r.perfil}, revision: {cuando})",
    ]
    if r.ganadora is not None:
        out.append(f"  gana:       {r.ganadora.claim_id} = {r.ganadora.object_literal!r}")
    else:
        out.append("  gana:       NADIE — la politica no pudo elegir")
    if r.sin_resolver:
        out.append(
            f"  sin resolver: {len(r.elegidas)} afirmaciones empatadas en la misma jerarquia"
        )
    for d in r.descartadas:
        out.append(
            f"  descartada: {d.afirmacion.claim_id} = {d.afirmacion.object_literal!r}  [{d.motivo}]"
        )
    return out


# ---------------------------------------------------------------------------
# B34 — LAS SEIS PREGUNTAS, Y UN SOLO MODELO DETRAS
# ---------------------------------------------------------------------------


def _superficie(storage: object, tenant_id: str, project_id: str) -> object:
    """La superficie, sobre el `Storage` abierto.

    **POR QUE ESTA EN UN SITIO Y NO EN CADA HANDLER.** Los seis handlers
    de abajo son casi iguales: abren el proyecto, construyen una `Consulta`,
    llaman a `responder` y renderizan. Si cada uno construyera su propia
    superficie, habria seis caminos por los que podrian divergir —y en el
    momento en que divergieran, el gate del bloque («las mismas query
    models alimentan CLI y agent handoff») seria verdad en el papel y falso
    en el codigo.

    La anotacion es `object` y no el ADT concreto a proposito: este modulo
    es la CAPA DE I/O y habla con el puerto, no con el ADT. Es la misma
    linea que `KnowledgeQueryCapability` con `KnowledgeRepository`.
    """
    from skillgraph.knowledge.superficie import SuperficieConocimiento

    return SuperficieConocimiento(storage, tenant_id=tenant_id, project_id=project_id)


def _pregunta(args: argparse.Namespace, nombre: str) -> object:
    """La `Consulta` de la superficie, desde los flags de la CLI.

    **POR QUE UN CONSTRUCTOR Y NO SEIS CALLS DISTINTAS.** Los tres campos
    opcionales (`claim_id`, `revision`, `commit`) son los mismos para todas
    las preguntas y solo algunos tienen sentido en cada una. Dejarlos en
    `getattr(args, ..., None)` significa que quien anada un flag no tiene
    que acordarse de anadirlo en los seis sitios, y el que se acuerde
    desaparece en cuanto anade el septimo.
    """
    from skillgraph.knowledge.superficie import Consulta

    return Consulta(
        pregunta=nombre,
        subject=args.subject,
        claim_id=getattr(args, "claim_id", None),
        revision=getattr(args, "at_revision", None),
        commit=getattr(args, "commit", None),
    )


def _responder_y_salir(args: argparse.Namespace, nombre: str) -> int:
    """Abre, pregunta, renderiza. El cuerpo comun de los seis.

    Se escribe UNA vez y se llama seis veces, y esa es la forma de que «las
    mismas query models alimentan la CLI» sea una propiedad del codigo: si
    un subcomando tuviera su propio camino, este helper dejaria de ser el
    camino y el guard que lo mide dejaria de ver nada.
    """
    from skillgraph.knowledge.superficie import respuesta_a_payload

    with _open_known_project(args, args.project) as (tenant_id, project_id, storage):
        respuesta = _superficie(storage, tenant_id, project_id).responder(_pregunta(args, nombre))
        if args.json:
            salida = json.dumps(respuesta_a_payload(respuesta), indent=2, ensure_ascii=False)
        else:
            salida = "\n".join(_render_respuesta(respuesta))

    print(salida)
    return EXIT_OK


def cmd_knowledge_what(args: argparse.Namespace) -> int:
    """Lo que se afirma del sujeto. Todas las afirmaciones, sin jerarquizar.

    No resuelve: `what` pregunta por lo que se AFIRMA, no por lo que es
    cierto. Quien quiera lo segundo lo pregunta con `conflicts` y un
    `--intent`, que es donde el sistema sabe cual es lo segundo.
    """
    return _responder_y_salir(args, "what")


def cmd_knowledge_why(args: argparse.Namespace) -> int:
    """Por que se AFIRMO esa afirmacion. Procedencia, no causa.

    **LO QUE ESTE SUBCOMANDO NO PROMETE.** No responde «por que el mundo es
    como es»: responde de donde salio ESTA afirmacion, con su evidencia, su
    fuente, quien la extrajo y a que claim reemplaza. El sistema tiene
    procedencia, no causalidad, y el nombre corto no puede prometer mas de
    lo que el modelo entrega.
    """
    return _responder_y_salir(args, "why")


def cmd_knowledge_impact(args: argparse.Namespace) -> int:
    """A que afecta: la arista inversa. Quien MENCIONA esta entidad."""
    return _responder_y_salir(args, "impact")


def cmd_knowledge_changed(args: argparse.Namespace) -> int:
    """Que se sabia, en una revision o desde un commit.

    Los dos relojes siguen siendo dos y no se traducen: `--at-revision` es
    el orden de observacion local (B29) y `--commit` es la ascendencia real
    (B32).
    """
    return _responder_y_salir(args, "changed")


def cmd_knowledge_conflicts(args: argparse.Namespace) -> int:
    """Que se contradice, y —con `--intent`— quien gana para que pregunta.

    Sin `--intent` devuelve los conflictos SIN resolver, que es la
    respuesta honesta a «¿qué se contradice?». Un `--intent` con valor por
    defecto seria el ranking global que B28 cerro.
    """
    return _responder_y_salir(args, "conflicts")


def cmd_knowledge_evidence(args: argparse.Namespace) -> int:
    """De donde sale cada afirmacion del sujeto."""
    return _responder_y_salir(args, "evidence")


def _render_respuesta(respuesta: object) -> list[str]:
    """La `Respuesta` en texto para una persona.

    **POR QUE UNA LINEA POR AFIRMACION Y NADA MAS.** Un handoff es un
    contrato firmado y Budget, y un texto de relleno convierte una respuesta
    en algo que hay que volver a parsear. Lo que se imprime es lo que la
    `Respuesta` trae; si un campo no aplica va vacio y no inventing informacion
    para que la linea no quede corta.
    """
    lineas = [f"{respuesta.consulta.pregunta} de {respuesta.consulta.subject}"]
    for claim in respuesta.claims:
        lineas.append(
            f"  {claim.claim_id}: {claim.predicate} = {_objeto_de(claim)}  "
            f"[{claim.assertion_origin} @ {claim.checked_at_revision}]"
        )
    for proc in respuesta.procedencia:
        origen = proc.source_id if proc.source_id is not None else "sin fuente"
        lineas.append(
            f"  procedencia {proc.claim_id}: {proc.extraction_method} "
            f"({proc.extractor_version}), origen {origen}"
        )
    if respuesta.resolucion is not None and respuesta.resolucion.ganadora is not None:
        g = respuesta.resolucion.ganadora
        lineas.append(
            f"  resuelve {respuesta.consulta.pregunta} -> {g.claim_id}: "
            f"{g.predicate} = {g.object_literal!r}"
        )
    if respuesta.vacia:
        lineas.append("  (sin resultados)")
    return lineas


def _objeto_de(claim: object) -> str:
    """El objeto de una afirmacion, sea literal o referencia.

    **POR QUE HACE FALTA Y NO ES COSMÉTICA.** MEDIDO ejecutando
    `sg knowledge impact`: imprimia `imports_module = ''` para la
    afirmacion cuyo objeto es una ENTIDAD, porque se imprimia
    `object_literal` y en ese caso vale `None`. Un `''` no es «no tiene
    objeto»: es «tiene un objeto que este render no sabe pintar», que es
    justo la clase de linea que hace que una persona deje de fiarse de la
    salida.

    B25 declaro que el objeto es **exactamente uno**: literal o entidad.
    El render tiene que honourar las dos mitades.
    """
    # MEDIDO dos veces. La primera uso `object_entity`, que es lo que lleva
    # el ADT `Claim`, y seguio imprimiendo `''`: lo que devuelve el puerto
    # es `StoredClaim`, y ese campo se llama `object_entity_id` con el
    # criterio de XOR del repo —`""` significa LITERAL, un id significa
    # ENTIDAD—. Un `''` no era un fallo de formato: era un campo leido del
    # objeto equivocado, y el codigo no decia nada porque `getattr` con
    # default devuelve `None` en vez de fallar.
    entidad = getattr(claim, "object_entity_id", "")
    if entidad:
        return f"-> {entidad}"
    return repr(getattr(claim, "object_literal", None))


# ---------------------------------------------------------------------------
# B35 — la puerta: el operador llega a la capability por la CLI
# ---------------------------------------------------------------------------
#
# MEDIDO antes de escribir esto (`scripts/measure_b35_vertical.py`, ronda 4):
# por AST sobre los imports de `cli/`, NINGUNO. Ni `code_analysis`, ni
# `telemetry_query`, ni `knowledge_query`, ni `CapabilityRegistry`. Y el texto
# de la CLI SI contiene `KnowledgeQueryCapability` —dentro de un docstring que
# lo describe en pasado—, que es exactamente como un instrumento que busca por
# texto dice que una puerta existe porque alguien escribio una frase sobre ella.


def cmd_knowledge_ingest_code(args: argparse.Namespace) -> int:
    """Analiza un fichero y convierte el analisis en afirmaciones.

    **ESTA ES LA VERTICAL COMPLETA, Y ANTES NO HABIA NINGUNA.** Antes de
    B35, `sg.code.analysis` solo se podia lanzar escribiendo Python: leer el
    fichero, construir la `Source`, montar la capability, invocar, deserializar
    el envelope e ingerirlo. Seis pasos, ninguno con puerta.

    Returns:
        `EXIT_OK` si el analisis se ingirio.
    """
    ruta = Path(args.file)
    contenido = ruta.read_text(encoding="utf-8")
    # **POR QUE LA REVISION ES EL HASH DEL CONTENIDO.** `revision` es el reloj
    # epistemico de `checked_at_revision`, y para un fichero local lo que
    # cambia es su contenido: si el fichero cambia, cambia el hash, luego la
    # revision cambia y lo anterior queda en la suya en vez de contradecir al
    # nuevo. Un `--revision` explicito lo deja forzar, para cuando el
    # contenido no es lo que define la version.
    huella = hashlib.sha256(contenido.encode("utf-8")).hexdigest()
    revision = args.revision or huella
    # El instante SI se lee aqui y no en la capability, y NO rompe la
    # idempotencia: MEDIDO, el `claim_id` se deriva de (sujeto, predicado,
    # objeto, fuente, revision) y `observed_at` NO esta dentro. La capability no
    # puede leerlo porque es codigo externo al repo (AGENTS 1.3); el operador
    # si, porque el operador es el que esta ejecutando.
    observado_en = now_iso()

    with _open_known_project(args, args.project) as (tenant_id, project_id, storage):
        fuente = Source(
            source_id=source_id(f"local:{ruta}"),
            kind=KIND_FICHERO,
            content_hash=huella,
            locator={"path": str(ruta)},
            git_commit_sha=None,
            git_tree_sha=None,
            working_tree_status=None,
            checked_at=observado_en,
            freshness="current",
        )
        storage.register_source(tenant_id=tenant_id, project_id=project_id, source=fuente)

        registro = registro_de_conocimiento(
            storage,
            tenant_id=tenant_id,
            project_id=project_id,
            source_id=str(fuente.source_id),
            revision=revision,
        )
        # `resolve` y no la clase: este comando no sabe QUE capability hay,
        # sabe que pide UNA por nombre. Y si el registro no la tiene, el error
        # dice que hay, que es lo unico que evita el `ls` a mano.
        capability = registro.resolve(CODE_ANALYSIS)
        resultado = capability.invoke(
            CapabilityRequest(
                spec=capability.spec,
                subject=str(ruta),
                arguments={
                    "path": str(ruta),
                    "content": contenido,
                    "observed_at": observado_en,
                },
            )
        )
        # **Y AQUI ESTA EL PASO QUE FALTABA.** El `dict` del payload -> el
        # `ObservationEnvelope` que `ingerir` exige. MEDIDO: esa traduccion
        # estaba escrita a mano en DOS ficheros de test, y ya divergian.
        envelope = envelope_de_payload(resultado.payload["envelope"])
        ingesta = ingerir(storage, tenant_id=tenant_id, project_id=project_id, env=envelope)

        print(f"analizado {ruta}  revision={revision}")
        for claim in ingesta.claims:
            print(f"  - {claim.predicate} = {claim.object_literal!r}")
        print(f"{len(ingesta.claims)} afirmacion(es) escritas")
        return EXIT_OK
