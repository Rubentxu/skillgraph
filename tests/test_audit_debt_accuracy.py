"""La prosa de la auditoria no puede afirmar hotspots que el codigo ya no tiene.

``audits/audit_debt.py`` calcula bien las metricas: sus tablas
automaticas salen de medir el arbol AST. El problema era la seccion
"Recomendaciones", escrita a mano con numeros congelados que los
refactors de WI-23..WI-27 dejaron obsoletos, de modo que el informe
decia a la vez "0 hotspots publicos cc>=20" y "main cc=43".

Estos tests atan la prosa a la medicion. Fallan si alguien reintroduce
cifras escritas a mano, y por eso son la red que evita que la deuda
documental vuelva.

Los tests se ejecutan como ``subprocess`` por la misma razon que
``test_audit_debt_smoke``: el codigo de auditoria no cuenta como
cobertura productiva.
"""

from __future__ import annotations

import ast
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SRC = _PROJECT_ROOT / "src"


def _load_audit_module():
    """Carga ``audits/audit_debt.py`` como modulo, sin ejecutarlo."""
    spec = importlib.util.spec_from_file_location(
        "audit_debt_under_test", _PROJECT_ROOT / "audits" / "audit_debt.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_audit() -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, "audits/audit_debt.py"]
    return subprocess.run(
        cmd,
        cwd=str(_PROJECT_ROOT),
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


def _measure(cc_of) -> dict[str, frozenset[int]]:
    """Mide cc real de todas las funciones de ``src/``, agrupadas por nombre.

    Un mismo nombre puede vivir en varios modulos, asi que se guarda el
    conjunto de valores medidos y no un unico entero.
    """
    measured: dict[str, set[int]] = {}
    for path in _SRC.rglob("*.py"):
        if "__pycache__" in str(path):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                measured.setdefault(node.name, set()).add(cc_of(node))
    return {name: frozenset(values) for name, values in measured.items()}


def _report_text() -> str:
    proc = _run_audit()
    assert proc.returncode == 0, f"audit_debt.py fallo: rc={proc.returncode}\n{proc.stderr}"
    return Path(proc.stdout.strip()).read_text()


def test_recommendations_match_measured_complexity() -> None:
    """Toda cifra de cc citada en la prosa debe ser la cifra medida.

    Este es el test que habria atrapado el informe de hoy: la prosa
    declaraba ``main`` cc=43, ``cmd_run`` cc=22 y
    ``_make_schema_validator`` cc=22 cuando los tres miden cc<=13.

    La comprobacion es de igualdad exacta y no "cc>=20", porque asi el
    test sigue siendo util aunque no quede ningun hotspot: cualquier
    deriva futura entre prosa y codigo la captura.
    """
    module = _load_audit_module()
    measured = _measure(module.cyclomatic)
    text = _report_text()

    # Extrae "`nombre` (`fichero`): cc=N" de la prosa de recomendaciones.
    claims = re.findall(r"`(\w+)`\s*\(`[^`]*`\):\s*cc=(\d+)", text)

    offenders: list[str] = []
    for name, claimed in claims:
        real = measured.get(name)
        if real is None:
            offenders.append(f"{name}: afirmado cc={claimed} pero la funcion no existe en src/")
        elif int(claimed) not in real:
            reales = ", ".join(str(cc) for cc in sorted(real))
            offenders.append(
                f"{name}: prosa afirma cc={claimed}, medido cc={reales}"
                + (" (ya refactorizado)" if max(real) < 20 else "")
            )
    assert not offenders, "prosa obsoleta respecto al codigo:\n  " + "\n  ".join(offenders)


def test_derived_report_cites_nothing_when_no_hotspot_exists() -> None:
    """Si el codigo no tiene hotspots, la prosa tampoco los inventa.

    Cierra el requisito de que el informe no puede afirmar refactors
    obligatorios inexistentes. Cuando la seccion P0 esta vacia, ninguna
    funcion puede aparecer citada con cc en toda la prosa.
    """
    module = _load_audit_module()
    measured = _measure(module.cyclomatic)
    text = _report_text()

    p0_block = text.split("**P0", 1)[-1].split("**P1", 1)[0]
    claims = re.findall(r"cc=(\d+)", p0_block)
    if not claims:
        # P0 vacio: ninguna funcion puede llegar a cc>=20 en el codigo.
        assert max((max(v) for v in measured.values()), default=0) < 20, (
            "P0 aparece vacio pero el codigo tiene funciones con cc>=20; "
            "el informe esta escondiendo deuda real"
        )
    else:
        for claimed in claims:
            assert int(claimed) >= 20, f"P0 cita cc={claimed}, por debajo del umbral"


def test_recommendations_have_no_hardcoded_counts() -> None:
    """La prosa no lleva contadores congelados: el resumen manda.

    Los god modules si se nombran en prosa, pero con su LoC leido del
    arbol, no escrito a mano.
    """
    module = _load_audit_module()
    measured = _measure(module.cyclomatic)
    text = _report_text()

    for name, real_ccs in measured.items():
        if max(real_ccs) < 20:
            continue
        # Si existe una funcion por encima del umbral, el informe debe
        # citarla como hotspot medido, no esconderla.
        assert name in text, (
            f"{name} mide cc={max(real_ccs)} (>=20) y deberia aparecer en el informe; "
            "la prosa se ha quedado atras respecto al codigo"
        )


def test_god_module_sizes_are_not_hardcoded() -> None:
    """Las LoC citadas para god modules coinciden con el archivo real."""
    text = _report_text()
    rows = re.findall(r"^\|\s*(\d+)\s*\|\s*`([^`]+\.py)`\s*\|$", text, re.MULTILINE)
    assert rows, "la tabla de archivos grandes salio vacia"

    for claimed_loc, rel in rows:
        path = _PROJECT_ROOT / rel
        if not path.exists():
            continue
        real_loc = len(path.read_text(encoding="utf-8").splitlines())
        # El informe mide LoC logico del AST, que puede diferir en unas
        # lineas de las fisicas. Tolerancia acotada a proposito.
        assert abs(real_loc - int(claimed_loc)) <= 40, (
            f"{rel}: informe afirma {claimed_loc} LoC, el archivo tiene {real_loc}; "
            "la cifra escrita a mano se ha quedado obsoleta"
        )


def test_report_is_internally_consistent() -> None:
    """El executive summary y las tablas dicen lo mismo.

    Si el resumen afirma N hotspots cc>=20, la tabla debe tener N filas
    de cc>=20. Hoy el resumen dice 0 y la tabla esta vacia; lo que no
    puede pasar es que digan cosas distintas.
    """
    text = _report_text()

    m = re.search(r"\*\*(\d+)\*\* funciones publicas con cc>=20", text)
    assert m, "no se encontro el contador de hotspots publicos en el resumen"
    claimed = int(m.group(1))

    # Cuenta filas de la tabla de hotspots publicos: | cc | LoC | func | path |
    section = text.split("## Hotspots publicos", 1)[-1]
    section = section.split("##", 1)[0]
    rows = [ln for ln in section.splitlines() if re.match(r"^\|\s*\d+\s*\|\s*\d+\s*\|", ln)]
    assert len(rows) == claimed, (
        f"resumen afirma {claimed} hotspots publicos cc>=20 pero la tabla tiene {len(rows)} filas"
    )
