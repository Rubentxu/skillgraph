#!/usr/bin/env python3
"""Deriva el bump de SemVer de una release desde el historial de commits.

Por que existe
--------------
El proyecto declara COMO se deriva la version (AGENTS.md §12 es su dueno) y
esa declaracion **no la comprobaba nadie**: durante 47 releases el calculo se
hizo a mano. `tests/test_release_governance.py` ata la etiqueta a
`__version__`, que es una mitad; esta es la otra: que el numero sea el que
corresponde a los commits que hay entre una etiqueta y la siguiente.

Regla (AGENTS.md §12)
---------------------
    feat                            -> MINOR
    fix                             -> PATCH
    feat! / fix! / BREAKING CHANGE  -> MAJOR
    refactor,test,docs,spec,chore,
    style                           -> sin bump (no hay release)

    Salvedad 0.x: el proyecto esta en 0.x y, mientras lo este, un
    `BREAKING CHANGE` **no** obliga a saltar a 1.0.0. Se aplico tres veces
    (v0.7.0, v0.15.0, v0.16.2). Ver AGENTS.md §12.

Como leer un commit
-------------------
- `BREAKING CHANGE` en el **cuerpo** cuenta, no solo en el asunto: es la forma
  que los tres precedentes usaron.
- `!` antes de `:` en el asunto cuenta.
- El orden importa: un `feat!` es breaking, no feat. Un commit que llega a
  `v0.16.2` con 1 breaking y 5 fix es PATCH de la release anterior, porque el
  breaking no sube a MAJOR mientras se este en 0.x.

Trampa conocida
---------------
Contar **tipos de commit** y no **mensajes**: un `docs(changelog)` que menciona
«MAJOR» en su texto no convierte nada en breaking. Por eso se lee el marcador
`!:` y el footer, no palabras sueltas.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEMVER = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")

# Tipos que no mueven la version, por la regla de AGENTS.md §12.
NEUTRALES = frozenset({"refactor", "test", "docs", "spec", "chore", "style", "build", "ci"})

# Salvedad 0.x: mientras la version mayor sea 0, un breaking change no obliga a
# 1.0.0. Los tres precedentes estan en AGENTS.md §12 con su commit.
EXENCIÓN_0X = True


def _git(*args: str) -> str:
    return subprocess.run(
        ("git", *args), cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout


def tags() -> list[str]:
    """Etiquetas SemVer, ordenadas por version (no alfabeticamente)."""
    return sorted(
        (t for t in _git("tag", "--list", "v*").split() if SEMVER.match(t)),
        key=_version,
    )


def _version(tag: str) -> tuple[int, int, int]:
    return tuple(int(p) for p in SEMVER.match(tag).group(1, 2, 3))  # type: ignore[return-value]


def commits(tags_: list[str], tag: str) -> list[str]:
    """Asuntos y cuerpos de los commits que cnluyen `tag`, desde la anterior.

    El rango es `prev..tag` **inclusivo de `tag`**: el commit que etiqueta la
    release es parte de la release. Excluirlo haria que una release de un solo
    commit (`chore(release)`) pareciese vacia.
    """
    i = tags_.index(tag)
    rango = f"{tags_[i - 1]}..{tag}" if i else tag
    crudo = _git("log", "--format=%s%x00%b%x01", rango)
    salida: list[str] = []
    for rec in crudo.split("\x01"):
        rec = rec.strip()
        if not rec:
            continue
        asunto, _, cuerpo = rec.partition("\x00")
        salida.append(asunto + "\n" + cuerpo)
    return salida


def clasificar(asunto_cuerpo: str) -> str:
    """`breaking` | `feat` | `fix` | `neutro` | `desconocido` para un commit.

    `desconocido` existe para que un **tipo mal escrito** no se confunda con
    «no bumpea». `featt(cli):` es un `feat` que nadie va a leer como tal, y
    si cae en la rama de los neutros la release se pierde en silencio. Aqui
    se cuenta aparte, y el informe lo enseña.
    """
    asunto = asunto_cuerpo.split("\n", 1)[0]
    cuerpo = asunto_cuerpo.split("\n", 1)[1] if "\n" in asunto_cuerpo else ""

    # El orden importa: `feat!` es breaking, no feat.
    if re.search(r"\w+(\([^)]*\))?!:", asunto):
        return "breaking"

    # El footer de Conventional Commits es una LINEA que empieza por
    # `BREAKING CHANGE:` (o `BREAKING-CHANGE:`). Buscar la frase suelta en
    # el cuerpo es un falso positivo facil: un commit que *describe* un
    # breaking change —como el que documenta la salvedad 0.x— no es un
    # breaking change. MEDIDO: sin estaPrecision, el propio bloque que
    # escribio la clausula se contaba a si mismo como breaking.
    if re.search(r"^BREAKING[ -]CHANGE:?\s", cuerpo, re.M):
        return "breaking"

    m = re.match(r"^(\w+)(\(|:)", asunto)
    tipo = m.group(1) if m else ""
    if tipo == "feat":
        return "feat"
    if tipo == "fix":
        return "fix"
    if tipo in NEUTRALES:
        return "neutro"
    return "desconocido"


def resumen(tags_: list[str], tag: str) -> dict[str, int]:
    cuenta: dict[str, int] = {"breaking": 0, "feat": 0, "fix": 0, "neutro": 0, "desconocido": 0}
    for c in commits(tags_, tag):
        cuenta[clasificar(c)] += 1
    return cuenta


def bump_esperado(tags_: list[str], tag: str) -> str:
    """`MAJOR` | `MINOR` | `PATCH` | `""` (sin release) para la release `tag`."""
    c = resumen(tags_, tag)
    en_0x = _version(tag)[0] == 0

    if c["breaking"] and not (EXENCIÓN_0X and en_0x):
        return "MAJOR"
    if c["feat"]:
        return "MINOR"
    if c["fix"]:
        return "PATCH"
    return ""


def derivacion_esperada(tags_: list[str], tag: str) -> str | None:
    """La etiqueta que la regla produciria, o `None` si la regla dice no liberar.

    Se devuelve como etiqueta (`v0.16.21`) para poder compararla con la real.
    """
    i = tags_.index(tag)
    base = (0, 0, 0) if i == 0 else _version(tags_[i - 1])

    b = bump_esperado(tags_, tag)
    if b == "MAJOR":
        return f"v{base[0] + 1}.0.0"
    if b == "MINOR":
        return f"v{base[0]}.{base[1] + 1}.0"
    if b == "PATCH":
        return f"v{base[0]}.{base[1]}.{base[2] + 1}"
    return None


def coincide(tag: str, esperado: str) -> bool:
    return _version(tag) == _version(esperado)


def commits_desde_ultima(tags_: list[str]) -> list[str]:
    """Los commits posteriores a la etiqueta mas reciente, incluidos en HEAD.

    Es la direccion que se usa de verdad: no «que versionPublisho v0.16.12»
    sino «que version tengo que publicar ahora». Sin esto el script informa
    sobre historia y obliga a repetir su aritmetica a mano en el momento de
    la release, que es justo lo que se quiere evitar.
    """
    return _git("log", "--format=%s%x00%b%x01", f"{tags_[-1]}..HEAD").split("\x01")


def proxima_version(tags_: list[str]) -> tuple[str, dict[str, int], str]:
    """(etiqueta sugerida, recuento por tipo, clase de bump) para HEAD.

    Devuelve tambien la clase (`MINOR`/`PATCH`/`""`) porque «por que esa
    version» es la pregunta que se hace al releer el informe dentro de seis
    meses.
    """
    cuenta: dict[str, int] = {"breaking": 0, "feat": 0, "fix": 0, "neutro": 0, "desconocido": 0}
    for rec in commits_desde_ultima(tags_):
        rec = rec.strip()
        if rec:
            cuenta[clasificar(rec + "\n" + rec.partition("\x00")[2])] += 1

    base = _version(tags_[-1])
    en_0x = base[0] == 0

    if cuenta["breaking"] and not (EXENCIÓN_0X and en_0x):
        return f"v{base[0] + 1}.0.0", cuenta, "MAJOR"
    if cuenta["feat"]:
        return f"v{base[0]}.{base[1] + 1}.0", cuenta, "MINOR"
    if cuenta["fix"]:
        return f"v{base[0]}.{base[1]}.{base[2] + 1}", cuenta, "PATCH"
    return "", cuenta, ""


def cambios_rompedores_sin_marcar(tags_: list[str]) -> list[tuple[str, str]]:
    """Commits que hablan de un cambio rompedor SIN llevar el marcador.

    MEDIDO: los tres precedentes de la salvedad 0.x (`v0.7.0`, `v0.15.0`,
    `v0.16.2`) caen aqui. Anuncian el cambio en prosa —una viñeta que empieza
    por «Esto es BREAKING CHANGE»— y no con `!` ni con `BREAKING CHANGE:` al
    principio de una linea. Con el marcador, ninguna herramienta puede
    verlos; sin el, el bump se deduce mal y la exencion 0.x queda sin
    justification visible.

    Se reporta aparte, y **no cuenta** para el bump: la convención es la
    convención, y ensancharla para que estos casos cuenten seria rehacer la
    regla despues de ver los datos.
    """
    salida: list[tuple[str, str]] = []
    for tag in tags_:
        for c in commits(tags_, tag):
            asunto = c.split("\n", 1)[0]
            cuerpo = c.split("\n", 1)[1] if "\n" in c else ""
            if clasificar(c) == "breaking":
                continue  # este si va marcado
            if re.search(r"^BREAKING[ -]CHANGE:?\s", cuerpo, re.M):
                continue
            if re.search(r"break(ing|ed)", cuerpo, re.I) and re.search(
                r"rompedor|breaking change|incompatible|shims?", cuerpo, re.I
            ):
                salida.append((tag, asunto))
    return salida


def main() -> int:
    """Informe: el bump real de cada etiqueta frente al que dicta la regla."""
    tags_ = tags()
    print(f"{'etiqueta':<11} {'b/f/x/n':<16} {'regla':<7} {'esperada':<11} estado")
    print("-" * 62)
    divergentes = 0
    for tag in tags_:
        c = resumen(tags_, tag)
        b = bump_esperado(tags_, tag)
        esperado = derivacion_esperada(tags_, tag)
        conteo = f"{c['breaking']}/{c['feat']}/{c['fix']}/{c['neutro']}"
        if c["desconocido"]:
            conteo += f" (+{c['desconocido']} ?)"
        if esperado is None:
            estado = "SIN RELEASE (la regla no pide bump)"
        elif coincide(tag, esperado):
            estado = "ok"
        else:
            estado = "DIVERGE"
            divergentes += 1
        print(f"{tag:<11} {conteo:<16} {b or '-':<7} {esperado or '-':<11} {estado}")

    print()
    print(f"etiquetas: {len(tags_)} | divergentes de la regla: {divergentes}")
    if divergentes:
        print("Las divergentes NO se corrigen: son historia publicada. Ver AGENTS.md §12.")

    # Los `?` son commits cuyo tipo no está en la regla. MEDIDO: todos caen
    # en el tramo anterior a v0.14, y son `H3 slice N:`, `merge ...` y
    # `release(version):`, que preceden a los Conventional Commits. En la era
    # actual hay CERO. No se amplia NEUTRALES para que el contador quede a
    # cero: seria tapar la señal de que aquel tramo no sigue la regla.
    desconocidos = sum(resumen(tags_, t)["desconocido"] for t in tags_)
    if desconocidos:
        print()
        print(
            f"tipos fuera de la regla: {desconocidos} commit(s), todos en el tramo "
            "anterior a v0.14 (`H3 slice N:`, `merge ...`, `release(version):`, "
            "`audit`), que precede a los Conventional Commits. En la era actual: 0."
        )

    sugerida, cuenta, clase = proxima_version(tags_)
    print()
    print(f"== desde {tags_[-1]} hasta HEAD ==")
    print(
        f"  b/f/x/n/d: {cuenta['breaking']}/{cuenta['feat']}/{cuenta['fix']}/"
        f"{cuenta['neutro']}/{cuenta['desconocido']}"
    )
    if clase:
        print(f"  la regla pide {clase} -> {sugerida}")
    else:
        print("  la regla dice SIN BUMP: no hay release que emitir, se acumula")

    sin_marcar = cambios_rompedores_sin_marcar(tags_)
    if sin_marcar:
        print()
        print(f"== cambios rompedores SIN marcador: {len(sin_marcar)} commit(s) ==")
        print("  Los cuentan las tres veces que se aplico la salvedad 0.x.")
        print("  No cuentan para el bump: la convencion es la convencion.")
        for tag, asunto in sin_marcar:
            print(f"    {tag:<10} {asunto[:70]}")
        print("  Marcarlos cuesta un caracter (`!` en el asunto) y hace que la")
        print("  exencion 0.x quede justificada por algo mas legible que un")
        print("  recordatorio. Es heuristica: hay ruido. Ver AGENTS.md 12.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
