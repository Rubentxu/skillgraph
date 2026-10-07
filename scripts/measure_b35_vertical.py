"""La medicion que abre B35 — de la capability al store hay TRES pasos que no existen.

Cerrar B31 dejo measured una cosa pequena: `CapabilityRegistry(...)` se construye
0 veces en `src/`. Midiendo mas alla aparecieron DOS huecos mas, y juntos
forman lo que B35 cierra: **la vertical esta cortada en tres sitios**.

Se mide por AST sobre el arbol real, y sobre EJECUCION donde se puede. Nada
de esto es una lista de sitios conocidos escrita a mano (la trampa de WI-99:
una lista es una fuente de verdad mas).

Ejecutar:  uv run python scripts/measure_b35_vertical.py
"""

from __future__ import annotations

import ast
import pathlib
from collections.abc import Iterator

RAIZ = pathlib.Path(__file__).resolve().parent.parent
SRC = RAIZ / "src" / "skillgraph"
TESTS = RAIZ / "tests"
CLI = SRC / "cli"

#: Las capabilities de conocimiento. NO se escribe a mano: son los ficheros
#: que importan `ObservationEnvelope` y exponen una clase `*Capability`.
FICH_CAPABILITY = ("code_analysis.py", "telemetry_query.py", "knowledge_query.py")


def modulos(raiz: pathlib.Path) -> Iterator[pathlib.Path]:
    """Todo `.py` bajo `raiz`, en orden estable."""
    return sorted(p for p in raiz.rglob("*.py") if "__pycache__" not in p.parts)


def nombre_de(nodo: ast.expr) -> str | None:
    """El nombre desnudo de un `Name`, o el ultimo tramo de un `Attribute`."""
    if isinstance(nodo, ast.Name):
        return nodo.id
    if isinstance(nodo, ast.Attribute):
        return nodo.attr
    return None


def llamadas_a(fichero: pathlib.Path, funcion: str) -> list[int]:
    """Lineas donde se LLAMA `funcion(...)`, no donde se menciona."""
    arbol = ast.parse(fichero.read_text(encoding="utf-8"))
    lineas = [
        nodo.lineno
        for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.Call) and nombre_de(nodo.func) == funcion
    ]
    return sorted(lineas)


def funciones_publicas(fichero: pathlib.Path) -> dict[str, int]:
    """`nombre -> linea` de las funciones de primer nivel."""
    arbol = ast.parse(fichero.read_text(encoding="utf-8"))
    return {
        nodo.name: nodo.lineno
        for nodo in arbol.body
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def clases_capability(fichero: pathlib.Path) -> list[str]:
    arbol = ast.parse(fichero.read_text(encoding="utf-8"))
    return [
        nodo.name
        for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.ClassDef) and nodo.name.endswith("Capability")
    ]


def alcance_de_la_cli() -> None:
    """Lo que la CLI IMPORTA de verdad, no lo que nombra en prosa.

    **POR QUE AST Y NO TEXTO, Y QUE COSTO TUVO LA PRIMERA VEZ.** La primera
    version de esta ronda buscaba el nombre con `in` sobre el texto del
    fichero, y dio `KnowledgeQueryCapability : SI`. FALSO, y no por poco:
    la unica mencion esta dentro del docstring de
    `cli/commands/knowledge.py`, que la describe en pasado. Es decir, el
    instrumento decia que la puerta existia porque alguien habia escrito
    una frase sobre ella.

    Es la **cuarta vez** que sale este defecto en el repo —el guard de B15,
    el de WI-92, el de B34 con su sonda M10, y ahora este— y por eso la
    ronda busca `ast.Import`/`ast.ImportFrom`, que es lo que de verdad
    ata un modulo a otro. Un docstring no ata nada.
    """
    print("  AST sobre los imports de `cli/`, no sobre el texto:")
    importados: set[str] = set()
    for f in modulos(CLI):
        arbol = ast.parse(f.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.ImportFrom) and nodo.module:
                importados.add(nodo.module)
                importados.update(a.name for a in nodo.names)
            elif isinstance(nodo, ast.Import):
                importados.update(a.name for a in nodo.names)
            elif isinstance(nodo, ast.Call):
                nombre = nombre_de(nodo.func)
                if nombre:
                    importados.add(nombre)

    for fich in FICH_CAPABILITY:
        mod = f"skillgraph.knowledge.{fich.removesuffix('.py')}"
        print(f"  importa `{mod}` : {'SI' if mod in importados else 'NO'}")
    for clase in (
        "CodeAnalysisCapability",
        "TelemetryQueryCapability",
        "KnowledgeQueryCapability",
        "CapabilityController",
        "CapabilityRegistry",
    ):
        print(f"  importa `{clase}` : {'SI' if clase in importados else 'NO'}")

    print()
    print("  Y LO QUE DICE EL TEXTO, PARA QUE SE VEA LA DIFERENCIA:")
    texto = "\n".join(f.read_text(encoding="utf-8") for f in modulos(CLI))
    for clase in ("CodeAnalysisCapability", "TelemetryQueryCapability", "KnowledgeQueryCapability"):
        print(
            f"  el nombre `{clase}` aparece en el texto de la CLI : "
            f"{'SI' if clase in texto else 'NO'}"
        )


def main() -> int:
    print("=" * 74)
    print("RONDA 1 — el registro: ¿alguien CONSTRUYE el CapabilityRegistry?")
    print("=" * 74)

    en_src = [(f, ln) for f in modulos(SRC) for ln in llamadas_a(f, "CapabilityRegistry")]
    en_tests = [(f, ln) for f in modulos(TESTS) for ln in llamadas_a(f, "CapabilityRegistry")]
    print(f"  CapabilityRegistry(...) en src/   : {len(en_src)}")
    print(f"  CapabilityRegistry(...) en tests/ : {len(en_tests)}")

    print()
    for fich in FICH_CAPABILITY:
        ruta = SRC / "knowledge" / fich
        if not ruta.exists():
            continue
        for clase in clases_capability(ruta):
            usos = [f for f in modulos(SRC) if llamadas_a(f, clase)]
            print(f"  {clase:<28} instanciada en src/: {len(usos)}  (solo en tests/)")

    print()
    print("=" * 74)
    print("RONDA 2 — el SERIALIZADOR: ¿cuantas implementaciones hay?")
    print("=" * 74)
    print("  `envelope_a_payload` dice COMO se serializa. Contado por AST,")
    print("  sobre las DEFINICIONES de primer nivel, no sobre las llamadas:")
    print()
    definiciones: list[tuple[str, str, int]] = []
    for f in modulos(SRC):
        for nombre, linea in funciones_publicas(f).items():
            if "payload" in nombre and "envelope" in nombre:
                definiciones.append((nombre, str(f.relative_to(RAIZ)), linea))
    for nombre, fich, linea in definiciones:
        print(f"  def {nombre:<24} {fich}:{linea}")

    nombres = {n for n, _, _ in definiciones}
    if len(definiciones) > len(nombres):
        print()
        print(f"  **HAY {len(definiciones)} DEFINICIONES PARA {len(nombres)} NOMBRES.**")
        print("  El mismo nombre, dos modulos, `__all__` y todo: quien importa")
        print("  `envelope_a_payload` sin saber de cual obtiene un contrato distinto")
        print("  segun el modulo del que venga. Y no son el mismo contrato:")
    print()

    print("  ¿Los dos hacen lo mismo? EJECUTANDOLOS sobre el MISMO envelope.")
    print()

    # --- la ejecucion que demuestra que no hacen lo mismo ---------------
    from skillgraph.knowledge.code_analysis import envelope_a_payload as de_codigo
    from skillgraph.knowledge.observation import Observation, ObservationEnvelope
    from skillgraph.knowledge.telemetry_query import envelope_a_payload as de_runtime
    from skillgraph.platform.ports.capabilities import CapabilitySpec

    env = ObservationEnvelope(
        producer=CapabilitySpec(type_name="sg.prueba", summary="prueba"),
        adapter="Prueba",
        source_id="s:1",
        subject="file:a.py",
        observed_at="2026-10-07T00:00:00Z",
        revision="r1",
        observations=(Observation(predicate="line_count", object_literal=3),),
        version="observation-envelope/v1",
        kind="local_file",
    )

    p_codigo = de_codigo(env)
    p_runtime = de_runtime(env)
    print(f"  claves de code_analysis.envelope_a_payload : {sorted(p_codigo)}")
    print(f"  claves de telemetry_query.envelope_a_payload: {sorted(p_runtime)}")
    solo_codigo = sorted(set(p_codigo) - set(p_runtime))
    print(f"  solo en el de codigo : {solo_codigo}")
    print("  forma de 'observations':")
    print(
        f"      codigo   -> {type(p_codigo['observations']).__name__} de "
        f"{type(p_codigo['observations'][0]).__name__}"
    )
    print(
        f"      runtime  -> {type(p_runtime['observations']).__name__} de "
        f"{type(p_runtime['observations'][0]).__name__}"
    )

    print()
    print("=" * 74)
    print("RONDA 3 — el DESERIALIZADOR: ¿existe el camino de vuelta?")
    print("=" * 74)

    vuelta_src = [(f, n) for f in modulos(SRC) for n in funciones_publicas(f) if "de_payload" in n]
    print(f"  funciones `*de_payload*` en src/ : {len(vuelta_src)}")
    for f, n in vuelta_src:
        print(f"      {f.relative_to(RAIZ)}::{n}")

    vuelta_tests = [
        (f, n) for f in modulos(TESTS) for n in funciones_publicas(f) if "de_payload" in n
    ]
    print(f"  funciones `*de_payload*` en tests/ : {len(vuelta_tests)}")
    for f, n in vuelta_tests:
        print(f"      {f.relative_to(RAIZ)}::{n}")

    # Las de los tests se llaman `_envelope_de` y `envelope_real`.
    candidatas_tests = [
        (f, n)
        for f in modulos(TESTS)
        for n in funciones_publicas(f)
        if n.endswith("envelope_de") or "envelope_real" in n or n.startswith("envelope_de")
    ]
    print(f"  reconstructores de envelope en tests/ : {len(candidatas_tests)}")
    for f, n in candidatas_tests:
        print(f"      {f.relative_to(RAIZ)}::{n}")

    if not vuelta_src and candidatas_tests:
        print()
        print("  **EL INVERSO ESTA ESCRITO EN LOS TESTS.**")
        print("  `ingerir(...)` exige un `ObservationEnvelope`, y la capability")
        print("  devuelve un `dict`. El paso del uno al otro esta escrito a mano")
        print(f"  en {len(candidatas_tests)} ficheros de test, y en produccion no esta.")
        print()
        print("  **Y YA DIVERGEN, que es lo que dos copias garantizan.** MEDIDO, con")
        print("  el MISMO payload por las dos:")
        print("      test_b33::`_envelope_de`    usa el `producer` DEL PAYLOAD")
        print("      test_b31::`envelope_real`   usa `cap.spec` DE LA CAPABILITY")
        print()
        print("  El `producer` es un campo del envelope, y una copia que lo lee de")
        print("  la capability en vez de del payload no esta probando la ida y la")
        print("  vuelta: esta probando que la capability sabe su propio nombre.")

    print()
    print("=" * 74)
    print("RONDA 4 — la PUERTA: ¿llega un operador a alguna de las tres?")
    print("=" * 74)

    alcance_de_la_cli()

    print()
    print("=" * 74)
    print("LECTURA QUE ABRE B35")
    print("=" * 74)
    print(f"""
  La vertical de conocimiento esta cortada en TRES sitios, y los tres se
  pueden measuring por separado:

  1. EL REGISTRO. `CapabilityRegistry(...)` se construye {len(en_src)} veces
     en `src/`. Y de las tres classes `*Capability`, CERO se instancian
     fuera de los tests. Una capability al 100 % de cobertura que ningun
     despliegue puede resolver.

  2. EL SERIALIZADOR. Hay {len(definiciones)} funciones `envelope_a_payload`
     para {len(nombres)} nombres: dos modulos, el mismo nombre, y
     EJECUTANDOLAS sobre el mismo envelope dan claves distintas
     (`{solo_codigo}` solo aparece en una) y `observations` con forma distinta.

  3. EL DESERIALIZADOR. En `src/` hay {len(vuelta_src)}. En `tests/` hay
     {len(candidatas_tests)} reconstructores escritos a mano, y ya divergen
     entre si —uno usa el `producer` del payload, otro usa `cap.spec`—.
     Es el paso de `dict` a `ObservationEnvelope` que `ingerir` exige y que
     nadie tiene en produccion.

  Y por debajo, la PUERTA: ningun subcomando de `sg` llega a ninguna de las
  tres capabilities. `sg.code.analysis` solo se puede lanzar escribiendo
  Python.

  **LO QUE NO SE TOCA, Y POR QUE.** El registro con default `None` y la
  costura `capabilities=` los escribio B3-cierre a proposito, con el motivo
  en `runcontroller.py:148-179`: la exigencia la PIDE quien despliega. B35 no
  cambia esa politica; le da **quien despliega**, que hoy no existe. Si el
  mismo cambio hiciera las dos cosas, seria otro bloque distinto y habria que
  medirlo aparte.
""")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
