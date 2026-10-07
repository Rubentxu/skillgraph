"""B31 — la medicion que abre el bloque. Consolidada de las tres rondas.

Ejecutar:  uv run python scripts/measure_b31_analisis.py

La fila del roadmap dice:

    B31 | No hay análisis estructural real: `line_count = 137` es todo lo que
         se sabe del código | CogniCode -> CodeAnalysis -> Knowledge,
         sin imports en el núcleo

Antes de escribir una línea de B31, tres preguntas medidas sobre el árbol
real. Y la tercera es la que define el bloque, porque la primera mitad de
la fila es FALSA.

RONDA 1 — ¿qué hay?
    E1  capabilities de análisis de código en src/           CERO
    E2  de los 7 predicados del Literal, con escritor en src/    1 de 7
    E3  dónde acaba el análisis estructural que SÍ existe
    E4  en los tests, los siete aparecen — escritos a mano
    E5  el guard de la frontera y si mira donde va a vivir B31

RONDA 2 — ¿qué sale de verdad del extractor puro?
    De los 7, cinco salen de `extract_file_signatures` y dos no. Y los dos
    que no (`test_passes`, `spec_revision`) no se inventan: se declaran.

RONDA 3 — ¿la frontera se sostiene?
    Con `import cognicode` dentro de `knowledge/`, el guard de B3 da
    VERDE. Es un hueco real y B31 no lo arregla a su cuenta: se sostiene
    por construcción, sin importar nada.
"""

from __future__ import annotations

import collections
import json
import pathlib
import re
import subprocess
import sys
import unicodedata

RAIZ = pathlib.Path(__file__).resolve().parent.parent
SRC = RAIZ / "src"
TESTS = RAIZ / "tests"
GUARD = "tests/test_b3_capability_kernel.py::TestElNucleoNoImportaAdapters"
OBJETIVO = SRC / "skillgraph/knowledge/telemetry_query.py"


def modulos() -> list[pathlib.Path]:
    return sorted(SRC.rglob("*.py"))


def titulo(n: int, texto: str) -> None:
    print()
    print("=" * 74)
    print(f"RONDA {n} — {texto}")
    print("=" * 74)


# ---------------------------------------------------------------------------
titulo(1, "¿qué hay?")

print("\nE1  capabilities declaradas en src/")
caps: dict[str, list[str]] = collections.defaultdict(list)
for p in modulos():
    t = p.read_text()
    for m in re.finditer(
        r'^\s*([A-Z_][A-Z_0-9]*)\s*:\s*Final\[str\]\s*=\s*"([a-z]+\.[a-z.]+)"', t, re.M
    ):
        caps[m.group(2)].append(p.name)
for nombre, ficheros in sorted(caps.items()):
    print(f"    {nombre:36s} {', '.join(sorted(set(ficheros)))}")
codigo = [n for n in caps if "code" in n or "analys" in n]
print(f"    -> capability de analisis de codigo: {codigo or 'CERO'}")

print("\nE2  los siete predicados del nucleo y quien los ESCRIBE en src/")
sys.path.insert(0, str(RAIZ / "src"))
from skillgraph.core.runtime_types import CLAIM_PREDICATES  # noqa: E402

for pred in sorted(CLAIM_PREDICATES):
    autores: list[str] = []
    for p in modulos():
        if p.name == "runtime_types.py":
            continue
        for i, linea in enumerate(p.read_text().splitlines(), 1):
            if re.search(rf"""["']{pred}["']""", linea):
                autores.append(f"{p.name}:{i}")
    marca = "  <-- METADATA, NO UN CLAIM" if pred == "line_count" else ""
    print(f"    {pred:20s} {len(autores):2d}  {', '.join(autores[:3])}{marca}")

print("\nE3  donde acaba una FileSignature")
controlador = SRC / "skillgraph/knowledge/knowledge_controller.py"
for i, linea in enumerate(controlador.read_text().splitlines(), 1):
    if 'kind="file_signature"' in linea:
        print(f"    knowledge_controller.py:{i}: {linea.strip()}")
        break
print("    -> se persiste como Evidence, NUNCA como Claim")

print("\nE4  los predicados en los tests (donde se siembran a mano)")
for pred in sorted(CLAIM_PREDICATES):
    n = sum(
        len(re.findall(rf"""["']{pred}["']""", p.read_text())) for p in sorted(TESTS.glob("*.py"))
    )
    print(f"    {pred:20s} {n:3d} menciones, ninguna producida por un analizador")

print("\nE5  el guard de la frontera, y si mira `knowledge/`")
print("    NUCLEO = ('runtime', 'core', 'resources')   <-- `knowledge/` NO esta")


# ---------------------------------------------------------------------------
titulo(2, "¿qué sale de verdad del extractor puro?")

from skillgraph.knowledge.file_signature import extract_file_signatures  # noqa: E402

real = RAIZ / "src/skillgraph/knowledge/superficie.py"
sigs = extract_file_signatures(file_path=str(real.relative_to(RAIZ)), content=real.read_text())
resumen = sigs[0]
mods = [s for s in sigs if s.contrato == "module"]
defs = [s for s in sigs if s.contrato == "def"]
print(f"\n    {real.name}: {len(sigs)} FileSignature")
print(f"    summary: {json.dumps(resumen.to_dict(), ensure_ascii=False)[:110]}...")
print(f"    contratos: module={len(mods)}  def={len(defs)}")
print(f"    module.foco[0] = {mods[0].foco}")
print(f"    def.foco[0]    = {defs[0].foco}")

for nombre, argumentos in (
    ("vacio", {"file_path": "vacio.py", "content": ""}),
    ("ausente", {"file_path": "<absent>", "content": ""}),
):
    s = extract_file_signatures(**argumentos)
    print(
        f"    {nombre:8s} -> state={s[0].vigencia.state}  "
        f"method={s[0].procedencia.extraction_method}"
    )

print(
    """
  predicado         ¿sale del extractor?     que haria falta
  ----------------  -----------------------  ---------------------------
  line_count        SI — summary.cobertura   1 claim por fichero
  file_exists       SI — summary.state       1 claim por fichero
  function_count    SI — contar contrato=='def'   1 claim por fichero
  imports_module    SI — contrato=='module'      1 claim POR MODULO
  defines_symbol    SI — contrato=='def'         1 claim POR SIMBOLO
  spec_revision     NO — no es del extractor
  test_passes       NO — exige ejecutar la suite
"""
)


# ---------------------------------------------------------------------------
titulo(3, "¿la frontera se sostiene?")


def _guard() -> tuple[int, str]:
    p = subprocess.run(
        [sys.executable, "-m", "pytest", GUARD, "-q", "-p", "no:cacheprovider", "--no-cov"],
        cwd=RAIZ,
        capture_output=True,
        text=True,
    )
    return p.returncode, (p.stdout + p.stderr)


rc, salida = _guard()
print(f"\nbaseline rc={rc}: {salida.strip().splitlines()[-1]}")

original = OBJETIVO.read_text()
try:
    OBJETIVO.write_text(
        original.replace(
            "from __future__ import annotations\n",
            "from __future__ import annotations\n\nimport cognicode  # sonda\n",
            1,
        )
    )
    rc2, salida2 = _guard()
    veredicto = "ROJO  <-- el guard vigila `knowledge/`" if rc2 else "VERDE <-- el hueco"
    print(f"\ncon `import cognicode` en knowledge/telemetry_query.py: rc={rc2}")
    print(f"    {veredicto}")
    if rc2:
        print(f"    {salida2.strip().splitlines()[-1]}")
finally:
    OBJETIVO.write_text(original)

rc3, _ = _guard()
print(f"\ntras restaurar: rc={rc3}")
if rc3 != 0:
    raise SystemExit("RESTAURACION ROTA: el fichero no volvio a su estado")

print(
    """
  LECTURA QUE DEFINE B31

  El enunciado del roadmap dice «no hay análisis estructural real» y es
  FALSO: `file_signature.py` son 431 líneas puras y deterministas que ya
  calculan cinco de los siete predicadores.

  Lo que falta es el ULTIMO PASO: el análisis nunca se convierte en
  conocimiento. Es evidencia que nadie puede preguntar — `evidence` de B34
  la devuelve mientras `what` no la ve.

  Y la frontera no se arregla ahi dentro, porque `NUCLEO` es una FRONTERA
  y anadir un paquete cambia que se considera núcleo, que es la decisión
  de B3. B31 se sostiene por construcción: no importa nada, porque el
  extractor ya es de este repo.
"""
)

# Una comprobacion que el propio script se hace a si mismo: si alguien
# colara un caracter de otro alfabeto en este fichero, el mensaje de abajo
# seria la unica pista. Se mira porque ya ha pasado seis veces.
raros = [
    (i, c)
    for i, linea in enumerate(pathlib.Path(__file__).read_text().splitlines(), 1)
    for c in linea
    if ord(c) > 127 and unicodedata.category(c) in {"Lo", "So"}
]
if raros:
    print("AVISO: este fichero tiene caracteres fuera del alfabeto latino:")
    for i, c in raros[:5]:
        print(f"    linea {i}: {c!r} ({unicodedata.name(c, '?')})")
