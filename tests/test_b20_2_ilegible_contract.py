"""B20-2: `project_truth.py` tiene DOS respuestas, y solo una se miraba.

El hallazgo
-----------
`scripts/project_truth.py` no tiene una salida: tiene DOS, y las dos son JSON
valido. La de `Estado` trae las cinco verdades y `coherente`; la de
`VerdadNoLegible` trae `coherente: false` e `ilegible`, y **ninguna** de las
cinco. El codigo de salida las distingue —0/1 contra 2— pero la FORMA no se
parece en nada, y por eso son dos contratos y no uno con un campo a veces
ausente.

De sus consumidores, uno conocia la segunda forma
(`measure_b14_truth_single_reader.py`, que lee `ilegible`) y los otros dos no:

- `tests/test_b0_truth_convergence.py` hacia `carga["bloque"]` sobre las dos, y
  sobre la segunda reventaba con `KeyError: 'bloque'`: el guard que existe
  para explicar por que el proyecto no esta bien era el que no lo explicaba.
- `measure_b9_gate_1_0.py` caia en la rama de contradicciones y devolvia
  `OPEN` con la lista VACIA: un veredicto que afirma que la propiedad no se
  cumple cuando lo que pasa es que el instrumento no pudo leer, y que ademas
  orienta mal —`OPEN` pide arreglar el proyecto y aqui lo que hay que
  arreglar es una verdad rota.

Que se separen los dos veredictos
--------------------------------
`NO_MEASURABLE` existe en el vocabulario de la cabecera del gate para
exactamente esto: «no hay forma de decidirla con este entorno, y se dice por
que». Las dos dejan 1.0 lejos —declarar `PASS` seria la unica forma de
mentir—, asi que aqui no se esta ablandando el gate: se esta dejando de
confundir «no se cumple» con «no se ha podido mirar».

Lo que estos tests NO hacen
---------------------------
No fabrican la carga. Levantan un arbol de verdad con una verdad rota,
ejecutan el script de verdad ahi, y pasan **su salida** al predicado. Una
carga escrita en el test seria el error de WI-106 aplicado a un test: el
guard comprobando su propia copia.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any

RAIZ = Path(__file__).resolve().parents[1]
SCRIPT = RAIZ / "scripts" / "project_truth.py"
GATE = RAIZ / "scripts" / "measure_b9_gate_1_0.py"

#: Lo unico que el script lee. Se copia al sandbox, con el script dentro, para
#: que su `RAIZ` —derivado de `__file__`— sea el sandbox y no el repositorio.
LOS_FICHEROS_DE_LA_VERDAD = (
    "STATE.yaml",
    "ROADMAP.md",
    "CURRENT.md",
    "src/skillgraph/__init__.py",
)


def _carga_el_gate() -> ModuleType:
    """El gate, cargado por ruta porque `scripts/` no es un paquete.

    El `sys.modules[...] = modulo` antes de ejecutar NO es decorativo: el gate
    declara dataclasses, y `dataclasses` busca `sys.modules[cls.__module__]`
    para resolver anotaciones. Sin el registro, cargar el modulo revienta con
    `AttributeError: 'NoneType' object has no attribute '__dict__'`.
    """
    spec = importlib.util.spec_from_file_location("gate_b20_2", GATE)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    sys.modules["gate_b20_2"] = modulo
    spec.loader.exec_module(modulo)
    return modulo


def _arbol_roto(destino: Path) -> Path:
    """Un arbol donde `__init__.py` existe pero ya no declara `__version__`.

    Es la causa mas economica de provocar la rama, y la que nombra el propio
    script en su linea 183.
    """
    for relativo in LOS_FICHEROS_DE_LA_VERDAD:
        destino_fichero = destino / relativo
        destino_fichero.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(RAIZ / relativo, destino_fichero)
    (destino / "scripts").mkdir(parents=True, exist_ok=True)
    shutil.copy2(SCRIPT, destino / "scripts" / SCRIPT.name)
    (destino / "src" / "skillgraph" / "__init__.py").write_text(
        "# el fichero existe pero ya no declara la version\n", encoding="utf-8"
    )
    return destino


def _respuesta_real(raiz: Path) -> subprocess.CompletedProcess[str]:
    """La salida REAL del script, ejecutada en `raiz`."""
    return subprocess.run(
        [sys.executable, str(raiz / "scripts" / SCRIPT.name)],
        cwd=raiz,
        capture_output=True,
        text=True,
        check=False,
    )


class TestLaRespuestaIlegibleNoEsUnaContradiccion:
    """La rama nueva, y la de al lado, que no puede quedar absorbida."""

    def test_una_verdad_rota_sale_ilegible_y_no_contradictoria(self) -> None:
        """Que las dos formas sean de verdad distintas, no una con campos a menos.

        Sin esto, la rama nueva se podria activar con cualquier respuesta
        `coherente: false` y tragarse la de contradicciones de al lado.
        """
        with tempfile.TemporaryDirectory(prefix="b20_2_ilegible_") as tmp:
            proc = _respuesta_real(_arbol_roto(Path(tmp)))

        carga = json.loads(proc.stdout)
        assert proc.returncode == 2, f"una verdad ilegible sale con 2, dio {proc.returncode}"
        assert carga.get("ilegible"), f"la respuesta no nombra la causa: {carga}"
        assert carga.get("contradicciones") is None, (
            "la rama ilegible no trae contradicciones: si las trajera, el "
            f"consumidor no podria decir cual de las dos formas es. Trae: {carga}"
        )

    def test_el_predicado_dice_instrumento_y_no_proyecto(self, monkeypatch) -> None:
        """La propiedad: `NO_MEASURABLE` con la causa, no `OPEN` en silencio.

        Se redirige SOLO donde se lanza el subproceso —el `_corre` del gate— y
        se le pasa la salida real del script sobre el arbol roto. El resto del
        predicado es el de produccion.
        """
        gate = _carga_el_gate()
        with tempfile.TemporaryDirectory(prefix="b20_2_ilegible_") as tmp:
            real = _respuesta_real(_arbol_roto(Path(tmp)))
        monkeypatch.setattr(gate, "_corre", lambda *a, **k: real)

        veredicto, evidencia = gate._roadmap_state_docs_coherentes()

        assert veredicto == "NO_MEASURABLE", (
            "una respuesta ilegible NO es una propiedad que no se cumple: "
            f"el veredicto fue {veredicto!r} con la evidencia {evidencia!r}"
        )
        assert "__version__" in evidencia, (
            "la evidencia no dice que verdad se rompio, luego quien lee tiene "
            f"que abrir el script a adivinar. Decia: {evidencia!r}"
        )
        assert "contradiccion" in evidencia.lower(), (
            "la evidencia tiene que decir por que NO es una contradiccion: sin "
            f"eso las dos ramas se confunden. Decia: {evidencia!r}"
        )

    def test_una_contradiccion_de_verdad_sigue_diciendo_OPEN(self, monkeypatch) -> None:
        """La otra direccion: la rama nueva NO se come la de al lado.

        Es el contrasalto de conjuntos disjuntos. Si el `if ilegible` se
        comiera tambien la respuesta coherente-falsa, el gate dejaria de
        distinguir «esto no cuadra» de «no lo he podido mirar», que es
        justamente el defecto que B19 cerro en otro sitio y que aqui volveria
        a abrir por la puerta de atras.
        """
        gate = _carga_el_gate()
        carga: dict[str, Any] = {
            "coherente": False,
            "contradicciones": ["workitem: STATE dice B19, CURRENT dice B20"],
        }
        proc = subprocess.CompletedProcess(
            args=["project_truth.py"], returncode=1, stdout=json.dumps(carga), stderr=""
        )
        monkeypatch.setattr(gate, "_corre", lambda *a, **k: proc)

        veredicto, evidencia = gate._roadmap_state_docs_coherentes()

        assert veredicto == "OPEN", (
            f"una contradiccion de verdad sigue siendo OPEN, dio {veredicto!r}"
        )
        assert "B19" in evidencia and "B20" in evidencia, (
            f"la evidencia tiene que nombrar las dos caras, dio: {evidencia!r}"
        )
        assert "NO_MEASURABLE" not in evidencia, (
            "la rama ilegible se ha comido la de contradicciones"
        )

    def test_una_respuesta_sana_sigue_diciendo_PASS(self, monkeypatch) -> None:
        """Y la tercera: que el camino de siempre no se haya roto.

        Con tres casos y ningun contrasalto en la direccion de «sigue
        funcionando», un arreglo puede dejar el camino bueno peor que antes y
        los tres tests de arriba no lo ven.
        """
        gate = _carga_el_gate()
        carga: dict[str, Any] = {
            "bloque": "B20",
            "coherente": True,
            "version": "0.32.5.dev0",
            "tests_declarados": 3412,
            "tests_reales": 3412,
        }
        proc = subprocess.CompletedProcess(
            args=["project_truth.py"], returncode=0, stdout=json.dumps(carga), stderr=""
        )
        monkeypatch.setattr(gate, "_corre", lambda *a, **k: proc)

        veredicto, evidencia = gate._roadmap_state_docs_coherentes()

        assert veredicto == "PASS", f"la respuesta sana tiene que seguir en PASS, dio {veredicto!r}"
        assert "B20" in evidencia, f"la evidencia del PASS perdio el bloque: {evidencia!r}"
