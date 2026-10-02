# ADR-0024 — `RunController` por dominios: tres mixin, un módulo cada uno

Estado: aceptado (sesión 2026-10-02, ciclo `wi-67-runcontroller-mixins`).
Completa ADR-0019 fase 2, sobre el corte de fases de ADR-0023.

## Contexto

Tras ADR-0023, `runcontroller.py` pesaba **1421 LoC** con una única
clase `RunController` de 37 métodos y 1252 LoC de cuerpo. El audit lo
reportaba como god module.

La medición por AST no dio un bloque sino **seis clusters disjuntos**
por responsabilidad, sin solapamiento:

| Cluster | Métodos | LoC |
|---|---:|---:|
| ejecución de nodo | 12 | 405 |
| ciclo de vida del run | 6 | 219 |
| consulta/observabilidad | 8 | 214 |
| transiciones/locks | 5 | 137 |
| budget | 2 | 107 |
| handoff/knowledge | 2 | 101 |
| `__init__` | 1 | 69 |

## Decisión

Mover **tres** clusters a un mixin cada uno, en **módulos separados**:

| Módulo | Mixin | Métodos | LoC |
|---|---|---:|---:|
| `node_execution_delegations.py` | `NodeExecutionDelegations` | 12 | 487 |
| `run_observability_delegations.py` | `RunObservabilityDelegations` | 8 | 255 |
| `run_budget_delegations.py` | `RunBudgetDelegations` | 2 | 138 |

`runcontroller.py` queda en **665 LoC** con 14 métodos: ciclo de vida,
locks/transiciones, handoff/knowledge y `__init__`. God modules: 3 → 2.

### Un módulo por dominio, no uno con tres mixin

La primera versión generó un `runcontroller_delegations.py` único que
salía en **845 LoC**: el problema no se movía, se reubicaba. Un módulo
por dominio deja cada uno holgado (487/255/138) y hace que la razón de
cambio de cada uno sea una sola.

### Qué se queda en `RunController`

Ciclo de vida del run, locks/transiciones de estado y compilación de
handoff/knowledge. Son las partes que orquestan las otras, y movirlas
sería partir el flujo en vez de la estructura.

`MAX_NODE_ATTEMPTS`, `_NodeGuard` y `_NodeExecution` viajan con su
cluster (el orquestador los usa, e importarlos desde `runcontroller`
sería un ciclo), pero `runcontroller` los **re-importa** para no cambiar
su superficie.

## Consecuencias

- Sin cambio de comportamiento: 2019 tests, incluidos los 483 de
  runtime/H9/H10.
- `ports/__init__.py` (927) y `storage_delegations.py` (915) quedan
  como únicos god modules. El segundo son cinco clases cohesivas con
  métodos de ≤27 LoC: estalla por tamaño de fichero, no por
  concentración de responsabilidad. Cruzarlo exige decidir si el
  criterio del audit debe ser "clase" y no "fichero".

### El shim de re-exports, y por qué esta vez se fijó antes

`ruff --fix` borró `BudgetViolationKind` por F401, y
`test_wi59_run_types_extraction` cayó. Es la **tercera** vez que este
proyecto sufre ese mismo modo de fallo (WI-65 lo rompió con 61
tests, WI-66 con 133). La diferencia esta vez es que el daño se
detectó en la red dirigida, no al final.

Dos aprendizajes que la red deja escritos:

1. Un grep de `from ... import` **no basta** para saber qué se re-exporta:
   hay accesos por atributo (`runcontroller.BudgetViolationKind`). Hay
   que buscar ambos patrones. La red ahora fija la lista de nombres
   consumidos desde fuera, uno a uno.
2. `vars(cls)` solo ve el namespace propio. Para afirmar sobre la
   superficie pública de una clase con herencia hay que usar
   `inspect.getmembers`, o el test declara rota una clase que sí cumple
   el contrato. Es el segundo test en caer por esto (el primero fue
   `test_persistence_ports.py`).

## Red de contrato

`tests/test_wi67_runcontroller_mixins.py` (34 tests) fija:

1. Los 22 métodos se heredan, no se redefinen, y
   `RunController.<m> is <Mixin>.<m>` (identidad de función).
2. Clusters disjuntos: 22 métodos exactos, ninguno en dos mixin.
3. Ningún módulo de mixin importa `runcontroller` (sería un ciclo).
4. Superficie pública intacta, medida sobre el conjunto **accesible**.
5. Los 14 re-exports siguen importables y declarados en `__all__`.
6. `runcontroller.py` por debajo de 800 LoC.
7. Cada método opera sobre `self` y no declara `global` (nodo AST, no
   subcadena: "budget global del Run" está en los comentarios).

## Alternativas rechazadas

- **Un único módulo de delegaciones**: 845 LoC, solo reubica el
  problema.
- **Mover también ciclo de vida y locks**: partirían el flujo de
  reconciliación, que es lo que coordina los clusters ya movidos.
- **`__getattr__` dinámico**: rompe el tipado estático (§4.1).
