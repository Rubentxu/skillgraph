"""Red de contrato WI-70: `extract_file_signatures` deriva la vigencia.

La funcion era 116 LoC con cc~10, la mas larga y mas compleja que
queda en el frente P3. Su peso no era logica: eran **cuatro
construcciones repetidas** de `SignatureVigencia` con el par
`fresh`/`stale` escrito a mano, y cuatro de `SignatureProcedencia`.

Ese par no es arbitrario: `SignatureVigencia.__post_init__` **rechaza**
la incoherencia, asi que escribirlo a mano en cada sitio son cuatro
oportunidades de que el extractor reviente en runtime con un fichero
correcto. Derivarlo del estado en un unico sitio hace que esa
inferencia sea imposible de equivocar.

Lo que fija esta red:

1. `fresh`/`stale` se **derivan** del estado, no se escriben a mano:
   hay una unica funcion que decide la regla, y la red comprueba que
   cubre los cinco estados de la ADT cerrada.
2. La salida del extractor no cambia: mismo numero de signatures, mismo
   orden (summary primero), mismos estados para los tres casos
   (ausente, vacio, con contenido).
3. `_scan_lines` distingue `import` de `def` y respeta el `continue`
   (una linea de import no puede caer tambien en la rama de def).
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from skillgraph.knowledge import file_signature as fs
from skillgraph.knowledge.file_signature import (
    EXTRACTION_STATES,
    FileSignature,
    SignatureVigencia,
    extract_file_signatures,
)


class TestVigenciaDerivedNotWritten:
    """REQ-WI70-1: la regla fresh/stale vive en un solo sitio."""

    def test_helper_exists(self) -> None:
        assert callable(getattr(fs, "_vigencia", None)), "falta el constructor unico"

    @pytest.mark.parametrize("state", sorted(EXTRACTION_STATES))
    def test_helper_covers_every_state(self, state: str) -> None:
        v = fs._vigencia(state)
        assert v.state == state
        # La regla del docstring de SignatureVigencia: fresh solo para
        # complete; stale para el resto.
        assert v.fresh is (state == "complete"), f"fresh mal derivado para {state}"
        assert v.stale is (state != "complete"), f"stale mal derivado para {state}"

    def test_helper_is_the_only_place_the_pair_is_decided(self) -> None:
        """No basta con que exista: debe usarse en todas partes."""
        src = inspect.getsource(extract_file_signatures)
        assert "fresh=" not in src, (
            "extract_file_signatures sigue escribiendo fresh= a mano: "
            "la regla debe pasar por _vigencia()"
        )
        assert "stale=" not in src, "extract_file_signatures sigue escribiendo stale= a mano"

    def test_procedencia_helper_exists(self) -> None:
        assert callable(getattr(fs, "_procedencia", None))
        p = fs._procedencia("regex_import")
        assert p.extraction_method == "regex_import"
        assert p.extractor_version == fs._EXTRACTOR_VERSION


class TestOutputUnchanged:
    """REQ-WI70-2: mismo comportamiento, otro reparto."""

    def test_absent_sentinel(self) -> None:
        sigs = extract_file_signatures(file_path="<absent>", content="import os\n")
        assert len(sigs) == 1
        assert sigs[0].vigencia.state == "absent"
        assert sigs[0].vigencia.fresh is False
        assert sigs[0].vigencia.stale is True
        assert sigs[0].cobertura == 0
        assert sigs[0].procedencia.extraction_method == "absent_sentinel"

    def test_empty_file(self) -> None:
        sigs = extract_file_signatures(file_path="a.py", content="")
        assert len(sigs) == 1
        assert sigs[0].vigencia.state == "empty"
        assert sigs[0].cobertura == 0

    def test_summary_comes_first(self) -> None:
        sigs = extract_file_signatures(file_path="a.py", content="import os\n")
        assert sigs[0].contrato == "file_summary"
        assert sigs[0].foco == "a.py"
        assert sigs[0].vigencia.state == "complete"

    def test_no_heuristic_gives_partial(self) -> None:
        """Sin imports ni defs el summary es `partial`, no `complete`."""
        sigs = extract_file_signatures(file_path="a.py", content="x = 1\ny = 2\n")
        assert len(sigs) == 1
        assert sigs[0].vigencia.state == "partial"
        assert sigs[0].vigencia.fresh is False
        assert sigs[0].cobertura == 2

    def test_imports_and_defs_are_extracted(self) -> None:
        sigs = extract_file_signatures(
            file_path="a.py", content="import os\nfrom x import y\ndef f():\n    pass\n"
        )
        summary = sigs[0]
        rest = sigs[1:]
        contratos = {s.contrato for s in rest}
        assert contratos == {"module", "def"}, contratos
        assert summary.cobertura == 4
        defs = [s for s in rest if s.contrato == "def"]
        assert defs[0].foco == "a.py::def::f"
        assert defs[0].vigencia.state == "complete"

    def test_from_import_records_the_imported_symbol(self) -> None:
        """Comportamiento ACTUAL, fijado para que el refactor no lo mueva.

        `from pkg.mod import thing` produce foco `a.py::thing`, no
        `a.py::pkg.mod`: el regex toma el grupo 2 (el simbolo) antes que
        el grupo 1 (el modulo). El campo se llama `module` y se
        etiqueta `contrato="module"`, asi que el nombre no coincide con
        lo que registra para imports con `from`.

        No lo corrijo aqui: cambiarlo altera el payload que alimenta
        `compile_handoff_from_scopes` y la compilacion de contexto, y
        eso excede un refactor estructural. Queda como decision de
        producto, no como deuda de legibilidad.
        """
        sigs = extract_file_signatures(file_path="a.py", content="from pkg.mod import thing\n")
        modules = [s for s in sigs if s.contrato == "module"]
        assert modules[0].foco == "a.py::thing", modules[0].foco

    def test_plain_import_records_the_module(self) -> None:
        sigs = extract_file_signatures(file_path="a.py", content="import os\n")
        modules = [s for s in sigs if s.contrato == "module"]
        assert modules[0].foco == "a.py::os", modules[0].foco

    def test_every_signature_is_valid(self) -> None:
        """`__post_init__` acepta todo lo que produce el extractor."""
        sigs = extract_file_signatures(
            file_path="a.py", content="import os\ndef f():\n    pass\nplain = 1\n"
        )
        for s in sigs:
            assert isinstance(s, FileSignature)
            assert isinstance(s.vigencia, SignatureVigencia)
            assert s.cobertura >= 0

    def test_is_pure(self) -> None:
        """Sin I/O, sin reloj, sin red (AGENTS 1.1/1.3)."""
        src = inspect.getsource(fs)
        for forbidden in ("open(", "Path(", "datetime", "time.time", "requests", "sqlite3"):
            assert forbidden not in src, f"file_signature usa {forbidden}"


class TestScanLineSeparation:
    """REQ-WI70-3: import y def no se mezclan."""

    def test_scan_lines_exists(self) -> None:
        assert callable(getattr(fs, "_scan_lines", None))

    def test_import_line_is_not_also_a_def(self) -> None:
        sigs = extract_file_signatures(file_path="a.py", content="import os\n")
        contratos = {s.contrato for s in sigs[1:]}
        assert contratos == {"module"}, contratos

    def test_continue_is_preserved(self) -> None:
        """Una linea `import` no debe caer en la rama de `def`.

        Es el detalle que un `if/elif` mal hecho romperia en silencio.
        """
        sigs = extract_file_signatures(
            file_path="a.py", content="from a.b import c\ndef g():\n    pass\n"
        )
        modules = [s for s in sigs if s.contrato == "module"]
        defs = [s for s in sigs if s.contrato == "def"]
        assert len(modules) == 1 and modules[0].foco == "a.py::c"
        assert len(defs) == 1 and defs[0].foco == "a.py::def::g"
        # Lo que el `continue` protege: la linea de import NO produce
        # ademas una signature de tipo "def". summary + module + def.
        assert len(sigs) == 3, [x.contrato for x in sigs]


class TestLegibility:
    def test_extractor_under_80_loc(self) -> None:
        loc = len(inspect.getsource(extract_file_signatures).splitlines())
        assert loc < 80, f"extract_file_signatures sigue en {loc} LoC"

    def test_module_growth_is_deliberate_not_accidental(self) -> None:
        """El fichero CRECE (258 -> ~287) y es una decision consciente.

        Se paga un docstring por helper a cambio de que la regla
        fresh/stale exista en un unico sitio. Lo que no se admite es que
        crezca por duplicacion: los helpers no se re-definen ni se
        copian entre si.
        """
        import ast

        path = inspect.getsourcefile(fs)
        assert path is not None
        with Path(path).open(encoding="utf-8") as handle:
            tree = ast.parse(handle.read())
        funcs = [n.name for n in tree.body if isinstance(n, ast.FunctionDef)]
        assert len(funcs) == len(set(funcs)), f"helpers duplicados: {funcs}"
        for name in (
            "_procedencia",
            "_vigencia",
            "_summary",
            "_module_signature",
            "_def_signature",
            "_scan_lines",
        ):
            assert name in funcs, f"falta el helper {name}"
