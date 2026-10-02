"""WI-71: `analyze_skill` se descompone en resolver, clasificar y fusionar.

El corte no cambia comportamiento. Mueve el detalle de clasificacion a
`_classify_file` y la resolucion de la raiz a `_resolve_source`, dejando
`analyze_skill` como un plegado de una sola pasada sobre `_merge`.

La red sujeta el corte por los dos lados:

1. Estructura: el detalle de clasificacion (los motivos de ambiguedad,
   las ramas por kind) ya no vive dentro de `analyze_skill`, y los records
   intermedios son dataclasses inmutables con ``slots``.
2. Equivalencia: el informe se compara contra un **oraculo diferencial**
   que reimplementa aqui el algoritmo original de una sola pasada. Si el
   plegado pierde un campo, reordena un acento o salta una rama, el
   oraculo lo delata aunque ambas implementaciones "parezcan iguales".

Los tests 4 y 5 fijan rarezas preexistentes que ningun test cubria (el
`.` como ruta relativa en import de fichero unico, y el mensaje de error
con la raiz ya resuelta). Se fijan tal cual: documentan el comportamiento
vigente, no lo corrigen.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
from pathlib import Path

import pytest

from skillgraph.domain.skill_importer import (
    AmbiguousEntry,
    SkillImportReport,
    StructuredFile,
    _classify,
    _classify_file,
    _extract_capabilities_from_markdown,
    _FileVerdict,
    _hash_bytes,
    _hash_dir,
    _ImportSource,
    _merge,
    _read_text_safely,
    _resolve_source,
    _ScanResult,
    analyze_skill,
)
from skillgraph.knowledge.graph import source_id as make_source_id

# Motivos de ambiguedad que deben haber salido de `analyze_skill`.
_CLASSIFICATION_DETAIL = (
    "Script Python detectado",
    "Binario no textual",
    "Extension desconocida",
)


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _write_binary(path: Path, blob: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(blob)
    return path


def _sample_skill(root: Path) -> Path:
    """Arbol que ejercita TODOS los kinds que clasifica `_classify`."""
    skill = root / "skill"
    _write(skill / "SKILL.md", "# Titulo\n## Seccion A\n### Sub A1\ncuerpo\n")
    _write(skill / "notas.txt", "texto plano\n")
    _write(skill / "config.json", "{}\n")
    _write(skill / "config.yaml", "a: 1\n")
    _write(skill / "herramienta.py", "print('no se ejecuta')\n")
    _write(skill / "misterio.foobar", "data\n")
    _write_binary(skill / "logo.png", bytes(range(256)))
    _write(skill / "sub" / "anidado.md", "## Anidada\n")
    return skill


def _reference_report(root: Path) -> SkillImportReport:
    """Oraculo: el algoritmo original de `analyze_skill`, linea por linea.

    Se mantiene deliberadamente en forma imperativa y sin helpers, que es
    justo la forma que el corte pretendia eliminar de produccion. Su unico
    papel es ser un segundo criterio independiente con el que comparar.
    """
    root = Path(root).resolve()
    if not root.exists():
        raise FileNotFoundError(f"skill path no existe: {root}")

    if root.is_file():
        content_hash = _hash_bytes(root.read_bytes())
        original_path = str(root)
        files_iter = [root]
    else:
        content_hash = _hash_dir(root)
        original_path = str(root)
        files_iter = sorted(p for p in root.rglob("*") if p.is_file())

    files_total = len(list(files_iter))

    structured: list[StructuredFile] = []
    ambiguous: list[AmbiguousEntry] = []
    scripts: list[str] = []
    capabilities: list[str] = []

    for f in files_iter:
        rel = f.relative_to(root).as_posix()
        size = f.stat().st_size
        fhash = _hash_bytes(f.read_bytes())
        kind = _classify(f)

        if kind == "python_script":
            scripts.append(rel)
            ambiguous.append(
                AmbiguousEntry(
                    path=rel,
                    reason=(
                        "Script Python detectado. NO se ejecuta (criterio UAT-14/"
                        "ADR-0009). Conservado como material original; su "
                        "comportamiento permanece encapsulado hasta que un "
                        "Adapter real lo evalue."
                    ),
                    ambiguity="ignored",
                )
            )
            continue

        if kind == "binary":
            ambiguous.append(
                AmbiguousEntry(
                    path=rel,
                    reason="Binario no textual. Sin capacidad de inspeccionar contenido.",
                    ambiguity="unparsed",
                )
            )
            continue

        if kind == "unknown":
            ambiguous.append(
                AmbiguousEntry(
                    path=rel,
                    reason=f"Extension desconocida ({f.suffix!r}). Sin heuristica aplicable.",
                    ambiguity="unparsed",
                )
            )
            continue

        structured.append(StructuredFile(path=rel, kind=kind, size_bytes=size, content_hash=fhash))

        if kind == "markdown_doc":
            text = _read_text_safely(f)
            if text is not None:
                capabilities.extend(_extract_capabilities_from_markdown(text))

    nota = (
        "Las capacidades extraidas son señales heurísticas (headers Markdown), "
        "NO decisiones verificadas. La skill permanece en estado encapsulado "
        "hasta que un Adapter real evalúe su comportamiento."
    )

    return SkillImportReport(
        source_id=make_source_id(f"skill:{original_path}"),
        original_path=original_path,
        content_hash=content_hash,
        imported_at="<ignorado: reloj>",
        files_total=files_total,
        files_structured=tuple(structured),
        entries_ambiguous=tuple(ambiguous),
        scripts_detected=tuple(scripts),
        capabilities_extracted=tuple(capabilities),
        nota_honesta=nota,
    )


def _comparable(report: SkillImportReport) -> dict[str, object]:
    """Campos del informe sin el reloj, que cambia entre invocaciones."""
    data = report.to_dict()
    data.pop("imported_at")
    return data


# ---------------------------------------------------------------------------
# 1. Equivalencia: el corte no cambia el informe
# ---------------------------------------------------------------------------


def test_report_is_identical_to_the_single_pass_oracle(tmp_path: Path) -> None:
    """El plegado produce exactamente el informe del algoritmo original."""
    skill = _sample_skill(tmp_path)

    produced = analyze_skill(skill)
    expected = _reference_report(skill)

    assert _comparable(produced) == _comparable(expected)
    assert produced.source_id == expected.source_id
    assert produced.content_hash == expected.content_hash
    assert produced.imported_at  # el reloj real si se inyecta


def test_oracle_exercises_every_classification_branch(tmp_path: Path) -> None:
    """Guard del oraculo: si no cubre las ramas, su acuerdo es vacio.

    Un oraculo diferencial que solouje la rama feliz no demuestra nada,
    asi que este test falla si el arbol de muestra deja de producir kinds
    que las ramas de `analyze_skill` distinguen.
    """
    report = _reference_report(_sample_skill(tmp_path))

    kinds = {sf.kind for sf in report.files_structured}
    ambiguities = {ae.ambiguity for ae in report.entries_ambiguous}
    assert kinds == {"markdown_doc", "plain_text", "json_config", "yaml_config"}
    assert ambiguities == {"ignored", "unparsed"}
    assert report.scripts_detected == ("herramienta.py",)


# ---------------------------------------------------------------------------
# 2. Estructura: el detalle salio de `analyze_skill`
# ---------------------------------------------------------------------------


def test_analyze_skill_holds_no_classification_detail() -> None:
    """Los motivos de ambiguedad viven en `_classify_file`, no en el orquestador."""
    source = inspect.getsource(analyze_skill)

    for detail in _CLASSIFICATION_DETAIL:
        assert detail not in source, (
            f"analyze_skill vuelve a contener el detalle de clasificacion {detail!r}; "
            "el corte WI-71 se ha revertido"
        )


def test_analyze_skill_is_a_short_orchestrator() -> None:
    """El orquestador cabe en un pliegue legible, no en un pipeline de 100 lineas."""
    assert len(inspect.getsource(analyze_skill).splitlines()) <= 40


def test_intermediate_records_are_frozen_with_slots() -> None:
    """Los records del corte son datos publicados, no acumuladores mutables."""
    for record in (_ImportSource, _FileVerdict, _ScanResult):
        params = record.__dataclass_params__
        assert params.frozen is True, f"{record.__name__} es mutable"
        assert hasattr(record, "__slots__"), f"{record.__name__} no usa __slots__"


def test_merge_returns_a_new_accumulator() -> None:
    """`_merge` es una funcion pura: nunca muta el acumulador recibido."""
    empty = _ScanResult()
    verdict = _FileVerdict(structured=StructuredFile("a.md", "markdown_doc", 1, "sha256:x"))

    merged = _merge(empty, verdict)

    assert merged is not empty
    assert empty.structured == ()
    assert merged.structured == (verdict.structured,)


# ---------------------------------------------------------------------------
# 3. Semantica de `_classify_file`: un archivo, un veredicto
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("SKILL.md", (True, False, False)),
        ("notas.txt", (True, False, False)),
        ("config.json", (True, False, False)),
        ("config.yaml", (True, False, False)),
        # Un .py informa DOS datos: el script se conserva (scripts_detected)
        # y ademas queda senalado como ambiguo 'ignored' (UAT-14).
        ("herramienta.py", (False, True, True)),
        ("logo.png", (False, True, False)),
        ("misterio.foobar", (False, True, False)),
    ],
)
def test_classify_file_yields_the_expected_shape(
    tmp_path: Path, filename: str, expected: tuple[bool, bool, bool]
) -> None:
    """Cada kind se resuelve a la forma documentada de `_FileVerdict`."""
    skill = tmp_path / "skill"
    if filename.endswith(".png"):
        target = _write_binary(skill / filename, bytes(range(256)))
    else:
        target = _write(skill / filename, "# T\n## S\n")

    verdict = _classify_file(skill, target)

    shape = (
        verdict.structured is not None,
        verdict.ambiguous is not None,
        verdict.script is not None,
    )
    assert shape == expected


@pytest.mark.parametrize(
    "filename",
    ["SKILL.md", "notas.txt", "config.json", "config.yaml", "herramienta.py", "misterio.foobar"],
)
def test_structured_and_ambiguous_are_mutually_exclusive(tmp_path: Path, filename: str) -> None:
    """Invariante del veredicto: clasificado o ambiguo, nunca los dos."""
    skill = tmp_path / "skill"
    target = _write(skill / filename, "# T\n## S\n")

    verdict = _classify_file(skill, target)

    assert (verdict.structured is None) != (verdict.ambiguous is None), (
        f"{filename}: structured={verdict.structured} ambiguous={verdict.ambiguous}"
    )


def test_script_is_registered_but_never_read_as_capability(tmp_path: Path) -> None:
    """Un .py aporta script + ambiguedad 'ignored', y ninguna capacidad (UAT-14)."""
    skill = tmp_path / "skill"
    script = _write(skill / "herramienta.py", "## Esto no es una capacidad\nraise SystemExit(1)\n")

    verdict = _classify_file(skill, script)

    assert verdict.script == "herramienta.py"
    assert verdict.structured is None
    assert verdict.capabilities == ()
    assert verdict.ambiguous is not None
    assert verdict.ambiguous.ambiguity == "ignored"


def test_markdown_capabilities_only_come_from_markdown(tmp_path: Path) -> None:
    """Los headers h2/h3 se extraen solo de `.md`, no de cualquier texto."""
    skill = tmp_path / "skill"
    markdown = _write(skill / "a.md", "## Uno\n### Dos\n")
    text = _write(skill / "b.txt", "## No.Should count\n")

    assert _classify_file(skill, markdown).capabilities == ("Uno", "Dos")
    assert _classify_file(skill, text).capabilities == ()


# ---------------------------------------------------------------------------
# 4. Rarezas preexistentes fijadas (no corregidas)
# ---------------------------------------------------------------------------


def test_single_file_import_uses_dot_as_relative_path(tmp_path: Path) -> None:
    """Rareza vigente: importar un fichero suelto lo nombra `"."`.

    `Path(f).relative_to(f)` es `"."`, asi que el informe nombra `"."` y
    no el nombre del archivo. Ningun test lo cubria. Se fija el
    comportamiento ACTUAL; corregirlo es decision de producto (cambia el
    payload que consumen UAT y el informe), no un efecto del refactor.
    """
    solo = _write(tmp_path / "solo.md", "# Titulo\n## Sub\n")

    report = analyze_skill(solo)

    assert report.files_total == 1
    assert [sf.path for sf in report.files_structured] == ["."]
    # Solo h2/h3 son capacidades; `# Titulo` es h1 y no se extrae.
    assert report.capabilities_extracted == ("Sub",)


def test_resolve_source_error_names_the_resolved_root(tmp_path: Path) -> None:
    """Rareza vigente: el mensaje de ruta inexistente usa la raiz RESUELTA."""
    missing = tmp_path / ".." / "no-existe"

    with pytest.raises(FileNotFoundError) as exc:
        _resolve_source(missing)

    assert str(missing.resolve()) in str(exc.value)


# ---------------------------------------------------------------------------
# 5. La firma publica no se mueve
# ---------------------------------------------------------------------------


def test_public_signature_and_return_type_are_unchanged() -> None:
    """`analyze_skill` sigue siendo `(root: Path) -> SkillImportReport`."""
    sig = inspect.signature(analyze_skill)
    assert list(sig.parameters) == ["root"]
    assert sig.return_annotation in ("SkillImportReport", SkillImportReport)


def test_module_exports_are_unchanged() -> None:
    """El corte no altera la superficie publica del modulo."""
    from skillgraph.domain import skill_importer

    assert set(skill_importer.__all__) == {
        "Ambiguity",
        "AmbiguousEntry",
        "SkillImportReport",
        "StructuredFile",
        "analyze_skill",
        "register_imported_skill",
    }
    for name in skill_importer.__all__:
        assert hasattr(skill_importer, name), f"{name} desaparecio del modulo"


def test_helpers_are_module_level_functions() -> None:
    """Los helpers del corte son funciones de modulo, no metodos colgados."""
    for helper in (_resolve_source, _classify_file, _merge):
        assert inspect.isfunction(helper), f"{helper.__name__} deberia ser funcion de modulo"
    tree = ast.parse(Path(inspect.getsourcefile(analyze_skill) or "").read_text(encoding="utf-8"))
    names = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    assert {"_resolve_source", "_classify_file", "_merge"} <= names


def test_dataclass_field_order_is_stable() -> None:
    """El orden de los campos de `SkillImportReport` es parte del contrato to_dict."""
    fields = [f.name for f in dataclasses.fields(SkillImportReport)]
    assert fields == [
        "source_id",
        "original_path",
        "content_hash",
        "imported_at",
        "files_total",
        "files_structured",
        "entries_ambiguous",
        "scripts_detected",
        "capabilities_extracted",
        "nota_honesta",
    ]
