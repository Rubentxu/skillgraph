"""KnowledgeController: API de alto nivel para el subsistema de conocimiento.

Doc externo:
  specs/h3-slice-2.md (sub-spec firmado en el H3).
  external/blueprint-v1/docs/08-conocimiento-y-contexto.md.
  external/blueprint-v1/adr/ADR-0011-controladores.md.

Este modulo introduce la clase `KnowledgeController` que envuelve los
metodos de `Storage` introducidos en Slice 1. Encapsula:

- Validacion previa (los ADT frozen ya validan en `__post_init__`).
- Generacion automatica de IDs reproducibles via UUIDv5.
- Aislamiento por `(tenant_id, project_id)` inyectado en `__init__`.
- Conversion de errores de Storage a errores de dominio:
  - FK violation -> UnknownEntityError / UnknownSourceError.
  - "not found" en lookup -> UnknownSourceError / UnknownClaimError.

Lo que NO hace este slice:
- Invalidacion transitiva (slice 4).
- Git fingerprinting (slice 3).
- ContextRecipe / Handoff (slice 5).
"""

from __future__ import annotations

import uuid
import warnings
from dataclasses import dataclass

from skillgraph.core.errors import (
    NotFoundError,
    StaleKnowledgeWarning,
    UnknownClaimError,
    UnknownEntityError,
    UnknownSourceError,
)
from skillgraph.knowledge.file_signature import FileSignature
from skillgraph.knowledge.graph import (
    Claim,
    ClaimID,
    Entity,
    EntityID,
    Evidence,
    EvidenceID,
    Finding,
    FindingID,
    OutcomeTrace,
    Source,
    SourceID,
    TraceID,
)
from skillgraph.platform.storage import Storage

# Namespace estable para UUIDv5: cualquier texto puede ser, pero usamos
# un UUID fijo (no aleatorio por proceso) para que el mismo contenido
# siempre genere el mismo ID. Esto da idempotencia por contenido sin
# necesidad de UNIQUE adicionales en Storage.
NAMESPACE_KNOWLEDGE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


def make_claim_id(
    *,
    subject_entity_id: EntityID,
    predicate: str,
    source_id: SourceID,
    checked_at_revision: str,
) -> ClaimID:
    """Genera un ClaimID determinista via UUIDv5 sobre la tupla natural."""
    seed = f"{subject_entity_id}|{predicate}|{source_id}|{checked_at_revision}"
    return ClaimID(f"claim-{uuid.uuid5(NAMESPACE_KNOWLEDGE, seed)}")


def make_evidence_id(*, source_id: SourceID, content_repr: str) -> EvidenceID:
    """Genera un EvidenceID determinista via UUIDv5."""
    seed = f"{source_id}|{content_repr}"
    return EvidenceID(f"ev-{uuid.uuid5(NAMESPACE_KNOWLEDGE, seed)}")


def make_finding_id(
    *,
    entity_id: EntityID,
    rule_ref: str,
    rule_version: str,
) -> FindingID:
    """Genera un FindingID determinista via UUIDv5."""
    seed = f"{entity_id}|{rule_ref}|{rule_version}"
    return FindingID(f"fnd-{uuid.uuid5(NAMESPACE_KNOWLEDGE, seed)}")


@dataclass(frozen=True, slots=True)
class KnowledgeController:
    """API de alto nivel para Source/Entity/Claim/Evidence/Finding/OutcomeTrace.

    Recibe `storage`, `tenant_id`, `project_id` por inyeccion. Esto permite:
    - Mockear Storage en tests sin SQLite.
    - Reutilizar el mismo controller con distintos `(tenant, project)`.
    - Testeo determinista con fixtures inyectados.
    """

    storage: Storage
    tenant_id: str
    project_id: str

    # ----- Sources -----

    def register_source(self, *, source: Source) -> SourceID:
        """Registra una Source. Emite `StaleKnowledgeWarning` si la source
        ya existe con `freshness != 'fresh'` (re-registro de source stale)."""
        existing = self.storage.get_source(
            tenant_id=self.tenant_id,
            project_id=self.project_id,
            source_id=source.source_id,
        )
        if existing is not None and existing.freshness != "fresh":
            warnings.warn(
                f"re-registrando source stale: {source.source_id!r}",
                StaleKnowledgeWarning,
                stacklevel=2,
            )
        self.storage.register_source(
            tenant_id=self.tenant_id,
            project_id=self.project_id,
            source=source,
        )
        return source.source_id

    def get_source(self, *, source_id: SourceID) -> Source:
        """Recupera una Source. `UnknownSourceError` si no existe."""
        result = self.storage.get_source(
            tenant_id=self.tenant_id,
            project_id=self.project_id,
            source_id=source_id,
        )
        if result is None:
            raise UnknownSourceError(
                "Source no encontrada"
            )  # NO expone source_id (S2/I)
        return result

    def mark_source_stale(self, *, source_id: SourceID) -> None:
        """Marca una Source como stale. Lanza UnknownSourceError si no existe."""
        existing = self.get_source(source_id=source_id)
        self.storage.update_source_freshness(
            tenant_id=self.tenant_id,
            project_id=self.project_id,
            source_id=existing.source_id,
            freshness="stale",
        )

    def mark_source_fresh(self, *, source_id: SourceID) -> None:
        """Marca una Source como fresh."""
        existing = self.get_source(source_id=source_id)
        self.storage.update_source_freshness(
            tenant_id=self.tenant_id,
            project_id=self.project_id,
            source_id=existing.source_id,
            freshness="fresh",
        )

    # ----- Entities -----

    def upsert_entity(self, *, entity: Entity) -> EntityID:
        """Inserta o reemplaza una Entity. Devuelve su entity_id."""
        self.storage.upsert_entity(
            tenant_id=self.tenant_id,
            project_id=self.project_id,
            entity=entity,
        )
        return entity.entity_id

    def get_entity(self, *, entity_id: EntityID) -> Entity:
        """Recupera una Entity. UnknownEntityError si no existe."""
        result = self.storage.get_entity(
            tenant_id=self.tenant_id,
            project_id=self.project_id,
            entity_id=entity_id,
        )
        if result is None:
            raise UnknownEntityError(
                "Entity no encontrada"
            )  # NO expone entity_id (S2/I)
        return result

    def find_entity(self, *, kind: str, stable_key: str) -> Entity | None:
        """Busca una Entity por (kind, stable_key). None si no existe.

        Implementacion: query directa sobre `entities` (UNIQUE(kind,
        stable_key) por tenant/project garantiza unicidad).
        """

        row = self.storage._conn.execute(
            """
            SELECT * FROM entities
            WHERE tenant_id = ? AND project_id = ?
              AND kind = ? AND stable_key = ?
            """,
            (self.tenant_id, self.project_id, kind, stable_key),
        ).fetchone()
        if row is None:
            return None
        return Entity(
            entity_id=row["entity_id"],
            kind=row["kind"],
            stable_key=row["stable_key"],
        )

    # ----- Evidences -----

    def record_evidence(self, *, evidence: Evidence) -> EvidenceID:
        """Registra una Evidence. Convierte FK violation en UnknownSourceError."""
        try:
            self.storage.record_evidence(
                tenant_id=self.tenant_id,
                project_id=self.project_id,
                evidence=evidence,
            )
        except Exception as exc:
            msg = str(exc)
            if "FOREIGN KEY" in msg:
                raise UnknownSourceError(
                    "Source no existe"
                ) from exc  # NO expone source_id (S2/I)
            raise
        return evidence.evidence_id

    def get_evidences_for_claim(self, *, claim_id: ClaimID) -> tuple[Evidence, ...]:
        """Devuelve las Evidences asociadas a un Claim."""
        return self.storage.get_evidences_for_claim(
            tenant_id=self.tenant_id,
            project_id=self.project_id,
            claim_id=claim_id,
        )

    # ----- FileSignatures (H11 evolution-v2) -----

    def record_evidence_for_file_signature(
        self,
        *,
        source_id: SourceID,
        file_signature: FileSignature,
        evidence_id: EvidenceID = "",  # placeholder; generado si vacio
    ) -> EvidenceID:
        """Persiste una ``FileSignature`` como ``Evidence`` (kind='file_signature').

        H11: el contrato externo es un payload logico (FileSignature
        inmutable con foco, contrato, cobertura, procedencia y
        vigencia). El storage concreto es una Evidence de kind
        especial para evitar una migracion de schema (regla
        AGENTS §1.5: no crear abstracciones nuevas si las
        existentes cubren el requisito).

        Args:
            source_id: source al que pertenece la signature.
            file_signature: dataclass inmutable con el payload.
            evidence_id: opcional, generado si vacio.

        Returns:
            El ``EvidenceID`` asignado.
        """
        if not isinstance(file_signature, FileSignature):
            raise TypeError(
                f"file_signature debe ser FileSignature, recibio {type(file_signature).__name__}"
            )

        # Generar evidence_id si vacio (UUIDv5 determinista por contenido).
        if not evidence_id:
            import json as _json

            payload = file_signature.to_dict()
            evidence_id = make_evidence_id(
                source_id=source_id,
                content_repr=_json.dumps(payload, sort_keys=True),
            )

        # Wrap en Evidence con kind='file_signature' y content=dict serializado.
        # Storage.record_evidence serializa dict|str; pasar dict deja una
        # sola capa de json.dumps (no doble encoding).
        evidence = Evidence(
            evidence_id=evidence_id,
            kind="file_signature",
            content=file_signature.to_dict(),
            source_id=source_id,
            observed_at=file_signature.vigencia.checked_at_revision or "h11",
        )
        return self.record_evidence(evidence=evidence)

    def list_file_signatures_for_source(
        self,
        *,
        source_id: SourceID,
        only_stale: bool = False,
    ) -> tuple[FileSignature, ...]:
        """Lee las FileSignatures persistidas para un source.

        Args:
            source_id: source a consultar.
            only_stale: si True, filtra las signatures con
                ``vigencia.stale=True`` (estado frozen al persistir)
                O cuya source tiene ``freshness="stale"`` (cambio
                upstream detectado tras la extraccion). Esto
                modela la regla H11 "stale al cambiar source".

        Returns:
            Tupla de FileSignatures deserializadas. Vacía si no hay.
        """
        import json as _json

        from skillgraph.knowledge.file_signature import (
            FileSignature,
            SignatureProcedencia,
            SignatureVigencia,
        )

        # Si only_stale=True, comprobar el freshness del source primero.
        source_is_stale = False
        if only_stale:
            try:
                src = self.get_source(source_id=source_id)
                source_is_stale = src.freshness == "stale"
            except UnknownSourceError:
                source_is_stale = False

        evidences = self.storage.list_evidences_for_source(
            source_id=source_id,
        )
        sigs: list[FileSignature] = []
        for e in evidences:
            if e.get("kind") != "file_signature":
                continue
            content_json = e.get("content_json")
            if not isinstance(content_json, str):
                continue
            payload = _json.loads(content_json)
            sig = FileSignature(
                foco=payload["foco"],
                contrato=payload["contrato"],
                cobertura=payload["cobertura"],
                procedencia=SignatureProcedencia(**payload["procedencia"]),
                vigencia=SignatureVigencia(**payload["vigencia"]),
                metadata=payload.get("metadata", {}),
            )
            # Stale por signature O por source (regla H11).
            is_stale = sig.vigencia.stale or source_is_stale
            if only_stale and not is_stale:
                continue
            sigs.append(sig)
        return tuple(sigs)

    # ----- Scopes H12 (evolution-v2) -----

    def aggregate_file_signatures(
        self,
        *,
        scope_query: object,  # ScopeQuery (forward ref para evitar ciclo import)
        member_source_ids: tuple[str, ...],
    ) -> object:  # forward ref (lazy import para evitar ciclo import)
        """Agrega FileSignatures de varios sources con aislamiento.

        H12 evolution-v2: UAT-EVO-05..08.

        Args:
            scope_query: ``ScopeQuery`` (file_scope) declarativo.
            member_source_ids: tupla de source_ids a agregar.

        Returns:
            ``AggregatedSignatures`` (file_scope) con cobertura global
            y signatures deduplicadas por foco.

        Raises:
            UnknownSourceError: si algun ``member_source_ids`` NO
                pertenece al scope (tenant_id, project_id) de este
                controller. Es el comportamiento de UAT-EVO-08:
                rechazo explicito sin filtrar contenido.

        Notes:
            El aislamiento es por (tenant_id, project_id): el controller
            inyecta ambos en ``__init__``. ``get_source`` ya filtra por
            estos campos; si devuelve UnknownSourceError, NO hay
            filtrado parcial: el caller ve el rechazo explicito.
        """
        # Lazy imports para evitar ciclo runtime<->knowledge (regla AGENTS §11.7).
        from skillgraph.knowledge.file_scope import (
            AggregatedSignatures,
            ScopeQuery,
            aggregate_signatures,
        )

        # Validacion de tipo: si scope_query no es ScopeQuery, TypeError
        # explicito antes de iterar.
        if not isinstance(scope_query, ScopeQuery):
            raise TypeError(
                f"scope_query debe ser ScopeQuery, recibio {type(scope_query).__name__}"
            )
        if not member_source_ids:
            # Sin miembros: agregacion vacia.
            return AggregatedSignatures(
                scope=scope_query,
                signatures=(),
                total_files=0,
                cobertura_global=0,
            )

        # Aislamiento E2E-08: distinguir source-en-otro-proyecto de
        # source-inexistente. Si el source existe en OTRO proyecto, se
        # rechaza explicitamente (no se filtra contenido). Si NO existe
        # en ningun proyecto, se omite silenciosamente (typo del caller).
        sources_in_scope: list[str] = []
        for source_id in member_source_ids:
            try:
                self.get_source(source_id=source_id)
                sources_in_scope.append(source_id)
            except UnknownSourceError:
                # Distinguir: source-en-otro-proyecto vs no-existe.
                cross = self.storage._conn.execute(
                    "SELECT 1 FROM sources WHERE source_id = ? LIMIT 1",
                    (source_id,),
                ).fetchone()
                if cross is not None:
                    # Existe en OTRO tenant/project: rechazo explicito.
                    # El mensaje NO revela el source_id (regla E2E-08:
                    # no filtrar contenido de otro proyecto).
                    raise UnknownSourceError(
                        "Uno o mas sources pertenecen a otro proyecto; "
                        "rechazado sin filtrar contenido (UAT-EVO-08)"
                    ) from None
                # No existe en ningun proyecto: omitir silenciosamente.

        # Recolectar FileSignatures de cada source existente en el scope.
        signatures_per_source: dict[str, tuple[FileSignature, ...]] = {}
        for source_id in sources_in_scope:
            signatures_per_source[source_id] = self.list_file_signatures_for_source(
                source_id=source_id,
                only_stale=False,
            )

        return aggregate_signatures(
            signatures_per_source=signatures_per_source,
            scope=scope_query,
        )

    # ----- Claims -----

    def record_claim(self, *, claim: Claim) -> ClaimID:
        """Registra un Claim. Convierte FK violation en UnknownEntityError.

        Si el ADT tiene `claim_id=""` (vacio), genera uno determinista
        via UUIDv5 sobre (subject, predicate, source, revision).
        """
        # Si el caller paso claim_id vacio, generamos uno.
        claim_to_record = claim
        if not claim.claim_id:
            generated = make_claim_id(
                subject_entity_id=claim.subject_entity_id,
                predicate=claim.predicate,
                source_id=claim.source_id,
                checked_at_revision=claim.checked_at_revision,
            )
            claim_to_record = Claim(
                claim_id=generated,
                subject_entity_id=claim.subject_entity_id,
                predicate=claim.predicate,
                object_literal=claim.object_literal,
                source_id=claim.source_id,
                evidence_ids=claim.evidence_ids,
                extraction_method=claim.extraction_method,
                extractor_version=claim.extractor_version,
                checked_at_revision=claim.checked_at_revision,
                stale=claim.stale,
            )
        try:
            self.storage.record_claim(
                tenant_id=self.tenant_id,
                project_id=self.project_id,
                claim=claim_to_record,
            )
        except Exception as exc:
            # SQLite emite "FOREIGN KEY constraint failed" sin nombrar la tabla.
            # Distinguimos por el orden de chequeo: SQLite evalua FKs por orden
            # de insercion, asi que si subject_entity_id no existe, falla antes
            # que source_id. Hacemos lookup para saber cual.
            msg = str(exc)
            if "FOREIGN KEY" in msg:
                if (
                    self.storage.get_entity(
                        tenant_id=self.tenant_id,
                        project_id=self.project_id,
                        entity_id=claim.subject_entity_id,
                    )
                    is None
                ):
                    raise UnknownEntityError(
                        "Entity no existe"
                    ) from exc  # NO expone entity_id (S2/I)
                raise UnknownSourceError(
                    "Source no existe"
                ) from exc  # NO expone source_id (S2/I)
            raise
        return claim_to_record.claim_id

    def get_claim(self, *, claim_id: ClaimID) -> Claim:
        """Recupera un Claim. UnknownClaimError si no existe."""
        result = self.storage.get_claim(
            tenant_id=self.tenant_id,
            project_id=self.project_id,
            claim_id=claim_id,
        )
        if result is None:
            raise UnknownClaimError(
                "Claim no encontrado"
            )  # NO expone claim_id (S2/I)
        return result

    def list_claims_for_source(self, *, source_id: SourceID) -> list[Claim]:
        """Lista Claims asociados a una Source."""
        return self.storage.list_claims_for_source(
            tenant_id=self.tenant_id,
            project_id=self.project_id,
            source_id=source_id,
        )

    def list_claims_for_subject(self, *, subject_entity_id: EntityID) -> list[Claim]:
        """Lista Claims cuyo subject_entity_id coincide."""
        import json

        rows = self.storage._conn.execute(
            """
            SELECT * FROM claims
            WHERE tenant_id = ? AND project_id = ? AND subject_entity_id = ?
            ORDER BY checked_at_revision DESC
            """,
            (self.tenant_id, self.project_id, subject_entity_id),
        ).fetchall()
        out: list[Claim] = []
        for row in rows:
            ev_rows = self.storage._conn.execute(
                "SELECT evidence_id FROM claim_evidence WHERE claim_id = ?",
                (row["claim_id"],),
            ).fetchall()
            out.append(
                Claim(
                    claim_id=row["claim_id"],
                    subject_entity_id=row["subject_entity_id"],
                    predicate=row["predicate"],
                    object_literal=json.loads(row["object_literal_json"]),
                    source_id=row["source_id"],
                    evidence_ids=tuple(r["evidence_id"] for r in ev_rows),
                    extraction_method=row["extraction_method"],
                    extractor_version=row["extractor_version"],
                    checked_at_revision=row["checked_at_revision"],
                    stale=bool(row["stale"]),
                )
            )
        return out

    # ----- Findings -----

    def record_finding(self, *, finding: Finding) -> FindingID:
        """Registra un Finding. Si `finding_id=""`, genera uno via UUIDv5."""
        f = finding
        if not finding.finding_id:
            generated = make_finding_id(
                entity_id=finding.entity_id,
                rule_ref=finding.rule_ref,
                rule_version=finding.rule_version,
            )
            f = Finding(
                finding_id=generated,
                entity_id=finding.entity_id,
                observation=finding.observation,
                rule_ref=finding.rule_ref,
                rule_version=finding.rule_version,
                evidence_ids=finding.evidence_ids,
                result=finding.result,
                valid_until_revision=finding.valid_until_revision,
            )
        self.storage.record_finding(
            tenant_id=self.tenant_id,
            project_id=self.project_id,
            finding=f,
        )
        return f.finding_id

    # ----- Outcome traces -----

    def record_trace(self, *, trace: OutcomeTrace) -> TraceID:
        """Registra un OutcomeTrace y sus enlaces preservando orden."""
        self.storage.record_trace(
            tenant_id=self.tenant_id,
            project_id=self.project_id,
            trace=trace,
        )
        return trace.trace_id

    def link_trace(
        self,
        *,
        trace_id: TraceID,
        link_kind: str,
        link_id: str,
        position: int,
    ) -> None:
        """Adjunta un enlace adicional a un trace."""
        self.storage.link_trace(
            tenant_id=self.tenant_id,
            project_id=self.project_id,
            trace_id=trace_id,
            link_kind=link_kind,
            link_id=link_id,
            position=position,
        )

    # ----- Invalidation (delegates to knowledge_invalidator) -----
    # Import lazy aqui para evitar ciclos y para que el invalidator se
    # pueda importar standalone en tests.

    def invalidate_from_source(
        self,
        *,
        source_id: SourceID,
        max_hops: int = 2,
    ) -> list[ClaimID]:
        """Marca stale las Claims que dependen del source (transitivo).

        Wrapper de `knowledge_invalidator.invalidate_from_source`.
        """
        from skillgraph.knowledge.knowledge_invalidator import invalidate_from_source as _inv

        return _inv(
            self,
            source_id=source_id,
            max_hops=max_hops,
        )

    def refresh_source(
        self,
        *,
        source_id: SourceID,
        new_revision: str,
    ) -> list[ClaimID]:
        """Re-valida Claims contra nueva revision (las reactiva)."""
        from skillgraph.knowledge.knowledge_invalidator import refresh_source as _ref

        return _ref(
            self,
            source_id=source_id,
            new_revision=new_revision,
        )

    def list_stale_claims(self) -> list[Claim]:
        """Lista todas las Claims stale del proyecto actual."""
        from skillgraph.knowledge.knowledge_invalidator import list_stale_claims as _ls

        return list(_ls(self))


__all__ = [
    "NAMESPACE_KNOWLEDGE",
    "KnowledgeController",
    "NotFoundError",  # re-export para tests
    "make_claim_id",
    "make_evidence_id",
    "make_finding_id",
]
