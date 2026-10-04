"""B14 — medicion de linea base: puede la autoridad de COHERENCIA ser engañada?

POR QUE ESTE INSTRUMENTO MUTA EN SITIO Y NO EN UNA COPIA
---------------------------------------------------------
La primera version monto una copia temporal del estado y ejecutaba alli el
verificador. Dio 7 de 8 en PASS, y era mentira: la copia no colecta tests,
`project_truth` no puede leer el recuento real, y por eso TODO devolvia
rc=2 —incluidas las siete que el script contaba como buenas. Un instrumento
que se pasa a si mismo porque el entorno no puede correr es la forma exacta
del falso verde que este repositorio lleva diez bloques cazando.

Asi que aqui se muta el estado de verdad y se restaura, y la restauracion se
COMPRUEBA por sha256 antes de dar por buena la medicion. Si un fichero no
vuelve a su hash, el script aborta con rc=3 en vez de seguir: un instrumento
que no puede garantizar que el arbol volvio no tiene derecho a informar.

Que mide
--------
Que `scripts/project_truth.py` —la respuesta a «¿donde esta el proyecto?», y
la claim en la que B0..B13 se apoyan— no pueda decir `coherente: true` cuando
el estado no lo esta. Ya se ha medido un caso: al anadir una segunda clave
`current_workitem`, su regex leyo `B13` y `yaml.safe_load` leyo `B13_cerrado`,
y project_truth reporto coherente sin avisar.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Derivado de donde ESTA el script. Escrito a mano, el instrumento medía
# un arbol que puede no ser el suyo, y mutaba ficheros de otra maquina.
RAIZ = Path(__file__).resolve().parent.parent
#: `scripts/project_truth.py` entra aqui por la autocomprobacion, que lo DEFORMA.
#: MEDIDO: sin el, la primera ejecucion de `--autocomprobacion` revento a mitad
#: y dejo el verificador sin el constructor de claves duplicadas, y el arbol se
#: fue a `coherente: false` sin que nadie lo dijera. La red existia —
#: `restaura()` verifica por sha256— pero no cubria el fichero que este script
#: mas manipula, que es justo el que no puede quedar sucio: es la autoridad de
#: coherencia del repo, y un verificador cojo no avisa, dice cualquier cosa con
#: la misma autoridad.
MUTABLES = (
    "STATE.yaml",
    "ROADMAP.md",
    "CURRENT.md",
    "src/skillgraph/__init__.py",
    "scripts/project_truth.py",
)


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


class Arbol:
    """Guarda los mutables y los devuelve byte a byte, o aborta."""

    def __init__(self) -> None:
        self.copia = Path(tempfile.mkdtemp(prefix="b14_restore_"))
        self.hashes: dict[str, str] = {}
        for rel in MUTABLES:
            origen = RAIZ / rel
            destino = self.copia / rel
            destino.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(origen, destino)
            self.hashes[rel] = _sha(origen)

    def restaura(self) -> None:
        for rel in self.hashes:
            shutil.copy2(self.copia / rel, RAIZ / rel)
        for rel, esperado in self.hashes.items():
            actual = _sha(RAIZ / rel)
            if actual != esperado:
                raise SystemExit(
                    f"ABORTA: {rel} no volvio a su hash.\n"
                    f"  antes  {esperado}\n  ahora  {actual}\n"
                    f"La copia buena esta en {self.copia}."
                )

    def __enter__(self) -> Arbol:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.restaura()
        shutil.rmtree(self.copia, ignore_errors=True)


def _corre() -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, str(RAIZ / "scripts" / "project_truth.py")],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=False,
        timeout=900,
    )
    return proc.returncode, proc.stdout + proc.stderr


def _coherente(salida: str) -> bool | None:
    import json

    try:
        return json.loads(salida).get("coherente")
    except (json.JSONDecodeError, AttributeError):
        return None


_WORKITEM = re.compile(r"^(\s*)current_workitem:.*$", re.MULTILINE)


def _leido(estado: str, clave: str) -> object:
    """Lo que el PARSER lee de `clave`, no lo que el texto parece decir.

    La diferencia es el negocio entero de B13: seis ficheros de test leian el
    estado con `yaml.safe_load` y `project_truth` lo leia con un regex, y cada
    uno encuentras una cosa distinta del mismo fichero sin que nadie lo notara.
    Comparar texto contra texto para decidir si una mutacion surtiio es el mismo
    error una vez mas abajo.
    """
    import yaml

    datos = yaml.safe_load(estado)
    valor = datos.get("roadmap", {}).get(clave)
    return "" if valor is None else str(valor).split()[0]


def _pon_workitem(texto: str, valor: str) -> str:
    """El estado con `current_workitem` a `valor`, o ABORTA si no se pudo.

    MEDIDO: este instrumento hacia `.replace("  current_workitem: B13", ...)`
    en tres preguntas, con el workitem vivo escrito a mano. Al pasar el bloque
    vivo a B14 los tres `.replace` se volvieron no-ops: el estado nunca se
    mutaba, el verificador contestaba `coherente: true` con su respuesta
    NORMAL a un estado intacto, y el instrumento imprimia 5/8 diciendo que el
    arreglo de B14 no funcionaba. Lo que estaba roto era el instrumento, y
    hacia tres preguntas a la vez.

    Un no-op aqui es peor que en un test: aqui no cae nadie, solo se pierde la
    medicion, y una medicion perdida se lee como un defecto del codigo que se
    acaba de arreglar. Por eso el numero de sustituciones es una condicion de
    exito, no un detalle.
    """
    cambiado, n = _WORKITEM.subn(rf"\g<1>current_workitem: {valor}", texto, count=1)
    if n != 1:
        raise SystemExit(
            "ABORTA: STATE.yaml ya no declara `current_workitem` con esa forma, y la "
            "pregunta no mutaria nada. Un PASS aqui seria el de un estado intacto."
        )
    if _leido(cambiado, "current_workitem") != valor:
        raise SystemExit(
            "ABORTA: la sustitucion dejo el estado declarando "
            f"{_leido(cambiado, 'current_workitem')!r} y no {valor!r}. MEDIDO: la primera "
            "version de este helper remplazaba la LINEA entera por el valor, se llevaba "
            "el nombre de la clave, y dejaba un `B99` suelto: YAML invalido, el "
            "verificador con rc=2, y la pregunta 4 contando eso como PASS. Un abort "
            "que comprueba la cadena entera no habria visto nada, porque el nombre de "
            "la clave aparece en otras lineas del fichero: lo que se comprueba es el "
            "VALOR que el parser lee, que es lo que el verificador va a mirar."
        )
    return cambiado


def _duplica_workitem(texto: str, valor: str) -> str:
    """El estado con la MISMA clave declarada DOS veces, o ABORTA si no pudo.

    No es «poner un valor»: es la lectura duplicada, que es el caso que B13
    produjo sin querer y que ninguna de las otras preguntas reproduce.
    """

    def _dos(m: re.Match[str]) -> str:
        return f"{m.group(0)}\n{m.group(1)}current_workitem: {valor}"

    cambiado, n = _WORKITEM.subn(_dos, texto, count=1)
    if n != 1:
        raise SystemExit(
            "ABORTA: STATE.yaml ya no declara `current_workitem` con esa forma, y la "
            "pregunta de la clave duplicada no inyectaria la segunda declaracion."
        )
    return cambiado


def _contradicciones(salida: str) -> list[str]:
    import json

    try:
        valor = json.loads(salida).get("contradicciones")
    except json.JSONDecodeError:
        return []
    return [str(c) for c in valor] if isinstance(valor, list) else []


def _ilegible(salida: str) -> str:
    import json

    try:
        valor = json.loads(salida).get("ilegible", "")
    except json.JSONDecodeError:
        return ""
    return str(valor)


def _pregunta(nombre: str) -> dict[str, object]:
    return {"nombre": nombre, "cumple": None, "detalle": ""}


PREGUNTAS: list[dict[str, object]] = [
    _pregunta("el estado real de hoy se lee coherente"),
    _pregunta("una clave de verdad duplicada NO pasa por alto"),
    _pregunta("un total de tests que no cuadra con el arbol se detecta"),
    _pregunta("un workitem que no existe en ninguna parte se detecta"),
    _pregunta("una version activa incoherente con el tag se detecta"),
    _pregunta("un campo de verdad VACIO no se lee como si valiera"),
    _pregunta("el verificador falla ruidosamente si falta un fichero"),
    _pregunta("una contradiccion REAL se nombra, no solo se cuenta"),
]


#: Deformaciones del VERIFICADOR, y las preguntas que tienen que ponerse OPEN.
#:
#: MEDIDO, y por que este bloque existe. Durante B14 este instrumento dio 7/8 y
#: luego 8/8, y en ninguno de los dos casos se sabia si decia la verdad: sus
#: predicados eran «el verificador no dice coherente», y eso lo cumple un modulo
#: roto con la misma facilidad que un modulo que dejo de mirar. Se demostro en
#: carne propia — una sustitucion mal escrita dejo el YAML invalido, el
#: verificador salio con rc=2, y la pregunta dio PASS por un motivo que no era
#: el suyo. Un 8/8 que no puede ponerse en rojo no es un 8/8.
#:
#: Cada sonda se ancla en el texto EXACTO que escribio `ruff format`; el
#: instrumento se niega a arrancar si un ancla no es unica o no existe, que es
#: el mismo criterio que usa `mutate_b14_truth_single_reader.py`.
SONDAS_AUTOCOMPROBACION: tuple[tuple[str, str, str, frozenset[int]], ...] = (
    (
        "sin el constructor de claves duplicadas",
        # Sin los 4 espacios de delante: en `project_truth` la llamada esta a
        # nivel de modulo. Con ellos el ancla no aparecia NINGUNA vez y el
        # instrumento se negaba a arrancar, que es lo correcto para una ancla
        # mal escrita, pero delata que el fallo es del ancla y no del codigo.
        "_SinClavesDuplicadas.add_constructor("
        "yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construye)",
        "# Autocomprobacion: sin este constructor, YAML elige una de las dos.",
        frozenset({1}),
    ),
    (
        "el total deja de comprobar que es un entero",
        "    if not isinstance(total, int) or isinstance(total, bool):",
        "    if False:",
        # SOLO la 5. La 2 es «un total que NO CUADRA con el arbol» y la
        # comprobacion de tipo no tiene nada que ver con la aritmetica:
        # MEDIDO con el tipo sin comprobar, un `total: 9999` sigue siendo
        # detectado, porque lo que se compara es el numero con el recuento y
        # 9999 no es un entero valido sino uno que no cuadra. Declarar la 2 aqui
        # era una expectativa mia, no una propiedad: la autocomprobacion la
        # marco como [SIN CAZAR] y por eso esta acotada a lo que el defecto
        # rompe de verdad.
        frozenset({5}),
    ),
    (
        "el workitem deja de cruzarse con CURRENT.md",
        '    if v["workitem_state"] != v["workitem_current"]:',
        "    if False:",
        # La 3 (el workitem se detecta) y la 7 (la contradiccion se NOMBRA).
        # La 4 es la de la version, que esta sonda no toca, y declararla aqui
        # fue un numero de mas: la autocomprobacion dio [SIN CAZAR] [4] y lo
        # correcto era preguntar si la 4 tiene que caer, no si se puede hacer
        # caer. MEDIDO con esta deformacion puesta, el verificador dice, textual:
        #
        #     "coherente": true,  "contradicciones": [],
        #     "workitem_current": "B14",  "workitem_state": "B99"
        #
        # Es el defecto central de B14 a la vista, con la deformacion puesta:
        # el verificador publica como coherente un estado en el que STATE y
        # CURRENT dicen cosas distintas. Las preguntas 3 y 7 lo cazan.
        frozenset({3, 7}),
    ),
)


def _autocomprobacion() -> int:
    """Deforma el verificador de verdad y exige que las preguntas se caigan.

    No mira el verificador: lo EJECUTA, con las mismas preguntas y los mismos
    predicados que la medicion. Si una deformacion deja el 8/8 intacto, el
    predicado de esa pregunta no mira lo que dice mirar.
    """
    ruta = RAIZ / "scripts" / "project_truth.py"
    original = ruta.read_text(encoding="utf-8")
    for nombre, ancla, deformado, indices in SONDAS_AUTOCOMPROBACION:
        apariciones = original.count(ancla)
        if apariciones != 1:
            print(f"NO SE EJECUTA: el ancla de «{nombre}» aparece {apariciones} veces.")
            return 2
        if deformado == ancla:
            print(f"NO SE EJECUTA: «{nombre}» no deforma nada. Una deformacion que no")
            print("cambia el texto no puede hacer caer a nadie: probaria el harness,")
            print("no el codigo que dice vigilar.")
            return 2
        if not indices:
            print(f"NO SE EJECUTA: «{nombre}» no declara que preguntas tienen que caer.")
            print("Una sonda sin preguntas no se puede ni cazar ni fallar.")
            return 2
    print(f"autocomprobacion: {len(SONDAS_AUTOCOMPROBACION)} anclas unicas")

    fallos: list[str] = []
    for nombre, ancla, deformado, indices in SONDAS_AUTOCOMPROBACION:
        # La restauracion la hace el `with`, UNA vez, y la verifica por sha256.
        # MEDIDO: la primera version restauraba otra vez FUERA del `with` —que ya
        # lo habia hecho y habia borrado la copia— y reventaba con
        # FileNotFoundError; como la restauracion del verificador venia
        # DESPUES, la excepcion se comio esa restauracion y el verificador se
        # quedo deformado en el arbol. Una red que no cubre el fichero que este
        # script deforma no es una red, es decoracion.
        with Arbol():
            ruta.write_text(original.replace(ancla, deformado, 1), encoding="utf-8")
            _mide()
        siguen = [i for i in sorted(indices) if PREGUNTAS[i]["cumple"]]
        if siguen:
            fallos.append(f"{nombre}: las preguntas {siguen} siguen en PASS")
            print(f"  [SIN CAZAR] {nombre}: {siguen} siguen en PASS")
        else:
            print(f"  [CAZADA]    {nombre}: preguntas {sorted(indices)} en OPEN")

    if ruta.read_text(encoding="utf-8") != original:
        print("ABORTA: el verificador no volvio a su texto original.")
        return 2
    if fallos:
        print(f"\n{len(fallos)} sonda(s) sin cazar: los predicados no miran lo que dicen.")
        return 1
    print(f"\n{len(SONDAS_AUTOCOMPROBACION)}/{len(SONDAS_AUTOCOMPROBACION)} sondas cazadas")
    return 0


def _mide() -> None:
    """Rellena PREGUNTAS ejecutando el verificador de verdad.

    NO imprime: la autocomprobacion corre esto ocho veces, una por sonda, y
    una tabla de resultados por sonda seria ruido que tapa el veredicto.
    """
    with Arbol() as arbol:
        rc, salida = _corre()
        c = _coherente(salida)
        PREGUNTAS[0]["cumple"] = rc == 0 and c is True
        PREGUNTAS[0]["detalle"] = f"rc={rc} coherente={c}"

        def muta(rel: str, nuevo: str) -> None:
            (RAIZ / rel).write_text(nuevo, encoding="utf-8")

        def texto(rel: str) -> str:
            return (RAIZ / rel).read_text(encoding="utf-8")

        # 2. Clave duplicada: el caso MEDIDO durante B13.
        muta("STATE.yaml", _duplica_workitem(texto("STATE.yaml"), "B99_inventado"))
        rc, salida = _corre()
        c = _coherente(salida)
        import json

        try:
            parsed = json.loads(salida)
            contras = parsed.get("contradicciones")
            ilegible_bruto = parsed.get("ilegible", "")
        except json.JSONDecodeError:
            contras = None
            ilegible_bruto = ""
        # NO basta con que el veredicto cambie. Sin el constructor de claves
        # duplicadas, YAML toma la ULTIMA y el verificador dice «STATE declara
        # B99_inventado, CURRENT declara B13»: elige una de las dos y la
        # publica como la verdad. El veredicto cambia, luego un predicado de
        # «coherente is not true» lo daria por bueno — y asi dio 8/8 con el
        # mecanismo central roto. Lo que se exige es que el estado sea
        # ILEGIBLE nombrando la clave.
        ilegible = ilegible_bruto
        PREGUNTAS[1]["cumple"] = "current_workitem" in ilegible
        PREGUNTAS[1]["detalle"] = (
            f"rc={rc} coherente={c} ilegible={ilegible[:70]!r} contradicciones={contras}"
        )
        arbol.restaura()

        # 3. Total que no cuadra con el arbol.
        muta(
            "STATE.yaml",
            re.sub(
                r"^(\s*total:)\s*\d+",
                r"\g<1> 9999",
                texto("STATE.yaml"),
                count=1,
                flags=re.MULTILINE,
            ),
        )
        rc, salida = _corre()
        c = _coherente(salida)
        contras3 = _contradicciones(salida)
        # Un total que no cuadra NO es un estado ilegible: se lee bien y lo que
        # no cuadra es la ARITMETICA. Por eso se exige rc=1 y una contradiccion
        # que hable de los tests, y no «no es coherente»: con el campo vacio el
        # verificador sale con rc=2, `coherente: false`, y un predicado de
        # «falso» lo daria por bueno sin haber mirado la cifra.
        PREGUNTAS[2]["cumple"] = rc == 1 and any("tests" in x for x in contras3)
        PREGUNTAS[2]["detalle"] = f"rc={rc} coherente={c} contradicciones={contras3}"
        arbol.restaura()

        # 4. Workitem que no existe en ninguna parte.
        muta("STATE.yaml", _pon_workitem(texto("STATE.yaml"), "B99"))
        rc, salida = _corre()
        c = _coherente(salida)
        contras4 = _contradicciones(salida)
        # NO basta con «no es coherente». MEDIDO: con la sustitucion rota —que
        # se llevaba el nombre de la clave y dejaba un `B99` suelto— el estado
        # era YAML invalido, el verificador salia con rc=2 y `coherente: false`,
        # y esta pregunta lo contaba como PASS. Es el mismo falso verde que
        # B14 persigue, en el instrumento que certifica a B14: un predicado que
        # se puede satisfacer por una causa ajena al objeto que mide.
        #
        # Un workitem que no existe es un estado PERFECTAMENTE LEGIBLE con una
        # str que no cuadra: lo honesto es rc=1 y una contradiccion, no ilegible.
        PREGUNTAS[3]["cumple"] = rc == 1 and bool(contras4)
        PREGUNTAS[3]["detalle"] = f"rc={rc} coherente={c} contradicciones={contras4}"
        arbol.restaura()

        # 5. Version activa incoherente con el tag.
        original_init = texto("src/skillgraph/__init__.py")
        # SOLO el valor, no el fichero entero. MEDIDO: la primera version
        # reescribia `__init__.py` a una linea, y ese modulo es el que reexporta
        # las APIs publicas: 27 ficheros de test dejaban de importar, la colecta
        # se rompia, y el verificador salia con rc=2 sin llegar a mirar la
        # version. La pregunta se ponia en OPEN —por la causa equivocada— en el
        # mismo commit que introduce el «no cuentes una colecta a medias». Dos
        # instrumentos rompidos por la misma mutation, que es la clase de
        # defecto que este bloque persigue: uno que se satisface por lo que no
        # es. La pregunta que se quiere es «¿la version incoherente se NOMBRA?»,
        # y para eso el resto del arbol tiene que estar sano.
        init_mudado, cambios = re.subn(
            r'^__version__ = "[^"]*"',
            '__version__ = "7.7.7"',
            original_init,
            count=1,
            flags=re.MULTILINE,
        )
        if cambios != 1:
            raise SystemExit(
                "ABORTA: src/skillgraph/__init__.py ya no declara `__version__` con esa "
                "forma, y la pregunta de la version no mutaria nada."
            )
        muta("src/skillgraph/__init__.py", init_mudado)
        rc, salida = _corre()
        c = _coherente(salida)
        contras5 = _contradicciones(salida)
        # El mensaje que el verificador escribe es `version:`, no `release:`:
        # lo que se compara es `__init__.py` contra el ULTIMO TAG, y la release
        # declarada concuerda con el. MEDIDO: el predicado pedia «release» y dio
        # OPEN con el codigo correcto — un predicado escrito de memoria mide la
        # memoria, no el codigo. Se exige que la contradiccion nombre la version.
        PREGUNTAS[4]["cumple"] = rc == 1 and any("version" in x for x in contras5)
        PREGUNTAS[4]["detalle"] = f"rc={rc} coherente={c} contradicciones={contras5}"
        (RAIZ / "src/skillgraph/__init__.py").write_text(original_init, encoding="utf-8")

        # 6. Campo de verdad VACIO.
        muta(
            "STATE.yaml",
            re.sub(
                r"^\s*total:\s*\d+", "  total:", texto("STATE.yaml"), count=1, flags=re.MULTILINE
            ),
        )
        rc, salida = _corre()
        c = _coherente(salida)
        ilegible6 = _ilegible(salida)
        # MEDIDO: el predicado era `not (rc == 0 and coherente)`, que se puede
        # satisfacer por CUALQUIER motivo de fallo — incluido un `total:` vacio
        # que el verificador leiera como None y que por el hueco se notara como
        # una cifra que no cuadra. Sin comprobar el TIPO, la comprobacion del
        # tipo es opcional y nadie lo sabe. Se exige lo que el caso really es:
        # el estado no se lee, y el mensaje dice que campo.
        PREGUNTAS[5]["cumple"] = "total" in ilegible6
        PREGUNTAS[5]["detalle"] = f"rc={rc} coherente={c} ilegible={ilegible6[:90]!r}"
        arbol.restaura()

        # 7. Falta un fichero: tiene que fallar ruidosamente.
        (RAIZ / "CURRENT.md").unlink()
        rc, salida = _corre()
        PREGUNTAS[6]["cumple"] = rc != 0 and "ilegible" in salida.lower()
        PREGUNTAS[6]["detalle"] = f"rc={rc} dice_ilegible={'ilegible' in salida.lower()}"
        arbol.restaura()

        # 8. Una contradiccion real se NOMBRA. Un verificador que dice «falso»
        #    sin decir cual era la verdad deja a quien corrige haciendo la
        #    cuenta a mano, que es el trabajo que el verificador existe para
        #    evitar.
        muta("STATE.yaml", _pon_workitem(texto("STATE.yaml"), "B99"))
        rc, salida = _corre()
        contras = _contradicciones(salida)
        # El valor que se comprueba es el que INYECTO esta instrumentacion, no
        # el que el estado declaraba: si el verificador contestara con un valor
        # suyo, estaria leyendo otra cosa, y eso es justo lo que hay que cazar.
        PREGUNTAS[7]["cumple"] = bool(contras) and "B99" in " ".join(contras)
        PREGUNTAS[7]["detalle"] = f"contradicciones={contras}"
        arbol.restaura()


def main() -> int:
    if "--autocomprobacion" in sys.argv:
        return _autocomprobacion()
    with Arbol():
        _mide()
    paso = sum(1 for p in PREGUNTAS if p["cumple"])
    print("B14 · la autoridad de coherencia, medida antes de escribir nada")
    print("(mutaciones EN SITIO con restauracion verificada por sha256)\n")
    print(f"{'pregunta':<58} {'CUMPLE':<7} detalle")
    print("-" * 132)
    for p in PREGUNTAS:
        print(f"{p['nombre']:<58} {'PASS' if p['cumple'] else 'OPEN':<7} {p['detalle']}")
    print(f"\n{paso}/{len(PREGUNTAS)} preguntas en PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
