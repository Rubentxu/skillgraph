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

RAIZ = Path("/var/mnt/DiscoChino2-fast/Proyectos/python/skillgraph")
MUTABLES = ("STATE.yaml", "ROADMAP.md", "CURRENT.md", "src/skillgraph/__init__.py")


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


def main() -> int:
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
        muta(
            "STATE.yaml",
            texto("STATE.yaml").replace(
                "  current_workitem: B13",
                "  current_workitem: B13\n  current_workitem: B99_inventado",
                1,
            ),
        )
        rc, salida = _corre()
        c = _coherente(salida)
        import json

        try:
            contras = json.loads(salida).get("contradicciones")
        except json.JSONDecodeError:
            contras = None
        PREGUNTAS[1]["cumple"] = not (rc == 0 and c is True)
        PREGUNTAS[1]["detalle"] = f"rc={rc} coherente={c} contradicciones={contras}"
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
        PREGUNTAS[2]["cumple"] = c is False
        PREGUNTAS[2]["detalle"] = f"rc={rc} coherente={c}"
        arbol.restaura()

        # 4. Workitem que no existe en ninguna parte.
        muta(
            "STATE.yaml",
            texto("STATE.yaml").replace("  current_workitem: B13", "  current_workitem: B99", 1),
        )
        rc, salida = _corre()
        c = _coherente(salida)
        PREGUNTAS[3]["cumple"] = c is False
        PREGUNTAS[3]["detalle"] = f"rc={rc} coherente={c}"
        arbol.restaura()

        # 5. Version activa incoherente con el tag.
        original_init = texto("src/skillgraph/__init__.py")
        muta("src/skillgraph/__init__.py", '__version__ = "7.7.7"\n')
        rc, salida = _corre()
        c = _coherente(salida)
        PREGUNTAS[4]["cumple"] = c is False
        PREGUNTAS[4]["detalle"] = f"rc={rc} coherente={c}"
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
        PREGUNTAS[5]["cumple"] = not (rc == 0 and c is True)
        PREGUNTAS[5]["detalle"] = f"rc={rc} coherente={c} salida={salida.strip()[:90]!r}"
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
        muta(
            "STATE.yaml",
            texto("STATE.yaml").replace("  current_workitem: B13", "  current_workitem: B99", 1),
        )
        rc, salida = _corre()
        try:
            contras = json.loads(salida).get("contradicciones") or []
        except json.JSONDecodeError:
            contras = []
        PREGUNTAS[7]["cumple"] = bool(contras) and "B13" in " ".join(contras)
        PREGUNTAS[7]["detalle"] = f"contradicciones={contras}"
        arbol.restaura()

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
