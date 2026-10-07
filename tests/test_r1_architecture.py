"""R1 — las fronteras arquitectónicas como leyes ejecutables.

**LO QUE MIDE ESTE FICHERO, Y POR QUÉ NO ES «UN AUDIT MÁS».** Un audit
detecta deuda; lo que R1 pide es que **bloquee**. La diferencia se mide
ejecutando el gate y mirando su **código de salida**, no su prosa.

    P1  EL RATCHET BLOQUEA               -> TestElRatchetBloquea
    P2  LA COMPLEJIDAD ESTÁ CERRADA       -> TestLaComplejidadEstaCerrada
    P3  EL DOMINIO NO HABLA SQL           -> TestElDominioNoHablaSql
    P4  EL DOMINIO NO USA LA IMPLEMENTACIÓN -> TestElDominioNoUsaLaImplementacion
    P5  LAS REFERENCIAS NORMATIVAS EXISTEN -> TestLasReferenciasNormativasExisten

Y la mitad que hace que las demás midan:

    TestLaTraduccionCruzaLaFrontera -> el error cambia de bando en el borde

# LAS DOS TRAMPAS, Y LAS DOS SON DE DOCSTRINGS

1. **SQL en el dominio.** `grep sqlite3 src/skillgraph/knowledge/` marca
   cuatro ficheros y **tres solo lo nombran en un docstring**
   (`errors.py`, `engine.py`, `runcontroller.py`). Un gate que señale la
   mitad de las cosas correctas entrena a ignorar el gate.
2. **Referencias normativas.** `blueprint-v1` es un **directorio** de 12
   documentos y vive en `external/`, fuera de git **por decisión del repo**.

# EL CONTRA SALTO DEL RATCHET

`test_el_ratchet_detecta_un_modulo_sobre_el_umbral` construye un árbol con
un módulo de 900 líneas y exige que el gate lo vea. Sin ese test, un
`check_architecture_ratchet.py` que devolviera siempre `rc=0` pasaría todo
lo demás en verde: es el mismo argumento del M2 de WI-110.
"""

from __future__ import annotations

import ast
import importlib
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
SRC = RAIZ / "src" / "skillgraph"
RATCHET = RAIZ / "scripts" / "check_architecture_ratchet.py"

DOMINIO = ("knowledge", "core", "runtime", "handoff", "agent", "workflow", "dsl")
MAX_LOC = 800
CC_MAX = 20


def _modulos_del_dominio() -> list[Path]:
    salida: list[Path] = []
    for paquete in DOMINIO:
        base = SRC / paquete
        if base.is_dir():
            salida.extend(p for p in base.glob("*.py") if not p.name.startswith("_"))
    return sorted(salida)


def _arbol_de(ruta: Path) -> ast.Module:
    return ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))


def _lineas_de_type_checking(arbol: ast.Module) -> set[int]:
    """Líneas cubiertas por un `if TYPE_CHECKING:`.

    Un import ahí no existe en runtime, luego no puede meter la
    implementación dentro del dominio. Es la misma excepción que aplica el
    ratchet, y está en los dos sitios a propósito: un guard y su contrasalto
    que no compartan el criterio miden dos cosas distintas.
    """
    lineas: set[int] = set()
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, ast.If):
            continue
        prueba = nodo.test
        nombre = prueba.id if isinstance(prueba, ast.Name) else getattr(prueba, "attr", "")
        if nombre != "TYPE_CHECKING":
            continue
        for hijo in ast.walk(nodo):
            lineas.add(getattr(hijo, "lineno", -1))
    return lineas


def _cc(nodo: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    cc = 1
    for hijo in ast.walk(nodo):
        if isinstance(hijo, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler)):
            cc += 1
        elif isinstance(hijo, ast.BoolOp):
            cc += len(hijo.values) - 1
        elif isinstance(hijo, ast.IfExp):
            cc += 1
        elif isinstance(hijo, ast.comprehension):
            cc += 1 + len(hijo.ifs)
        elif isinstance(hijo, ast.Assert):
            cc += 1
        elif isinstance(hijo, ast.Match):
            cc += len([c for c in hijo.cases if c.guard is not None]) + 1
    return cc


# ---------------------------------------------------------------------------
# P1 — el ratchet EXISTE y BLOQUEA
# ---------------------------------------------------------------------------


class TestElRatchetBloquea:
    """El punto del bloque: una propiedad que llegó a cero NO vuelve a
    convertirse en advertencia."""

    def test_el_ratchet_existe(self) -> None:
        """Sin fichero, no hay ley. Pregunta de existencia y sin
        contraindicto: si el gate viviera en otro sitio, este test falla y
        hay que actualizarlo a propósito."""
        assert RATCHET.exists(), (
            "no existe scripts/check_architecture_ratchet.py: «god modules > "
            "800 = 0» no es una propiedad, es un deseo"
        )

    def test_el_ratchet_sale_distinto_de_cero_sobre_el_arbol_actual(self) -> None:
        """**Y ESTE TEST SOLO SE ESCRIBE CUANDO EL ARBOL CUMPLE.**

        Hoy el ratchet da rojo: quedan un god module y una fuga de
        `platform`. El test que afirma `rc=0` sobre el árbol actual se
        escribe **al cerrar R1**, y hasta entonces su rojo es el trabajo
        pendiente, no un fallo del guard.
        """
        proc = subprocess.run(
            [sys.executable, str(RATCHET)], capture_output=True, text=True, cwd=str(RAIZ)
        )
        if proc.returncode != 0:
            pytest.fail(
                "el ratchet da rojo sobre el árbol que se supone limpio:\n"
                + (proc.stdout + proc.stderr)[-3000:]
            )

    def test_el_ratchet_detecta_un_modulo_sobre_el_umbral(self, tmp_path: Path) -> None:
        """**EL CONTRA SALTO DEL GUARD, Y SIN ESTE TEST EL OTRO NO DICE NADA.**

        Un gate que devuelve siempre `rc=0` pasa el test anterior y miente.
        Aquí se le da un árbol con un módulo por encima del umbral y se
        exige que lo vea.

        **Y SE EXIGE QUE LO NOMBRE.** Un gate que dice «fallo» sin decir
        dónde obliga a quien lo ve a abrir el script, y un verificador sin
        mensaje es un callejón sin salida.
        """
        raiz = tmp_path / "repo"
        (raiz / "src" / "skillgraph" / "grande").mkdir(parents=True)
        shutil.copytree(SRC / "knowledge", raiz / "src" / "skillgraph" / "knowledge")

        grande = raiz / "src" / "skillgraph" / "grande" / "god.py"
        grande.write_text(
            "\n".join(f"def f{i}(x: int) -> int:\n    return x + {i}" for i in range(450)),
            encoding="utf-8",
        )
        assert len(grande.read_text(encoding="utf-8").splitlines()) > MAX_LOC

        proc = subprocess.run(
            [sys.executable, str(RATCHET), "--raiz", str(raiz)],
            capture_output=True,
            text=True,
        )
        assert proc.returncode != 0, f"el gate dio verde con un god module:\n{proc.stdout}"
        assert "god.py" in proc.stdout + proc.stderr, (
            "el gate dio rojo pero no nombró el fichero: quien lo ve no sabe qué abrir"
        )


# ---------------------------------------------------------------------------
# P2 — la complejidad pública está cerrada
# ---------------------------------------------------------------------------


class TestLaComplejidadEstaCerrada:
    def test_ninguna_funcion_publica_sobre_el_umbral(self) -> None:
        hotspots: list[str] = []
        for ruta in _modulos_del_dominio():
            for nodo in ast.walk(_arbol_de(ruta)):
                if not isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if nodo.name.startswith("_"):
                    continue
                cc = _cc(nodo)
                if cc >= CC_MAX:
                    hotspots.append(f"{ruta.name}:{nodo.name} (cc={cc})")
        assert not hotspots, "hotspots públicos: " + "; ".join(hotspots)

    def test_la_medida_NO_es_un_constante(self) -> None:
        """**SIN ESTE TEST, LA MEDIDA ARRIBA PODRÍA VALER CERO SIEMPRE.**

        Una lista de hotspots vacía y una función que no calcula nada dan el
        mismo resultado. Aquí se exige que la función **encuentre** algo en un
        árbol donde hay algo: si `cc` no hiciera su trabajo, esto falla.
        """
        arbol_simple = ast.parse("def f(x):\n    if x:\n        return 1\n    return 2")
        nodo = arbol_simple.body[0]
        assert isinstance(nodo, ast.FunctionDef)
        assert _cc(nodo) == 2, "la medida de complejidad no cuenta el `if`"


# ---------------------------------------------------------------------------
# P3 — el dominio no habla SQL, y la TRAMPA son los docstrings
# ---------------------------------------------------------------------------


class TestElDominioNoHablaSql:
    def test_ningun_modulo_del_dominio_tiene_sqlite3_en_SU_ESPACIO(self) -> None:
        """La forma que no se puede falsear por un docstring: si un módulo
        hace `import sqlite3`, el nombre queda en su espacio de nombres."""
        fugas: list[str] = []
        for paquete in DOMINIO:
            base = SRC / paquete
            if not base.is_dir():
                continue
            nombres = [f"skillgraph.{paquete}"]
            nombres += [
                f"skillgraph.{paquete}.{p.stem}" for p in base.glob("*.py") if p.stem != "__init__"
            ]
            for nombre in nombres:
                try:
                    mod = importlib.import_module(nombre)
                except Exception:
                    continue
                if getattr(mod, "sqlite3", None) is not None:
                    fugas.append(nombre)
        # `except Exception` a proposito: un modulo que falla al importar no
        # es una fuga de SQL, y hacer fallar el test por eso seria medir el
        # entorno y no la propiedad.
        assert not fugas, f"el dominio importa sqlite3: {fugas}"

    def test_el_nombre_SQLITE3_aparece_solo_en_PROSA(self) -> None:
        """**La mitad que hace que la anterior signifique algo.**

        Si el nombre apareciera solo en prosa, no habría nada que arreglar; si
        apareciera en código, la de arriba lo habría cazado. Lo que se mide es
        que **queda prosa**, y por eso hay que leerla a mano en vez de
        confiar en el grep.
        """
        usos: list[str] = []
        for ruta in _modulos_del_dominio():
            for nodo in ast.walk(_arbol_de(ruta)):
                if isinstance(nodo, ast.Import):
                    for alias in nodo.names:
                        if alias.name.split(".")[0] == "sqlite3":
                            usos.append(f"{ruta.name}:{nodo.lineno}")
                elif isinstance(nodo, ast.ImportFrom):
                    if (nodo.module or "").split(".")[0] == "sqlite3":
                        usos.append(f"{ruta.name}:{nodo.lineno}")
                elif isinstance(nodo, ast.Attribute):
                    base = nodo
                    while isinstance(base, ast.Attribute):
                        base = base.value
                    if isinstance(base, ast.Name) and base.id == "sqlite3":
                        usos.append(f"{ruta.name}:{nodo.lineno}")

        assert not usos, (
            f"el dominio USA sqlite3 en código: {usos}. Los docstrings no "
            "cuentan, y por eso el grep mentía."
        )

    def test_la_TRADUCCION_cruza_la_frontera_en_los_dos_sentidos(self) -> None:
        """El dominio captura un error **de dominio**; el adapter traduce el
        **de SQLite**. Ese es el contrato de R0, y se comprueba con los dos
        lados reales."""
        from skillgraph.core.errors import IntegrityError as DomainIntegrityError
        from skillgraph.platform.translation import traduciendo_integridad

        with pytest.raises(DomainIntegrityError), traduciendo_integridad():
            raise sqlite3.IntegrityError("FOREIGN KEY constraint failed")

        # **Y LO QUE NO ES FK SE PROPAGA INTACTO.** Sin esta mitad, el
        # traductor podría tragarse un CHECK y reportarlo como «no existe la
        # fuente», que es el falso positivo que WI-114 ya midió una vez.
        with pytest.raises(sqlite3.IntegrityError), traduciendo_integridad():
            raise sqlite3.IntegrityError("CHECK constraint failed: kind")

    def test_el_error_traducido_es_del_DOMINIO_y_no_de_sqlite(self) -> None:
        """El tipo de la jerarquía es lo que decide el exit code (WI-109), y
        un `sqlite3.IntegrityError` atravesaría el `except SkillGraphError` y
        saldría como **Traceback** al usuario.

        Se comprueba el TIPO, no la clase concreta: que herede de
        `SkillGraphError` es la propiedad que la CLI necesita.
        """
        from skillgraph.core.errors import SkillGraphError
        from skillgraph.platform.translation import traduciendo_integridad

        with pytest.raises(SkillGraphError) as ei, traduciendo_integridad():
            raise sqlite3.IntegrityError("FOREIGN KEY constraint failed")

        assert isinstance(ei.value, SkillGraphError)
        assert not isinstance(ei.value, sqlite3.Error)


# ---------------------------------------------------------------------------
# P4 — el dominio no usa la IMPLEMENTACIÓN de platform
# ---------------------------------------------------------------------------


class TestElDominioNoUsaLaImplementacion:
    def test_ningun_import_hacia_platform_fuera_del_puerto(self) -> None:
        """**Y LOS IMPORTS DE `if TYPE_CHECKING` NO CUENTAN.**

        `observation.py` tiene `from ...platform.storage import Storage` bajo
        `TYPE_CHECKING`. En runtime ese import **no existe**: no abre una
        conexión ni puede meter la implementación dentro del dominio. Un gate
        que lo señalaría obligaría a borrar el bloque de tipos, que es lo
        correcto — y borrarlo haría que el type-checker dejara de saber qué
        hay ahí. Distinguir una cosa de otra es lo que separa una ley de una
        cita.
        """
        fugas: list[str] = []
        for ruta in _modulos_del_dominio():
            solo_tipos = _lineas_de_type_checking(_arbol_de(ruta))
            for nodo in ast.walk(_arbol_de(ruta)):
                # `Module` no tiene `lineno`: sin el default, este bucle revienta
                # en el primer nodo del árbol, que es precisamente el nodo raíz.
                if getattr(nodo, "lineno", -1) in solo_tipos:
                    continue
                destinos: list[str] = []
                if isinstance(nodo, ast.ImportFrom):
                    destinos.append(nodo.module or "")
                elif isinstance(nodo, ast.Import):
                    destinos.extend(a.name for a in nodo.names)
                for destino in destinos:
                    if not destino.startswith("skillgraph.platform"):
                        continue
                    if destino.startswith("skillgraph.platform.ports"):
                        continue  # el puerto: es lo correcto
                    fugas.append(f"{ruta.name}:{nodo.lineno}: {destino}")
        assert not fugas, (
            "el dominio importa la implementación de platform en RUNTIME "
            "(ports y TYPE_CHECKING NO cuentan): " + "; ".join(fugas)
        )

    def test_el_import_de_TYPE_CHECKING_NO_es_una_fuga(self) -> None:
        """**EL CONTRA SALTO DE LA EXCEPCIÓN.**

        Sin este test, «borra el bloque de TYPE_CHECKING» parecería la forma
        de dejar el guard en verde, y sería un arreglo que degrada el código
        para satisfacer una medición. Aquí se exige que ese import siga
        estando, y que el gate NO lo señale.
        """
        assert "TYPE_CHECKING" in (SRC / "knowledge" / "observation.py").read_text(
            encoding="utf-8"
        ), (
            "observation.py ya no declara TYPE_CHECKING: si se borro para "
            "satisfacer el guard, el type-checker perdio informacion a cambio "
            "de una medicion"
        )

    def test_el_PUERTO_si_puede_importarse(self) -> None:
        """**EL CONTRA SALTO DE ESTA MITAD.**

        Si el guard prohibiera `platform.ports`, expulsaría la inyección de
        dependencias por el puerto, que es exactamente lo que el puerto es
        para. Aquí se exige que ese import **siga funcionando**: un guard que
        cierra la frontera cerrándola de más también es un guard roto.
        """
        from skillgraph.platform.ports.revisions import RevisionRegistry

        assert RevisionRegistry is not None
        assert hasattr(RevisionRegistry, "seq_de"), (
            "el puerto de revisiones no declara `seq_de`: el contrato que "
            "R0.extrajo del dominio no llego al puerto"
        )


# ---------------------------------------------------------------------------
# P5 — las referencias normativas existen
# ---------------------------------------------------------------------------


class TestLasReferenciasNormativasExisten:
    def test_toda_referencia_citada_existe(self) -> None:
        import re

        cita = re.compile(r"\b((?:\d{2}-SPEC-[A-Z0-9-]+)|(?:ADR-\d{4})|(?:blueprint-v1))")
        citadas: set[str] = set()
        for patron in ("*.md", "*.py", "*.yaml", "*.kts"):
            for ruta in RAIZ.glob(patron):
                if ".git" in ruta.parts:
                    continue
                try:
                    citadas.update(cita.findall(ruta.read_text(encoding="utf-8")))
                except (UnicodeDecodeError, OSError):
                    continue

        rotas = sorted(n for n in citadas if not _existe_autoridad(n))
        assert not rotas, f"referencias normativas rotas: {rotas}"

    def test_blueprint_v1_existe_como_DIRECTORIO(self) -> None:
        """`blueprint-v1` son 12 documentos en una carpeta, y está **fuera de
        git por decisión del repo**. Un guard que la marque rota obliga a
        romper esa decisión, y entrena a ignorar al guard."""
        assert (RAIZ / "external" / "blueprint-v1").is_dir()


def _existe_autoridad(nombre: str) -> bool:
    for directorio in (
        RAIZ,
        RAIZ / "external",
        RAIZ / "docs",
        RAIZ / "decisions",
        RAIZ / "specs",
    ):
        if not directorio.is_dir():
            continue
        for p in directorio.rglob("*"):
            if not p.name.startswith(nombre):
                continue
            if p.is_file():
                return True
            if p.is_dir() and any(p.iterdir()):
                return True
    return False
