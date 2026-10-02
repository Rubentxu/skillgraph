"""WI-91 — el registro de conformidad H9 no puede afirmar sobre el codigo.

Por que existe este fichero
---------------------------
`STATE.yaml.goal.h9_addendum_2026_09_25` es el artefacto que decide si el
hito H9 del blueprint esta cumplido. Se escribio el 2026-09-25. El
2026-09-26, v0.14.7 entrego los cuatro entregables que el registro daba
por pendientes, y el registro no se revalidó: quedo afirmando cuatro
cosas falsas y una quinta cierta.

Nada lo comprobaba. Este fichero es el guard.

La forma del guard: **afirmacion y testigo, simultaneamente**
-------------------------------------------------------------
Cada entregable declara `estado` y `evidencia_paths`. El guard exige
que las dos cosas sean verdad A LA VEZ, en los dos sentidos:

  - el estado declarado es el medido  ->  caza el registro caducado;
  - los testigos declarados existen    ->  caza la afirmacion sin
                                          respaldo.

Un guard de una sola direccion deja pasar la mitad de los fallos, que es
justo la mitad que se cuela en un documento.

Los checks viven en funciones puras (`_violaciones_*`) y este modulo las
llama de DOS maneras: sobre el `STATE.yaml` real, y sobre registros
sinteticos que se saben incorrectos. La segunda via es la que demuestra
que el guard muerde; una clase de tests que solo lee el fichero real no
distingue "el guard funciona" de "el fichero esta bien hoy".
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

import pytest
import yaml

REPO_ROOT: Final = Path(__file__).resolve().parent.parent
STATE_PATH: Final = REPO_ROOT / "STATE.yaml"

# El estado medido contra el arbol. Si esto y el registro discrepan, el
# registro es lo que se corrige: el codigo no se fixturea.
ESTADO_MEDIDO: Final[dict[str, str]] = {
    "E1-Adapter-real": "CUMPLIDA",
    "E2-Seguridad": "CUMPLIDA",
    "E3-Recuperacion": "CUMPLIDA",
    "E4-Documentacion-operativa": "CUMPLIDA",
    "E5-Suite-UAT": "CUMPLIDA",
}

# Testigos minimos que sostienen cada afirmacion. Un entregable no se
# declara cumplido sin que exista esto.
TESTIGOS: Final[dict[str, tuple[str, ...]]] = {
    "E1-Adapter-real": ("src/skillgraph/runtime/http_adapter.py",),
    "E2-Seguridad": (
        "src/skillgraph/runtime/redaction.py",
        "docs/architecture/ADR-0015-threat-model-stride.md",
    ),
    "E3-Recuperacion": ("src/skillgraph/platform/run_repository.py",),
    "E4-Documentacion-operativa": ("docs/observability-runbook.md",),
    "E5-Suite-UAT": ("tests/uat_audit.py",),
}

Entregable = dict[str, object]


# --------------------------------------------------------------------------
# Checks puros. Devuelven una lista de violaciones; vacia = conforme.
# Son funciones puras a proposito: reciben el registro y no tocan disco
# mas que para comprobar que un testigo existe, que es el efecto que el
# guard necesita comprobar y no puede simular.
# --------------------------------------------------------------------------


def _violaciones_estado(entregables: dict[str, Entregable]) -> list[str]:
    """Direccion 1: el estado declarado no es el medido contra el arbol."""
    salida = []
    for eid, medido in ESTADO_MEDIDO.items():
        declarado = str(entregables.get(eid, {}).get("estado"))
        if declarado != medido:
            salida.append(f"{eid} declara estado={declarado!r} y el codigo dice {medido!r}")
    return salida


def _violaciones_testigos(entregables: dict[str, Entregable], raiz: Path) -> list[str]:
    """Direccion 2: lo que el registro cita como evidencia no esta ahi."""
    salida = []
    for eid in TESTIGOS:
        entregable = entregables.get(eid)
        if entregable is None:
            salida.append(f"{eid} no aparece en el registro")
            continue
        declarados = entregable.get("evidencia_paths")
        if not declarados:
            salida.append(f"{eid} no declara evidencia_paths")
            continue
        for rel in declarados:  # type: ignore[union-attr]
            if not (raiz / str(rel)).exists():
                salida.append(f"{eid} declara evidencia {rel!r} y no existe")
        faltan = set(TESTIGOS[eid]) - {str(r) for r in declarados}  # type: ignore[union-attr]
        if faltan:
            salida.append(f"{eid} no declara estos testigos: {sorted(faltan)}")
    return salida


def _violaciones_resumen(addendum: dict[str, object]) -> list[str]:
    """El resumen no puede llevar su propia cuenta."""
    entregables: dict[str, Entregable] = {
        str(e["id"]): dict(e)
        for e in addendum["entregables"]  # type: ignore[index,union-attr]
    }
    resumen: dict[str, object] = dict(addendum["resumen"])  # type: ignore[arg-type]
    salida = []

    cumplidos = [e for e, v in entregables.items() if str(v["estado"]).startswith("CUMPLIDA")]
    declarados = int(resumen["entregables_cumplidos"])  # type: ignore[arg-type]
    if declarados != len(cumplidos):
        salida.append(
            f"resumen.entregables_cumplidos={declarados} pero hay {len(cumplidos)}: "
            f"{sorted(cumplidos)}"
        )

    pendientes = [e for e, v in entregables.items() if str(v["estado"]).startswith("PENDIENTE")]
    declarados_p = int(resumen["entregables_pendientes"])  # type: ignore[arg-type]
    if declarados_p != len(pendientes):
        salida.append(
            f"resumen.entregables_pendientes={declarados_p} pero hay {len(pendientes)}: "
            f"{sorted(pendientes)}"
        )

    score = str(resumen["conformance_score"])
    if not score.startswith(f"{len(cumplidos)}/"):
        salida.append(
            f"conformance_score={score!r} no arranca por {len(cumplidos)}/, que es lo medido"
        )
    return salida


def _registro() -> dict[str, object]:
    state = yaml.safe_load(STATE_PATH.read_text(encoding="utf-8"))
    return dict(state["goal"]["h9_addendum_2026_09_25"])  # type: ignore[index]


def _entregables(addendum: dict[str, object] | None = None) -> dict[str, Entregable]:
    addendum = addendum if addendum is not None else _registro()
    return {str(e["id"]): dict(e) for e in addendum["entregables"]}  # type: ignore[index,union-attr]


# --------------------------------------------------------------------------
# El guard sobre el registro real
# --------------------------------------------------------------------------


class TestGuardSobreElRegistroReal:
    def test_estado_declarado_es_el_medido(self) -> None:
        violaciones = _violaciones_estado(_entregables())
        assert not violaciones, (
            "el registro afirma sobre el codigo y no coincide. Si el estado "
            "nuevo es el correcto, actualiza ESTADO_MEDIDO con la medicion "
            "que lo respalda; si no, corrige el registro:\n  " + "\n  ".join(violaciones)
        )

    def test_todo_testigo_declarado_existe(self) -> None:
        violaciones = _violaciones_testigos(_entregables(), REPO_ROOT)
        assert not violaciones, "afirmacion sin respaldo:\n  " + "\n  ".join(violaciones)

    def test_resumen_cuadra_con_los_entregables(self) -> None:
        violaciones = _violaciones_resumen(_registro())
        assert not violaciones, "el resumen lleva su propia cuenta:\n  " + "\n  ".join(violaciones)

    @pytest.mark.parametrize("entregable_id", sorted(ESTADO_MEDIDO))
    def test_cada_entregable_es_una_afirmacion_con_testigo(self, entregable_id: str) -> None:
        """Cada entregable declara estado Y testigo. Nunca solo uno."""
        entregable = _entregables()[entregable_id]
        assert entregable.get("estado"), f"{entregable_id} sin estado"
        assert entregable.get("evidencia_paths"), (
            f"{entregable_id} sin evidencia_paths. Sin un testigo "
            f"machine-checkable su estado es una opinion, y una opinion "
            f"envejece sin avisar: es exactamente como se produjo WI-91."
        )


# --------------------------------------------------------------------------
# El guard contra registros que se saben incorrectos
#
# Sin esta clase, un guard roto pasa verde mientras el fichero real este
# conforme. Aqui se comprueba que las dos direcciones muerden.
# --------------------------------------------------------------------------


def _registro_sintetico(
    estado: str, evidencia_paths: list[str], *, solo_e1: bool = True
) -> dict[str, object]:
    """Registro de laboratorio, no el de STATE.yaml.

    `solo_e1=True` construye un unico entregable: sirve para probar que
    el guard CAZA. `solo_e1=False` construye los cinco en estado
    conforme: sirve para probar que el guard NO muerde cuando debe.
    """
    if solo_e1:
        entregables: list[Entregable] = [
            {"id": "E1-Adapter-real", "estado": estado, "evidencia_paths": evidencia_paths}
        ]
    else:
        entregables = [
            {"id": eid, "estado": "CUMPLIDA", "evidencia_paths": list(TESTIGOS[eid])}
            for eid in sorted(ESTADO_MEDIDO)
        ]
    cumplidos = sum(1 for e in entregables if str(e["estado"]).startswith("CUMPLIDA"))
    pendientes = len(entregables) - cumplidos
    return {
        "entregables": entregables,
        "resumen": {
            "entregables_cumplidos": cumplidos,
            "entregables_pendientes": pendientes,
            "conformance_score": f"{cumplidos}/{len(ESTADO_MEDIDO)}",
        },
    }


class TestGuardMuerdeEnLasDosDirecciones:
    def test_caza_el_registro_caducado(self) -> None:
        """E1 marcado PENDIENTE mientras su testigo esta en el arbol."""
        registro = _registro_sintetico("PENDIENTE", ["src/skillgraph/runtime/http_adapter.py"])
        violaciones = _violaciones_estado(_entregables(registro))
        assert violaciones, "el guard no caza un estado caducado con su testigo presente"
        assert "E1-Adapter-real" in violaciones[0]

    def test_caza_la_afirmacion_sin_respaldo(self) -> None:
        """E1 marcado CUMPLIDA sin el fichero que lo sostiene."""
        registro = _registro_sintetico("CUMPLIDA", ["src/skillgraph/no_existe.py"])
        violaciones = _violaciones_testigos(_entregables(registro), REPO_ROOT)
        assert violaciones, "el guard no caza una evidencia que no existe"
        assert any("no_existe" in v for v in violaciones)

    def test_caza_el_entregable_sin_testigos(self) -> None:
        registro = _registro_sintetico("CUMPLIDA", [])
        violaciones = _violaciones_testigos(_entregables(registro), REPO_ROOT)
        assert any("evidencia_paths" in v for v in violaciones), (
            "el guard no caza un entregable sin evidencia_paths"
        )

    def test_caza_el_resumen_descuadrado(self) -> None:
        registro = _registro_sintetico("CUMPLIDA", ["src/skillgraph/runtime/http_adapter.py"])
        registro["resumen"] = {  # type: ignore[index]
            "entregables_cumplidos": 4,
            "entregables_pendientes": 0,
            "conformance_score": "4/5",
        }
        violaciones = _violaciones_resumen(registro)
        assert violaciones, "el guard no caza un resumen que no cuadra"
        assert any("conformance_score" in v for v in violaciones)

    def test_un_registro_correcto_no_produce_violaciones(self) -> None:
        """La contraparte: un guard que siempre falla no es un guard."""
        registro = _registro_sintetico("CUMPLIDA", [], solo_e1=False)
        entregables = _entregables(registro)
        assert not _violaciones_estado(entregables), (
            "un registro conforme no debe producir violaciones de estado"
        )
        assert not _violaciones_testigos(entregables, REPO_ROOT), (
            "un registro conforme no debe producir violaciones de testigos"
        )
        assert not _violaciones_resumen(registro), (
            "un registro conforme no debe producir violaciones de resumen"
        )


class TestElCriterioDeSalidaNoSeDeclaraCumplidoSinEjecutarlo:
    """Los 5 entregables cumplidos NO son el criterio de salida.

    'Escenarios reales' exige ejecutar contra un proveedor real, y eso
    necesita credenciales. Este test existe para que nadie convierta la
    correccion de WI-91 en la afirmacion de que H9 esta cerrado: seria
    el mismo error que el que se acaba de corregir, en la direccion
    contraria.
    """

    def test_criterio_de_salida_sigue_declarando_el_hueco(self) -> None:
        addendum = _registro()
        texto = (
            str(addendum.get("valoracion_honesta", ""))
            + str(addendum.get("criterio_de_salida_h9", ""))
            + " ".join(str(v) for v in addendum.get("resumen", {}).values())
        )  # type: ignore[union-attr]
        marcas = ("proveedor real", "credenciales", "NO ejecutado", "sin ejecutar")
        assert any(m in texto for m in marcas), (
            "el registro ya no dice en ningun sitio que el criterio de "
            "salida ('escenarios reales') NO se ha ejecutado contra un "
            "proveedor. Con los 5 entregables cumplidos ese hueco es "
            "facil de perder de vista; no se puede perder."
        )
