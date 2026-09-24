"""Tests del modulo skill_importer (H5).

Cubre:
- Pipeline IMPORT -> ANALYZE -> STRUCTURE -> VALIDATE -> REGISTER.
- NUNCA ejecuta scripts Python del material.
- Conserva el source con content_hash.
- Genera informe con files_structured/entries_ambiguous/scripts_detected.
- capabilities_extraidas son SEÑALES (no decisiones).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from skillgraph.domain.skill_importer import (
    analyze_skill,
    register_imported_skill,
)
from skillgraph.platform.storage import Storage


def _write(p: Path, content: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


class TestSkillImportPipeline:
    def test_script_never_executes_during_import(self, tmp_path: Path) -> None:
        """Regla dura: scripts Python del material importado NO se ejecutan."""
        skill = tmp_path / "skill"
        skill.mkdir()
        _write(
            skill / "evil.py",
            "raise SystemExit(99)\n",  # Si se ejecuta, falla el test.
        )

        report = analyze_skill(skill)

        # El script aparece como ambiguo (ignored) y NUNCA como exit code !=0.
        assert any(
            e.path == "evil.py" and e.ambiguity == "ignored" for e in report.entries_ambiguous
        )
        assert "evil.py" in report.scripts_detected

    def test_structured_files_get_kind_and_hash(self, tmp_path: Path) -> None:
        skill = tmp_path / "skill"
        skill.mkdir()
        _write(skill / "README.md", "# Title\n\n## Body\nText.\n")
        _write(skill / "config.json", '{"k": "v"}')

        report = analyze_skill(skill)

        structured_paths = {sf.path for sf in report.files_structured}
        assert structured_paths == {"README.md", "config.json"}
        for sf in report.files_structured:
            assert sf.content_hash.startswith("sha256:")
            assert sf.size_bytes > 0
            if sf.path.endswith(".md"):
                assert sf.kind == "markdown_doc"
            elif sf.path.endswith(".json"):
                assert sf.kind == "json_config"

    def test_capabilities_are_signals_not_decisions(self, tmp_path: Path) -> None:
        skill = tmp_path / "skill"
        skill.mkdir()
        _write(
            skill / "README.md",
            "# Skill\n\n## Capability: review\nDescription.\n\n### Sub: lint\nMore.\n",
        )

        report = analyze_skill(skill)

        # Headers literales, no reinterpretados.
        assert "Capability: review" in report.capabilities_extracted
        assert "Sub: lint" in report.capabilities_extracted
        # nota_honesta lo deja claro.
        assert "NO decisiones verificadas" in report.nota_honesta

    def test_binary_files_marked_unparsed(self, tmp_path: Path) -> None:
        skill = tmp_path / "skill"
        skill.mkdir()
        (skill / "data.bin").write_bytes(b"\x00\x01\x02\xff\xfe")

        report = analyze_skill(skill)

        assert any(
            e.path == "data.bin" and e.ambiguity == "unparsed" for e in report.entries_ambiguous
        )
        # No se estructura.
        assert all(sf.path != "data.bin" for sf in report.files_structured)

    def test_content_hash_stable(self, tmp_path: Path) -> None:
        """El hash NO cambia entre invocaciones del mismo material."""
        skill = tmp_path / "skill"
        skill.mkdir()
        _write(skill / "a.md", "# a\n")
        _write(skill / "b.json", "{}")

        r1 = analyze_skill(skill)
        r2 = analyze_skill(skill)
        assert r1.content_hash == r2.content_hash

    def test_raises_for_missing_path(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            analyze_skill(tmp_path / "nonexistent")


class TestRegisterImportedSkill:
    def test_source_persisted_with_skill_pack_kind(self, tmp_path: Path) -> None:
        skill = tmp_path / "skill"
        skill.mkdir()
        _write(skill / "x.md", "# x\n")

        report = analyze_skill(skill)
        db = tmp_path / "test.sqlite"
        storage = Storage(db)

        sid = register_imported_skill(
            storage=storage,
            tenant_id="default",
            project_id="demo",
            report=report,
        )
        assert sid == report.source_id

        with sqlite3.connect(db) as conn:
            row = conn.execute(
                "SELECT source_id, kind, content_hash FROM sources WHERE source_id = ?",
                (sid,),
            ).fetchone()
        assert row is not None
        assert row[0] == sid
        assert row[1] == "skill_pack"
        assert row[2] == report.content_hash

    def test_to_dict_roundtrip(self, tmp_path: Path) -> None:
        """to_dict() produce JSON estable serializable."""
        skill = tmp_path / "skill"
        skill.mkdir()
        _write(skill / "r.md", "# r\n\n## c\n")

        report = analyze_skill(skill)
        d = report.to_dict()
        # Debe ser serializable.
        s = json.dumps(d)
        d2 = json.loads(s)
        assert d2["source_id"] == report.source_id
        assert d2["original_path"] == str(skill.resolve())
        assert d2["files_total"] == 1
