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
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
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


#: Las dos clases de evidencia que puede tener una propiedad. No es una escala
#: de calidad: las dos son validas, y lo que se declara es CUAL es cada una.
#:
#: - ``ejecutada``: el veredicto salio de CORRER algo —un subproceso, un
#:   subproceso que construye un paquete— y mirar lo que devolvio. Si el
#:   proyecto cambia, el veredicto cambia solo.
#: - ``derivada``: el veredicto salio de LEER el arbol. Es una afirmacion
#:   sobre lo que el codigo dice, no sobre lo que hace.
#:
#: Las dos son legítimas y hay que decirlo, porque hasta B15 no habia manera de
#: saber cual era cual: los dieciocho PASS salian en la misma lista y con la
#: misma tipografía. Un PASS ``ejecutada`` se cae solo cuando el proyecto se
#: rompe; un PASS ``derivada`` solo se cae si alguien vuelve a medirlo.
ClaseEvidencia = Literal["ejecutada", "derivada"]


#: Nombres de funcion que lanzan un programa. La lista es corta a proposito: lo
#: que se busca es «sale un proceso hijo», y anadir nombres de mas convertiria
#: una clasificacion en una lista de sinónimos que hay que mantener.
_LANZA_PROCESO = frozenset({"run", "check_output", "check_call", "Popen", "call"})


def _grafo_del_modulo(fuente: str) -> dict[str, frozenset[str]]:
    """Quien llama a quien, **dentro de este fichero**.

    Se construye desde el AST y no desde una lista: un predicado puede llegar a
    lanzar un proceso a traves de un helper, y un helper a traves de otro. Si
    el grafo se escribiera a mano, bastaria con que un helper dejara de
    nombrar al proceso para que un ``ejecutada`` se declarara ``derivada`` sin
    que nadie lo decidiera.

    **Por que recibe el texto y no lee `__file__`.** MEDIDO: leer el fichero
    desde dentro hace la funcion IMPOSIBLE de probar con codigo deformado, que
    es la unica prueba que importa — que la clase siga a lo que el codigo hace
    y no a una lista. Un guard que no se puede deformar es un guard que solo
    sabe pasar. Con el texto como parametro, un test puede anadir un
    `subprocess.run` a un predicado `derivada` y exigir que la clase gire, sin
    tocar el fichero real.
    """
    arbol = ast.parse(fuente)
    definidos = {
        nodo.name
        for nodo in ast.walk(arbol)
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    grafo: dict[str, frozenset[str]] = {}
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        llama: set[str] = set()
        for sub in ast.walk(nodo):
            if not isinstance(sub, ast.Call):
                continue
            func = sub.func
            nombre = None
            if isinstance(func, ast.Name):
                nombre = func.id
            elif isinstance(func, ast.Attribute) and func.attr in _LANZA_PROCESO:
                # `subprocess.run(...)` y `subprocess.check_output(...)`:
                # el atributo ES la senal de que sale un proceso.
                valor = func.value
                if isinstance(valor, ast.Name) and valor.id == "subprocess":
                    llama.add("subprocess")
            if nombre in definidos:
                llama.add(nombre)
        grafo[nodo.name] = frozenset(llama) & (definidos | {"subprocess"})
    return grafo


def _alcanza_proceso(nombre: str, grafo: dict[str, frozenset[str]], visto: frozenset[str]) -> bool:
    """Si desde `nombre` se llega a `subprocess`, por muchas capas que sean."""
    if nombre in visto:
        return False
    for siguiente in grafo.get(nombre, frozenset()):
        if siguiente == "subprocess" or _alcanza_proceso(siguiente, grafo, visto | {nombre}):
            return True
    return False


#: Los predicados se registran en `PREDICADOS` con un `_` delante del slug.
#: MEDIDO: la primera version de esta funcion buscaba el slug a secas, no lo
#: encontraba, y devolvia "derivada" **por defecto** — veinte de veinte, con la
#: autoridad de un `print` y ninguna advertencia. Era falso: seis de esos
#: predicados lanzan subproceso. Un fallo de busqueda que devuelve un valor en
#: vez de decir «no lo se» es el mismo defecto que este bloque persigue, y lo
#: primero que produjo fue, exactamente, el falso que venia a cerrar.
PREFIJO_PREDICADO = "_"


def _funcion_del_predicado(slug: str, grafo: dict[str, frozenset[str]]) -> str:
    """El nombre de la funcion que implementa este slug, o LVE.

    Levanta en vez de devolver un valor por defecto. La razon esta en la
    docstring de arriba: un nombre que no se encuentra NO es «no ejecuta», es
    «no lo se», y las dos cosas tienen que verse distinto en la salida.
    """
    candidatos = (PREFIJO_PREDICADO + slug, slug)
    for nombre in candidatos:
        if nombre in grafo:
            return nombre
    raise LookupError(
        f"el slug {slug!r} no corresponde a ninguna funcion de este modulo. Los "
        f"predicados se registran en PREDICADOS como {PREFIJO_PREDICADO!r} + slug; "
        f"buscar solo uno de los dos, y no beiden, devuelve una clase equivocada sin "
        f"avisar. Es el fallo que MEDIDO dio veinte 'derivada' sobre una mitad de "
        f"predicados que si ejecutan."
    )


def clase_de_evidencia(slug: str, fuente: str | None = None) -> ClaseEvidencia:
    """Si el predicado de esta propiedad EJECUTA o solo DERIVA. Del arbol.

    **Por que esto no es una lista escrita a mano.** Dieciocho lineas de
    ``"roadmap_estable": "ejecutada"`` serian una segunda fuente de verdad que
    divergiria de la primera en cuanto alguien anadiera un helper, y divergiria
    en silencio: el gate seguiria imprimiendo PASS con una clase que ya no
    describe lo que hace. Es la trampa de WI-106 y la de WI-99, dos veces mas.

    Y por que LVE si no encuentra el predicado, en vez de asumir `derivada`:
    asumir es exactamente el fallo medido en la primera version de esta
    funcion.
    """
    texto = Path(__file__).read_text(encoding="utf-8") if fuente is None else fuente
    grafo = _grafo_del_modulo(texto)
    funcion = _funcion_del_predicado(slug, grafo)
    return "ejecutada" if _alcanza_proceso(funcion, grafo, frozenset()) else "derivada"


@dataclass(frozen=True, slots=True)
class Propiedad:
    """Una propiedad del gate y lo que el instrumento pudo decir de ella.

    ``clase_evidencia`` NO se pasa: sale de ``clase_de_evidencia`` sobre el
    propio slug. Que el dataclass la derive y no la reciba es lo que hace
    imposible que un ``ejecutada`` se declare a mano.
    """

    nombre: str
    veredicto: Estado
    evidencia: str
    clase_evidencia: ClaseEvidencia = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "clase_evidencia", clase_de_evidencia(_slug(self.nombre)))


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


def _paquete_de(fichero: Path) -> tuple[str, ...]:
    """El PAQUETE al que pertenece un fichero, en partes y respecto a `src/`.

    MEDIDO, y hace falta porque los imports relativos **no tienen nombre**: son
    una cantidad de puntos mas un trozo, y solo significan algo contra el
    paquete del que salen. Un `from ..platform import x` en
    `src/skillgraph/core/runtime_types.py` vale `skillgraph.platform`, y sin
    esto no hay forma de saberlo salvo a mano.

    **MEDIDO TAMBIEN, Y ESTO FUE UN DEFECTO MIO AL ESCRIBIRLO.** La primera
    version hacia `pop()` SOLO cuando el fichero se llamaba `__init__.py`, y en
    el resto de los casos no quitaba nada: devolvia
    `('skillgraph', 'core', 'runtime_types')` —el MODULO, no el PAQUETE—. Con
    ese error, un `from ..platform.storage import ...` de nivel 2 resolvia a
    `skillgraph.core.platform.storage`, que **empieza por `skillgraph.core`**,
    luego el predicado lo descartaba por ser del nucleo y daba PASS. O sea que
    el arreglo arreglaba el recuento —los imports pasaron de 5 a 6— y dejaba
    el defecto entero, que es la forma mas traicionera de arreglar algo: el
    numero se mueve, luego parece que funciona.

    El condicional era ademas redundante: en los dos casos hay que quitar el
    ultimo trozo. En `__init__.py` ese trozo es el propio nombre del paquete; en
    cualquier otro es el modulo que esta DENTRO del paquete. Los dos se van.
    """
    relativo = fichero.relative_to(RAIZ / "src").with_suffix("")
    partes = list(relativo.parts)
    partes.pop()
    return tuple(partes)


def _resuelve_import_relativo(paquete: tuple[str, ...], nivel: int, modulo: str | None) -> str:
    """A que modulo absoluto apunta un `from ...x import y` de `nivel` puntos.

    `nivel == 0` es un import absoluto y no pasa por aqui. `nivel == 1` es «este
    paquete»; `nivel == 2` es el de arriba, y asi sucesivamente.

    **Y QUE PASA CUANDO EL NIVEL SE SALE DEL PAQUETE.** MEDIDO: subir de mas es
    un error de Python en tiempo de importacion, y un predicado que lo
    aceptara en silencio se estaria inventando un nombre. Aqui se devuelve una
    cadena vacia, que el llamante cuenta como un modulo que **no se puede
    resolver** —que es un dato, y no un fallo del recorrido—. Es lo que
    distingue «mire y no hay nada» de «mire y hay algo que no entiendo».
    """
    base = list(paquete[: len(paquete) - (nivel - 1)]) if nivel > 0 else []
    if len(base) < 0:  # pragma: no cover - `nivel` es un entero positivo
        return ""
    if nivel - 1 > len(paquete):
        return ""
    if modulo:
        base.extend(modulo.split("."))
    return ".".join(base)


def _imports_de(paquete: str) -> tuple[str, ...]:
    """Todos los modulos que importan los ficheros de un paquete de ``src``.

    Se recorre el arbol de verdad y no una lista escrita aqui: un paquete
    nuevo tiene que entrar en la medicion por existir, no por que alguien
    se acuerde de anadirlo.

    **MEDIDO, Y ESTA ERA LA MITAD QUE NO SE MIRABA.** La version anterior exigia
    `nodo.level == 0`, o sea que solo contaba los imports ABSOLUTOS, y todo
    import RELATIVO se le escapaba. Y como `core/` esta en
    `src/skillgraph/core/`, un `from ..platform.storage import Storage` tiene
    `level == 2` y **sale de `core/` entero**. Anadido ese import de verdad a un
    modulo del nucleo, la propiedad daba PASS con la MISMA cadena de evidencia
    que el caso limpio, byte a byte: un veredicto que no puede distinguir «el
    nucleo esta limpio» de «no he mirado la mitad de la superficie».

    Y lo que la hace mas peligrosa: MEDIDO, `core/` **no usa hoy ningun import
    relativo**. La superficie esta vacia, y una superficie vacia no se mira
    porque no hay nada que mirar.

    Por eso los relativos se resuelven a su nombre absoluto en vez de
    ignorarse. Lo que **no** hace este bloque es prohibirlos: que `core/` pueda
    escribir `from .errors import ...` es correcto, y forzarle a escribir
    `from skillgraph.core.errors import ...` para que un predicado lo vea es
    cambiar el codigo para que el guard quede bien.
    """
    raices = sorted((RAIZ / "src" / "skillgraph" / paquete).rglob("*.py"))
    encontrados: set[str] = set()
    for fichero in raices:
        arbol = ast.parse(fichero.read_text(encoding="utf-8"), filename=str(fichero))
        suyo = _paquete_de(fichero)
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Import):
                encontrados.update(alias.name for alias in nodo.names)
            elif isinstance(nodo, ast.ImportFrom):
                if nodo.level == 0:
                    if nodo.module:
                        encontrados.add(nodo.module)
                    continue
                resuelto = _resuelve_import_relativo(suyo, nodo.level, nodo.module)
                if resuelto:
                    encontrados.add(resuelto)
    return tuple(sorted(encontrados))


def _ficheros_de(paquete: str) -> int:
    """Cuantos ficheros recorre `_imports_de` para ese paquete.

    MEDIDO: la evidencia de `core sin dependencias de impl. externa` decia
    «core/ solo importa de si mismo y de la estandar (5 modulos)». Y `core/`
    tiene **cuatro** ficheros: la cifra era el numero de nombres de import
    DISTINTOS, y no de modulos. Y no decia cuantos ficheros se habian
    recorrido, luego quien lo leia no podia saber si el recorrido estaba
    completo —que es la otra mitad del defecto que B16 cerro: un PASS cuya
    evidencia no describe lo que recorrio—.

    Se expone como funcion y no como un segundo `rglob` dentro del predicado
    porque **las dos cifras tienen que salir del mismo recorrido**. Dos
    recorridos que cuentan lo mismo no pueden desincronizarse, pero dos
    preguntas sobre «los ficheros de core» escritas en dos sitios si.
    """
    return len(list((RAIZ / "src" / "skillgraph" / paquete).rglob("*.py")))


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
    """Ontologia extensible = el nucleo no DEPENDE de ningun tipo de recurso.

    Es la forma ejecutable de la propiedad: si ``core/`` no depende de los
    tipos que viven en los paquetes de recurso, anadir uno no obliga a tocar el
    nucleo. Y se mide con AST, no con grep, para que un nombre de recurso en el
    docstring de un modulo no conta como dependencia.

    **LO QUE ESTE PREDICADO TENIA Y ERA PEOR QUE UNA LISTA.** Medido, y con las
    dos caras, que es lo que lo hace un defecto:

    - De los ocho tipos de recurso que el proyecto DECLARA de verdad,
      ``^[A-Z][A-Za-z]*Pack$`` ve **cero**. Con
      ``from skillgraph.packaging.manifest import PackManifest`` en ``core/`` —
      el tipo CENTRAL del proyecto, el manifiesto de un pack — el veredicto era
      ``PASS`` con una evidencia byte a byte identica a la del caso limpio.
    - El unico nombre que el patron contaba era ``FilaDePack``, que es una FILA
      de la tabla de packs, no un tipo de recurso. Con el import puesto salia
      ``OPEN`` acusando al nucleo de depender de los recursos.

    **Y LO QUE HACE ESPECIFICO, MEDIDO: el gate se contradia a si mismo.**
    Con ese mismo import, ``core sin dependencias de impl. externa`` daba
    ``OPEN`` y este daba ``PASS``. Dos propiedades del mismo gate, sobre el
    mismo hecho, con veredictos distintos; 7 contradicciones de 9 casos medidos
    sobre la superficie real del proyecto.

    **POR QUE UN PATRON NO ES UNA DEFINICION.** B16 paso este predicado de
    cadenas a imports y atributos, y el endurecimiento fue sobre el FORMATO de
    la mirada: una vista mas aguda de una cosa que no es la que hay. «Anadir un
    recurso no obliga a tocar el nucleo» no se cumple mirando COMO SE ESCRIBEN
    los nombres; se cumple preguntando A QUE CONJUNTO PERTENECE cada nombre. Y
    el conjunto se deriva del arbol, de los paquetes que el proyecto llama
    recursos por el nombre de su directorio.

    **Y POR QUE UN DOCSTRING NO ES UNA DEPENDENCIA, QUE ES UNA DECISION.**
    MEDIDO: ``core/`` menciona ``WorkflowPlan`` en tres docstrings y en ninguna
    linea de codigo. Documentar la frontera es lo contrario de depender de ella.
    Contarlos seria un ``OPEN`` sobre una frontera respetada —el fallo
    conservador que B18 le atribuyo a la lista de la estandar—. Los docstrings
    que nombran un recurso se CUENTAN y se DICEN, que es informacion, y no abren
    el veredicto.
    """
    recursos = _tipos_de_recurso()
    dependencias: dict[str, set[str]] = {}
    menciones: set[str] = set()
    ficheros = 0
    nombres_mirados = 0
    for modulo in sorted((RAIZ / "src" / "skillgraph" / "core").rglob("*.py")):
        ficheros += 1
        rel = str(modulo.relative_to(RAIZ))
        arbol = ast.parse(modulo.read_text(encoding="utf-8"), filename=str(modulo))
        docstrings = _docstrings_de(arbol)
        # (1) Los IMPORTS, que son dependencias por definicion.
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.ImportFrom) and nodo.module:
                for alias in nodo.names:
                    if alias.name in recursos:
                        dependencias.setdefault(alias.name, set()).add(
                            f"{rel} (import de {nodo.module})"
                        )
            elif isinstance(nodo, ast.Import):
                for alias in nodo.names:
                    for trozo in alias.name.split("."):
                        if trozo in recursos:
                            dependencias.setdefault(trozo, set()).add(
                                f"{rel} (import de {alias.name})"
                            )
            # (2) Los ATRIBUTOS y las ANOTACIONES de tipo: `registry.BrickType`
            # llega al nucleo como atributo, y una anotacion
            # `-> CompiledResource` es una dependencia que no necesita ni un
            # import, porque el nucleo no tiene que ejecutar nada para estar
            # atado al tipo.
            #
            # El ejemplo de este comentario solia ser `packs.DomainPack`, que no
            # es codigo: no hay modulo `packs`, y `DomainPack` no es un simbolo
            # sino el `kind` de un recurso escrito como cadena. MEDIDO EN B20.
            # Un ejemplo inventado en un comentario no rompe nada, pero siembra
            # justo el patron-por-forma que este predicado sufria.
            elif isinstance(nodo, ast.Attribute) and nodo.attr in recursos:
                dependencias.setdefault(nodo.attr, set()).add(f"{rel} (atributo)")
            elif isinstance(nodo, ast.Name) and nodo.id in recursos:
                dependencias.setdefault(nodo.id, set()).add(f"{rel} (nombre)")

        # (3) Las CADENAS, separando lo que se EJECUTA de lo que DOCUMENTA.
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
                es_docstring = id(nodo) in docstrings
                for tipo in recursos:
                    if re.search(rf"\b{re.escape(tipo)}\b", nodo.value):
                        nombres_mirados += 1
                        if es_docstring:
                            menciones.add(f"{tipo} ({rel}, docstring)")
                        else:
                            dependencias.setdefault(tipo, set()).add(f"{rel} (cadena)")
    base = (
        f"MEDIDO sobre {ficheros} ficheros de core/ y {len(recursos)} tipos de recurso, "
        f"derivados de los paquetes {', '.join(PAQUETES_DE_RECURSO)} por AST"
    )
    if dependencias:
        detalle = "; ".join(
            f"{tipo} en {sorted(donde)[0]}" for tipo, donde in sorted(dependencias.items())
        )
        return (
            "OPEN",
            f"core/ DEPENDA de {len(dependencias)} tipo(s) de recurso — {detalle}. "
            f"El nucleo depende de los recursos, y la propiedad dice que no depende: "
            f"anadir un recurso pasaria a obligar a tocar el nucleo. {base}",
        )
    documentado = ""
    if menciones:
        documentado = (
            f" Documenta ademas {len(menciones)} tipo(s) en docstrings — "
            f"{'; '.join(sorted(menciones)[:6])}"
            f"{'...' if len(menciones) > 6 else ''} — lo cual NO es dependencia: "
            f"documentar la frontera es lo contrario de depender de ella, y por eso no "
            f"abre el veredicto pero se dice."
        )
    return (
        "PASS",
        f"core/ no depende de ningun tipo de recurso: ni por import, ni por atributo, "
        f"ni por anotacion, ni por cadena que se ejecute. {base}"
        f"{documentado}",
    )


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


#: Que cuenta como «tipo de recurso» para la frontera del nucleo.
#:
#: **ESTO ERA UN SUFIJO ESCRITO A MANO, Y ERA PEOR QUE UNA LISTA. MEDIDO, y
#: con las dos caras, que es lo que lo hace un defecto y no una rudeza.**
#:
#: `_TIPO_DE_RECURSO = ^[A-Z][A-Za-z]*Pack$` decia, en el comentario de al lado,
#: que no escribir la lista de tipos evita tener una segunda fuente de verdad. El
#: razonamiento es correcto sobre una cosa y no ve la otra: **un patron por forma
#: ES una lista, una mas corta y peor**, porque decide como se ESCRIBE un nombre
#: en vez de a que conjunto PERTENECE. Y medido, sobre el arbol real:
#:
#:   · de 8 tipos de recurso que el proyecto DECLARA de verdad —PackManifest,
#:     CompiledResource, CapabilitySpec, BrickType, Catalog, Brick— el patron
#:     ve CERO. Con `from skillgraph.packaging.manifest import
#:     PackManifest` puesto en core/, que es el tipo CENTRAL del proyecto, el
#:     veredicto es PASS con una evidencia byte a byte IDENTICA a la del caso
#:     limpio. El patron no ve lo que importa.
#:
#:   · el UNICO nombre que el patron cuenta es `FilaDePack`, que es una fila de
#:     la tabla de packs, no un tipo de recurso. Con el import puesto, el
#:     veredicto es OPEN acusando al nucleo de depender de los recursos. La
#:     divergencia va en las DOS direcciones.
#:
#: **Y LO QUE HACE ESPEFICO, MEDIDO: el gate se contradecía a si mismo.** Con
#: ese mismo import, `core sin dependencias de impl. externa` —que B18
#: endurecio hace un bloque— da OPEN y `ontology extensible` da PASS. Dos
#: propiedades del mismo gate, sobre el mismo hecho, con veredictos distintos.
#: MEDIDO sobre la superficie real: 7 contradicciones de 9 casos.
#:
#: **POR QUE ERA UN PATRON Y NO UNA LISTA, Y POR QUE ESO ES JUSTO EL DEFECTO.**
#: B16 paso este predicado de cadenas a imports y atributos, y el endurecimiento
#: fue sobre el FORMATO de la mirada: le dio una vista mas aguda de una cosa que
#: no es la que hay. La propiedad «anadir un recurso no obliga a tocar el
#: nucleo» no se cumple mirando como se escriben los nombres: se cumple
#: preguntando a que conjunto pertenece cada nombre.
#:
#: **LO QUE ENTRA: el conjunto se DERIVA del arbol**, de los paquetes que el
#: PROPIO proyecto llama recursos por el nombre de su directorio. Se declara el
#: nombre del PAQUETE —dos entradas— y no la lista de sus clases, que son
#: veintitantas y cambian. Un nombre de directorio es un hecho del proyecto, y
#: `resources/` se llama `resources/` porque es donde viven los recursos.
#:
#: **Y LO QUE NO ENTRA, QUE ES UNA DECISION Y NO UN OLVIDO: los docstrings NO
#: son dependencia.** MEDIDO: core/ menciona `WorkflowPlan` en tres docstrings y
#: en ninguna linea de codigo. Documentar la frontera es lo CONTRARIO de depender
#: de ella: un docstring que explica un recurso es el nucleo diciendo donde esta
#: el limite. Contarlos seria un OPEN sobre una frontera respetada —el fallo
#: conservador que B18 le atribuyo a la lista de la estandar—, y la distincion
#: entre un docstring y una cadena que se ejecuta es de AST, no de texto. Los
#: docstrings que nombran un recurso se CUENTAN y se DICEN en la evidencia, que
#: es informacion, y no abren el veredicto.
PAQUETES_DE_RECURSO = ("resources", "packaging")


def _tipos_de_recurso() -> dict[str, str]:
    """Los tipos de recurso del proyecto, DERIVADOS del arbol: {clase: modulo}.

    MEDIDO, y el numero importa porque es la cifra que faltaba: sin ella, una
    evidencia que dice «core/ no nombra ningun tipo de recurso» no permite saber
    quantos habia que no nombrar. Es el mismo fallo que la evidencia de B18, que
    decia «(5 modulos)» sobre un paquete de cuatro ficheros: no decia que
    recorrido, luego no decia si el recorrido estaba completo.
    """
    base = RAIZ / "src" / "skillgraph"
    tipos: dict[str, str] = {}
    for paquete in PAQUETES_DE_RECURSO:
        for modulo in sorted((base / paquete).rglob("*.py")):
            rel = str(modulo.relative_to(RAIZ))
            arbol = ast.parse(modulo.read_text(encoding="utf-8"), filename=str(modulo))
            for nodo in ast.walk(arbol):
                if isinstance(nodo, ast.ClassDef):
                    tipos.setdefault(nodo.name, rel)
    return tipos


def _docstrings_de(arbol: ast.AST) -> set[int]:
    """Los `id()` de los nodos Constant cuyo valor es un DOCSTRING.

    MEDIDO, Y ESTA FUNCION HA TENIDO DOS DEFECTOS, que son el mismo defecto.

    1. La primera version hacia `id(ast.get_docstring(nodo))`, que es el id de
       un **string**, no el del nodo `Constant` del arbol, luego la comparacion
       no coincidia nunca y el instrumento de medicion de B20 informo de «0
       docstrings» con `core/` llenandose de ellos.
    2. La segunda, ya con los nodos, solo miraba `body[0]` de cada modulo,
       clase o funcion. MEDIDO: eso encuentra los docstrings de verdad pero
       **pierde la documentacion suelta**, que en este repo es el patron del
       `NewType`::

           NodeName = NewType("NodeName", str)
           \"\"\"Identificador local de un nodo dentro de un WorkflowPlan.\"\"\"

       que es la segunda sentencia del cuerpo del modulo, no la primera, y es
       documentacion de manual. Con esa version el predicado daba ``OPEN`` sobre
       un arbol sano: dos tipos de recurso «mencionados», que lo eran solo en su
       documentacion. Un ``OPEN`` falso en estado sano es el fallo mas caro que
       puede tener un guard, porque entrena a su lector a no creerlo.

    **LO QUE SE ACEPTA COMO DOCUMENTACION, Y ES UNA DECISION.** Una
    `Expr(Constant(str))` en el cuerpo de un modulo, una clase o una funcion:
    Python exige que sea un string, y una sentencia suelta de ese tipo no hace
    nada mas que documentar. Quedan FUERA las cadenas que se ejecutan —una
    f-string, un argumento, un valor— porque esas no son prosa: son codigo que
    produce el texto que el nucleo emite.

    **Y POR QUE ESTO NO ES UN DETALLE DE IMPLEMENTACION.** Los dos defectos son
    la misma cosa: un clasificador escrito sin una prueba que diga que
    clasifica. Es el mismo patron que los cuatro fallos de B19, y el
    contrasalto es el mismo: un clasificador que devuelve siempre lo mismo no se
    nota hasta que se compara con un caso que se sabe.
    """
    ids: set[int] = set()
    cuerpos: list[list[ast.stmt]] = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            cuerpos.append(nodo.body)
    for cuerpo in cuerpos:
        for sentencia in cuerpo:
            if (
                isinstance(sentencia, ast.Expr)
                and isinstance(sentencia.value, ast.Constant)
                and isinstance(sentencia.value.value, str)
            ):
                ids.add(id(sentencia.value))
    return ids


#: Donde la version de las capabilities TIENE que vivir. El nombre de la
#: propiedad dice «el puerto, y solo el»; medir solo «que no haya dos» deja
#: abierta la mitad de la frase, que es la que importa: una constante que
#: todos importan desde un sitio que no es el puerto sigue siendo una
#: segunda fuente de verdad, solo que con una palabra menos.
#:
#: MEDIDO: la version anterior de este predicado solo contaba declarantes y
#: decia PASS con «se declara en un solo sitio: []» cuando no habia ninguno. Un
#: veredicto cuyo texto dice una lista vacia no es un veredicto sobre el
#: proyecto: es sobre su propia capacidad de contar.
PUERTO_DE_CAPABILITIES = "src/skillgraph/platform/ports/capabilities.py"


def _declara_la_version(modulo: Path) -> bool:
    r"""Si este modulo ASIGNA `CAPABILITY_VERSION`. Por AST, no por regex.

    MEDIDO: la busqueda por linea con `re.match(r"\s*CAPABILITY_VERSION\s*[:=]")`
    no ve una declaracion partida en varias lineas, ni una que lleve anotacion de
    tipo, ni una dentro de una clase. Es el mismo defecto que B13 cerro en el
    guard de SQL —mirar una forma del codigo que no es la que se ejecuta—.
    """
    arbol = ast.parse(modulo.read_text(encoding="utf-8"), filename=str(modulo))
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.AnnAssign):
            objetivo = nodo.target
        elif isinstance(nodo, ast.Assign):
            objetivo = nodo.targets[0] if nodo.targets else None
        else:
            continue
        for hijo in ast.walk(objetivo) if objetivo is not None else ():
            if isinstance(hijo, ast.Name) and hijo.id == "CAPABILITY_VERSION":
                return True
    return False


def _capabilities_deterministas() -> tuple[Veredicto, str]:
    """La version de una capability la declara EL PUERTO, y solo el.

    Si un adaptador vuelve a declarar su propia version, la determinista es
    mentira: dos adaptadores del mismo puerto pueden dejar de declarar lo
    mismo. Y si NADIE la declara, tambien: no hay version que sea
    determinista porque no hay version.
    """
    declarantes = sorted(
        str(modulo.relative_to(RAIZ))
        for modulo in (RAIZ / "src" / "skillgraph").rglob("*.py")
        if _declara_la_version(modulo)
    )
    if not declarantes:
        return (
            "OPEN",
            "NADIE declara CAPABILITY_VERSION: no hay version que pueda ser "
            "determinista, y este predicado antes de B16 devolvia PASS con la "
            "evidencia «se declara en un solo sitio: []»",
        )
    if len(declarantes) > 1:
        return "OPEN", f"CAPABILITY_VERSION se declara en mas de un sitio: {declarantes}"
    if declarantes[0] != PUERTO_DE_CAPABILITIES:
        return (
            "OPEN",
            f"CAPABILITY_VERSION se declara en {declarantes[0]}, y la propiedad "
            f"dice que la declara EL PUERTO ({PUERTO_DE_CAPABILITIES})",
        )
    return "PASS", f"CAPABILITY_VERSION la declara solo el puerto: {declarantes[0]}"


def _core_sin_dependencias_de_impl_externa() -> tuple[Veredicto, str]:
    """El nucleo no importa nada que no sea el nucleo o la libreria estandar.

    **MEDIDO, Y SON TRES DEFECTOS QUE TIENEN UNA RAIZ.** Este predicado no
    sabia que superficie estaba mirando, y por eso hay que decirlo en las tres
    formas en que se nota:

    1. **No miraba los imports RELATIVOS.** `_imports_de` exigia
       `nodo.level == 0`. Y como `core/` esta en `src/skillgraph/core/`, un
       `from ..platform.storage import Storage` tiene `level == 2` y sale de
       `core/` entero. Anadido ese import de verdad, la propiedad daba PASS
       **con la misma cadena de evidencia que el caso limpio, byte a byte**: un
       veredicto que no puede distinguir «el nucleo esta limpio» de «no he
       mirado la mitad de la superficie». Y MEDIDO, `core/` no usa hoy NINGUN
       import relativo, luego la superficie estaba vacia y una superficie vacia
       no se mira porque no hay nada que mirar.

    2. **La estandar eran trece renglones escritos a mano.** MEDIDO: el
       interprete sabe de 290. `pathlib`, `contextlib`, `abc`, `io`, `warnings`
       y `copy` son de la estandar y **no estaban en la lista**, luego un
       import legitimo de cualquiera de ellos en `core/` habria producido un
       `OPEN` sobre una frontera que se estaba respetando. Una propiedad que se
       pone roja por lo contrario es una propiedad que entrena a su lector a no
       creerla, y ese es un fallo aunque salga del lado conservador.

    3. **La evidencia decia «(5 modulos)» y no eran modulos.** Eran los nombres
       de import **distintos**, y no decia cuantos ficheros se habian
       recorrido —que son cuatro—. Una evidencia que no describe lo que
       recorrio no permite saber si el recorrido estaba completo.

    **LA RAIZ DE LAS TRES, Y POR QUE EL ARREGLO ES EL QUE ES.** «Que es de la
    estandar» es un **hecho del interprete** y se deriva de el. Que superficie
    se recorre es un **hecho del arbol** y se cuenta y se dice. Nada de esto se
    escribe a mano, porque escrito a mano se queda viejo en silencio —y una
    lista de trece que se queda vieja no avisa: simplemente empieza a dar
    veredictos que nadie reviso—.

    **Y LO QUE ESTE PREDICADO NO HACE, A PROPOSITO.** No prohibe los imports
    relativos. Que `core/` escriba `from .errors import ...` es correcto, y
    obligarle a escribir `from skillgraph.core.errors import ...` para que un
    predicado lo vea es cambiar el codigo para que el guard quede bien. Lo que
    faltaba era **mirarlos**, y ahora se miran.
    """
    externos: set[str] = set()
    for nombre in _imports_de("core"):
        if nombre.startswith("skillgraph.core"):
            continue
        if nombre.split(".")[0] in _MODULOS_ESTANDAR:
            continue
        externos.add(nombre)
    ficheros = _ficheros_de("core")
    vistos = len(_imports_de("core"))
    if externos:
        return (
            "OPEN",
            f"core/ depende de fuera de si mismo, MEDIDO sobre {ficheros} ficheros y "
            f"{vistos} imports (absolutos y relativos, ya resueltos): {sorted(externos)}. "
            f"El nucleo no puede depender de la implementacion: la frontera que declara "
            f"esta propiedad es la que permite anadir una capacidad sin tocarlo, y esa "
            f"frontera se comprueba con la version de la estandar del interprete "
            f"({_MODULOS_ESTANDAR_ORIGEN})",
        )
    return (
        "PASS",
        f"core/ no depende de fuera de si mismo, MEDIDO sobre {ficheros} ficheros y "
        f"{vistos} imports ABSOLUTOS Y RELATIVOS, ya resueltos a su nombre: todos son de "
        f"skillgraph.core o de la estandar segun {_MODULOS_ESTANDAR_ORIGEN} "
        f"({len(_MODULOS_ESTANDAR)} modulos de estandar reconocidos). La cifra de "
        f"ficheros va aqui porque sin ella no se puede saber si el recorrido fue completo",
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
    """Se mide EJECUTANDO el ciclo, no contando nombres de subcomandos.

    **LO QUE ESTE PREDICADO ERA, MEDIDO, Y NO ES UNA HIPOTESIS.** Decia
    «`sg pack` expone el ciclo completo: ['import', 'install', 'list',
    'load', 'remove', 'update']», y su unico trabajo era mirar si tres
    CADENAS estaban en un `dict` que salen del parser. La propiedad que
    declara es «el ciclo de vida que B8 nombro es install/update/remove»,
    y eso no es un nombre: es que `install` RECHACE lo que no encaja, que
    `update` exige que la version SUBA, y que `remove` de algo que no esta
    lo diga en vez de reventar.

    MEDIDO, con la decision de `install` rota en una COPIA del arbol —el
    `if` que levanta `ValidationError` cuando `motivos_de_incompatibilidad`
    devuelve motivos, y no `es_compatible`, que es la verdad del dominio y
    que no se toca porque romper las dos no mediria una—:

        gate   : PASS    <- leia NOMBRES
        B11 Q1 : PASS    <- leia NOMBRES, y es LITERALMENTE este predicado
        B11 Q2 : OPEN    <- EJECUTO install con un pack incompatible
        resumen: OPEN: 1 · PASS: 4

    **El ciclo estaba roto y la propiedad que lo declara estaba en verde.**

    Y el hallazgo mas uncomfortable no es del gate: es que **este
    predicado era Q1 del instrumento de B11**, y Q1 es la mas debil de las
    cinco —las otras cuatro ejecutan la CLI de verdad—. O sea que el gate
    llevaba tiempo decidiendo «el ciclo de vida existe» con la unica de las
    cinco preguntas que no lo prueba. Q1 lo sabe y lo dice en su docstring;
    no es que estea equivocado, es que estaba solo.

    Por eso aqui no se reimplementa el instrumento: se CORRE, que es la
    forma de B12 para `upgrade desde releases soportadas` y la de B10 para
    las superficies. Delegar y no reimplementar, porque dosDerivaciones son
    dos verdades y la que no se ejecuta es la que se queda vieja.

    **Y POR QUE NO SE TOCA Q1.** La pregunta «¿existen los comandos?» es una
    condicion necesaria y es barata; lo que no puede hacer es BASTAR, y con
    las cinco en AND deja de bastar. Cambiarla sin un instrumento que la
    reemplace seria perder cobertura, y este bloque no esta para eso.
    """
    proc = _corre([sys.executable, str(RAIZ / "scripts" / "measure_b11_pack_lifecycle.py")])
    salida = (proc.stdout + proc.stderr).strip()
    if not salida:
        return "NO_MEASURABLE", (
            f"scripts/measure_b11_pack_lifecycle.py no devolvio nada (rc={proc.returncode}). "
            "Un instrumento que no dice nada no es un instrumento que diga que no: "
            "este veredicto NO es «el ciclo esta roto» ni «el ciclo esta bien»"
        )
    preguntas = _preguntas_del_instrumento(salida)
    if proc.returncode != 0 and not preguntas:
        # MEDIDO: la primera version de este predicado caia aqui con el texto
        # «se ha EJECUTADO para saberlo» y «Caen 0 de 0 preguntas». Y no se
        # habia ejecutado NADA: el instrumento no arranco —rc=2, «can't open
        # file»—, y el predicado afirmaba una ejecucion que no habia ocurrido,
        # con un recuento de preguntas que era cero sobre cero. Lo cazo el
        # guard de este mismo bloque.
        #
        # Son dos preguntas distintas y no se pueden sumar: «¿el ciclo de vida
        # se sostiene?» y «¿puedo medir si se sostiene?». Un subproceso puede
        # no correr —sin `scripts/` en la copia, sin permiso, sin el
        # interprete— y su fallo no es un fallo del ciclo. Es el mismo defecto
        # que B14 cerro en `tests_colectados()`: publicar un dato de una
        # medicion que no se hizo, con la autoridad de quien si la hizo.
        return "NO_MEASURABLE", (
            f"NO SE HA PODIDO MEDIR: scripts/measure_b11_pack_lifecycle.py no ha "
            f"contestado (rc={proc.returncode}) y su salida no contiene ni una "
            f"pregunta con veredicto. Esto NO es «el ciclo de vida este roto»: es "
            f"«no se ha podido mirar», y son dos cosas con dos arreglos distintos —"
            f"uno en el entorno y otro en el ciclo—. Salida: {salida[-400:]}"
        )
    if proc.returncode != 0:
        caidas = [nombre for nombre, veredicto in preguntas if veredicto != "PASS"]
        detalle = (
            "; ".join(
                f"{nombre}: {veredicto}" for nombre, veredicto in preguntas if veredicto != "PASS"
            )
            or "sin detalle por pregunta"
        )
        return "OPEN", (
            f"el ciclo de vida de los packs NO se sostiene, y se ha EJECUTADO para "
            f"saberlo: scripts/measure_b11_pack_lifecycle.py rc={proc.returncode}. "
            f"Caen {len(caidas)} de {len(preguntas)} preguntas — {detalle}. "
            f"Que el ciclo exista como comando no lo prueba: lo prueba que instale, "
            f"rechace lo que no encaja y se pueda quitar. Salida: {salida[-400:]}"
        )
    return "PASS", (
        f"el ciclo de vida de los packs se ha EJECUTADO, no contado: "
        f"scripts/measure_b11_pack_lifecycle.py rc=0, "
        f"{len(preguntas)} de {len(preguntas)} preguntas en PASS — "
        + "; ".join(f"{nombre}: {veredicto}" for nombre, veredicto in preguntas)
        + ". Una de ellas EJECUCIA `install` con un pack incompatible y exigia que "
        "lo rechazara diciendo por que, que es lo que un nombre de subcomando no "
        "puede distinguir de un `def install(): pass`"
    )


def _preguntas_del_instrumento(salida: str) -> tuple[tuple[str, str], ...]:
    """Los veredictos por pregunta del instrumento, DERIVADOS de su salida.

    MEDIDO, y es la razon de que esto sea una funcion y no un `split` en el
    predicado: la instrumentacion tiene que venir de lo que el instrumento
    DICE, no de lo que este gate recuerda que dice. Si el formato cambia, lo
    que tiene que ponerse en rojo es la instrumentacion —que es lo que
    emitio el dato—, y no el consumidor.

    El formato es `[VEREDICTO] pregunta`, con el veredicto entre corchetes
    para que la alineacion de la tabla no lo parta.
    """
    preguntas: list[tuple[str, str]] = []
    for linea in salida.splitlines():
        limpia = linea.strip()
        if not limpia.startswith("["):
            continue
        cierre = limpia.find("]")
        if cierre < 0:
            continue
        veredicto = limpia[1:cierre].strip()
        nombre = limpia[cierre + 1 :].strip()
        if veredicto and nombre:
            preguntas.append((nombre, veredicto))
    return tuple(preguntas)


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
    """El modelo de amenaza esta al dia si CUBRE lo que el producto expone.

    **LO QUE ESTE PREDICADO ERA, Y POR QUE ERA UN DEFECTO.** Comparaba
    `tests declarados == tests colectados`, con la cifra que el propio ADR
    escribio al aprobarse. Tres cosas iban mal:

    1. Media una FOTO, no una propiedad. En cuanto se anadia un test, el ADR
       quedaba «caducado» sin que nadie hubiera tocado una sola linea del
       analisis. Un gate que se pone rojo por causas ajenas al objeto que
       vigila ensena a ignorarlo, que es peor que no tenerlo.
    2. Era un FALSO POSITIVO structural. Con 3254 tests contra 830
       declarados daba OPEN, y el veredicto era «el modelo describe un
       producto que ya no es este» —lo cual era verdad, pero por razones
       que la cifra no distinguishia: el modelo se habia quedado sin cubrir
       los packs, las migraciones y la carga de planes. Arreglarlo subiendo
       el numero habria hecho PASS un modelo igual de incompleto.
    3. Daba PASS a un documento que dijera lo que quisiera mientras los
       numeros cuadraran. Un modelo de amenaza que llama «OK» a una fuga
       entre tenants que existe —que es lo que ocurria— es exactamente el
       caso que este gate pretendia vigilar.

    Ahora se mide lo que el modelo tiene que cubrir: **las superficies**.
    Se EJECUTA la comprobacion en vez de comparar dos numeros, que es la
    forma que B10 demostro que es la unica que muerde.
    """
    proc = _corre(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "--no-header",
            "tests/test_b13_threat_model.py",
        ],
        timeout=900,
    )
    lineas = [linea for linea in proc.stdout.splitlines() if linea.strip()]
    resumen = lineas[-1] if lineas else f"sin salida (rc={proc.returncode})"
    if proc.returncode != 0:
        caidos = [
            linea.split("::", 1)[1].split(" ")[0]
            for linea in proc.stdout.splitlines()
            if linea.startswith("FAILED ")
        ]
        return "OPEN", (
            "el modelo de amenaza no sostiene lo que afirma: "
            f"{resumen}. Fallan {len(caidos)} comprobaciones: {sorted(caidos)[:6]}. "
            f"Se mide ejecutando scripts/ y tests/, no comparando una cifra."
        )
    return "PASS", (
        f"ejecutado tests/test_b13_threat_model.py: {resumen}. El veredicto es el "
        f"del guard: cada superficie del arbol esta enumerada y nombra la "
        f"prueba que la sostiene, y el aislamiento entre tenants se EJECUTA "
        f"en vez de declararse."
    )


#: El fichero que se toca entre las dos construcciones. Solo cambia su FECHA:
#: el contenido es identico, y se comprueba antes y despues.
_FICHERO_DE_FECHA = "src/skillgraph/__init__.py"


def _huella_de_entrada() -> str:
    """La huella de lo que hay en el ARBOL, que es lo que entra al paquete.

    **POR QUE ESTA FUNCION EXISTE, Y POR QUE NO PUEDE SER NADA MAS SENCILLO.**

    MEDIDO, y el defecto es de este clase: `distribution reproducible`
    construye dos veces y compara los BYTES. Si difieren, decia «la
    distribucion NO es reproducible». Y hay dos causas con DOS ACCIONES
    OPUESTAS:

      (a) el build del proyecto es irreproducible   -> se arregla el BUILD
      (b) la entrada cambio entre las dos             -> se arregla la MEDICION
                                                    -> se mide OTRA cosa

    El predicado no las distinguia. Y la que se carryo durante la certificacion
    de B18 fue la segunda, con un OPEN que acusa al proyecto de un defecto que
    no tiene: la distribucion ES reproducible, MEDIDO 8 de 8 construcciones con
    bytes iguales, con y sin tocar la fecha.

    **Y NO SE PUEDE AVERIGUAR DESDE EL ARTEFACTO.** Comparar el contenido de los
    dos paquetes no alcanza: si un fichero ya versionado cambia entre las dos
    construcciones, los dos artefactos son coherentes consigo mismos y aun
    asi se construyeron con entradas DISTINTAS. Hace falta el estado del arbol,
    y el unico sitio donde esta es el arbol de trabajo.

    **LO QUE YA EXISTIA Y NO ALCANZABA.** `sg_build_sdist_no_versionado`, en
    scripts/check_package_build.py, rechaza que el paquete lleve un fichero que
    git no versiona, con un mensaje que es exactamente el que haria falta. Es un
    buen guard y cubre la mitad del problema. La otra mitad es un fichero que SI
    esta versionado y que ha cambiado, y ese no lo ve: pregunta «¿git lo
    versiona?» y no «¿ha cambiado?».

    **POR QUE ESTA DERIVADA Y NO ESCRITA A MANO.** Las tres piezas que la
    componen —HEAD, el estado del arbol, y el diff contra HEAD— son hechos de
    git, y de git se leen. `git diff HEAD` es lo que aporta el CONTENIDO de lo
    modificado, que sin el seria un `git status` que solo ve nombres: dos
    ficheros con el mismo nombre y distinto contenido darian la misma huella.
    """
    proc_head = _corre(["git", "rev-parse", "HEAD"])
    proc_estado = _corre(["git", "status", "--porcelain", "-z"])
    proc_diff = _corre(["git", "diff", "HEAD"])
    if proc_head.returncode != 0:
        raise RuntimeError(
            f"git rev-parse devolvio {proc_head.returncode}: {proc_head.stderr.strip()[-300:]}"
        )
    # El separador NUL es lo que hace que la huella no se pueda construir por
    # casualidad con las tres partes pegadas: un nombre de fichero acaba en
    # blanco, y un sha no.
    crudo = "\0".join((proc_head.stdout, proc_estado.stdout, proc_diff.stdout))
    return hashlib.sha256(crudo.encode("utf-8", "surrogateescape")).hexdigest()


def _construye_en(destino: Path) -> dict[str, str]:
    """Construye la distribucion en `destino` y devuelve {artefacto: sha256}.

    No se usa `dist/` del repositorio: el gate se ejecuta con frecuencia y
    escribir ahi dejaria el arbol del proyecto con un estado que nadie pidio.
    """
    shutil.rmtree(destino, ignore_errors=True)
    destino.mkdir(parents=True)
    proc = _corre(["uv", "build", "--out-dir", str(destino)], timeout=900)
    if proc.returncode != 0:
        raise RuntimeError(
            f"uv build devolvio {proc.returncode}: {(proc.stderr or proc.stdout)[-400:]}"
        )
    return {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(destino.iterdir())
        if p.is_file() and not p.name.startswith(".")
    }


def _decide_por_bytes(
    primera: dict[str, str],
    segunda: dict[str, str],
    *,
    huella_antes: str,
    huella_despues: str,
) -> tuple[Veredicto, str]:
    """Decide sobre dos construcciones. NO construye: decide.

    **POR QUE ESTA SEPARADA, Y POR QUE NO ES COSMETICA.** La construccion son
    cuatro `uv build` y el bloque entero tardaba mas de un minuto por caso. Si
    el fallo estuviera dentro de la decision —que es donde esta — un guard que
    solo puede probarla construyendo tardaria un minuto en CADA asercion, y un
    guard lento se deja de ejecutar. La decision es pura: dos dicts de hashes y
    dos huellas, sin disco y sin reloj, y por eso se puede deformar en
    milisegundos.

    Y medido, no supuesto: la primera version de este bloque metio la decision
    dentro de `_distribution_reproducible` y los tests no tardaban un minuto
    cada uno — tardaban CERO, porque no se podia deformar la decision sin
    deformar tambien la construccion, y lo que se deformaba era la construccion
    entera. Un guard que no se puede deformar sin disparar el sistema entero no
    vigila la decision: vigila que el sistema entero corra.
    """
    if not primera or not segunda:
        return "OPEN", "una de las dos construcciones no produjo artefactos"
    if set(primera) != set(segunda):
        return (
            "OPEN",
            f"las dos construcciones no producen los MISMOS artefactos: "
            f"solo en la primera {sorted(set(primera) - set(segunda))}, "
            f"solo en la segunda {sorted(set(segunda) - set(primera))}",
        )
    distintos = sorted(n for n in primera if primera[n] != segunda[n])
    if not distintos:
        return (
            "PASS",
            f"la distribucion es REPRODUCIBLE, medido: {len(primera)} artefactos "
            f"construidos dos veces con la fuente tocada entre medias (contenido identico, "
            f"fecha distinta) y los {len(primera)} sha256 coinciden. Ademas el paquete "
            f"construye y lleva lo que declara. {', '.join(sorted(primera))}",
        )
    # MEDIDO, Y ESTA ES LA SEPARACION QUE NO EXISTIA. Los bytes pueden diferir
    # por DOS motivos que piden acciones OPUESTAS, y confundirlos hace que
    # alguien arregle el build de un proyecto cuyo build esta bien.
    #
    # Aqui se ha podido COMPROBAR que la entrada era la misma —el arbol de
    # trabajo no cambio— luego lo que queda es la reproducibilidad del build,
    # que es exactamente lo que el veredicto dice. No se baja el tono: se puede
    # sostener porque se ha medido la precondicion.
    if huella_antes != huella_despues:
        return (
            "NO_MEASURABLE",
            f"el ARBOL DE TRABAJO cambio entre las dos construcciones "
            f"(huella {huella_antes[:12]} -> {huella_despues[:12]}), y por eso los bytes "
            f"difieren en {len(distintos)} artefacto(s): {', '.join(distintos)}. NO es un "
            f"defecto de reproducibilidad: se han medido DOS ENTRADAS DISTINTAS, y un "
            f"veredicto que las llama «no reproducible» acusa al proyecto de algo que no ha "
            f"hecho. Lo que hay que medir es la reproducibilidad con el arbol quieto; lo que "
            f"hay que arreglar, si algo, es por que el arbol se movio entre las dos "
            f"construcciones",
        )
    detalle = "; ".join(f"{n}: {primera[n][:12]} vs {segunda[n][:12]}" for n in distintos)
    return (
        "OPEN",
        f"la distribucion NO es reproducible: mismo contenido y distinta fecha dan "
        f"bytes distintos en {len(distintos)} artefacto(s) — {detalle}. Y esto SI se puede "
        f"sostener porque se ha comprobado que el arbol de trabajo era el mismo en las dos "
        f"construcciones (huella {huella_antes[:12]}), luego la diferencia es del build",
    )


def _distribution_reproducible() -> tuple[Veredicto, str]:
    """La distribucion es REPRODUCIBLE: mismas entradas, mismos bytes.

    **Por que construir dos veces y no una.** MEDIDO antes de escribir esto:
    este predicado ejecutaba `check_package_build.py`, que construye el wheel y
    el sdist, y devolvia PASS con la evidencia *«el wheel y el sdist se
    construyen y llevan lo que declaran»*. Eso prueba que SE CONSTRUYEN.
    Reproducible es otra cosa: que las mismas entradas den los mismos bytes.
    Un unico build no puede Distinguir «reproducible» de «esta vez salio bien»,
    y el gate declaraba la primera sin haber medido la segunda.

    **Por que se toca la FECHA de un fuente entre medias.** Construir dos veces
    seguidas no prueba nada: si el reloj no tick entre las dos, los timestamps
    que se meten en el zip coinciden aunque el build sea irreproducible, y el
    gate passaria con un defecto real. Tocando el mtime —contenido identico— la
    unica variable que queda es la que hace que un build NO sea reproducible, y
    si los bytes siguen igual, es que de verdad no depende de ella.

    **Y LO QUE LE FALTABA, MEDIDO AL CERTIFICAR B18.** Este predicado decidia
    mirando los BYTES y nada mas, y hay dos razones por las que pueden diferir
    que piden acciones OPUESTAS: que el build sea irreproducible —se arregla el
    build— o que la ENTRADA haya cambiado entre las dos construcciones —se
    arregla la medicion—. Decia «la distribucion NO es reproducible» en los dos
    casos. MEDIDO: dio OPEN 1 vez de 8 durante la certificacion de B18, con la
    evidencia «mismo contenido y distinta fecha dan bytes distintos en 2
    artefacto(s)», y la distribucion ES reproducible —8 de 8 construcciones dan
    bytes iguales, con y sin tocar la fecha—.

    **Lo que entra, y por que no se resuelve dentro del artefacto.** No se puede
    saber desde el paquete si las dos construcciones recibieron la misma entrada:
    con un fichero ya versionado que cambia entre medias, los dos artefactos son
    coherentes consigo mismos y aun asi se construyeron con entradas distintas.
    Hace falta el estado del arbol, y se toma con `_huella_de_entrada` justo
    antes de cada construccion. Con la entrada comprobada, el `OPEN` que acusa
    se puede sostener; sin ella, era una acusacion sin prueba.

    **LO QUE YA EXISTIA Y CUBRE LA MITAD.** `sg_build_sdist_no_versionado`, en
    scripts/check_package_build.py, rechaza que el paquete lleve un fichero que
    git no versiona. MEDIDO: con un fichero nuevo en el arbol, el veredicto es
    OPEN y la evidencia dice «el artefacto depende de lo que haya en el arbol
    de trabajo, no del commit». Es un buen guard y no se toca.
    """
    # Primero, lo de siempre: que el paquete se pueda construir y llevar lo que
    # declara. Sin esto, un fallo de construccion se presentaria como un fallo
    # de REPRODUCIBILIDAD, que es otra cosa y pide otra accion.
    proc = _corre([sys.executable, "scripts/check_package_build.py"], timeout=900)
    if proc.returncode != 0:
        return (
            "OPEN",
            f"scripts/check_package_build.py rc={proc.returncode}: {proc.stdout.strip()[-300:]}",
        )

    fuente = RAIZ / _FICHERO_DE_FECHA
    contenido = fuente.read_bytes()
    mtime = fuente.stat().st_mtime
    try:
        # La huella se toma INMEDIATAMENTE ANTES de cada construccion, no una
        # vez al principio: lo que se quiere saber es si cada construccion
        # recibio la misma entrada, y eso solo se responde tomando la huella en
        # el instante de cada una.
        with tempfile.TemporaryDirectory(prefix="gate1_a_") as da:
            huella_antes = _huella_de_entrada()
            primera = _construye_en(Path(da))
            # La fecha se separa de forma VISIBLE: dos segundos. Si el build
            # embebiese el mtime, dos segundos bastarian para que se notara.
            time.sleep(2.1)
            futuro = time.time() + 5
            os.utime(fuente, (futuro, futuro))
            assert fuente.read_bytes() == contenido, "tocar la fecha no puede cambiar el texto"
            with tempfile.TemporaryDirectory(prefix="gate1_b_") as db:
                huella_despues = _huella_de_entrada()
                segunda = _construye_en(Path(db))
    except RuntimeError as exc:
        return "OPEN", f"no se pudo construir dos veces para comparar: {exc}"
    finally:
        os.utime(fuente, (mtime, mtime))
        fuente.write_bytes(contenido)

    return _decide_por_bytes(
        primera, segunda, huella_antes=huella_antes, huella_despues=huella_despues
    )


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
#: Que cuenta como modulo de la ESTANDAR, DERIVADO del interprete.
#:
#: MEDIDO, Y ESTA CONSTANTE ESTABA ESCRITA A MANO CON TRECE RENGLONES. El
#: interprete sabe de 290, y entre los que faltaban estan `pathlib`,
#: `contextlib`, `abc`, `io`, `warnings` y `copy` — todos de la estandar. Un
#: import legitimo de cualquiera de ellos en `core/` habria producido un
#: `OPEN` sobre una frontera que se estaba respetando, y una propiedad que se
#: pone roja por lo contrario es una propiedad que entrena a su lector a no
#: creerla. Ese fallo es tan malo como el de dar verde: los dos hacen que el
#: veredicto deje de ser informacion.
#:
#: MEDIDO tambien que hoy la lista escrita a mano no contenia NINGUN nombre
#: que no fuera de la estandar, luego la lista era correcta y ESTA VIEJA. Que
#: fuera correcta hoy es exactamente lo que la hacia peligroso: una lista
#: escrita a mano que se queda vieja no avisa, simplemente empieza a dar
#: veredictos que nadie reviso.
#:
#: `sys.stdlib_module_names` es el HECHO, y AGENTS.md 1.4 pide que no haya una
#: segunda fuente de verdad que se pueda quedar vieja en silencio. Un guard que
#: compara contra su propia copia no vigila nada —el error de WI-106—, y una
#: lista escrita a mano es la copia del guard.
#:
#: Se quitan los PRIVADOS de un solo underscore —`_abc`, `_ast`—, que son
#: implementacion del interprete y no una API. MEDIDO: la primera version de
#: este filtro era «not nombre que empiece por guion bajo» y se llevaba por
#: delante `__future__`, que tambien empieza por guion bajo y que es una
#: CONSTRUCTORA DEL LENGUAJE, no un privado. El resultado fue un `OPEN` falso que
#: nombraba `__future__` como dependencia externa del nucleo —y un nucleo no puede
#: importar la estandar sin `__future__` si quiere postponed annotations—.
#:
#: Y ese falso `OPEN` es, precisamente, la MEJORA DE LA EVIDENCIA haciendose
#: visible: la evidencia nueva nombra el modulo culpable y cuantos ficheros se
#: midieron, y la de antes decia «(5 modulos)» y no decia nada. Un `OPEN`
#: equivocado que se puede leer en dos segundos es un `OPEN` que se arregla; uno
#: escondido detras de un numero sin nombre es uno que se acepta.
#: Los nombres con punto se dejan como estan: lo que se compara es el PRIMER
#: TROZO del import, y `os.path` y `os` tienen que contar igual. Lo que se quita
#: son los privados de un solo guion bajo, que son implementacion del
#: interprete y no una API.
_ESTANDAR_QUE_NO_ES_API: frozenset[str] = frozenset(
    nombre
    for nombre in sys.stdlib_module_names
    if nombre.startswith("_") and not nombre.startswith("__")
)

_MODULOS_ESTANDAR: frozenset[str] = frozenset(sys.stdlib_module_names) - _ESTANDAR_QUE_NO_ES_API

#: De donde sale la lista, y se dice en la EVIDENCIA del predicado. Un PASS que
#: no dice como se obtuvo su verdad es el mismo PASS de antes con otra
#: tipografia, y esta vez la verdad era una lista escrita a mano.
_MODULOS_ESTANDAR_ORIGEN: str = (
    f"sys.stdlib_module_names, el conjunto que declara el propio interprete "
    f"(Python {sys.version_info.major}.{sys.version_info.minor})"
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
