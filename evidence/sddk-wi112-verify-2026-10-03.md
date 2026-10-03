# WI-112 — el reloj tenía diez puntos de definición y declaraba uno

- **Fecha**: 2026-10-03
- **Ciclo SDDK**: `p-b7740b96d79ec013/wi112-clock-single-source` (path `A-full`)
- **Release**: `v0.22.3` (PATCH)
- **Serie**: «¿qué declara el repo que nada comprueba?», decimocuarta vía
- **Commit**: `166f0b1`

---

## 1. La declaración

`AGENTS.md §1.3`, viñeta segunda:

> - El reloj se inyecta (default factory con `datetime.now(UTC)`)
>   y se puede mockear.

Y `runtime/engine.py`, en el helper que el repo declara autoritativo:

> **Unico punto de definicion**: antes existian 3 copias (...)

Las dos son verificables, y ninguna se sostenía.

## 2. La medición

Rastreo por **AST** sobre `src/skillgraph`, no por cadena. Medido
antes de tocar nada: **10** llamadas a `datetime.now`, en **tres**
formatos.

| formato | nº | ejemplo |
|---|---|---|
| `isoformat()` | 5 | `2026-10-03T09:00:00.123456+00:00` |
| `replace(microsecond=0)` | 2 | `2026-10-03T09:00:00+00:00` |
| `strftime(...)` | 3 | `2026-10-03T09:00:00Z` |

La consecuencia no es estética: dos instantes del mismo segundo
podían serializarse a dos strings que no comparaban entre sí.

Y `RuntimeEvent` traía su propia copia del problema:
`field(default_factory=lambda: datetime.now(UTC).isoformat())`. Una
lambda que captura el reloj real **no tiene por dónde inyectarle
otro**, así que «se puede mockear» era cierto solo con monkeypatch del
módulo.

## 3. Lo que se descartó, y por qué

Se escribe para que el camino descartado también sea evidencia.

**El reloj no rompe el orden del journal.** Mi primer comentario en
el script afirmaba que los dos formatos «no ordenan entre sí». Es
cierto como afirmación sobre *strings*, pero `event_store.py:132`
ordena `ORDER BY sequence ASC`, no por `timestamp`. Ese defecto no
existe aquí.

**Un `RuntimeEvent` sin timestamp explícito no es no-determinista de
un modo malo.** Un journal debe llevar la hora real. Lo que estaba
mal era el *formato*, no que se leyera el reloj.

## 4. El arreglo

- `now_iso(clock: Clock | None = None)` es la **única** lectura del
  reloj del núcleo, y acepta un reloj inyectado. Se pasa explícito y
  no por un global porque `AGENTS.md §1.4` prohíbe el estado global
  mutable.
- `RuntimeEvent.timestamp` pasa a `default_factory=now_iso`, con lo
  que hereda el formato único.
- `event_store`, `catalog`, `expansion`, `promotion` y `backups`
  delegan en el helper.

### El default factory se queda

`AGENTS.md §1.3` **pide** un default factory. Hacer `timestamp`
obligatorio iba contra la regla, y rompía **37 tests** sin añadir
capacidad. La inyección real es `now_iso(clock=...)` y
`EventBuilder._emit(timestamp=...)`. Un default factory que llama al
reloj es cómodo de usar y opaco de fijar: son dos propiedades
distintas, y la regla solo declara la primera.

## 5. Lo que NO se unificó

`governance/backups.py`, `improvement.py` y `receipts.py` siguen
usando `strftime`, y **deben**: producen `2026-10-03T09:00:00Z`, que
es un **nombre de fichero**, no un instante de evento. Unificarlos
cambiaría receipts y nombres de backup ya emitidos.

La lista está declarada **en el guard**, no en el código de
producción, porque es una excepción y no una regla. Y el guard la
vigila **en las dos direcciones**: que los módulos existan, y que
ningún otro use `strftime`.

## 6. El guard mide la propiedad, no el nombre

La propiedad es «no hay una segunda lectura del reloj», no «existe
una función llamada `now_iso`». Por eso el rastreo es por AST: el
docstring del propio `now_iso` menciona `datetime.now`, y un rastreo
por cadena contaría la prosa.

Hay dos tests que rompen si el rastreo pasa a buscar texto: uno con
un docstring inventado y otro con el caso real del repo — que tiene
varios docstrings así. Sin el segundo, el primero sería un
contraejemplo de laboratorio.

## 7. Un guard que tenía razón y cuyo veredicto había que aceptar

Al correr la suite con `TMPDIR` dentro del repo para esquivar un
`OSError: [Errno 122] Disk quota exceeded`, fallaron dos tests de
**WI-89**:

```
tests.test_audit_debt_smoke._run_audit() escribio DENTRO del
repositorio: .pipelinek/tmp/sg-audit-qjzlvdj0/architecture-debt-...md
```

Tenían razón: el sandbox de pruebas debe estar **fuera** del repo. Mi
`TMPDIR` estaba dentro. Movido a `/var/home/rubentxu/.sg-tmp` — fuera,
con espacio de sobra — y los 7 tests de WI-89 volvieron a verde sin
tocar el guard.

Es el mismo patrón de WI-108: **un guard que solo sabe pasar no
está probado**, y un guard que mide el entorno puede ser el que te
dice que has roto el contrato.

El `Disk quota exceeded` era de `/tmp`: 38 GB de un tmpfs con cuota
de 38,5 GB, ocupado en 26 GB por trabajo ajeno. No es del bloque.

## 8. Certificación

**Run canónico**: `d760dba5-29a7-41ca-9628-3c29010b9df1`. Leído del
journal **después** de terminar, por `run_id` **y** `occurred_at`.

| # | etapa | outcome |
|---|---|---|
| 0 | `discover-repo` | success |
| 1 | `sync-deps` | success |
| 2 | `unit-tests` | success |
| 3 | `coverage-floors` | success |
| 4 | `package-build` | success |
| 5 | `ci-parity` | success |
| 6 | `lint` | success |
| 7 | `evidence` | success |

`RunFinished` → `outcome: success`, `diagnostics: []`. **8/8 etapas en
`success`**.

**Suite dentro del run**: `pytest: 2812 passed in 576.33s`, **0
skipped**. 2795 + 17 = 2812: la aritmética y el run coinciden.

| | |
|---|---|
| HEAD | `c6575ce` post-release |
| versión activa | `0.22.3.dev0` |
| último tag | `v0.22.3` sobre `5812c7b` |
| SHA-256 `.pipeline.kts` | `7541ced5…2dd42`, **sin drift** |
| árbol | limpio |

**Criterios del PRE-FLIGHT:**

| criterio | verificado |
|---|---|
| C1 una sola lectura del reloj para instantes | 10 → 1, por AST |
| C2 un solo formato de instante | sin microsegundos, `+00:00` |
| C3 el default del evento hereda el formato | `RuntimeEvent()` sin `timestamp` |
| C4 el reloj es inyectable | `now_iso(clock=...)`, sin monkeypatch |
| C5 los `strftime` de nombre de fichero siguen igual | guard en las dos direcciones |
| C6 suite verde | 2812 passed, 0 skipped, 8/8 etapas |

## 9. Resultado

| | |
|---|---|
| lecturas de reloj para instantes | **10 → 1** |
| tests nuevos | 14 (`tests/test_wi112_clock_single_source.py`) |
| mutaciones | **5/5 cazadas**, 0 no detectadas, 0 sin sonda, 0 inválidas |
| tests afectados | 498 verdes |
| mypy | 143 antes, 143 después (preexistentes) |
| SemVer | PATCH → `v0.22.3` |
