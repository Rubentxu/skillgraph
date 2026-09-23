# Slice 3 — Git fingerprinting con dulwich

> Sub-spec del H3 (`specs/h3-knowledge.md`). Define la clase
> `GitSource` que captura commit/tree/blob SHAs y detecta cambios.
> Depende de Slice 1 (Source ADT + Storage) y Slice 2 (KnowledgeController
> para registrar las sources extraídas).
> NO se ejecuta antes de que el spec H3 esté firmado (D2, D3, D4).
> Estado: **DISEÑO**.

## 1. Objetivo

Introducir `GitSource` como fábrica de `Source` que automatiza la
captura de identidad Git (commit SHA + tree SHA + blob SHAs de los
pathspecs relevantes + working tree status) sin requerir que el
caller sepa de Git.

**Lo que este slice entrega:**
- `src/skillgraph/git_source.py` con la clase.
- Dependencia opcional `dulwich` añadida a `pyproject.toml` (no obligatoria).
- 8 tests con un repo Git temporal en `tmp_path`.

## 2. Decisiones de diseño

### D13 — `dulwich` como dependencia opcional

```toml
[project.optional-dependencies]
git = ["dulwich>=0.21"]
```

Los usuarios que no usen Git fingerprinting NO necesitan instalar
`dulwich`. El import se hace lazy dentro de `git_source.py`:

```python
try:
    from dulwich.repo import Repo
    HAS_DULWICH = True
except ImportError:
    HAS_DULWICH = False
```

`GitSource.from_commit()` lanza `dulwich.NotAvailableError` con
código `sg_dulwich_not_installed` si no está.

### D14 — `GitSource` dataclass frozen, no subclass de `Source`

`Source` es el ADT persistente. `GitSource` es una fábrica +
helper para detectar cambios. NO se persiste como tal.

```python
@dataclass(frozen=True, slots=True)
class GitSource:
    repo_root: Path
    commit_sha: str
    pathspecs: tuple[str, ...]  # globs o paths relativos

    def to_source(self, *, source_id: SourceID) -> Source: ...
    def detect_changes(self, *, since_commit: str) -> list[ChangedFile]: ...
```

### D15 — `ChangedFile` minimal info para invalidación

```python
@dataclass(frozen=True, slots=True)
class ChangedFile:
    path: str
    old_blob_sha: str | None
    new_blob_sha: str
    status: Literal["modified", "added", "deleted"]
```

Slice 4 usará `ChangedFile` para propagar invalidación.

## 3. API pública

```python
class GitSource:
    """Fabrica de Source a partir de un commit Git."""

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

        Devuelve (GitSource, Source) para que el caller pueda
        registrar el Source en KnowledgeController y mantener el
        GitSource localmente para refrescos.
        """

    def refresh(self) -> Source:
        """Re-captura el Source en el mismo commit_sha (sin avanzar)."""

    def detect_changes(
        self,
        *,
        since_commit: str,
        until_commit: str | None = None,  # default = HEAD
    ) -> list[ChangedFile]:
        """Diff entre dos commits, filtrado por pathspecs."""
```

## 4. Tests (`tests/test_git_source.py`)

**8 tests con repo temporal en `tmp_path`:**

1. `test_from_commit_captures_head` — captura HEAD, devuelve SHAs no vacíos.
2. `test_from_commit_explicit_sha` — captura SHA específico, NO HEAD.
3. `test_from_commit_pathspec_filters_blobs` — pathspec `"src/*.py"`
   limita los blobs capturados.
4. `test_to_source_roundtrip` — `GitSource.to_source()` produce un
   `Source` válido que el KnowledgeController acepta.
5. `test_refresh_returns_updated_source` — modifica working tree
   pero NO commit; refresh devuelve Source con working_tree_status
   actualizado pero commit_sha sin cambios.
6. `test_detect_changes_returns_modified_files` — commit inicial,
   modificar file, commit; `detect_changes` lista el cambio.
7. `test_detect_changes_with_pathspec_filter` — el filter limita
   el diff a los paths relevantes.
8. `test_from_commit_without_dulwich_raises` — monkeypatch
   `dulwich_import_failed` → lanza `DulwichNotAvailableError`.

## 5. Dependencia añadida

```toml
[project.optional-dependencies]
git = ["dulwich>=0.21,<1.0"]

[dependency-groups]
dev = [
    "pytest>=8",
    "pytest-cov>=6",
    "ruff>=0.6",
    "dulwich>=0.21",  # solo en dev para tests de Slice 3+
]
```

## 6. Criterios de aceptación

Slice 3 completado cuando:
1. 8 tests verdes (`bash scripts/ci.sh` → 161+17+14+8 = **200 passed**).
2. `dulwich` está en `dev` group pero NO en `dependencies`.
3. `git_source.py` no rompe el import si `dulwich` falta.
4. Tests usan `tmp_path` para crear el repo, sin red.
5. Commit: `feat(h3-s3): Git fingerprinting con dulwich (local-only)`.

## 7. Out of scope

- **Invalidación transitiva**: `detect_changes` devuelve `list[ChangedFile]`
  pero NO marca Claims como stale. Eso es Slice 4.
- **Red/clone/push/fetch**: NO se hace nada con remotos. `GitSource`
  solo lee `.git/` local.
- **Submodules/worktrees**: no soportados. Documentado en `R6`.

## 8. Riesgos

### R6 — Submodules y worktrees múltiples

`dulwich.Repo` solo abre el worktree principal. Si un proyecto
usa submodules o worktrees múltiples, no se cubren. Documentar
como limitation. H4+ puede reconsiderar.

### R7 — Performance sobre repos grandes

`get_walker(paths=[...])` con pathspec amplio puede ser lento en
repos con >100k commits. Mitigación: pathspecs específicos.
Documentado en `R7`.

### R8 — Working tree status vs index

`dulwich.porcelain.status(repo)` retorna `staged`/`unstaged`/
`untracked`. Slice 3 captura todos en el JSON del Source. Slice 4
decidirá cuáles disparan invalidación.

## 9. Referencias

- Spec padre: `specs/h3-knowledge.md` §2.4.
- D1 cerrada: `dulwich` (commit `0e94e16`).
- Spike de validación: `/tmp/sg-git-spike/probe.py` (ya no existe;
  resultados en `specs/h3-knowledge.md` §8 D1).
- Blueprint §5 (Git fingerprinting).
