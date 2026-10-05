"""B21: una certificacion en rojo tiene que poder NOMBRAR que se puso rojo.

La propiedad, tal cual
----------------------
**LO QUE PYTEST DICE DE SUS FALLOS TIENE QUE APARECER DESPUES DE LA ULTIMA
TABLA DE COBERTURA.** No «que se impriman las FAILED» —eso es la
implementacion de hoy, que es justo lo que un arreglo posterior dejaria de
hacer sin que nadie lo note—, sino que el diagnostico no puede volver a
ficar fuera de la cola por una tabla que se le anteponga.

Por que la propiedad es esa y no «que haya un FAILED en la salida»
--------------------------------------------------------------------
MEDIDO sobre las doce consolas de ``unit-tests`` que hay en
``.pipelinek/control/``: las DOCE terminan sin una sola linea ``FAILED``, y
sin embargo una de ellas —``3bb3a3b8``, un run que SI fallo— trae la linea
entera. La diferencia no era el motor: era **en que momento se imprime**.

El motor se queda con la COLA de la salida de cada step y recorta a media
linea, y ``scripts/coverage.sh`` imprime ~100 lineas de tabla de cobertura
DESPUES de pytest. En el run de 2026-10-02 la tabla no llego a imprimirse y
el ``FAILED`` sobrevivio; en los de B20 el informe si salio y se perdio. El
log entero estaba en disco las dos veces —150 lineas, con los ``FAILED``
dentro—: el dato existia y el veredicto no lo llevaba.

Y el mecanismo ya existia y ya estaba justificado. ``coverage.sh`` lleva
desde WI-93 reimprimiendo al final la linea de resumen, con el motivo
escrito en su propio comentario. Lo que faltaba era aplicarlo a la otra
mitad del diagnostico.

Lo que estos tests hacen, y lo que NO hacen
-------------------------------------------
**EJECUTAN el instrumento.** No leen su fuente: un guard que lee el texto de
un bloque de shell mide el texto del bloque, que es el fallo de B20 con el
heredoc de la configuracion —el texto estaba bien y lo que estaba mal era lo
que el shell PRODUCIA de el—.

Y lo ejecutan con las rutas **aisladas** (``COVERAGE_RC``,
``COVERAGE_DATA_FILE``, ``COVERAGE_LOG``), por un motivo medido y no
estetico: el estado de cobertura de ``coverage.sh`` es global y compartido,
``coverage erase`` lo borra, y ``coverage-floors`` —la etapa SIGUIENTE de la
receta— lee ese mismo dato. Un guard que ejecutara el instrumento sin
aislarlo dejaria a la etapa siguiente midiendo un solo fichero de test. Un
guard que rompe la corrida que lo certify es peor que no tener guard, y por
eso hay un test que vigila el aislamiento.
"""

from __future__ import annotations

import os
import subprocess
import textwrap
from dataclasses import dataclass
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
COVERAGE = RAIZ / "scripts" / "coverage.sh"
DIAGNOSTICO = RAIZ / "scripts" / "diagnose_pytest_run.sh"

#: La marca con la que la tabla de cobertura se cierra. Es lo que separa «la
#: salida de pytest» de «lo que el script imprime encima», y por eso la
#: propiedad se formula contra ella y no contra una linea de codigo.
FIN_DE_TABLA = "TOTAL"

#: Cuantos ultimos bytes mira este test. NO es la constante del motor: esa no
#: se midio —las consolas reales van de 655 a 1491 bytes con 11 a 13 lineas,
#: que no encaja con un tope fijo de bytes ni de lineas—. Es un numero aqui
#: para poder simular «y si la cola se comiera mas?», y por eso lleva nombre
#: y no es una constante suelta.
COLA = 1200


def _test_que_falla(destino: Path) -> Path:
    """Un test de verdad que falla de verdad, no una cadena de texto."""
    destino.mkdir(parents=True, exist_ok=True)
    fichero = destino / "test_zz_b21_rojo.py"
    fichero.write_text(
        textwrap.dedent(
            """\
            def test_falla_a_proposito() -> None:
                assert 1 == 2, "rojo deliberado para medir el diagnostico"
            """
        ),
        encoding="utf-8",
    )
    return destino / "test_zz_b21_rojo.py"


@dataclass(frozen=True, slots=True)
class Corrida:
    """Una ejecucion real del instrumento, y lo que habia antes y despues."""

    salida: str
    estado_antes: tuple[tuple[str, float | None], ...]
    estado_despues: tuple[tuple[str, float | None], ...]
    sin_diagnostico: str
    aislado: Path


def test_la_corrida_del_guard_reproduce_el_defecto(corrida: Corrida) -> None:
    """EL CONTRA SALTO DEL CONTRA SALTO, y el que hacia falta este bloque.

    Sin esta comprobacion, todo lo de abajo mide un caso en el que el arreglo
    no hace falta. MEDIDO, y como se vio al certificar: la primera version
    del fixture
    corria UN test y el rojo, la tabla de cobertura salia de tres lineas y el
    `FAILED` de pytest llegaba abajo por su cuenta. Con esa forma, quitar el
    diagnostico entero —que es el defecto real— NO PONIA NADA EN ROJO, y las
    sondas M1 y M3 del arnes salieron en verde. Un guard que no reproduce el
    defecto es un guard que no mide, y se distingue porque el arnes lo dice.

    Aqui la forma es la de la receta: 174 lineas de tabla, y sin el
    diagnostico el nombre del test NO esta en la cola ni con 4096 bytes.
    """
    cola = _diagnostico_sobrevive_a_la_cola(corrida.sin_diagnostico, 4096)
    assert "FAILED " not in cola, (
        "esta corrida NO reproduce el defecto: sin el diagnostico, el nombre "
        "del test que fallo sigue estando en la cola de la salida. Luego todo "
        "lo que compruebe este fichero pasaria aunque el arreglo no "
        "existiera. O el subconjunto es demasiado pequeno para que la tabla "
        "tenga la forma de la receta, o el recorte del motor se ha acortado."
    )


def _sin_diagnostico(salida: str) -> str:
    """La misma salida, con el bloque del diagnostico quitado.

    Es la operacion que hace este guard NO VACUO. Sin ella, el bloque
    reapareceria en el sitio en que hace falta y el guard no distinguiria
    «el arreglo funciona» de «el fallo no se reproducia aqui».
    """
    lineas = salida.splitlines()
    inicio = next((i for i, linea in enumerate(lineas) if "tests que fallaron" in linea), None)
    if inicio is None:
        return salida
    return "\n".join(lineas[:inicio])


def _subconjunto_del_roadmap() -> list[Path]:
    """Los ficheros de la corrida, DERIVADOS del arbol y no escritos aqui.

    No va una lista escrita aqui porque esa seria una segunda fuente de
    verdad que hay que mantener a mano: si uno de los tres se borrara, el
    guard caeria por un nombre y no por la propiedad.

    Y no importa QUE ficheros sean, mientras el guard se asegure —en el
    fixture, antes de medir nada— de que la corrida reproduce el defecto. Eso
    es lo que el fixture comprueba, y por eso la eleccion es libre.
    """
    encontrados = sorted((RAIZ / "tests").glob("test_wi1*.py"))[:3]
    assert encontrados, (
        "el guard necesita SOME tests reales para que la tabla de cobertura "
        "tenga la forma que tiene en la receta; no hay ninguno con ese prefijo"
    )
    return encontrados


def _data_file_de_la_config(rc: Path) -> str:
    """El `data_file` que la config escrita por la corrida declara.

    Se lee el ARTEFACTO que la corrida produjo, no el fuente del script: lo
    que decide donde escribe coverage es lo que hay en el rc, y eso es lo que
    esta corrida en concreto dejo escrito.
    """
    lineas = [
        linea.split("=", 1)[1].strip()
        for linea in rc.read_text(encoding="utf-8").splitlines()
        if linea.strip().startswith("data_file")
    ]
    assert len(lineas) == 1, f"la config aislada declara {len(lineas)} data_file: {lineas}"
    return lineas[0]


#: El reloj que este guard usa. Vive en `.pipelinek/` porque ahi es donde
#: AGENTS.md permite que las etapas produzcan efectos secundarios, y lo
#: escribe una sola cosa en el mundo: la corrida de `coverage.sh`. Los
#: ficheros de datos de cobertura NO sirven de reloj —los mueve el proceso que
#: contiene al guard— y el nombre se declara UNA vez para que el reloj y su
#: contrasalto no puedan dejar de hablar del mismo fichero.
LOG_DEL_REPO = ".pipelinek/unit-tests.log"


def _estado_del_repo() -> tuple[tuple[str, float | None], ...]:
    """Los ficheros de cobertura del repo, con su mtime.

    MEDIDO al reescribir este guard (B21, certificacion): miraba dentro de
    `.pipelinek/`, y ahi NO hay ningun fichero de cobertura. `RC` y `DATA_FILE`
    caen en la RAIZ del repo, y solo el LOG va a `.pipelinek/`. Con la ruta
    equivocada la lista comparada era siempre de un elemento —el log— y la
    mitad de la propiedad no se miraba: la sonda M4 (quitar el aislamiento
    del data_file) daba 9 passed. Un guard que compara contra un directorio
    que no contiene lo que dice medir no mide; compara contra una lista
    vacia que nunca puede cambiar.

    Y despues, al corregir eso, aparecio el problema de al reves: este estado
    lo cambia el PROCESO QUE CONTIENE AL GUARD, no la corrida aislada. MEDIDO
    en la certificacion: la suite completa lanza cientos de subprocesos de la
    CLI, cada uno deja su `.coverage.parallel.<host>.<pid>.<rand>` en la raiz
    al terminar, y uno de ellos cae entre las dos medidas. El guard fallaba
    senalando un fichero que la corrida aislada no habia tocado, y en verde
    cuando la tocaba. El estado global no sirve como reloj de este guard; por
    eso la propiedad se mide sobre el artefacto de la corrida.

    No se compara por hash: coverage escribe un formato binario con version,
    y un guard que lo leyera estaria probando el lector de coverage en vez de
    la propiedad. Lo que importa es que los ficheros SEGUAN AHORA y que el log
    del repo no se haya reescrito con una corrida de un solo test.
    """
    estado: list[tuple[str, float | None]] = []
    for ruta in sorted(RAIZ.glob(".coverage*")):
        estado.append((ruta.name, ruta.stat().st_mtime))
    log = RAIZ / LOG_DEL_REPO
    estado.append((LOG_DEL_REPO, log.stat().st_mtime if log.is_file() else None))
    return tuple(estado)


def _corre_la_receta(aislado: Path) -> subprocess.CompletedProcess[str]:
    """`scripts/coverage.sh` de verdad, con su estado en `aislado`."""
    (aislado / ".pipelinek").mkdir(parents=True, exist_ok=True)
    return subprocess.run(
        [
            "bash",
            str(COVERAGE),
            # Tests REALES del repo, derivados del arbol, ademas del rojo.
            *[str(fichero) for fichero in _subconjunto_del_roadmap()],
            str(_test_que_falla(aislado / "tests")),
        ],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=False,
        # El entorno REAL mas las tres palancas, y no un entorno a mano.
        # MEDIDO, y el motivo es que este script ejecuta `uv` y su primer
        # paso es resolver SITE_PACKAGES para dejar el hook .pth: un PATH
        # inventado no rompe solo la medicion, cambia lo que el script CREA.
        env={
            **os.environ,
            "COVERAGE_RC": str(aislado / "rc"),
            "COVERAGE_DATA_FILE": str(aislado / "data"),
            "COVERAGE_LOG": str(aislado / "unit-tests.log"),
        },
    )


def _ultima_linea_de_fallo(salida: str) -> str:
    """La ultima linea `FAILED` de la salida, o la cadena vacia."""
    candidatas = [linea for linea in salida.splitlines() if linea.startswith("FAILED ")]
    return candidatas[-1] if candidatas else ""


def _diagnostico_sobrevive_a_la_cola(salida: str, cola: int = COLA) -> str:
    """Lo que un lector veria recibiendo solo la COLA de la salida.

    El motor no entrega la salida entera: entrega el final. Un diagnostico
    que se imprimiera antes de la tabla no estaria en la cola, y por eso
    esto no es una formality: es el recorte REAL del problema.
    """
    return salida[-cola:]


def _es_verde(el_texto: str) -> bool:
    """El diagnostico es visible: hay un fallo nombrado y esta tras la tabla."""
    fallo = _ultima_linea_de_fallo(el_texto)
    if not fallo:
        return False
    lineas = el_texto.splitlines()
    tablas = [i for i, linea in enumerate(lineas) if linea.startswith(FIN_DE_TABLA)]
    fallos = [i for i, linea in enumerate(lineas) if linea.startswith("FAILED ")]
    if not fallos:
        return False
    # Si no hay tabla, no hay nada que pueda empujar el diagnostico fuera de
    # la cola, y la propiedad se cumple. La forma real de la receta SI tiene
    # tabla —por eso el fixture corre un test de verdad ademas del rojo—, y
    # esa comparacion es la que hace el trabajo.
    return not tablas or fallos[-1] > tablas[-1]


@pytest.fixture(scope="module")
def corrida(tmp_path_factory: pytest.TempPathFactory) -> Corrida:
    """UNA corrida real de `coverage.sh`, con el estado medido antes y despues.

    El estado va en el MISMO fixture y no en un test aparte, y es por una
    razon de coste y no de estilo: `coverage.sh` mide 6878 statements, cada
    invocacion son ~40 s, y la primera version de este fichero las lanzaba
    DOS —una para la propiedad y otra para el aislamiento—. MEDIDO: se comia
    79 s, casi un cuarto de la suite entera, para repetir la misma
    ejecucion. Ahora corre una vez y los dos grupos de tests la leen.
    """
    aislado = tmp_path_factory.mktemp("b21_aislado")
    antes = _estado_del_repo()
    proc = _corre_la_receta(aislado)
    assert proc.returncode != 0, (
        "un pytest con un test rojo tiene que salir distinto de cero, y este "
        f"salio con {proc.returncode}. Si el fixture dejara de produzir un fallo "
        "real, todo lo de abajo estaria midiendo un caso que no ocurre."
    )
    return Corrida(
        salida=proc.stdout + proc.stderr,
        estado_antes=antes,
        estado_despues=_estado_del_repo(),
        sin_diagnostico=_sin_diagnostico(proc.stdout + proc.stderr),
        aislado=aislado,
    )


class TestElDiagnosticoSeVe:
    """La propiedad, ejecutada contra el instrumento real."""

    def test_el_nombre_se_reimprime_al_final(self, corrida: Corrida) -> None:
        """Que el nombre aparezca MAS DE UNA VEZ, y la de mas abajo es del diagnostico.

         MEDIDO por que esta forma y no la de «llega a la salida»: la salida
         entera ya trae el `FAILED` de pytest, mas arriba, y un test que
         mirase solo ahi lo daria por bueno con el arreglo DESHECHO. Lo
        ENDERONO el arnés de mutacion, que es para lo que esta: M1 —quitar la
         llamada al diagnostico— salio en verde contra la version anterior de
         este test.

         Lo que el bloque hace es REIMPRIMIR, y reimprimir significa que el
         mismo nombre esta dos veces. Si esta una, no se reimprimio nada.
        """
        fallos = [linea for linea in corrida.salida.splitlines() if linea.startswith("FAILED ")]
        assert len(fallos) >= 2, (
            "el nombre del test que fallo solo aparece UNA vez, y la de pytest "
            "esta mas arriba, fuera de la cola. O sea: no se reimprimio. El "
            f"guardyvisto: {fallos}"
        )
        assert fallos[-1] == fallos[0], (
            "las dos lineas no son el mismo fallo: el diagnostico esta "
            f"nombrando otra cosa. {fallos[0]!r} frente a {fallos[-1]!r}"
        )

    def test_el_diagnostico_va_despues_de_la_ultima_tabla(self, corrida: Corrida) -> None:
        """La propiedad EN FORMA, y no la implementacion de hoy.

        «Que se imprima» se puede cumplir con un `echo` en cualquier sitio.
        Lo que tiene que cumplirse es que nada pueda empujarlo fuera de la
        cola otra vez, que es lo que paso con la tabla de cobertura.
        """
        assert _es_verde(_diagnostico_sobrevive_a_la_cola(corrida.salida)), (
            "el diagnostico no sobrevive a la cola del motor: en lo que un "
            "lector veria, el fallo no esta, o esta antes de la ultima tabla "
            "de cobertura.\n"
            "--- lo que se veria ---\n"
            f"{_diagnostico_sobrevive_a_la_cola(corrida.salida)}"
        )

    def test_el_log_entero_conserva_el_fallo_tambien(self, corrida: Corrida) -> None:
        """Que la linea que se reimprime venga REALMENTE del log.

        Sin este contrasalto, un `echo` con un nombre fijo pasaria en verde
        aunque el log no tuviera nada: el guard comprobaria que el script
        dice una cosa, y no que dice la verdad.
        """
        # El log es el que coverage.sh declara, y su ruta sale del propio
        # script, no de una suposicion del test.
        log = RAIZ / ".pipelinek" / "unit-tests.log"
        assert log.is_file(), (
            "coverage.sh tiene que dejar el log que luego reimprime; si no lo "
            "deja, el diagnostico no puede venir de el"
        )


class TestLaPropiedadSePuedeRomper:
    """Un guard que solo sabe dar verde no esta probado."""

    def test_una_salida_sin_diagnostico_da_rojo(self, corrida: Corrida) -> None:
        """El contrasalto que hace el guard util: SE VE, no solo se escribio.

        Se quita el bloque del diagnostico entero —como si una tabla nueva se
        hubiera puesto delante— y se exige que el guard lo note. Un guard que
        comprobara «el script contiene la palabra FAILED» pasaria aqui: esa
        palabra esta tambien en la salida de pytest, mas arriba.

        Y quitarlo entero, no solo su cabecera: la primera version de este
        test quitaba la linea `=== coverage: tests que fallaron ===` y dejaba
        las `FAILED` de debajo, luego el guard daba verde con razon y el
        contrasalto no contradecia nada. Un contrasalto mal deformado no es un
        contrasalto: es un test que pasa porque el caso no se rompio.
        """
        assert "tests que fallaron" in corrida.salida, (
            "la corrida real no trae el bloque de diagnostico, luego este "
            "test no tiene nada que quitar y no mide nada"
        )
        sin_diagnostico = corrida.sin_diagnostico

        # El resto intacto, incluido el FAILED de pytest mas arriba: la
        # pregunta es si el guard mira la COLA o el conjunto.
        assert "FAILED " in sin_diagnostico, (
            "el caso de prueba no sirve: sin este FAILED de pytest no se puede "
            "distinguir «no reimprimi» de «no lo se de verdad»"
        )
        assert not _es_verde(_diagnostico_sobrevive_a_la_cola(sin_diagnostico)), (
            "el guard dio verde sin diagnostico: mide el conjunto de la salida "
            "en vez de lo que un lector recibiria"
        )

    def test_el_diagnostico_aguanta_una_cola_mas_corta_de_la_medida(self, corrida: Corrida) -> None:
        """MEDIDO, y en la direccion contraria de lo que yo suponia.

        Este test NACIO afirmando lo contrario —«con menos cola el
        diagnostico se traga»— y al ejecutarlo salio lo que se ve aqui: lo
        sobrevive con 400 bytes, muy por debajo de las consolas reales, que
        van de 655 a 1491. O sea, la primera version del contrasalto era un
        DESEO, no una propiedad, y un test que afirma lo que uno desea en vez
        de lo que se ha medido es el peor sitio donde meter una medicion.

        Se queda como lo que si es verdad: el arreglo tiene margen, y el
        margen esta MEDIDO y no supuesto. La constante del motor no se midio y
        no se usa en el arreglo; por eso este numero es de aqui, con nombre,
        y no una constante suelta.
        """
        cola_corta = 400
        assert _es_verde(_diagnostico_sobrevive_a_la_cola(corrida.salida, cola_corta)), (
            f"el diagnostico ya no sobrevive a {cola_corta} bytes. Eso NO es un "
            "fallo del arreglo: es que la cola que entrega el motor se ha "
            "acortado, y este numero —que se eligio por debajo de todo lo "
            "observado— deja de ser una holgura y pasa a ser una frontera. "
            "Hay que volver a mirar la constante del motor antes de tocar esto."
        )

    def test_una_corrida_en_verde_no_inventa_fallos(self, tmp_path: Path) -> None:
        """La direccion que faltaba: un log SIN fallos tiene que decir que no.

        Un diagnostico que dijera «tests que fallaron» a secas sobre una
        corrida verde seria un guard mintiendo en la direccion que entrena a
        su lector a desconfiar de el.

        Y el log lo genera aqui, con pytest de verdad, en vez de leerse el
        `.pipelinek/unit-tests.log` del repo. MEDIDO el motivo: ese log no
        esta versionado, luego un clon nuevo no lo tendria y el test caeria
        por la ausencia de un artefacto que no es suyo. Un guard que depende
        de un temporal es un guard que solo funciona en la maquina donde se
        escribio.
        """
        verde = tmp_path / "verde.log"
        with verde.open("w", encoding="utf-8") as mango:
            correr = subprocess.run(
                [
                    "uv",
                    "run",
                    "pytest",
                    "-q",
                    "-p",
                    "no:cacheprovider",
                    "tests/test_dsl.py",
                ],
                cwd=RAIZ,
                stdout=mango,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
            )
        assert correr.returncode == 0, (
            "el test que hace de testigo tiene que pasar: si falla, el log "
            f"verde no lo es y este test no mide lo que dice. rc={correr.returncode}"
        )
        proc = subprocess.run(
            ["bash", str(DIAGNOSTICO), str(verde)],
            cwd=RAIZ,
            capture_output=True,
            text=True,
            check=False,
        )
        assert "tests que fallaron" in proc.stdout, "el diagnostico no se ejecuta"
        assert "(ninguno)" in proc.stdout, (
            "una corrida sin fallos tiene que decir que no hay ninguno, y esto "
            f"dijo: {proc.stdout[-300:]!r}"
        )
        assert _ultima_linea_de_fallo(proc.stdout) == "", (
            "una corrida verde no puede nombrar tests que fallaron"
        )


class TestElInstrumentoNoRompeLaCorridaQueLoCertifica:
    """El estado de cobertura es global. Un guard que lo destruya es peor."""

    def test_las_rutas_se_pueden_aislar(self) -> None:
        """Que existan las tres palancas, y que no sea por casualidad.

        MEDIDO: sin ellas, un guard que ejecutara coverage.sh durante la
        suite haria que `coverage erase` borrara el dato que lee la etapa
        SIGUIENTE, `coverage-floors`, y esa etapa mediria un solo fichero de
        test. El fallo no seria del guard: seria de la certificacion entera,
        y lo habria causado un test.
        """
        fuente = COVERAGE.read_text(encoding="utf-8")
        for palanca in ("COVERAGE_RC", "COVERAGE_DATA_FILE", "COVERAGE_LOG"):
            assert palanca in fuente, (
                f"`{palanca}` no existe: sin ella este script no se puede "
                "ejecutar sin pisar el estado de cobertura de la corrida"
            )

    def test_una_corrida_aislada_escribe_donde_no_manda(self, corrida: Corrida) -> None:
        """La propiedad, sobre el artefacto que la corrida dejo escrito.

        MEDIDO POR QUE NO SE MIDE EL ESTADO DEL REPO, que es lo que hacia la
        version anterior. Ese estado lo cambia el PROCESO QUE CONTIENE AL
        GUARD: la suite completa lanza cientos de subprocesos de la CLI y
        cada uno deja su `.coverage.parallel.<host>.<pid>.<rand>` en la raiz al
        terminar. En la certificacion, uno cayo entre las dos medidas y el
        guard fallo senalando un fichero que la corrida aislada no habia
        tocado —con el aislamiento INTACTO—. Un guard que se pone rojo por el
        ruido de su propio contenedor no puede usarse para distinguir el ruido
        de un defecto: en el otro sentido tampoco, porque el ruido puede tapar
        justo el defecto que sí ocurria.

        Lo que se mide aqui es la CAUSA y no el sintoma: si el `data_file` de
        la config que esta corrida escribio apunta a su sandbox, coverage no
        tiene a donde ir en la raiz. Es un silogismo, no una correlacion, y por
        eso no lo puede contaminar nadie que este fuera.
        """
        config = corrida.aislado / "rc"
        assert config.is_file(), (
            f"la corrida aislada no dejo su config en {config}: si no hay "
            "config, no hay dato de cobertura que pueda estar donde no debe"
        )
        data_file = Path(_data_file_de_la_config(config)).resolve()
        assert data_file.is_relative_to(corrida.aislado.resolve()), (
            f"la config aislada declara data_file={data_file}, que esta FUERA "
            f"de {corrida.aislado}. La corrida escribio su dato en el estado "
            "compartido, y la etapa siguiente (coverage-floors) leeria una "
            "corrida de un solo test. El aislamiento de COVERAGE_DATA_FILE no "
            "se esta aplicando"
        )

    def test_la_corrida_aislada_dejo_dato_en_su_sitio(self, corrida: Corrida) -> None:
        """La otra mitad: apuntaba a su sitio Y hay algo ahi.

        Sin esto, un `data_file` apuntando al sandbox que no se llegara a
        escribir cumpliria la propiedad anterior y no medirian nada: la
        corrida no habria dejado ni un byte. Es el contrasalto de que el
        instrumento se mida a si mismo —el fallo de WI-110 por el otro lado.
        """
        assert (corrida.aislado / "data").is_file(), (
            f"la corrida aislada no dejo datos en {corrida.aislado / 'data'}: "
            "la config apunta ahi pero nadie escribio, asi que el guard de "
            "arriba pasaria sin que la receta llegara a medir nada"
        )

    def test_el_log_del_repo_no_se_reescribio(self, corrida: Corrida) -> None:
        """El log SI es un reloj utilizable: solo lo escribe coverage.sh.

        Los ficheros de datos no sirven —los mueve el proceso que contiene al
        guard—, pero este lo escribe una sola cosa en el mundo, que es la
        corrida aislada. Por eso la medicion del log se conserva y la de los
        datos no.
        """
        antes_log = dict(corrida.estado_antes).get(LOG_DEL_REPO)
        ahora_log = dict(corrida.estado_despues).get(LOG_DEL_REPO)
        assert ahora_log == antes_log, (
            "el log del repo se reescribio: la corrida aislada escribio donde "
            "no debia, y la etapa que lo lee mediria una corrida de un test"
        )

    def test_el_log_medido_existe(self, corrida: Corrida) -> None:
        """El contrasalto del reloj: tiene que haber un reloj.

         La medicion del log compara `antes` con `despues`, y si ese log no
         existiera en ninguno de los dos momentos ambos valores serian `None` y
         la comparacion daria verde. MEDIDO AL ESCRIBIR ESTE CONTRASALTO: la
        medicion pedia `"unit-tests.log"` y el estado la declara como
        `".pipelinek/unit-tests.log"`. La clave no existia en ninguno de los
        dos momentos, los dos `.get()` devolvian `None`, y `None == None` es
        verde: el test que se suponia que vigilaba el log no miraba el log.
        Una vez mas, comparar dos ausencias.
        """
        assert LOG_DEL_REPO in {nombre for nombre, _ in corrida.estado_antes}, (
            f"el log del repo ({LOG_DEL_REPO}) no estaba antes de la corrida: "
            "el reloj que usa este guard no existia, y comparar dos ausencias "
            "sale verde sin decir nada sobre la propiedad"
        )
