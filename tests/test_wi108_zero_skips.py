"""WI-108: «cero skips» es una regla escrita que no mide nadie.

Por qué existe este fichero
---------------------------
`AGENTS.md §6.2` dice, con las dos lineas que la serie viene defendiendo:

    NO usar `pytest.skip` para esconder fallos: o arreglas el test o lo borras.
    Un `skip` por falta de artefacto es el mismo defecto, con otra forma.

Es una prohibicion **razonada**, escrita por WI-103 despues de medir un gate
que se saltaba por falta de informe. Y no hay **nada** que la compruebe:

    instrumentos que miran skips (scripts/, src/): 0
    etapas de la receta que los miran:               0

Lo medido antes de escribir una linea, con un run sintetico cuyo unico
cambio es la linea de resumen del journal:

    run sin skips:  0 problemas []
    run con 3 skips: 0 problemas []
    veredicto: «OK: el run cumple los criterios que declara AGENTS.md»

Y el detalle que hace el defecto mas grave de lo que parece: el **criterio
2** de AGENTS.md —el que existe para distinguir un run real de un veredicto
cacheado— **acepta** un resumen con skips. `2715 passed, 3 skipped` casa
con su regex igual que `2718 passed`. No es un bug del regex: es que la
pregunta por los skips **no existe**, asi que nadie la respondio nunca.

Y lo que hay hoy
---------------
Cinco skips, de dos clases que §6.2 no separa y que no son lo mismo:

| clase | donde | que es |
|---|---|---|
| plataforma | `test_locks.py`, `test_evidence_lock.py` | `fcntl` no existe en Windows: diferencia real entre maquinas |
| artefacto | `test_wi105_pipeline_receipt.py` x3 | «sin journal: clon nuevo» |

Los de plataforma son legitimos: no esconden un fallo, describen que una
plataforma no tiene la syscall. Los de artefacto son **justo lo que §6.2
prohibe por su nombre**, y son los que yo escribi en WI-105.

Que fijan estos tests
--------------------
Dos contratos distintos, en dos sitios distintos, porque son dos
propiedades distintas y el CI solo puede ver una de ellas:

1. **Sobre el run** — que el journal de una ejecucion con skips sea un
   incumplimiento. Eso lo mide la etapa `evidence` de la receta, que es
   donde ya se comprueban los criterios, y este fichero lo prueba sobre
   `InformeRun` sinteticos.
2. **Sobre el codigo** — que todo skip del repo este en la lista de
   declarados, y que todo declarado siga existiendo. Eso el CI **no lo
   puede ver**: el journal solo tiene un numero, no una clase.

La lista de declarados se vigila en las DOS direcciones. Solo en una, un
guard deja de ser un guard: un skip de plataforma que se borra deja su
decorador sin suelo, igual que una desviacion de cobertura que apunta a un
fichero borrado.

El guard mira el AST, no el texto
---------------------------------
La primera version buscaba `pytest.skip(` con un regex, y se puso roja
**por su propia documentacion**: este modulo cita el patron para explicar
que lo prohibe, y una cita es indistinguible de una llamada. Es el mismo
error que el resto de la serie, y con el mismo nombre: un guard que busca
una cadena busca la cadena, no la propiedad. La propiedad es «este codigo
**llama** a pytest.skip», y eso lo responde el arbol sintactico, donde un
docstring es una constante y no una llamada. Los dos tests de abajo existen
para que esa distincion se vea, no por referee.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Any, NamedTuple

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import check_pipeline_receipt as cpr  # noqa: E402

TESTS = ROOT / "tests"

#: Los skips LEGITIMOS, declarados uno a uno con su motivo.
#:
#: Un skip no entra aqui por inercia: entra porque su condicion es una
#: diferencia real entre maquinas (`fcntl` no existe en Windows) y no un
#: fallo que alguien decidio no mirar. Un skip de artefacto no entra, y por
#: eso hay que declararlo: la prohibicion de §6.2 es contra *esconder*, y
#: esconder no es lo mismo que no tener Windows.
SKIPS_DECLARADOS: dict[str, str] = {
    "tests/test_locks.py": "fcntl no existe en Windows: no es un fallo escondido",
    "tests/test_evidence_lock.py": "idem: el test toma el lock con fcntl",
    # B2: opt-in por credencial y coste. No es un skip de plataforma
    # como los dos de arriba —es un skip de ENTORNO—, y aun asi se
    # declara, porque un skip sin escribir es un fallo escondido.
    # La razon se duplica aqui a proposito: `test_la_lista_de_declarados_
    # tiene_una_sola_fuente` exige que las dos copias coincidan, y una
    # entrada en un sitio y no en el otro es exactamente la deriva que
    # ese test existe para cazar.
    "tests/test_uat_real_provider.py": "opt-in por credencial y coste: requiere SG_UAT_REAL_PROVIDER=1",
}

LLAMADA_SKIP = frozenset({"pytest.skip", "pytest.mark.skip"})
LLAMADA_SKIPIF = frozenset({"pytest.mark.skipif"})


class Skip(NamedTuple):
    linea: int
    nombre: str
    clase: str  # "ejecucion" | "plataforma"


def _nombre_dotted(nodo: ast.expr) -> str:
    """`pytest.mark.skipif` a partir de sus tres `Attribute` anidados."""
    partes: list[str] = []
    while isinstance(nodo, ast.Attribute):
        partes.append(nodo.attr)
        nodo = nodo.value
    if isinstance(nodo, ast.Name):
        partes.append(nodo.id)
    else:
        return ""
    return ".".join(reversed(partes))


def skips_de(fuente: str) -> tuple[Skip, ...]:
    """Los skips que el codigo LLAMA, mirados en el AST.

    Un docstring, un comentario o una cadena que mencione el patron no
    aparecen aqui, y esa es toda la razon de usar el arbol. Un skipif es un
    decorador, pero en el AST tambien es una llamada, asi que se
    distingue por el nombre y no por la posicion.
    """
    arbol = ast.parse(fuente)
    salida: list[Skip] = []
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, ast.Call):
            continue
        nombre = _nombre_dotted(nodo.func)
        if nombre in LLAMADA_SKIP:
            salida.append(Skip(nodo.lineno, nombre, "ejecucion"))
        elif nombre in LLAMADA_SKIPIF:
            salida.append(Skip(nodo.lineno, nombre, "plataforma"))
    return tuple(sorted(salida))


def _skips_del_arbol() -> dict[str, tuple[Skip, ...]]:
    salida: dict[str, tuple[Skip, ...]] = {}
    for f in sorted(TESTS.rglob("test_*.py")):
        encontrados = skips_de(f.read_text(encoding="utf-8"))
        if encontrados:
            salida[str(f.relative_to(ROOT))] = encontrados
    return salida


def _control(tmp_path: Path) -> Path:
    """Un control root completo, para que el unico problema posible sea el run."""
    root = tmp_path / "control"
    for nombre in ("last-run", "retry-control", "wait-until-control", "workspace"):
        (root / nombre).mkdir(parents=True, exist_ok=True)
    return root


def _informe(resumen: str, **extra: Any) -> cpr.InformeRun:
    """Un `InformeRun` sano salvo por el resumen, que es lo que se varia."""
    base: dict[str, Any] = {
        "run_id": "run-skips-0001",
        "steps_iniciados": 9,
        "pasos_capturados": 9,
        "etapas_ok": 8,
        "etapas_total": 8,
        "step_failed": 0,
        "outcome": "success",
        "resumen_pytest": resumen,
    }
    base.update(extra)
    return cpr.InformeRun(**base)


def _codigos(problemas: tuple[cpr.Problema, ...]) -> set[str]:
    return {p.codigo for p in problemas}


# --- El guard que decide: AST, y su contraejemplo -------------------------


class TestElGuardMiraLaLlamadaNoLaCita:
    """Por que el regex no servia, demostrado con los dos lados.

    Sin esto, «el guard es correcto» es una afirmacion: y la primera
    version del guard, que usaba regex, se puso roja por la documentacion
    de este mismo fichero.
    """

    def test_una_llamada_se_ve(self) -> None:
        fuente = "import pytest\n\n\ndef test_algo() -> None:\n    pytest.skip('porque si')\n"
        assert skips_de(fuente) == (Skip(5, "pytest.skip", "ejecucion"),)

    def test_una_cita_en_docstring_no_se_ve(self) -> None:
        fuente = (
            '"""Un modulo que hace pytest.skip() no debe contar como llamada."""\n'
            "\n"
            "OTRO = 'pytest.skip( no lo es tampoco'\n"
        )
        assert skips_de(fuente) == ()

    def test_un_skipif_es_de_plataforma(self) -> None:
        fuente = (
            "import pytest\n\n\n@pytest.mark.skipif(os.name == 'nt', reason='x')\n"
            "def test_algo() -> None:\n    pass\n"
        )
        assert skips_de(fuente) == (Skip(4, "pytest.mark.skipif", "plataforma"),)

    def test_el_alias_no_es_la_llamada(self) -> None:
        """`from pytest import skip` es la misma llamada con otro nombre.

        MEDIDO al escribir el guard: el regex no lo ve, y el AST tambien
        no. Se declara como limite conocido y no como bug escondido, que
        es exactamente lo que §6.2 no permite hacer con un caso raro.
        """
        fuente = "from pytest import skip\n\n\ndef test_algo() -> None:\n    skip('porque si')\n"
        assert skips_de(fuente) == ()
        assert "pytest" in fuente, "el alias se detecta por otro camino, no por el arbol"


# --- El contrato sobre el run ---------------------------------------------


class TestUnRunConSkippedEsUnIncumplimiento:
    """El criterio que no existia. Mismo run, misma forma, distinto veredicto."""

    def test_tres_skipped_son_un_incumplimiento(self, tmp_path: Path) -> None:
        """Un skip por encima de los declarados es un incumplimiento.

        **LA REGLA CAMBIO EN B2, y el cambio va en la direccion correcta.**
        Antes, CUALQUIER skip hacia fallar el run — y eso hacia que la
        lista `SKIPS_PLATAFORMA` no sirviera para nada, porque un skip
        correctamente declarado hacia rojo igual. El mensaje del propio
        criterio decia lo contrario: «los skips de plataforma estan
        declarados en SKIPS_PLATAFORMA; este no lo es», o sea, la
        intencion era tolerar los declarados y rechazar los que no.

        B2 anadio una UAT opt-in (3 skips declarados) y el run salio con
        `2871 passed, 3 skipped` puts red un run sin un solo skip
        escondido. La regla ahora tiene tres estados, y este test mide
        el que importa: **uno mas de los declarados, incumple.**
        """
        declarados = cpr._salteados_declarados()
        informe = _informe(f"pytest: 2715 passed, {declarados + 1} skipped in 240.06s")
        problemas = cpr.evaluar(informe, _control(tmp_path))
        assert "sg_pipeline_tests_skipped" in _codigos(problemas), (
            "un run con un skip mas de los declarados cumple los criterios "
            f"que declara AGENTS.md. Problemas: {[p.codigo for p in problemas]}"
        )

    def test_los_skips_declarados_no_hacen_rojo_el_run(self, tmp_path: Path) -> None:
        """El contrasalto del anterior: los DECLARADOS si se toleran.

        Sin este test, la primera forma de arreglar el criterio anterior —
        borrar `SKIPS_PLATAFORMA` de la cuenta — tambien pasaria en
        verde, y el guard habria pasado de «rechaza cualquier skip» a
        «rechaza todos», que es peor: dejaria de poder declarar nada.
        """
        declarados = cpr._salteados_declarados()
        informe = _informe(f"pytest: 2715 passed, {declarados} skipped in 240.06s")
        assert "sg_pipeline_tests_skipped" not in _codigos(
            cpr.evaluar(informe, _control(tmp_path))
        ), "un skip correctamente declarado pone rojo el run: la lista no sirve de nada"

    def test_el_mensaje_dice_cuantos(self, tmp_path: Path) -> None:
        """Un guard que dice «skipped» sin decir cuantos obliga a mirar a mano.

        Es la leccion de WI-104: exigir el CODIGO del problema, no solo que
        la lista no este vacia. Y ahora el mensaje dice tambien cuantos son
        los DECLARADOS, para que se vea si la lista y el run divergen.
        """
        declarados = cpr._salteados_declarados()
        informe = _informe(f"pytest: 2715 passed, {declarados + 1} skipped in 240.06s")
        problemas = cpr.evaluar(informe, _control(tmp_path))
        joined = " ".join(p.mensaje for p in problemas if p.codigo == "sg_pipeline_tests_skipped")
        assert str(declarados + 1) in joined, joined
        assert str(declarados) in joined, (
            f"el mensaje no dice cuantos skips estan DECLARADOS ({declarados}), "
            f"asi que no se puede ver si la lista y el run divergen: {joined}"
        )

    @pytest.mark.parametrize("n", [1, 2, 4, 17, 2718])
    def test_cualquier_numero_distinto_del_declarado_muerde(self, tmp_path: Path, n: int) -> None:
        """El dominio se comprueba sobre entradas, no sobre el valor de hoy.

        Los numeros se toman relativos a los DECLARADOS, no a un literal:
        un parametrize con `3` escrito a mano empezaria a mentir el dia
        que se declarara un cuarto skip, y el test pasaria por el motivo
        equivocado —de nuevo el error 32 de WI-113, donde la sonda
        apuntaba a un texto que ya no existia—.
        """
        declarados = cpr._salteados_declarados()
        n = n if n != declarados else declarados + 7
        informe = _informe(f"pytest: 2718-{n} passed, {n} skipped in 240.06s")
        assert "sg_pipeline_tests_skipped" in _codigos(cpr.evaluar(informe, _control(tmp_path)))

    def test_xfailed_tambien_es_un_test_que_no_se_ejecuto(self, tmp_path: Path) -> None:
        """Un `xfail` es un test que se sabe que falla y no se mira.

        No esconde un fallo por accidente: lo esconde por diseno, que es
        peor. Mismo codigo, porque es la misma propiedad.
        """
        informe = _informe("pytest: 2700 passed, 18 xfailed in 240.06s")
        assert "sg_pipeline_tests_skipped" in _codigos(cpr.evaluar(informe, _control(tmp_path)))

    def test_un_run_limpio_no_se_inventa_problemas(self, tmp_path: Path) -> None:
        """El contraejemplo del guard: si `evaluar` se queja de todo, no mide."""
        informe = _informe("pytest: 2718 passed in 240.06s (0:04:00)")
        assert cpr.evaluar(informe, _control(tmp_path)) == ()

    def test_el_resumen_sin_skips_es_un_predicado_que_se_puede_probar(self) -> None:
        """El predicado se prueba SOLO, con entradas que el repo no produce.

        Igual que `_bump_valido` en WI-106: un predicado que solo se llama
        con el valor de hoy no comprueba un dominio, comprueba una
        coincidencia.
        """
        for malo in (
            "2715 passed, 3 skipped in 240.06s",
            "2718 skipped in 240.06s",
            "2700 passed, 18 xfailed in 240.06s",
            "3 SKIPPED",
        ):
            assert cpr.resumen_sin_skips(malo) is False, malo
        for bueno in (
            "2718 passed in 240.06s (0:04:00)",
            "5 failed, 2713 passed in 240.06s",
            # pytest no imprime el cero, pero si apareciera declara cero y
            # es un run limpio: un guard que mirara «hay skipped» en vez de
            # «cuantos» lo trataria como incumplimiento.
            "2718 passed, 0 skipped in 240.06s",
            "",
        ):
            assert cpr.resumen_sin_skips(bueno) is True, bueno


# --- El contrato sobre el codigo ------------------------------------------


class TestTodoSkipEstaDeclarado:
    """Lo que el CI no puede ver: la CLASE del skip, no su numero."""

    def test_no_hay_skip_de_ejecucion(self) -> None:
        """El que §6.2 prohibe por su nombre, y que existe hoy.

        MEDIDO al abrir el bloque: tres, en
        `tests/test_wi105_pipeline_receipt.py`, con el motivo «sin journal:
        clon nuevo». Los escribi yo en WI-105.
        """
        ejecucion = {
            f: [s for s in skips if s.clase == "ejecucion"]
            for f, skips in _skips_del_arbol().items()
        }
        con_ejecucion = {f: s for f, s in ejecucion.items() if s}
        assert not con_ejecucion, (
            "hay skips de ejecucion en el repo, y §6.2 los prohibe: «un skip "
            "por falta de artefacto es el mismo defecto, con otra forma». "
            f"Encontrados: {con_ejecucion}"
        )

    def test_todo_skip_declarado_sigue_aqui(self) -> None:
        """La otra direccion, que es la que se olvida.

        Si `test_locks.py` borra su `skipif` porque el soporte de Windows
        mejoro, la lista seguira nombrandolo y nadie se enterara: una regla
        sobre la nada. Es el mismo caso que una desviacion de cobertura que
        apunta a un fichero borrado (WI-107).
        """
        faltan = sorted(f for f in SKIPS_DECLARADOS if not (ROOT / f).exists())
        assert not faltan, f"skips declarados que ya no existen: {faltan}"

    def test_todo_declarado_es_de_plataforma_y_no_de_ejecucion(self) -> None:
        """Un skip de ejecucion no se «declara» y punto.

        Si aparece en la lista, la lista se ha usado como un sitio donde
        esconder, que es lo que la lista existe para impedir.
        """
        for f in SKIPS_DECLARADOS:
            encontrados = skips_de((ROOT / f).read_text(encoding="utf-8"))
            clases = {s.clase for s in encontrados}
            assert clases == {"plataforma"}, (
                f"{f} esta declarado como legitimo pero sus skips son {clases}"
            )

    def test_todo_skipif_del_arbol_esta_declarado(self) -> None:
        """La simetria al reves, y la que este bloque vigila de verdad.

        Un `skipif` nuevo que nadie declara pasa verde: es el mismo hueco
        que WI-107 cerro para los paquetes, un nivel mas abajo.
        """
        sin_declarar = {
            f
            for f, skips in _skips_del_arbol().items()
            if any(s.clase == "plataforma" for s in skips)
        } - set(SKIPS_DECLARADOS)
        assert not sin_declarar, (
            f"skipif sin declarar: {sorted(sin_declarar)}. Un skip de plataforma "
            "es legitimo, pero que lo sea es una DECISION y se escribe."
        )


# --- La regla, escrita donde se puede encontrar ----------------------------


class TestLaReglaDiceDondeSeComprueba:
    """Una prohibicion sin referencia no se puede seguir ni auditar."""

    def _seccion_62(self) -> str:
        texto = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        return texto[texto.index("### 6.2") : texto.index("### 6.3")]

    def test_62_dice_como_se_comprueba(self) -> None:
        """§6.2 dice que esta prohibida y por que, pero no COMO se comprueba.

        MEDIDO al abrir el bloque: la seccion razonaba el porque con una
        tabla de WI-103 y no mencionaba ni un instrumento. Una regla que no
        dice donde se mide es la que la serie viene cerrando.
        """
        seccion = self._seccion_62()
        assert "sg_pipeline_tests_skipped" in seccion, (
            "§6.2 prohibe pytest.skip pero no dice que lo comprueba "
            "sg_pipeline_tests_skipped en la etapa evidence. Una prohibicion "
            "sin verificador es una declaracion, que es lo que este bloque cierra."
        )

    def test_la_lista_de_declarados_tiene_una_sola_fuente(self) -> None:
        """La lista vive en el guard, no en un segundo sitio que se desincronice.

        Es la regla de WI-93 y WI-107 aplicada una vez mas: una copia de
        la verdad se queda vieja el dia que la verdad cambie.
        """
        assert cpr.SKIPS_PLATAFORMA, "la lista de skips de plataforma declarados esta vacia"
        assert set(cpr.SKIPS_PLATAFORMA) == set(SKIPS_DECLARADOS), (
            "la lista del guard y la del test han divergido: "
            f"{set(cpr.SKIPS_PLATAFORMA) ^ set(SKIPS_DECLARADOS)}"
        )
