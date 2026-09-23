"""H9-Coverage-4: cobertura de las ramas no ejercitadas de
`skillgraph.knowledge.git_source` (86% -> >=95%).

Las ramas cubiertas aqui son:
- from_commit: commit_obj.type_name != b"commit" -> ValueError
- refresh(): self.pathspecs truthy filtra blobs
- detect_changes: until_commit=None (usa HEAD), pathspecs filtra,
  status added (sha None old), status deleted (sha None new)
- _matches_pathspec: literal (no glob) matchea por prefijo-segmento
- _safe_capture_status: exito (repo limpio devuelve dict)

Sin modificacion de produccion. Spec: specs/h9-coverage-git-source.md.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from skillgraph.knowledge.git_source import (
    GitSource,
    _matches_pathspec,
    _safe_capture_status,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _new_repo(tmp_path: Path) -> Path:
    from dulwich import porcelain

    root = tmp_path / "repo"
    porcelain.init(str(root))
    return root


def _commit_files(
    root: Path,
    *,
    files: dict[str, str],
    message: bytes = b"commit",
) -> str:
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


def _remove_files(root: Path, rels: list[str]) -> None:
    """Quita archivos del working tree y los stagea con `porcelain.remove`."""
    from dulwich import porcelain

    for rel in rels:
        (root / rel).unlink()
    porcelain.remove(str(root), paths=rels)


# ---------------------------------------------------------------------------
# from_commit: SHA que NO apunta a commit
# ---------------------------------------------------------------------------


def test_from_commit_with_non_commit_sha_raises(tmp_path: Path) -> None:
    """`from_commit` con un SHA que NO es un commit lanza ValueError."""
    from dulwich.objects import Blob
    from dulwich.repo import Repo

    root = _new_repo(tmp_path)
    repo = Repo(str(root))

    # Crear un Blob explicito en el object store del repo. El SHA del
    # blob NO apunta a un commit, asi que `from_commit` debe rechazarlo.
    blob = Blob.from_string(b"orphan blob for non-commit test")
    repo.object_store.add_object(blob)
    non_commit_sha = blob.id.decode()

    # El blob existe en el object store pero NO es un commit.
    with pytest.raises(ValueError, match=r"sha no apunta a un commit"):
        GitSource.from_commit(
            repo_root=root,
            commit_sha=non_commit_sha,
        )


# ---------------------------------------------------------------------------
# refresh(): self.pathspecs truthy filtra blobs
# ---------------------------------------------------------------------------


def test_refresh_with_pathspecs_filters_blobs(tmp_path: Path) -> None:
    """`refresh()` con pathspecs filtra los blobs por el prefijo."""
    root = _new_repo(tmp_path)
    _commit_files(
        root,
        files={
            "src/a.py": "a\n",
            "src/b.py": "b\n",
            "README.md": "readme\n",
        },
    )
    gs, _ = GitSource.from_commit(
        repo_root=root,
        commit_sha=_commit_files(root, files={}, message=b"empty"),
        pathspecs=("src/",),
    )

    # refresh devuelve un Source con locator.pathspecs y content_hash
    # basado SOLO en blobs bajo src/.
    src = gs.refresh()
    locator = src.locator
    assert "src/" in locator["pathspecs"]

    # Comparar con un refresh sin pathspecs (todos los blobs).
    gs_all, _ = GitSource.from_commit(repo_root=root, commit_sha=gs.commit_sha)
    src_all = gs_all.refresh()
    assert src.content_hash != src_all.content_hash


# ---------------------------------------------------------------------------
# detect_changes: until_commit=None (usa HEAD)
# ---------------------------------------------------------------------------


def test_detect_changes_uses_head_when_until_commit_none(tmp_path: Path) -> None:
    """`detect_changes(since_commit=...)` con `until_commit=None` usa HEAD."""
    root = _new_repo(tmp_path)
    sha1 = _commit_files(root, files={"a.txt": "1\n"}, message=b"first")
    _commit_files(root, files={"b.txt": "2\n"}, message=b"second")

    gs = GitSource.from_commit(repo_root=root, commit_sha=sha1)[0]

    changes = gs.detect_changes(since_commit=sha1)
    # b.txt es nuevo en sha2 -> debe aparecer
    paths = [c.path for c in changes]
    assert "b.txt" in paths


# ---------------------------------------------------------------------------
# detect_changes: pathspecs filtra cambios
# ---------------------------------------------------------------------------


def test_detect_changes_with_pathspecs_filters(tmp_path: Path) -> None:
    """`detect_changes` filtra cambios por pathspecs del GitSource."""
    root = _new_repo(tmp_path)
    sha1 = _commit_files(
        root,
        files={"src/a.py": "1\n", "README.md": "r1\n"},
        message=b"first",
    )
    _commit_files(
        root,
        files={"src/b.py": "2\n", "README.md": "r2\n"},
        message=b"second",
    )

    gs = GitSource.from_commit(
        repo_root=root,
        commit_sha=sha1,
        pathspecs=("src/",),
    )[0]

    changes = gs.detect_changes(since_commit=sha1)
    paths = [c.path for c in changes]
    # src/b.py es added, README.md esta fuera del pathspec
    assert "src/b.py" in paths
    assert "README.md" not in paths


# ---------------------------------------------------------------------------
# detect_changes: status added (file nuevo)
# ---------------------------------------------------------------------------


def test_detect_changes_includes_added_files(tmp_path: Path) -> None:
    """Archivos nuevos en el segundo commit tienen status='added'."""
    root = _new_repo(tmp_path)
    sha1 = _commit_files(root, files={"base.txt": "x\n"}, message=b"first")
    sha2 = _commit_files(root, files={"new.txt": "n\n"}, message=b"second")

    gs = GitSource.from_commit(repo_root=root, commit_sha=sha1)[0]
    changes = gs.detect_changes(since_commit=sha1, until_commit=sha2)

    added = {c.path: c.status for c in changes if c.status == "added"}
    assert "new.txt" in added


# ---------------------------------------------------------------------------
# detect_changes: status deleted (file eliminado)
# ---------------------------------------------------------------------------


def test_detect_changes_includes_deleted_files(tmp_path: Path) -> None:
    """Archivos eliminados en el segundo commit tienen status='deleted'."""
    root = _new_repo(tmp_path)
    sha1 = _commit_files(
        root,
        files={"keep.txt": "k\n", "doomed.txt": "d\n"},
        message=b"first",
    )
    # Eliminar `doomed.txt` y commitear.
    _remove_files(root, ["doomed.txt"])
    from dulwich import porcelain

    author = b"test <test@example.invalid>"
    sha2 = porcelain.commit(
        str(root),
        message=b"remove doomed",
        author=author,
        committer=author,
    ).decode()

    gs = GitSource.from_commit(repo_root=root, commit_sha=sha1)[0]
    changes = gs.detect_changes(since_commit=sha1, until_commit=sha2)

    deleted = {c.path: c.status for c in changes if c.status == "deleted"}
    assert "doomed.txt" in deleted


# ---------------------------------------------------------------------------
# _matches_pathspec: literal (no glob) como prefijo-segmento
# ---------------------------------------------------------------------------


def test_matches_pathspec_literal_prefix_segment() -> None:
    """Pathspec literal matchea como prefijo-segmento (no substring).

    'src' matchea 'src/a.py' pero NO 'src_old/x.py'.
    """
    # Prefijo segmento: True
    assert _matches_pathspec("src/a.py", "src") is True
    assert _matches_pathspec("src/sub/b.py", "src") is True
    assert _matches_pathspec("a.py", "a.py") is True
    assert _matches_pathspec("a.py", "a.py/") is True  # rstrip("/") normaliza

    # Substring NO matchea
    assert _matches_pathspec("src_old/x.py", "src") is False
    assert _matches_pathspec("srcbackup/x.py", "src") is False


# ---------------------------------------------------------------------------
# _safe_capture_status: exito en repo limpio
# ---------------------------------------------------------------------------


def test_safe_capture_status_returns_dict_on_clean_repo(tmp_path: Path) -> None:
    """_safe_capture_status en repo limpio devuelve dict (puede estar vacio)."""
    import dulwich.porcelain as _p
    import dulwich.repo as _r

    root = _new_repo(tmp_path)
    _r.Repo(str(root))
    status = _safe_capture_status(str(root), _p)
    # Repo limpio: status es un dict (posiblemente vacio, sin raise).
    assert isinstance(status, dict)
