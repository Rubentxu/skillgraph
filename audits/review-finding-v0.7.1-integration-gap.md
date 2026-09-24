# Hallazgo de revisión externa — v0.7.1, integración real de Plan B

**Origen**: revisión externa del release público `v0.7.1` (commit
anotado `8b63db6a8e4cc585e51cdf7da39379f25a60fbc5`).

**Status del release v0.7.1**: NO se retracta (es una mejora real y las
pruebas focales son válidas). Lo que NO se acreditó fue el cierre
operativo del runtime principal.

## Defecto detectado

`RunController._execute_one` en la revisión etiquetada sigue invocando
las APIs **no atómicas** de `Storage`:

| Momento | Llamada Storage | Emisión posterior |
|---|---|---|
| Inicio | `Storage.start_node_execution(...)` | `EventLog.append(NodeStarted)` |
| Finalización | `Storage.complete_node_execution(...)` | `EventLog.append(NodeCompleted)` + `EventLog.append(EvidenceProduced)` |
| Fallo | `Storage.mark_node_failed(...)` | `EventLog.append(NodeFailed)` |

Las APIs nuevas `*_atomically` están implementadas en `Storage` y probadas
aisladamente por `tests/test_h9_plan_b_atomicity.py` (T7-T11), pero
**ningún consumidor real las invoca** en la versión etiquetada.

### Consecuencia práctica

Si el proceso falla entre el INSERT/UPDATE de `node_executions` y el
INSERT del evento, el recorrido real puede dejar ambos registros
desincronizados. Las pruebas T7-T11 no detectan esa condición porque
ejercitan directamente las APIs nuevas: no construyen un RunController
ni inyectan fallos en su recorrido.

## Distinción importante (no es la LIMITACIÓN-7)

Este defecto es **diferente** de LIMITACIÓN-7 (el `Storage._tx()` con
`with self._conn:` que no rollbackea). Conectar RunController a las APIs
atómicas y revisar `Storage._tx()` son dos trabajos relacionados pero
distintos:

- **Este hallazgo**: integrar las APIs nuevas en el recorrido existente.
- **LIMITACIÓN-7**: refactor de Storage para que TODA escritura use
  BEGIN/COMMIT/ROLLBACK explícitos. Es un trabajo de fondo mucho más
  invasivo.

Cerrar este hallazgo no resuelve LIMITACIÓN-7.

## Lo que el release v0.7.1 sí cierra (honestamente)

- **Capacidad implementada**: 3 APIs atómicas nuevas en `Storage` con
  BEGIN/COMMIT/ROLLBACK explícitos. Probadas unitariamente.
- **LIMITACIÓN-1 grietas B/C/D: PARCIALMENTE**. Las APIs están listas
  pero el runtime no las invoca. Por tanto: "0% cerrado en runtime"
  en el sentido operativo.

## Lo que sigue abierto (más allá de este hallazgo)

- **LIMITACIÓN-7** (Storage._tx no rollbackea): requiere refactor
  amplio. No resolverá este hallazgo.
- **Plan A** (cobertura), **Plan C** (concurrencia/backup/adaptador real):
  siguen diferidos.

## Acción correctiva prevista: v0.7.2

`v0.7.2` será el release correctivo. Su consigna:

> Conectar `RunController` a las APIs `*_atomically` y demostrar
> garantía transaccional en el recorrido real, con pruebas de
> integración (no solo unitarias).

Reglas (per la consigna del auditor):

1. Sustituir en `RunController` los pares modificar-estado → emitir-evento
   por las APIs `*_atomically` existentes.

2. Conservar identificadores de eventos, outcomes, handoffs y
   transiciones actuales.

3. Añadir pruebas que ejecuten `RunController` y al menos un recorrido
   desde la CLI con fallos inducidos entre la mutación de estado y el
   registro del evento.

4. Comprobar en una base reabierta que cada operación incluida
   confirma conjuntamente estado y eventos, o revierte ambos.

5. Documentar por separado las operaciones de `workflow_runs` y la
   LIMITACIÓN-7.

**Gate**: Plan B no se cierra hasta que el consumidor real use las
APIs nuevas y las pruebas de interrupción demuestren la garantía en
ese recorrido.

## Estado de la rama `h9-plan-b-atomicity`

Cerrada y mergeada en `main` con tag `v0.7.1` anotado en `8b63db6`.
La rama local `h9-plan-b-atomicity` fue borrada tras el merge.

## Estado del release v0.7.1

- Tag `v0.7.1` sigue anotando `8b63db6`. No se mueve.
- El bundle reproducible y las evidencias siguen siendo válidos como
  reproducciones del código del release.
- Este hallazgo se incorpora al release notes sin retractar el tag.

## Próximo paso

Iniciar `v0.7.2` con la consigna correctiva. Sin modificar
retroactivamente `v0.7.1` ni sus evidences.
