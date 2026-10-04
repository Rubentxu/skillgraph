# B8 — Recibo de implementación

**Ciclo**: `p-b7740b96d79ec013/b8`
**Entrega**: `4d72177`
**Base**: `7363f0f`

## Qué se entregó

| Fichero | Qué es |
|---|---|
| `src/skillgraph/packaging/manifest.py` | el contrato: manifiesto, `requires`, compatibilidad |
| `src/skillgraph/packaging/__init__.py` | la superficie pública |
| `tests/test_b8_package_contract.py` | 66 tests |
| `scripts/measure_b8_package_contract.py` | el medidor del gate |
| `scripts/mutate_b8_package_contract.py` | la sonda de los guards |

## Verificación en el momento de la entrega

- Suite completa en el hook del commit: **3158 passed, 3 skipped, 0 failed**
- Tests de B8: **66 passed**
- Cobertura del paquete nuevo: **100 %** (suelo de `AGENTS.md` §6.3: 90 %)
- Medidor del gate: `rc=0`, 0 de 5 huecos
- Contra-saltos: **5/5 con 5 conjuntos distintos de tests**
- `tests.total`: 3161, con el desglose medido

## Defectos reales corregidos

1. **El parser rechazaba el formato del propio gate.** `">=0.30,<1"` mezcla
   `>=0.30` —dos componentes— y `<1` —uno solo—. La regex exigía `X.Y` o
   SemVer completo, así que **ningún pack encajaba** contra el formato que el
   gate define. Lo cazaron seis tests a la vez.
2. **La capability larga se rompía en silencio.** `{type_name, version}`
   producía `type_name="a.b.v2@v2"` con la versión pegada y la del puerto en
   el campo `version`. No se puede comparar con un `CapabilitySpec`
   instalado, y el síntoma es «falta la capability», que es creíble.
3. **`es_al_menos` reventaba con `KeyError`** ante un nivel inexistente: una
   situación de despliegue, no un error de programación, y WI-109 cerró justo
   ese camino.
4. **Un `pytest.skip` propio** que escondía un fallo del contrato — lo que
   `AGENTS.md` §6.2 prohíbe. `test_wi108_zero_skips.py` lo cazó.
5. **Un test que no podía fallar**: mutar `requires.skillgraph` en el dict
   de origen no puede cambiar un `frozen` dataclass, porque los strings son
   inmutables. Se quitó esa aserción y la sonda se movió a `metadatos`.

## Defectos de los instrumentos

1. **El medidor rechazaba la forma correcta.** `ast.literal_eval` no lee
   `frozenset(get_args(PackKind))`, y esa es la forma que se PREFIERE. Le
   decía al código correcto que su conjunto no existía — un guard que
   obliga a escribir peor para poder ser medido.
2. **El índice de alias no veía `X = Literal[...]`** sin anotación, que es un
   `Assign` a secas. `get_args(PackKind)` no resolvía a nada.
3. **El harness decía «restaurado» sin estarlo.** Al restaurar, el `mtime`
   puede no avanzar y Python sigue ejecutando el `.pyc` de la versión
   mutada. Se vio porque M5 cazaba los tests de M4. Ahora borra
   `__pycache__` y **vuelve a pasar la suite al final**.

## Requisitos que aparecieron al ejecutar

R7 — el parser tiene que entender el formato del gate.
R8 — la versión no puede quedar pegada al nombre.
