"""Subcomandos `sg expansion` (WI-52, ADR-0018).

Componente real del estrangulamiento H-02: los 7 handlers
`cmd_expansion_*` y sus helpers privados salen de `cli/runner.py`
verbatim. `runner` conserva alias de import para la tabla de dispatch
(WI-41); los call-sites (tests H4, UAT-08/09) no se editan.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC
from pathlib import Path

from skillgraph.cli.support import (
    EXIT_DOMAIN,
    EXIT_OK,
    EXIT_PLAN_NOT_FOUND,
    EXIT_PROJECT_NOT_FOUND,
    EXIT_VALIDATION,
    _load_plan_from_path,
    _load_plan_from_storage,
    _open_project_or_error,
    _plan_path,
    _write_plan_to_storage,
)
from skillgraph.core.errors import ValidationError
from skillgraph.governance.graph_expansion import (
    AddNode,
    AddTransition,
    Authorization,
    GraphExpansionProposal,
    RemoveTransition,
    apply_expansion,
    propose,
    record_rejection,
    validate,
)
from skillgraph.platform.storage import Storage
from skillgraph.resources.workflow import WorkflowNode, WorkflowTransition


def _utcnow_iso() -> str:
    """ISO-8601 UTC con sufijo +00:00 (legible, ordenable lexicograficamente)."""
    from datetime import datetime

    return datetime.now(UTC).isoformat()


def _infer_proposal_stage(
    proposal_path: Path,
    proposal_id: str,
    rejection_ids: set[str],
) -> str:
    """Inferir stage desde markers en disco (mismo patron que list/show).

    Precedencia: ARCHIVED > APPLIED > REJECTED > PROPOSED.
    """
    base = proposal_path.with_suffix(proposal_path.suffix)
    archived_marker = base.with_suffix(base.suffix + ".archived")
    applied_marker = base.with_suffix(base.suffix + ".applied")
    if archived_marker.is_file():
        return "ARCHIVED"
    if applied_marker.is_file():
        return "APPLIED"
    if proposal_id in rejection_ids:
        return "REJECTED"
    return "PROPOSED"


def _collect_rejection_ids(rejections_dir: Path) -> set[str]:
    """Lee ``expansion_rejections/*.json`` y devuelve proposal_ids rechazados.

    Tolerante a JSON corrupto y a archivos sin ``proposal_id``.
    """
    ids: set[str] = set()
    if not rejections_dir.is_dir():
        return ids
    for p in rejections_dir.iterdir():
        if p.suffix != ".json":
            continue
        try:
            d = json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(d, dict) and "proposal_id" in d:
            ids.add(str(d["proposal_id"]))
    return ids


def _load_registry(project_db: Path, *, tenant_id: str, project_id: str) -> dict[str, str]:
    """Devuelve dict capability_name -> brick_ref, leido de los resources
    del proyecto.

    Usa la API publica ``Storage.list_resources`` (H1). Las capabilities
    viven en ``spec_json.spec.capabilities`` (JSON del brick).
    """
    storage = Storage(project_db)
    try:
        rows = storage.list_resources(tenant_id=tenant_id, project_id=project_id)
    finally:
        storage.close()
    out: dict[str, str] = {}
    for r in rows:
        try:
            spec = json.loads(r.spec_json or "{}")
        except (ValueError, TypeError):
            continue
        caps = (spec or {}).get("capabilities", []) or []
        for cap in caps:
            out[cap] = f"{r.namespace}:{r.kind}/{r.name}"
    return out


def _ops_from_dict(ops_json: list[dict[str, object]]) -> tuple[object, ...]:
    """Deserializa la lista de operaciones PatchOp desde JSON."""
    ops: list[object] = []
    for op in ops_json:
        kind = op["op"]
        if kind == "add_node":
            node_data = op["node"]  # type: ignore[assignment]
            assert isinstance(node_data, dict)
            node = WorkflowNode(
                name=node_data["name"],
                kind=node_data["kind"],
                namespace=node_data["namespace"],
                api_version=node_data["api_version"],
                resource_revision=node_data["resource_revision"],
                expected_result=node_data["expected_result"],
                capabilities=tuple(node_data.get("capabilities", [])),
                metadata=node_data.get("metadata", {}) or {},
            )
            ops.append(AddNode(node=node))
        elif kind == "add_transition":
            t_data = op["transition"]  # type: ignore[assignment]
            assert isinstance(t_data, dict)
            trans = WorkflowTransition(
                source=t_data["source"],
                outcome=t_data["outcome"],
                target=t_data["target"],
            )
            ops.append(AddTransition(transition=trans))
        elif kind == "remove_transition":
            ops.append(
                RemoveTransition(
                    from_node=op["from_node"],  # type: ignore[arg-type]
                    outcome=op["outcome"],  # type: ignore[arg-type]
                )
            )
        else:
            raise ValidationError(f"op desconocida: {kind!r}")
    return tuple(ops)


def _load_proposal_json(path: Path) -> GraphExpansionProposal:
    """Carga una propuesta desde JSON, validando campos minimos."""
    import json as _json

    raw = _json.loads(path.read_text())
    auth_raw = raw["authorization"]
    authorization = Authorization(
        mode=auth_raw["mode"],
        granted_by=auth_raw.get("granted_by"),
        granted_at=auth_raw.get("granted_at"),
    )
    return propose(
        base_revision=raw["base_revision"],
        problem_observed=raw["problem_observed"],
        evidence=tuple(raw.get("evidence", [])),
        operations=_ops_from_dict(raw["operations"]),
        new_dependencies=tuple(raw.get("new_dependencies", [])),
        capabilities_needed=tuple(raw.get("capabilities_needed", [])),
        scope=raw.get("scope", "NODE"),
        attachment_point=raw["attachment_point"],
        rollback_plan=tuple(raw.get("rollback_plan", [])),
        authorization=authorization,
        author=raw["author"],
    )


def cmd_expansion_propose(args: argparse.Namespace) -> int:
    """``sg expansion propose <project> <proposal.json>``: imprime el proposal_id."""
    project, rc = _open_project_or_error(args, args.project)
    if rc != EXIT_OK:
        return rc
    assert project is not None
    try:
        proposal = _load_proposal_json(args.proposal_json)
    except (KeyError, ValueError, ValidationError) as exc:
        print(f"ERROR: propuesta invalida: {exc}", file=sys.stderr)
        return EXIT_VALIDATION
    project_dir = Path(project["db_path"]).parent
    proposals_dir = project_dir.parent.parent / "expansion_proposals"
    proposals_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "proposal_id": proposal.proposal_id,
        "author": proposal.author,
        "created_at": proposal.created_at,
        "problem_observed": proposal.problem_observed,
        "operations": str(args.proposal_json),
        "capabilities_needed": list(proposal.capabilities_needed),
        "new_dependencies": list(proposal.new_dependencies),
        "attachment_point": proposal.attachment_point,
        "authorization_mode": proposal.authorization.mode,
    }
    out = proposals_dir / f"{proposal.proposal_id}.json"
    out.write_text(json.dumps(payload, indent=2, sort_keys=True))
    print(f"Propuesta {proposal.proposal_id} registrada en {out}")
    return EXIT_OK


def cmd_expansion_apply(args: argparse.Namespace) -> int:
    """``sg expansion apply <project> --proposal P --plan-file F``: aplica."""
    project, rc = _open_project_or_error(args, args.project)
    if rc != EXIT_OK:
        return rc
    assert project is not None
    project_dir = Path(project["db_path"]).parent
    try:
        proposal = _load_proposal_json(args.proposal)
    except (KeyError, ValueError, ValidationError) as exc:
        print(f"ERROR: propuesta invalida: {exc}", file=sys.stderr)
        return EXIT_VALIDATION

    if args.plan_file is not None:
        # Carga desde Markdown+YAML o JSON interno (segun formato del archivo).
        plan = _load_plan_from_path(args.plan_file)
        # Persiste la version "canonica" del plan en project_dir/plan.json
        # para que ``apply`` pueda usarla como base y la propuesta modifique
        # ese archivo al aplicar.
        _write_plan_to_storage(project_dir, plan)
    try:
        plan = _load_plan_from_storage(project_dir)
    except SystemExit:
        return EXIT_PLAN_NOT_FOUND

    registry = _load_registry(
        Path(project["db_path"]),
        tenant_id=project["tenant_id"],
        project_id=project["name"],
    )
    result = apply_expansion(proposal, plan, registry=registry)

    if result.is_err():
        err = result.unwrap_err()
        rejection_path = record_rejection(
            proposal,
            reason=err.reason,
            rejected_by="validator-cli",
            project_dir=project_dir,
            violated_invariants=err.violated_invariants,
        )
        print(
            f"REJECTED: {proposal.proposal_id}: {err.reason} (violated={list(err.violated_invariants)})",
            file=sys.stderr,
        )
        print(f"Evidencia persistida en {rejection_path}", file=sys.stderr)
        return EXIT_DOMAIN

    new_plan = result.unwrap()
    _write_plan_to_storage(project_dir, new_plan)
    # Persiste la propuesta aplicada en ``expansion_proposals/`` (mismo
    # patron que ``cmd_expansion_propose``) para que ``list``/``show`` la
    # puedan descubrir tras el apply. Tambien crea el marker APPLIED,
    # analogo al marker ARCHIVED de ``cmd_expansion_archive``.
    proposals_dir = project_dir.parent.parent / "expansion_proposals"
    proposals_dir.mkdir(parents=True, exist_ok=True)
    proposal_json = proposals_dir / f"{proposal.proposal_id}.json"
    if not proposal_json.is_file():
        proposal_json.write_text(
            json.dumps(
                {
                    "proposal_id": proposal.proposal_id,
                    "author": proposal.author,
                    "created_at": proposal.created_at,
                    "problem_observed": proposal.problem_observed,
                    "operations": str(args.proposal),
                    "capabilities_needed": list(proposal.capabilities_needed),
                    "new_dependencies": list(proposal.new_dependencies),
                    "attachment_point": proposal.attachment_point,
                    "authorization_mode": proposal.authorization.mode,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
    applied_marker = proposals_dir / f"{proposal.proposal_id}.json.applied"
    applied_marker.write_text(
        json.dumps(
            {
                "proposal_id": proposal.proposal_id,
                "applied_at": _utcnow_iso(),
                "applied_by": "expansion-apply-cli",
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    print(f"OK: {proposal.proposal_id} aplicado. Nuevo plan en {_plan_path(project_dir)}")
    print(f"Nodos antes: {len(plan.nodes)} -> despues: {len(new_plan.nodes)}")
    return EXIT_OK


def cmd_expansion_validate(args: argparse.Namespace) -> int:
    """``sg expansion validate ...``: imprime ValidationResult, no muta."""
    project, rc = _open_project_or_error(args, args.project)
    if rc != EXIT_OK:
        return rc
    assert project is not None
    project_dir = Path(project["db_path"]).parent
    try:
        proposal = _load_proposal_json(args.proposal)
    except (KeyError, ValueError, ValidationError) as exc:
        print(f"ERROR: propuesta invalida: {exc}", file=sys.stderr)
        return EXIT_VALIDATION

    if args.plan_file is not None:
        plan = _load_plan_from_path(args.plan_file)
        _write_plan_to_storage(project_dir, plan)
    try:
        plan = _load_plan_from_storage(project_dir)
    except SystemExit:
        return EXIT_PLAN_NOT_FOUND

    registry = _load_registry(
        Path(project["db_path"]),
        tenant_id=project["tenant_id"],
        project_id=project["name"],
    )
    result = validate(proposal, plan=plan, registry=registry)
    out = {
        "accepted": result.accepted,
        "reason": result.reason,
        "violated_invariants": list(result.violated_invariants),
        "warnings": list(result.warnings),
    }
    print(json.dumps(out, indent=2))
    return EXIT_OK if result.accepted else EXIT_DOMAIN


def cmd_expansion_rejections(args: argparse.Namespace) -> int:
    """``sg expansion rejections <project>``: lista rechazos persistidos."""
    project, rc = _open_project_or_error(args, args.project)
    if rc != EXIT_OK:
        return rc
    assert project is not None
    project_dir = Path(project["db_path"]).parent
    rej_dir = project_dir / "expansion_rejections"
    if not rej_dir.is_dir():
        print("(sin rechazos)")
        return EXIT_OK
    files = sorted(p for p in rej_dir.iterdir() if p.suffix == ".json")
    if not files:
        print("(sin rechazos)")
        return EXIT_OK
    for p in files:
        data = json.loads(p.read_text())
        print(
            f"- {data['proposal_id']}: reason={data['reason']!r} "
            f"rejected_by={data['rejected_by']!r} at={data['rejected_at']}"
        )
    return EXIT_OK


# ---------------------------------------------------------------------------
# Slice-3 handlers: list / show / archive
# ---------------------------------------------------------------------------


def _scan_proposals_dir(proposals_dir: Path) -> list[tuple[Path, dict[str, object]]]:
    """Lee todos los JSON de propuestas. Devuelve (path, payload).

    Ignora silenciosamente archivos con JSON malformado (no rompe
    el comando entero por un archivo corrupto).
    """
    if not proposals_dir.is_dir():
        return []
    out: list[tuple[Path, dict[str, object]]] = []
    for p in sorted(proposals_dir.iterdir()):
        if p.suffix != ".json":
            continue
        try:
            data = json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(data, dict):
            out.append((p, data))
    return out


def cmd_expansion_list(args: argparse.Namespace) -> int:
    """``sg expansion list <project> [--stage STAGE]``: lista propuestas.

    Slice-3: lee desde el directorio ``expansion_proposals/`` existente
    (JSON files planos, source-of-truth actual; ver specs/h4-slice-3.md
    limitacion 3). NO migra a SQLite (deferido slice-4).

    Stage inferido (precedencia: ARCHIVED > APPLIED > REJECTED > PROPOSED):
    - ARCHIVED: existe ``<proposal_id>.archived`` (marker file).
    - APPLIED: existe ``<proposal_id>.applied`` (marker file, creado por
      ``cmd_expansion_apply`` al persistir el nuevo plan).
    - REJECTED: hay un archivo en ``expansion_rejections/`` con ese proposal_id.
    - Si nada match: PROPOSED (estado inicial tras cmd_expansion_propose).
    """
    project, rc = _open_project_or_error(args, args.project)
    if rc != EXIT_OK:
        return rc
    assert project is not None
    project_dir = Path(project["db_path"]).parent
    proposals_dir = project_dir.parent.parent / "expansion_proposals"
    rejections_dir = project_dir / "expansion_rejections"

    rejection_ids = _collect_rejection_ids(rejections_dir)

    rows = _scan_proposals_dir(proposals_dir)
    if not rows:
        print("(sin propuestas)")
        return EXIT_OK

    shown = 0
    for path, data in rows:
        proposal_id = str(data.get("proposal_id", path.stem))
        stage = _infer_proposal_stage(path, proposal_id, rejection_ids)
        if args.stage is not None and args.stage != stage:
            continue
        created = data.get("created_at", "?")
        author = data.get("author", "?")
        print(f"- {proposal_id}: stage={stage} author={author} created_at={created}")
        shown += 1
    if shown == 0:
        print(f"(sin propuestas en stage={args.stage})")
    return EXIT_OK


def cmd_expansion_show(args: argparse.Namespace) -> int:
    """``sg expansion show <project> <proposal_id>``: muestra la propuesta."""
    project, rc = _open_project_or_error(args, args.project)
    if rc != EXIT_OK:
        return rc
    assert project is not None
    project_dir = Path(project["db_path"]).parent
    proposals_dir = project_dir.parent.parent / "expansion_proposals"
    rejections_dir = project_dir / "expansion_rejections"

    rejection_ids = _collect_rejection_ids(rejections_dir)

    rows = _scan_proposals_dir(proposals_dir)
    for path, data in rows:
        if str(data.get("proposal_id", "")) == args.proposal_id:
            stage = _infer_proposal_stage(path, str(data["proposal_id"]), rejection_ids)
            payload = {**data, "stage": stage}
            print(json.dumps(payload, indent=2, sort_keys=True))
            return EXIT_OK
    print(f"ERROR: proposal_id={args.proposal_id!r} no encontrado", file=sys.stderr)
    return EXIT_PROJECT_NOT_FOUND


def cmd_expansion_archive(args: argparse.Namespace) -> int:
    """``sg expansion archive <project> <proposal_id>``: marca ARCHIVED.

    Crea un marker file ``<proposal_id>.json.archived`` adyacente al
    proposal JSON. No borra el proposal (audit forense). Idempotente.
    """
    project, rc = _open_project_or_error(args, args.project)
    if rc != EXIT_OK:
        return rc
    assert project is not None
    project_dir = Path(project["db_path"]).parent
    proposals_dir = project_dir.parent.parent / "expansion_proposals"

    rows = _scan_proposals_dir(proposals_dir)
    for path, data in rows:
        if str(data.get("proposal_id", "")) == args.proposal_id:
            marker = path.with_suffix(path.suffix + ".archived")
            marker.touch()
            print(f"Archived: {args.proposal_id} (marker={marker})")
            return EXIT_OK
    print(f"ERROR: proposal_id={args.proposal_id!r} no encontrado", file=sys.stderr)
    return EXIT_PROJECT_NOT_FOUND
