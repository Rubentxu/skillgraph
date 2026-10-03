# Blocker B5 — el ciclo existe pero el id corto responde "no encontrado"

Fecha: 2026-10-03
Severidad: **alta** (produce diagnóstico falso: "el estado se perdió")
Estado: **abierto, con workaround documentado**

## Síntoma

`sddk cycle <cmd> --cycle b5` responde `cycle not found: b5`, mientras
que el mismo comando con el id **cualificado** responde con el estado real:

```bash
$ sddk cycle status --cycle b5
error[STORAGE_NOT_FOUND]: cycle not found: b5

$ sddk cycle status --cycle p-b7740b96d79ec013/b5
{
  "cycle_id": "p-b7740b96d79ec013/b5",
  "status": "OPEN",
  "phase": "verify",
  "artifacts": 5
}
```

Afecta a `status`, `lock acquire`, `lock status` y `rebuild`. No afecta a
`cycle start`, que acepta el id corto y lo cualifica solo.

## Por qué importa: el diagnóstico equivocado al que lleva

El error `cycle not found` dice exactamente lo contrario de la verdad, y esa
es la parte grave. Medido en esta sesión:

```
$ ls -la .../p-b7740b96d79ec013/ledger.sqlite
-rw-r--r-- 1 rubentxu rubentxu 0 oct  3 22:33 ledger.sqlite

$ python -c "sqlite3 ... → select name from sqlite_master"
tablas: NINGUNA (fichero vacio de verdad)

$ sddk ledger events --limit 700    # 630 eventos, el mas reciente de 2026-10-02
```

La lectura que invita a hacer es «el ledger se vació y se perdió el
trabajo de B4 y B5». **Es falsa**, y por el camino se intentó
`cycle rebuild` como reparación, que no puede funcionar: exige un
lease, y el lease se pide sobre un ciclo que el mismo tooling no encuentra.

El `ledger.sqlite` de 0 bytes es **real pero no es el store de eventos**:
los eventos viven en otro sitio, y `sddk ledger export` los devuelve
intactos. La comprobación que faltaba era esa, no el tamaño del fichero.

## Workaround

Usar siempre el id cualificado `<project_id>/<cycle>`:

```bash
sddk cycle status --cycle p-b7740b96d79ec013/b5
```

Esto **también** explica el ciclo `b4-cierre` que quedó abierto por error:
se creó porque `b4` no se encontraba con el id corto, cuando `b4` sí
existía. Es el mismo bug, y por eso la entrada de este blocker no se
considera un descuido de la sesión anterior sino un fallo del tooling.

## Segundo defecto, en el mismo camino

`sddk cycle start` acepta el id corto, escribe el evento con
`"sequence": 1` —que ya existe 130 veces en el mismo ledger— y devuelve
un recibo que parece bueno:

```bash
$ sddk cycle start --root . --scope . --name b5-cierre
{"cycle_id":"p-b7740b96d79ec013/b5-cierre","status":"OPEN",
 "event_id":"evt-89206b18-...","event_hash":"sha256:a6c80656..."}

$ sddk cycle lock acquire --cycle b5-cierre --owner mavis-b5
error[STORAGE_NOT_FOUND]: cycle not found: b5-cierre
```

El evento **sí** persiste (el export pasa de 630 a 631 líneas y lo
contiene), pero la colisión de `sequence` rompe el store: al intentar
supersederlo aparece

```
admission event recording failed (fail-soft): storage error:
  event_store:duplicate_event_id:authority-approval-system-cycle_supersede-require_approval
```

`cycle start` reporta `OPEN` sobre una escritura que deja el store
inconsistente. Un comando que devuelve éxito y un id de evento real
debería poder ser seguido por un `status` sobre ese mismo id.

## Impacto en B5

Ninguno sobre el trabajo: el código, los tests, la release y la
certificación existen y están commiteados. El impacto es de **trazabilidad
del ciclo**, y está resuelto usando el id cualificado. Los cuatro gates de
`verify` quedan registrados con evidencia real:

| gate | outcome | evidencia |
|---|---|---|
| `tests-pass` | passed | 3027 passed, 3 skipped, digest `sha256:17b98e74…` |
| `policy-compliant` | passed | mutaciones 8/8, digest `sha256:6a6b1f58…` |
| `debt-severity-assigned` | **failed** | detección de deuda no implementada en esta build |
| `debt-priority-assigned` | **failed** | ídem |

`b5` queda en `verify` con `requires_met: False`. No pasa a `Release`, y no
va a pasar mientras los gates de deuda no sean evaluables —ver
`blocker-B4-debt-report-context.md`, que sigue vigente y cuya redacción
la propia herramienta confirma.

## Tercera manifestación, medida en B6: el artefacto se guarda y el ciclo no lo ve

El 2026-10-04, al caminar el ciclo `b6`, apareció la misma clase de fallo
en otro sitio: **una escritura que la herramienta reporta como exitosa y
que no llega al destino que la hace útil**.

```bash
$ sddk artifact store --file evidence/sddk-b6-exploration-2026-10-03.md \
      --kind exploration-report --cycle p-b7740b96d79ec013/b6 --producer mavis-b6
{"artifact_id": "art-98ecdb80d9dd-40c4a166",
 "sha256": "sha256:98ecdb80d9dd56e2918fa04abc78da50e4b895344d50873063cefdaca9e46ecb",
 "size": 3835}

$ sddk cycle status --cycle p-b7740b96d79ec013/b6
{"status": "OPEN", "phase": "explore", "artifacts": 0}      # <-- 0

$ sddk cycle transition --transition phase.explore.complete ...
error[ENGINE_MISSING_ARTIFACT]: missing artifact "exploration-report"
```

El artefacto **sí** existe y se lee byte a byte idéntico
(`sddk artifact get --digest ... --output` y `diff` no encuentran
diferencia). Lo que no se escribe es la **vinculación** artefacto → ciclo.

Las tres manifestaciones del mismo defecto, entonces:

| # | qué dice el comando | qué es verdad |
|---|---|---|
| 1 | `cycle status --cycle b5` → `cycle not found` | el ciclo existe; sólo falla el id corto |
| 2 | `cycle start` → `OPEN` con `event_id` | el evento va con `sequence 1`, que colisiona con 130 |
| 3 | `artifact store` → `artifact_id` y `sha256` | el ciclo sigue con `artifacts: 0` |

**Por qué importa más de lo que parece.** Las tres devuelven un
identificador y un digest convincentes. Un agente que se fíe de la salida
daria el bloque por registrado. Aquí no se hizo: el ciclo `b6` queda en
`explore` con la evidencia commiteada **en el repositorio**, que es donde
se puede leer y verificar, y no en el store del framework, que es donde no
se puede.

**Workaround.** La evidencia de un bloque vive en `evidence/` y se
commitea. El ciclo registra lo que sí puede registrar —los gates, con su
`argv`, `exit_code` y `output_digest` reales— y lo que no puede, queda
dicho en el informe de verificación en vez de darse por bueno.
