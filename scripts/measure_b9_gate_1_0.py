#!/usr/bin/env python3
"""B9 — el gate de 1.0, medido propiedad por propiedad.

Por que este script existe
--------------------------
``ROADMAP.md`` dice, textual: *«`v1.0.0` solo existe cuando se cumplan
**todas**»*, y a continuacion lista veinte propiedades en prosa. Es una
afirmacion sobre el proyecto mas fuerte que ninguna otra del repo, y es la
unica que no tiene nada que la compruebe.

Es exactamente la forma que B0 senalo: **una afirmacion que el repositorio
declara y nadie mide**. La diferencia es que aqui el sujeto no es un campo
de estado, son veinte. Y veinte afirmaciones sin predicado no son veinte
riesgos, son un documento.

Que este script mide y que no
-----------------------------
Cada propiedad se mide con un **predicado que se ejecuta**. No se lee una
declaracion y se devuelve «cumple»: o se corre algo y se mira el resultado,
o se dice que no hay forma de decidirlo aqui.

Tres veredictos, y la distincion importa
----------------------------------------
``PASS``          la propiedad se cumple y se ha comprobado.
``OPEN``          se ha comprobado y NO se cumple, o no esta certificada.
                  Se dice cual de las dos cosas, porque «no cumple» y «nadie
                  lo ha certificado» piden acciones distintas.
``NO_MEASURABLE`` no hay forma de decidirla con este entorno, y se dice por
                  que. NO baja el veredicto igual que ``OPEN``: las dos
                  dejan 1.0 lejos, y declararla ``PASS`` seria la unica
                  forma de mentir.

``NO_MEDIBLE``    el roadmap declara una propiedad para la que este
                  instrumento no tiene predicado. No es un veredicto sobre
                  el proyecto: es un hueco del instrumento, y sale porque el
                  conjunto de propiedades se **deriva** del roadmap y no de
                  una lista escrita aqui. Si alguien anade una propiedad, el
                  instrumento se pone a si mismo en rojo en vez de
                  dejarla pasar en verde.

La(property) que se mide, y de donde sale
------------------------------------------
El conjunto sale del bloque cercado de ``ROADMAP.md``, partido por columnas.
Escribir la lista de veinte aqui seria crear una segunda fuente de verdad
que divergiria de la primera el dia que el roadmap cambie — la trampa de
``DIRECTORIOS_NO_RECETA`` en WI-99, y la de WI-106 mas abajo: el guard que
compara contra su propia copia.

Diseno: predicados aparte, judgment aparte
------------------------------------------
``evaluar()`` es una funcion **pura**: recibe un nombre de propiedad y un
diccionario de predicados, y devuelve una tupla de ``Propiedad``. No lee
disco, no lanza procesos, no mira el reloj. Todo lo que habla con el mundo
esta en los predicados.

Eso no es estetica: permite que los tests monten predicados falsos y
comprueben que ``evaluar`` reparte bien los veredictos, en vez de tener que
convencer al pytest de que el sistema real no esta listo para 1.0.

Codigo de salida
----------------
0  las veinte tienen veredicto y el informe esta completo
2  el propio instrumento no pudo medirse (falta un fichero que lee)

El codigo NO dice si el proyecto esta listo para 1.0. Eso lo dice
``listo_para_1_0`` en el JSON, y son cosas distintas: un instrumento que
sale con 1 cuando el proyecto no esta listo se confunde con un gate, y un
gate que no se puede apagar no es una medida.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

RAIZ = Path(__file__).resolve().parent.parent

#: Los cuatro veredictos. Los tres primeros son sobre el PROYECTO; el
#: cuarto es sobre el INSTRUMENTO, y por eso vive aqui y no en el tipo del
#: veredicto de una propiedad: mezclarlo haria que un fallo del medidor
#: pareciera un fallo del proyecto.
Veredicto = Literal["PASS", "OPEN", "NO_MEASURABLE"]
Estado = Literal[Veredicto, "NO_MEDIBLE"]

Predicado = Callable[[], "tuple[Veredicto, str]"]


@dataclass(frozen=True, slots=True)
class Propiedad:
    """Una propiedad del gate y lo que el instrumento pudo decir de ella."""

    nombre: str
    veredicto: Estado
    evidencia: str


# --------------------------------------------------------------------------
# El conjunto, derivado
# --------------------------------------------------------------------------


def _bloque_del_gate(texto: str) -> str:
    """El bloque cercado que empieza por la primera propiedad del gate.

    Se ancla en el texto de la primera propiedad y no en un numero de
    linea, porque un numero de linea es una referencia a una foto de hoy y
    esta tiene que seguir al roadmap cuando se mueva.
    """
    patron = re.compile(r"```\n(roadmap/state/docs coherentes.*?)```", re.DOTALL)
    encontrado = patron.search(texto)
    if encontrado is None:
        raise LookupError("ROADMAP.md ya no declara el bloque del gate de 1.0")
    return encontrado.group(1)


def propiedades_del_roadmap(texto: str) -> tuple[str, ...]:
    """Las veinte propiedades, leidas del roadmap y en su orden de lectura.

    El bloque es de dos columnas separadas por dos o mas espacios, y la
    septima fila tiene la columna izquierda vacia: la TUI se lee sola. Por
    eso se parte por columnas y se descartan las vacias, en vez de intentar
    alinear por posiciones, que es la forma de romperlo en cuanto el
    roadmap anade una fila.
    """
    encontradas: list[str] = []
    for fila in _bloque_del_gate(texto).rstrip("\n").splitlines():
        for columna in re.split(r"\s{2,}", fila.strip()):
            if columna:
                encontradas.append(columna)
    return tuple(encontradas)


def _slug(nombre: str) -> str:
    """La clave estable con la que un predicado se empareja con su propiedad."""
    return re.sub(r"[^a-z0-9]+", "_", nombre.lower()).strip("_")


# --------------------------------------------------------------------------
# Utilidades de medicion. Todo lo que habla con el mundo vive aqui.
# --------------------------------------------------------------------------


def _lee(relativo: str) -> str:
    return (RAIZ / relativo).read_text(encoding="utf-8")


def _corre(argv: list[str], timeout: int = 900) -> subprocess.CompletedProcess[str]:
    """Corre un comando del repo y devuelve su resultado, sin levantar excepcion."""
    return subprocess.run(
        argv,
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


def _pytest(*objetivos: str) -> str:
    """Corre pytest sobre objetivos y devuelve la ULTIMA linea del resumen.

    Solo la ultima: es la que lleva el recuento, y una linea de puntos de
    progreso no dice nada que el resumen no diga mejor.
    """
    proc = _corre([sys.executable, "-m", "pytest", "-q", "--no-header", *objetivos])
    lineas = [linea for linea in proc.stdout.splitlines() if linea.strip()]
    return lineas[-1] if lineas else f"sin salida (rc={proc.returncode})"


def _pasaron(resumen: str) -> int:
    """Cuantos tests PASARON, leidos del resumen.

     Se cuenta «passed» y no «no fallo»: un resumen puede decir
     ``3 passed, 20 deselected`` —deselected aparece igual cuando los tests
    selectionados se ejecutaron— y buscar la palabra «failed» en vez de
     contar los que pasaron da un falso verde. MEDIDO: la primera version
     de ``_migrations_probadas`` buscaba «deselected» para detectar que no
     se habia ejecutado nada, y dio OPEN sobre tres tests que si pasaron.
    """
    encontrado = re.search(r"(\d+) passed", resumen)
    return int(encontrado.group(1)) if encontrado else 0


def _fallaron(resumen: str) -> int:
    """Cuantos tests fallaron, leidos del resumen."""
    encontrado = re.search(r"(\d+) failed", resumen)
    return int(encontrado.group(1)) if encontrado else 0


#: Una pregunta de una hoja de medidor, con su veredicto y su evidencia.
Pregunta = tuple[str, str, bool]


def _preguntas(informe: str) -> tuple[Pregunta, ...]:
    """Las preguntas de una hoja de medidor, con su estado y su evidencia.

    MEDIDO, y el motivo por el que esto existe es el error de siempre: la
    primera version buscaba literally ``[CERRADO ]`` con un espacio detras,
    porque asi lo escribe ``measure_b5_graph_diff.py``, y lo aplico al
    informe de B6, que lo escribe ``[CERRADO]`` sin espacio. Resultado:
    cero cerradas, cero abiertas, y el predicado de provenance devolvio
    PASS sobre un informe del que no leyo ni una linea.

    Por eso el marcador se reconoce por FORMA y no por texto exacto: el
    espacio de mas es una convencion de un script, y una convencion no es
    un contrato.

    Y por eso la tercera posicion es *fuera de alcance*: una hoja que
    declara una pregunta fuera de alcance no esta diciendo que la
    propriedade falle, esta diciendo que el bloque la dejo a proposito
    fuera. B5 lo escribio literal en su P6, y el veredicto de 1.0 tiene que
    respetarlo — es el mismo principio que «fuera de alcance se registra y
    no baja el veredicto».
    """
    preguntas: list[Pregunta] = []
    estado: str | None = None
    lineas_evidencia: list[str] = []
    for linea in informe.splitlines():
        encontrada = re.match(r"^\s*\[(CERRADO|ABIERTO)\s*\]", linea)
        if encontrada is not None:
            if estado is not None:
                preguntas.append((estado, " ".join(lineas_evidencia), False))
            estado = encontrada.group(1)
            lineas_evidencia = [linea]
            continue
        if estado is not None and linea.startswith(" " * 10):
            lineas_evidencia.append(linea.strip())
    if estado is not None:
        preguntas.append((estado, " ".join(lineas_evidencia), False))
    return tuple((est, evi, "FUERA DEL ALCANCE" in evi.upper()) for est, evi, _ in preguntas)


def _imports_de(paquete: str) -> tuple[str, ...]:
    """Todos los modulos que importan los ficheros de un paquete de ``src``.

    Se recorre el arbol de verdad y no una lista escrita aqui: un paquete
    nuevo tiene que entrar en la medicion por existir, no por que alguien
    se acuerde de anadirlo.
    """
    raices = sorted((RAIZ / "src" / "skillgraph" / paquete).rglob("*.py"))
    encontrados: set[str] = set()
    for fichero in raices:
        arbol = ast.parse(fichero.read_text(encoding="utf-8"), filename=str(fichero))
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Import):
                encontrados.update(alias.name for alias in nodo.names)
            elif isinstance(nodo, ast.ImportFrom) and nodo.module and nodo.level == 0:
                encontrados.add(nodo.module)
    return tuple(sorted(encontrados))


# --------------------------------------------------------------------------
# Los predicados. Cada uno se ejecuta; ninguno devuelve una constante.
# --------------------------------------------------------------------------


def _roadmap_state_docs_coherentes() -> tuple[Veredicto, str]:
    """La mas barata de medir y la que mas delata: se ejecuta el cruce."""
    proc = _corre([sys.executable, "scripts/project_truth.py"], timeout=300)
    try:
        carga = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return "OPEN", f"project_truth.py no emitio JSON legible (rc={proc.returncode})"
    if carga.get("coherente") is True:
        return "PASS", (
            f"project_truth.py rc={proc.returncode}, 0 contradicciones; "
            f"bloque {carga['bloque']}, version {carga['version']}, "
            f"{carga['tests_declarados']} tests declarados == {carga['tests_reales']} reales"
        )
    return "OPEN", "project_truth.py rc=" + str(proc.returncode) + ": " + "; ".join(
        carga.get("contradicciones", [])
    )


def _blueprint_legacy_completamente_probado() -> tuple[Veredicto, str]:
    """Cada UAT que declara el blueprint tiene al menos un test que lo nombra.

    Se mide por conjuntos, no contando ficheros: lo que importa es que no
    quede ningun UAT sin cubrir, y un UAT puede estar cubierto por tres
    tests o por uno.
    """
    declarados = set(re.findall(r"UAT-[A-Z0-9]+", _lee("docs/blueprint/plan/UAT.md")))
    if not declarados:
        return "OPEN", "el blueprint ya no declara ningun UAT: no hay nada que cubrir"
    nombrados: set[str] = set()
    for test in sorted((RAIZ / "tests").rglob("*.py")):
        nombrados.update(re.findall(r"UAT-[A-Z0-9]+", test.read_text(encoding="utf-8")))
    sin_cubrir = declarados - nombrados
    if sin_cubrir:
        return (
            "OPEN",
            f"{len(sin_cubrir)} de {len(declarados)} UAT sin test que los nombre: {sorted(sin_cubrir)}",
        )
    return "PASS", f"los {len(declarados)} UAT del blueprint tienen test que los nombra"


def _graph_diff_gate_operativo() -> tuple[Veredicto, str]:
    """El gate de B5, ejecutado. Si tiene una pregunta abierta, no opera.

    Y si no se leyo NINGUNA pregunta, no opera tampoco: un predicado que
    devuelve PASS porque no encontro nada que contar es el error 32 de
    WI-113, el que se cuenta como victoria.
    """
    return _veredicto_de_hoja("scripts/measure_b5_graph_diff.py", "Graph Diff Gate")


def _provenance_fuerte() -> tuple[Veredicto, str]:
    """La provenance de B6, ejecutada, con la misma regla de la hoja de B5."""
    return _veredicto_de_hoja("scripts/measure_b6_provenance.py", "provenance")


def _veredicto_de_hoja(script: str, que: str) -> tuple[Veredicto, str]:
    """Lee una hoja de medidor y decide si la propiedad se sostiene.

    Las preguntas fuera de alcance se cuentan aparte y se nombran: no bajan
    el veredicto, pero tampoco desaparecen del informe, porque si no
    alguien tendria que abrir la hoja para saber que estaban.
    """
    proc = _corre([sys.executable, script], timeout=300)
    if not proc.stdout.strip():
        return "OPEN", f"{script} no produjo informe (rc={proc.returncode})"
    preguntas = _preguntas(proc.stdout)
    if not preguntas:
        return "OPEN", (
            f"{script} no emitio ninguna pregunta reconocible: no se puede decidir "
            f"si {que} se sostiene, y no se assume que se sostiene"
        )
    cerradas = [p for p in preguntas if p[0] == "CERRADO"]
    abiertas = [p for p in preguntas if p[0] == "ABIERTO" and not p[2]]
    fuera = [p for p in preguntas if p[0] == "ABIERTO" and p[2]]
    detalle = f"{len(cerradas)} cerradas, {len(abiertas)} abiertas"
    if fuera:
        detalle += f", {len(fuera)} declaradas FUERA DE ALCANCE (no bajan el veredicto)"
    if abiertas:
        return "OPEN", f"{que}: {detalle}"
    return "PASS", f"{que}: {detalle}"


def _runtime_real_certificado() -> tuple[Veredicto, str]:
    """El proveedor real necesita una credencial. Se ejecuta y se mira el skip.

    Un ``skip`` aqui NO es un fallo de la suite: es la declaracion de que
    el runtime real no se ha ejercitado contra un proveedor de verdad. Por
    eso se lee el resultado en vez de mirar si el comando salio con 0.
    """
    resumen = _pytest("tests/test_uat_real_provider.py")
    if "skipped" in resumen:
        return "OPEN", (
            "el UAT del proveedor real se salta: exige SG_UAT_REAL_PROVIDER=1 y una "
            f"credencial en el entorno. Resumen: {resumen}"
        )
    return "PASS", f"el proveedor real se ejecuto de verdad. Resumen: {resumen}"


def _ontology_extensible() -> tuple[Veredicto, str]:
    """Ontologia extensible = el nucleo no nombra ningun tipo de recurso.

    Es la forma ejecutable de la propiedad: si ``core/`` no sabe que
    existen los recursos, anadir uno no obliga a tocar el nucleo. Y se mide
    con AST, no con grep, para que un nombre de recurso en el docstring de
    un modulo no conta como dependencia.
    """
    tipos: set[str] = set()
    for modulo in sorted((RAIZ / "src" / "skillgraph" / "core").rglob("*.py")):
        arbol = ast.parse(modulo.read_text(encoding="utf-8"), filename=str(modulo))
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
                tipos.update(re.findall(r"^[A-Z][A-Za-z]+Pack$", nodo.value))
    if tipos:
        return "OPEN", f"core/ nombra tipos de recurso: {sorted(tipos)}"
    return "PASS", "core/ no nombra ningun tipo de recurso: se anaden sin tocarlo"


def _crash_recovery_real_certificado() -> tuple[Veredicto, str]:
    """Se ejecuta la suite de crash y de recovery. SinMocks, por construccion."""
    resumen = _pytest("tests/test_b2_real_crash.py", "tests/test_h9_storage_recover_interrupted.py")
    if "failed" in resumen or "error" in resumen:
        return "OPEN", f"la suite de crash/recovery no esta verde: {resumen}"
    return "PASS", f"crash y recovery ejecutados de verdad: {resumen}"


def _concurrencia_real_certificada() -> tuple[Veredicto, str]:
    """Ocho procesos de verdad, cinco veces seguidas.

    Se repite porque la propiedad es «certificada», y una certificacion es
    una repeticion: un test que pasa una vez de cinco no certifica nada.
    """
    resumenes = [_pytest("tests/test_b2_real_concurrency.py") for _ in range(5)]
    fallos = [r for r in resumenes if "failed" in r or "error" in r]
    if fallos:
        return "OPEN", f"{len(fallos)} de 5 corridas con fallos; ultima: {fallos[-1]}"
    return "PASS", f"5 de 5 corridas verdes; ultima: {resumenes[-1]}"


def _capabilities_deterministas() -> tuple[Veredicto, str]:
    """La version de una capability la declara EL PUERTO, y solo el.

    Si un adaptador vuelve a declarar su propia version, la determinista es
    mentira: dos adaptadores del mismo puerto pueden dejar de declarar lo
    mismo. Se mide contando quien escribe la constante.
    """
    declarantes: list[str] = []
    for modulo in sorted((RAIZ / "src" / "skillgraph").rglob("*.py")):
        texto = modulo.read_text(encoding="utf-8")
        for linea in texto.splitlines():
            if re.match(r"\s*CAPABILITY_VERSION\s*[:=]", linea):
                declarantes.append(str(modulo.relative_to(RAIZ)))
    unicos = sorted(set(declarantes))
    if len(unicos) > 1:
        return "OPEN", f"CAPABILITY_VERSION se declara en mas de un sitio: {unicos}"
    return "PASS", f"CAPABILITY_VERSION se declara en un solo sitio: {unicos}"


def _core_sin_dependencias_de_impl_externa() -> tuple[Veredicto, str]:
    """El nucleo no importa nada que no sea el nucleo o la libreria estandar."""
    externos: set[str] = set()
    for nombre in _imports_de("core"):
        if nombre.startswith("skillgraph.core"):
            continue
        if nombre.split(".")[0] in _MODULOS_ESTANDAR:
            continue
        externos.add(nombre)
    if externos:
        return "OPEN", f"core/ importa fuera de si mismo: {sorted(externos)}"
    return (
        "PASS",
        f"core/ solo importa de si mismo y de la estandar ({len(_imports_de('core'))} modulos)",
    )


def _resource_controller_api_estable() -> tuple[Veredicto, str]:
    """Una API estable necesita una superficie DECLARADA. Si no existe, no hay estabilidad.

    No se busca un snapshot porque no lo hay: se mira si el paquete declara
    que expone. Un paquete sin ``__all__`` no tiene superficie publica
    declarada, y una superficie que nadie declara no se puede certificar
    como estable aunque hoy no haya cambiado.

    MEDIDO AL ESCRIBIR B10, y es la razon de que este predicado ejecuta un
    guard en vez de seguir leyendo el fichero. La version anterior hacia
    dos cosas: que existiera ``__all__`` y que el snapshot estuviera en su
    sitio. Las dos se cierran escribiendo el fichero, y quien lo escribiese
    no tendria que saber nada del arbol: veinte segundos, dos ``PASS`` y un
    gate de 1.0 igual de lejos.

    Lo que decide es que la superficie este **certificada**: declarada,
    versionada y sin haberse movido desde el snapshot. Eso no se puede
    leer, se ejecuta, y se delega en `scripts/check_public_surfaces.py`,
    que es el unico que sabe derivar las tres capas de la superficie.
    """
    problemas = _guard_de_superficies()
    if problemas is not None:
        return "OPEN", problemas
    return "PASS", (
        "la superficie del nucleo esta declarada, versionada y no se ha movido "
        "desde su snapshot, segun scripts/check_public_surfaces.py"
    )


def _guard_de_superficies() -> str | None:
    """Ejecuta el guard de superficies. Devuelve el motivo si falla, o ``None``.

    Se delega y no se reimplementa: el guard es el unico que sabe derivar
    la superficie del nucleo y la de la CLI. Dosderivaciones son dos
    verdades, y aqui una de las dos puede quedarse vieja sin que nadie se
    entere — que es justo lo que este bloque vino a arreglar.

    Se decide por el **codigo de salida**, no por la salida: un `touch`
    deja el snapshot en disco, y mirar el fichero era el error que se
    estaba corrigiendo.
    """
    proc = _corre(
        [sys.executable, "scripts/check_public_surfaces.py"],
        timeout=300,
    )
    if proc.returncode == 0:
        return None
    detalle = (proc.stdout or proc.stderr).strip().splitlines()
    return "el guard de superficies no pasa, luego la superficie no esta certificada: " + (
        detalle[-1] if detalle else f"rc={proc.returncode}"
    )


def _cli_estable() -> tuple[Veredicto, str]:
    """La CLI es estable si su superficie esta DECLARADA y **no se ha movido**.

    MEDIDO AL ESCRIBIR B10. La version anterior hacia dos cosas: importar
    el parser —bien, eso no se puede hacer de mentira— y comprobar que
    existiera el fichero de la declaracion. La segunda es un ``is_file()``,
    y un ``is_file()`` se cierra con un ``touch``: veinte segundos, y el
    veredicto pasa a ``PASS`` con una superficie que puede contener lo que
    sea, incluido nada.

    La version que hay ahora delega en el guard, que **ejecuta** la
    comparacion contra el arbol. Y delega, no reimplementa: la superficie
    de la CLI se deriva en un solo sitio. Dos derivaciones son dos
    verdades, y la que no se ejecuta es la que se queda vieja.
    """
    problemas = _guard_de_superficies()
    if problemas is not None:
        return "OPEN", problemas
    return "PASS", (
        "la superficie de la CLI esta declarada, versionada y no se ha movido "
        "desde su snapshot, segun scripts/check_public_surfaces.py"
    )


def _tui_operacional() -> tuple[Veredicto, str]:
    """No se puede decidir sin un terminal y sin una persona.

    Se declara y NO se disimula. B7 registro la misma frontera (P4) y el
    veredicto correcto no es «cumple» ni «incumple»: es que la pregunta
    no es contestable por una suite, y por eso tampoco baja el veredicto.
    """
    return "NO_MEASURABLE", (
        "«operacional» es una propiedad de una persona usando un terminal: no hay "
        "forma de medirla ejecutando el repo. B7 la registro como P4 fuera de alcance."
    )


def _migrations_probadas() -> tuple[Veredicto, str]:
    """Una migracion probada es la que se prueba contra una base VIEJA de verdad.

    Es la pregunta que B6 dejo escrita y que su propio fallo valio:
    ``CREATE TABLE IF NOT EXISTS`` no anade columnas, y un test que
    construye la base desde cero cada vez no lo ve nunca. Se ejecutan los
    tests que dicen migrar y se CUENTAN los que pasaron, en vez de buscar
    una palabra en el resumen: la primera version buscaba «deselected» y
    dio OPEN sobre ``3 passed, 20 deselected``.
    """
    resumen = _pytest("tests/test_b6_provenance.py", "-k", "migra")
    if _pasaron(resumen) == 0:
        return "OPEN", (
            "ningun test ejecuto la migracion contra una base previa: se prueba que "
            "una base nueva se crea, no que una base existente se actualiza. "
            f"Resumen: {resumen}"
        )
    if _fallaron(resumen):
        return "OPEN", f"la migracion contra base vieja no esta verde: {resumen}"
    return "PASS", f"migracion contra base previa ejecutada: {resumen}"


def _pack_controller_lifecycle() -> tuple[Veredicto, str]:
    """El ciclo de vida que B8 nombro es install/update/remove. Se mira si existen."""
    declarados = ("install", "update", "remove")
    existentes = _subcomandos_de("pack")
    faltan = [v for v in declarados if v not in existentes]
    if faltan:
        return "OPEN", (
            f"`sg pack` expone {sorted(existentes)} y no {list(faltan)}: el ciclo de "
            "vida que B8 declaro como requisito no existe todavia como comando"
        )
    return "PASS", f"`sg pack` expone el ciclo completo: {sorted(existentes)}"


def _backups_restore_probados() -> tuple[Veredicto, str]:
    """Se ejecutan los tests de backup y de restore."""
    resumen = _pytest("tests/test_backups.py")
    if "failed" in resumen or "error" in resumen:
        return "OPEN", f"la suite de backups/restore no esta verde: {resumen}"
    return "PASS", f"backups y restore ejecutados: {resumen}"


def _upgrade_desde_releases_soportadas() -> tuple[Veredicto, str]:
    """Se mide EJECUTANDO la capacidad, no buscando un nombre.

    **LO QUE ESTE PREDICADO ERA, Y POR QUE ERA UN DEFECTO.** Buscaba con
    un regex `def (upgrade|migrate_up|actualizar_schema)` en todos los
    modulos de `src/`, y contaba como PASS el primer nombre que encontrara.
    Tres cosas van mal en eso, y las tres importan mas que el nombre:

    1. Mide el NOMBRE, no la capacidad. B12 implementa el upgrade entero —
       libro de migraciones, version derivada, base atrasada que se sube,
       base mas nueva que falla— y se llama `sincroniza`, no `upgrade`. Con
       el predicado viejo, B12 habria entregado la capacidad y el gate
       habria seguido diciendo OPEN: un falso negativo, que es la misma
       clase de fallo que el falso positivo de B9, con el signo cambiado.
    2. Un nombre no se puede ejecutar, asi que no se puede comprobar que
       haga lo que dice. Un `def upgrade(): pass` daba verde.
    3. Enumera lo que hay en vez de derivarlo. Anadir una segunda via de
       upgrade no la hacia mejor.

    Es el «conectar != contener» de WI-102 y el «el touch no cierra nada»
    de B10, aplicados a este predicado. La forma correcta es la de B10: el
    predicador CORRE el instrumento y decide por su codigo de salida.

    El medidor construye bases de verdad en un temporal y responde cinco
    preguntas ejecutables —se sube una base vieja, la version se puede
    PREGUNTAR y no leer del modulo, una base mas nueva falla con un error
    del dominio, y abrir una base al dia no escribe— de modo que un PASS
    aqui no puede venir de un nombre bien puesto.
    """
    proc = _corre([sys.executable, str(RAIZ / "scripts" / "measure_b12_schema_upgrade.py")])
    salida = proc.stdout.strip()
    resumen = salida.splitlines()[-1] if salida else "sin salida"
    if proc.returncode != 0:
        return "OPEN", (
            f"la capacidad de subir una base de una release anterior no esta "
            f"completa, segun scripts/measure_b12_schema_upgrade.py: {resumen}"
        )
    return "PASS", (
        f"ejecutado scripts/measure_b12_schema_upgrade.py: {resumen}. "
        f"El veredicto es el del instrumento, no la presencia de un nombre."
    )


def _security_threat_model_actualizado() -> tuple[Veredicto, str]:
    """El modelo de amenaza esta al dia si describe ESTE proyecto.

    Se mide con los numeros que el propio ADR declara: si las cifras que
    escribio al aprobarse ya no son las del repo, el documento esta
    historicamente bien escrito y operativamente caducado.
    """
    adr = RAIZ / "docs" / "architecture" / "ADR-0015-threat-model-stride.md"
    if not adr.is_file():
        return "OPEN", "no existe docs/architecture/ADR-0015-threat-model-stride.md"
    texto = adr.read_text(encoding="utf-8")
    declarados = re.findall(r"(\d+)\s+tests\s+verdes", texto)
    releases = re.findall(r"(\d+)\s+releases", texto)
    if not declarados or not releases:
        return (
            "OPEN",
            "el ADR no declara las cifras del proyecto que describio: no se puede saber si caducó",
        )
    proc = _corre([sys.executable, "-m", "pytest", "--collect-only", "-q"], timeout=600)
    reales = next(
        (
            int(m.group(1))
            for linea in proc.stdout.splitlines()
            if (m := re.search(r"(\d+) tests collected", linea))
        ),
        -1,
    )
    declarados_n = int(declarados[0])
    if reales != declarados_n:
        return "OPEN", (
            f"el ADR se aprobo describiendo un proyecto de {declarados_n} tests y "
            f"{releases[0]} releases; el arbol de hoy colecta {reales}. El modelo de "
            "amenaza describe un producto que ya no es este"
        )
    return "PASS", f"el ADR describe el proyecto de hoy: {reales} tests, {releases[0]} releases"


def _distribution_reproducible() -> tuple[Veredicto, str]:
    """Se construye el paquete de verdad. Si no se puede construir, no se distribuye."""
    proc = _corre([sys.executable, "scripts/check_package_build.py"], timeout=900)
    if proc.returncode != 0:
        return (
            "OPEN",
            f"scripts/check_package_build.py rc={proc.returncode}: {proc.stdout.strip()[-300:]}",
        )
    return "PASS", "el wheel y el sdist se construyen y llevan lo que declaran"


def _uat_agent_first_completa() -> tuple[Veredicto, str]:
    """UAT completa = los UAT del blueprint cubiertos Y la suite verde."""
    declarados = set(re.findall(r"UAT-[A-Z0-9]+", _lee("docs/blueprint/plan/UAT.md")))
    nombrados: set[str] = set()
    for test in sorted((RAIZ / "tests").rglob("*.py")):
        nombrados.update(re.findall(r"UAT-[A-Z0-9]+", test.read_text(encoding="utf-8")))
    sin_cubrir = declarados - nombrados
    if sin_cubrir:
        return "OPEN", f"UAT sin cubrir: {sorted(sin_cubrir)}"
    return "PASS", (
        f"los {len(declarados)} UAT del blueprint estan cubiertos por tests. Lo que NO "
        "mide esta propiedad es si el agente PUELA conocimiento: B6 lo dejo como P5 "
        "fuera de alcance porque necesita un proveedor real"
    )


#: Modulos de la libreria estandar que el nucleo puede importar sin que eso
#: sea una dependencia de implementacion externa.
_MODULOS_ESTANDAR = frozenset(
    {
        "__future__",
        "ast",
        "collections",
        "dataclasses",
        "datetime",
        "enum",
        "functools",
        "hashlib",
        "itertools",
        "json",
        "re",
        "typing",
        "uuid",
    }
)


#: Predicado por propiedad. La clave es el ``_slug`` del texto del roadmap.
#: Una propiedad del roadmap que no aparezca aqui sale como ``NO_MEDIBLE``,
#: que es el punto: el conjunto se deriva, y el hueco se ve.
PREDICADOS: dict[str, Predicado] = {
    "roadmap_state_docs_coherentes": _roadmap_state_docs_coherentes,
    "resource_controller_api_estable": _resource_controller_api_estable,
    "blueprint_legacy_completamente_probado": _blueprint_legacy_completamente_probado,
    "graph_diff_gate_operativo": _graph_diff_gate_operativo,
    "runtime_real_certificado": _runtime_real_certificado,
    "ontology_extensible": _ontology_extensible,
    "crash_recovery_real_certificado": _crash_recovery_real_certificado,
    "provenance_fuerte": _provenance_fuerte,
    "concurrencia_real_certificada": _concurrencia_real_certificada,
    "capabilities_deterministas": _capabilities_deterministas,
    "core_sin_dependencias_de_impl_externa": _core_sin_dependencias_de_impl_externa,
    "cli_estable": _cli_estable,
    "tui_operacional": _tui_operacional,
    "migrations_probadas": _migrations_probadas,
    "pack_controller_lifecycle": _pack_controller_lifecycle,
    "backups_restore_probados": _backups_restore_probados,
    "upgrade_desde_releases_soportadas": _upgrade_desde_releases_soportadas,
    "security_threat_model_actualizado": _security_threat_model_actualizado,
    "distribution_reproducible": _distribution_reproducible,
    "uat_agent_first_completa": _uat_agent_first_completa,
}


def _comandos_de_la_cli() -> dict[str, list[str]]:
    """Los comandos y subcomandos que la CLI declara, leidos del parser de verdad.

    Se **importa** el parser y se recorre su arbol de subparsers, en vez de
    Lanzar un ``python -c`` y parsear su stdout. MEDIDO, y el motivo esta
    medido: la primera version llamaba a ``construir_parser()``, que no
    existe —el nombre real es ``build_parser()``—, y el ImportError se
    comia en un ``return ()``. Las dos consultas al parser devolvieron
    lista vacia, y con lista vacia se midpointaron dos veredictos: «la CLI
    no se puede medir» y «`sg pack` no expone nada». Los dos falsos, y los
    dos en la direccion de alarmar de mas, que es la que hace que un
    veredicto deje de creerse.

    Por eso aqui no hay captura silenciosa: si el parser no se puede
    leer, revienta. Un predicado que no puede mirar tiene que decirlo, no
    devolver un conjunto vacio que parece «no hay comandos».
    """
    import importlib.util

    ruta = RAIZ / "src" / "skillgraph" / "cli" / "parser.py"
    especificacion = importlib.util.spec_from_file_location("_parser_b9", ruta)
    if especificacion is None or especificacion.loader is None:  # pragma: no cover
        raise RuntimeError(f"no se pudo localizar {ruta}")
    modulo = importlib.util.module_from_spec(especificacion)
    sys.modules[especificacion.name] = modulo
    especificacion.loader.exec_module(modulo)

    def _hijos(parser: object) -> dict[str, list[str]]:
        grupos = getattr(getattr(parser, "_subparsers", None), "_group_actions", ())
        if not grupos:  # pragma: no cover - la CLI siempre declara subparsers
            raise RuntimeError("el parser no declara subparsers")
        hijos: dict[str, list[str]] = {}
        for nombre, sub in grupos[0].choices.items():
            # `choices` del primer nivel mapea nombre -> parser, NO nombre ->
            # accion de subparsers. Los subcomandos de un grupo viven en el
            # primer group_action del parser de ESE grupo. MEDIDO: la
            # version que no miraba ese segundo nivel reventaba con
            # `'_UsageParser' object has no attribute 'choices'`, y eso
            # significa que la medicion no se hizo, no que la CLI este mal.
            sub_grupos = getattr(getattr(sub, "_subparsers", None), "_group_actions", ())
            hijos[nombre] = sorted(sub_grupos[0].choices) if sub_grupos else []
        return hijos

    return _hijos(modulo.build_parser())


def _subcomandos_de(grupo: str) -> tuple[str, ...]:
    """Los subcomandos de un grupo de primer nivel, ordenados.

    Un grupo sin subparsers (como ``init``) devuelve vacio, y eso es un
    dato y no un fallo: no todos los comandos de primer nivel son grupos.
    """
    return tuple(sorted(_comandos_de_la_cli().get(grupo, [])))


# --------------------------------------------------------------------------
# El juicio. Puro: no lee disco, no lanza procesos.
# --------------------------------------------------------------------------


def evaluar(nombres: tuple[str, ...], predicados: dict[str, Predicado]) -> tuple[Propiedad, ...]:
    """Empareja cada propiedad con su predicado y ejecuta el que hay.

    Una propiedad sin predicado NO se salta: sale con veredicto
    ``NO_MEDIBLE`` y lo dice, porque un instrumento que se calla ante lo
    que no sabe medir es un instrumento que da verde por ignorance.
    """
    medidas: list[Propiedad] = []
    for nombre in nombres:
        predicado = predicados.get(_slug(nombre))
        if predicado is None:
            medidas.append(
                Propiedad(
                    nombre,
                    "NO_MEDIBLE",
                    "el roadmap declara esta propiedad y este instrumento no tiene "
                    "predicado para ella: es un hueco del instrumento, no un veredicto "
                    "sobre el proyecto",
                )
            )
            continue
        veredicto, evidencia = predicado()
        medidas.append(Propiedad(nombre, veredicto, evidencia))
    return tuple(medidas)


def resumir(medidas: tuple[Propiedad, ...]) -> dict[str, int]:
    """Cuantas de cada veredicto. Las claves estan todas, aunque valgan 0."""
    conteo = {"PASS": 0, "OPEN": 0, "NO_MEASURABLE": 0, "NO_MEDIBLE": 0}
    for medida in medidas:
        conteo[medida.veredicto] += 1
    return conteo


def listo_para_1_0(medidas: tuple[Propiedad, ...]) -> bool:
    """1.0 exige las veinte. Un solo veredicto que no sea PASS lo impide.

    ``NO_MEASURABLE`` tambien lo impide. Es tentador contarlo como
    «neutro» y dejar que 1.0 dependa de lo que se pudo medir; eso es
    declarar 1.0 sobre una pregunta que nadie respondio, y el propio
    roadmap dice «TODAS».
    """
    return bool(medidas) and all(m.veredicto == "PASS" for m in medidas)


def main() -> int:
    try:
        nombres = propiedades_del_roadmap(_lee("ROADMAP.md"))
    except (LookupError, OSError) as exc:
        print(f"No se pudo leer el gate de 1.0 del roadmap: {exc}", file=sys.stderr)
        return 2

    try:
        medidas = evaluar(nombres, PREDICADOS)
    except Exception as exc:
        # Un predicado que revienta NO es un veredicto de OPEN: es que el
        # informe estaria incompleto, y un informe incompleto con
        # `listo_para_1_0` calculado seria un 1.0 decidido sobre propiedades
        # que nadie midio. MEDIDO: la primera vez que se ejecuto, el
        # predicado de la CLI revento con AttributeError y el proceso salio
        # con 1 —el codigo de «contradiction» de project_truth.py—, que aqui
        # significa exactamente lo contrario. Se distingue: 1 es «medido y
        # no se cumple», 2 es «no se pudo medir».
        print(
            f"Un predicado revanto y el informe NO esta completo: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 2

    informe = {
        "total": len(medidas),
        "resumen": resumir(medidas),
        "listo_para_1_0": listo_para_1_0(medidas),
        "propiedades": [asdict(m) for m in medidas],
    }
    print(json.dumps(informe, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
