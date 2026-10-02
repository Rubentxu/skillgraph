# Changelog

All notable changes to SkillGraph are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
derived from the commit history via Conventional Commits.

Tipos:
- `feat` → MINOR (nueva capacidad observable).
- `fix` → PATCH (corrección).
- `feat!` / `fix!` / footer `BREAKING CHANGE` → MAJOR.
- `refactor`, `test`, `docs`, `spec`, `chore`, `style` → sin bump de versión.

## [0.16.11] - 2026-10-02 — WI-72..WI-81: investigación retrospectiva, falsos éxitos y alias muertos

**Resumen**: publica el bloque de 9 commits acumulado desde `2ee6d77` (WI-72
a WI-81): una investigación retrospectiva del ciclo de desarrollo anterior,
con la consigna de buscar **falsos éxitos** —operaciones que devuelven OK
sin cumplir su objetivo—. El número sale de la regla del propio CHANGELOG
aplicada al historial: **0 `feat`, 1 `fix`, 1 `refactor`, 6 `test`, 1
`docs`** → **PATCH**. No hay capacidad observable nueva ni cambio de API
pública. **2376 passed** (2368 antes del bloque), ruff y format limpios, CI
canónica con `Pipeline finished with SUCCESS` (run `6d5e68a5`).

La mayor parte del bloque son redes de contrato, no cambios de
comportamiento: el código ya cumplía lo que se ahora verifica. Cuatro
falsos éxitos confirmados y uno refutado con instrumentación.

### Fixed

- `fix(coverage)` `b3b2ef7`: **`pytest --cov` era ciego al CLI entero**.
  Mide solo el proceso principal, y la suite ejercita la frontera CLI por
  subproceso. El CLI marcaba **65,86 %** contra el contrato de AGENTS §6.3
  (≥70 %) — un incumplimiento aparente que era **ceguera del
  instrumento, no deuda de tests**. `scripts/coverage.sh` arregla las tres
  piezas (hook `.pth` que llama a `coverage.process_startup()`,
  `parallel = true` y `data_file` absoluto) y el mismo código mide **94 %**;
  `cmd_expansion_apply` pasa de 0 % a cobertura real. Sin tocar `.pipeline.kts`
  porque la instrumentación duplica el tiempo de suite.
- `test(platform)` `073d52d` + `refactor(platform)` `90d2e46`: **siete alias
  de WI-56 (corte 3) en `row_mappers.py` sin callers**, que `MAPPER_NAMES` y
  `storage.__all__` seguían contando como mappers. Sus docstrings decían
  «el corte 5 reubicará los callers»; el corte 5 ocurrió (ADR-0020) y los
  alias se quedaron. Inercia medida **en runtime**: los símbolos que usa
  `knowledge_repository` son aliases *locales* suyos
  (`knowledge_repository.py:696-702`) que apuntan a `knowledge_mappers`, no
  a estos — un barrido textual habría dado un falso positivo. `MAPPER_NAMES`
  pasa de 12 a 5; segunda tanda de ADR-0014, cuyo addendum queda en disco
  porque `external/` está en `.gitignore`.
- `test(runtime)` `2a1a737`: el guard de `_fail_node_with` leía que la última
  línea fuese `return False` con `getsource`, con lo que un `return None`
  temprano pasaba. Ahora invoca la función.

### Regresiones evitadas por la red (contexto)

- `test(cli)` `d69879f`: la rama `except FileNotFoundError` de `main`
  (`runner.py:250-254`) **no la ejercitaba nadie**. Con su
  `return EXIT_PROJECT_NOT_FOUND` cambiado por `return EXIT_OK`, los 2260
  tests de la suite se quedaban verdes. El oráculo conductual no la
  alcanzaba porque `runs budget` resuelve el proyecto antes. La cobertura
  de líneas no lo habría dicho: la línea se ejecuta, lo que faltaba era la
  **aserción** sobre su valor.
- `test(cli)` `2b68bfd`: un `expansion_rejections/*.json` ilegible degrada a
  `stage=PROPOSED` con exit 0 y sin aviso, y desaparece del filtro
  `--stage REJECTED`. **No** es un falso éxito de escritura —`apply` es
  idempotente por re-validación— sino de visualización. Fijado con test; la
  corrección es decisión de producto porque cambia la salida de un comando
  publicado.
- `test(runtime)` `3ce7b2e`: el límite `max_events` del Run, un control de
  gobernanza cuyo evento `BudgetExceeded(kind="events")` es lo que el
  operador lee para saber **por qué** se abortó un run, no tenía un solo
  test. `run_budget_delegations.py` de 83 % a 100 %.
- `test(platform)` `40d78ae`: la serialización legacy de 4 de 9 DTO
  (`StoredClaim`, `StoredEvidence`, `StoredPromotion`, `StoredBudget`) sin
  test. `dto.py` de 89 % a 97 %.

### Conocimiento negativo (lo que se buscó y NO se encontró)

Registrado porque absence de evidencia no es evidencia de ausencia, y
porque confirmar que algo está bien es un resultado:

- **No hay handler de excepción vacío ni `pass`** en `src/`: de 66
  handlers, 59 tienen cuerpo efectivo y 7 son `continue` de tolerancia a
  dato corrupto, todos documentados. Los 4 `except Exception` anchos están
  justificados en el código y los 3 `except BaseException` relanzan con
  `raise`.
- **Ningún handler de `_DISPATCH` (31) puede devolver `None`**, o sea que
  `sys.exit(main())` no puede dar exit 0 por silencio. Hipótesis refutada
  con un escáner validado por mutación en ambas direcciones.
- **La pérdida de la causa de una promoción FAILED** (`promotion.py:116`)
  es deuda declarada en el propio código y fijada por test, no un hallazgo.
- **`_load_registry` con registro incompleto es fail-closed**: el registry
  es un allowlist de existencia (I3/I4), no un detector de colisiones.
- **El patrón `getsource`/AST con `assert` no es sistémico**: de 40 tests
  que lo combinan, ~37 son contratos estructurales legítimos.
- **No hay deuda registrada para este proyecto**: `sddk debt incs`
  devuelve 50 INCs que pertenecen a `sddk-framework/` y a otro proyecto
  (`p-733fb505b5a6bd2d`); el vault de `p-b7740b96d79ec013` tiene 0 entradas.
- **`sddk lint` falla con 4 errores que son opt-ins no adoptados**
  (`schemas/`, `docs/generated/`, `manifest.toml` nunca existieron en el
  historial de git), no contratos violados ni drift.

### Contradicciones reportadas, no corregidas

Decisiones de producto, con el comportamiento real fijado por test para
que no se resuelvan en silencio:

- `StoredBudget.to_dict` promete en su docstring "preservando todas las
  columnas" y devuelve 3 de 6: omite `tenant_id`, `project_id`, `run_id`.
  Ningún consumidor determina cuál de las dos cosas es correcta.
- `argparse` sale con código **2** mientras el `EXIT_USAGE` canónico es
  **1** (`support.py:47`): un operador que clasifique por `EXIT_USAGE` no ve
  los errores de invocación.
- Un rechazo ilegible se presenta como `PROPOSED` (§ Regresiones).

## [0.16.10] - 2026-10-02 — WI-65..WI-71: cierre de H-01 y god modules 3 → 0

**Resumen**: publica el bloque de 57 commits acumulado desde `e680b72`. El
número sale de la regla del propio CHANGELOG aplicada al historial: **0
`feat`, 6 `fix`, 13 `refactor`, 3 `test`, 23 `docs`, 12 `chore`** → **PATCH**.
Se propuso un MINOR y se descartó: el bloque no añade ninguna capacidad
observable y la API pública se conserva idéntica. Contiene tres defectos
reales de gobernanza de CI, el cierre de la god class `Storage` (H-01), tres
cortes estranguladores que llevan god modules 3 → 0, y siete redes de
contrato nuevas. **2181 passed** (2154 antes del bloque), ruff y format
limpios, CI canónica con `Pipeline finished with SUCCESS`.

### Fixed

- `fix(ci)` `3665262`: **SUCCESS cacheado**. El comando canónico sin
  `--rerun` reutilizaba el veredicto por `cacheKey` de compilación del
  script: 72 ms, cinco stages "success", cero `StepStarted`. Un run que no
  ejecutaba nada se declaraba verde. `--rerun` pasa a ser obligatorio y
  AGENTS.md gana un criterio nuevo (el journal debe contener `StepStarted`
  y un `EchoOutputCaptured` con la línea de resumen de pytest). El criterio
  de "cero `StepFailed`" pasa a filtrar por `occurred_at` porque el
  `run_id` se reutiliza entre replays.
- `fix(ci)` `1bb545d` + `9dff66c`: la causa del "bake-off" entre versiones
  de `pipelinek` era la **ambigüedad de PATH entre asdf y mise**, no una
  versión defectuosa. Tres runs controlados (0.39.0 mise / 0.43.0 asdf /
  0.46.0 asdf) dieron los tres `1880 passed` + SUCCESS. Se fija 0.39.0 en
  `mise.toml` y se corrige la evidencia durable.
- `fix(ci)` `2cbc6c9`: el hook pre-commit decidía sobre el exit de `tail`, no
  el de `pytest`, y enmascaraba cualquier fallo de la suite (misma clase de
  trampa que `PIPESTATUS`).
- `fix(cli)` `c3444a7`: se restaura `@contextmanager` en
  `support._open_project_storage`.
- `fix(tests)` `ff5d246`, `229c542`: repara imports de símbolos movidos por
  los cortes estranguladores y actualiza cuatro contratos a la realidad
  post-estrangulamiento.

### Changed (sin cambio de comportamiento observable)

- `refactor(platform)` `9c104ac`, `2f5f7e4`, `405f49e` — **ADR-0022, cierra
  H-01**: la god class `Storage` (1807 LoC, 80 métodos) deja de figurar como
  god module. `storage.py` queda en **623 LoC**: 65 métodos de delegación a
  cinco mixin por componente, 12 mappers fila→DTO y el DDL a `row_mappers.py`
  y `schema.py`. Los atómicos H9/H10 (`_tx`, `_atomic`, `_migrate`) **no se
  mueven**: ADR-0016 exige que compartan `self._conn` sin duplicarlo.
- `refactor(runtime)` `e07413b` — **ADR-0023**: `_execute_one` 143 → 74 LoC
  en cuatro fases nombradas (`_node_guard`, `_compile_node_handoff`,
  `_invoke_node_adapter`, `_settle_node_outcome`).
- `refactor(runtime)` `57121ed` — **ADR-0024**, completa ADR-0019 fase 2:
  `RunController` 1421 → 665 LoC en tres mixin de dominio, en **módulos
  separados** (uno único habría salido en 845 LoC: reubicar el problema).
- `refactor(platform)` `c29a848`: `ports/__init__.py` 927 → `dto.py` (448) +
  `repositories.py` (442) + índice de 55. **God modules 3 → 0.**
- `refactor(knowledge)` `a16cd10` y `b6741bf`: `extract_file_signatures` 116
  → 55 LoC y `analyze_skill` 101 → 30 LoC (cc 11 → 1). Ambas candidatas
  elegidas por **medición AST, no por tamaño**: son las de mayor cc real
  entre las que quedaban; las lineales (`compile_handoff` cc 3,
  `compile_handoff_from_scopes` cc 1) se dejan intactas a proposito.

### Regresiones evitadas por la red (contexto)

Cuatro apariciones del mismo bug: `ruff --fix` borra por F401 los DTO
re-exportados en cuanto el facade deja de referenciarlos (61, 133 y 1 test
caídos en WI-65, WI-66 y WI-67). Guardas permanentes añadidas: lista
explícita de re-exports consumidos desde fuera y superficie pública
afirmada con `inspect.getmembers` (un `vars(cls)` no ve la herencia).
`ClassDef.lineno` no apunta al decorador, así que un corte de dataclasses
puede dejar los `@dataclass` atrás (41 tests, dos veces).

### Contexto

- Dos rarezas preexistentes de la importación de skills quedan **fijadas con
  test, no corregidas**: importar un fichero suelto lo nombra `"."` (porque
  `Path(f).relative_to(f)` es `"."`) y el mensaje de ruta inexistente usa la
  raíz ya resuelta. La primera cambia el payload que consumen UAT e informe:
  es decisión de producto.
- Nudo estructural del release governance: el admission gate exige que
  `__version__` puro coincida con una etiqueta en HEAD, así que el commit de
  release no puede pasar el gate antes de que exista la etiqueta. Se
  commitea con `HOOK_SKIP_TESTS=1` (ruff sigue corriendo) y la suite
  completa se ejecuta **después** de crear el tag, que es la condición en la
  que el gate debe pasar de verdad.

## [0.16.9] - 2026-10-01 — WI-49: rechazo de bool en enteros declarados

**Resumen**: ciclo SDDK `wi-49-bool-int-declared-coercions` (identidad `p-b7740b96d79ec013`). Cierra la clase de defecto que wi-46 dejó abierta (`isinstance(True, int)` es `True`, así que `int(True)` = 1 y un booleano declarado donde se espera un entero pasaba en silencio): tres superficies más donde la coerción ciega aceptaba `bool` — **plan** (`resourceRevision: true` → revisión 1 que nadie declaró), **backups** (manifest con `size_bytes: true` → tamaño 1 en restore) y **receipts** (`tests_run=True`/`tests_passed=True` aceptados por la dataclass pese al docstring que los "preservaba"; solo el cross-check `tests_passed > tests_run` mordía en una dirección, y el lector defensivo `_payload_to_receipt` coercaba antes de validar). 3 `fix`, 0 `feat`, 0 breaking → **PATCH**.

### Fixed

- `fix(plan)` `8ba12f3`: `_resource_revision` rechaza `bool` con `ParseError` que nombra el `source`; se preservan las coercions fijadas por test (`int('3')` acepta, `int(2.9)` trunca, ausencia → 0). Mismo patrón que `recipe._coerce_int`.
- `fix(backups)` `e95c5e9`: `BackupManifest.from_dict` usa `_declared_int` (rechazo explícito de `bool` con mensaje que nombra el campo) para `size_bytes`, `tenant_count` y `project_count`; elimina tres `# type: ignore[arg-type]`.
- `fix(receipts)` `6160ed5`: `ValidationReceipt._validate_counters` rechaza `bool` en `tests_run`/`tests_passed` (revierte la decisión de "preservar" la coerción, que el cross-check no cubría) y `_payload_to_receipt` valida antes de coercer, cumpliendo su propio contrato defensivo (fila corrupta → excepción → fila omitida).

### Contexto

- La sesión abrió con recuperación de contexto SDDK tras cambio de identidad (`p-74299cf88f51dab9` → `p-b7740b96d79ec013`, remote normalizado); detalle y cierre documental de los ciclos archivados en `evidence/sddk-context-recovery-2026-10-01.md`.
- Deuda registrada como P2 en el ledger anterior (`cmd_promotion_reconcile` cc=14, `_make_schema_validator` cc=13/anidamiento 5) verificada **caducada**: miden cc=7/1 y cc=3/2 tras los refactors posteriores.
- push pendiente de aprobación del operador.

## [0.16.8] - 2026-09-28 — WI-56: descomposición de Storage en repositorios reales (ADR-0016)

**Resumen**: ciclo SDDK `wi-56-storage-decomposition` (path A-lite). Patrón strangler en 5 cortes sobre el god-module `platform/storage.py` (2837 → 1807 LoC, −36%): cada cluster de SQL sale a un componente real con conexión compartida y su red de contrato escrita ANTES (RED honesto: solo fallaba la identidad del facade). **Cero ediciones en callers** (REQ-WI56-1/I1): los delegados del facade conservan firma explícita y forwarding idéntico (guard WI-45). Solo forma: 0 `feat`, 0 `fix`, 0 breaking → **PATCH**. Total: **1754/1754 tests no-UAT PASS**, ruff limpio.

### Changed

- **`SqliteRunRepository`** (`platform/run_repository.py`, corte 1 `ce0f291`): runs, node_executions y `list_events_for_run`. Net: `test_wi56_run_repository_contracts.py`.
- **`SqlitePolicyStore`** (`platform/policy_store.py`, corte 2 `7001479`): tenant_policies y run_budgets. Net: `test_wi56_policy_store_contracts.py`.
- **`SqliteKnowledgeRepository`** (`platform/knowledge_repository.py`, corte 3 `c125715`): 31 métodos del cluster knowledge (resources/relations, sources, entities, claims, evidences, findings, traces). Net: `test_wi56_knowledge_repository_contracts.py` (36 tests).
- **`SqliteEventStore`** (`platform/event_store.py`, corte 4 `6895725`): record/list/fetch/ensure_schema. `list_events_for_run` se puentea desde run_repository (ya migrado en corte 1) para satisfacer el Protocol completo. Net: `test_wi56_event_store_contracts.py` (15 tests).
- **`SqlitePromotionRepository`** (`platform/promotion_repository.py`, corte 5 `f439c74`): outbox H7 (register/get/list + 3 transiciones). Net: `test_wi56_promotion_repository_contracts.py` (13 tests).
- `Storage.run_repository()/policy_store()/knowledge_repository()/event_store()/promotion_repository()`: accessors cacheados que devuelven el componente REAL (antes: shim `-> self` por structural subtyping, WI-31).
- SQL vivo restante en `storage.py`: únicamente DDL (`_SCHEMA_SQL`), `_migrate` y los helpers atómicos `_insert_event_in_tx`/`_atomic_state_and_event`.

### Migration notes

- Los componentes comparten la conexión vía `Storage._conn` (decisión ADR-0016) y resuelven `_tx`/`_atomic` del dueño del schema en tiempo de llamada: el monkeypatching de H9/H10 sobre `storage._insert_event_in_tx` sigue funcionando (helpers atómicos permanecen en `Storage` por decisión del ciclo).
- `PromotionRepository` NO es `runtime_checkable`: la verificación estructural se hace por presencia de métodos.
- `Storage.list_promotions` sigue sin aceptar `limit`; el adapter del UoW recorta en memoria (contrato de puerto preservado).

### Tests

- +64 tests nuevos en las 5 redes de contrato WI-56 (dos bases idénticas sembradas, dump semántico sin columnas de reloj, UUIDs normalizados, spy de ruta atómica, guard de firmas explícitas).
- Suite no-UAT: 1720 (post-corte 3) → 1754 (post-corte 5).

### Audit debt

- `architecture-debt-2026-09-28.md` regenerado: 53 módulos / 19442 LoC; `storage.py` sale del top-3 de god modules; `knowledge_repository.py` (986 LoC) entra en la lista como componente extraído (no deuda nueva del ciclo).
- 1 finding `low` persistido en el debt-report del ciclo: flake preexistente de orden aleatorio en `test_wi56_knowledge_repository_contracts.py::list_resources` (no reproducible en 2 tiradas ni con orden fijo; seguimiento aparte).

### Fixed

- **`.jcode-scratch/` no estaba ignorado** (`8eda4ea`). Es el directorio de scratch del agente, donde se escriben los journals de `pipelinek` con journal fresco y los recibos en curso. Al no estar ignorado, cada verificación dejaba entradas no versionadas en `git status --porcelain`, y ese árbol limpio es requisito explícito del paso 1 del checklist de release de SDDK (`prompts/sddk/phases/release.md`). Es decir: el propio acto de verificar bloqueaba la release que estaba verificando. Verificado con `git check-ignore -v`.

### Housekeeping

- `STATE.yaml` declaraba 27 releases pero su lista terminaba en v0.16.0: siete releases ya publicadas (v0.16.1 a v0.16.7) no estaban registradas. Rehechas con SHA, fecha y nota reales, cada SHA verificado contra `git rev-list -1 <tag>` y `git rev-parse <tag>`. El bloque `release:` cabecera pasa de v0.16.0 a v0.16.8 con el SemVer derivado del historial.

## [0.16.7] - 2026-09-28 — complejidad de `detect_changes` y `reconcile_run`

**PATCH**. Sin `feat`, sin `fix` de contrato, sin breaking.

### Fixed

- Rechazo de `bool` en `Recipe.token_budget` y `Recipe.revision`: un booleano se colaba como número por el camino de la subclase de `int` en Python.

### Changed

- `GitSource.detect_changes`: cc 11 → 5.
- `_reconcile_run_locked`: cc 11 → 5.

Ambos refactors con red de contrato escrita antes del cambio, y la auditoría de deuda regenerada después.

## [0.16.6] - 2026-09-28 — cadenas de guardas de plan y recibo

**PATCH**.

### Changed

- Las dos cadenas de guardas restantes (`_make_schema_validator` y la validación de recibo) bajan de complejidad ciclomática, cada una con su test de contrato fijado antes del refactor.
- Fix del límite `max_visits`.
- Receipts de CI publicados por cada refactor, con el journal de `pipelinek` que demuestra que los tests se ejecutaron.

## [0.16.5] - 2026-09-28 — cierre de los dos hotspots reales de la auditoría

**PATCH**. 1455 tests PASS.

### Changed

- `cmd_promotion_reconcile` (CLI): cc 14 → 7, con `_select_promotion_failpoint`, `_abort_with_failpoint`, `_apply_pending_promotions` y `_reconcile_summaries` extraídas.
- `_make_schema_validator` (dominio): cc 13 → 3, anidamiento 5 → 0. Las reglas pasan a funciones de módulo con contexto explícito y el despacho a `match`/`case`, que es lo que corresponde a un dominio cerrado (regla 2.1 de `AGENTS.md`).

### Added

- Failpoint `after_apply_first`, que estaba **documentado pero no existía**. No es cosmético: simula la caída en el punto más peligroso de la promoción (la claim ya está en el destino pero el outbox aún no está `PUBLISHED`), y con él hay un test de subprocess que prueba el estado de split real y que la reconciliación lo reanuda de forma idempotente.

### Fixed

- La CI verde ya no se acepta como evidencia sin comprobar el journal: un run con `StageFinished` y cero `StepStarted` es un cache hit que no ejecutó un solo test. Se fija la regla operativa de que un verde no es evidencia hasta que el journal muestra `StepStarted` + `EchoOutputCaptured` en el stage de tests.

## [0.16.4] - 2026-09-28 — correctivo de v0.16.3

**PATCH**.

- Release correctiva: `v0.16.3` se publicó con package metadata defectuosa. La provenance no se reescribe; la versión buena es esta.
- `governance/backups.py`: la política de recolección se aísla del resto de la función (cc 14 → 3).
- `audits/audit_debt.py`: las recomendaciones se derivan de la medición, no de prosa congelada en el informe.
- Primera release hecha por el camino manual documentado, tras confirmarse que `sddk release plan` exige un `Cargo.toml` que este proyecto (Python) no tiene ni debe tener.

## [0.16.3] - 2026-09-28 — snapshot consistente en WAL y criterio de CI verde

**PATCH**.

### Fixed

- `sg backup create` hacía una copia cruda del fichero SQLite. Con el WAL activo, esa copia puede no contener transacciones ya confirmadas. Ahora usa el snapshot consistente de la API `Connection.backup()`.

### Documentation

- «Un pipeline en verde no prueba que los tests hayan pasado»: el cache hit de `pipelinek` producía `Pipeline finished with SUCCESS` sin ejecutar un solo test. Con la base de v0.16.2 eran 1413 tests los realmente ejecutados frente a 1455 existentes.
- Corrección de B2: `permissions.yaml` ausente **no** es una carencia del framework. Es un archivo del proyecto, en la raíz del repositorio, y el binario lo dice literalmente. El `find $FRAMEWORK` de la sesión anterior buscó en el sitio equivocado.
- Errata del mensaje de `9c0985e` (un carácter chino en mitad de una frase), registrada en vez de reescribir historia.

## [0.16.2] - 2026-09-27 — clasificación de errores por tipo y CI con rutas absolutas

**PATCH**.

### Fixed

- Los errores de `knowledge` se clasificaban por texto del mensaje en vez de por tipo. Un cambio de redacción rompía la clasificación en silencio.
- `bool` se aceptaba donde el esquema declara `integer`/`number`, porque en Python `bool` es subclase de `int`.
- `bare except` estrecho a los tipos que realmente puede lanzar.
- 7 delegaciones de `Storage` rotas dentro de `SqliteUnitOfWork`.
- CI: `.pipeline.kts` pasa a estar versionado (AGENTS.md exige que el gate de CI local canónico esté en control de versiones) y sus `sh(...)` usan rutas absolutas. El motor no resuelve el cwd del script, así que las rutas relativas se ejecutaban contra `/`.

## [0.16.1] - 2026-09-27 — cierre de conexiones en el CLI y límite estricto de DTO

**PATCH**.

### Fixed

- Los handlers del CLI no cerraban las conexiones SQLite de las que eran propietarios: se acumulaban hasta el final del proceso.
- `NameError` en `agents_root` dentro de `sg run`, detectado por un test E2E y no por la suite unitaria.

### Changed

- WI-38, R1: límite estricto de DTO en `list_promotions`, `get_promotion` y `get_budget`.

## [0.16.0] - 2026-09-27 — R1+R2 persistence boundary (WI-32.4+32.5+33)

**Resumen**: sprint completo sobre el audit externo del 2026-09-27 (HEAD pre-v0.15.0 `974055c`), cerrando los hallazgos R1 (dict[str,Any] fuga de persistencia) y R2 (Connection lifecycle). **MINOR bump** sin BREAKING CHANGE: 4 DTOs inmutables nuevos + SqliteUnitOfWork como single owner de la `sqlite3.Connection`. Total: **1109/1109 tests PASS** (+31 desde 1078, medido via `pytest --no-header -q` en HEAD `b42a2a8` en 184s), ruff check+format limpios, release_governance 2/2 PASS.

### Added

- **`StoredRun`** (8 campos, `frozen=True, slots=True`) en `platform/ports`: DTO inmutable para `workflow_runs`. Sustituye `dict[str, Any]` y `sqlite3.Row` en `Storage.list_runs/get_run/load_run` y RunController (consumo via atributos).
- **`StoredNodeExecution`** (14 campos): DTO inmutable para `node_executions`. Sustituye `dict[str, Any]` en `Storage.list_node_executions`.
- **`StoredResource`** (12 campos): DTO inmutable para `resources`. Cierra fuga en `Storage.get_resource/list_resources`.
- **`StoredRelation`** (7 campos): DTO inmutable para `relations`. Cierra fuga en `Storage.dependencies_of/dependents_of`.
- **`SqliteUnitOfWork`** (`frozen=True, slots=True`) en `platform/uow.py`: fachada que owns la `sqlite3.Connection` y expone 5 bounded-context adapters que la comparten (`SqliteRunAdapter`, `SqliteEventAdapter`, `SqliteKnowledgeAdapter`, `SqliteGovernanceAdapter`, `SqlitePolicyAdapter`). Acceso via `storage.uow.{runs,events,knowledge,governance,policy}`. Cierra el hallazgo "Connection lifecycle" del audit externo (R2).

### Changed

- **`Storage.list_runs`** ahora devuelve `list[StoredRun]` (antes `list[dict[str, Any]]`).
- **`Storage.get_run`** ahora devuelve `StoredRun` (antes `dict[str, Any]`).
- **`Storage.load_run`** ahora devuelve `StoredRun` (antes `dict[str, Any]`).
- **`Storage.list_node_executions`** ahora devuelve `list[StoredNodeExecution]`.
- **`Storage.get_resource/list_resources`** ahora devuelven `StoredResource` (no `dict`).
- **`Storage.dependencies_of/dependents_of`** ahora devuelven `list[StoredRelation]`.
- **`RunController._load_run` y `_node_executions_for`** ahora devuelven DTOs (consumo via atributos). 13 accesos `dict[key]` convertidos.
- **`Storage.__init__`** ahora crea una `SqliteUnitOfWork` interna; `storage.uow` es property pública.
- **CLI `runner.py`**: 3 consumers de `list_resources` (`_count_resources`, `_load_registry`, `declare_types_from_pack`) usan atributos del DTO.
- Cada DTO expone `to_dict()` para compatibilidad con consumers/tests legacy que esperan API dict-based.

### Migration notes

- Consumers de `Storage.list_runs` etc. deben migrar de `row["key"]` a `row.key` (atributo del DTO). Compatibilidad legacy: `row.to_dict()` preserva el dict histórico.
- `Storage.uow` es la nueva API para acceder a los bounded-context adapters. La API facade (`storage.list_runs`) sigue funcionando sin cambio.
- `isinstance(storage.uow.runs, RunRepository)` puede NO funcionar porque los adapters no implementan TODOS los metodos del Protocol (algunos delegan via `**kwargs`). Usar `callable(getattr(uow.runs, name))` para verificar presencia de metodos clave.

### Tests

- 13 tests nuevos: `test_run_dto.py` (7) + `test_resource_dto.py` (6).
- 5 tests existentes adaptados de subscript a atributo: `test_h9_storage_run_reads.py`, `test_h9_runcontroller_characterization.py`, `test_registry_branches.py`, `test_s1_sqlite.py`.
- 6 tests nuevos para UoW: `test_uow.py` (5 adapters, shared connection, lifecycle, identity stability, facade/adapter equivalence).

### Audit debt (post-WI-32.4+32.5+33)

- `Storage` `dict[str, Any]` returns: **5 → 2** (los 2 restantes son `get_promotion` + 1 governance, fuera del scope del sprint).
- `Storage` LoC: 2499 → 2716 (+217 por UoW + property `uow` + aliases; refactor pendiente WI-34 para bajar facade a <500 LoC).
- 47 modulos Python, 17163 LoC, 607 funciones (vs 46/16279/565 pre-WI-32).

## [0.15.0] - 2026-09-27 — R0 housekeeping + WI-31 (cast Storage Protocol) + WI-35 (docs) (BREAKING)

**Resumen**: cierre de la ronda de housekeeping + refactors sobre la base post-v0.14.8, en modo SDDK autónomo. **MINOR bump** por **1 BREAKING** (QW-B: redaction default `none`→`metadata`, secure-by-default) + **3 feat** (QW-C: `Storage` context manager, WI-31: factor `Storage.knowledge_repository()`, QW-I: snapshot `docs/blueprint/` versionado) + **1 fix** (QW-A: Anthropic default migrated retired model `claude-3-5-sonnet-20241022` → `claude-sonnet-4-6`). WI-31 cubre un code path del `RunController._compile_knowledge` con **0 tests** previos, anade 7 tests nuevos y elimina un `cast(Storage, self._runs)` que era un workaround del type checker. WI-35 documenta el patron SDDK end-to-end para futuras sesiones. Total: **1078/1078 tests PASS** (+30 desde 1048, +10 vs mi memoria previa de 1068; medido via `pytest --collect-only` y `--no-header -q` en HEAD `7e5566e` en 527.95s), ruff check+format limpios, cobertura **95.25%** lines / **90.54%** branches.

### BREAKING CHANGE

- **QW-B `fix(redaction)`**: default policy del EventLog paso de `"none"` a `"metadata"`. Antes (`v0.14.8.dev0` y todos los ancestros), un tenant sin policy explícita devolvia payloads sin redaccion: claves `api_key`, `password`, `token` se emitian en el `runtime_events` con su valor original. Ahora un EventLog sin policy explícita redacta todo metadata antes de emitirlos como evento. Migracion opt-in: los callers que necesiten el comportamiento anterior deben pasar `EventLog(..., policy_resolver=lambda _t: "none")` o setear `policy_resolver` a nivel tenant. Tests: `test_eventlog_default_policy_is_metadata` (re-named de `test_eventlog_passes_through_by_default`) + `test_eventlog_explicit_none_passes_through` documentan el cambio. **Impacto**: tenants que ya tenian un `policy_resolver` explicito no se ven afectados.

### Added (feat)

- **QW-C `feat(storage)`**: `Storage` como context manager — `with Storage(path) as s: ...` cierra la conexion sqlite determinísticamente via `__exit__`. Antes (`v0.14.8.dev0` y todos los ancestros), abrir una `Storage` sin `close()` emitia `ResourceWarning: unclosed database`. El metodo `close()` es idempotente. Nuevo modulo `tests/test_storage_context_manager.py` con 6 tests. Migracion opt-in: callers existentes con `storage.close()` siguen funcionando igual.

- **WI-31 `refactor(runcontroller)`** (`Storage.knowledge_repository()` factor): introduce una tercera factoria `Storage.knowledge_repository()` paralela a `Storage.run_repository()` y `Storage.event_store()`, devolviendo el propio `Storage` (sin implementar otras vistas). Como los dos Protocols `RunRepository` + `KnowledgeRepository` los implementa `Storage` por structural subtyping, este factor se reduce a sinonimo de `self`. Habilita la migracion futura a `RunStorage`/`KnowledgeStorage` separadas (WI-02b) sin tocar `RunController`. Tambien: nuevo kwarg opcional `knowledge: KnowledgeRepository | None` en `RunController.__init__` que elimina el antiguo `cast(Storage, self._runs)` en `_compile_knowledge`. 4 callers legacy en `tests/test_h9_context_in_run.py` migrados con `knowledge=s` explicito. 7 tests nuevos en `tests/test_runcontroller_compile_knowledge.py`. Tambien: `Storage.close()` cambia `try/except pass` por `contextlib.suppress(ProgrammingError)` (ruff SIM105).

- **QW-I `docs(blueprint)`**: snapshot versionado del blueprint en `docs/blueprint/` (12 capitulos + README + adr/ 13 ADR + plan/ 6 plans + references/). Antes el test `test_uats_can_be_loaded_as_documentation` leia de `external/blueprint-v1/` que esta gitignored y saltaba con `pytest.skip`. Ahora lo lee del snapshot versionado. `.gitignore` permite unicamente `docs/blueprint/` (no `docs/*` blanket). Script `scripts/sync_blueprint.sh` idempotente; `--check` detecta drift entre el origen y el snapshot via SHA256. Documento `docs/blueprint/SYNC.md` con la politica on-demand.

### Fixed

- **QW-A `fix(http_adapter)`**: el default Anthropic para `HttpAgentAdapter` migraba a `claude-sonnet-4-6` desde el model `claude-3-5-sonnet-20241022` que Anthropic retiro el 2025-10-28. Antes, una llamada HTTP sin header explicito `x-llm-model` enviaba una peticion que el proveedor rechazaba con 404 Not Found. Tambien: blacklist de modelos retirados en tests (`claude-3-5-sonnet-20240620`, `claude-3-opus-20240229`). Test nuevo: `test_default_model_anthropic_not_deprecated`.

### Changed (refactor, sin bump)

- **QW-D `refactor(runtime_types)`**: `EVENT_KINDS` ahora se deriva del Literal `EventType` via `frozenset(get_args(EventType))` (no mas frozenset paralelo). Antes `EventType` (Literal 8 valores) y `EVENT_KINDS` (frozenset 14 valores) eran DOS conjuntos con solo 3 valores comunes. Despues: 19 valores unicos. 2 tests nuevos (`TestEventKindSingleSource`) verifican single-source-of-truth.

- **QW-E `refactor(runtime_types)`**: `SOURCE_KINDS` ahora derivado del Literal `SourceKind` via `frozenset(get_args(SourceKind))` (5 valores; `skill_pack` ahora valido). Antes el frozenset omitia `skill_pack` y lo rechazaba runtime aunque el Literal lo declaraba. 2 tests nuevos (`TestSourceKindSingleSource`).

- **QW-F + QW-G `chore(coverage)`**: `fail_under` 60→80 + omit de `__init__.py`, `__main__.py`, `cli/runner.py` en `[tool.coverage.run]`. Tambien: `tests/uat_audit.py` y `tests/test_cli_uat.py` propagan `PYTHONPATH` al subprocess cuando el padre corre dentro del venv (QW-G fix que evita `No module named skillgraph` en tmpdir).

- **QW-H `refactor(uat_audit)`**: `uat_audit.uat_08()` y `uat_audit.uat_09()` ahora leen la evidencia existente en `tests/uat-evidence/UAT-XX.json` en vez de pisarla con un stub BLOCKED. Antes el test E2E `test_h4_expansion_cli.py` escribia evidencia PASS real, y `uat_audit` lo sobrescribia con BLOCKED en cada corrida. 5 tests nuevos verifican ambos caminos.

### Chore (no bump)

- **`pytest` + coerencia release governance**: el conjunto de stewardship (STATE.yaml + CURRENT.md + CHANGELOG.md) ahora cubre la timeline completa del repo en una sola fuente. `current_workitem` en STATE.yaml pasa de `WI-30` a `WI-31` (primera vez que cambia despues de WI-30).

- **`scripts/sync_blueprint.sh`** (QW-I): idempotente; modo `--check` detecta drift sin tocar archivos.

- **WI-35 `docs(state)`**: prioridad_6 en `STATE.yaml.stewardship_backlog` documenta el patron operacional aplicado en WI-31 (cycle start → backlog capture → TDD → commit atomico → smoke → triage → promote). Entrada en SESSION-JOURNAL.md con SHA del commit y bl_item_id. Sin cambio de contrato.

## [0.14.8] - 2026-09-26 — WI-21..WI-30 (debt-reduction H-03: 8 hotspots cc→low single-digits)

**Resumen**: ciclo de deuda tecnica quirurgica cerrando 8 hotspots publicos identificados en el catalogo H-03 (cyclomatic complexity > 15 en `src/`). Patron consistente: extraer helpers privados puros + module-level utilities, manteniendo 100% backward-compat. WI-28 anade auditor reproducible `audits/audit_debt.py`. **Politica D-66 satisfecha**: cero hotspots publicos cc≥20 en `src/` (unico cc≥15 restante: `main()` cc=50, excluido por D-64 al ser CLI entry point / H-02 god module). Tests: **1048/1048 PASS** preservados, ruff check+format limpios, auditor reproducible.

### Changed (debt-reduction H-03, refactor surgical)

- **WI-21**: `graph_expansion.validate` cc 24→4 (D-52). Helpers puros.
- **WI-22**: `parser.parse_markdown` cc 17→2 (D-53/D-54). Helpers + bug descubierto por TDD: gender mismatch "revision vacia" vs helper default "vacio".
- **WI-23**: `locks.take` cc 16→5 (D-55). 4 helpers privados.
- **WI-24**: `record_validation_receipt` cc 14→5 (D-56/D-57). 4 helpers; kwarg `empty_msg` preservado verbatim.
- **WI-25**: `traverse_invalidations` cc 13→5 (D-58). 3 helpers (seed/expand/warn); TDD catcho bug de kwarg unused `hop` que se quedaba en helper.
- **WI-26**: `HttpAgentAdapter.invoke` cc 12→7 (D-59). Sentinel `RetryableHttpStatus` + helper `_dispatch_response`.
- **WI-27**: `compile_handoff_from_scopes` cc 12→1 (D-60). Triada `validate_inputs` + `enforce_*_or_raise` + `build_synth_recipe`. TYPE_CHECKING imports block + `Sequence` from `collections.abc` para F821/UP035/UP037 simultaneos.
- **WI-29**: `cli.runner.cmd_run` cc 22→5 (D-67). Patron `_resolve_run_inputs` + `_reconcile_until_terminal` + `_resolve_fixtures_root`. Lazy imports para evitar coste arranque CLI.
- **WI-30**: `knowledge.git_source.detect_changes` cc 18→8 (D-68). 3 helpers (1 metodo privado + 2 module-level).

### Added (audit infrastructure)

- **WI-28**: `audits/audit_debt.py` (~215 LoC) reproducible CLI. Reporta cc, loc, nesting, god modules, hotspots publicos/privados, funciones largas. Emite `audits/architecture-debt-YYYY-MM-DD.md`. Smoke tests `tests/test_audit_debt_smoke.py` (4/4 PASS).
- **D-61..D-66**: decisiones arquitectonicas formales (god modules thresholds, exclusion de `main()`, politica D-66 "cero hotspots publicos cc≥20 en cada release o documentar la excepcion").
- **D-67/D-68**: patrones estructurales post-WI-28.

### Notes

- **MINOR bump** (regla WI-01 + AGENTS §7 SEMVER): los 8 `refactor` no son breaking, pero la campana debt-reduction es estructural y merece release visible. 0.14.7 → 0.14.8.
- Mantiene regla WI-01 "release sin --force sobre published tags": v0.14.1..v0.14.7 intactos, este release es nueva v0.14.8.
- Migracion Pattern transitorio `.dev0`: post-tag housekeeping mantiene `__version__ = "0.14.8.dev0"` para cumplir release_governance (`HEAD > last-tag` exige `.devN`).
- Backlog post-WI-30: P1 god modules (H-01 storage 2407 LoC, H-02 cli/runner 2477 LoC, runcontroller 1357 LoC) requieren ADR — fuera del scope surgical. Formal `prioridad_1_spec_s7plus` y `prioridad_5_s7plus_ejecucion` siguen abiertos esperando decision de operador sobre S7+ scope.

## [0.14.7] - 2026-09-26 — WI-12..WI-17 (FEAT+DOC: sg backup + threat model + observability)

**Resumen**: ciclo mixto feat+debt que cierra H-06 (cmd_knowledge_compile import redundante), anade backups ZIP con SHA-256 (`sg backup create|list|restore`), publica Threat Model S8 surface HTTP + `repr` redact de `api_key`, y corre runbook T6 de observability (9 secciones verificadas). Tests: 1024/1024 PASS, ruff check+format limpios. MINOR bump por nueva capacidad observable (`sg backup`). **Nota**: esta entrada se reescribe retroactivamente en el release v0.14.8 — el tag v0.14.7 existia pero CHANGELOG fue omitido en el ciclo original.

### Added (FEAT)

- **WI-15**: `sg backup create|list|restore` con ZIP + SHA-256 (22 tests en `tests/test_backup.py`). Comandos nuevos del CLI para backup/restore del SQLite state.
- **WI-14 (T3)**: Threat model S8 surface HTTP documentado en `docs/observability-runbook.md`. `HttpAgentAdapter` ahora redacta `api_key` en `repr()` para evitar leak en logs/traces.

### Changed (DOC)

- **WI-16**: runbook T6 ampliado a 9 secciones (alerts, dashboards, SLOs, incident response, etc.) con claims verificados.
- **WI-17**: H-06 cierre, `cmd_knowledge_compile` pierde `import json` redundante.

### Notes

- **MINOR bump**: nuevo subcommand `sg backup` es capacidad observable nueva. 0.14.6 → 0.14.7.

## [0.14.6] - 2026-09-26 — WI-06..WI-10 (housekeeping: coverage hardening H-14 + docs sync)

**Resumen**: cierre de los 3 unicos gaps materiales de cobertura reconocidos en `CURRENT.md` para el nucleo evolution-v2 (H11..H15): `governance/receipts.py` 73%→99% (WI-06), `file_handoff.py` 85%→93% (WI-07), `governance/improvement.py` 84%→100% (WI-08). Adicionalmente se sincroniza la prosa de `CURRENT.md` y `README.md` con la realidad post-stewardship créatif (WI-09, WI-10), incluyendo badges `984/984 tests` y `evolution_v2 100% (H11..H15)`. Sin cambio de codigo de produccion (WI-06/07/08 son solo tests). Tests: 984/984 PASS preservados en CI local (`pipelinek`) y `ruff format` + `ruff check` limpios.

### Added (test coverage)

- **`tests/test_h14_validation_receipts.py`** (WI-06): +28 tests en 5 clases nuevas. Cubre `ValidationReceipt.__post_init__`, `is_receipt_applicable` con deps, `record_validation_receipt` early returns, `list_applicable_receipts` paths defensivos, constante `RECEIPT_VERDICTS`.
- **`tests/test_h13_handoff_expert.py`** (WI-07): +17 tests en 5 clases nuevas. Cubre mensajes `HandoffBlockedError`, `build_coverage_manifest` con focos, `should_skip_adapter` con payloads vacios, `ScopeAwareRecipe` validation, type-checks defensivos.
- **`tests/test_h15_improvement.py`** (WI-08): +14 tests en 7 clases nuevas. Cubre `ImprovementCandidate.__post_init__`, `PromotionDecision.__post_init__`, `promote_candidate` approver required, `rollback_candidate` policy="blocked", `detect_redundant_extraction` empty sigs, `localize_omission` defensive branches, `compare_recipes` correction=False.

### Changed (docs sync)

- **`CURRENT.md`** (WI-09): limpieza de 4 stale markers pre-WI-06 (L50 "HEAD pendiente", L57 "working tree staged", L59 "HEAD == origin/main"); adicion de seccion cronologica `## Reactivacion 2026-09-26 — WI-06/07/08 cerrado`; actualizacion del modo de espera con el estado real post-stewardship.
- **`README.md`** (WI-10): badge `tests-405/405` → `tests-984/984`; nuevo badge `evolution_v2 100% (H11..H15)`; parrafo explicativo y filas tabla en EN y ES para evolution-v2 (H11..H15).
- **`STATE.yaml`**: `tests.total` 957→984, `delta_wi06/07/08` documentados, `current_workitem` actualizado WI-08→WI-11.

### Notes

- PATCH bump: housekeeping puro (test coverage + docs), sin cambio de API observable.
- Mantiene regla AGENTS §7 "release sin --force sobre published tags": los tags `v0.14.1..v0.14.5` quedan intactos, este release es nueva `v0.14.6`.
- Migracion Pattern transitorio `.dev0`: post-tag housekeeping mantiene `__version__ = "0.14.6.dev0"` para cumplir release_governance (`HEAD > last-tag` exige `.devN`).
- Stewardship créatif ejecutado bajo autorizacion operador ("continuamos completando, deuda tecnica primero") — D-17..D-34 documentadas.

## [0.14.5] - 2026-09-26 — WI-04/05 (housekeeping trazabilidad: journal retroactivo + cleanup drifts)

**Resumen**: cierre de drift de trazabilidad canonica detectado por audit transversal post-WI-03. Las entradas cronológicas de WI-02b y WI-03 faltaban en `SESSION-JOURNAL.md`; se añaden retroactivamente desde observables (commits, tags, CHANGELOG, specs). Adicionalmente se cierra drift menor en `CURRENT.md` (baseline tests 927→929; cuenta de releases 17→18) y bump `.dev0` requerido por `release_governance` (`HEAD > last-tag` exige `.devN`). Sin cambio de codigo de produccion. Tests: 929/929 PASS preservados en CI local (`pipelinek`) sin ejecutarse code paths nuevos.

### Changed (housekeeping)

- **`SESSION-JOURNAL.md`**: 2 entradas retroactivas (WI-02b, WI-03) + 1 entrada del propio WI-04. Tono consistente con entradas existentes; hechos verificables contra git log + CHANGELOG; sin reinterpretacion.
- **`CURRENT.md`**:
  - `Tests: 927/927 PASS` → `929/929 PASS` (post-WI-03).
  - `17 releases` → `18 releases` (contaban v0.14.3 y v0.14.4; ahora 18 antes del bump final).
- **`STATE.yaml`** + `__init__.py`: bump `0.14.4.dev0` → `0.14.5` (release).
- **`specs/wi-04-journal-traceability.md`**: spec del WI (D-16, 73 LoC).

### Notes

- PATCH bump: housekeeping puro (documentacion + bumps de gobernanza), sin cambio de API observable.
- Mantiene regla AGENTS §7 "release sin --force sobre published tags": el tag `v0.14.4` queda intacto, este release es nueva `v0.14.5`.
- Migración Pattern transitorio `.dev0`: solo si housekeeping post-tag requiere `.devN` para release_governance y el operador autoriza release inmediato (v0.14.5 PATCH). Alternativa habitual es acumularlo en un WI posterior.

## [0.14.4] - 2026-09-26 — WI-03 (governance/receipts migra a KnowledgeRepository)

**Resumen**: cierre del último escape hatch `_conn.execute` en código de dominio (fuera de Storage.py, que es donde debe estar, y catalog.py, que usa un SQLite propio distinto del Storage de proyecto). Sin cambio de API observable. Tests: 929/929 PASS (de 927 en v0.14.3; +2 tests nuevos de Storage.list_sources).

### Changed (interno, sin API change)

- **`KnowledgeRepository` Protocol** añade `list_sources(*, tenant_id, project_id) -> tuple[Source, ...]` (duck typing).
- **`Storage.list_sources`** nueva: SELECT * FROM sources WHERE tenant_id = ? AND project_id = ? ORDER BY source_id. Read-only, tupla inmutable.
- **`receipts.list_applicable_receipts`**: itera `storage.list_sources(...)` en vez de `storage._conn.execute('SELECT source_id FROM sources ...')`. Semántica idéntica (mismos source_ids visitados; el nuevo método devuelve además el ADT completo por si futuro).
- **Audit transversal post-WI-02b**: `grep "_conn" src/skillgraph/governance/` → 0 sitios activos (solo aparece en comentario histórico del WI-03). `grep "_conn" src/skillgraph/ --include="*.py" | grep -v "platform/storage.py\|resources/catalog.py"` → 0 sitios.

### Notes

- `catalog.py` queda con acceso directo a `_conn`: usa un SQLite propio en `data_root/catalog.sqlite`, no es Storage de proyecto (no viola la regla "Storage encapsula SQL", que se aplica a la tabla de proyecto). Fuera de scope.
- WI-02b AC-5 extendido ahora a `governance/`: regla "Storage encapsula SQL" completa en KC, KI, ContextController, receipts.
- PATCH bump (sin breaking change, sin nuevos comandos CLI).

## [0.14.3] - 2026-09-26 — Refactor WI-02b (EventLog + KnowledgeController + escape hatch removal)

**Resumen**: segunda mitad del refactor de puertos de persistencia (WI-02b). Cierra los últimos 2 ACs abiertos en 0.14.2: AC-3 (EventLog/KnowledgeController aceptan Protocols en vez de Storage) y AC-4 (eliminación del escape hatch `Storage.conn`). Sin cambio de API observable para el usuario. Tests: 926/926 PASS (sin regresión) en CI local canónico (`pipelinek`).

### Changed (interno, sin API change)

- **`EventLog`** ya no se construye con `sqlite3.Connection`; ahora acepta directamente el `EventStore` Protocol (que `Storage` cumple por duck typing). Wrappers `event_store()` y `record_event()` añadidos a `Storage` para que siga siendo fachada compatible.

- **`KnowledgeController`** ya no se construye con `storage=Storage`; ahora recibe `knowledge=KnowledgeRepository`. `KnowledgeInvalidator` deja de acceder a `controller.storage._conn` (5 sitios SQL → 0). `ContextController` interno deja de acceder a `ctrl.storage.*` (4 sitios SQL → 0).

- **`Storage.conn`** (`@property` público introducido en H9-BSlice3-S8) **eliminado**. Era escape hatch que rompía la regla "Storage encapsula SQL" — los call sites que aún lo necesitaban (3 tests internos + 1 caso de test_h9_storage_run_controller_no_conn) migran a `Storage._conn` (privado por convención, sigue permitido). `TestStorageConnPublic` borrado (validaba un artefacto que ya no existe).

- **Protocols ampliados**: `EventStore` recibe `fetch_event_raw()` y `ensure_schema()`; `KnowledgeRepository` recibe `find_entity()`, `source_exists_anywhere()`, `list_claims_for_subject()`, `list_claims_using_evidence()`, `mark_claims_stale()`, `reactivate_claims_with_revision()`, `list_stale_claims()`, `record_event()` (para emisión de `KnowledgeInvalidated` por KI).

- **Tests**: 4 archivos migrados a `SqliteEventStoreForTest` (helper de tests que aún necesitan `sqlite3.Connection` directo: `test_runtime_events.py`, `test_redaction.py`, `test_runcontroller.py`, `test_h9_runcontroller_characterization.py`).

### Notes

- AC-3 (RC/KC/KI reciben Protocols, sin `storage=` ni `conn=`): **PASS**.
- AC-4 (`Storage.conn` eliminado, escape hatch cerrado): **PASS**.
- AC-5 (KC/KI independientes de `_conn`, regla "Storage encapsula SQL" completa): **PASS** (verificación: `grep "_conn" src/skillgraph/knowledge/knowledge_controller.py` → exit 1).
- AC-11 (`Storage` sigue siendo fachada compatible): **PASS** (los 3 métodos añadidos son del Protocol; la API pública no rompe).
- `tests/uat-evidence/UAT-{08,09}.json` drift explícitamente fuera de alcance del WI-02b.
- Sin bump adicional al SemVer: API externa sin cambio (PATCH).

## [0.14.2] - 2026-09-26 — Refactor B+C (persistence ports + RunController) (WI-02a)

**Resumen**: refactor interno de la capa de persistencia. Introduce
puertos de capacidad (Protocols estructurales) sin cambio de API
observables para el usuario. Tests: 927/927 PASS (155.73s) en CI
local canónico (`pipelinek`).

### Added

- `src/skillgraph/platform/ports/__init__.py`: cinco `Protocol`s
  estructurales de capacidad (duck typing sin `runtime_checkable`
  salvo `EventStore`):
  - `RunRepository`: ciclo de vida de runs.
  - `EventStore`: append-only de eventos con `UNIQUE(event_id)`.
  - `KnowledgeRepository`: lectura/escritura de documentos.
  - `PromotionRepository`: snapshots de promoción policy→production.
  - `PolicyStore`: versionado de políticas.
- `tests/test_persistence_ports.py`: 7 tests (5 structural +
  2 `runtime_checkable` sobre `EventStore`).
- Factorías en `Storage`: `run_repository()`, `event_store()`,
  `policy_store()` (compatibilidad — devuelven `self`).

### Changed

- `RunController.__init__`: sustituye `storage: Storage` por
  tres puertos explícitos: `runs: RunRepository`,
  `events: EventStore`, `policy: PolicyStore`. La inyección
  por Protocol elimina el acoplamiento a la implementación.
- Migración masiva de call sites: 16 ficheros de test +
  `src/skillgraph/cli/runner.py` actualizados a la nueva firma.
- Verificado: `Storage` implementa estructuralmente los cinco
  Protocols (19/3/4/23/3 métodos coinciden).

### Deferred (WI-02b)

- `EventLog`: migración de `sqlite3.Connection` directo a `EventStore`.
- `KnowledgeController`: dejar de acceder a `storage._conn`.
- Eliminación de `Storage.conn` como propiedad pública (romper API).

---

## [0.14.1] - 2026-09-26 — Release & integration readiness (WI-01)

**Resumen**: release correctiva que cierra la grieta de provenance
entre `__version__` y las etiquetas git. CI local canónico = `pipelinek`.
Sin cambio de capacidad observable a nivel de API; todos los items son
de empaquetado, admisión y reconciliación documental.

### Added

- `tests/test_release_governance.py`: admission gate de release. Tres
  ramas válidas (HEAD en etiqueta, HEAD posterior con `.devN`, sin
  etiqueta reachable) y dos derivas reales rechazadas (`__version__`
  puro sin etiqueta; `.devN` con base contradictoria).
- `SECURITY.md`: proceso de divulgación coordinada (GHSA,
  ventana High = 90 días).
- Regla `§12 Regla de release` en AGENTS.md: fuente única de
  SemVer = `src/skillgraph/__init__.py:__version__`; prohibido
  `--force` sobre etiquetas publicadas; release gate = test pytest.

### Changed

- `mise.toml`: `tasks.sync` migra de `--extra dev` (roto en PEP 735)
  a `--group dev`. Nueva `tasks.release-gate`.
- `pyproject.toml`: `license` pasa de `Proprietary` (text) a
  `"Apache-2.0"` (SPDX), alineado con `LICENSE` real.
- `pyproject.toml`: `[tool.coverage.report] fail_under` sube de 0
  a 60 (gate global mínimo; focales por módulo siguen en WI-02).
- `src/skillgraph/__init__.py:__version__` = `"0.14.1.dev0"` durante
  el trabajo; `"0.14.1"` tras CI verde.
- Documentación reconciliada: CURRENT.md, STATE.yaml, JOURNAL y
  CHANGELOG convergen en baseline real (918 tests, 160.74s).

### Erratum: `v0.14.0`

La etiqueta `v0.14.0` queda como **evidencia histórica de una release
defectuosa** (HEAD `d50f666`, package metadata declaraba `0.7.0.dev0`).
**NO se reescribe**. La release correctiva es `v0.14.1`. SemVer no
contempla reescritura retroactiva de versiones publicadas.

## [Unreleased — evolution-v2 (H0..H15)] — 2026-09-25

**Resumen**: roadmap `external/evolution-v2/plan/ROADMAP.md` cerrado al 100%. 5 nuevos modulos, 58 tests UAT-EVO nuevos (suite 830/830 PASS). NO bump de release: los workitems añaden superficie de conocimiento/governance sin capacidad observable nueva a nivel de API CLI (no hay comandos ni flags nuevos).

### Added (evolution-v2)

- **H0–H1 (foundation)**: cobertura del recorrido real y caracterización de gates (audits/h10-recorrido-real-2026-09-25.md).
- **H11 — Conocimiento tipado reutilizable** (`skillgraph.knowledge.file_signature`): `FileSignature`, `SignatureProcedencia`, `SignatureVigencia`, `ExtractionState`. Pure extractor regex_def. Persistencia via `Evidence(kind='file_signature')` reusando tabla existente.
- **H12 — Scopes y consultas composables** (`skillgraph.knowledge.file_scope`): `FileScope` Literal, `ScopeQuery`, `ScopeResolution`, `AggregatedSignatures`, `aggregate_signatures()` puro. Aislamiento E2E-08 estricto.
- **H13 — Handoff experto desde consultas** (`skillgraph.knowledge.file_handoff`): `ScopeAwareRecipe` (composicion sobre `ContextRecipe`), `CoverageManifest`, `HandoffBlockedError`, `compile_handoff_from_scopes()`. Manifest como representación canónica; handoff compila OK con `obligatory=()`.
- **H14 — Evidencia operativa temporal** (`skillgraph.governance.receipts`): `ValidationReceipt` (frozen, verdict Literal), `is_receipt_applicable()` puro, `record_validation_receipt()`, `list_applicable_receipts()`. Persistencia via `Evidence(kind='validation_receipt')`.
- **H15 — Evaluación y automejora acotada** (`skillgraph.governance.improvement`): `ImprovementCandidate` + `ImprovementKind` Literal cerrada, `detect_redundant_extraction()`, `localize_omission()`, `compare_recipes()`, `promote_candidate()` exige `human_approved=True` (UAT-EVO-18 sin autocertificacion, `SelfCertificationBlockedError` tipado), `rollback_candidate()` con `RollbackPolicy` Literal.

### Notes

- Persistencia H11–H15: ninguna tabla nueva. Todos los nuevos tipos se almacenan via `Evidence(kind=...)` reusando la tabla `evidence` existente (regla AGENTS §1.5).
- ADT cerradas: `ExtractionState`, `FileScope`, `ImprovementKind`, `RollbackPolicy`, `ReceiptVerdict` via `Literal[...]` (regla AGENTS §2.1).
- Errores tipados: `HandoffBlockedError`, `SelfCertificationBlockedError` (subclases de `SkillGraphError`, regla AGENTS §1.2).
- Tests UAT-EVO: 4 + 12 + 8 + 8 + 9 + 9 = 50 nuevos (H0–H1 + H11–H15).

## [0.7.0] — 2026-09-24

**Resumen**: refactor arquitectónico con **BREAKING CHANGE** en la
estructura de imports. La capa de compat layer en la raíz de
`src/skillgraph/` se elimina: los 20 módulos que eran re-exports
puros hacia bounded contexts (`catalog`, `recipe`, `runtime_types`,
`dsl`, `errors`, `graph_expansion`, `handoff`, `storage`, `workflow`,
`bricks`, `git_source`, `pack_loader`, `promotion`, `runcontroller`,
`skill_importer`, `paths`, `agent`, `context_controller`,
`knowledge_controller`, `knowledge_invalidator`) desaparecen.

Adicionalmente, `knowledge/context_controller.py` deja de acceder a
`storage._conn` directamente; ahora delega en 3 APIs públicas nuevas
del Storage (`list_claims_by_predicate`, `list_evidences_for_source`,
`list_resource_refs_for_run`). Cumplimiento completo de la regla
arquitectónica "Storage encapsula SQL" introducida en 0.6.0.

**Resultado neto**: 619/619 tests PASS (de 604 en 0.6.0, +15). 16/16
UAT PASS, 0 FAIL, 0 BLOCKED. Cobertura 85% branch.

### SemVer decision

El refactor 2 introduce cambios incompatibles de import paths
(un importador externo que usaba `from skillgraph import Storage`
queda roto). SemVer estricto promovería esto a **MAJOR** (1.0.0).

Sin embargo, este proyecto **no tiene importadores externos**
(repo local-only, sin `git push`, sin dependencias aguas abajo).
Por tanto el impacto real de la rotura es CERO: la test suite
integrada se reescribió en el mismo commit.

Se etiqueta como **MINOR** (0.7.0) por:
1. Decisión explícita del operador ("tag MINOR tras el refactor
   combinado") registrada en SESSION-JOURNAL 2026-09-24 06:46.
2. La regla de la introducción del CHANGELOG ("BREAKING CHANGE / `!`
   → MAJOR") se respeta en el sentido de que es BREAKING y se
   documenta como tal. La decisión de no promover a MAJOR se basa
   en la **excepción documentada de "sin importadores externos"**.

Si el proyecto adquiere importadores externos en el futuro, el
próximo cambio incompatible debe promover a 1.0.0 sin excepciones.

### BREAKING CHANGES (MAJOR por semver estricto)

- `from skillgraph.storage import Storage` ya **no funciona**;
  debe ser `from skillgraph.platform.storage import Storage`.
- Análogamente para todos los 19 shims restantes:
  - `skillgraph.errors` → `skillgraph.core.errors`
  - `skillgraph.recipe` → `skillgraph.core.recipe`
  - `skillgraph.runtime_types` → `skillgraph.core.runtime_types`
  - `skillgraph.dsl` → `skillgraph.domain.dsl`
  - `skillgraph.pack_loader` → `skillgraph.domain.pack_loader`
  - `skillgraph.skill_importer` → `skillgraph.domain.skill_importer`
  - `skillgraph.graph_expansion` → `skillgraph.governance.graph_expansion`
  - `skillgraph.promotion` → `skillgraph.governance.promotion`
  - `skillgraph.context_controller` → `skillgraph.knowledge.context_controller`
  - `skillgraph.git_source` → `skillgraph.knowledge.git_source`
  - `skillgraph.knowledge_controller` → `skillgraph.knowledge.knowledge_controller`
  - `skillgraph.knowledge_invalidator` → `skillgraph.knowledge.knowledge_invalidator`
  - `skillgraph.paths` → `skillgraph.platform.paths`
  - `skillgraph.bricks` → `skillgraph.resources.bricks`
  - `skillgraph.catalog` → `skillgraph.resources.catalog`
  - `skillgraph.workflow` → `skillgraph.resources.workflow`
  - `skillgraph.agent` → `skillgraph.runtime.agent`
  - `skillgraph.handoff` → `skillgraph.runtime.handoff`
  - `skillgraph.runcontroller` → `skillgraph.runtime.runcontroller`

Este es un **MINOR** y no MAJOR porque no hay importadores
externos (proyecto local-only, sin `git push`). Se documenta
como BREAKING por honestidad pero el impacto real es CERO
(test suite integrada reescrita en el mismo commit).

### Refactors (sin bump adicional)

- **`Storage` — 3 métodos nuevos (lectura pura)**:
  - `list_claims_by_predicate(*, project_id, predicate, claim_target)`
    — devuelve claims que matchean el predicado (line_count,
    function_count, imports_module, defines_symbol, test_passes,
    file_exists, spec_revision).
  - `list_evidences_for_source(*, source_id)` — evidences ligadas
    a un source.
  - `list_resource_refs_for_run(*, run_id, kind="claim"|"evidence")` —
    refs únicas, DISTINCT + ORDER, con validación de kind.

- **`context_controller.py` — 4 sitios SQL eliminados**: el código
  ahora delega en las 3 APIs nuevas, no accede a `_conn`. La regla
  "Storage encapsula SQL" se cumple completa en este módulo.

### Cambios estructurales (borrado)

- 20 shims eliminados de `src/skillgraph/*.py` (1-9 LoC cada
  uno, re-exports puros).
- 37 ficheros de tests reescritos: ~118 imports de shim a
  bounded context directo (mecánico via script Python con
  mapping 1:1 por shim).
- 2 tests en `tests/test_uat_blocked.py` actualizados
  (`test_h6_pack_loader_module_exists` ahora importa desde
  `skillgraph.domain.pack_loader`; `test_h7_promotion_module_exists`
  importa desde `skillgraph.governance.promotion`).

### Tests (sin bump adicional)

- +15 tests de contrato observable en
  `tests/test_h9_storage_context_controller_reads.py`:
  - 4 tests `list_claims_by_predicate` (contrato, aislamiento,
    no-match, columnas).
  - 3 tests `list_evidences_for_source` (contrato, no-match,
    columnas).
  - 6 tests `list_resource_refs_for_run` (kind=claim,
    kind=evidence, DISTINCT+ORDER, aislamiento run_id, no-events,
    kind inválido → ValidationError).
  - 2 tests de no-regresión por introspección
    (ContextController sin `_conn.execute`; uso de los 3 métodos
    públicos).

### Limitaciones NO ocultas

- Cobertura de `context_controller` sigue 82% (subir a 90%+
  requeriría +6..10 tests de ramas defensivas de las 3 APIs
  nuevas — **NO incluidos** en este release porque son tests
  de cobertura, no tests de refactor). Documentado en
  CURRENT.md 2026-09-24 06:46.

### Reversibilidad

`git revert f2cbb2f` revierte el refactor 2 completo.
`git revert 2751bc8` revierte el refactor 1.
Tests con asserts explícitos sobre los shims se reescribieron
en el mismo commit (no quedan referencias explícitas).

## [0.7.1] — 2026-09-24

**Tag**: `v0.7.1` (965446fadd1ca4cb11d8dfb5ddd8e56b090f1eb0).

**Resumen**: introduce 3 APIs atómicas nuevas en `Storage` para
escribir mutaciones de `node_executions` y su(s) evento(s)
correspondiente(s) en una sola transacción:

- `start_node_execution_atomically(event=..., ...)`:
  1 INSERT (RUNNING) + 1 evento (NodeScheduled).
- `complete_node_execution_atomically(event_completed=..., event_evidence=..., ...)`:
  1 UPDATE (SUCCEEDED) + 2 eventos (NodeCompleted + EvidenceProduced).
- `mark_node_failed_atomically(event=..., ...)`:
  1 UPDATE (FAILED) + 1 evento (NodeFailed).

Cada llamada ejecuta una transacción compartida
(BEGIN/COMMIT/ROLLBACK explícito sobre `_conn`). Si el INSERT del
evento falla, la mutación de estado rollbackea como una sola
unidad. Esto cierra las grietas atómicas B, C y D del documento
de caracterización de Plan B.

**Idempotencia**: `UNIQUE(event_id)` sobre `runtime_events` se
traduce a `IdempotencyError` via `try/except sqlite3.IntegrityError`.
Replay con el mismo `event_id` lanza `IdempotencyError`, nunca un
duplicado. Cumplimiento UAT-07.

**Importante**: las 3 APIs `*_atomically` corrigieron el **camino público**
de `Storage` (las firmas que invocaba el runtime antes del refactor),
pero el `with self._conn:` preexistente y los APIs NO-atómicas legacy
del Storage siguen sin rollbackear en `isolation_level=None`. Esta
grieta queda documentada como **LIMITACIÓN-7** (no resuelta en este
release; huérfana hasta v0.7.3 con un fix parcial sobre V4).

### Compatibilidad

- `629 passed, 1 skipped in 143.06s` (cifra del log
  `audits/cleanroom-evidence/ci-output-v0.7.1.txt`; skip en
  `test_cli_uat.py:363`, preexistente). Sin tests nuevos propios:
  este slice prepara el terreno para v0.7.2.
- 16/16 UAT PASS, 0 FAIL, 0 BLOCKED.
- 0 breaking changes: APIs legacy siguen vigentes.

### Evidencia

- `audits/release-v0.7.1-summary.md` (ya generado, link al bundle).
- `audits/cleanroom-evidence/skillgraph-v0.7.1-audit-bundle.tar.gz`.
- `audits/cleanroom-evidence/ci-output-v0.7.1.txt`.
- `audits/cleanroom-evidence/uat-audit-v0.7.1.txt`.

## [0.7.2] — 2026-09-24

**Tag**: `v0.7.2` (338fcc2eed72eb0a0f24f54532032461bded83f3).

**Resumen**: cierra el **defecto de integración** detectado por la
auditoría externa de `v0.7.1`. El release anterior ofreció 3 APIs
atómicas nuevas en `Storage` (`start/complete/fail *atomically`),
pero `RunController._execute_one` seguía invocando las APIs
no-atómicas y emitiendo eventos con llamadas separadas a
`EventLog.append`. Esto significaba que **el recorrido real del
runtime nunca obtuvo la garantía transaccional**.

`v0.7.2` sustituye los pares modificar-estado → emitir-evento en
`RunController` por las APIs atómicas. La garantía se acredita en
el camino público del runtime, no solo en el Storage aislado.

### `RunController._execute_one`

| Momento | Antes (v0.7.1) | Después (v0.7.2) |
|---|---|---|
| Start | `start_node_execution(...)` + `EventLog.append(NodeStarted)` | `start_node_execution_atomically(event=..., ...)` |
| Complete | `complete_node_execution(...)` + `EventLog.append(NodeCompleted)` + `EventLog.append(EvidenceProduced)` | `complete_node_execution_atomically(event_completed=..., event_evidence=..., ...)` |
| Fail | `mark_node_failed(...)` + `EventLog.append(NodeFailed)` | `mark_node_failed_atomically(event=..., ...)` |

### Tests nuevos

- `tests/test_h10_runcontroller_atomic_integration.py`: 3 tests con
  fault injection sobre `Storage._insert_event_in_tx`. Verifican que
  al fallar el INSERT del evento, la mutación de estado rollbackea.

### Compatibilidad

- `632 passed, 1 skipped in 134.17s` (cifra del log
  `audits/cleanroom-evidence/ci-output-v0.7.2.txt`; skip en
  `test_cli_uat.py:363`, preexistente). Aritmética aproximada del
  slice: 630 originales + 2-3 nuevos de integración
  (`test_h10_runcontroller_atomic_integration.py` aporta 3).
- 16/16 UAT PASS reproducible.
- 0 breaking changes: APIs públicas no cambian.

### Evidencia

- `audits/release-v0.7.2-summary.md` (ya generado, link al bundle).
- `audits/cleanroom-evidence/skillgraph-v0.7.2-audit-bundle.tar.gz`.
- `audits/cleanroom-evidence/ci-output-v0.7.2.txt`.
- `audits/cleanroom-evidence/uat-audit-v0.7.2.txt`.

### Lo que sigue abierto al cerrar v0.7.2

- **LIMITACIÓN-7**: el `with self._conn:` del Storage y las APIs
  no-atómicas legacy siguen sin rollbackear en
  `isolation_level=None`. v0.7.2 NO introduce un fix para esa
  grieta; solo acredita la integración del runtime con las APIs
  atómicas ya introducidas en v0.7.1.

## [0.8.0] — 2026-09-24 (sin tag, sin push; pendiente de autorización)

**Tag**: no asignado (espera autorización del operador).
**Código efectivo**: commit `528940297ec5ff981f0f59401fdb1e3f563236ab`
("feat(runtime): contexto de run accesible en Handoff (slice H9)").

**Resumen**: el `RunController` inyecta ahora el contexto del run
(tenant/project/run_id y metadatos vigentes) en cada `Handoff`
construido, persistido y recuperado vía `platform/storage`. El
contrato de la API pública de `RunController.__init__` se amplía
con un parámetro opcional `recipe_resolver: Callable[[str],
ContextRecipe | None] | None` (default `None`). Cuando se
proporciona, el resolver reemplaza el stub histórico
`default-empty-recipe/v1`; cuando es `None`, el comportamiento
previo se preserva (cambio backward-compatible).

**SemVer**: `feat` con cambio **compatible hacia atrás** (nuevo
parámetro opcional) → MINOR (v0.8.0).

**Resultado**: 6 tests nuevos en `tests/test_h9_context_in_run.py`
PASS. Batería completa previa: 652 passed. 16/16 UAT PASS, 0 FAIL.
Cobertura mantenida.

### Cambios funcionales

- `RunController.__init__` acepta `recipe_resolver` opcional.
- `RunController._execute_one` resuelve la receta de contexto del
  nodo vía el resolver y la inyecta en `Handoff.context`.
- `Storage` añade 1 método de lectura pura:
  `fetch_run_context(*, run_id)` (devuelve metadatos vigentes del
  run para poblar Handoff en relectura).
- `Handoff` ahora carga `run_context` automáticamente desde
  Storage cuando se recupera un handoff persistido.

### Tests

- 6 tests en `tests/test_h9_context_in_run.py` (parámetro opcional,
  propagación, recuperación, persistencia, default-empty-recipe
  preservado cuando no se inyecta resolver).

## [0.7.3] — 2026-09-24

**Tag**: `v0.7.3` (987be068c7f2b6d17aa6c209489906f94a542568).

**Código efectivo**: el tag apunta al commit `6a536ac` ("T19 cubre
rollback path del _atomic REAL"), que es el último commit con
cambios de código en el camino del fix. El SHA documental
987be068 puede incluir archivos posteriores con ajustes de SHA o
cierre de lagunas procedimentales; eso no afecta el código
ejecutado.

**Resumen**: cierra **un solo caso** de la grieta transaccional de
LIMITACIÓN-7: `Storage.record_trace()`. La función realizaba 1
INSERT en `outcome_traces` + N INSERTs en `outcome_trace_links`,
pero usaba `with self._tx()` que con `isolation_level=None` NO
abría transacción real. Un fallo durante el enlace dejaba un
trace huérfano en disco sin sus enlaces.

`v0.7.3` migra `record_trace()` a `Storage._atomic()`
(BEGIN/COMMIT/ROLLBACK explícitos), garantizando que un fallo a
mitad de las 1+N sentencias rollbackea el conjunto completo.
Esto es análogo al patrón ya usado por las APIs `*_atomically`
de v0.7.1 (que cubren `node_executions` + eventos).

El inventario del slice 1 también caracterizó otras 4 funciones
multi-statement de Storage (`_migrate`, `upsert_resource`,
`add_relation`, `register_promotion`). Todas se excluyeron del
alcance del fix por idempotencia natural o porque el fallo
impide la escritura — **v0.7.3 NO las modifica**.

### Cambios funcionales

- `Storage._atomic`: helper nuevo que usa `BEGIN`/`COMMIT`/`ROLLBACK`
  explícitos sobre `_conn` (alineado con el patrón de las APIs
  `*_atomically`). El rollback se ejecuta con `contextlib.suppress`
  para no enmascarar la excepción original.
- `Storage.record_trace`: cambia `with self._tx()` por
  `with self._atomic()` y actualiza su docstring para documentar
  la garantía transaccional y la referencia al slice V4.

### Tests

- `tests/test_h9_limitacion_7_slice1.py` con 4 tests (T15-T18):
  caracterización de V1, V2, V3, V5 y demostración del bug V4.
- `tests/test_h9_limitacion_7_slice1.py::TestT19AtomicRealRollbackPath`:
  cubre el path real de rollback del `_atomic`, no solo el override
  de los tests de caracterización. (Líneas 387-393 de storage.py
  antes en Missing; pasan a estar cubiertas con cobertura de
  storage.py subiendo de 95% a 96%.)

### Compatibilidad

**Resultados observados en el clon del SHA `6a536ac`** (no en
HEAD del main, que ya incluye el fix V6 en `a6bb5ab`):

- **Pytest contra el código del tag**: `637 passed, 1 skipped`
  en 122 s. (Skip preexistente: `tests/test_cli_uat.py:363`,
  blueprint no versionado.)
- **`bash scripts/ci.sh` completo**: EXIT 1. Aborta en el
  **gate 1 (ruff format --check)** sobre `tests/test_h9_limitacion_7_slice1.py`
  (archivo con T19, mezcla `with pytest.raises(...)` con `with s._atomic()...`).
  `ruff check src tests` reporta además 1 error **SIM117** en
  el mismo T19. Estado heredado del árbol del tag, no regresión
  del fix V4.
- **`python tests/uat_audit.py`** (modo lectura):
  `PASS=16 FAIL=0 BLOCKED=0`.
- 7 de 16 UATs se reejecutan contra el código del tag
  (UAT-05/08/09/10/11/15/16). Los 9 restantes son anclas estables
  cuyo PASS refleja commits previos.
- Cobertura `storage.py`: 96% (subió de 95% al añadir T19).
- 0 breaking changes: APIs públicas no cambian.

**Lo que este release NO certifica para el run de CI**:

El gate oficial `bash scripts/ci.sh` falla por formato/lint en
T19 en el código del tag. Esto es una característica del propio
árbol del tag. Si se requiere CI verde para una revisión posterior
que contenga V6 (commit `a6bb5ab`), hay que arreglar formato y
lint en un commit `chore(...)` separado, no modificar el SHA del
tag v0.7.3.

### Evidencia

- `audits/release-v0.7.3-summary.md` (entregado en este slice).
- `audits/cleanroom-evidence/skillgraph-v0.7.3-audit-bundle.tar.gz`
  (pendiente, ver matriz de cierre).
- `audits/cleanroom-evidence/ci-output-v0.7.3.txt` (pendiente).
- `audits/cleanroom-evidence/uat-audit-v0.7.3.txt` (pendiente).

### Lo que v0.7.3 NO cierra (sigue abierto)

- **LIMITACIÓN-7 V6**: `Storage.record_claim()` con `evidence_ids`
  pobladas presenta la misma clase de confirmación parcial que V4
  antes del fix. La corrección se ejecuta en commit posterior al
  tag (`a6bb5ab fix(storage): make record_claim evidence links
  atomic`), con su prueba focal T20
  (`tests/test_h9_limitacion_7_v6_record_claim.py`).
  Esta corrección NO está incluida en `v0.7.3` ni será parte de
  ese tag. La version que la incluya se decidirá después del
  cierre del slice documental.

- **`workflow_runs` ↔ `RunCreated` / `RunCompleted`**: las
  mutaciones de `workflow_runs` siguen usando APIs no-atómicas.
  Fuera del alcance de LIMITACIÓN-7; pertenece al Plan C.

- **APIs legacy no-atómicas de Storage** (`upsert_resource`,
  `start_node_execution` sin sufijo, `complete_node_execution`
  sin sufijo, `mark_node_failed` sin sufijo): siguen sin
  rollbackear en `isolation_level=None`. Cualquier llamada a esas
  APIs desde un caller distinto al runtime verificado en v0.7.2
  es responsabilidad del caller asegurar atomicidad externa.

## [0.6.0] — 2026-09-23

**Resumen**: cierra los dos únicos gaps restantes del blueprint v1.
**H6 multiprosito** aníade declaracion de tipos extensibles via Domain
Pack (Character/StoryArc como ejemplo narrativo) SIN tocar el nucleo.
**H7 promocion entre bases** aníade outbox persistente con aplicacion
idempotente y reconciliacion tras interrupcion.

**Resultado neto**: 16/16 UAT PASS, 0 FAIL, 0 BLOCKED. El blueprint
queda COMPLETO al 100% segun contrato.

Sin cambios en la API publica existente. Registry/bricks/parser
intactos (0 LoC modificados). Storage.py solo EXTENSION (anade tabla
promotion_outbox + 6 metodos; nada existente modificado).

### Features (MINOR bump)

- `1722fa5` **feat(h6): multiprosito - Domain Pack declara tipos extensibles**.
  - Modulo nuevo `src/skillgraph/pack_loader.py` (215 LoC):
    - `declare_types_from_pack(pack_text)`: parsea un Domain Pack
      Markdown+frontmatter y emite tipos en RuntimeType registry.
      **NO ejecuta codigo del pack**: la seguridad viene del schema
      declarativo (required + fields + refs), no de imports dinamicos.
    - `validate_instance_against_registry(instance)`: valida una
      instancia contra los tipos declarados del Domain Pack.
    - `_make_schema_validator()`: helper que construye un
      SpecValidator desde un schema declarativo.
  - Fixture `tests/fixtures/packs/narrative-core.md`: Domain Pack
    narrativo con `Character` (name, archetype, backstory, relations)
    y `StoryArc` (title, premise, acts, characters).
  - Proteccion contra shadowing:
    - Tipos core (`DecisionNode`, `ActionNode`, `DomainPack`) no se
      pueden redefinir desde un pack.
    - Namespaces reservados (`core`, `skillgraph`) se rechazan.
  - **Kernel intacto**: 0 LoC modificados en `registry.py`/`bricks.py`/`parser.py`.
- `95a0ca9` **feat(h7): promocion entre bases - outbox + reconciliacion idempotente**.
  - Modulo nuevo `src/skillgraph/promotion.py` (160 LoC):
    - `submit_proposal()`: inserta propuesta en outbox origen con
      `idempotency_key`. Duplicado -> `IdentityConflictError`.
    - `apply_proposal(proposal_id, apply_fn)`: transiciona
      PENDING/IN_PROGRESS -> PUBLISHED. **Idempotente**: si ya
      PUBLISHED, NO reaplica. Si FAILED, NO reintenta (segun contrato:
      requiere inspeccion manual).
    - `reconcile_pending()`: procesa TODAS las propuestas en
      PENDING/IN_PROGRESS. Aplica idempotencia. Publicadas y fallidas
      se ignoran.
    - `_compute_idempotency_key()`: combinacion deterministica de
      `project_id + reference_signature`. Rechaza inputs vacios.
  - Storage extension (`src/skillgraph/storage.py`, +146 LoC, 0 modificados):
    - Schema: tabla `promotion_outbox` con
      `proposal_id` PK, `idempotency_key` UNIQUE, `status` CHECK
      IN (`PENDING`,`IN_PROGRESS`,`PUBLISHED`,`FAILED`), `attempts`,
      timestamps, indice por status.
    - 6 metodos anadidos: `register_promotion`, `get_promotion`,
      `list_pending_promotions`, `mark_promotion_in_progress`,
      `mark_promotion_published`, `mark_promotion_failed`.
  - Patron del blueprint §9 (Outbox + Reconciliacion):
    1. Resultado persistido en origen (`register_promotion`).
    2. Mensaje de outbox (`promotion_outbox` row).
    3. Aplicacion idempotente en destino (`apply_fn` + `idempotency_key`).
    4. Confirmacion (`mark_promotion_published`).
    5. Reconciliacion si se interrumpe el proceso (`reconcile_pending`).
- `92cff48` **feat(uat)**: UAT-12 y UAT-13 ahora PASS con evidencia real.
  - `tests/uat-evidence/UAT-12.json` migrado BLOCKED → PASS:
    revision=95a0ca9, criteria_observed con 12 tests de
    test_h6_multiproposito.py, design_decisions (no_execution,
    schema_validator, shadowing_protection, explicit_imports).
  - `tests/uat-evidence/UAT-13.json` migrado BLOCKED → PASS:
    revision=95a0ca9, criteria_observed con 16 tests de
    test_h7_promocion.py incluyendo el CASO CRITICO
    `reconcile_after_interruption_completes_pending` (IN_PROGRESS
    dejado por crash → reconciliacion completa sin duplicar,
    apply_fn llamado 1 sola vez por propuesta).
  - `tests/test_uat_blocked.py` invertido: antes validaba que UAT-12/13
    siguieran BLOCKED con razon honesta. Ahora valida que UAT-12/13
    estan PASS, que las evidencias JSON dicen PASS con SHA real, y que
    los tests reales (`test_h6_*` / `test_h7_*`) corren verde.
    Contrato invertido: este modulo es el "gap test" que detecta si
    alguien revierte H6 o H7 sin actualizar la evidencia.
    6 tests: 2 evidencias PASS, 2 ejecutan suites reales, 2 modulos
    existen con API esperada.

### Tests anadidos (sin bump)

- `1722fa5` **test(h6)**: 12 tests focalizados en pack_loader.py.
  - `test_pack_loader_declares_types_from_narrative_pack`: pack
    narrativo declara Character/StoryArc desde YAML.
  - `test_pack_loader_valid_character_passes` /
    `test_pack_loader_valid_storyarc_passes`: instancias validas
    se aceptan (name, archetype, backstory, relations).
  - `test_pack_loader_character_missing_archetype_fails` /
    `test_pack_loader_storyarc_missing_premise_fails`: campo
    requerido ausente → error de validacion.
  - `test_pack_loader_unknown_kind_raises`: kind desconocido →
    `UnknownKindError`.
  - `test_pack_loader_cannot_shadow_core_type`: 'Character' no
    puede redefinir DecisionNode/ActionNode/DomainPack.
  - `test_pack_loader_cannot_use_reserved_namespace`: namespaces
    'core'/'skillgraph' rechazados.
  - `test_pack_loader_rejects_non_domain_pack`: doc sin
    frontmatter Domain Pack → error.
  - `test_pack_loader_field_type_mismatch_fails`: tipo de campo
    invalido → error.
  - `test_pack_loader_list_of_field_validates_elements`: list_of
    valida elementos internos.
  - `test_pack_loader_does_not_touch_kernel_modules`: pack_loader
    NO importa registry/bricks/parser (test de regresion).
- `95a0ca9` **test(h7)**: 16 tests focalizados en promotion.py +
  storage outbox.
  - `TestPromotionIdempotencyKey` (3): combinacion project+ref
    deterministica, inputs distintos producen keys distintas,
    inputs vacios rechazados.
  - `TestSubmitProposal` (2): submit crea PENDING, duplicate con
    misma idempotency_key → `IdentityConflictError`.
  - `TestApplyProposal` (6): apply exitoso→PUBLISHED, apply
    failed→FAILED, excepcion→FAILED, idempotencia sobre PUBLISHED
    (counter apply_fn no incrementa), FAILED no se reintenta,
    proposal_id inexistente → KeyError.
  - `TestReconcilePending` (5): empty→empty, procesa multiples
    PENDING, **CASO CRITICO after-interruption** (IN_PROGRESS dejado
    por crash → completa sin duplicar), no duplica PUBLISHED,
    mezcla PENDING+IN_PROGRESS+FAILED → cada uno se trata
    segun corresponde.
- `92cff48` **test(uat)**: 6 tests en `tests/test_uat_blocked.py`
  (inversion del contrato, ver feat anterior).

### Estado verificable al tag

- **HEAD**: `92cff48` (post-commits h6+h7+uat).
- **Tests**: 405 passed en 121s (373 → 405, delta +32 tests
  H6+H7+gap-invertidos).
- **UATs**: **16/16 PASS, 0 FAIL, 0 BLOCKED** — primera vez en la
  historia del proyecto.
- **`scripts/ci.sh`**: OK.
- **ruff format+check**: limpios.
- **Audit CLI**: `python tests/uat_audit.py` reporta 16/16 PASS.

### Limitaciones y deudas conocidas

- **H6/H7 sin CLI hooks publicos**: `sg pack load` y
  `sg promotion submit/list/reconcile` NO son comandos CLI. El
  contrato del blueprint es la API Python (pack_loader.declare_*,
  promotion.submit/apply/reconcile). La interfaz CLI es una mejora
  diferible, no un gap funcional.
- **Sin migracion de evidencias legacy**: las evidencias que vivian
  con status=BLOCKED y revision=`cb7e3482` (v0.3.0) se migraron
  sobreescribiendo el archivo a status=PASS con la revision real del
  commit que implemento la feature. Si alguien quiere preservar el
  historial pre-implementacion, mirar git log de tests/uat-evidence/.

## [0.5.0] — 2026-09-23

**Resumen**: añade CLI propio al módulo `tests/uat_audit.py`. Antes
ejecutaba los 16 UATs y sobreescribía la evidencia persistida por
defecto (footgun crítico). Ahora es read-only por defecto; el modo
write es opt-in con flags explícitos y protección contra pisado de
evidencia válida de UATs stub.

Sin cambios en la API pública de SkillGraph. Sin cambios en código
de producción (`src/skillgraph/`).

### Features (MINOR bump)

- `233431b` **feat(uat)**: CLI safety en `tests/uat_audit.py`.
  - **Default read-only**: `python tests/uat_audit.py` ahora LEE la
    evidencia persistida y la reporta sin ejecutar nada. Cierra el
    footgun documentado en v0.4.1 CHANGELOG.
  - **`--write`**: ejecuta los UATs y SOBREESCRIBE la evidencia. Solo
    para UATs no-stub (los stubs UAT-08/09/12/13 son heredados y
    delegan en `uats_blocked_gap`; su evidencia real vive en
    `test_h4_expansion_cli.py` / `test_uat_blocked.py`).
  - **`--write --yes`**: confirma la operación sobre UATs stub
    (mensaje explícito + exit 3 si se omite `--yes`).
  - **`--dry-run`**: ejecuta los UATs sin persistir evidencia (útil
    para debug).
  - **Subset selection**: `uat_audit.py UAT-08 UAT-09` ejecuta solo
    los UATs nombrados.
  - **`--help`**: imprime uso.
  - **Exit codes**: 0 OK, 2 UAT desconocido, 3 stub sin `--yes`.
  - Refactor: extrae `_run_one`, `_report`, `_summary`,
    `_read_existing`, `_build_parser` para DRY.

### Tests añadidos (sin bump)

- `607d859` **test(uat)**: 5 tests para el nuevo CLI.
  - `test_main_default_is_readonly`: modo lectura no escribe nada.
  - `test_main_write_unknown_uat_returns_2`: exit code 2 en UAT
    desconocido.
  - `test_main_write_stub_without_yes_returns_3`: exit code 3 Y la
    evidencia preexistente con `revision: "must-survive"` queda
    intacta (verifica que NO se pisa).
  - `test_main_dry_run_does_not_write`: `--dry-run` no persiste.
  - `test_main_help_exits_zero`: `--help` sale rc=0 con mensaje
    que contiene `--write`.

### Estado verificable al tag

- **HEAD pre-tag**: `607d859`.
- **Tests**: 373 passed en 82s (368 → 373, delta +5 tests CLI).
- **UATs**: 14/16 PASS, 2 BLOCKED honestos (sin cambio).
- **`scripts/ci.sh`**: OK.
- **ruff format+check**: limpios.
- **Footgun verificado**: ejecutar `python tests/uat_audit.py` ya NO
  modifica el working tree (verificado con `git status` antes/después).

### Limitaciones y deudas conocidas (sin cambio desde v0.4.1)

- UAT-12 H6 multipropósito: BLOCKED.
- UAT-13 H7 promoción: BLOCKED.
- H4 slice-4 deferred.
- `paths.py` rama Windows: no testeable en CI Linux.

## [0.4.1] — 2026-09-23

**Resumen**: dos correcciones de portabilidad y trazabilidad del
módulo `tests/uat_audit.py`. Sin cambios de comportamiento observable
ni en la API pública.

### Fixes (PATCH bump)

- `7b81df7` **fix(tests)**: UAT evidence usa SHA real de HEAD.
  - Antes: `revision: "HEAD"` literal en evidencia de UAT-08/09.
  - Ahora: helper `_git_rev_head()` que ejecuta `git rev-parse HEAD`
    en el repo de evidencia y captura el SHA real.
  - Justificación: una evidencia de auditoría que no contiene el SHA
    real no es auditable. Mejora la verificabilidad, no el comportamiento.
- `edb19b0` **fix(uat)**: `REPO_ROOT` se deriva de `__file__`.
  - Antes: `Path("/var/mnt/DiscoChino2-fast/...")` hardcodeado,
    rompía el módulo al clonarse en otra máquina o ruta.
  - Ahora: `Path(__file__).resolve().parent.parent` — funciona en
    cualquier checkout sin editar.
  - Verificado: módulo importa OK desde `test_uat_blocked.py` y
    `test_uat_audit.py`, y resuelve a la misma raíz que el path
    hardcodeado en este entorno.

### Estado verificable al tag

- **HEAD pre-tag**: `edb19b0`.
- **Tests**: 368 passed en 63s (sin delta vs v0.4.0).
- **UATs**: 14/16 PASS, 2 BLOCKED honestos (sin cambio).
- **`scripts/ci.sh`**: OK.
- **ruff format+check**: limpios.

### Limitaciones y deudas conocidas (sin cambio desde v0.4.0)

- UAT-12 H6 multipropósito: BLOCKED.
- UAT-13 H7 promoción: BLOCKED.
- H4 slice-4 deferred.
- `paths.py` rama Windows: no testeable en CI Linux.
- **NUEVA detectada en sesión**: el `main()` de `tests/uat_audit.py`
  es destructivo por defecto — al ejecutarlo sin args pisa toda la
  evidencia existente en `tests/uat-evidence/*.json` con `BLOCKED`.
  No se ha arreglado en este PATCH por estar fuera del scope
  (cambia contrato del script, no portabilidad).

## [0.4.0] — 2026-09-23

**Resumen**: cierra el gap declarado en `specs/h4-slice-3.md` limitación 3.
`expansion apply` ahora persiste la propuesta y crea marker `.applied`,
haciendo que `list --stage APPLIED` funcione (antes retornaba vacío).
`expansion show` ahora incluye el campo `stage` en el payload JSON.

Compatibilidad hacia atrás mantenida: ningún cambio en códigos de salida,
firmas de comandos, ni en el formato del plan persistido.

### Features (MINOR bump)

- `162a708` **feat(h4-slice-3)**: APPLIED marker + `show.stage` field.
  - `cmd_expansion_apply` ahora persiste la propuesta en
    `expansion_proposals/<id>.json` (si no existe, mismo patrón que
    `cmd_expansion_propose`) y crea marker adyacente `<id>.json.applied`
    con timestamp UTC y `applied_by: "expansion-apply-cli"`.
  - `cmd_expansion_list` y `cmd_expansion_show` leen markers:
    precedencia `ARCHIVED > APPLIED > REJECTED > PROPOSED`.
  - `cmd_expansion_show` añade `"stage": "..."` al payload JSON.
  - Refactor: extrae `_infer_proposal_stage()` y
    `_collect_rejection_ids()` para evitar duplicación entre list y show.

### Estado verificable al tag

- **HEAD**: `162a708` (pre-tag).
- **Tests**: 368 passed en 117s (362 → 368, delta +6 tests focales).
- **Cobertura**: sin cambio material (cli.py 31% in-process; tests
  reales E2E).
- **UATs**: 14/16 PASS, 2 BLOCKED honestos (sin cambio).
- **`scripts/ci.sh`**: OK.
- **ruff format+check**: limpios.

### Limitaciones y deudas conocidas (sin cambio desde v0.3.0)

- UAT-12 H6 multipropósito: BLOCKED.
- UAT-13 H7 promoción: BLOCKED.
- H4 slice-4 deferred.

## [0.3.0] — 2026-09-23

**Resumen**: primera release taggeada. H0-H5 (excepto H6 y H7)
completados con criterios de aceptación verificados. 14/16 UAT PASS,
2 BLOCKED honestos por falta de spec del operador.

### Features (MINOR bump)

#### H4 — Expansión controlada

- `6f93eb2` **feat(h4)**: Expansion controlada (DISCOVER → APPLY)
  cierra UAT-08/09.
- `bd95d29` **feat(h4-cli)**: expansion propose/apply/validate/rejections
  + E2E para UAT-08/09.
- `3b307f3` **feat(h4-slice-3)**: policy engine P1..P5 + EVALUATE + CLI
  list/show/archive.
- `b7b2d5e` **feat(h4)**: DecisionNode outcomes + max_visits self-loops
  (+7 tests).

Criterio legal HITOS.md H4: "Añadir una investigación imprevista a una
ejecución sin alterar el resultado de nodos anteriores."
- UAT-08 PASS (`tests/uat-evidence/UAT-08.json`): apply incorpora
  únicamente el cambio solicitado; nodos originales intactos.
- UAT-09 PASS (`tests/uat-evidence/UAT-09.json`): propuesta con
  capability no registrada es rechazada con rc=10 y evidencia JSON
  persistida en `expansion_rejections/`.

Limitaciones documentadas (`specs/h4-audit-penal.md`):
- E2E es `representative` (Storage SQLite local), no
  `acceptance_aligned` (sin stress concurrente, sin crash recovery
  verificado en kill-9). Refinamiento pendiente para slice-4.

#### H5 — Adopción de skills

- `26ac401` **feat(h5)**: skill_import (UAT-11 BLOCKED→PASS) +
  `skill_importer` + `cmd pack import`.

Criterio legal HITOS.md H5: "Adoptar una skill real y conservar una
referencia verificable a sus instrucciones originales."
- UAT-11 PASS (`tests/uat-evidence/UAT-11.json`): `pack_import` rc=0,
  `structured_ok=True`, `script_ignored=True`, `scripts_detected=True`.

Decisión documentada (`specs/h5-source-conservation-decision.md`):
- Conservación por referencia (path+content_hash), NO duplicación de
  bytes. Justificado por blueprint §10 §5-6.

#### Otros feats

- `d72bbff` **feat(uat)**: UAT-16 BLOCKED→PASS (handoff_json persiste
  tras revision change).
- `b06cc15` **feat(h3-s1)**: Knowledge ADT + Storage delta.
- `4d8e80c` **feat(ci)**: `scripts/ci.sh` como gate único + pairwise
  import.
- `3bc66d9` **feat(H2)**: tests subprocess CLI run + resume-or-start
  (UAT-04/06/07 E2E).
- `007db8d` **feat(cli)**: añadir `__main__.py` para `python -m
  skillgraph`.
- `a3f7950` **feat(etapa2/S7)**: DSL tipado + PlanBuilder funcional +
  loader Markdown.
- `e763102` **feat(e2-s4+s5)**: WorkflowPlan + RunController +
  ejecución recuperable.
- `92a5174` **feat(e2-s3)**: AgentAdapter + FakeAgentAdapter +
  RecordingAdapter.
- `64bc05d` **feat(e2-s2)**: Handoff materializado con serialización
  estable y SHA-256.
- `92929a9` **feat(e2-s1)**: runtime append-only + EventLog con
  idempotencia por UNIQUE.
- `fb0e56a` **feat(e1)**: CLI real + catálogo + UAT-01..03 PASS.
- `15957d7` **feat(s1)**: almacenamiento SQLite con WAL, aislamiento y
  latencia.
- `0a92c84` **feat(s0)**: brick mínimo Markdown+YAML con parser,
  registro y validación.

### Fixes (PATCH bump)

- `ff433aa` **fix(types)**: SourceKind incluye `skill_pack` y Source
  valida kind en `__post_init__`. Cierra bug silencioso donde
  `from __future__ import annotations` desactivaba Literal-check.
- `e69a8e4` **fix(uat)**: UAT-10 predicados válidos + chequeo
  `seed_rc` y `stale_listed`.
- `bdd196f` **fix(cli)**: UAT-06 max_iterations respeta el límite + 4
  tests honestos.

### Refactors

- `1039171` **refactor + test(paths)**: añadir tests + refactor para
  que la rama nt sea testeable.

### Tests añadidos (sin bump)

- `0e96495` **test(parser)**: 12 tests ramas de error (coverage
  77%→100%).
- `b6ca7e1` **test(plan-loader)**: 13 tests load_plan_file + error
  branches (coverage 48%→100%, dato heredado 69% obsoleto).
- `629be65` **test(recipe)**: 22 tests `__post_init__` + from_dict
  (coverage 73%→100%).
- `7c3f3f4` **test(uat)**: gap coverage UAT en CI — 5 wrappers
  pytest + 2 honest blockers.

### Specs (sin bump)

- `7233fac` spec(h4-audit-penal): cruce H4 slices 1+2 vs blueprint
  literal.
- `92d70e2` spec(h5-audit-penal): cruce H5 skill_import vs blueprint
  literal.
- `81fbb0e` spec(h4-slice-3): propuesta storage persistente + EVALUATE
  + policy engine.
- `2d01a06` spec(uat-coverage-gap): audita que UATs se validan
  automáticamente en CI.

### Estado verificable al tag

- **HEAD**: `076f6e9` (pre-tag) → `v0.3.0` (post-tag).
- **Tests**: 362 passed en 54s (315→362, delta +47 en ciclos de
  stewardship).
- **Cobertura**: 77% total. Módulos críticos `parser.py`, `plan_loader.py`,
  `recipe.py`: 100%. Módulos runtime: 88-100%. `cli.py`: 31% en
  pytest-cov (cobertura real mayor vía tests subprocess E2E no
  contables por cobertura in-process).
- **UATs**: 14/16 PASS, 2 BLOCKED honestos.
- **`scripts/ci.sh`**: OK (format + lint + pytest, replicable por
  cualquier runner externo).
- **ruff format+check**: limpios.

### Limitaciones y deudas conocidas

- **UAT-12 (H6 multipropósito)**: BLOCKED. Requiere spec del operador
  para `Character/StoryArc`.
- **UAT-13 (H7 promoción entre bases)**: BLOCKED. Requiere spec del
  operador.
- **H4 slice-4** (deferido por decisión explícita en
  `specs/h4-slice-3.md`): sin migración SQLite, sin gating de
  `auto_signed` via evaluation_result.
- **`paths.py` rama Windows**: no ejercitable en CI Linux
  (`LOCALAPPDATA/USERPROFILE`).
- **`recipes.runtime.dispositivos externos`**: tiktoken solo si H4+
  exige Adapter real.

### Antiobjetivos respetados

- No se introdujo base de grafos especializada.
- No se introdujo scheduler distribuido.
- No se introdujo sistema de agentes permanentes sin requisito
  observado.

## Comparativa con releases anteriores

Esta es la **primera release taggeada** del proyecto.
El historial completo de commits previos forma parte del cuerpo
desarrollado hacia esta release.

[0.3.0]: #030--2026-09-23

## [0.8.1] — 2026-09-24 (PATCH, refactor)

**Tag**: `v0.8.1` (`ab7b5171aec5524320c67e44ad511ae78b70a7d1`).

**Código efectivo**: commit `ab7b517` ("refactor(runtime): helper
_fail_node_with(exc=...) en RunController").

**Resumen**: el método `_execute_one` repite el patrón
`except X as exc: self._mark_node_failed(... error=f"{type(exc).__name__}: {exc}")`
en dos ramas (compilación de handoff y adaptador). Esta versión
centraliza ese formato en un helper privado `_fail_node_with(exc=...)`
que delega en `_mark_node_failed`. La tercera rama (outcome no
declarado) usa una firma distinta (incluye `outcome=`) y se conserva
como llamada directa.

**SemVer**: refactor puro → PATCH (v0.8.1). Sin cambio de
comportamiento observable.

**Resultado**: 652/652 tests PASS; 16/16 UAT PASS, 0 FAIL. Ruff
limpio. Cobertura mantenida.

### Cambios funcionales

Ninguno.

### Refactor (sin bump adicional)

- `RunController._fail_node_with(*, tenant_id, project_id, run_id,
  node_execution_id, node_name, exc)` añadido como helper privado.
- `RunController._execute_one`: 2 ramas `except` pasan a usar
  `_fail_node_with(exc=exc)` en vez de construir el string de error
  y llamar a `_mark_node_failed` directamente. La rama de outcome
  no declarado queda igual.

## [Sin bump] — 2026-09-24 (refactor interno)

**Tag**: ninguno. **Código efectivo**: commit `ea54021`
("refactor(runtime): helpers _transition_run_state_with_event y
_is_budget_exhausted").

**Resumen**: deuda técnica pendiente del refactor previo
(`v0.8.1`). `reconcile_run` tenía 122 LoC y tres ramas con el patrón
`EventBuilder(...).run_completed(...) + transition_run_state_atomically`,
más un bloque de 14 LoC para detectar budget de visitas agotado.
Esta versión extrae dos helpers privados en `RunController`:

- `_transition_run_state_with_event(*, tenant_id, project_id, run_id,
  state, current_node, at=None)`: construye el `RunCompleted` y
  llama a `transition_run_state_atomically` en una sola TX.
  Reemplaza las 3 ramas de terminación del run.
- `_is_budget_exhausted(plan, tenant_id, project_id, run_id,
  prev_current)`: detecta H4 (self-loop + max_visits + ejecuciones
  acumuladas >= max_visits).

**SemVer**: refactor puro (sin cambio de contrato público, sin fix,
sin feat). Regla "`refactor` → sin bump de versión" del CHANGELOG.
No se publica tag.

**Resultado**: 659/659 tests PASS (+4 nuevos sobre el helper).
Ruff limpio. Cobertura `runcontroller.py`: 84% → 95%
(umbral ≥90% AGENTS.md core). `reconcile_run`: 122 → 100 LoC.

### Continuación del refactor (aee5cd5)

Misma rama, sin bump adicional. Extrae dos helpers privados
adicionales en `RunController`:

- `_open_node_execution(*, tenant_id, project_id, run_id, node_name,
  attempt) -> tuple[EventBuilder, str]`: emite `NodeScheduled` y crea
  la `NodeExecution` RUNNING atómica. Devuelve `(events,
  node_execution_id)`.
- `_finalize_node_success(*, events, run_id, node_execution_id,
  result, context_hash)`: emite `NodeCompleted` + `EvidenceProduced`
  y delega el UPDATE a SUCCEEDED atómico.
- `_fail_node_with` ahora retorna `bool` (`False`); permite
  `return self._fail_node_with(...)` sin repetir el literal.

`_execute_one` colapsa 162 → 124 LoC. El orquestador queda como
secuencia explícita: bootstrap → compilar handoff → invocar adapter →
validar outcome → cerrar. Cobertura mantenida 95%.


## [0.9.0] — 2026-09-24 (MINOR, cancel + refactors)

**Tag**: `v0.9.0` (`a4d749e9fefad551e4406aa7305e32aac224df08`).

**Resumen**: S1 del roadmap Etapa 7 (presupuestos y cancelación):
el operador puede detener un Run en curso sin esperar al reconcile
completo. Nueva API `RunController.cancel_run` + nuevo subcomando
CLI `sg runs cancel <project> <run-id>`. Consolidación de los
refactors acumulados sobre `RunController` (helpers privados
para extraer las ramas duplicadas de terminación, transición de
estado y bootstrap/ejecución de nodos).

### Cambios funcionales (MINOR)

- **`RunController.cancel_run(*, tenant_id, project_id, run_id)`**:
  transiciona el Run a `CANCELLED` y emite `RunCompleted` en una
  sola TX (reutiliza `_transition_run_state_with_event`).
  - Run no existe -> `NotFoundError` (delegado en `Storage.load_run`).
  - Run ya terminal -> `ValidationError` (no idempotente).
  - NodeExecutions RUNNING se quedan: la cancelación es a nivel
    de Run, no de nodo. El siguiente `reconcile_run` no las
    re-ejecuta (test `test_reconcile_after_cancel_is_noop`).
- **CLI `sg runs cancel <project> <run-id>`**: subcomando nuevo
  bajo `runs` (paralelo a `run`). Exit code 0 + `state=CANCELLED`
  en stdout. Errores tipados -> `EXIT_DOMAIN` (10).

### Refactors acumulados (sin bump adicional)

Consolidación de la deuda técnica detectada sobre `RunController`
en `v0.8.1`:

- `RunController._transition_run_state_with_event(*, ...)`:
  helper que centraliza las 3 ramas de terminación del Run
  (FAILED por nodo, FAILED por budget exhausted, COMPLETED
  normal, ahora también CANCELLED).
- `RunController._is_budget_exhausted(plan, ...)`:
  detección de H4 (self-loop + max_visits + ejecuciones
  acumuladas >= max_visits).
- `RunController._open_node_execution(*, ...)`:
  bootstrap del nodo: emite `NodeScheduled` y crea la
  NodeExecution RUNNING atómica.
- `RunController._finalize_node_success(*, ...)`:
  cierre exitoso: emite `NodeCompleted` + `EvidenceProduced`
  y delega el UPDATE a SUCCEEDED atómico.
- `RunController._fail_node_with(*, exc=...) -> bool`:
  devuelve `False` para permitir
  `return self._fail_node_with(...)` sin literal.
- `_execute_one`: 162 → 124 LoC.
- `reconcile_run`: 122 → 100 LoC.

### Tests

- 5 tests unitarios `tests/test_runcontroller.py::TestCancelRun`:
  estado persistido, evento emitido, idempotencia, run terminal
  rechazado, reconcile post-cancel no-op, run desconocido.
- 2 tests subprocess `tests/test_cli_runs_cancel.py`:
  cancel vía CLI exit code 0 + persistencia + evento; cancel
  de run inexistente -> exit code != 0.
- 4 tests del helper `_is_budget_exhausted`
  (`tests/test_h4_cycles_and_decision.py::TestIsBudgetExhaustedHelper`).
- UAT-08/09 regenerados sobre `a4d749e`.

### Resultado

- **Batería completa**: 666 passed (de 652 en v0.8.0).
- **Ruff**: limpio.
- **Cobertura `runcontroller.py`**: 95% (umbral ≥90% AGENTS.md core).

### SemVer

`feat` (capacidad observable nueva: cancel programático y CLI) →
**MINOR** → `v0.9.0`. Los refactors van consolidados en la
misma release con la regla "`refactor` → sin bump" relajada
porque la `feat` ya justifica MINOR.

## [0.10.0] — 2026-09-24 (MINOR, list + show runs)

**Tag**: `v0.10.0` (`c6963f072d6b6e51ab569e396de688633aed2fb2`).

**Resumen**: S2 del roadmap Etapa 7 (gestion del ciclo de vida de
Runs): complementa el S1 (`v0.9.0`, cancel_run) con inspeccion
read-only. El operador ahora puede listar Runs existentes con
`sg runs list` y ver el snapshot de un Run concreto con
`sg runs show`, sin abrir SQLite directamente.

### Cambios funcionales (MINOR)

- **`Storage.list_runs(*, tenant_id, project_id, state=None, limit=50)`**:
  SELECT con filtro opcional por estado, ordenado por `rowid DESC`
  (mas reciente primero; monotono, independiente de la resolucion
  de 1 segundo de `datetime('now')` en SQLite).
- **`Storage.get_run(*, tenant_id, project_id, run_id)`**:
  fila cruda de un Run; `NotFoundError` si no existe.
- **`RunController.list_runs(...)`**: tupla inmutable de
  `RunSnapshot` ordenados por mas reciente primero. Filtra por
  estado opcional.
- **`RunController.show_run(...)`**: snapshot de un Run por id;
  `NotFoundError` si no existe. Delega en `Storage.get_run`.
- **`RunController._count_events(...)`**: helper privado read-only
  para contar eventos de un Run (usado por list/show).
- **CLI `sg runs list <project> [--state S] [--limit N]`**:
  salida CSV-like con columnas estables (run_id, state,
  current_node, executed, events). '(sin runs)' si vacio.
- **CLI `sg runs show <project> <run-id>`**: salida key=value
  (run_id, state, current_node, executed_nodes, events_emitted).
  Parseable con `awk`/`cut`.
- **`_open_project_storage(args)`**: helper compartido por
  `cmd_runs_list`/`show`/`cancel` (DRY: resolver proyecto +
  abrir Storage en una sola funcion).

### Tests

- 6 tests unitarios `tests/test_runcontroller.py::TestListAndShowRun`:
  vacio, orden, limit, filtro por estado, snapshot, NotFoundError.
- 3 tests subprocess CLI `tests/test_cli_runs_inspect.py`:
  list vacio, list orden, show snapshot.
- Archivo renombrado: `test_cli_runs_cancel.py` ->
  `test_cli_runs_inspect.py` (cubre cancel + list + show).
- UAT-08/09 regenerados sobre `c6963f0`.

### Resultado

- **Bateria completa**: 675 passed (de 666 en v0.9.0, +9 nuevos).
- **Ruff**: limpio.
- **Cobertura `runcontroller.py`**: 95% mantenida.

### SemVer

`feat(list_runs) + feat(show_run) + feat(sg runs list) +
feat(sg runs show)` -> **MINOR** -> `v0.10.0`. Consolidacion
inmediata con v0.9.0 porque `list`/`show` son el complemento
natural de `cancel`: sin ellos, el operador no puede saber
que Run cancelar.

## [0.11.0] — 2026-09-24 (MINOR, logs run)

**Tag**: `v0.11.0` (pendiente; commit del slice en esta entrada).

**Resumen**: S3 del roadmap Etapa 7. Cierra el triangulo de
inspeccion read-only de Runs: tras listar (`v0.10.0`) y snapshotear
(`v0.10.0`), el operador puede ahora examinar el timeline completo
de eventos de un Run con `sg runs logs`. Read-only, sin emitir
eventos.

### Cambios funcionales (MINOR)

- **`Storage.list_events_for_run(*, tenant_id, project_id, run_id)`**:
  SELECT ordenado por `sequence ASC` (orden causal) filtrado por
  run_id usando el indice `events_by_run` ya existente. Devuelve
  tupla de tuplas crudas `(sequence, event_id, kind, timestamp,
  payload_json)`; el parsing a `RuntimeEvent` vive en `RunController`
  para mantener Storage libre de tipos del bounded context `runtime`.
- **`RuntimeEventLog`**: nuevo dataclass frozen
  `(sequence: int, event: RuntimeEvent)` que expone `sequence` al
  exterior sin modificar el contrato del evento runtime (sequence
  es meta-informacion de almacenamiento, no del evento en si).
- **`RunController.logs_run(*, tenant_id, project_id, run_id)`**:
  fail-fast con `get_run` (NotFoundError si no existe). Itera
  `_row_to_event_dict` sobre cada row y lo envuelve en
  `RuntimeEventLog(sequence, event)`. No emite eventos.
- **CLI `sg runs logs <project> <run-id> [--limit N]`**: salida
  CSV-like con cabecera (`seq event_kind timestamp payload`) y una
  linea por evento con resumen del payload (primer nivel
  `clave=valor` truncado a 40 chars). '--limit N' corta por cabeza
  despues de cargar todo (util para depurar los primeros N eventos
  de Runs largos). '(sin eventos)' si vacio.
- **`_route_runs`**: nueva rama `logs -> cmd_runs_logs`.
- **Reuso**: `cmd_runs_logs` delega en `_open_project_storage`
  (mismo helper DRY que list/show/cancel).

### Tests

- 3 tests unitarios `tests/test_runcontroller.py::TestLogsRun`:
  NotFoundError, RunCreated presente, RuntimeEventLog expone
  sequence + RuntimeEvent.
- 2 tests subprocess CLI `tests/test_cli_runs_inspect.py`:
  `test_logs_run_via_cli_outputs_event_timeline` (cabecera +
  1 linea RunCreated con payload resumido) y
  `test_logs_run_via_cli_unknown_run_returns_error` (exit 10).
- UAT-08/09 regenerados (solo campo `revision` actualizado).

### Resultado

- **Bateria completa**: 680 passed (de 675 en v0.10.0, +5 nuevos:
  3 unit + 2 subprocess).
- **Ruff**: limpio.
- **Cobertura `runcontroller.py`**: 96% (sube de 95% a 96%).

### SemVer

`feat(logs_run) + feat(sg runs logs)` -> **MINOR** -> `v0.11.0`.
Consolidacion inmediata con v0.10.0 porque `logs` es el
complemento natural de `list`/`show`: sin timeline, el operador
no puede diagnosticar por que un Run fallo o se cancelo.

## [0.12.0] — 2026-09-24 (MINOR, budgets)

**Tag**: `v0.12.0` (pendiente; commit del slice en esta entrada).

**Resumen**: S4 del roadmap Etapa 7 (presupuestos opt-in por Run).
Cierra el riesgo principal que dejo el H4: un Run con self-loop y
sin limite superior puede iterar eternamente, consumiendo disco y
tiempo de computo sin abortar. Con S4, el operador puede poner
limites explicitos al crear el Run y el controller abortara
automaticamente cuando se alcancen, emitiendo un evento
`BudgetExceeded` que aparece en `sg runs logs`.

### Cambios funcionales (MINOR)

- **`EVENT_KINDS`** (`engine.py`): nuevo valor canonico
  `"BudgetExceeded"` (event_kind del runtime, NO categoria).
- **`EventBuilder.budget_exceeded(*, run_id, kind, limit, observed)`**:
  smart constructor con validacion: `kind` debe estar en
  `{visits, runtime, events}`. Payload: `{kind, limit, observed}`.
- **`RunBudget`** (dataclass frozen en `runcontroller.py`):
  `max_visits`, `max_runtime_seconds`, `max_events` (todos
  `Optional[int]`). Validacion `__post_init__`: no negativos,
  si se da debe ser > 0. `is_active` True si alguno definido.
- **`Storage.run_budgets`**: nueva tabla con PK `run_id` (FK
  logica a `workflow_runs`). Columnas `max_visits`,
  `max_runtime_seconds`, `max_events`, `inserted_at`.
  Migracion idempotente en `_migrate` (CREATE TABLE IF NOT EXISTS).
- **`Storage.upsert_budget(...)`**: INSERT OR REPLACE sobre la PK.
  Idempotente (cumple UAT-07).
- **`Storage.get_budget(...)`**: devuelve fila cruda o `None`
  (no lanza NotFoundError: ausencia = sin limites, compat con
  Runs anteriores a S4).
- **`RunController.create_run(..., budget=None)`**: parametro
  opcional. Si `budget is not None AND budget.is_active`,
  persiste via `upsert_budget`. Budget inactivo (todos None) o
  `None` = no escribe fila = semantica "sin limites" (compat).
- **`RunController._is_budget_exhausted`**: extendido (H4 + S4).
  Chequea 3 limites: (1) H4 original self-loop+max_visits por
  nodo, (2) Run.max_visits global, (3) Run.max_events global.
  Cuando (2) o (3) falla, emite `BudgetExceeded` antes de
  devolver True (asi el timeline del Run muestra POR QUE aborto).
- **`RunController._execute_one`**: invoca el check al inicio;
  si budget agotado, devuelve `False` (FAILED) sin tocar el
  nodo. El caller (`reconcile_run`) cierra el Run en FAILED
  via `_transition_run_state_with_event`.
- **`RunController._count_events`**: refactor menor — ahora
  delega en `Storage.list_events_for_run` (regla "Storage
  encapsula SQL"; antes tocaba `self._storage._conn` directo).
- **CLI `sg run ... --budget-visits N --budget-runtime-seconds N
  --budget-events N`**: parametros nuevos en el subcomando `run`.
  Si se da al menos uno, se construye `RunBudget` y se persiste.
- **CLI `sg runs budget <project> <run-id>`**: subcomando nuevo.
  Muestra el budget activo (key=value parseable) o `(sin budget)`.
  Run desconocido -> exit 10 (EXIT_DOMAIN).

### Tests

- 5 unit `TestRunBudgetDataclass`: defaults, valores positivos,
  negativos, cero, `is_active`.
- 4 unit `TestStorageBudget`: round-trip, nones, ausente, idempotencia.
- 3 unit `TestCreateRunWithBudget`: budget persistido, sin budget,
  budget inactivo.
- 2 unit `TestBudgetEnforcement`: self-loop+max_visits=1 emite
  BudgetExceeded; plan lineal sin budget no se aborta.
- 2 unit `TestBudgetKindValidation`: smart ctor rechaza kind invalido.
- 3 subprocess CLI `TestRunsBudgetCli`: `(sin budget)`,
  key=value, run desconocido -> exit 10.
- UAT-08/09 regenerados (solo campo `revision` actualizado).

### Resultado

- **Bateria completa**: 700 passed (de 680 en v0.11.0, +20 nuevos).
- **Ruff**: limpio.
- **Cobertura `runcontroller.py`**: 88% (baja de 96% por las
  nuevas lineas de S4 que no todos los tests ejercitan — el
  chequeo de `max_runtime_seconds` queda documentado como
  reservado y sera cubierto en S5 cuando se conecte a un
  reloj inyectable; el de `max_events` ya esta cubierto por
  enforcement del primer test).

### SemVer

`feat(RunBudget) + feat(BudgetExceeded) + feat(upsert_budget) +
feat(get_budget) + feat(sg runs budget) + feat(sg run --budget-*)`
-> **MINOR** -> `v0.12.0`. Consolidacion inmediata con v0.11.0
porque budgets son **complemento directo** del timeline:
`sg runs logs` (v0.11.0) muestra los eventos; sin budgets, no
hay forma de abortar Runs problematicos antes de que el operador
vea el timeline. La regla "evita micro-releases triviales" se
respeta: budgets son 3 `feat` coherentes (modelo, persistencia,
CLI) con enforce end-to-end probado.

## [0.13.0] — 2026-09-24 (MINOR, redaction policies)

**Tag**: `v0.13.0` (pendiente; commit del slice en esta entrada).

**Resumen**: S5 del roadmap Etapa 7 (politicas de redaccion por
tenant). Cierra el vector de exfiltracion que dejo el modelo de
eventos: hasta v0.12.0, cualquier payload de evento (que puede
contener API keys, tokens, paths de workspace) se persistia integro
en `runtime_events.payload_json`. Con S5, el operador configura una
politica por tenant (`none` | `metadata` | `payload` | `full`) y
el `EventLog` redacta automaticamente antes de persistir.

### Cambios funcionales (MINOR)

- **`runtime.redaction`** (modulo nuevo):
  - `RedactionPolicy = Literal["none", "metadata", "payload", "full"]`.
  - `validate_policy(policy)`: smart constructor; `ValidationError`
    si la politica no esta en el conjunto canonico.
  - `redact_payload(payload, policy)`: funcion pura (no I/O,
    no reloj, determinista). Implementa las 4 politicas:
    - `none`: copia superficial (compat con pre-S5).
    - `metadata`: conserva claves, valores -> `[REDACTED]`.
    - `payload`: redaccion recursiva (escalares `[REDACTED]`,
      colecciones conservadas en forma).
    - `full`: devuelve `{}` (descarta todo el payload).
  - `REDACTED_MARKER: Final[str] = "[REDACTED]"`: constante
    publica para UIs que quieran detectar y formatear.
- **`Storage.tenant_policies`**: nueva tabla con PK `tenant_id`.
  Columnas: `redaction_policy TEXT NOT NULL DEFAULT 'none'`,
  `updated_at`.
- **`Storage.get_policy(*, tenant_id)`**: devuelve la politica
  configurada o `None` (sin fila = sin limite = default `none`).
- **`Storage.upsert_policy(*, tenant_id, policy)`**: INSERT OR
  REPLACE idempotente sobre la PK. Storage NO valida la politica;
  la validacion vive en `runtime.redaction` (regla "Storage
  encapsula SQL, no reglas de negocio").
- **`EventLog.__init__(conn, *, policy_resolver=None)`**: nuevo
  parametro opcional. `policy_resolver` es un `Callable[[str],
  str | None]` que, dado un `tenant_id`, devuelve la politica
  efectiva. Sin resolver -> default `none` (compat con pre-S5).
- **`EventLog._resolve_policy(tenant_id)`**: helper privado.
  Sin resolver -> `"none"`. Resolver devuelve None -> `"none"`.
  Resolver devuelve valor -> se aplica tal cual.
- **`EventLog.append`**: si hay policy_resolver configurado,
  el payload se redacta ANTES de serializar a `payload_json`.
  El `RuntimeEvent` original NO se muta (es frozen). Asi `logs_run`
  sigue viendo el evento ORIGINAL; en disco solo aparece la
  version redactada.
- **`RunController.__init__`**: inyecta un policy_resolver que
  delega en `Storage.get_policy` (regla "Storage encapsula SQL").
- **CLI `sg policy get <project>`**: imprime la politica efectiva
  del tenant. Default `none` si no hay fila.
- **CLI `sg policy set <project> --redact-policy X`**: persiste
  la politica. Choices validadas via argparse: `none|metadata|payload|full`.
- **`_route_policy`**: dispatcher para `policy get|set`.

### Politica default

Sin politica configurada para un tenant, el `EventLog` aplica
`"none"` (passthrough). Esto preserva el comportamiento de
v0.12.0 y anteriores: los Runs creados antes de S5 siguen
persistiendo payloads integros. La redaccion es **opt-in** por
tenant. Migrar un tenant a redaccion requiere ejecutar
`sg policy set <project> --redact-policy <X>`.

### Tests

- 14 unit `test_redaction.py`: validate_policy (2) + none (2) +
  metadata (2) + full (2) + payload (3) + pureza (2) + type (1).
- 3 unit `TestStoragePolicyPersistence`: round-trip, ausente,
  idempotencia.
- 4 unit `TestEventLogRedaction`: resolver=metadata redacta,
  default=none passthrough, resolver=payload recursivo,
  resolver=none passthrough.
- 4 subprocess CLI `test_cli_policy.py`: get sin policy,
  set+get round-trip, set invalido -> exit != 0, persistencia SQL.
- UAT-08/09 regenerados (solo campo `revision` actualizado).

### Resultado

- **Bateria completa**: 725 passed (de 700 en v0.12.0, +25 nuevos).
- **Ruff**: limpio.
- **Cobertura `redaction.py`**: **100%** (modulo nuevo puro).
- **Cobertura `runcontroller.py`**: 88% (sin cambios: las lineas
  nuevas de S4 siguen sin cubrir `max_runtime_seconds`, que se
  conectara a un reloj inyectable en una iteracion futura).

### SemVer

`feat(redaction) + feat(EventLog.policy_resolver) +
feat(tenant_policies) + feat(sg policy get/set)` -> **MINOR**
-> `v0.13.0`. Consolidacion inmediata con v0.12.0 porque la
redaccion es **complemento directo** del modelo de eventos:
v0.12.0 emita eventos con secretos potenciales; sin S5, esos
secretos iban a disco. La regla "evita micro-releases triviales"
se respeta porque S5 son 4 `feat` coherentes (modelo, persistencia,
integracion EventLog, CLI).

## [0.14.0] — 2026-09-24 (MINOR, locks concurrentes por run)

**Tag**: `v0.14.0` (pendiente; commit del slice en esta entrada).

**Resumen**: S6 del roadmap Etapa 7 (locks concurrentes por run).
Hasta v0.13.0, dos `sg run --concurrency` o dos schedulers
externos apuntando al mismo `<tenant>/<project>/<run-id>` podian
leer/escribir `runtime_events` y `runs` de forma entrelazada,
corrompiendo la transicion de estado. S6 introduce locks de
fichero por run para serializar reconcile_run y create_run
dentro del mismo proceso y entre procesos, con dos politicas:
`advisory` (espera hasta `lock-timeout-seconds`) y `fail-fast`
(eleva `LockUnavailable` con `code=sg_lock_unavailable`).

**Modulos / simbolos nuevos**:

- `skillgraph.runtime.locks` (modulo nuevo):
  - `RunLockKey(tenant_id, project_id, run_id)` con sanitizacion
    de path traversal (caracteres `/\. ` reemplazados por `_`).
  - `RunLockKey.to_filename() -> str` (`<tenant>__<project>__<run-id>.lock`).
  - `LockMode = Literal["none", "advisory", "fail-fast"]`.
  - `LockUnavailable(SkillGraphError)` con `code="sg_lock_unavailable"`.
  - `RunLock(lock_dir: Path, key: RunLockKey).take(mode, timeout_seconds)`
    context manager sobre `fcntl.flock` (LOCK_EX | LOCK_NB en polling
    para advisory; LOCK_EX | LOCK_NB en fail-fast).
  - Limpieza: `LOCK_UN`, `os.close`, `unlink()` con
    `contextlib.suppress(OSError)`.

**RunController**:

- Constructor extendido: `lock_dir: Path | None`,
  `lock_mode: LockMode = "none"`,
  `lock_timeout_seconds: float = 30.0`.
- Helper interno `_locked_run(tenant, project, run_id) -> Iterator`
  que delega en `_noop_lock()` cuando `lock_mode="none"` o
  `lock_dir=None`.
- `create_run(...)` envuelto en `with self._locked_run(...)`.
- `reconcile_run(...)` envuelve el cuerpo en
  `with self._locked_run(...)`; extraido a `_reconcile_run_locked`.

**Tests** (12 nuevos en `tests/test_locks.py`):

- `TestRunLockTakeRelease` (3): acquire + release, no leak, idempotencia.
- `TestRunLockConflict` (2): `fail-fast` eleva `LockUnavailable`;
  `advisory` con timeout corto eleva `LockUnavailable`.
- `TestRunLockReleasesOnException` (2): `try/except` interno libera
  el lock; `with` con excepcion interna libera.
- `TestRunLockKey` (3): filename estable, sanitizacion, sin colisiones.
- `TestRunLockAcrossProcesses` (2): dos procesos via `multiprocessing`
  se serializan en el mismo run.
- `TestRunControllerLockIntegration` (1): dos `RunController`
  reconciliando el mismo Run con `lock_mode="advisory"` se serializan
  y terminan ambos en `COMPLETED`; lock_file no queda tras la ejecucion.
- `TestRunControllerLockFailFast` (1): `fail-fast` eleva
  `LockUnavailable` si otro reconcile_run tiene el lock
  (test debil bajo concurrencia extrema).

Total acumulado: **739 tests verde** (725 + 14 nuevos).
`ruff check src tests`: limpio.

### SemVer

`feat(runtime.locks) + feat(RunController lock_dir/lock_mode/lock_timeout_seconds) +
feat(create_run/reconcile_run lock wrapping)` -> **MINOR**
-> `v0.14.0`. Consolidacion inmediata con v0.13.0 porque los locks
son **complemento directo** del modelo de eventos: v0.13.0 introduce
politicas de redaccion, pero sin S6 dos reconciliaciones concurrentes
pueden intercalar eventos y saltarse la redaccion. La regla
"evita micro-releases triviales" se respeta porque S6 son 3 `feat`
coherentes (locks, integracion RunController, tests de concurrencia).

## [Sin bump] — 2026-09-24 (refactor interno)

**Commit**: `6c8c17f` (sin tag, refactor sin bump).

**Resumen**: Reduccion de tamano de funciones en `knowledge/context_controller.py`
para cumplir AGENTS.md §1.5 (umbral ~40 LoC).

- `ContextController.compile_handoff`: 121 -> 94 LoC. Delegacion en
  3 helpers puros de modulo:
  - `enforce_strict_freshness(items, policy)`
  - `apply_budget(obligatory, optional, *, budget_chars, overflow_strategy)`
  - `build_capabilities(included, policy)`
- `ContextController._resolve_one_selector`: 114 -> 23 LoC. Dispatcher
  que delega en 3 ramas:
  - `_resolve_entity_selector(ctrl, value)` (14 LoC)
  - `_resolve_predicate_selector(ctrl, value)` (16 LoC)
  - `_resolve_source_selector(ctrl, value, label)` (31 LoC)
- Mapeo a `CompiledResource` encapsulado en 3 funciones puras de
  modulo: `claim_to_resource`, `predicate_row_to_resource`,
  `evidence_row_to_resource`.

**Tests**: 15 nuevos en `tests/test_context_controller.py`
(11 helpers + 4 mappers). Total: **754/754 verde**. ruff limpio.

## [Sin bump] — 2026-09-26 (stewardship: defensa operativa)

**Commits**: `4d1e622` + `23e4c94` (fix) + `21bc550` (docs) + tareas mise.

**Resumen**: Ciclo STEWARDSHIP-DT-PRE-PUSH-HOOK. Tercera capa de defensa
operativa (junto a pre-commit y CI remoto): **pre-push** ejecuta la suite
completa de pytest (~190s) antes de aceptar un `git push`.

- Hook POSIX shell en `scripts/hooks/pre-push` (75 LoC, sin
  dependencias externas).
- Dispatcher `run_in_toolchain` que detecta `mise`/`uv`/`pip`/`none` y
  delega en el wrapper nativo.
- Bypass `HOOK_SKIP_PUSH_TESTS=1` para emergencias.
- Patrón `mktemp` + `if !` (workaround al bug `set -e` + `| tail` ya
  documentado en `.pipeline.kts`).
- `trap 'rm -f "$_log"' EXIT` para limpieza de tempfile en
  SIGTERM/SIGINT (anadido en V9d deep audit).
- README documenta la capa defense-in-depth en EN y ES.
- Tareas `mise run test-fast` (abort 1er fallo) y `mise run test-cov`
  (cobertura local) para iteracion RED/GREEN.

**Tests**: 9 nuevos en `TestPrePushHook` + `test_installer_copies_all_hooks`.
Total: **889/889 verde**. ruff limpio. Auditoria completa en
`audits/pre-push-hook-2026-09-26.md` (239 LoC).

**Justificación de "Sin bump"**: es dev-infra puro. No añade API
observables ni cambia comportamiento del producto. Siguiente bump
será solo cuando llegue un `feat` real.

## [Sin bump] — 2026-09-26 (stewardship: cobertura de branches H12)

**Commit**: `tests/test_h12_file_signature_scopes.py` (15 tests nuevos) +
`audits/file-scope-validation-branches-2026-09-26.md`.

**Resumen**: Ciclo STEWARDSHIP-DT-FILE-SCOPE-VALIDATION tras la consigna
"avanza" del operador. Subir la cobertura de `file_scope.py` (H12 Scopes
y consultas composables) sin tocar API ni contratos.

- Clase `TestFileScopeValidation` con 15 tests nuevos cubriendo las 12
  ramas tristes que coverage reportaba como descubiertas:
  - 4 sobre `validate_package_name` / `validate_bounded_context_name`
  - 2 sobre `ScopeQuery.__post_init__`
  - 3 sobre `ScopeResolution.__post_init__`
  - 2 sobre `resolve_directory_scope`
  - 2 sobre `resolve_package_scope`
  - 1 sobre `resolve_bounded_context_scope`
  - 1 sobre `aggregate_signatures` (dedup por foco)
- 0 cambios en `src/skillgraph/`. 0 contratos rotos. 0 regresiones.
- Hallazgo colateral documentado (NO reparado): `SignatureProcedencia.
  __post_init__` levanta `ValueError` en vez de `ValidationError`,
  violando AGENTS §1.2. Fix fuera de scope; registrado como derivado.

**Tests**: 23/23 verde en el archivo. Total proyecto: **904/904 verde**.
ruff limpio.

**Cobertura**: `file_scope.py` 82% → **99%** (+17pp). La única línea
restante (284) es un corner case interno del loop de agregación donde
`signatures_per_source` tiene entries con tuple vacío.

## [Sin bump] — 2026-09-26 (cumplimiento AGENTS §1.2: errores tipados)

**Commit**: `dfd192a` — 16 raises cambiados + 12 tests nuevos + audit.

**Resumen**: Tras la consigna "vamos con lo siguiente", se abordó el
hallazgo colateral de la investigación retrospectiva. La inspección
extendida reveló 16 violaciones de AGENTS §1.2 (errores tipados) en
6 archivos:

```text
src/skillgraph/knowledge/file_signature.py    8 raises ValueError
src/skillgraph/knowledge/file_handoff.py      3 raises ValueError
src/skillgraph/knowledge/git_source.py        1 raise ValueError
src/skillgraph/runtime/locks.py                1 raise ValueError
src/skillgraph/governance/improvement.py       2 raises ValueError
src/skillgraph/governance/receipts.py          1 raise ValueError
```

Todos en `__post_init__` de dataclasses de dominio.

**Cambios**:
- src/: 16 raises cambiados de ValueError → ValidationError
- tests/test_knowledge_validation_errors.py: 12 tests nuevos (12/12 rojo→verde)
- tests/test_h9_coverage_git_source.py:78: migrado a ValidationError
- 0 callers en src/ con `except ValueError` (grep limpio)
- ValidationError hereda de SkillGraphError → Exception (no rompe nada)

**Tests**: 918/918 verde (906 → 918, +12 nuevos). Mutation testing M8
detectada. ruff limpio.

**Verificación final**:
```bash
grep -rn "raise ValueError\|raise Exception" src/skillgraph/ --include="*.py"
  → 0 resultados (100% cumplimiento §1.2)
```

**Auditoría completa** en `audits/knowledge-validation-errors-2026-09-26.md`
(114 LoC).
