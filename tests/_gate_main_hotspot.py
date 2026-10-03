"""WI-103: la medición del gate de `main` como hotspot público.

Por qué este módulo existe
--------------------------
`TestAuditGateForMain` declara una propiedad sobre el **código** —«`main` no
debe listarse como hotspot público (cc≥20)»— y la comprobaba leyendo
`audits/architecture-debt-<HOY>.md`, con un `pytest.skip` si ese fichero no
existía.

MEDIDO, con el gate tal como estaba:

| situación | resultado |
|---|---|
| sin informe de hoy | **SKIPPED**, exit 0 |
| informe de hoy generado | 1 passed (hoy `main` no es hotspot) |
| informe de hoy con `main` inyectado | 1 **failed**, exit 1 |

La propiedad es real y el gate muerde cuando el artefacto está. El defecto es
**la existencia del artefacto**: 6 informes en 7 días (falta el `2026-09-30`)
y hoy no hay ninguno, con el gate en `SKIPPED` y verde. Un gate que solo corre
cuando alguien se acuerda de correr el auditor no es un gate.

`AGENTS.md §6.2`: «NO usar `pytest.skip` para esconder fallos: o arreglas el
test o lo borras».

Qué hace este módulo
--------------------
Ejecuta `audits/audit_debt.py` —el mismo análisis que genera los informes— y
devuelve los nombres públicos con cc≥20. **Mide**, no lee un snapshot: el
resultado no depende de ninguna fecha y es el del código que hay ahora.

`--src-root` y `--out-dir` son parámetros desde WI-89, que los hizo parámetros
precisamente para que un test pueda auditar sin mutar `audits/`, que está
versionado. Aquí siempre se pasa un `out_dir` temporal.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Final

REPO_ROOT: Final = Path(__file__).resolve().parent.parent
AUDITOR: Final = REPO_ROOT / "audits" / "audit_debt.py"

#: Umbral de complejidad ciclomatica a partir del cual una funcion publica es
#: «hotspot». El MISMO que usa `audits/audit_debt.py` al escribir el informe:
#: si el gate usara otro, comprobaria una propiedad distinta de la que dice.
UMBRAL_CC: Final = 20


def _cargar_auditor() -> object:
    """Importa `audits/audit_debt.py` como modulo.

    `audits/` no es un paquete, asi que se carga por ruta. El modulo solo
    define funciones y constantes relativas; importarlo no ejecuta el
    analisis, que vive en `main()`.

    Vive aqui y no en el fichero de tests porque los tests lo importan y
    duplicar el cargador seria la forma de que los dos dejaran de cargar lo
    mismo sin que nada lo note.
    """
    spec = importlib.util.spec_from_file_location("audit_debt_wi103", AUDITOR)
    if spec is None or spec.loader is None:  # pragma: no cover - Path roto
        raise RuntimeError(f"no se pudo cargar el auditor: {AUDITOR}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def hotspots_publicos(arbol: Path, *, out_dir: Path) -> tuple[str, ...]:
    """Nombres de las funciones publicas con cc>=20 en `arbol`, ordenados.

    Filtra de forma MAS estrecha que el informe a proposito: el informe lista
    hotspots publicos **y privados**, y este gate vigila la lista publica. Si
    una funcion privada creeps a cc>=20, el informe lo dira y este gate no,
    que es lo correcto: la propiedad es sobre la superficie pública.

    El analisis se hace sobre `audits/audit_debt.py`, no con una cuenta
    propia. Reimplementar la metricca seria tener dos verdades sobre «que es
    un hotspot», y la segunda dejaria de coincidir con la primera el dia que
    el umbral cambie.
    """
    auditor = _cargar_auditor()
    out_dir.mkdir(parents=True, exist_ok=True)
    argv = ["--src-root", str(arbol), "--out-dir", str(out_dir)]
    assert auditor.main(argv) == 0, f"el auditor fallo sobre {arbol}"  # type: ignore[attr-defined]

    nombres: set[str] = set()
    for fichero in sorted(Path(arbol).rglob("*.py")):
        if "__pycache__" in str(fichero):
            continue
        for func in auditor.audit_file(fichero)["funcs"]:  # type: ignore[attr-defined]
            if not func["is_private"] and func["cc"] >= UMBRAL_CC:
                nombres.add(func["name"])
    return tuple(sorted(nombres))
