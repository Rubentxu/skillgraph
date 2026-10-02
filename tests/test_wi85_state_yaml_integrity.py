"""WI-85: `STATE.yaml` no puede volver a descartar informacion en silencio.

`STATE.yaml` es el punto de recuperacion durable del proyecto y su
encabezado dice "apunta a la verdad observable". El 2026-10-02 se midio
que tenia **7 claves YAML duplicadas**, y que el parser descarta en
silencio quedandose con la ultima:

    delta_wi12            (x2, descripciones distintas del mismo bloque)
    total                 (x3, dentro de `tests:`)
    refactor_v070_summary (x2)
    nota                  (x3, una por release en la lista)

El dano no era academico. `tests.total` **parseaba como `85%`** —un
porcentaje de cobertura de un snapshot que acabo anidado por error
dentro de `tests:`— en vez del numero de tests. Un lector humano del
fichero veia `1431`; cualquier cosa que lo parseara veia `85%`. Es
exactamente el modo de fallo que este proyecto rechaza en el codigo
(un dato plausible y falso es peor que un error) apareciendole en su
propio registro de estado.

`yaml.safe_load` NO avisa de esto: es especificacion YAML que la clave
repetida se descarta. Por eso hace falta una red explicita.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATE = PROJECT_ROOT / "STATE.yaml"


def _duplicate_keys(path: Path) -> list[tuple[str, int]]:
    """(clave, linea) de cada clave repetida dentro de un mismo mapping.

    Se usa `yaml.compose` y no un constructor de mapping a medida: el
    grafo de nodos crudo es lo unico que deja ver las claves repetidas,
    y un constructor casero que devuelve dict plano rompe el parsing de
    los bloques anidados (produce `ParserError` que parecen culpa del
    fichero, no del detector).
    """
    found: list[tuple[str, int]] = []
    with path.open(encoding="utf-8") as fh:
        root = yaml.compose(fh)

    def walk(node: Any) -> None:
        if isinstance(node, yaml.MappingNode):
            seen: set[str] = set()
            for key_node, value_node in node.value:
                if isinstance(key_node, yaml.ScalarNode):
                    name = str(key_node.value)
                    if name in seen:
                        found.append((name, key_node.start_mark.line + 1))
                    seen.add(name)
                walk(key_node)
                walk(value_node)
        elif isinstance(node, yaml.SequenceNode):
            for item in node.value:
                walk(item)

    walk(root)
    return found


class TestStateYamlIntegrity:
    def test_state_yaml_has_no_duplicate_keys(self) -> None:
        """Ninguna clave puede repetirse: el parser se queda con la ultima.

        El fallo es silencioso por especificacion YAML, asi que sin este
        test no hay ninguna senal. Y el modo de degradacion es
        especialmente traicionero: no rompe nada, simplemente deja de
        existir un dato.
        """
        duplicates = _duplicate_keys(STATE)
        assert not duplicates, (
            "STATE.yaml tiene claves duplicadas que el parser descarta en "
            f"silencio: {duplicates}. Cada una es informacion perdida. "
            "Renombrar la entrada que quede tapada."
        )

    def test_tests_total_is_a_count_not_a_percentage(self) -> None:
        """`tests.total` debe seguir siendo un numero de tests.

        Regresion concreta del 2026-10-02: dos snapshots de cobertura
        anidados por error dentro de `tests:` traian su propia clave
        `total: 85%`, que pisaba el recuento. Se renombraron a
        `total_coverage_subset_t1` y `total_coverage_suite_completa`;
        esto fija que la colision no vuelve.
        """
        doc = yaml.safe_load(STATE.read_text(encoding="utf-8"))
        total = doc["tests"]["total"]
        assert isinstance(total, int), (
            f"tests.total es {total!r} ({type(total).__name__}), no un "
            "entero: algo con clave `total` se ha colado dentro de `tests:`"
        )

    def test_shadowed_coverage_snapshots_are_still_readable(self) -> None:
        """Los datos que estaban ocultos siguen siendo legibles.

        Renombrar sin cambiar los valores es lo que hace este arreglo: el
        dato no se tira, se desoculta. Si alguien 'limpia' las claves
        renombradas en vez de conservarlas, los 7 datos vuelven a
        perderse y este test lo dice.
        """
        doc = yaml.safe_load(STATE.read_text(encoding="utf-8"))
        tests = doc["tests"]
        assert tests["total_coverage_subset_t1"] == "85%"
        assert tests["total_coverage_suite_completa"] == "85%"
        assert "refactor_v070_summary" in tests
        assert "refactor_v070_coverage_snapshot_narrativa" in tests
        assert "delta_wi12_detalle" in tests
        assert "delta_wi12" in tests

    @pytest.mark.parametrize("tag", ["v0.14.5", "v0.14.6", "v0.14.7"])
    def test_releases_with_two_notes_keep_both(self, tag: str) -> None:
        """Tres releases tenían dos claves `nota`; la segunda tapaba a la primera.

        Se conserva la nota canonica en `nota` y la previa en
        `nota_anterior`. Si desaparece cualquiera de las dos, se ha
        perdido historia de por que se agruparon esos bumps.
        """
        doc = yaml.safe_load(STATE.read_text(encoding="utf-8"))
        entry = next(r for r in doc["release"]["releases"] if r["tag"] == tag)
        assert "nota" in entry, f"{tag} perdio su nota canonica"
        assert "nota_anterior" in entry, f"{tag} perdio la nota anterior que la clave `nota` tapaba"
