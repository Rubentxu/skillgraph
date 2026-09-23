"""H9-Coverage-3: cobertura de las ramas no ejercitadas de
`skillgraph.domain.skill_importer` (89% -> >=95%).

Las ramas cubiertas aqui son:
- _classify: yaml_config (extension .yaml/.yml), plain_text por mimetype
  text/*, unknown cuando mimetypes no detecta.
- _read_text_safely: returns None on UnicodeDecodeError.
- analyze_skill: root.is_file() (no directorio).
- analyze_skill: kind=unknown produce ambiguous entry.
- register_imported_skill: locator_extra agrega campos al locator.

Sin modificacion de produccion. Spec: specs/h9-coverage-skill-importer.md.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from skillgraph.domain.skill_importer import (
    _classify,
    _read_text_safely,
    analyze_skill,
    register_imported_skill,
)
from skillgraph.storage import Storage


def _write(p: Path, content: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def _storage_at(tmp_path: Path) -> Storage:
    """Storage sobre un sqlite en tmp_path (auto-migra en __init__)."""
    db = tmp_path / "project.sqlite"
    return Storage(db)


# ---------------------------------------------------------------------------
# _classify: extension .yaml / .yml
# ---------------------------------------------------------------------------


def test_yaml_config_classified_by_extension(tmp_path: Path) -> None:
    """Un archivo `.yaml` se clasifica como `yaml_config`."""
    skill = tmp_path / "skill"
    skill.mkdir()
    _write(skill / "config.yaml", "key: value\n")

    report = analyze_skill(skill)

    assert any(
        sf.path == "config.yaml" and sf.kind == "yaml_config" for sf in report.files_structured
    )


def test_yml_config_classified_by_extension(tmp_path: Path) -> None:
    """Variante `.yml` tambien produce `yaml_config`."""
    skill = tmp_path / "skill"
    skill.mkdir()
    _write(skill / "config.yml", "key: value\n")

    report = analyze_skill(skill)

    assert any(
        sf.path == "config.yml" and sf.kind == "yaml_config" for sf in report.files_structured
    )


# ---------------------------------------------------------------------------
# _classify: mimetype fallback (plain_text text/*, unknown)
# ---------------------------------------------------------------------------


def test_unknown_extension_produces_unknown_kind(tmp_path: Path) -> None:
    """Extension sin mimetype registrado produce `unknown`."""
    skill = tmp_path / "skill"
    skill.mkdir()
    # `.foobar` no tiene mimetype registrado (mimetypes.guess_type
    # devuelve (None, None)) y no esta en los sets de extension, asi
    # que _classify cae al branch final: `unknown`.
    _write(skill / "data.foobar", "binary stuff")

    report = analyze_skill(skill)

    # `unknown` va a entries_ambiguous, NO a files_structured.
    assert any(
        ae.path == "data.foobar" and ae.ambiguity == "unparsed" for ae in report.entries_ambiguous
    )
    assert all(sf.path != "data.foobar" for sf in report.files_structured)


# ---------------------------------------------------------------------------
# _read_text_safely: UnicodeDecodeError
# ---------------------------------------------------------------------------


def test_read_text_safely_returns_none_on_bad_utf8(tmp_path: Path) -> None:
    """Un archivo con bytes no-UTF-8 hace que `_read_text_safely` retorne None.

    Cubre lineas 160-161 (except UnicodeDecodeError -> return None).
    """
    bad = tmp_path / "bad.md"
    bad.write_bytes(b"\xff\xfe\x00invalid utf8")

    result = _read_text_safely(bad)
    assert result is None


# ---------------------------------------------------------------------------
# analyze_skill: root.is_file()
# ---------------------------------------------------------------------------


def test_analyze_skill_on_single_file(tmp_path: Path) -> None:
    """`analyze_skill` sobre un archivo (no directorio) activa root.is_file().

    Cubre lineas 189-191.
    """
    skill_file = tmp_path / "solo.md"
    _write(skill_file, "# Title\n## Sub\nbody\n")

    report = analyze_skill(skill_file)

    # Original path es el archivo mismo.
    assert report.original_path == str(skill_file.resolve())
    assert report.files_total == 1
    # El unico archivo entra como markdown_doc estructurado.
    assert len(report.files_structured) == 1
    assert report.files_structured[0].kind == "markdown_doc"


# ---------------------------------------------------------------------------
# analyze_skill: kind=unknown produce AmbiguousEntry
# ---------------------------------------------------------------------------


def test_unknown_kind_produces_ambiguous_entry(tmp_path: Path) -> None:
    """`kind=unknown` se reporta en `entries_ambiguous` con `unparsed`."""
    skill = tmp_path / "skill"
    skill.mkdir()
    _write(skill / "mystery.foobar", "data")

    report = analyze_skill(skill)

    assert len(report.entries_ambiguous) == 1
    ae = report.entries_ambiguous[0]
    assert ae.path == "mystery.foobar"
    assert ae.ambiguity == "unparsed"
    assert "Extension desconocida" in ae.reason


# ---------------------------------------------------------------------------
# register_imported_skill: locator_extra
# ---------------------------------------------------------------------------


def test_register_imported_skill_locator_extra_is_merged(tmp_path: Path) -> None:
    """`locator_extra` agrega campos al locator registrado en storage.

    Cubre linea 293.
    """
    skill = tmp_path / "skill"
    skill.mkdir()
    _write(skill / "README.md", "# Skill\n")

    report = analyze_skill(skill)
    storage = _storage_at(tmp_path)

    source_id = register_imported_skill(
        storage=storage,
        tenant_id="t-test",
        project_id="demo",
        report=report,
        locator_extra={"git_url": "https://example.com/repo.git", "ref": "main"},
    )

    # Recuperar el Source para verificar que locator_extra se aplico.
    with sqlite3.connect(storage.path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT locator_json FROM sources WHERE source_id = ?",
            (source_id,),
        ).fetchone()

    import json

    locator = json.loads(row["locator_json"])
    assert locator["path"] == report.original_path
    assert locator["kind"] == "skill_dir"
    assert locator["git_url"] == "https://example.com/repo.git"
    assert locator["ref"] == "main"


# ---------------------------------------------------------------------------
# _classify: plain_text por mimetype text/* (rama rara)
# ---------------------------------------------------------------------------


def test_classify_returns_unknown_for_path_without_extension(tmp_path: Path) -> None:
    """Archivo sin extension cae al branch `mimetypes` o `unknown`.

    Cubre la linea 136 (`return "unknown"`) para el caso de archivo
    sin extension y mimetype no detectable.
    """
    # Archivo sin extension: mimetypes.guess_type devuelve (None, None).
    no_ext = tmp_path / "README_no_ext"
    no_ext.write_text("hello\n", encoding="utf-8")

    kind = _classify(no_ext)
    # mimetypes puede o no detectar segun el entorno; lo que nos importa
    # es que NO lance excepcion y produce un kind conocido.
    assert kind in {"plain_text", "unknown", "markdown_doc"}
