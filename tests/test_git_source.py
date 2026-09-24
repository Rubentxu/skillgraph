"""Tests H3 Slice 3: Git fingerprinting con dulwich.

Doc de cobertura:
  specs/h3-slice-3.md (8 tests propuestos).

Crea un repo Git temporal en tmp_path con dulwich para no depender de
la CLI `git`. Los tests son aislados: cada uno crea su propio repo.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from skillgraph.core.errors import DulwichNotAvailableError
from skillgraph.knowledge.git_source import (
    GitSource,
    set_dulwich_import_failed,
)
from skillgraph.knowledge.graph import Source
from skillgraph.knowledge.knowledge_controller import KnowledgeController
from skillgraph.platform.storage import Storage

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _new_repo(tmp_path: Path) -> Path:
    """Inicializa un repo Git vacio en tmp_path/repo y devuelve el root."""
    from dulwich import porcelain

    root = tmp_path / "repo"
    porcelain.init(str(root))
    return root


def _commit_files(
    root: Path,
    *,
    files: dict[str, str],
    message: bytes = b"initial",
) -> str:
    """Escribe archivos, los aniade y devuelve el SHA del commit."""
    from dulwich import porcelain

    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    rels = list(files.keys())
    porcelain.add(str(root), paths=rels)
    author = b"test <test@example.invalid>"
    return porcelain.commit(
        str(root),
        message=message,
        author=author,
        committer=author,
    ).decode()


# ---------------------------------------------------------------------------
# Tests (8)
# ---------------------------------------------------------------------------


def test_from_commit_captures_head(tmp_path: Path) -> None:
    """HEAD captura: SHAs no vacios, tree_sha presente, blob_shas poblado."""
    root = _new_repo(tmp_path)
    sha = _commit_files(
        root,
        files={"src/a.py": "a = 1\n", "README.md": "hi\n"},
    )
    gs, src = GitSource.from_commit(
        repo_root=root,
        commit_sha=sha,
        pathspecs=("*.py",),
    )
    assert isinstance(gs, GitSource)
    assert isinstance(src, Source)
    assert gs.commit_sha == sha
    assert gs.tree_sha is not None and len(gs.tree_sha) == 40
    assert any(p.endswith("a.py") for p in gs.blob_shas)
    assert src.git_commit_sha == sha
    assert src.git_tree_sha == gs.tree_sha


def test_from_commit_explicit_sha_not_head(tmp_path: Path) -> None:
    """Captura un SHA explicito y verifica que NO es HEAD cuando HEAD ya avanzo."""
    root = _new_repo(tmp_path)
    sha1 = _commit_files(root, files={"a.py": "1\n"}, message=b"first")
    # Hacer un segundo commit para que HEAD != sha1.
    _commit_files(root, files={"a.py": "2\n"}, message=b"second")
    gs, src = GitSource.from_commit(
        repo_root=root,
        commit_sha=sha1,
    )
    assert gs.commit_sha == sha1
    # El captured tree es el del primer commit, no del HEAD.
    assert gs.commit_sha != src.checked_at  # no es un test util real; mejor:
    # Verificar que el blob capturado corresponde al "1\n":
    # (hacemos refresh del contenido via repo directo).
    from dulwich.repo import Repo

    r = Repo(str(root))
    tree = r[sha1.encode()].tree
    blobs: dict[str, str] = {}

    def _visit(sha: bytes, path: bytes) -> None:
        obj = r[sha]
        if obj.type_name == b"tree":
            for entry in obj.items():
                _visit(entry.sha, path + entry.path)
        elif obj.type_name == b"blob":
            blobs[path.decode()] = sha.decode()

    for entry in r[tree].items():
        _visit(entry.sha, entry.path)
    # Primer commit solo tenia "1\n" => sha1 had content a = "1\n".
    assert blobs["a.py"] in gs.blob_shas.values()


def test_from_commit_pathspec_filters_blobs(tmp_path: Path) -> None:
    """pathspec='src/*.py' limita los blobs capturados a .py en src/."""
    root = _new_repo(tmp_path)
    sha = _commit_files(
        root,
        files={
            "src/a.py": "1\n",
            "src/b.md": "doc\n",
            "README.md": "hi\n",
        },
    )
    gs, _ = GitSource.from_commit(
        repo_root=root,
        commit_sha=sha,
        pathspecs=("src/*.py",),
    )
    paths = list(gs.blob_shas.keys())
    # Solo src/a.py; ni README.md ni src/b.md.
    assert "src/a.py" in paths
    assert "README.md" not in paths
    assert "src/b.md" not in paths


def test_to_source_roundtrip(tmp_path: Path) -> None:
    """to_source produce un Source valido que el KnowledgeController acepta."""
    root = _new_repo(tmp_path)
    sha = _commit_files(root, files={"a.py": "1\n"})
    gs, src = GitSource.from_commit(
        repo_root=root,
        commit_sha=sha,
        pathspecs=("*.py",),
    )
    # El KnowledgeController debe aceptar el Source.
    ctl = KnowledgeController(
        storage=Storage(tmp_path / "k.sqlite"),
        tenant_id="t",
        project_id="p",
    )
    ctl.register_source(source=src)
    fetched = ctl.get_source(source_id=src.source_id)
    assert fetched.git_commit_sha == sha
    # Y to_source con un ID explcito del caller tambien es aceptable.
    ctl.register_source(
        source=gs.to_source(source_id="git:customid:a.py"),
    )
    assert ctl.get_source(source_id="git:customid:a.py").git_commit_sha == sha


def test_refresh_updates_working_tree_status(tmp_path: Path) -> None:
    """Modificar el working tree sin commit: refresh detecta el cambio.

    El `commit_sha` NO cambia.
    """
    root = _new_repo(tmp_path)
    sha = _commit_files(root, files={"a.py": "1\n"})
    gs, _ = GitSource.from_commit(
        repo_root=root,
        commit_sha=sha,
        pathspecs=("*.py",),
    )
    # Modificar el archivo sin commitear.
    (root / "a.py").write_text("2\n")
    refreshed = gs.refresh()
    # commit_sha no cambia.
    assert refreshed.git_commit_sha == sha
    # Pero el working tree status refleja el cambio.
    wts = refreshed.working_tree_status
    assert wts is not None
    assert any("a.py" in s for s in wts.get("unstaged", []))


def test_detect_changes_returns_modified_files(tmp_path: Path) -> None:
    """commit A -> modificar -> commit B -> detect_changes(A, B) lista el cambio."""
    root = _new_repo(tmp_path)
    sha1 = _commit_files(
        root,
        files={"src/a.py": "v1\n", "src/b.py": "b1\n"},
        message=b"first",
    )
    # Modificar a.py y commitear.
    (root / "src/a.py").write_text("v2\n")
    from dulwich import porcelain

    porcelain.add(str(root), paths=["src/a.py"])
    author = b"test <test@example.invalid>"
    sha2 = porcelain.commit(
        str(root),
        message=b"second",
        author=author,
        committer=author,
    ).decode()
    gs, _ = GitSource.from_commit(
        repo_root=root,
        commit_sha=sha2,
        pathspecs=("*.py",),
    )
    changes = gs.detect_changes(since_commit=sha1)
    paths = [c.path for c in changes]
    assert "src/a.py" in paths
    # El cambio tiene old + new (modified).
    a_change = next(c for c in changes if c.path == "src/a.py")
    assert a_change.status == "modified"
    assert a_change.old_blob_sha is not None
    assert a_change.new_blob_sha is not None


def test_detect_changes_with_pathspec_filter(tmp_path: Path) -> None:
    """El pathspec filtra el diff a los paths que el caller definio."""
    root = _new_repo(tmp_path)
    sha1 = _commit_files(
        root,
        files={
            "src/a.py": "1\n",
            "src/b.py": "b1\n",
            "docs/readme.md": "hi\n",
        },
        message=b"first",
    )
    (root / "docs/readme.md").write_text("hi2\n")
    (root / "src/b.py").write_text("b2\n")
    from dulwich import porcelain

    porcelain.add(str(root), paths=["src/b.py", "docs/readme.md"])
    author = b"test <test@example.invalid>"
    sha2 = porcelain.commit(
        str(root),
        message=b"second",
        author=author,
        committer=author,
    ).decode()
    # Solo pathspec de docs.
    gs, _ = GitSource.from_commit(
        repo_root=root,
        commit_sha=sha2,
        pathspecs=("docs/*.md",),
    )
    changes = gs.detect_changes(since_commit=sha1)
    paths = {c.path for c in changes}
    # pathspec filtra: solo docs/readme.md.
    assert "docs/readme.md" in paths
    assert "src/b.py" not in paths


def test_from_commit_without_dulwich_raises(tmp_path: Path) -> None:
    """Si forzamos `dulwich_import_failed=True`, from_commit lanza DulwichNotAvailableError."""
    set_dulwich_import_failed(True)
    try:
        with pytest.raises(DulwichNotAvailableError):
            GitSource.from_commit(
                repo_root=tmp_path,
                commit_sha="deadbeef",
            )
    finally:
        set_dulwich_import_failed(False)
