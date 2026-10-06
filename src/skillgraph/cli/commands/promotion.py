"""Subcomandos `sg promotion` (WI-54 corte 3, ADR-0018).

Tercer corte del estrangulamiento H-02: los 3 handlers
`cmd_promotion_*` y sus helpers privados salen de `cli/runner.py`
verbatim. Los helpers compartidos con `cmd_run` (importador de
claims, failpoints, payload de entidad) viven en `cli.support`.
"""

from __future__ import annotations

import argparse
import dataclasses
import os
import sys
from pathlib import Path
from typing import Final, NoReturn

from skillgraph.cli.support import (
    EXIT_DOMAIN,
    EXIT_OK,
    resolve_project,
)
from skillgraph.knowledge.graph import Claim, Source
from skillgraph.platform.storage import Storage
from skillgraph.runtime.engine import now_iso


def _apply_pending_promotions(
    storage: Storage,
    dest_storage: Storage,
    *,
    tenant_id: str,
    target_project: str,
) -> list[dict[str, str]]:
    """Aplica cada propuesta pendiente y devuelve su estado final.

    El apply escribe en la base del PROYECTO DESTINO: el outbox vive en
    origen y el claim promovido vive en destino. La idempotencia es del
    storage destino (upserts), no de este bucle, asi que re-invocar el
    comando tras un crash completa la operacion sin duplicar.

    Los failpoint se disparan aqui porque son los unicos puntos donde el
    estado queda a medio camino:
    - `before_apply`: tras leer las pendientes, antes de aplicar ninguna.
    - `mid_apply`: tras marcar IN_PROGRESS, antes del apply de negocio.
    - `after_apply_first`: DENTRO del apply de la primera, entre el
      efecto de negocio y el marcado PUBLISHED. Es el unico punto real
      de estado partido: el claim ya esta en destino y el outbox sigue
      sin publicar. Colocarlo despues de `apply_proposal` no serviria
      de nada, porque ahi el outbox ya quedo PUBLISHED.

    Args:
        storage: outbox de origen (donde viven las propuestas).
        dest_storage: base destino (donde se registran los claims).
        tenant_id: tenant de la promocion.
        target_project: nombre del proyecto destino.

    Returns:
        Una entrada `{"proposal_id", "status"}` por propuesta aplicada.
    """
    from skillgraph.governance.promotion import apply_proposal

    base_apply = _default_claim_importer(
        dest_storage, tenant_id=tenant_id, target_project=target_project
    )
    failpoint = _select_promotion_failpoint()
    if failpoint == "before_apply":
        _abort_with_failpoint(failpoint)

    crashed = False

    def apply_fn(payload: dict) -> bool:
        """Aplica al destino y, si toca, deja el estado partido."""
        nonlocal crashed
        ok = base_apply(payload)
        if failpoint == "after_apply_first" and not crashed:
            crashed = True
            _abort_with_failpoint(failpoint)
        return ok

    results: list[dict[str, str]] = []
    for proposal in storage.list_pending_promotions():
        if failpoint == "mid_apply":
            storage.mark_promotion_in_progress(proposal["proposal_id"])
            _abort_with_failpoint(failpoint)

        final_status = apply_proposal(storage, proposal["proposal_id"], apply_fn=apply_fn)
        results.append({"proposal_id": proposal["proposal_id"], "status": final_status})
    return results


def _reconcile_summaries(results: list[dict[str, str]]) -> tuple[int, int]:
    """Cuenta (publicadas, fallidas) sobre los resultados del reconcile.

    Funcion pura: no toca storage ni imprime. Solo cuenta los dos estados
    que el comando conoce, de modo que un estado nuevo no altera el
    recuento por accidente.

    Args:
        results: entradas `{"proposal_id", "status"}` del reconcile.

    Returns:
        Par (published, failed). La lista vacia da (0, 0).
    """
    published = sum(1 for r in results if r["status"] == "PUBLISHED")
    failed = sum(1 for r in results if r["status"] == "FAILED")
    return published, failed


def _default_claim_importer(storage: Storage, *, tenant_id: str, target_project: str):
    """apply_fn por defecto: importa al proyecto destino lo que el claim
    referenciado necesita (source -> entity -> claim), reutilizando las
    APIs idempotentes de Storage (upsert_source/upsert_entity/record_claim,
    todas INSERT OR IGNORE/REPLACE). Asi el apply es re-ejecutable sin
    duplicar: la idempotencia es del storage destino, no del caller.

    El payload lo produce `cmd_promotion_submit`:
    {source, entity, claim, source_project, target_project}.
    Devuelve True si el claim quedó registrado en destino (o ya estaba).
    """

    from skillgraph.knowledge.graph import Claim, Entity, entity_ref

    def _apply(payload: dict) -> bool:
        c = payload.get("claim")
        if not isinstance(c, dict):
            return False
        s = payload.get("source")
        if isinstance(s, dict) and s.get("source_id"):
            storage.register_source(
                tenant_id=tenant_id,
                project_id=target_project,
                source=Source(
                    source_id=s["source_id"],
                    kind=s.get("kind", "local_file"),
                    content_hash=s.get("content_hash", "promoted"),
                    locator=s.get("locator", {}),
                    git_commit_sha=s.get("git_commit_sha"),
                    git_tree_sha=s.get("git_tree_sha"),
                    working_tree_status=s.get("working_tree_status"),
                    checked_at=s.get("checked_at") or now_iso(),
                    freshness=s.get("freshness", "fresh"),
                ),
            )
        e = payload.get("entity")
        if isinstance(e, dict) and e.get("entity_id"):
            storage.upsert_entity(
                tenant_id=tenant_id,
                project_id=target_project,
                entity=Entity(
                    entity_id=e["entity_id"],
                    kind=e.get("kind", "module"),
                    stable_key=e.get("stable_key", e["entity_id"]),
                ),
            )
        claim = Claim(
            claim_id=c["claim_id"],
            subject_entity_id=c["subject_entity_id"],
            predicate=c["predicate"],
            object_literal=c["object_literal"],
            source_id=c["source_id"],
            evidence_ids=tuple(c.get("evidence_ids", ()) or ()),
            # El origen se propaga en la promocion. Sin esta linea, un
            # Claim promovido de un proyecto a otro perderia quien lo
            # afirmaba y volvería a `observed`, que es exactamente la
            # perdida de provenance que el gate B6 prohibe.
            assertion_origin=c.get("assertion_origin", "observed"),
            extraction_method=c.get("extraction_method", "static_analysis"),
            extractor_version=c.get("extractor_version", "unknown"),
            checked_at_revision=c.get("checked_at_revision", "unknown"),
            # B26: la referencia a entidad se reconstruye AQUI, con el smart
            # constructor, en vez de asumir que no la hay. Antes se leia
            # `c["object_literal"]` y nada mas, y un claim promovido con objeto-
            # entidad llegaba sin el: el `Claim` se construia sin objeto, la
            # invariante de B25 lo rechazaba, y el fallo salia EN EL PROYECTO
            # DESTINO, que es el que nadie mira.
            #
            # Se conserva la lectura por clave, y no un `ObservationEnvelope`,
            # porque el payload de promocion tiene su propio contrato —lo
            # escribe `cmd_promotion_submit` y puede venir de un outbox de otra
            # epoca—. Lo que B26 cambia no es el contrato del payload: es que
            # la conversion pasa por los constructores que validan, y no por
            # asumir que un campo no existe.
            object_entity=entity_ref(c["object_entity_id"]) if c.get("object_entity_id") else None,
        )
        storage.record_claim(tenant_id=tenant_id, project_id=target_project, claim=claim)
        return True

    return _apply


def _source_to_payload(
    storage: Storage,
    *,
    tenant_id: str,
    project_id: str,
    source_id: str,
) -> dict | None:
    """Serializa una Source del proyecto origen para el payload de promocion.

    Delega en ``Storage.get_source`` (API publica, refactor H9-BSlice2).
    Devuelve el mismo formato ``dict`` que antes para mantener compatibilidad
    con el payload JSON que escribe ``promotion.submit_proposal``.

    Mejora de aislamiento: el filtro original usaba solo ``source_id`` +
    ``tenant_id`` (sin ``project_id``), lo que permitia colisiones entre
    proyectos del mismo tenant con mismo ``source_id``. El nuevo filtro
    discrimina tambien por proyecto: mas estricto, mas correcto
    (cumple blueprint 09 'aislamiento por proyecto').
    """
    source = storage.get_source(tenant_id=tenant_id, project_id=project_id, source_id=source_id)
    if source is None:
        return None
    import dataclasses
    import json as _json

    d = dataclasses.asdict(source)
    # `asdict` no deserializa los JSON strings; replicamos el parseo previo.
    for k in ("locator", "working_tree_status"):
        if isinstance(d.get(k), str):
            try:
                d[k] = _json.loads(d[k])
            except (ValueError, TypeError):
                d[k] = {}
        elif d.get(k) is None:
            d[k] = {}
    return d


def _entity_to_payload(
    storage: Storage,
    *,
    tenant_id: str,
    project_id: str,
    entity_id: str,
) -> dict | None:
    """Serializa una Entity del proyecto origen para el payload de promocion.

    Delega en ``Storage.get_entity`` (API publica, refactor H9-BSlice2).
    Misma nota de aislamiento que ``_source_to_payload``.
    """
    import dataclasses

    entity = storage.get_entity(tenant_id=tenant_id, project_id=project_id, entity_id=entity_id)
    if entity is None:
        return None
    return dataclasses.asdict(entity)


def _claim_to_payload(claim: Claim) -> dict:
    """Serializa un Claim del proyecto origen para el payload de promocion.

    Se extrae del `cmd_promotion_submit` para que el test pueda verificar
    el payload contra el CODIGO y no contra una copia escrita en el propio
    test. Un test que reconstruye el dict a mano verifica su propia copia,
    que es el error de WI-106: las dos divergen el dia que una se
    actualiza y la otra no, y el test sigue en verde.

    `assertion_origin` va aqui por el gate B6: si el campo se perdiera al
    exportar, la promocion funcionaria y el proyecto destino recibiria
    `observed` —una afirmacion de una persona reinterpretada como
    observacion— sin que nada fallara en el proyecto origen, que es
    donde se mira.

    **B26: ESTE DICT SE DERIVA DE LA FORMA, YA NO SE ESCRIBE A MANO.** Se
    construye con `dataclasses.asdict`, y lo unico que se ajusta a mano es
    `object_entity`, porque es el unico campo que no es un valor plano: es un
    `EntityRef`, y al otro lado del payload tiene que haber un `entity_id`.

    Antes se escribian nueve claves literalmente, y B25 anadio una décima
    (`object_entity`) que nadie Recordo. MEDIDO: la promocion de un claim con
    objeto-entidad reventaba con `InvalidClaimObjectError` **en el proyecto
    destino**, porque el payload llevaba `object_literal=None` y nada mas. El
    fallo aparecia donde nadie mira y ningun test lo decia.

    Con `asdict`, un campo nuevo en `Claim` viaja solo. No porque alguien lo
    anada dos veces: porque la enumeracion manual era el defecto, y era un
    defecto que solo se manifiesta en el camino de serializacion, que es
    justamente el que no tiene cobertura de campos.
    """
    payload = dataclasses.asdict(claim)
    ref = payload.pop("object_entity", None)
    payload["object_entity_id"] = ref["entity_id"] if isinstance(ref, dict) else None
    payload["evidence_ids"] = list(claim.evidence_ids)
    return payload


PROMOTION_FAILPOINTS: Final[frozenset[str]] = frozenset(
    {"before_apply", "mid_apply", "after_apply_first"}
)


_PROMOTION_FAILPOINT_ENV = "SKILLGRAPH_FAILPOINT_PROMOTION"


_FAILPOINT_EXIT_CODE = 9


def _select_promotion_failpoint() -> str | None:
    """Normaliza el failpoint pedido por el entorno, o None si no hay.

    Decision pura salvo por la lectura de entorno: separar la *decision*
    del `os._exit` es lo que hace comprobable el failpoint, porque el
    efecto termina el proceso y no se puede observar desde pytest.

    Returns:
        El nombre normalizado si es uno de `PROMOTION_FAILPOINTS`;
        None si la variable no esta, vacia o trae un nombre desconocido.
    """
    raw = os.environ.get(_PROMOTION_FAILPOINT_ENV)
    if raw is None:
        return None
    name = raw.strip().lower()
    return name if name in PROMOTION_FAILPOINTS else None


def _abort_with_failpoint(name: str) -> NoReturn:
    """Escribe el failpoint en stderr y termina el proceso.

    El codigo de salida es `_FAILPOINT_EXIT_CODE`, el mismo que usaban
    los failpoints inline antes de extraerse. Se conserva para no romper
    los asserts de los tests subprocess de UAT-13.

    Args:
        name: nombre del failpoint, ya validado.

    Raises:
        SystemExit: nunca; el proceso termina con `os._exit`.
    """
    sys.stderr.write(f"FAILPOINT: {name}\n")
    sys.stderr.flush()
    os._exit(_FAILPOINT_EXIT_CODE)


def cmd_promotion_submit(args: argparse.Namespace) -> int:
    """Registra una propuesta de promocion en el outbox (status=PENDING).

    El payload se construye desde el Claim indicado (source_project);
    target_project es el catalogo destino donde `reconcile` lo aplicara.
    """
    from skillgraph.core.errors import IdentityConflictError
    from skillgraph.governance.promotion import submit_proposal

    project, err = resolve_project(args, args.project)
    if err is not None:
        return err
    tenant_id = project["tenant_id"]

    storage = Storage(Path(project["db_path"]))
    try:
        claim = storage.get_claim(
            tenant_id=tenant_id, project_id=args.project, claim_id=args.claim_id
        )
        if claim is None:
            print(
                f"ERROR (sg_not_found): claim {args.claim_id!r} no existe en {args.project!r}",
                file=sys.stderr,
            )
            return EXIT_DOMAIN
        payload = {
            "source_project": args.project,
            "target_project": args.target,
            "source": _source_to_payload(
                storage, tenant_id=tenant_id, project_id=args.project, source_id=claim.source_id
            ),
            "entity": _entity_to_payload(
                storage,
                tenant_id=tenant_id,
                project_id=args.project,
                entity_id=claim.subject_entity_id,
            ),
            "claim": _claim_to_payload(claim),
        }
        proposal_id = args.proposal_id or f"promo-{args.claim_id}"
        try:
            submit_proposal(
                storage,
                proposal_id=proposal_id,
                tenant_id=tenant_id,
                source_project=args.project,
                target_catalog=args.target,
                knowledge_ref=args.claim_id,
                payload=payload,
            )
        except IdentityConflictError as exc:
            print(f"ERROR ({exc.code}): {exc}", file=sys.stderr)
            return EXIT_DOMAIN
    finally:
        storage.close()
    print(f"Propuesta registrada: {proposal_id} (PENDING)")
    print(f"Destino: {args.target}")
    return EXIT_OK


def cmd_promotion_list(args: argparse.Namespace) -> int:
    """Lista propuestas del outbox (todas o solo pendientes)."""
    project, err = resolve_project(args, args.project)
    if err is not None:
        return err

    storage = Storage(Path(project["db_path"]))
    try:
        # list_promotions() es la API publica; status='PENDING' devuelve solo
        # PENDING (no IN_PROGRESS). list_pending_promotions() conserva el
        # compat con IN_PROGRESS para callers internos (cmd_promotion_reconcile).
        rows = storage.list_pending_promotions() if args.pending else storage.list_promotions()
    finally:
        storage.close()
    if not rows:
        print("(sin propuestas)")
        return EXIT_OK
    for r in rows:
        print(
            f"{r['proposal_id']}  {r['status']:<12} {r['source_project']} -> {r['target_catalog']}"
        )
    return EXIT_OK


def cmd_promotion_reconcile(args: argparse.Namespace) -> int:
    """Reconcilia propuestas PENDING/IN_PROGRESS: aplica sin duplicar.

    Recorrido UAT-13: interrumpir el proceso (crash/failpoint) y
    re-invocar `promotion reconcile` completa la operacion sin
    duplicar el claim en el catalogo destino.
    """
    project, err = resolve_project(args, args.project)
    if err is not None:
        return err
    tenant_id = project["tenant_id"]
    target = args.target or args.project

    # El apply debe escribir en la base del PROYECTO DESTINO (el outbox
    # vive en origen; el claim promovido vive en destino).
    dest_project, err = resolve_project(args, target)
    if err is not None:
        print(
            f"ERROR: proyecto destino {target!r} no existe; crealo antes de reconciliar.",
            file=sys.stderr,
        )
        return EXIT_DOMAIN
    dest_storage = Storage(Path(dest_project["db_path"]))
    storage = Storage(Path(project["db_path"]))
    try:
        results = _apply_pending_promotions(
            storage,
            dest_storage,
            tenant_id=tenant_id,
            target_project=dest_project["name"],
        )
    finally:
        storage.close()
        dest_storage.close()
    if not results:
        print("(nada que reconciliar)")
        return EXIT_OK
    published, failed = _reconcile_summaries(results)
    for r in results:
        print(f"{r['proposal_id']}: {r['status']}")
    print(f"Reconciliadas: {len(results)} (PUBLISHED={published}, FAILED={failed})")
    return EXIT_OK if failed == 0 else EXIT_DOMAIN
