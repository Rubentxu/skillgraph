"""WI-73: el invariante de aislamiento UAT-EVO-08 tiene nombre.

`aggregate_file_signatures` metia dentro de su bucle de 18 lineas dos
responsabilidades sin nombre: comprobar pertenencia al scope y clasificar
el fallo cuando no la tiene. Este modulo extrae esa decision a
`_sources_in_scope` y sujeta el corte por tres vias:

1. **Oraculo diferencial**: el helper se compara contra una
   reimplementacion del bucle original, para los TRES casos y para
   combinaciones de varios sources. Un oraculo que solo cubre el camino
   feliz no demuestra nada: el caso interesante es el tercero.
2. **Los dos lados de UAT-EVO-08**: rechazo explicito sin revelar el
   `source_id`, y omision silenciosa del source inexistente. Son
   deliberadamente distintos, y una mutacion que los iguala (filtrar en
   silencio el cruce de proyecto) es una fuga de contenido: por eso hay
   un test dedicado a ella.
3. **Estructura**: el invariante tiene un nombre en el codigo, y el
   bucle ya no esta dentro del metodo publico.

Los helpers y fixtures se replican de `test_h12_file_signature_scopes.py`
a proposito (mismo criterio que los demas pares de red de este repo):
si el otro modulo los cambiara, esta red no debe romperse.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from skillgraph.core.errors import UnknownSourceError
from skillgraph.knowledge.file_scope import ScopeQuery
from skillgraph.knowledge.file_signature import (
    ExtractionState,
    FileSignature,
    SignatureProcedencia,
    SignatureVigencia,
)
from skillgraph.knowledge.graph import Source
from skillgraph.knowledge.knowledge_controller import KnowledgeController
from skillgraph.platform.storage import Storage

# ----- helpers (replicados de test_h12_file_signature_scopes.py) ----------


def _proc() -> SignatureProcedencia:
    return SignatureProcedencia(
        extraction_method="regex_def",
        extractor_version="skillgraph-rules/0.1.0",
    )


def _vig(state: ExtractionState = "complete") -> SignatureVigencia:
    return SignatureVigencia(state=state, fresh=(state == "complete"), stale=(state != "complete"))


def _sig(*, foco: str) -> FileSignature:
    return FileSignature(
        foco=foco,
        contrato="def",
        cobertura=1,
        procedencia=_proc(),
        vigencia=_vig(),
    )


def _register_source(controller: KnowledgeController, source_id: str) -> None:
    controller.register_source(
        source=Source(
            source_id=source_id,
            kind="local_file",
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
    return Storage(str(tmp_path / "wi73.sqlite"))


@pytest.fixture
def controller_p1(storage: Storage) -> KnowledgeController:
    return KnowledgeController(knowledge=storage, tenant_id="t1", project_id="p1")


@pytest.fixture
def controller_p2(storage: Storage) -> KnowledgeController:
    """Mismo storage, proyecto distinto. Aislado por tenant/project."""
    return KnowledgeController(knowledge=storage, tenant_id="t1", project_id="p2")


def _original_loop(
    controller: KnowledgeController, member_source_ids: tuple[str, ...]
) -> tuple[str, ...] | str:
    """ORACULO: el bucle original, linea por linea, sin mover.

    Se mantiene deliberadamente imperativo y sin nombre, que es justo la
    forma que el corte pretendia eliminar de produccion. Devuelve la
    tupla filtrada, o el string del mensaje de rechazo si el caso 2
    dispara: comparar tambien el rechazo es lo que hace el oraculo
    util.
    """
    sources_in_scope: list[str] = []
    for source_id in member_source_ids:
        try:
            controller.get_source(source_id=source_id)
            sources_in_scope.append(source_id)
        except UnknownSourceError:
            cross = controller.knowledge.source_exists_anywhere(source_id=source_id)
            if cross:
                return (
                    "Uno o mas sources pertenecen a otro proyecto; "
                    "rechazado sin filtrar contenido (UAT-EVO-08)"
                )
            # No existe en ningun proyecto: omitir silenciosamente.
    return tuple(sources_in_scope)


# ---------------------------------------------------------------------------
# 1. Oraculo diferencial: el helper decide igual que el bucle original
# ---------------------------------------------------------------------------


def _seed_two_projects(p1: KnowledgeController, p2: KnowledgeController | None = None) -> None:
    """p1 registra 3 sources; p2, si se pasa, registra 1 propio."""
    for source_id in ("src/a.py", "src/b.py", "src/c.py"):
        _register_source(p1, source_id)
    if p2 is not None:
        _register_source(p2, "src/own.py")


@pytest.mark.parametrize(
    "members",
    [
        (),
        ("src/a.py",),
        ("src/a.py", "src/b.py"),
        ("src/nonexistent.py",),
        ("src/nonexistent.py", "src/a.py"),
        ("src/a.py", "src/nonexistent.py", "src/c.py"),
        ("src/nope1.py", "src/nope2.py"),
    ],
)
def test_helper_agrees_with_the_original_loop(
    controller_p1: KnowledgeController,
    controller_p2: KnowledgeController,
    members: tuple[str, ...],
) -> None:
    """Casos 1 y 3: el helper devuelve exactamente la misma tupla."""
    _seed_two_projects(controller_p1, controller_p2)

    assert controller_p1._sources_in_scope(member_source_ids=members) == _original_loop(
        controller_p1, members
    )


def test_helper_agrees_with_the_original_loop_on_rejection(
    controller_p1: KnowledgeController, controller_p2: KnowledgeController
) -> None:
    """Caso 2: los dos rechazan, y con el MISMO mensaje."""
    _seed_two_projects(controller_p1, controller_p2)
    # p2 pide un source de p1: existe en otro proyecto.
    members = ("src/a.py",)

    with pytest.raises(UnknownSourceError) as from_helper:
        controller_p2._sources_in_scope(member_source_ids=members)
    expected = _original_loop(controller_p2, members)
    assert isinstance(expected, str), "el oraculo deberia haber rechazado"

    assert str(from_helper.value) == expected


# ---------------------------------------------------------------------------
# 2. Los dos lados de UAT-EVO-08, que son deliberadamente distintos
# ---------------------------------------------------------------------------


def test_cross_project_source_is_rejected_without_leaking_its_id(
    controller_p1: KnowledgeController, controller_p2: KnowledgeController
) -> None:
    """El rechazo NO puede revelar el source_id: seria filtrar contenido."""
    _seed_two_projects(controller_p1, controller_p2)
    # Registrado en p1, pedido desde p2: existe en OTRO proyecto (caso 2).
    _register_source(controller_p1, "src/secret.py")

    with pytest.raises(UnknownSourceError) as exc:
        controller_p2._sources_in_scope(member_source_ids=("src/secret.py",))

    msg = str(exc.value)
    assert "pertenecen a otro proyecto" in msg
    assert "src/secret.py" not in msg, "el mensaje esta filtrando el source_id"


def test_unknown_source_is_silently_skipped(
    controller_p2: KnowledgeController,
) -> None:
    """Un typo del caller se omite: no es un rechazo, es un dato que no existe.

    Este es el lado que NO debe confundirse con el anterior. Si los dos
    casos colapsaran en "filtrar en silencio", el cruce de proyecto
    pasaria sin avisar y seria una fuga.
    """
    assert controller_p2._sources_in_scope(member_source_ids=("src/typo.py",)) == ()


def test_valid_sources_are_returned_in_order(
    controller_p1: KnowledgeController,
) -> None:
    """El orden de entrada se preserva: el dict de firmas depende de el."""
    _seed_two_projects(controller_p1)

    assert controller_p1._sources_in_scope(
        member_source_ids=("src/c.py", "src/a.py", "src/b.py")
    ) == ("src/c.py", "src/a.py", "src/b.py")


# ---------------------------------------------------------------------------
# 3. Estructura: el invariante tiene nombre y el bucle no sigue dentro
# ---------------------------------------------------------------------------


def test_helper_exists_with_a_name_that_states_the_invariant() -> None:
    """REQ-1: el invariante UAT-EVO-08 se llama, no solo se documenta."""
    assert hasattr(KnowledgeController, "_sources_in_scope")
    assert inspect.isfunction(KnowledgeController._sources_in_scope)
    doc = inspect.getdoc(KnowledgeController._sources_in_scope) or ""
    assert "UAT-EVO-08" in doc, "el docstring debe nombrar el invariante que protege"
    assert "otro" in doc.lower(), "el docstring debe explicar el caso de rechazo"


def _method_node(name: str) -> ast.FunctionDef:
    """Localiza el metodo por AST; cleandoc dedentaria mal el cuerpo."""
    path = Path(inspect.getsourcefile(KnowledgeController) or "")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} no encontrado en {path}")


def test_public_method_no_longer_inlines_the_isolation_loop() -> None:
    """REQ-1: el `try/except UnknownSourceError` sale del metodo publico."""
    node = _method_node("aggregate_file_signatures")

    handlers = [
        n
        for n in ast.walk(node)
        if isinstance(n, ast.ExceptHandler)
        and n.type is not None
        and "UnknownSourceError" in ast.unparse(n.type)
    ]
    assert not handlers, (
        "aggregate_file_signatures vuelve a manejar UnknownSourceError en linea; "
        "esa decision pertenece a _sources_in_scope"
    )


def test_public_method_delegates_to_the_helper() -> None:
    """La delegacion existe: el helper se usa, no es codigo muerto."""
    source = inspect.getsource(KnowledgeController.aggregate_file_signatures)
    assert "_sources_in_scope" in source

    calls = [
        n
        for n in ast.walk(_method_node("aggregate_file_signatures"))
        if isinstance(n, ast.Call) and getattr(n.func, "attr", None) == "_sources_in_scope"
    ]
    assert len(calls) == 1, f"se esperaba 1 llamada a _sources_in_scope, hay {len(calls)}"


# ---------------------------------------------------------------------------
# 4. Contrato intacto en el metodo publico
# ---------------------------------------------------------------------------


def test_isolation_is_checked_before_any_signature_is_read(
    storage: Storage,
) -> None:
    """REQ-3: si hay un cruce, no se lee ninguna firma de p1.

    El orden no es cosmetico: leer antes de comprobar ya habria tocado el
    contenido del otro proyecto, que es justo lo que UAT-EVO-08
    prohibe.

    `KnowledgeController` es un dataclass frozen, asi que no admite
    monkeypatch de atributo (`FrozenInstanceError`): el espia es una
    subclase que sobrescribe el metodo, que ademas prueba que el punto de
    observacion es el metodo y no un detalle del storage.
    """
    p1 = KnowledgeController(knowledge=storage, tenant_id="t1", project_id="p1")

    class _SpyController(KnowledgeController):
        """Registra cada lectura de firmas sin cambiar el resultado."""

        def __init__(self, **kwargs: object) -> None:
            super().__init__(**kwargs)  # type: ignore[arg-type]
            self.reads: list[str] = []

        def list_file_signatures_for_source(
            self, *, source_id: str, only_stale: bool = False
        ) -> tuple[FileSignature, ...]:
            self.reads.append(source_id)
            return super().list_file_signatures_for_source(
                source_id=source_id, only_stale=only_stale
            )

    _seed_two_projects(p1, None)
    for source_id in ("src/a.py", "src/b.py"):
        p1.record_evidence_for_file_signature(
            source_id=source_id, file_signature=_sig(foco=f"{source_id}::def::x")
        )

    p2 = _SpyController(knowledge=storage, tenant_id="t1", project_id="p2")

    with pytest.raises(UnknownSourceError):
        p2.aggregate_file_signatures(
            scope_query=ScopeQuery(scope_kind="directory", target="src/"),
            member_source_ids=("src/a.py",),
        )

    assert p2.reads == [], f"se leyeron firmas antes de comprobar el aislamiento: {p2.reads}"


def test_type_guard_still_raises_type_error(
    controller_p1: KnowledgeController,
) -> None:
    """REQ-6: el guard de tipo NO se toca.

    `TypeError` para validar tipos y `ValidationError` para validar
    valores es la convencion de la casa; `file_handoff._validate_inputs`
    tiene cuatro iguales. Cambiar solo este crearia inconsistencia.
    """
    with pytest.raises(TypeError, match="scope_query debe ser ScopeQuery"):
        controller_p1.aggregate_file_signatures(
            scope_query="src/",  # type: ignore[arg-type]
            member_source_ids=("src/a.py",),
        )


def test_empty_members_still_short_circuits(
    controller_p1: KnowledgeController,
) -> None:
    """El camino de `member_source_ids` vacio sigue igual."""
    agg = controller_p1.aggregate_file_signatures(
        scope_query=ScopeQuery(scope_kind="directory", target="src/"),
        member_source_ids=(),
    )

    assert agg.signatures_count == 0
    assert agg.cobertura_global == 0
    assert agg.signatures == ()


def test_aggregate_still_returns_signatures_for_valid_members(
    controller_p1: KnowledgeController,
) -> None:
    """El camino feliz sigue agregando firmas."""
    _seed_two_projects(controller_p1)
    for source_id in ("src/a.py", "src/b.py"):
        controller_p1.record_evidence_for_file_signature(
            source_id=source_id, file_signature=_sig(foco=f"{source_id}::def::x")
        )

    agg = controller_p1.aggregate_file_signatures(
        scope_query=ScopeQuery(scope_kind="directory", target="src/"),
        member_source_ids=("src/a.py", "src/b.py"),
    )

    assert {s.foco for s in agg.signatures} == {"src/a.py::def::x", "src/b.py::def::x"}
