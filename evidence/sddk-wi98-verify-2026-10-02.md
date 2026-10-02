# SDDK WI-98 — verificación

**Ciclo**: `p-b7740b96d79ec013/wi98-ci-recipe-parity`
**Bloque**: WI-98 · **Release**: `v0.19.0` (MINOR) · **Fecha**: 2026-10-02

---

## 1. Qué abrió el bloque

`AGENTS.md`, «Compatibilidad con otros runners»:

> GitHub Actions, GitLab CI, Jenkins o cualquier otro runner remoto **debe**
> invocar el mismo `.pipeline.kts` desde el mismo checkout.

Medido: **no lo hace, y no podía.**

## 2. La divergencia, medida con el mismo instrumento

Instrumento: `scripts/check_coverage_floors.py` (criterio de recuentos) en
las dos recetas.

| | receta local | `ci.yml` antes |
|---|---|---|
| stages ejecutados | **8** | **1** (`lint`) |
| `unit-tests` | `scripts/coverage.sh` | `pytest --cov` a pelo |
| contratos exigibles | 4 | **0** |
| `cli/commands/runs.py` | **87,96 %** | **39 %** |
| `cli/commands/run.py` | 96,09 % | 81 % |
| `cli/support.py` | 85,71 % | **69 %** ← suelo declarado: 70 % |
| `cli/` agregado | 86,91 % | — |

El remoto podía dar **verde** un paquete que no cumplía el suelo que el
propio `AGENTS.md §6.3` declara.

**Por qué el mismo instrumento importa.** El remoto medía sin el hook
`.pth` de `scripts/coverage.sh`, así que el CLI ejecutado por subproceso no
se ve. Comparar ese número contra un 94 % de la receta instrumentada
habría sido comparar dos cosas distintas y llamarlas divergencia: el
número habría sido dramático y falso.

## 3. Por qué no se cumplía: la regla era inejecutable

`.pipeline.kts` llevaba **10** rutas absolutas a
`/var/mnt/DiscoChino2-fast/Proyectos/python/skillgraph/...`, y `AGENTS.md`
(«Extensión del script») **exigía** escribirlas así. La norma que hacía
inejecutable la regla de runners estaba en el mismo fichero que la declara.

Medido antes de escribir el código, no supuesto:

| Comprobación | Resultado |
|---|---|
| `GITHUB_WORKSPACE` exportado → llega al `sh()` | **sí** (`GITHUB_WORKSPACE=[/tmp/fake-checkout]`) |
| `System.getProperty("user.dir")` con cwd = raíz del repo | resuelve al repo |
| `cwd` del `sh()` | el workspace del motor, **no** el repo |

Solución, una línea:

```kotlin
val repo = System.getenv("GITHUB_WORKSPACE") ?: System.getProperty("user.dir")
```

## 4. Los guards que existían no comparaban nada

Nueve tests en `tests/test_hooks_system.py::TestCIWorkflow`, todos de la
forma «la cadena X está en el contenido»:

```python
assert "pytest" in content or "test" in content.lower()   # satisfecha por un comentario
```

**Ningún test del repo comparaba `ci.yml` con `.pipeline.kts`.**
Sustituidos por ocho que miden propiedades.

## 5. El guard cayó en la trampa que viene a cerrar

Las cinco primeras mutaciones dieron `rc=0`. El defecto estaba en el
**diseño del invariante**:

- **C1** buscaba `.pipeline.kts` en el contenido entero del workflow. El
  workflow real lo menciona en un comentario que explica que se usa, y el
  guard encontraba la cadena ahí. Ahora mira los **pasos ejecutables**.
- **C2** buscaba rutas absolutas solo dentro de `sh(...)` y no las veía
  cuando estaban en una `val` de Kotlin — justo donde se mueven para
  arreglar el problema. **Un invariante que solo mira una sintaxis
  concreta se esquiva cambiando de sintaxis.** Ahora: el script
  **resuelve** la raíz y **no contiene** la raíz de este árbol.

El parser de pasos vive en el checker, no en el fichero de tests: el
invariante depende de él, y duplicarlo es la forma de que dejen de contar
lo mismo sin que nada lo note.

## 6. El script de mutaciones también estaba mal

Dos motivos, ambos escritos para que no se repitan:

1. `mktemp` pasa por un wrapper que **manda el fichero recién creado a la
   papelera**. Los respaldos no existían, las cinco «mutaciones» leyeron el
   árbol ya restaurado y el `ABORTO` final destapó el motivo. Restaurado por
   contenido, como manda la regla.
2. Las mutaciones sustituían **una línea** de un bloque `run: >` dejando
   las siguientes, con lo cual la receta seguía presente en el paso.

**Un contraejemplo que no degrada nada no prueba que el guard funcione:
prueba que el script de mutaciones está mal.**

## 7. Mutaciones: 5/5

| | Mutación | Código | Lo caza |
|---|---|---|---|
| M1 | el remoto ejecuta su propia receta | `sg_ci_receta_propia` | script |
| M2 | la receta deja de resolver la raíz | `sg_ci_ruta_absoluta` | script |
| M3 | la receta se ata a esta máquina (`val`) | `sg_ci_ruta_absoluta` | script |
| M4 | la receta solo aparece en un comentario | `sg_ci_receta_propia` | script |
| M5 | la receta no declara etapas | `sg_ci_etapa_desconocida` | script |

Restauración **byte a byte** de los dos ficheros.

## 8. Verificación

- **Suite completa**: `2625 passed in 130.78s` (estado ya commiteado, sin
  edición concurrente).
- **CI canónica**: `Pipeline finished with SUCCESS`, **8/8 stages** (stage
  nuevo `ci-parity`), run `32ffe214-5302-447c-a477-9e0b1015eecc`,
  **0 `StepFailed`**, `2625 passed in 245.73s`. Los **cuatro** contratos
  exigibles en verde.
- **SHA-256** de `.pipeline.kts` =
  `d865896832f1c391344cb76a1b52b14c68915b99cefd985e976381dfe8d3ddcc`.
- **SemVer**: `derive_semver.py` → `b/f/x/n/d: 0/1/2/3/0` → **MINOR**.
- **Gobernanza**: `test_release_governance`,
  `test_state_release_integrity` y el guard del CHANGELOG verdes.

## 9. Capacidad conservada

La subida de `coverage.xml` era una capacidad real, no un *string*. Se
mantiene cambiando el **origen** del dato: se exporta del `.coverage`
combinado e instrumentado que deja la receta, no de un `pytest --cov` a
pelo. Un test nuevo (`test_workflow_uploads_coverage_artifact`) comprueba
también que el fichero **se genera**, no solo que se nombra: se puede
subir un artefacto que no existe y el paso sigue en verde.

## 10. Estado

**SIN PUSH.** 96 commits sin publicar; `origin/main` en `0ebbd58`.
