"""Cuantos instrumentos cita el repo y cuantos puede reproducir un clon.

Ejecutar:  uv run python scripts/measure_citas_no_versionadas.py

QUE MIDE, Y POR QUE NO ES DE FORMA

La pregunta es «¿lo que este repo afirma que midio, se puede volver a
medir?». Y se mide **ejecutando `git ls-files`**, que es la unica fuente
de lo que un clon trae: si un instrumento no esta en esa lista, no existe
para quien clonee, por mucho que su ruta este escrita en 43 sitios.

No sale de comparar dos listas escritas a mano —el error de WI-106, un
guard que compara contra su propia copia—. Las dos listas que compara son
`git ls-files` y lo que de verdad hay en el arbol.

El mecanismo del hueco: `.gitignore:81` excluye `.pipelinek/*` salvo
`.gitkeep`, mientras `evidence/` SI se versiona —el propio repo tiene
versionado `evidence/pipelinek/expansion-3625a30/journal.sqlite`—. Luego
la convencion declarada es «la evidencia es un entregable», y las citas que
se apoyan en `.pipelinek/` apuntan a algo que no viaja.

ANTES DE MIGRAR B31..B34

    instrumentos citados              43
    existen en este arbol             40
    VIAJAN EN GIT                      0

Y de esos 43, **tres ni siquiera existen en la maquina que los escribio**
(`b2_concurrency_child.py`, `hijo.py`, `wi102_muts/m1..m6.py`): son citas
a nada, que es exactamente el defecto que `citas_rotas()` de B1 pretendia
cerrar — y que vive, irónicamente, en `.pipelinek/b1_verdict.py`, es decir
tambien sin versionar.

LO QUE ESTO YA NO ES UN DEFEECTO

B31..B34 migraron sus instrumentos a `scripts/`, que es donde ya estaban
los 18 anteriores y donde si se versionan. Las 36 citas restantes son
trabajo abierto y se declaran como tal, con esta cifra al lado: dejarlas
es una decision, no un olvido.
"""

from __future__ import annotations

import pathlib
import re
import subprocess

RAIZ = pathlib.Path(__file__).resolve().parent.parent
PATRON = re.compile(r"\.pipelinek/([A-Za-z0-9_./-]+\.py)")


def versionados() -> set[str]:
    fuera = subprocess.run(
        ["git", "ls-files"], cwd=RAIZ, capture_output=True, text=True, check=True
    )
    return set(fuera.stdout.split())


def citadores() -> list[pathlib.Path]:
    versionados_ = versionados()
    salida: list[pathlib.Path] = []
    for rel in sorted(versionados_):
        p = RAIZ / rel
        if p.suffix in {".py", ".md", ".yaml", ".yml", ".toml", ".kts"} and p.is_file():
            try:
                texto = p.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if ".pipelinek/" in texto:
                salida.append(p)
    return salida


def main() -> int:
    ficheros = citadores()
    print("=" * 74)
    print("CITAS A INSTRUMENTOS QUE UN CLON NO TIENE")
    print("=" * 74)

    citadas: dict[str, list[str]] = {}
    for p in ficheros:
        rel = str(p.relative_to(RAIZ))
        for m in PATRON.finditer(p.read_text(encoding="utf-8")):
            citadas.setdefault(m.group(0), []).append(rel)

    en_disco = {c: (RAIZ / c).is_file() for c in citadas}
    versionadas = {c: c in versionados() for c in citadas}

    print(f"\nficheros versionados que citan .pipelinek/*.py : {len(ficheros)}")
    print(f"instrumentos distintos citados                 : {len(citadas)}")
    print(f"de los cuales existen en este arbol             : {sum(en_disco.values())}")
    print(f"de los cuales viaja en git                      : {sum(versionadas.values())}")

    print("\n--- detalle ---")
    print(f"{'instrumento':46s} {'disco':>6s} {'git':>5s}  citas")
    for c in sorted(citadas):
        print(
            f"{c:46s} {'si' if en_disco[c] else 'NO':>6s} "
            f"{'si' if versionadas[c] else 'NO':>5s}  {len(citadas[c])}"
        )

    print(
        f"""
  LECTURA

  {sum(versionadas.values())}/{len(citadas)} de los instrumentos citados viajan en git.

  Es decir: **la evidencia de este repo no es reproducible desde un clon**,
  y las citas no son decorativas — en `evidence/` y en `ROADMAP.md` son la
  RAZON de por que se afirma lo que se afirma. Una de las tres reglas que
  este repo se impone es «medir antes de escribir una línea»; el
  instrumento con el que se midió es lo primero que se pierde.

  Y el lado ironico lo da el propio `.gitignore`: su comentario explica que
  se excluye el CONTENIDO y no el directorio, con un motivo bueno —que la
  receta documentada no era ejecutable fuera de este árbol—, y al hacerlo
  deja fuera los `.py` de medicion, que no son artefactos de ejecucion de
  PipelineK sino entregables del proyecto.

  LO QUE NO SE HACE AQUI, y por que

  Des-ignorar `.pipelinek/*.py` no es una linea: son decenas de scripts y
  algunos leen rutas absolutas a `/var/mnt/DiscoChino2-fast/...`, que es la
  maquina de quien los escribio. Versionarlos sin arreglar eso persistiria
  scripts que no corren en ningun otro sitio — una forma de reproducibilidad
  que es peor que su ausencia, porque parece que la hay.

  Es un workitem con nombre, y por ahora lo que corresponde es DEJARLO
  ESCRITO con la medicion al lado.
"""
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
