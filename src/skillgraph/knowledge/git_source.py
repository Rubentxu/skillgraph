"""GitSource: fabrica de `Source` a partir de un commit Git local.

Doc externo:
  specs/h3-slice-3.md (sub-spec firmado en el H3).
  external/blueprint-v1/docs/08-conocimiento-y-contexto.md.
  external/blueprint-v1/adr/ADR-0010-controlador-gitsource.md (a redactar).

Esta clase NO se persiste: es una fabrica + helper para detectar
cambios. La `Source` resultante se registra en el `KnowledgeController`
(Slice 2) y `GitSource` guarda localmente los SHAs necesarios para
refresh y diff.

Dependencia opcional `dulwich` (se importa aqui; los callers NO
necesitan hacer nada). Si falta, se lanza `DulwichNotAvailableError`
desde `from_commit`.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from skillgraph.core.errors import DulwichNotAvailableError, ValidationError
from skillgraph.knowledge.graph import Source, SourceID
from skillgraph.runtime.engine import now_iso as _now_iso

# Tipo solo en tiempo de check: el modulo real no se importa en runtime.
if TYPE_CHECKING:
    pass  # dulwich solo se importa cuando se necesita.


# ---------------------------------------------------------------------------
# Tipos auxiliares
# ---------------------------------------------------------------------------

ChangeStatus = Literal["modified", "added", "deleted"]


@dataclass(frozen=True, slots=True)
class ChangedFile:
    """Cambio entre dos commits para un pathspec concreto.

    Slice 4 usara esto para propagar invalidacion.
    """

    path: str
    old_blob_sha: str | None
    new_blob_sha: str
    status: ChangeStatus


ChangeStatusLiteral = Literal["modified", "added", "deleted"]


# ---------------------------------------------------------------------------
# Import lazy de dulwich
# ---------------------------------------------------------------------------


def _import_dulwich() -> tuple[object, object, object]:
    """Importa `dulwich.repo.Repo`, `dulwich.porcelain`, `dulwich.diff_tree.tree_changes`.

    Lanza `DulwichNotAvailableError` si no esta instalado.

    Para testing, exponer `dulwich_import_failed` (override) — esto se
    usa en los tests para simular ausencia de dulwich sin modificar
    el env.
    """
    # Hook para tests: si esta puesto a True, simulamos que no esta.
    if _dulwich_import_failed_for_test():
        raise DulwichNotAvailableError("dulwich no disponible (forzado por test)")
    try:
        from dulwich import porcelain
        from dulwich.diff_tree import tree_changes
        from dulwich.repo import Repo
    except ImportError as exc:
        raise DulwichNotAvailableError(
            "dulwich no esta instalado; instala con `uv pip install "
            "skillgraph[git]` o `pip install dulwich`"
        ) from exc
    return Repo, porcelain, tree_changes


# Variable de control para tests (no es API publica).
_TEST_DULWICH_MISSING: bool = False


def _dulwich_import_failed_for_test() -> bool:
    return _TEST_DULWICH_MISSING


def set_dulwich_import_failed(value: bool) -> None:
    """Solo para tests: fuerza el path 'dulwich no disponible'.

    Llamar con True antes del test y False en cleanup (fixture).
    """
    global _TEST_DULWICH_MISSING
    _TEST_DULWICH_MISSING = value


# ---------------------------------------------------------------------------
# GitSource
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GitSource:
    """Fabrica de Source + helper de invalidacion a partir de un commit Git."""

    repo_root: Path
    commit_sha: str
    pathspecs: tuple[str, ...] = ()
    tree_sha: str | None = None
    blob_shas: dict[str, str] = field(default_factory=lambda: {})

    @classmethod
    def from_commit(
        cls,
        *,
        repo_root: Path,
        commit_sha: str,
        pathspecs: tuple[str, ...] = (),
        source_id: SourceID | None = None,
    ) -> tuple[GitSource, Source]:
        """Captura commit + tree + blobs en el SHA dado.

        Devuelve (GitSource, Source) para que el caller registre la
        Source via KnowledgeController y conserve el GitSource para
        refrescos.

        Si `source_id` es None, genera uno con prefijo `git:<first8>:`.
        """
        Repo, porcelain, _ = _import_dulwich()

        repo = Repo(str(repo_root))
        commit_obj = repo[commit_sha.encode()]
        if commit_obj.type_name != b"commit":
            raise ValidationError(f"sha no apunta a un commit: {commit_sha!r}")

        tree_sha = commit_obj.tree.decode()
        blob_shas = _collect_blob_shas(repo, commit_obj.tree)

        # Working tree status. `None` = no se pudo determinar (repo
        # roto o no-repo); NO se confunde con un working tree limpio.
        working_tree_status = _safe_capture_status(str(repo_root), porcelain)

        # Filtrar blob_shas por pathspecs si vienen.
        if pathspecs:
            filtered: dict[str, str] = {}
            for path, sha in blob_shas.items():
                if any(_matches_pathspec(path, ps) for ps in pathspecs):
                    filtered[path] = sha
            blob_shas = filtered

        # Generar content_hash determinista.
        content_hash = _compute_content_hash(blob_shas)

        if source_id is None:
            source_id = f"git:{commit_sha[:8]}:{'+'.join(pathspecs) or 'all'}"

        locator = {
            "vcs": "git",
            "repo_root": str(repo_root),
            "commit_sha": commit_sha,
            "pathspecs": list(pathspecs),
        }

        gs = cls(
            repo_root=repo_root,
            commit_sha=commit_sha,
            pathspecs=pathspecs,
            tree_sha=tree_sha,
            blob_shas=blob_shas,
        )
        src = Source(
            source_id=source_id,
            kind="git_commit",
            content_hash=content_hash,
            locator=locator,
            git_commit_sha=commit_sha,
            git_tree_sha=tree_sha,
            working_tree_status=working_tree_status,
            checked_at=_now_iso(),
            freshness="fresh",
        )
        return gs, src

    def refresh(self) -> Source:
        """Re-captura el Source en el mismo commit_sha (sin avanzar).

        `commit_sha` no cambia; `working_tree_status` y la captura del
        working tree se actualizan.
        """
        Repo, porcelain, _ = _import_dulwich()
        repo = Repo(str(self.repo_root))
        commit_obj = repo[self.commit_sha.encode()]
        # Repite blob capture pero con los pathspecs guardados.
        blob_shas = _collect_blob_shas(repo, commit_obj.tree)
        if self.pathspecs:
            blob_shas = {
                p: s
                for p, s in blob_shas.items()
                if any(_matches_pathspec(p, ps) for ps in self.pathspecs)
            }
        working_tree_status = _safe_capture_status(str(self.repo_root), porcelain)
        return Source(
            source_id=f"git:{self.commit_sha[:8]}:{'+'.join(self.pathspecs) or 'all'}",
            kind="git_commit",
            content_hash=_compute_content_hash(blob_shas),
            locator={
                "vcs": "git",
                "repo_root": str(self.repo_root),
                "commit_sha": self.commit_sha,
                "pathspecs": list(self.pathspecs),
            },
            git_commit_sha=self.commit_sha,
            git_tree_sha=self.tree_sha,
            working_tree_status=working_tree_status,
            checked_at=_now_iso(),
            freshness="fresh",
        )

    def detect_changes(
        self,
        *,
        since_commit: str,
        until_commit: str | None = None,
    ) -> list[ChangedFile]:
        """Diff entre dos commits, filtrado por pathspecs guardados.

        `until_commit` por defecto = HEAD del repo. El filtro por
        pathspecs se aplica DESPUES del diff completo; `old`/`new` del
        tree change dictan el estado (added/modified/deleted).
        """
        c1, c2 = self._resolve_commit_pair(since_commit, until_commit)
        Repo, _, tree_changes = _import_dulwich()
        repo = Repo(str(self.repo_root))
        changes = [
            cf
            for ch in tree_changes(repo.object_store, c1.tree, c2.tree)
            if (cf := _changed_file_from(ch)) is not None
        ]
        if self.pathspecs:
            changes = [
                c for c in changes if any(_matches_pathspec(c.path, ps) for ps in self.pathspecs)
            ]
        return changes

    def _resolve_commit_pair(
        self, since_commit: str, until_commit: str | None
    ) -> tuple[object, object]:
        """Carga los dos commits a comparar.

        Si `until_commit` es None, usa HEAD del repo.
        Mantenemos `Repo(...)` lazy solo aqui para no penalizar el
        arranque de tests que importan `git_source` sin usar dulwich.
        """
        Repo, _, _ = _import_dulwich()
        repo = Repo(str(self.repo_root))
        if until_commit is None:
            until_commit = repo.head().decode()
        c1 = repo[since_commit.encode()]
        c2 = repo[until_commit.encode()]
        return c1, c2

    def to_source(self, *, source_id: SourceID) -> Source:
        """Convierte este GitSource en un Source con un source_id explicito.

        NO recalcula nada: usa los blobs ya capturados en este GitSource.
        Util cuando el caller quiere regenerar el Source con un ID
        determinista de su eleccion.
        """
        return Source(
            source_id=source_id,
            kind="git_commit",
            content_hash=_compute_content_hash(self.blob_shas),
            locator={
                "vcs": "git",
                "repo_root": str(self.repo_root),
                "commit_sha": self.commit_sha,
                "pathspecs": list(self.pathspecs),
            },
            git_commit_sha=self.commit_sha,
            git_tree_sha=self.tree_sha,
            working_tree_status=None,
            checked_at=_now_iso(),
            freshness="fresh",
        )


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


def _collect_blob_shas(repo: object, tree_sha: bytes) -> dict[str, str]:
    """Recorre un tree recursivamente y devuelve {path: blob_sha}.

    El path se reconstruye como 'a/b/c' insertando '/' entre componentes.
    dulwich entrega `entry.path` como bytes solo con el nombre del
    segmento (no incluye '/' final aunque sea un subdirectorio), asi
    que concatenacion directa -> 'srca.py' en vez de 'src/a.py'.
    """
    out: dict[str, str] = {}

    def _visit(sha: bytes, path: bytes) -> None:
        obj = repo[sha]
        if obj.type_name == b"tree":
            for entry in obj.items():
                child = path + b"/" + entry.path if path else entry.path
                _visit(entry.sha, child)
        elif obj.type_name == b"blob":
            out[path.decode(errors="replace")] = sha.decode()

    for entry in repo[tree_sha].items():
        root = entry.path
        _visit(entry.sha, root)
    return out


def _changed_file_from(ch: object) -> ChangedFile | None:
    """Convierte un tree change de dulwich en `ChangedFile`, o None.

    Un tree change sin path en old ni new no es representable como
    cambio de fichero y se descarta (comportamiento observado, fijado
    por la red de contrato de detect_changes).
    """
    path = _resolve_change_path(ch)
    if path is None:
        return None
    old_sha = ch.old.sha.decode() if ch.old and ch.old.sha else None  # type: ignore[attr-defined]
    new_sha = ch.new.sha.decode() if ch.new and ch.new.sha else None  # type: ignore[attr-defined]
    return ChangedFile(
        path=path,
        old_blob_sha=old_sha,
        new_blob_sha=new_sha or "",
        status=_classify_change_status(old_sha, new_sha),
    )


def _matches_pathspec(path: str, pathspec: str) -> bool:
    """Match un path contra un pathspec.

    Soporta:
      - globs con wildcards en cualquier posicion ('*.py', 'src/*.py',
        'src/foo-?.py') via fnmatch.
      - paths literales como prefijo: 'src' matchea 'src/a.py' pero NO
        'src_old/x.py'.
    """
    import fnmatch

    if any(c in pathspec for c in "*?["):
        return fnmatch.fnmatch(path, pathspec)

    # Literal: prefijo-segmento (no substring).
    normalized = pathspec.rstrip("/")
    return path == normalized or path.startswith(normalized + "/")


def _safe_capture_status(repo_root: str, porcelain: object) -> dict[str, object] | None:
    """Captura el working tree status.

    Antes devolvia `{}` ante cualquier fallo, y ese `{}` viaja dentro
    del `Source.locator`. Un repo roto, o no-repo, se convertia asi
    en un Source que afirma "no hay cambios pendientes": un dato
    plausible y falso, que es peor que un error.

    `None` significa "no se pudo determinar" y la clave se omite del
    locator, de modo que la ausencia es distinguishable de un working
    tree limpio. El consumidor decide si eso es tolerable.
    """
    try:
        st = porcelain.status(repo_root)
    except Exception:
        # Se captura `Exception` entera porque `dulwich` falla con
        # varias familias (ValueError en un path no-repo, KeyError con
        # refs ausentes, OSError en un repo corrupto) y enumerarlas
        # ataria esta funcion al backend. El `return None` de abajo hace
        # que el fallo NO se disfraze de "working tree limpio".
        return None
    return {
        "staged": {
            "add": list(st.staged["add"]),
            "delete": list(st.staged["delete"]),
            "modify": list(st.staged["modify"]),
        },
        "unstaged": [p.decode(errors="replace") for p in st.unstaged],
        "untracked": [p.decode(errors="replace") for p in st.untracked],
    }


def _compute_content_hash(blob_shas: dict[str, str]) -> str:
    """Hash determinista de los blob SHAs ordenados: sha256(path\x00blob-sha\x00...)."""
    h = hashlib.sha256()
    for path in sorted(blob_shas):
        h.update(path.encode())
        h.update(b"\x00")
        h.update(blob_shas[path].encode())
        h.update(b"\x00")
    return f"sha256:{h.hexdigest()}"


def _resolve_change_path(ch: object) -> str | None:
    """Path de un tree change; None si no hay path en old ni new."""
    if ch.old and ch.old.path:
        return ch.old.path.decode(errors="replace")
    if ch.new and ch.new.path:
        return ch.new.path.decode(errors="replace")
    return None


def _classify_change_status(old_sha: str | None, new_sha: str | None) -> ChangeStatusLiteral:
    """added/old=None, deleted/new=None, modified/ambas."""
    if old_sha is None:
        return "added"
    if new_sha is None:
        return "deleted"
    return "modified"


__all__ = [
    "ChangeStatus",
    "ChangedFile",
    "DulwichNotAvailableError",
    "GitSource",
    "_dulwich_import_failed_for_test",
    "set_dulwich_import_failed",
]
