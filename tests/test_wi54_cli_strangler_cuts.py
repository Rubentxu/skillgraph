"""Red de contrato WI-54 cortes 3-5: estrangulamiento CLI (round A: promotion).

Patron ADR-0018: los clusters salen a `cli.commands.<dominio>` con sus
helpers privados; los compartidos (`_default_claim_importer`,
`_source_to_payload`, `_entity_to_payload`, `_select_promotion_failpoint`,
`_abort_with_failpoint` — usados tambien por `cmd_run`) viven en
`cli.support` y `runner` conserva alias.
"""

from __future__ import annotations

import skillgraph.cli.commands.knowledge as knowledge
import skillgraph.cli.commands.pack as pack
import skillgraph.cli.commands.promotion as promotion
from skillgraph.cli import runner
from skillgraph.cli.support import _build_registry_for_project


class TestPromotionStranglerIdentity:
    """runner.cmd_promotion_* DEBE ser el componente real, no una copia."""

    def test_submit_identity(self) -> None:
        assert runner.cmd_promotion_submit is promotion.cmd_promotion_submit

    def test_list_identity(self) -> None:
        assert runner.cmd_promotion_list is promotion.cmd_promotion_list

    def test_reconcile_identity(self) -> None:
        assert runner.cmd_promotion_reconcile is promotion.cmd_promotion_reconcile


class TestSharedHelpersPlacement:
    """Los helpers resultaron exclusivos del cluster: viven en promotion.

    El analisis inicial los marco como compartidos con cmd_run, pero el
    barrido post-extraccion mostro cero usos en runner: se reubican al
    componente (regla ADR-0018: uso exclusivo -> va con el cluster).
    """

    def test_promotion_owns_the_helpers(self) -> None:
        assert hasattr(promotion, "_abort_with_failpoint")
        assert hasattr(promotion, "_default_claim_importer")
        assert hasattr(promotion, "_select_promotion_failpoint")
        assert hasattr(promotion, "_source_to_payload")
        assert hasattr(promotion, "_entity_to_payload")


class TestPackStranglerIdentity:
    """Corte 4: cmd_pack_* sale a cli.commands.pack; el builder compartido
    (1 uso fuera del cluster: cmd_init) vive en support."""

    def test_load_identity(self) -> None:
        assert runner.cmd_pack_load is pack.cmd_pack_load

    def test_import_identity(self) -> None:
        assert runner.cmd_pack_import is pack.cmd_pack_import

    def test_registry_builder_shared_in_support(self) -> None:
        assert runner._build_registry_for_project is _build_registry_for_project


class TestKnowledgeStranglerIdentity:
    """Corte 5: los 5 handlers cmd_knowledge_* salen a cli.commands.knowledge;
    _open_known_project (3 usos fuera del cluster) vive en support."""

    def test_stale_identity(self) -> None:
        assert runner.cmd_knowledge_stale is knowledge.cmd_knowledge_stale

    def test_invalidate_identity(self) -> None:
        assert runner.cmd_knowledge_invalidate is knowledge.cmd_knowledge_invalidate

    def test_refresh_identity(self) -> None:
        assert runner.cmd_knowledge_refresh is knowledge.cmd_knowledge_refresh

    def test_compile_identity(self) -> None:
        assert runner.cmd_knowledge_compile is knowledge.cmd_knowledge_compile

    def test_trace_identity(self) -> None:
        assert runner.cmd_knowledge_trace is knowledge.cmd_knowledge_trace

    def test_known_project_opener_is_cluster_private(self) -> None:
        """Los '3 usos fuera' eran comentarios: es exclusiva del cluster."""
        assert hasattr(knowledge, "_open_known_project")
        assert not hasattr(runner, "_open_known_project")

    def test_runner_has_no_private_copies(self) -> None:
        import inspect

        source = inspect.getsource(runner)
        assert "def _apply_pending_promotions" not in source
        assert "def _reconcile_summaries" not in source
        assert "def _entity_to_payload" not in source
