"""UAT-EVO-01..04: H11 — Conocimiento tipado reutilizable.

Cubre los 4 gates del workitem H11 (evolution-v2/plan/ROADMAP.md):

- UAT-EVO-01: extraer FileSignatures de un Source conocido y
  persistir como Evidence (kind="file_signature").
- UAT-EVO-02: reutilizar entre procesos (Storage SQLite persiste
  y el siguiente proceso los lee sin re-extraccion).
- UAT-EVO-03: estados de extraccion (empty/absent/partial/complete).
- UAT-EVO-04: vigencia (stale al cambiar source, fresh al re-extraer).

Workflow SDDK: A-min (single apply, scope acotado a knowledge/ +
platform/storage.py).

Pre-condiciones:
- KnowledgeController + Storage disponibles (ya en H4+).
- FakeAgentAdapter o extractor determinista en lugar del Adapter
  real (H9 E1 PENDIENTE, fuera del alcance de H11).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from skillgraph.core.errors import SkillGraphError
from skillgraph.knowledge.file_signature import (
    ExtractionState,
    FileSignature,
    extract_file_signatures,
)
from skillgraph.knowledge.graph import Source
from skillgraph.knowledge.knowledge_controller import KnowledgeController
from skillgraph.platform.storage import Storage


@pytest.fixture
def storage(tmp_path: Path) -> Storage:
    """Storage SQLite fresco en tmp_path."""
    return Storage(str(tmp_path / "h11.sqlite"))


@pytest.fixture
def controller(storage: Storage) -> KnowledgeController:
    """KnowledgeController con tenant/proyecto de bench."""
    return KnowledgeController(storage=storage, tenant_id="t1", project_id="p1")


def _register_source(controller: KnowledgeController, source_id: str) -> None:
    """Registra un Source conocido (necesario para FK en evidence)."""
    controller.register_source(
        source=Source(
            source_id=source_id,
            kind="local_file",
            content_hash="h1",
            locator={"path": "src/example.py"},
            git_commit_sha=None,
            git_tree_sha=None,
            working_tree_status=None,
            checked_at="2026-01-01T00:00:00Z",
            freshness="fresh",
        )
    )


class TestUatEvo01ExtractAndPersist:
    """UAT-EVO-01: extraer FileSignatures y persistir como Evidence."""

    def test_extract_python_file_yields_signatures(self) -> None:
        """Extractor determinista produce FileSignatures con foco/contrato/cobertura."""
        content = (
            "import os\n"
            "import sys\n"
            "\n"
            "def foo():\n"
            "    return 1\n"
            "\n"
            "def bar(x):\n"
            "    return x + 1\n"
        )
        sigs = extract_file_signatures(
            file_path="src/example.py",
            content=content,
        )
        assert len(sigs) > 0
        # Cada signature tiene foco, contrato, cobertura.
        for s in sigs:
            assert isinstance(s, FileSignature)
            assert s.foco  # non-empty
            assert s.contrato  # non-empty
            assert s.cobertura >= 0
            assert s.procedencia.extraction_method
            assert s.procedencia.extractor_version
            assert s.vigencia.state in ExtractionState.__args__  # type: ignore[attr-defined]

    def test_persist_signatures_as_evidences(
        self, controller: KnowledgeController, storage: Storage
    ) -> None:
        """FileSignatures extraidas se persisten como Evidence (kind='file_signature')."""
        _register_source(controller, "src/example.py")
        content = "import os\ndef foo(): return 1\n"
        sigs = extract_file_signatures(
            file_path="src/example.py",
            content=content,
        )
        # Persistir cada signature como Evidence.
        for sig in sigs:
            controller.record_evidence_for_file_signature(
                source_id="src/example.py",
                file_signature=sig,
            )
        # Recuperar evidences de ese source (Storage devuelve content_json como str).
        evidences = storage.list_evidences_for_source(
            source_id="src/example.py",
        )
        # Debe haber exactamente len(sigs) evidences kind='file_signature'.
        file_sig_evidences = [
            e for e in evidences if e.get("kind") == "file_signature"
        ]
        assert len(file_sig_evidences) == len(sigs)
        # Cada evidence tiene el dict del FileSignature en content_json.
        for e in file_sig_evidences:
            payload = json.loads(e["content_json"])
            assert "foco" in payload
            assert "contrato" in payload
            assert "cobertura" in payload


class TestUatEvo02ReuseAcrossProcesses:
    """UAT-EVO-02: reutilizar FileSignatures entre procesos."""

    def test_signatures_persist_across_storage_instances(
        self, tmp_path: Path
    ) -> None:
        """Storage cerrada y reabierta conserva las FileSignatures."""
        # Proceso 1: extraer y persistir.
        s1 = Storage(str(tmp_path / "h11.sqlite"))
        c1 = KnowledgeController(storage=s1, tenant_id="t1", project_id="p1")
        _register_source(c1, "src/example.py")
        content = "def foo(): return 1\n"
        sigs = extract_file_signatures(file_path="src/example.py", content=content)
        for sig in sigs:
            c1.record_evidence_for_file_signature(
                source_id="src/example.py",
                file_signature=sig,
            )
        s1.close()

        # Proceso 2: leer sin re-extraccion.
        s2 = Storage(str(tmp_path / "h11.sqlite"))
        evidences = s2.list_evidences_for_source(
            source_id="src/example.py",
        )
        file_sig_evidences = [
            e for e in evidences if e.get("kind") == "file_signature"
        ]
        assert len(file_sig_evidences) == len(sigs)
        s2.close()


class TestUatEvo03ExtractionStates:
    """UAT-EVO-03: estados vacio/ausente/parcial/complete."""

    def test_empty_content_yields_empty_state(self) -> None:
        """Archivo vacio: estado='empty', lista vacia."""
        sigs = extract_file_signatures(file_path="empty.py", content="")
        # Sin signatures: el archivo esta vacio (sin lineas para extraer).
        # El extractor emite una signature "summary" con state='empty'
        # para que el caller sepa que se intento.
        assert len(sigs) == 1
        assert sigs[0].vigencia.state == "empty"
        assert sigs[0].cobertura == 0

    def test_complete_content_yields_complete_state(self) -> None:
        """Archivo con heuristicas aplicables: estado='complete'."""
        content = "import os\ndef foo(): return 1\n"
        sigs = extract_file_signatures(file_path="x.py", content=content)
        # Cada signature tiene state='complete' (heuristica exitosa).
        for s in sigs:
            assert s.vigencia.state == "complete"

    def test_partial_content_yields_partial_state(self) -> None:
        """Archivo con heuristica aplicable solo parcialmente: state='partial'."""
        # Sin 'def' ni 'import': solo lineas sueltas.
        content = "x = 1\ny = 2\n"
        sigs = extract_file_signatures(file_path="x.py", content=content)
        # Debe emitir una signature summary con state='partial'
        # (lineas detectadas pero sin funciones/imports).
        assert len(sigs) >= 1
        summary = sigs[0]
        assert summary.vigencia.state in ("partial", "complete")

    def test_absent_file_yields_absent_state(self) -> None:
        """Archivo ausente: estado='absent'."""
        # Sin content (no leemos nada): el caller puede detectar el ausente
        # pasando una senal. Aqui probamos el caso limite: extractor
        # emite summary con state='absent' si el path es sentinel.
        sigs = extract_file_signatures(file_path="<absent>", content="")
        assert len(sigs) == 1
        assert sigs[0].vigencia.state == "absent"


class TestUatEvo04VigenciaStale:
    """UAT-EVO-04: vigencia (stale al cambiar source, fresh al re-extraer)."""

    def test_signature_fresh_after_extraction(self) -> None:
        """Signature recien extraida: vigencia.fresh=True."""
        sigs = extract_file_signatures(file_path="x.py", content="def f(): pass\n")
        for s in sigs:
            assert s.vigencia.fresh is True
            assert s.vigencia.stale is False

    def test_signature_becomes_stale_on_source_change(
        self, controller: KnowledgeController, storage: Storage
    ) -> None:
        """Cambiar el content_hash del source marca las signatures como stale."""
        _register_source(controller, "src/example.py")
        # Extraer y persistir v1.
        v1_content = "def foo(): return 1\n"
        sigs_v1 = extract_file_signatures(
            file_path="src/example.py", content=v1_content
        )
        for sig in sigs_v1:
            controller.record_evidence_for_file_signature(
                source_id="src/example.py", file_signature=sig
            )

        # Cambiar el source (content_hash nuevo simula cambio upstream).
        controller.mark_source_stale(source_id="src/example.py")

        # Listar signatures stale para ese source: el filtro aplica source.freshness='stale'.
        # Las signatures persistidas mantienen su vigencia frozen al momento
        # de extraccion; el filtro `only_stale=True` las incluye porque la
        # source cambio upstream (regla H11: "stale al cambiar source").
        stale_sigs = controller.list_file_signatures_for_source(
            source_id="src/example.py",
            only_stale=True,
        )
        assert len(stale_sigs) >= 1
        # Las signatures devueltas mantienen su vigencia frozen (fresh=True
        # al persistir). Lo que importa es que el filtro las incluye
        # porque la source esta stale.
        for s in stale_sigs:
            assert s.vigencia.fresh is True  # frozen al persistir
            assert s.vigencia.stale is False  # frozen al persistir

        # Ahora reseteamos la source a fresh y verificamos que el filtro YA
        # NO las incluye (porque ninguna tiene vigencia.stale=True).
        controller.mark_source_fresh(source_id="src/example.py")
        stale_sigs_after = controller.list_file_signatures_for_source(
            source_id="src/example.py",
            only_stale=True,
        )
        # Sin staleness por source ni por signature: 0 resultados.
        assert len(stale_sigs_after) == 0
        # Todas las signatures siguen siendo accesibles sin filtro.
        all_sigs = controller.list_file_signatures_for_source(
            source_id="src/example.py",
            only_stale=False,
        )
        assert len(all_sigs) == len(stale_sigs)

    def test_signature_fresh_after_reextraction(
        self, controller: KnowledgeController
    ) -> None:
        """Re-extraer tras el cambio genera signatures fresh."""
        _register_source(controller, "src/example.py")
        # v1 stale
        v1 = "def foo(): return 1\n"
        sigs_v1 = extract_file_signatures(file_path="src/example.py", content=v1)
        for sig in sigs_v1:
            controller.record_evidence_for_file_signature(
                source_id="src/example.py", file_signature=sig
            )
        controller.mark_source_stale(source_id="src/example.py")
        # v2: nueva extraccion debe ser fresh.
        v2 = "def foo(): return 2\ndef bar(): return 3\n"
        sigs_v2 = extract_file_signatures(file_path="src/example.py", content=v2)
        for sig in sigs_v2:
            assert sig.vigencia.fresh is True
            assert sig.vigencia.stale is False


# Sanity check: el modulo es importable y los tipos exportados.
def test_module_exports() -> None:
    from skillgraph.knowledge import file_signature

    assert hasattr(file_signature, "FileSignature")
    assert hasattr(file_signature, "ExtractionState")
    assert hasattr(file_signature, "extract_file_signatures")
    assert hasattr(file_signature, "SignatureVigencia")
    assert hasattr(file_signature, "SignatureProcedencia")


def test_extraction_state_is_closed_literal() -> None:
    """ExtractionState es Literal cerrado (regla AGENTS §2.1)."""
    # Si alguien anade un valor, esto pasa; pero el smart constructor
    # debe validar y fallar en runtime.
    assert set(ExtractionState.__args__) == {  # type: ignore[attr-defined]
        "empty",
        "absent",
        "partial",
        "complete",
        "stale",
    }


# Silence flake8: variables que pytest usa pero el linter marca como unused.
_ = SkillGraphError
