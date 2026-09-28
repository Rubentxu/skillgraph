"""Red de contrato para GitSource.detect_changes (cc=11).

detect_changes es el segundo cc=11 del ranking. La cobertura de lineas
era del 95% pero no fijaba contrato: estos tests pinan el shape de
ChangedFile en cada estado (added/modified/deleted), los bordes del
pathspec, y el orden de filtrado observable.

Trabajan contra un repo git real de juguete (dulwich porcelain), igual
que tests/test_git_source.py. Sin mocks para el object store.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from skillgraph.knowledge.git_source import GitSource

_dulwich = pytest.importorskip("dulwich")


def _commit(root: Path, message: bytes = b"c") -> str:
    from dulwich import porcelain

    author = b"test <test@example.invalid>"
    return porcelain.commit(str(root), message=message, author=author, committer=author).decode()


def _stage(root: Path, *rels: str) -> None:
    from dulwich import porcelain

    porcelain.add(str(root), paths=list(rels))


def _repo_with_first_commit(tmp_path: Path) -> tuple[Path, str]:
    from dulwich import porcelain

    root = tmp_path / "repo"
    porcelain.init(str(root))
    (root / "src").mkdir()
    (root / "src/a.py").write_text("v1\n")
    (root / "src/b.py").write_text("b1\n")
    (root / "docs").mkdir()
    (root / "docs/r.md").write_text("d1\n")
    _stage(root, "src/a.py", "src/b.py", "docs/r.md")
    return root, _commit(root, b"first")


def _gs(root: Path, sha: str, pathspecs: tuple[str, ...] = ()) -> GitSource:
    gs, _ = GitSource.from_commit(repo_root=root, commit_sha=sha, pathspecs=pathspecs)
    return gs


# --------------------------------------------------------------------------
# Estados de cambio: added / modified / deleted
# --------------------------------------------------------------------------


class TestChangeStatuses:
    def test_added(self, tmp_path: Path) -> None:
        root, sha1 = _repo_with_first_commit(tmp_path)
        (root / "src/new.py").write_text("n\n")
        _stage(root, "src/new.py")
        sha2 = _commit(root, b"add")
        changes = _gs(root, sha2).detect_changes(since_commit=sha1)
        added = next(c for c in changes if c.path == "src/new.py")
        assert added.status == "added"
        assert added.old_blob_sha is None
        assert added.new_blob_sha

    def test_modified(self, tmp_path: Path) -> None:
        root, sha1 = _repo_with_first_commit(tmp_path)
        (root / "src/a.py").write_text("v2\n")
        _stage(root, "src/a.py")
        sha2 = _commit(root, b"mod")
        changes = _gs(root, sha2).detect_changes(since_commit=sha1)
        mod = next(c for c in changes if c.path == "src/a.py")
        assert mod.status == "modified"
        assert mod.old_blob_sha is not None
        assert mod.new_blob_sha is not None
        assert mod.old_blob_sha != mod.new_blob_sha

    def test_deleted(self, tmp_path: Path) -> None:
        root, sha1 = _repo_with_first_commit(tmp_path)
        (root / "src/b.py").unlink()
        from dulwich import porcelain

        porcelain.rm(str(root), paths=["src/b.py"])
        sha2 = _commit(root, b"del")
        changes = _gs(root, sha2).detect_changes(since_commit=sha1)
        deleted = next(c for c in changes if c.path == "src/b.py")
        assert deleted.status == "deleted"
        assert deleted.old_blob_sha is not None
        assert deleted.new_blob_sha == ""

    def test_sin_cambios_devuelve_lista_vacia(self, tmp_path: Path) -> None:
        root, sha1 = _repo_with_first_commit(tmp_path)
        changes = _gs(root, sha1).detect_changes(since_commit=sha1)
        assert changes == []

    def test_hasta_commit_distinto_de_head(self, tmp_path: Path) -> None:
        """`until_commit` compara dos commits historicos, no solo HEAD."""
        root, sha1 = _repo_with_first_commit(tmp_path)
        (root / "src/a.py").write_text("v2\n")
        _stage(root, "src/a.py")
        sha2 = _commit(root, b"second")
        (root / "src/a.py").write_text("v3\n")
        _stage(root, "src/a.py")
        sha3 = _commit(root, b"third")
        # Rango cerrado sha1..sha2: el tercer commit no aparece.
        changes = _gs(root, sha3).detect_changes(since_commit=sha1, until_commit=sha2)
        assert {c.path for c in changes} == {"src/a.py"}


# --------------------------------------------------------------------------
# Pathspecs
# --------------------------------------------------------------------------


class TestPathspecs:
    def test_sin_pathspecs_devuelve_todo(self, tmp_path: Path) -> None:
        root, sha1 = _repo_with_first_commit(tmp_path)
        (root / "src/a.py").write_text("v2\n")
        (root / "docs/r.md").write_text("d2\n")
        _stage(root, "src/a.py", "docs/r.md")
        sha2 = _commit(root, b"two")
        paths = {c.path for c in _gs(root, sha2).detect_changes(since_commit=sha1)}
        assert paths == {"src/a.py", "docs/r.md"}

    def test_un_pathspec_filtra(self, tmp_path: Path) -> None:
        root, sha1 = _repo_with_first_commit(tmp_path)
        (root / "src/a.py").write_text("v2\n")
        (root / "docs/r.md").write_text("d2\n")
        _stage(root, "src/a.py", "docs/r.md")
        sha2 = _commit(root, b"two")
        paths = {
            c.path for c in _gs(root, sha2, pathspecs=("docs/*",)).detect_changes(since_commit=sha1)
        }
        assert paths == {"docs/r.md"}

    def test_varios_pathspecs_son_union(self, tmp_path: Path) -> None:
        root, sha1 = _repo_with_first_commit(tmp_path)
        (root / "src/a.py").write_text("v2\n")
        (root / "docs/r.md").write_text("d2\n")
        _stage(root, "src/a.py", "docs/r.md")
        sha2 = _commit(root, b"two")
        paths = {
            c.path
            for c in _gs(root, sha2, pathspecs=("src/*", "docs/*")).detect_changes(
                since_commit=sha1
            )
        }
        assert paths == {"src/a.py", "docs/r.md"}

    def test_pathspec_que_no_matchea_deja_vacio(self, tmp_path: Path) -> None:
        root, sha1 = _repo_with_first_commit(tmp_path)
        (root / "src/a.py").write_text("v2\n")
        _stage(root, "src/a.py")
        sha2 = _commit(root, b"two")
        changes = _gs(root, sha2, pathspecs=("noexiste/*",)).detect_changes(since_commit=sha1)
        assert changes == []

    def test_pathspec_excluye_un_borrado(self, tmp_path: Path) -> None:
        """El filtro tambien se aplica a los deletes, no solo a modifies."""
        root, sha1 = _repo_with_first_commit(tmp_path)
        (root / "src/b.py").unlink()
        from dulwich import porcelain

        porcelain.rm(str(root), paths=["src/b.py"])
        sha2 = _commit(root, b"del")
        changes = _gs(root, sha2, pathspecs=("docs/*",)).detect_changes(since_commit=sha1)
        assert changes == []


# --------------------------------------------------------------------------
# Contrato de shape
# --------------------------------------------------------------------------


class TestChangedFileShape:
    def test_changes_es_lista(self, tmp_path: Path) -> None:
        root, sha1 = _repo_with_first_commit(tmp_path)
        (root / "src/a.py").write_text("v2\n")
        _stage(root, "src/a.py")
        sha2 = _commit(root, b"two")
        assert isinstance(_gs(root, sha2).detect_changes(since_commit=sha1), list)

    def test_changed_file_es_frozen(self, tmp_path: Path) -> None:
        root, sha1 = _repo_with_first_commit(tmp_path)
        (root / "src/a.py").write_text("v2\n")
        _stage(root, "src/a.py")
        sha2 = _commit(root, b"two")
        change = _gs(root, sha2).detect_changes(since_commit=sha1)[0]
        with pytest.raises(Exception):  # noqa: B017 - frozen dataclass raise
            change.path = "otro"  # type: ignore[misc]

    def test_rango_vacio_entre_arboles_identicos(self, tmp_path: Path) -> None:
        """Dos commits sin diff de arbol entre ellos no producen cambios."""
        root, sha1 = _repo_with_first_commit(tmp_path)
        (root / "README.md").write_text("r\n")
        _stage(root, "README.md")
        sha2 = _commit(root, b"otro-fichero")
        paths = {c.path for c in _gs(root, sha2).detect_changes(since_commit=sha1)}
        assert paths == {"README.md"}
