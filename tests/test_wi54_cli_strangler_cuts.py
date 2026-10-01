"""Red de contrato WI-54 cortes 3-5: estrangulamiento CLI (round A: promotion).

Patron ADR-0018: los clusters salen a `cli.commands.<dominio>` con sus
helpers privados; los compartidos (`_default_claim_importer`,
`_source_to_payload`, `_entity_to_payload`, `_select_promotion_failpoint`,
`_abort_with_failpoint` — usados tambien por `cmd_run`) viven en
`cli.support` y `runner` conserva alias.
"""

from __future__ import annotations

import skillgraph.cli.commands.promotion as promotion
from skillgraph.cli import runner


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

    def test_runner_has_no_private_copies(self) -> None:
        import inspect

        source = inspect.getsource(runner)
        assert "def _apply_pending_promotions" not in source
        assert "def _reconcile_summaries" not in source
        assert "def _entity_to_payload" not in source
