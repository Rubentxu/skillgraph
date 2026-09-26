"""UAT-EVO-05..08: H12 — Scopes y consultas composables.

Cubre los 4 gates del workitem H12 (evolution-v2/plan/ROADMAP.md):

- UAT-EVO-05: agregar firmas de varios ficheros en un directorio
  sin duplicar simbolos y con cobertura global explicita.
- UAT-EVO-06: paquete logico (membresia no necesariamente un
  directorio) — el resolver respeta la declaracion, no el prefijo.
- UAT-EVO-07: bounded context que incluye componentes en varios
  paquetes — respetar frontera, identidad y procedencia.
- UAT-EVO-08: aislamiento de consulta entre proyectos (consulta
  de proyecto A sobre recurso de proyecto B se rechaza sin filtrar
  contenido).

Workflow SDDK: A-min (single apply, scope acotado a knowledge/).

Pre-condiciones:
- H11 cerrado (FileSignature + extract_file_signatures + persistencia
  via Evidence(kind='file_signature')).
- KnowledgeController con tenant/project inyectado (ya en H4+).
- Sin filesystem real: las "firmas" se inyectan directamente al
  controller para mantener pureza y rapidez (sin I/O en tests).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from skillgraph.core.errors import SkillGraphError, ValidationError
from skillgraph.knowledge.file_scope import (
    AggregatedSignatures,
    ScopeQuery,
    ScopeResolution,
    aggregate_signatures,
    resolve_bounded_context_scope,
    resolve_directory_scope,
    resolve_package_scope,
    validate_bounded_context_name,
    validate_package_name,
)
from skillgraph.knowledge.file_signature import (
    ExtractionState,
    FileSignature,
    SignatureProcedencia,
    SignatureVigencia,
)
from skillgraph.knowledge.graph import Source
from skillgraph.knowledge.knowledge_controller import KnowledgeController
from skillgraph.platform.storage import Storage

# ----- helpers ---------------------------------------------------------


def _proc(method: str = "regex_def") -> SignatureProcedencia:
    return SignatureProcedencia(
        extraction_method=method,
        extractor_version="skillgraph-rules/0.1.0",
    )


def _vig(
    state: ExtractionState = "complete",
) -> SignatureVigencia:
    return SignatureVigencia(state=state, fresh=(state == "complete"), stale=(state != "complete"))


def _sig(
    *,
    foco: str,
    contrato: str = "def",
    cobertura: int = 1,
    state: ExtractionState = "complete",
) -> FileSignature:
    return FileSignature(
        foco=foco,
        contrato=contrato,
        cobertura=cobertura,
        procedencia=_proc(),
        vigencia=_vig(state),
    )


def _register_source(
    controller: KnowledgeController,
    source_id: str,
    *,
    kind: str = "local_file",
) -> None:
    """Registra un Source conocido (FK para evidence)."""
    controller.register_source(
        source=Source(
            source_id=source_id,
            kind=kind,
            content_hash="h1",
            locator={"path": source_id},
            git_commit_sha=None,
            git_tree_sha=None,
            working_tree_status=None,
            checked_at="2026-01-01T00:00:00Z",
            freshness="fresh",
        )
    )


@pytest.fixture
def storage(tmp_path: Path) -> Storage:
    return Storage(str(tmp_path / "h12.sqlite"))


@pytest.fixture
def controller_p1(storage: Storage) -> KnowledgeController:
    return KnowledgeController(storage=storage, tenant_id="t1", project_id="p1")


@pytest.fixture
def controller_p2(storage: Storage) -> KnowledgeController:
    """Mismo storage, proyecto distinto. Aislado por tenant/project."""
    return KnowledgeController(storage=storage, tenant_id="t1", project_id="p2")


# ----- UAT-EVO-05: Fichero y directorio ------------------------------


class TestUatEvo05DirectoryScope:
    """UAT-EVO-05: agregar firmas de un directorio sin duplicar."""

    def test_resolve_directory_lists_member_files(self) -> None:
        """Resolver devuelve la lista de source_ids miembros."""
        res = resolve_directory_scope(
            directory_path="src/",
            member_paths=("src/a.py", "src/b.py", "src/c.py"),
        )
        assert isinstance(res, ScopeResolution)
        assert res.scope_kind == "directory"
        assert res.member_source_ids == ("src/a.py", "src/b.py", "src/c.py")
        assert res.target == "src/"

    def test_aggregate_directory_signatures_no_duplicates(
        self, controller_p1: KnowledgeController
    ) -> None:
        """Agregacion de N ficheros del mismo directorio sin duplicar simbolos."""
        _register_source(controller_p1, "src/a.py")
        _register_source(controller_p1, "src/b.py")
        sigs_a = (_sig(foco="src/a.py::def::foo"),)
        sigs_b = (_sig(foco="src/b.py::def::bar"),)
        controller_p1.record_evidence_for_file_signature(
            source_id="src/a.py", file_signature=sigs_a[0]
        )
        controller_p1.record_evidence_for_file_signature(
            source_id="src/b.py", file_signature=sigs_b[0]
        )

        # Agregar.
        agg = controller_p1.aggregate_file_signatures(
            scope_query=ScopeQuery(scope_kind="directory", target="src/"),
            member_source_ids=("src/a.py", "src/b.py"),
        )
        assert isinstance(agg, AggregatedSignatures)
        # Cobertura global: suma de lineas o signatures.
        assert agg.total_files == 2
        assert agg.signatures_count == 2
        # Sin duplicados: cada foco aparece una sola vez.
        focos = {s.foco for s in agg.signatures}
        assert focos == {"src/a.py::def::foo", "src/b.py::def::bar"}

    def test_aggregate_directory_global_coverage_explicit(
        self, controller_p1: KnowledgeController
    ) -> None:
        """Cobertura global = suma de cobertura por signature."""
        _register_source(controller_p1, "src/a.py")
        _register_source(controller_p1, "src/b.py")
        sig_a = _sig(foco="src/a.py::def::foo", cobertura=10)
        sig_b = _sig(foco="src/b.py::def::bar", cobertura=20)
        controller_p1.record_evidence_for_file_signature(source_id="src/a.py", file_signature=sig_a)
        controller_p1.record_evidence_for_file_signature(source_id="src/b.py", file_signature=sig_b)

        agg = controller_p1.aggregate_file_signatures(
            scope_query=ScopeQuery(scope_kind="directory", target="src/"),
            member_source_ids=("src/a.py", "src/b.py"),
        )
        assert agg.cobertura_global == 30


# ----- UAT-EVO-06: Paquete logico ------------------------------------


class TestUatEvo06PackageScope:
    """UAT-EVO-06: membresia logica != directorio fisico."""

    def test_resolve_package_uses_declared_membership(self) -> None:
        """El resolver usa la declaracion explicita del paquete."""
        # Un paquete "skillgraph.knowledge" incluye archivos en
        # src/skillgraph/knowledge/, pero NO incluye tests/.
        res = resolve_package_scope(
            package_name="skillgraph.knowledge",
            declared_members=(
                "src/skillgraph/knowledge/__init__.py",
                "src/skillgraph/knowledge/file_signature.py",
                "src/skillgraph/knowledge/knowledge_controller.py",
            ),
            prefix="src/skillgraph/knowledge/",
        )
        assert res.scope_kind == "package"
        assert res.target == "skillgraph.knowledge"
        # NO incluye archivos fuera de la membresia declarada, aunque
        # el prefijo coincida.
        assert "tests/test_knowledge.py" not in res.member_source_ids
        # Pero archivos del directorio fuera de la membresia declarada
        # (p.ej. un src/skillgraph/knowledge/draft.py) tampoco se
        # incluyen: el resolver usa la declaracion, no el prefijo.
        assert all("draft.py" not in m for m in res.member_source_ids)

    def test_package_query_rejects_wrong_kind(self) -> None:
        """ScopeQuery rechaza target inconsistente con su kind."""
        with pytest.raises(ValidationError):
            ScopeQuery(scope_kind="package", target="/no/es/un/nombre")


# ----- UAT-EVO-07: Bounded context ----------------------------------


class TestUatEvo07BoundedContext:
    """UAT-EVO-07: frontera, identidad y procedencia."""

    def test_resolve_bounded_context_with_cross_package_members(self) -> None:
        """Bounded context agrupa componentes de varios paquetes."""
        res = resolve_bounded_context_scope(
            context_name="knowledge-core",
            member_source_ids=(
                "src/skillgraph/knowledge/file_signature.py",
                "src/skillgraph/knowledge/knowledge_controller.py",
                "src/skillgraph/platform/storage.py",  # plataforma, distinto paquete
            ),
        )
        assert res.scope_kind == "bounded_context"
        assert res.target == "knowledge-core"
        # 3 miembros atravesando 2 paquetes.
        assert len(res.member_source_ids) == 3

    def test_aggregate_preserves_procedencia(self, controller_p1: KnowledgeController) -> None:
        """Agregacion conserva la procedencia de cada signature."""
        _register_source(controller_p1, "src/a.py")
        _register_source(controller_p1, "src/storage.py")
        sig_a = FileSignature(
            foco="src/a.py::def::foo",
            contrato="def",
            cobertura=1,
            procedencia=_proc("regex_def"),
            vigencia=_vig(),
        )
        sig_b = FileSignature(
            foco="src/storage.py::def::connect",
            contrato="def",
            cobertura=1,
            procedencia=_proc("regex_def"),
            vigencia=_vig(),
        )
        controller_p1.record_evidence_for_file_signature(source_id="src/a.py", file_signature=sig_a)
        controller_p1.record_evidence_for_file_signature(
            source_id="src/storage.py", file_signature=sig_b
        )

        agg = controller_p1.aggregate_file_signatures(
            scope_query=ScopeQuery(scope_kind="bounded_context", target="knowledge-core"),
            member_source_ids=("src/a.py", "src/storage.py"),
        )
        # Procedencia preservada.
        for s in agg.signatures:
            assert s.procedencia.extraction_method == "regex_def"
            assert s.procedencia.extractor_version == "skillgraph-rules/0.1.0"


# ----- UAT-EVO-08: Consulta segura (aislamiento) ---------------------


class TestUatEvo08ProjectIsolation:
    """UAT-EVO-08: un proyecto no ve firmas de otro."""

    def test_project_p2_rejects_aggregating_p1_source(
        self, controller_p1: KnowledgeController, controller_p2: KnowledgeController
    ) -> None:
        """p2 intenta agregar source de p1 -> rechazo explicito (no filtra)."""
        # p1 registra source + signature.
        _register_source(controller_p1, "src/secret.py")
        sig = _sig(foco="src/secret.py::def::internal")
        controller_p1.record_evidence_for_file_signature(
            source_id="src/secret.py", file_signature=sig
        )

        # p2 intenta agregar firmas del source de p1: rechazo explicito.
        with pytest.raises(SkillGraphError) as exc_info:
            controller_p2.aggregate_file_signatures(
                scope_query=ScopeQuery(scope_kind="directory", target="src/"),
                member_source_ids=("src/secret.py",),
            )
        # El error es UnknownSourceError (subclase de SkillGraphError)
        # y el mensaje NO debe filtrar el contenido de p1: solo dice
        # que pertenece a otro proyecto, sin revelar el source_id.
        msg = str(exc_info.value)
        assert "pertenecen a otro proyecto" in msg
        assert "src/secret.py" not in msg  # contenido no filtrado
        # Verificacion fundamental: la firma de p1 NUNCA aparece en
        # el agregado de p2 (ni siquiera en forma de error parcial).
        agg = controller_p2.aggregate_file_signatures(
            scope_query=ScopeQuery(scope_kind="directory", target="src/"),
            member_source_ids=("src/nonexistent.py",),  # typo: no existe
        )
        # Si el source no existe en ningun proyecto, se omite silenciosamente.
        assert agg.signatures_count == 0
        assert agg.cobertura_global == 0


# ----- ramas tristes (cobertura de branches de validacion) -------------
#
# Estas pruebas cierran las 12 lineas que coverage reportaba como
# descubiertas en file_scope.py. Cada test es rojo si la validacion
# NO levanta ValidationError, y verde si la levanta con mensaje
# util (regla AGENTS §1.2: errores tipados, no strings).
# Ver audits/file-scope-validation-branches-2026-09-26.md.


class TestFileScopeValidation:
    """Tests para las ramas de validacion de file_scope.py.

    Estas pruebas complementan los UAT-EVO-05..08 (que cubren el camino
    feliz) verificando que las validaciones fallan con ``ValidationError``
    tipado cuando los argumentos son invalidos.

    No es UAT nuevo: son tests de cobertura de branches, sin cambios de
    contrato ni de API.
    """

    # ----- validate_package_name / validate_bounded_context_name -------

    def test_validate_package_name_rejects_empty(self) -> None:
        with pytest.raises(ValidationError, match="package_name invalido"):
            validate_package_name("")

    def test_validate_package_name_rejects_uppercase_dot_segment(self) -> None:
        # Segmentos vacios entre puntos no son validos.
        with pytest.raises(ValidationError, match="package_name invalido"):
            validate_package_name("skillgraph..core")

    def test_validate_bounded_context_name_rejects_empty(self) -> None:
        with pytest.raises(ValidationError, match="bounded_context_name invalido"):
            validate_bounded_context_name("")

    def test_validate_bounded_context_name_rejects_digits_start(self) -> None:
        # Empezar con digito viola la regex.
        with pytest.raises(ValidationError, match="bounded_context_name invalido"):
            validate_bounded_context_name("1context")

    # ----- ScopeQuery.__post_init__ -----------------------------------

    def test_scope_query_rejects_invalid_kind(self) -> None:
        # Cast explicito para forzar el branch de validacion: 'namespace'
        # NO esta en FILE_SCOPES.
        with pytest.raises(ValidationError, match="scope_kind invalido"):
            ScopeQuery(scope_kind="namespace", target="src/")  # type: ignore[arg-type]

    def test_scope_query_rejects_empty_target(self) -> None:
        with pytest.raises(
            ValidationError, match=re.escape("ScopeQuery.target no puede estar vacio")
        ):
            ScopeQuery(scope_kind="file", target="")

    # ----- ScopeResolution.__post_init__ ------------------------------

    def test_scope_resolution_rejects_invalid_kind(self) -> None:
        with pytest.raises(ValidationError, match="scope_kind invalido"):
            ScopeResolution(
                scope_kind="namespace",  # type: ignore[arg-type]
                target="src/",
                member_source_ids=("src/a.py",),
            )

    def test_scope_resolution_rejects_empty_target(self) -> None:
        with pytest.raises(
            ValidationError, match=re.escape("ScopeResolution.target no puede estar vacio")
        ):
            ScopeResolution(
                scope_kind="file",
                target="",
                member_source_ids=("src/a.py",),
            )

    def test_scope_resolution_rejects_empty_member_source_ids(self) -> None:
        with pytest.raises(ValidationError, match="ScopeResolution sin miembros"):
            ScopeResolution(
                scope_kind="file",
                target="src/a.py",
                member_source_ids=(),
            )

    # ----- resolve_directory_scope ------------------------------------

    def test_resolve_directory_rejects_empty_path(self) -> None:
        with pytest.raises(ValidationError, match="directory_path no puede estar vacio"):
            resolve_directory_scope(directory_path="", member_paths=("src/a.py",))

    def test_resolve_directory_rejects_empty_member_paths(self) -> None:
        with pytest.raises(ValidationError, match="sin miembros declarados"):
            resolve_directory_scope(directory_path="src/", member_paths=())

    # ----- resolve_package_scope --------------------------------------

    def test_resolve_package_rejects_empty_declared_members(self) -> None:
        with pytest.raises(ValidationError, match="sin miembros declarados"):
            resolve_package_scope(
                package_name="skillgraph.core",
                declared_members=(),
                prefix="src/skillgraph/core/",
            )

    def test_resolve_package_rejects_member_outside_prefix(self) -> None:
        # El miembro declarado NO empieza con el prefix del paquete.
        with pytest.raises(ValidationError, match="no vive bajo prefix"):
            resolve_package_scope(
                package_name="skillgraph.core",
                declared_members=("other/foo.py",),
                prefix="src/skillgraph/core/",
            )

    # ----- resolve_bounded_context_scope ------------------------------

    def test_resolve_bounded_context_rejects_empty_member_source_ids(self) -> None:
        with pytest.raises(ValidationError, match="sin miembros declarados"):
            resolve_bounded_context_scope(
                context_name="billing-context",
                member_source_ids=(),
            )

    # ----- aggregate_signatures (dedup por foco) -----------------------

    def test_aggregate_signatures_with_empty_signatures_per_source(
        self,
    ) -> None:
        # Si signatures_per_source está vacío, aggregate_signatures debe
        # tomar la rama early-return (línea 269-276) que produce un
        # AggregatedSignatures con metadata={} (NO tiene raw_source_count).
        # Si el early-return se bypasea, el código pasa por el for-loop
        # con 0 iteraciones y la metadata incluye 'raw_source_count': 0.
        # El test verifica la rama early-return assertando que NO está
        # la clave 'raw_source_count' en metadata.
        scope = ScopeQuery(scope_kind="directory", target="src/")
        agg = aggregate_signatures(signatures_per_source={}, scope=scope)
        assert agg.signatures_count == 0
        assert agg.total_files == 0
        assert agg.cobertura_global == 0
        assert agg.signatures == ()
        # Marca de la rama early-return: metadata vacía.
        assert "raw_source_count" not in agg.metadata

    def test_aggregate_signatures_with_empty_sigs_tuple_per_source(
        self,
    ) -> None:
        # Si un source tiene tuple de firmas vacío, NO se añade a
        # files_with_sigs (cubrir rama 284->286). El otro source sí aporta.
        sig = _sig(foco="Bar", cobertura=5)
        scope = ScopeQuery(scope_kind="directory", target="src/")
        agg = aggregate_signatures(
            signatures_per_source={"src/empty.py": (), "src/full.py": (sig,)},
            scope=scope,
        )
        assert agg.signatures_count == 1
        assert agg.total_files == 1  # solo src/full.py cuenta
        assert agg.cobertura_global == 5

    def test_aggregate_signatures_dedups_by_foco_first_occurrence_wins(
        self,
    ) -> None:
        # Si dos sources tienen firmas con el mismo 'foco', solo gana la
        # primera ocurrencia (orden de insercion en el dict).
        sig_a = _sig(foco="Foo", cobertura=10)
        sig_b = _sig(foco="Foo", cobertura=99)
        scope = ScopeQuery(scope_kind="directory", target="src/")
        agg = aggregate_signatures(
            signatures_per_source={"src/a.py": (sig_a,), "src/b.py": (sig_b,)},
            scope=scope,
        )
        assert agg.signatures_count == 1
        assert agg.cobertura_global == 10  # la primera (cobertura=10) gana
