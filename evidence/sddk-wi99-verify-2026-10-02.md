# WI-99 — evidencia de auditoría reproducible

**Fecha**: 2026-10-02
**Ciclo**: `p-b7740b96d79ec013/wi99-audit-evidence-reproducible`
**Commit certificado**: `984289d80207c1547be066b63a2f153ca3d9dff0`

---

## 1. La pregunta del bloque

`scripts/audit_bundle.sh` existe para dar evidencia reproducible a una
auditoría independiente. ¿La evidencia que produce es reproducible?

La primera medición dio la respuesta, y no era la que se esperaba.

**Mismo commit, dos árboles:**

| | commit `504b65d` |
|---|---|
| árbol de trabajo (donde se construyó) | `2625 passed` |
| clon limpio del mismo commit | **`2 failed, 2623 passed`** |

Una divergencia de 2 tests entre el sitio donde se trabaja y el sitio donde
se audita. Los dos fallos eran
`tests/test_wi91_h9_conformance_record.py::TestGuardSobreElRegistroReal::test_todo_testigo_declarado_existe`
y `::TestGuardMuerdeEnLasDosDirecciones::test_un_registro_correcto_no_produce_violaciones`,
y el mensaje literal del guard era **«afirmación sin respaldo»**.

Un guard que dice la verdad y falla en el sitio donde se audita. Eso no es
un test rojo: es un entregable declarado cumplido cuya evidencia no viaja
en el repo.

---

## 2. Causa raíz 1 — `.gitignore` tapaba la evidencia

`STATE.yaml` declaraba dos entregables de H9 (E2 y E4) como CUMPLIDOS, con
`docs/architecture/ADR-0015-threat-model-stride.md` y
`docs/observability-runbook.md` como evidencia. Ninguno de los dos estaba
versionado: el patrón `docs/*` del `.gitignore` los cubría.

Barrido de las 150 referencias con forma de fichero declaradas en
`STATE.yaml`:

| categoría | cantidad | veredicto |
|---|---|---|
| no versionadas | 3 | **fallo real** |
| inexistentes | 1 | irrecuperable |
| bajo `external/` | 3 | correcto por diseño |
| plantillas (`tests/uat-evidence/UAT-XX.json`) | 1 | correcto |

La inexistente, `docs/architecture/h9-bslice3-runcontroller-storage.md`, se
anotó en `STATE.yaml` como referencia irrecuperable. **No se inventó el
documento**: un testigo que se fabrica no es un testigo.

El `.gitignore` se reescribió separando las dos categorías que `docs/*`
trataba como una —evidencia que el código referencia frente a material de
trabajo— y se versionaron los tres documentos.

> **Decisión**: versionar la evidencia en vez de degradar el estado del
> entregable. El trabajo se hizo; el `.gitignore` lo tapó por accidente. Un
> entregable cuya evidencia no está en el repo no está cumplido: el que lo
> construye no lo recibe, y el que lo audita no lo puede leer.

`tests/test_wi91_h9_conformance_record.py`: 14 passed.

---

## 3. Causa raíz 2 — `scripts/ci.sh` era una cuarta receta

Medido en WI-99, `ci.sh` ejecutaba su **propia** receta: `ruff format
--check`, `ruff check` y `pytest` a pelo. Sin el hook `.pth` de
`scripts/coverage.sh`, el CLI ejecutado por subproceso no se ve:

| | receta canónica | `scripts/ci.sh` |
|---|---|---|
| stages | 8/8 | 3 |
| contratos exigibles | 4/4 | **0** |
| `cli/commands/runs.py` | 87,96 % | **39 %** |

Y `audit_bundle.sh` lo invocaba. Es decir: **el instrumento que existe para
medir medía con el que no ve**, y la evidencia versionada en
`audits/cleanroom-evidence/` se había producido así.

Arreglar una vez arregla las dos cosas: `ci.sh` pasa a **delegar** en
`.pipeline.kts`, y `audit_bundle.sh` pasa a producir la evidencia con el
instrumento correcto sin tocar una línea.

---

## 4. Causa raíz 3 — el comando canónico no arrancaba en un clon nuevo

Con `ci.sh` delegando, el bundle dejó de funcionar en un clon limpio. Dos
precondiciones que no se veían leyendo `AGENTS.md`:

```
$ mise exec -- pipelinek run --rerun --db .pipelinek/db.sqlite \
      --control-root .pipelinek/control .pipeline.kts
mise: Trust them with `mise trust`
```

```
java.sql.SQLException: path to '.pipelinek/db.sqlite':
'/ruta/al/clon/.pipelinek' does not exist
```

`mise` no ejecuta las herramientas de un checkout en el que no confía, y
`pipelinek` **abre el fichero SQLite, no el directorio que lo contiene**.

Un auditor que clonara el repositorio y ejecutara lo documentado recibía
dos errores de herramientas, ninguno de los cuales menciona esta sección.
Es el mismo patrón que WI-98 eliminó de `.pipeline.kts` (diez rutas
absolutas a un árbol de trabajo concreto): **una regla que no se puede
cumplir fuera de esta máquina no es un contrato, es una costumbre.**

Arreglo: `.pipelinek/.gitkeep` versionado (el `.gitignore` pasa a ignorar el
**contenido**, no el directorio) y `scripts/ci.sh` hace `mise trust` y
`mkdir -p .pipelinek` por su cuenta.

**Verificado con `git add --dry-run`**, que es el instrumento que resuelve;
`git check-ignore` no distingue aquí porque la última regla que coincide es
la negación.

---

## 5. El invariante que impide la recaída

Arreglar `ci.sh` sin un guard es arreglarlo hasta la próxima vez. C4, en
`scripts/check_ci_recipe_parity.py`:

> Un script de `scripts/` que ejecuta `pytest` tiene que estar conectado a
> la receta canónica: o es un **fragmento** que ella invoca, o **delega** en
> ella.

**Disyuntiva a propósito.** La versión restrictiva —«nadie ejecuta pytest
salvo `.pipeline.kts`»— hace del propio fichero de cobertura una
infracción, y su única salida es una lista de excepciones que el guard
mantiene: un guard que vigila la lista que él mismo mantiene no vigila
nada.

Decisiones que se tomaron **midiendo**, no suponiendo:

| decisión | por qué |
|---|---|
| los fragmentos se **leen** de `.pipeline.kts` | una constante solo vigila los que ya conocía |
| los scripts se **descubren** por extensión en `scripts/` | un `verify.sh` nuevo entra solo en el contrato |
| se buscan **órdenes**, no líneas | la invocación real está partida con `\`: buscarla por línea concluiría que `ci.sh` no delega, y el defecto estaría en el invariante |
| comentarios con «marca al inicio o tras espacio» | partir por el primer `//` trunca `https://mise.run`; por cualquier `#`, trunca `echo "## CI Summary"`. La regla es la misma para YAML y shell: ahora es **una** función, no dos |
| `scripts/hooks/` **excluido, y el test fija la exclusión** | `pre-push` mide con el instrumento ciego; que ampliar la exclusión rompa un test la convierte en puerta trasera en acuerdo escrito |

**Límite declarado**: un script que sí delega podría ejecutar `pytest`
además en su camino certificante y seguir cumpliendo. Verlo exigiría un
parser de flujo de bash, un instrumento mayor que el problema que se cierra.

### Mutaciones: 6/6

Un test que nunca se ha visto fallar es una esperanza, no un test. Las seis
mutaciones verificadas con `bash .pipelinek/wi99_mutate.sh`, con autocontrol
(árbol limpio, control previo verde) y restauración byte a byte:

| | mutación | veredicto |
|---|---|---|
| M1 | `ci.sh` vuelve a su receta propia — **el fichero real de `504b65d`, sacado de git** | rojo |
| M2 | `.pipeline.kts` deja de invocar `coverage.sh` (el otro brazo de la property) | rojo |
| M3 | `ci.sh` ejecuta `pytest` sin delegar | rojo |
| M4 | aparece un `scripts/verify.sh` con `pytest` a pelo (descubrimiento) | rojo |
| M5 | `ci.sh` delega en **otro** pipeline (separa «delega» de «delega en LA canónica») | rojo |
| M6 | la exclusión crece hasta tapar `scripts/` entero | el test que la fija se pone rojo |

M1 usa el contraejemplo real, no uno inventado: un contraejemplo sintético
demostraría que el test está bien, no que el guard muerde.

M6 no pone rojo el checker —se auto-excluye y por eso calla—, y por eso la
comprobación es sobre el test. Un guard que se puede silenciar a sí mismo
no está verificado.

---

## 6. Cierre: el bundle sobre el commit certificado

```
$ bash scripts/audit_bundle.sh 984289d80207c1547be066b63a2f153ca3d9dff0
```

En un **clon limpio** (`git clone --no-local`), ejecutando la receta
canónica a través de `scripts/ci.sh`:

| criterio `AGENTS.md` | medido |
|---|---|
| 1. `Pipeline finished with SUCCESS` | ✅ run `2401fe95-d673-4a4e-b6c3-ac3e43501210` |
| 2. ejecutó pasos de verdad | ✅ 53 eventos, `2636 passed in 239.26s` |
| 3. journal SQLite con eventos tipados | ✅ `CompilationStarted` … `RunFinished/success` |
| 4. control root | ✅ `last-run present`, `workspace tracking present` |
| 5. cero `StepFailed` en este run | ✅ |
| 6. SHA-256 de `.pipeline.kts` comparable con git | ✅ |

Los 8 stages: `discover-repo`, `sync-deps`, `unit-tests`, `coverage-floors`,
`package-build`, `ci-parity`, `lint`, `evidence` — todos `success`.

| contrato | veredicto en el clon |
|---|---|
| `unit-tests` | 2636 passed, cobertura total **95,22 %** |
| `coverage-floors` | todos los suelos declarados se cumplen |
| `package-build` | el paquete construye y cumple su contrato declarado |
| `ci-parity` | *«…y ninguna otra receta ejecuta pytest por su cuenta»* ← C4 verificado en el clon |
| `lint` | All checks passed |
| `uat_audit` | **PASS=16 FAIL=0 BLOCKED=0** |

**Divergencia 0 en el commit `984289d`.** El mismo commit da 2636 en el
árbol de trabajo y 2636 en el clon. Antes de WI-99 eran 2625 y 2623+2
failed.

> ### Lo que esta medición NO cubrió
>
> `984289d` es **anterior a la trazabilidad de este bloque**. La primera CI
> canónica sobre el estado final dio `2 failed, 2634 passed`:
>
> | test | por qué |
> |---|---|
> | `test_every_semver_tag_is_listed_exactly_once` | el tag `v0.20.0` no estaba en `STATE.yaml release.releases` |
> | `test_el_bloque_vivo_tiene_al_una_cita_que_verificar` | el bloque vivo de `CURRENT.md` no citaba ninguna línea verificable |
>
> Los dos los atraparon guards que ya existían. Es decir: la afirmación
> «divergencia 0» era cierta **para el commit medido** y falsa **como
> propiedad del estado final**, porque el estado final se había escrito
> después de medir. Un guard que vigila el mismo commit que uno acaba de
> certificar no puede ver lo que uno escribe después.
>
> **La reproducibilidad hay que certificarla después de escribir la
> certificación.** Corregido y re-medido sobre el estado final.

### Una observación del entorno, no del repo

Cada step del motor deja una línea `mavis-trash: moved to trash:
'…/.pipelinek/control/<run>-s<N>-<M>/.cookie'`. El wrapper de borrado del
entorno se lleva los ficheros de cookie que pipelinek deja en su control
root. **No rompe nada** —los criterios 3 y 4 se cumplen y los 8 stages
pasan— pero ensucia la salida y conviene saber que está ahí antes de que
alguien lo lea como un fallo del motor.

---

## 7. Lo que este bloque NO resolvió

Registro, sin abrir frentes:

| | por qué no se resuelve aquí |
|---|---|
| **97+ commits sin publicar** | `origin/main` en `0ebbd58`. Push no autorizado. |
| **Credenciales Anthropic/OpenAI** | ausentes. Bloquean el criterio de salida de H9, incumplido desde WI-91. |
| **`release.complete` inalcanzable** | exige `release-receipt`, que solo emite `sddk release apply`, cuyo plano exige `Cargo.toml`. Se cierra con `cycle supersede`. |
| **`scripts/hooks/pre-push`** | ejecuta la suite a pelo y emite veredicto con el instrumento ciego. Excluido de C4 **por escrito** y con la exclusión fijada por un test. Convergerlo es un workitem propio. |
| **`ADR-0015` designa dos documentos distintos** | decisión del mantenedor, no ejecutada. Fuera de alcance. |
| **4 errores de `sddk lint`** | checks de perfil **autor de pack** (`schemas/`, `docs/generated/*`, `manifest.toml`). Este repo es perfil **consumidor**. Sin opt-out, y no está en ningún stage. Adoptarlos sería cargo-culting. |
| **63 informes en `audits/`** | política de datos, decisión del mantenedor. |
| **Desorden antiguo del CHANGELOG** | medido y aceptado en WI-95. |
| **2 líneas con caracteres CJK en `AGENTS.md`** (119, 251) | preexistentes, ajenas al alcance. |
| **Debt reportada, no real** | `raise ValueError`/`Exception` en el dominio: **0**. `RuntimeError` (2), `KeyError` (5) y `TypeError` (5) son idiomáticos. La alerta no se sostiene. |

---

## 8. Lo que se aprendió

1. **Un guard que solo mira una sintaxis concreta se esquiva cambiando de
   sintaxis.** WI-98 lo sufrió dos veces y WI-99 lo confirms: la primera
   versión de C4 habría buscado `pipelinek` y `.pipeline.kts` en la misma
   línea, y la invocación real está partida con barras invertidas. El
   defecto habría estado en el invariante, no en el repo.
2. **Un contraejemplo real no se puede discutir.** M1 restaura el fichero
   de verdad, sacado de git. Un contraejemplo inventado demuestra que el
   test está bien, no que el guard muerde.
3. **Un guard que se puede silenciar a sí mismo no está verificado.** M6
   por eso se comprueba sobre el test, no sobre el checker.
4. **Delegar arregla dos cosas a la vez.** `ci.sh` deja de ser una receta
   y `audit_bundle.sh` deja de medir mal, sin tocar la segunda.
5. **La reproducibilidad es una propiedad del repo, no del trabajo.** El
   mismo commit daba dos resultados distintos según dónde se ejecutara. Eso
   no lo arregla quien lo construyó bien; lo arregla lo que viaja.

---

## 9. Reproducir esta evidencia

```bash
git clone <repo> && cd <repo>
mise trust
bash scripts/audit_bundle.sh $(git rev-parse HEAD)
```

Sin `mise trust` ni `.pipelinek/` (que ahora viaja versionado vía
`.gitkeep`) el comando no arranca. Con ellos, los 8 stages y el bundle.
