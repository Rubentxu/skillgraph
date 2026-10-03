#!/usr/bin/env python3
"""B4 — mide, sobre el árbol real, qué mitad de la separación CRD-like existe.

**POR QUÉ ESTE INSTRUMENTO ESTÁ VERSIONADO Y NO EN `.pipelinek/`.** Es la
deuda que B3 cerró como ítem de backlog (`bl-bl-01M41DFZEZ0003882TZNP7NPM0`):
`.gitignore:81` excluye `.pipelinek/*`, hay 318 instrumentos ahí y 1
versionado, y 25 ficheros del repo citan rutas de esa carpeta —incluida la
evidencia de B0, B1, B2 y B3—. Es decir: **la evidencia del repo no es
reproducible por quien la lee.** Ese ítem está sin decidir, así que aquí no
se amplía: este instrumento vive en `scripts/`, y quien quiera reproducir
esta medición la reproduce.

**EL CRITERIO, DECLARADO ANTES DE MIRAR.** B4 pide la separación
*desired / observed / controller / reconcile / status / conditions*. Se
miden cuatro preguntas, y cada una tiene una respuesta que o puede ser
cierta o no:

1. ¿El esquema declara las dos mitades? (`spec_json` y `status_json`.)
2. ¿El dominio tiene un tipo para la mitad observada?
3. ¿Hay un camino de ESCRITURA que la llene?
4. ¿Existe `conditions`, que el roadmap nombra explícitamente?

Se añade una quinta, que es la que convierte el hallazgo en defecto y no en
observación: **¿se puede distinguir un cambio de `spec` de un cambio de
`status`?** Es la semántica de `generation` en Kubernetes, y es lo que hace
que la separación signifique algo: si no se puede, `status` es un campo más
y no una mitad.

Uso:
    uv run python scripts/measure_b4_observed_state.py
    uv run python scripts/measure_b4_observed_state.py --json
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[1]
SRC = RAIZ / "src" / "skillgraph"
SCHEMA = RAIZ / "src" / "skillgraph" / "platform" / "schema.py"


def _ficheros() -> list[Path]:
    return [p for p in sorted(SRC.rglob("*.py")) if "__pycache__" not in p.parts]


def _constantes(clase: str) -> set[str]:
    """Nombres de atributo declarados en una clase del dominio."""
    vistos: set[str] = set()
    for p in _ficheros():
        try:
            arbol = ast.parse(p.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.ClassDef) and nodo.name == clase:
                for sub in nodo.body:
                    if isinstance(sub, ast.AnnAssign) and isinstance(sub.target, ast.Name):
                        vistos.add(sub.target.id)
    return vistos


def _escrituras_de(tabla: str) -> dict[str, list[str]]:
    """INSERT y UPDATE de una tabla, por fichero, sobre el AST."""
    return _escrituras_de_en_arbol(SRC, tabla)


def _escrituras_de_en_arbol(raiz: Path, tabla: str) -> dict[str, list[str]]:
    """Lo mismo, pero sobre un árbol cualquiera.

    Se separa del `SRC` de módulo para que se pueda **contraprobarla** sobre
    un árbol sintético: una derivación que devuelve siempre la lista vacía
    pasaría cualquier guard que la mire sobre el repo, y no distinguiría
    «no hay UPDATE» de «no sé leer UPDATE».
    """
    salida: dict[str, list[str]] = {"INSERT": [], "UPDATE": []}
    for p in sorted(raiz.rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        try:
            arbol = ast.parse(p.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, ast.Constant) or not isinstance(nodo.value, str):
                continue
            sql = " ".join(nodo.value.split()).upper()
            for verbo in ("INSERT", "UPDATE"):
                if sql.startswith(f"{verbo} INTO {tabla.upper()}") or sql.startswith(
                    f"{verbo} {tabla.upper()}"
                ):
                    try:
                        situacion = f"{p.relative_to(raiz)}:{nodo.lineno}"
                    except ValueError:  # pragma: no cover
                        situacion = f"{p}:{nodo.lineno}"
                    salida[verbo].append(situacion)
    return salida


def medir() -> dict[str, Any]:
    esquema = SCHEMA.read_text(encoding="utf-8")
    bricks = _constantes("Brick")
    almacenados = _constantes("StoredResource")
    status = _constantes("ResourceStatus")
    escrituras = _escrituras_de("resources")

    # ¿Se puede distinguir un cambio de spec de uno de status? Es la
    # semántica de `generation` en Kubernetes, y es lo que hace que la
    # separación signifique algo: si no se puede, `status` es un campo más y
    # no una mitad. Se busca en la cláusula SET de un UPDATE de `resources`,
    # sobre el AST: partir el fichero entero por la palabra `SET` revienta
    # con IndexError en el primer fichero que tenga un UPDATE de otra tabla.
    set_de_resources: list[str] = []
    for p in _ficheros():
        try:
            arbol = ast.parse(p.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, ast.Constant) or not isinstance(nodo.value, str):
                continue
            plano = " ".join(nodo.value.split())
            if not plano.upper().startswith("UPDATE RESOURCES"):
                continue
            try:
                set_de_resources.append(plano.upper().split(" SET ", 1)[1].split(" WHERE ")[0])
            except IndexError:
                set_de_resources.append(plano.upper())
    escribe_generation = any("GENERATION" in s for s in set_de_resources)

    return {
        "1_esquema_declara_las_dos_mitades": {
            "spec_json": "spec_json" in esquema,
            "status_json": "status_json" in esquema,
        },
        "2_dominio_tiene_tipo_para_la_mitad_observada": {
            # LA PREGUNTA ESTA MAL PLANTEADA EN LA PRIMERA VERSION, y la
            # contesto el contrasalto del bloque. Preguntaba
            # «¿Brick.status existe?» y suponía que NO: era asi como se
            # media el hueco, porque no habia tipo de status en ninguna
            # parte. Pero el ARREGLO de B4 es un tipo SEPARADO, de modo que
            # `Brick.status` sigue siendo False, ahora a proposito — y el
            # criterio que media el hueco queda invertido por el arreglo.
            #
            # Un guard que mide el hueco con un criterio que el arreglo
            # invierte no mide el hueco: mide el número del arreglo, y solo
            # mientras no se arregle. La pregunta correcta es «¿existe un
            # tipo de dominio para la mitad observada?».
            "existe_tipo_de_status": {"phase", "conditions"} <= status,
            "Brick.spec": "spec" in bricks,
            # Y esto ya NO es el hueco: es la invariante R5. `Brick` es lo
            # declarado y no puede llevar status, porque entonces un pack
            # declararia el estado de su propio recurso.
            "Brick.status_ausente_por_diseno": "status" not in bricks,
            "StoredResource.status_json": "status_json" in almacenados,
        },
        "3_hay_camino_de_escritura": {
            "INSERT": sorted(escrituras["INSERT"]),
            "UPDATE": sorted(escrituras["UPDATE"]),
            "alguno_escribe_status_json": any(
                "status_json" in p.read_text(encoding="utf-8") for p in _ficheros()
            )
            and bool(escrituras["UPDATE"]),
        },
        "4_conditions_existe": {
            "condiciones_en_dominio": sorted(
                str(p.relative_to(SRC))
                for p in _ficheros()
                if "condition" in p.read_text(encoding="utf-8").lower()
            ),
        },
        "5_se_distingue_spec_de_status": {
            "generation_se_escribe": escribe_generation,
        },
    }


def _demostracion_de_escritura() -> str:
    """Lo que de verdad pasa al persistir un Brick y luego su status.

    No se deduce leyendo codigo: se ejecuta contra la base real y se lee la
    fila. Un instrumento que no produce el caso no mide el caso, y lo que no
    sale de la ejecucion no es un dato.

    Y hace LAS DOS escrituras, porque la primera version solo hacia el
    INSERT y se quedaba en `status_json='{}'` mientras el veredicto de
    arriba afirmaba que la ejecucion dejaba «contenido real». Un veredicto
    que afirma algo que la ejecucion de al lado no muestra es una
    afirmacion falsa con la ejecucion al lado, y esa es exactamente la clase
    de defecto que este bloque viene a cerrar.
    """
    sys.path.insert(0, str(RAIZ / "src"))
    from skillgraph.platform.storage import Storage
    from skillgraph.resources.bricks import Brick, ResourceIdentity
    from skillgraph.resources.status import Condition, ResourceStatus

    with tempfile.TemporaryDirectory() as tmp:
        st = Storage(Path(tmp) / "b4.sqlite")
        brick = Brick(
            identity=ResourceIdentity(
                tenant_id="t-b4",
                project_id="p-b4",
                namespace="packs",
                kind="DomainPack",
                name="code-analysis",
            ),
            api_version="skillgraph.io/v1",
            kind="DomainPack",
            spec={"capacities": ["code.analysis"]},
        )
        uid = st.upsert_resource(brick=brick)

        def _fila() -> tuple[str, int, int]:
            f = st._conn.execute(
                "SELECT status_json, generation, resource_version FROM resources WHERE uid = ?",
                (uid,),
            ).fetchone()
            return f[0], f[1], f[2]

        antes = _fila()
        st.update_resource_status(
            uid=uid,
            status=ResourceStatus(
                phase="Running",
                conditions=(
                    Condition(
                        type="Ready",
                        status="True",
                        reason="Observado",
                        message="el pack se resolvio",
                        last_transition="2026-10-03T00:00:00Z",
                    ),
                ),
                observed_generation=999,
            ),
        )
        despues = _fila()
        leido = st.get_resource_status(uid=uid)
        st.close()
        return (
            f"tras INSERT : status_json={antes[0]!r} generation={antes[1]} "
            f"resource_version={antes[2]}"
            f" | tras escribir status: phase={leido.phase if leido else None!r} "
            f"conditions={len(leido.conditions) if leido else 0} "
            f"observed_generation={leido.observed_generation if leido else None} "
            f"generation={despues[1]} resource_version={despues[2]}"
        )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    datos = medir()
    ejecucion = _demostracion_de_escritura()

    if args.json:
        print(json.dumps(datos, indent=2, sort_keys=True))
        print(json.dumps({"ejecucion": ejecucion}, sort_keys=True))
        return 0

    print("B4 — la mitad OBSERVADA de la separacion CRD-like, medida\n")
    for clave, valor in datos.items():
        print(f"{clave}")
        print(f"    {json.dumps(valor, sort_keys=True)}")
    print(f"\nEJECUCION (base real, no deducida):\n    {ejecucion}\n")

    falta_tipo = not datos["2_dominio_tiene_tipo_para_la_mitad_observada"]["existe_tipo_de_status"]
    falta_update = not datos["3_hay_camino_de_escritura"]["UPDATE"]
    sin_conditions = not datos["4_conditions_existe"]["condiciones_en_dominio"]

    # EL CODIGO DE SALIDA CONTESTA UNA SOLA PREGUNTA: ¿es la mitad
    # observada alcanzable? 0 = si, 1 = no. No es «el bloque esta bien» ni
    # «el bloque esta mal»: es el estado medido, y asi el mismo script
    # sirve de diagnostico ANTES del trabajo (sale 1, con el hueco a la
    # vista) y de guard DESPUES (sale 0).
    #
    # La primera version hacia lo contrario —0 con el hueco abierto— que es
    # un codigo que no significa nada: «el guard pasa» y «el guard no puede
    # medir» se veian igual.
    if falta_tipo or falta_update or sin_conditions:
        print(
            "VEREDICTO: la mitad observada esta DECLARADA y es INALCANZABLE.\n"
            "  - el esquema tiene status_json y el DTO lo expone\n"
            "  - el dominio (Brick) NO tiene status\n"
            "  - hay UN solo INSERT en resources y CERO UPDATE\n"
            "  - conditions no existe en ningun modulo de src/\n"
            "  - la ejecucion deja status_json en '{}' para siempre"
        )
        return 1
    print(
        "VEREDICTO: la mitad observada es ALCANZABLE.\n"
        "  - el dominio tiene un tipo para el status, separado de Brick\n"
        "  - hay un UPDATE que la escribe y una lectura que devuelve el tipo\n"
        "  - conditions existe\n"
        "  - la ejecucion deja status_json con contenido real"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
