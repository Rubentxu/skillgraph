"""ValidationReceipts — H14 Evidencia operativa temporal.

Destino (evolution-v2/plan/ROADMAP.md H14):
consultar que se comprobo, bajo que revision, y que recibos siguen
siendo aplicables. Permite:

- Persistir un ValidationReceipt tras ejecutar una suite (cmd real,
  revision, resultado, artefacto, scope).
- Consultar recibos historicos por revision.
- Decidir si un recibo es APLICABLE a la revision/deps actuales
  (regla UAT-EVO-14: un recibo de A NO es validacion automatica de B).

Adaptado a las primitivas existentes:
- NO introduce tabla nueva (regla AGENTS §1.5): reusa
  ``Evidence(kind="validation_receipt")`` con ``content_json`` para
  el payload logico. Esto evita migracion y mantiene el storage
  cerrado.
- ADT cerrada via Literal (regla AGENTS §2.1): ReceiptVerdict
  ("pass" | "fail") y ReceiptScope ("command" | "tests" | "file" |
  "package") para que el caller declare el ambito acotado.
- Funciones puras sin I/O donde es posible (regla AGENTS §1.1):
  ``is_receipt_applicable`` no toca Storage.

Historia y aplicabilidad (UAT-EVO-14):
- Un recibo es APTO si ``receipt.revision == current_revision`` y
  todas sus ``dependency_revisions`` coinciden con las actuales.
- Si cambia la revision o cualquier dependencia, el recibo queda
  INVALIDO para la revision actual pero sigue consultable
  historicamente (la funcion de listado acepta un parametro
  ``current_revision``: cuando coincide con ``receipt.revision`` y
  ``dependency_revisions``, se incluye; cuando no, no).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from skillgraph.core.errors import ValidationError
from skillgraph.knowledge.graph import Evidence, Source
from skillgraph.knowledge.knowledge_controller import KnowledgeController

# --- ADT cerradas (regla AGENTS §2.1) -------------------------------

ReceiptVerdict = Literal["pass", "fail"]
ReceiptScope = Literal["command", "tests", "file", "package", "directory", "bounded_context"]

RECEIPT_VERDICTS: frozenset[str] = frozenset({"pass", "fail"})
RECEIPT_SCOPES: frozenset[str] = frozenset(
    {"command", "tests", "file", "package", "directory", "bounded_context"}
)


# --- Dataclasses frozen ----------------------------------------------


@dataclass(frozen=True, slots=True)
class ValidationReceipt:
    """Recibo de validacion persistido tras una ejecucion de tests.

    Atributos observables (UAT-EVO-12):
    - ``receipt_id``: ID determinista UUIDv5 (vacio para autogenerar).
    - ``command``: comando real ejecutado.
    - ``revision``: revision HEAD al ejecutar (SHA completo).
    - ``timestamp``: ISO-8601 UTC.
    - ``verdict``: "pass" | "fail" (regla AGENTS §2.1: Literal cerrada).
    - ``tests_run``: tests ejecutados.
    - ``tests_passed``: tests pasados.
    - ``artifact_path``: ruta al artefacto (debe existir al persistir).
    - ``scope``: ambito acotado (Literal cerrada).
    - ``dependency_revisions``: dict {dep_name: sha} para chequeo de
      aplicabilidad (UAT-EVO-14).
    - ``extra_metadata``: payload libre (extensible).

    Certificacion acotada (UAT-EVO-13): el recibo declara
    ``tests_run`` y ``tests_passed`` explicitamente. NO se
    interpreta como "seguridad global": el scope y las deps
    determinan su aplicabilidad.
    """

    receipt_id: str
    command: str
    revision: str
    timestamp: str
    verdict: ReceiptVerdict
    tests_run: int
    tests_passed: int
    artifact_path: str
    scope: str
    dependency_revisions: dict[str, str] = field(default_factory=dict)
    extra_metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.receipt_id:
            raise ValueError("receipt_id vacio")
        if not self.command:
            raise ValidationError("command vacio")
        if not self.revision:
            raise ValidationError("revision vacia")
        if not self.timestamp:
            raise ValidationError("timestamp vacio")
        if self.verdict not in RECEIPT_VERDICTS:
            raise ValidationError(f"verdict invalido: {self.verdict!r}")
        if self.tests_run < 0:
            raise ValidationError(f"tests_run negativo: {self.tests_run}")
        if self.tests_passed < 0:
            raise ValidationError(f"tests_passed negativo: {self.tests_passed}")
        if self.tests_passed > self.tests_run:
            raise ValidationError(
                f"tests_passed ({self.tests_passed}) > tests_run ({self.tests_run})"
            )
        if not self.artifact_path:
            raise ValidationError("artifact_path vacio")
        if not self.scope:
            raise ValidationError("scope vacio")

    @property
    def is_pass(self) -> bool:
        return self.verdict == "pass"

    @property
    def coverage_ratio(self) -> float:
        """Fraccion de tests pasados (0.0..1.0)."""
        if self.tests_run == 0:
            return 1.0  # vacio == sin fallos por convencion
        return self.tests_passed / self.tests_run

    def to_payload(self) -> dict[str, Any]:
        """Serializa el receipt como payload JSON-friendly."""
        return {
            "receipt_id": self.receipt_id,
            "command": self.command,
            "revision": self.revision,
            "timestamp": self.timestamp,
            "verdict": self.verdict,
            "tests_run": self.tests_run,
            "tests_passed": self.tests_passed,
            "artifact_path": self.artifact_path,
            "scope": self.scope,
            "dependency_revisions": dict(self.dependency_revisions),
            "extra_metadata": dict(self.extra_metadata),
        }


# --- Funciones puras (sin I/O) --------------------------------------


def is_receipt_applicable(
    *,
    receipt: ValidationReceipt,
    current_revision: str,
    dependency_revisions: dict[str, str] | None = None,
) -> bool:
    """Decide si un recibo es aplicable al estado actual (UAT-EVO-14).

    Reglas:
    1. ``receipt.revision == current_revision``.
    2. Para cada ``dep_name`` en ``receipt.dependency_revisions``:
       el SHA actual (``dependency_revisions[dep_name]``) debe coincidir.

    Si el caller no aporta ``dependency_revisions`` y el receipt tiene
    alguna declarada, el recibo NO es aplicable (no podemos verificar
    la consistencia de las deps).

    Args:
        receipt: ValidationReceipt a evaluar.
        current_revision: SHA actual de HEAD.
        dependency_revisions: dict {dep_name: sha} del estado actual.

    Returns:
        True si el recibo es aplicable, False en caso contrario.

    Notes:
        Funcion pura: NO toca Storage. La decision se queda en el
        caller, que es quien orquesta la consulta.
    """
    if receipt.revision != current_revision:
        return False
    if receipt.dependency_revisions:
        if dependency_revisions is None:
            return False
        for dep_name, expected_sha in receipt.dependency_revisions.items():
            actual_sha = dependency_revisions.get(dep_name)
            if actual_sha != expected_sha:
                return False
    return True


# --- Funciones con I/O (registro + consulta) -------------------------


def _utc_now_iso() -> str:
    """Devuelve la hora UTC actual en formato ISO-8601."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _make_receipt_id(*, command: str, revision: str, timestamp: str, tests_run: int) -> str:
    """Genera un receipt_id determinista (UUIDv5 namespace).

    Sin randomness: el mismo (command, revision, timestamp, tests_run)
    produce el mismo receipt_id, permitiendo idempotencia natural
    (regla AGENTS §1.3).
    """
    import hashlib
    import uuid

    # Namespace fijo (mismo que KnowledgeController para consistencia).
    namespace = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
    payload = f"{command}|{revision}|{timestamp}|{tests_run}"
    digest = hashlib.sha256(payload.encode("utf-8")).digest()
    return str(uuid.uuid5(namespace, digest.hex()))


def record_validation_receipt(
    *,
    controller: KnowledgeController,
    command: str,
    revision: str,
    result: ReceiptVerdict,
    tests_run: int,
    tests_passed: int,
    artifact_path: str,
    scope: str,
    dependency_revisions: dict[str, str] | None = None,
    extra_metadata: dict[str, Any] | None = None,
    timestamp: str | None = None,
    receipt_id: str = "",
) -> str:
    """Persiste un ValidationReceipt como Evidence(kind='validation_receipt').

    Args:
        controller: KnowledgeController (aporta tenant/project + Storage).
        command: comando real ejecutado.
        revision: SHA de HEAD al ejecutar.
        result: "pass" | "fail".
        tests_run: tests ejecutados.
        tests_passed: tests pasados.
        artifact_path: ruta al artefacto (debe existir en disco).
        scope: ambito acotado (str).
        dependency_revisions: dict opcional {dep_name: sha}.
        extra_metadata: dict opcional.
        timestamp: ISO-8601 UTC (default: ahora).
        receipt_id: ID explicito (default: autogenerado determinista).

    Returns:
        El receipt_id asignado.

    Raises:
        ValidationError: si algun campo obligatorio falta, el verdict
            es invalido, o artifact_path NO existe en disco.
        SkillGraphError: cualquier error de persistencia.
    """
    # Validaciones tempranas (smart constructors).
    if not command:
        raise ValidationError("command vacio")
    if not revision:
        raise ValidationError("revision vacia")
    if result not in RECEIPT_VERDICTS:
        raise ValidationError(f"result invalido: {result!r}")
    if not artifact_path:
        raise ValidationError("artifact_path vacio")
    if not scope:
        raise ValidationError("scope vacio")
    # artifact_path debe existir en disco (UAT-EVO-12 "vinculado al artefacto").
    if not Path(artifact_path).exists():
        raise ValidationError(
            f"artifact_path no existe en disco: {artifact_path!r}"
        )

    ts = timestamp or _utc_now_iso()
    rid = receipt_id or _make_receipt_id(
        command=command,
        revision=revision,
        timestamp=ts,
        tests_run=tests_run,
    )

    receipt = ValidationReceipt(
        receipt_id=rid,
        command=command,
        revision=revision,
        timestamp=ts,
        verdict=result,
        tests_run=tests_run,
        tests_passed=tests_passed,
        artifact_path=artifact_path,
        scope=scope,
        dependency_revisions=dict(dependency_revisions or {}),
        extra_metadata=dict(extra_metadata or {}),
    )

    # Persistir como Evidence(kind='validation_receipt'). Reusa tabla
    # existente (regla AGENTS §1.5: no tabla nueva). Necesitamos un
    # Source "validacion" para satisfacer la FK.
    source_id = f"validation:{rid}"
    controller.register_source(
        source=Source(
            source_id=source_id,
            kind="local_file",
            content_hash=rid,
            locator={"path": artifact_path},
            git_commit_sha=None,
            git_tree_sha=None,
            working_tree_status=None,
            checked_at=ts,
            freshness="fresh",
        )
    )
    evidence = Evidence(
        evidence_id="",  # autogenerado por KnowledgeController
        source_id=source_id,
        kind="validation_receipt",
        content=receipt.to_payload(),
        observed_at=ts,
    )
    controller.record_evidence(evidence=evidence)
    return rid


def list_applicable_receipts(
    *,
    storage: Any,  # Storage (forward ref para evitar ciclos)
    tenant_id: str,
    project_id: str,
    current_revision: str,
    dependency_revisions: dict[str, str] | None = None,
    scope: str | None = None,
) -> tuple[ValidationReceipt, ...]:
    """Lista los ValidationReceipts aplicables al estado actual.

    Filtros aplicados:
    1. tenant/project (via Storage.list_evidences_for_source indirecto).
    2. kind == "validation_receipt".
    3. receipt.revision == current_revision.
    4. receipt.dependency_revisions compatibles con dependency_revisions.
    5. scope opcional.

    Args:
        storage: instancia de Storage (acceso directo).
        tenant_id: tenant del caller.
        project_id: project del caller.
        current_revision: SHA de HEAD actual.
        dependency_revisions: dict opcional {dep_name: sha}.
        scope: si se da, filtra recibos con este scope.

    Returns:
        Tupla de ValidationReceipts que pasan todos los filtros.
        Un recibo que NO pasa el filtro de aplicabilidad sigue
        siendo consultable historicamente (esta funcion filtra
        explicitamente por ``is_receipt_applicable``).

    Notes:
        Itera sobre TODOS los sources del tenant/project. Para
        catalogs grandes se puede anadir un indice por source.kind
        en el futuro; H14 mantiene el contrato simple.
    """
    out: list[ValidationReceipt] = []
    # Iterar sobre evidences del tenant/project. Accedemos a
    # ``storage.list_evidences_for_source`` por source_id; como
    # desconocemos los source_ids, usamos el patron conocido:
    # un source por receipt. Para simplificar, leemos TODAS las
    # evidences del tenant/project y filtramos por kind.
    # Esto es O(N) en evidences; aceptable para H14 (no escala
    # enorme todavia).
    sources = storage._conn.execute(
        "SELECT source_id FROM sources WHERE tenant_id = ? AND project_id = ?",
        (tenant_id, project_id),
    ).fetchall()
    for (source_id,) in sources:
        rows = storage.list_evidences_for_source(source_id=source_id)
        for row in rows:
            if row.get("kind") != "validation_receipt":
                continue
            content_json = row.get("content_json")
            if not isinstance(content_json, str):
                continue
            try:
                payload = json.loads(content_json)
            except json.JSONDecodeError:
                continue
            try:
                receipt = _payload_to_receipt(payload)
            except (KeyError, ValueError, TypeError):
                continue
            if scope is not None and receipt.scope != scope:
                continue
            if not is_receipt_applicable(
                receipt=receipt,
                current_revision=current_revision,
                dependency_revisions=dependency_revisions,
            ):
                continue
            out.append(receipt)
    return tuple(out)


def _payload_to_receipt(payload: dict[str, Any]) -> ValidationReceipt:
    """Reconstruye un ValidationReceipt desde su payload JSON.

    Funcion defensiva: cualquier campo faltante o de tipo incorrecto
    produce excepcion (capturada por el caller para omitir el row).
    """
    return ValidationReceipt(
        receipt_id=payload["receipt_id"],
        command=payload["command"],
        revision=payload["revision"],
        timestamp=payload["timestamp"],
        verdict=payload["verdict"],  # type: ignore[arg-type]
        tests_run=int(payload["tests_run"]),
        tests_passed=int(payload["tests_passed"]),
        artifact_path=payload["artifact_path"],
        scope=payload["scope"],
        dependency_revisions=dict(payload.get("dependency_revisions", {})),
        extra_metadata=dict(payload.get("extra_metadata", {})),
    )
