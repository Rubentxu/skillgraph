#!/usr/bin/env python3
"""B29 — autocomprobacion del instrumento de vigencia: cinco sondas, cinco propiedades.

**POR QUE EXISTE UN HARNESS QUE ROMPE EL CODIGO A PROPOSITO.** Un guard que
solo sabe ponerse en verde no esta probado: `measure_b29_vigencia.py` podria
estar contando el nombre de una columna y devolver «0/5 ABIERTAS» sin que
ninguna de las cinco propiedades sea certaina. Este script **aplica una sonda
que deliberadamente rompe una propiedad, comprueba que el guard se pone rojo, y
restaura el arbol**.

Es el mismo argumento que `mutate_b28_autoridad.py`, que `mutate_b27_conflictos.py`
y que el M2 de WI-110: una derivacion que devolviera siempre la lista vacia pasaria
todos los tests en verde porque no mediria nada.

# QUE SE ROMPE EN CADA SONDA, Y POR QUE ESA PROPIEDAD

    M1  LA VENTANA EN EL ADT   -> `Claim` deja de declarar `valid_from/until_revision`
    M2  LA CADENA DE SUPERSESION-> `claims` deja de tener `supersedes_claim_id`
    M3  LA CONSULTA POR REVISION-> `Storage` deja de exponer `claims_at_revision`
    M4  LA CADUCIDAD EN HEAD   -> nada caduca, y un cambio vuelve a ser conflicto
    M5  LA VIGENCIA POR REVISION -> nada es vigente fuera de HEAD (CONTRA SALTO DEL GUARD)

**M4 Y M5 SE TOCAN EL MISMO `if` Y NO SON INTERCAMBIABLES, Y ESE ES EL PUNTO.**
M4 rompe la primera mitad de P5 —«las ventanas disjuntas NO son conflicto»— y por
eso abre P4. M5 deja HEAD **intacto** y rompe la segunda mitad —«las solapadas SI
lo son»—, y por eso abre P5 y **no** P4. Un arreglo que comprase «cero conflictos»
apagando el detector pasaria P4 en verde; M5 es lo que demuestra que el
instrumento no compra eso.

# LAS SONDAS SON MULTI-FICHERO, Y POR QUE — QUE ES LO NUEVO DE ESTE HARNESS

Las cinco de B28 apuntaban a un unico modulo. Aqui **no se puede**, y la razon
enseña algo sobre lo que se esta midiendo:

- **M1 y M2 son preguntas de EXISTENCIA.** P1 mira `Claim.__dataclass_fields__` y
  P2 mira `PRAGMA table_info(claims)`. La sonda honesta es **renombrar el
  identificador de punta a punta** —el campo del ADT, el nombre de la columna, el
  `ALTER TABLE` de la migracion, la lectura del mapper y el `INSERT`—, de modo
  que el arbol **sigue cargando y las otras cuatro preguntas siguen midiendo**.
  La sonda ingenua —borrar la columna— hace que el mapper lea una columna
  inexistente y el instrumento reviente con `sqlite3.OperationalError`. Esa
  sonda estaria «cazada» por un crash, que no es la propiedad rota sino el arbol
  roto: es el error 32 de B26 y el error 32 de WI-113, por tercera vez.
- **M3 se queda en un fichero** y por eso **no** se aplica el mismo criterio:
  renombrar el metodo a `_claims_at_revision` lo saca de `Storage`, que es
  exactamente la pregunta de P3 («¿se puede PREGUNTAR por una revision?»), y no
  revienta nada porque el delegador solo la invoca en runtime.

# LAS ANCLAS SON REGEX, Y POR QUE NO TEXTO LITERAL

La version de B28 anclaba con texto exacto y **`ruff format` las desanclo todas**.
Aqui las cinco sondas usan patron. Lo que se muta es la **semantica** —el nombre
del campo, el `return`, el `if`—, y eso no cambia porque alguien parta la linea
en otro sitio.

# EL GUARD DE SINTAXIS

Una sonda que rompe la sintaxis hace que el guard se ponga rojo por la razon
equivocada. Este harness **importa los modulos tocados antes de juzgar**, y una
sonda que no cargue se clasifica `ROTA`: no cuenta ni como cazada ni como
inocua, porque seria un fallo del harness. Solo se acepta `CAZADA` cuando el
arbol carga y el guard se pone rojo **por la propiedad**.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path


def _cargar_harness_comun() -> object:
    """Carga `scripts/mutation_harness.py` por ruta.

    R1.E: este harness deja de ser una copia mas. Los estados y el
    restaurador vienen del modulo comun; lo que queda aqui es lo que es de
    B29: las sondas, que son multi-fichero y con regex, y las preguntas.

    Se registra en `sys.modules` porque `@dataclass(slots=True)` busca el
    espacio de nombres del modulo ahi y sin registro falla con un
    `AttributeError` en la importacion.
    """
    spec = importlib.util.spec_from_file_location(
        "mutation_harness", Path(__file__).resolve().parent / "mutation_harness.py"
    )
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    sys.modules["mutation_harness"] = modulo
    spec.loader.exec_module(modulo)
    return modulo


_h = _cargar_harness_comun()

# La `Sonda` de este fichero es multi-fichero y con regex, y la del modulo
# comun es de un solo fichero. Son dos cosas distintas con el mismo nombre de
# dominio, asi que la del comun entra con otro nombre en vez de tapar esta.
SondaSimple = _h.Sonda
Restaurador = _h.Restaurador
Veredicto = _h.Veredicto

#: Lo que este harness llamaba `ROTA`: una sonda que no midio nada. En el
#: modulo comun ese estado se llama `MUTACION_INVALIDA`, y el alias se queda
#: porque el nombre viejo aparece en la salida y en los receipts.
ROTA = Veredicto.MUTACION_INVALIDA

RAIZ = Path(__file__).resolve().parent.parent

SRC = RAIZ / "src" / "skillgraph"
INSTRUMENTO = RAIZ / "scripts" / "measure_b29_vigencia.py"
PY = RAIZ / ".venv" / "bin" / "python"

CAZADA = "CAZADA"
INOCUA = "INOCUA"
ROTA = "ROTA"
#: El instrumento no pudo terminar: el arbol esta roto, y eso ES un fallo de
#: las propiedades, no una sonda que no mordio.
CAIDA = -1

#: Todo lo que hay que importar para saber que el arbol SIGUE CARGANDO. No
#: hace falta que sea el arbol entero: basta con que caigan los modulos que las
#: sondas tocan, que es donde un fallo de sintaxis o un nombre-colonia roto
#: reventaria.
MODULOS = (
    "skillgraph.knowledge.graph",
    "skillgraph.platform.storage",
    "skillgraph.platform.schema",
    "skillgraph.platform.migrations",
    "skillgraph.platform.knowledge_claims",
    "skillgraph.platform.knowledge_conflicts",
    "skillgraph.platform.knowledge_mappers",
    "skillgraph.platform.knowledge_repository",
)


@dataclass(frozen=True, slots=True)
class Cambio:
    """Una sustitucion regex en UN fichero.

    `fichero` es relativo a `RAIZ`. `viejo` es **regex**, `nuevo` admite
    backreferences `\\g<1>` porque se expande con `Match.expand()`.

    `cuantas` es el numero exacto de apariciones que se sustituyen, y **`-1`
    significa «todas, pero al menos una»**. La distincion no es cosmetica: la
    primera version de M2 renombraba `supersedes_claim_id` con `count=1`, y
    como el identificador aparece DOS veces en casi cada fichero —la columna y
    su lectura, el campo y su invariante—, la sonda dejaba el `__post_init__`
    leyendo `self.supersedes_claim_id` sobre un Claim que ya no lo tenia. La
    sonda «cazada» por un `AttributeError` y no por la propiedad: el mismo
    crash-con-razon-equivocada de las sondas de una sola columna.
    """

    fichero: str
    viejo: str
    nuevo: str
    cuantas: int = 1


@dataclass(frozen=True, slots=True)
class Sonda:
    """Una mutacion y la propiedad que se supone que rompe."""

    nombre: str
    que_rompe: str
    cambios: tuple[Cambio, ...]
    p_abiertas_minimo: int = 1


#: Las cinco sondas.
SONDAS: tuple[Sonda, ...] = (
    # ------------------------------------------------------------------ M1
    # P1 mira `Claim.__dataclass_fields__`. Se renombra el campo del ADT Y sus
    # dos lecturas (el mapper que la reconstruye y el INSERT que la guarda), de
    # modo que el arbol carga y solo P1 se abre: las columnas siguen ahi, luego
    # P2 sigue cerrada, y P4/P5 —que van por SQL— ni se enteran.
    Sonda(
        nombre="M1",
        que_rompe="la ventana desaparece del ADT (las columnas siguen)",
        cambios=(
            Cambio(
                fichero="src/skillgraph/knowledge/graph.py",
                viejo=r"(?m)^    valid_from_revision: str \| None = None\n"
                r"    valid_until_revision: str \| None = None$",
                nuevo=r"    valid_desde_revision: str | None = None\n"
                r"    valid_hasta_revision: str | None = None",
            ),
            Cambio(
                fichero="src/skillgraph/platform/knowledge_mappers.py",
                viejo=(
                    r'(?m)^        valid_from_revision=row\["valid_from_revision"\],\n'
                    r'        valid_until_revision=row\["valid_until_revision"\],$'
                ),
                nuevo=(
                    '        valid_desde_revision=row["valid_from_revision"],\n'
                    '        valid_hasta_revision=row["valid_until_revision"],'
                ),
            ),
            Cambio(
                fichero="src/skillgraph/platform/knowledge_claims.py",
                viejo=r"(?m)^                    claim\.valid_from_revision,\n"
                r"                    claim\.valid_until_revision,$",
                nuevo="                    claim.valid_desde_revision,\n"
                "                    claim.valid_hasta_revision,",
            ),
        ),
    ),
    # ------------------------------------------------------------------ M2
    # P2 mira `PRAGMA table_info(claims)`. Un renombrado de punta a punta del
    # identificador: la columna, el `ALTER TABLE` de la migracion, el INSERT, el
    # mapper y el campo del ADT. **El ADT tambien**, porque si el campo se
    # quedara con el nombre viejo el mapper no podria construir el Claim y el
    # arbol reventaria —que es el crash, no la propiedad.
    Sonda(
        nombre="M2",
        que_rompe="la cadena de supersesion desaparece (columna y campo)",
        cambios=tuple(
            Cambio(
                fichero=f,
                viejo=r"\bsupersedes_claim_id\b",
                nuevo="supersede_a",
                # TODAS las apariciones del fichero. Ver la nota de `Cambio`:
                # con `count=1` la sonda dejaba el invariante de
                # `__post_init__` apuntando al nombre viejo y reventaba el
                # arbol —una «cazada» por la razon equivocada.
                cuantas=-1,
            )
            for f in (
                "src/skillgraph/platform/schema.py",
                "src/skillgraph/platform/migrations.py",
                "src/skillgraph/platform/knowledge_claims.py",
                "src/skillgraph/platform/knowledge_mappers.py",
                "src/skillgraph/knowledge/graph.py",
            )
        ),
    ),
    # ------------------------------------------------------------------ M3
    # P3 mira los metodos PUBLICOS de `Storage` con «revision» en el nombre.
    #
    # **LA PRIMERA VERSION DE ESTA SONDA APUNTABA AL FICHERO EQUIVOCADO, Y LO
    # DEMOSTRO EL CONTRASALTO: dio INOCUA.** `knowledge_repository.py` tiene su
    # `claims_at_revision` —el que llama a la capa baja—, pero **ese no es el
    # que `Storage` expone**: `Storage` hereda de `KnowledgeDelegations`
    # (`storage.py` -> `knowledge_delegations.KnowledgeDelegations`), y de ahi
    # sale el metodo publico. Renombrar el interno deja el publico intacto y la
    # pregunta P3 sigue cerrada, que es la lectura que miente en verde.
    #
    # MEDIDO, no supuesto: `getattr(Storage, 'claims_at_revision').__module__`
    # devuelve `skillgraph.platform.knowledge_delegations`.
    Sonda(
        nombre="M3",
        que_rompe="la consulta por revision deja de ser publica en Storage",
        cambios=(
            Cambio(
                fichero="src/skillgraph/platform/knowledge_delegations.py",
                viejo=r"(?m)^    def claims_at_revision\(",
                nuevo="    def _claims_at_revision_oculta(",
            ),
        ),
    ),
    # ------------------------------------------------------------------ M4
    # P4: en HEAD, lo caducado no esta vigente. Quitar el filtro de
    # `valid_until` devuelve `c-A` al conflicto con `c-B`.
    Sonda(
        nombre="M4",
        que_rompe="nada CADUCA en HEAD: un cambio vuelve a ser contradiccion",
        cambios=(
            Cambio(
                fichero="src/skillgraph/platform/knowledge_conflicts.py",
                viejo=r'return row\["valid_until_revision"\] is None',
                nuevo="return True",
            ),
        ),
    ),
    # ------------------------------------------------------------------ M5
    # P5: fuera de HEAD, la ventana se compara por `seq`. Una revision que no
    # existe deja de «no decir nada» y pasa a decir «nada esta vigente», que
    # apaga el detector de conflictos en toda revision con nombre. HEAD queda
    # INTACTO, luego P4 sigue cerrada: es la sonda que separa las dos mitades.
    Sonda(
        nombre="M5",
        que_rompe="nada es VIGENTE fuera de HEAD: el detector se apaga por revision",
        cambios=(
            Cambio(
                fichero="src/skillgraph/platform/knowledge_conflicts.py",
                viejo=r"(?m)^    if seq is None:\n        return False$",
                nuevo="    if True:\n        return False",
            ),
        ),
    ),
)


def carga_el_arbol() -> tuple[bool, str]:
    """¿Cargan TODOS los modulos que las sondas tocan?

    **POR QUE EL `import` Y NO UNA COMPILACION.** Una sonda puede dejar el texto
    sintacticamente valido y aun asi romper el arbol en tiempo de importacion
    —una columna que ya no existe, un nombre que el mapper no puede pasar— y
    `py_compile` la daria por buena. Lo que tiene que funcionar es el modulo
    **cargado**, porque es lo que el instrumento importa.
    """
    proc = subprocess.run(
        [str(PY), "-c", "import " + ", ".join(MODULOS)],
        capture_output=True,
        text=True,
        cwd=str(RAIZ),
        check=False,
    )
    return proc.returncode == 0, (proc.stdout + proc.stderr)[-800:]


def preguntas_abiertas() -> tuple[int, str]:
    """Corre el instrumento y cuenta las preguntas ABIERTAS.

    **Y DEVUELVE VEREDICTO AUNQUE EL INSTRUMENTO REVENTE** (leccion de B28,
    error 32): una caida es `CAZADA`, porque un arbol que ni siquiera puede
    ejecutar el instrumento NO satisface las propiedades. Lo que el harness
    clasifica aparte es la *caida*, porque esa es la razon y no el veredicto.
    """
    proc = subprocess.run(
        [str(PY), str(INSTRUMENTO)],
        capture_output=True,
        text=True,
        cwd=str(RAIZ),
        check=False,
    )
    salida = proc.stdout + proc.stderr
    for ln in salida.splitlines():
        if ln.startswith("RESULTADO:"):
            return int(ln.split(":")[1].strip().split("/")[0]), salida
    return CAIDA, salida


@dataclass
class Informe:
    resultados: list[tuple[str, str, str]] = field(default_factory=list)
    rotas: list[str] = field(default_factory=list)


def aplica(originales: dict[str, str], sonda: Sonda) -> dict[str, str] | None:
    """Devuelve los ficheros mutados, o `None` si alguna sonda esta DESANCLADA.

    **`Match.expand()`, no el retorno crudo.** Con `repl` como funcion, Python
    usa el valor devuelto **literalmente**: un `\\g<1>` en el retorno se
    escribiria como texto en vez de expandirse y la sonda escribiria basura en
    vez de mutar.
    """
    mutados: dict[str, str] = {}
    for cambio in sonda.cambios:
        if cambio.fichero not in originales:
            return None
        patron = re.compile(cambio.viejo)
        texto = originales[cambio.fichero]
        if not patron.search(texto):
            return None
        count = 0 if cambio.cuantas < 0 else cambio.cuantas
        nuevo_texto, n = patron.subn(
            lambda m, nuevo=cambio.nuevo: m.expand(nuevo), texto, count=count
        )
        if cambio.cuantas < 0:
            if n < 1:
                return None
        elif n != cambio.cuantas:
            return None
        mutados[cambio.fichero] = nuevo_texto
    return mutados


def main() -> int:
    originales: dict[str, str] = {}
    for sonda in SONDAS:
        for cambio in sonda.cambios:
            f = cambio.fichero
            if f not in originales:
                originales[f] = (RAIZ / f).read_text(encoding="utf-8")

    print("B29 — autocomprobacion del instrumento de vigencia")
    print("  ficheros: " + ", ".join(sorted(originales)))
    print(f"  sondas: {len(SONDAS)} (multi-fichero)\n")

    base_abiertas, salida_base = preguntas_abiertas()
    print(f"  sin sondas: {base_abiertas} preguntas abiertas")
    if base_abiertas == CAIDA:
        print("  el instrumento NO TERMINA sobre el arbol sin sondas")
        print(salida_base[-600:])
        return 2
    if base_abiertas != 0:
        print("  el bloque NO esta cerrado: se mide sobre un arbol que ya falla")
        print(salida_base[-600:])
        return 2

    informe = Informe()
    for sonda in SONDAS:
        mutados = aplica(originales, sonda)
        if mutados is None:
            informe.resultados.append(
                (
                    sonda.nombre,
                    ROTA,
                    "el texto a mutar NO existe (desanclada) en alguno de sus ficheros",
                )
            )
            informe.rotas.append(sonda.nombre)
            print(f"  {sonda.nombre}  {ROTA:<7} {sonda.que_rompe}")
            continue

        for f, texto in mutados.items():
            (RAIZ / f).write_text(texto, encoding="utf-8")
        try:
            carga, salida_carga = carga_el_arbol()
            if not carga:
                informe.resultados.append(
                    (sonda.nombre, ROTA, "la sonda rompe la carga de los modulos")
                )
                informe.rotas.append(sonda.nombre)
                print(f"  {sonda.nombre}  {ROTA:<7} {sonda.que_rompe}")
                print(f"      {salida_carga.strip()[:200]}")
                continue

            abiertas, salida = preguntas_abiertas()
            if abiertas == CAIDA:
                # Una CAIDA ES una cazada (el arbol roto no satisface las
                # propiedades), pero se registra como tal Y se imprime la
                # salida: una sonda «cazada» que en realidad solo reventaba
                # es el fallo del harness que este bloque existe para no
                # dejar pasar en verde.
                veredicto = CAZADA
                cazada = True
                detalle = (
                    "el instrumento no pudo terminar: el arbol quedo roto, y eso no "
                    f"satisface las propiedades. {sonda.que_rompe}"
                )
            else:
                cazada = abiertas >= sonda.p_abiertas_minimo
                veredicto = CAZADA if cazada else INOCUA
                quien = ", ".join(
                    ln.split()[0]
                    for ln in salida.splitlines()
                    if len(ln.split()) > 1 and ln.split()[1] == "ABIERTA"
                )
                detalle = (
                    f"abre {abiertas} pregunta(s)"
                    + (f" ({quien})" if quien else "")
                    + f"; {sonda.que_rompe}"
                )
            informe.resultados.append((sonda.nombre, veredicto, detalle))
            print(f"  {sonda.nombre}  {veredicto:<7} {sonda.que_rompe}")
            print(f"      {detalle}")
            if abiertas == CAIDA:
                print(f"      POR QUE NO TERMINO: {salida.strip()[-500:]}")
            elif not cazada:
                print(f"      SIN CAZAR: {salida[-400:]}")
        finally:
            for f, texto in originales.items():
                (RAIZ / f).write_text(texto, encoding="utf-8")

    cazadas = [n for n, v, _ in informe.resultados if v == CAZADA]
    inocuas = [n for n, v, _ in informe.resultados if v == INOCUA]
    rotas = [n for n, v, _ in informe.resultados if v == ROTA]

    print()
    print(f"  cazadas: {len(cazadas)}/{len(SONDAS)}  {cazadas}")
    if inocuas:
        print(f"  INOCUAS: {inocuas}  <-- el guard no muerde, o la sonda no rompe nada")
    if rotas:
        print(f"  ROTAS (error del harness, no del bloque): {rotas}")

    print("\n  tras restaurar el arbol:")
    restauradas, salida = preguntas_abiertas()
    linea = [ln for ln in salida.splitlines() if ln.startswith("RESULTADO:")]
    print(f"  {linea[0].strip() if linea else 'el instrumento no termina'}")
    if restauradas != 0:
        print("  FALLA: el arbol no volvio a su estado")
        print(salida[-600:])
        return 1
    print("  VERDE: el bloque vuelve a dar 0/5 abiertas")

    if rotas:
        print("\n  FALLA del harness: hay sondas ROTAS")
        return 2
    if inocuas:
        print("\n  FALLA: alguna sonda NO fue cazada")
        return 1
    print(f"\n  OK: {len(cazadas)}/{len(SONDAS)} sondas cazadas, y el bloque cerrado")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
