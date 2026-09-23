"""Tests focalizados de las ramas de error del parser Markdown+YAML.

Cubre las 7 ramas de validacion que pytest-cov reporta como uncovered
en `src/skillgraph/parser.py` cuando se ejecuta la suite completa:

- _parse_yaml: YAML invalido (YAMLError) y YAML no-dict a nivel raiz.
- parse_markdown: input no-string, apiVersion/kind faltante o no-string,
  metadata/spec no-mapping, namespace no-string.

NO duplica lo que ya cubren tests/test_s0_brick_minimo.py (happy paths
via parse_file). Aqui solo se verifica que las ramas de error emiten
ParseError con mensaje util para debugging contractual.

Ver specs/h4-slice-3.md (stewardship de cobertura).
"""

from __future__ import annotations

import pytest

from skillgraph import ParseError, ResourceIdentity
from skillgraph.resources.parser import parse_markdown

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _identity() -> ResourceIdentity:
    return ResourceIdentity(
        tenant_id="t",
        project_id="p",
        namespace="ns-test",
        kind="ActionNode",
        name="any",
    )


VALID_FRONT = """---
apiVersion: skillgraph.dev/v1alpha1
kind: ActionNode
metadata:
  name: test
  namespace: ns-test
spec:
  capabilities:
    - lint
---
# body markdown
"""


# ---------------------------------------------------------------------------
# T1: _parse_yaml error branches
# ---------------------------------------------------------------------------


def test_parse_markdown_raises_on_yaml_invalid_syntax() -> None:
    """YAML malformado (e.g. tabuladores invalidos) emite ParseError."""
    bad_yaml = VALID_FRONT.replace("skillgraph.dev/v1alpha1", ": : invalid")
    with pytest.raises(ParseError, match="YAML inv"):
        parse_markdown(bad_yaml, source="bad.md", identity=_identity())


def test_parse_markdown_raises_when_yaml_top_level_is_list() -> None:
    """YAML cuyo top-level es lista (no dict) emite ParseError.

    El parser exige un mapping a nivel raiz para poder extraer
    apiVersion/kind/metadata/spec.
    """
    list_yaml = """---
- uno
- dos
---
"""
    with pytest.raises(ParseError, match="mapping en el nivel superior"):
        parse_markdown(list_yaml, source="list.md", identity=_identity())


def test_parse_markdown_raises_when_yaml_top_level_is_scalar() -> None:
    """YAML cuyo top-level es escalar (e.g. '42') emite ParseError."""
    scalar_yaml = """---
42
---
"""
    with pytest.raises(ParseError, match="mapping en el nivel superior"):
        parse_markdown(scalar_yaml, source="scalar.md", identity=_identity())


# ---------------------------------------------------------------------------
# T2: parse_markdown input validation
# ---------------------------------------------------------------------------


def test_parse_markdown_raises_when_input_not_string() -> None:
    """Entrada que no es texto (e.g. bytes, int, None) emite ParseError."""
    with pytest.raises(ParseError, match="debe ser texto"):
        parse_markdown(123, source="not-text.md", identity=_identity())  # type: ignore[arg-type]


def test_parse_markdown_raises_when_input_is_bytes() -> None:
    """Bytes tampoco son aceptados (input debe ser str)."""
    with pytest.raises(ParseError, match="debe ser texto"):
        parse_markdown(b"---\nkind: X\n---", source="bytes.md", identity=_identity())  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# T3: parse_markdown missing-field validation
# ---------------------------------------------------------------------------


def test_parse_markdown_raises_when_api_version_missing() -> None:
    """apiVersion ausente emite ParseError."""
    no_api = """---
kind: ActionNode
metadata:
  name: x
  namespace: ns
spec: {}
---
"""
    with pytest.raises(ParseError, match="apiVersion ausente"):
        parse_markdown(no_api, source="no-api.md", identity=_identity())


def test_parse_markdown_raises_when_api_version_not_string() -> None:
    """apiVersion presente pero no es string emite ParseError."""
    bad_api = """---
apiVersion: 123
kind: ActionNode
metadata:
  name: x
  namespace: ns
spec: {}
---
"""
    with pytest.raises(ParseError, match="apiVersion ausente o no es string"):
        parse_markdown(bad_api, source="bad-api.md", identity=_identity())


def test_parse_markdown_raises_when_kind_missing() -> None:
    """kind ausente emite ParseError."""
    no_kind = """---
apiVersion: x/v1
metadata:
  name: x
  namespace: ns
spec: {}
---
"""
    with pytest.raises(ParseError, match="kind ausente"):
        parse_markdown(no_kind, source="no-kind.md", identity=_identity())


def test_parse_markdown_raises_when_kind_not_string() -> None:
    """kind presente pero no es string emite ParseError."""
    bad_kind = """---
apiVersion: x/v1
kind: 42
metadata:
  name: x
  namespace: ns
spec: {}
---
"""
    with pytest.raises(ParseError, match="kind ausente o no es string"):
        parse_markdown(bad_kind, source="bad-kind.md", identity=_identity())


def test_parse_markdown_raises_when_metadata_not_mapping() -> None:
    """metadata presente pero no es mapping emite ParseError."""
    bad_metadata = """---
apiVersion: x/v1
kind: ActionNode
metadata: "string-not-mapping"
spec: {}
---
"""
    with pytest.raises(ParseError, match="metadata debe ser un mapping"):
        parse_markdown(bad_metadata, source="bad-metadata.md", identity=_identity())


def test_parse_markdown_raises_when_spec_not_mapping() -> None:
    """spec presente pero no es mapping emite ParseError."""
    bad_spec = """---
apiVersion: x/v1
kind: ActionNode
metadata:
  name: x
  namespace: ns
spec: "string-not-mapping"
---
"""
    with pytest.raises(ParseError, match="spec debe ser un mapping"):
        parse_markdown(bad_spec, source="bad-spec.md", identity=_identity())


def test_parse_markdown_raises_when_namespace_not_string() -> None:
    """metadata.namespace presente pero no es string emite ParseError."""
    bad_ns = """---
apiVersion: x/v1
kind: ActionNode
metadata:
  name: x
  namespace: 42
spec: {}
---
"""
    with pytest.raises(ParseError, match="namespace debe ser string"):
        parse_markdown(bad_ns, source="bad-ns.md", identity=_identity())
