# SDDK WI-97 — verificación

**Ciclo**: `p-b7740b96d79ec013/wi97-package-build-contract`
**Bloque**: WI-97 · **Release**: `v0.18.0` (MINOR) · **Tag**: `7ffc456`
**Fecha**: 2026-10-02

---

## 1. Qué abrió este bloque

La pregunta que abre la serie —*¿qué declara el repo que nada comprueba?*—
llegaba a su último eslabón: `git → __version__ → pyproject (hatch) → wheel`.

Medido antes de decidir nada:

```
$ grep -rlniE 'hatchling|uv build|entry_points|importlib\.metadata|console_scripts' tests/
(sin resultados)
```

Los 6 stages de `.pipeline.kts` no construían el paquete. Ningún test
referenciaba el build.

## 2. La premisa del bloque era falsa

La hipótesis de partida era que el build estaba roto. **Medida, es falsa**:

| Medición | Valor |
|---|---|
| `uv build` (sdist + wheel), en frío y en caliente | **1,7 s** |
| Wheel | 248 KB, **80 módulos**, `py.typed` incluido |
| Instalación en venv limpio | OK |
| `skillgraph --help` desde el paquete instalado | rc=0 |
| `skillgraph --version` | `0.17.0.dev0`, coincide con `importlib.metadata` |

El hueco no es que nada funcione: es que **nadie lo miraba nunca**.

## 3. Las invariantes

`scripts/check_package_build.py`, stage `package-build`.

| Invariante | Qué impide |
|---|---|
| `sg_build_version_drift` | que el número del artefacto no sea el del código |
| `sg_build_target_no_resoluble` | que un `[project.scripts]` apunte a algo inexistente |
| `sg_build_modulo_faltante` / `..._sobrante` | que el wheel no recoja el paquete (heredando del árbol) |
| `sg_build_py_typed_ausente` | que el paquete declare `py.typed` y no lo lleve |
| `sg_build_sdist_no_versionado` | que el artefacto herede del árbol de trabajo, no del commit |
| `sg_build_sdist_falta` / `..._sin_declarar` | que `only-include` y artefacto dejen de corresponderse |
| `sg_build_sdist_esencial_ausente` | que el sdist deje de poder reconstruirse y probarse |

## 4. Lo que encontró el checker al ejecutarse

### 4.1 El sdist declaraba nueve rutas y llevaba catorce

Con el `include` original (9 entradas) el artefacto sale con **14 rutas de
primer nivel**: `bench/` y `docs/` viajan sin estar declaradas. Cambiando un
solo patrón de la lista, también se cuela `audits/`.

Motivo: el `include` de hatchling es un **filtro**, no una lista blanca
(`builders/config.py`: `path_is_included`); `only-include` sí es lista blanca.
Corregido a `only-include`. El conjunto que viaja **no cambia**; lo que
cambia es que el artefacto queda determinado por la lista.

### 4.2 Un `pytest.skip` que nunca se tomaba

`tests/test_cli_uat.py:370` saltaba si faltaba `docs/blueprint/plan/UAT.md`.
El fichero está versionado, así que la rama no se tomaba nunca, y llevaba
`pragma: no cover`. `AGENTS.md §6.2` prohíbe `pytest.skip` para esconder
fallos.

Verificado con un contraejemplo real:

```
$ mv docs/blueprint/plan/UAT.md /tmp/
$ pytest tests/test_cli_uat.py::test_uats_can_be_loaded_as_documentation
FAILED ... AssertionError        # antes: "1 skipped"
$ mv /tmp/UAT.md docs/blueprint/plan/UAT.md
1 passed                          # restaurado byte a byte
```

## 5. Mutaciones: 7/7, y dos nacieron de ellas

Primera pasada: **5/7**.

| | Mutación | Código | Lo caza |
|---|---|---|---|
| M1 | `packages` reducido | `sg_build_modulo_faltante` | script + test |
| M2 | `version path` a otro fichero | deriva de versión | script + test |
| M3 | target `skillgraph.cli:principal` | `sg_build_target_no_resoluble` | script + test |
| M4 | `exclude` de `py.typed` | `sg_build_py_typed_ausente` | script + test |
| M5 | sin `tests` en `only-include` | `sg_build_sdist_esencial_ausente` | script + test |
| M6 | `only-include` → `include` | `sg_build_sdist_sin_declarar` | script + test |
| M7 | declara `external` (gitignored) | `sg_build_sdist_falta` | script + test |

### Los dos agujeros que abrieron

**M3 — comparar lo declarado con lo publicado es tautología a medias.** Lo
publicado **se deriva** de lo declarado. Un target equivocado sale idéntico
en los dos lados mientras el comando no existe. Solo importar el módulo
distingue «declaré algo que existe» de «declaré algo que no existe y el
backend lo copió sin mirarlo».

**M5 — una lista más corta no contradice a nada.** Quitar `tests` del
`only-include` reduce el sdist y ningún check de git lo nota: no es una
promesa rota, es una promesa **retirada**.

### Las dos que NO debían cazarse

M4 en su forma original (quitar el `include` del wheel) y M6 en su forma
original (declarar `audits`) eran **mutaciones inválidas**, no fallos del
contrato: `packages` ya recoge el directorio entero, y `audits` sí está
versionado. **Un contraejemplo que no debe cazarse también es un dato.**

## 6. Verificación

- **Suite completa**: `2605 passed in 130.06s` (estado ya commiteado, sin
  edición concurrente).
- **CI canónica**: `Pipeline finished with SUCCESS`, **7/7 stages**, run
  `c7c5790a-e532-46f9-a712-9b8996a81b54`, **0 `StepFailed`**, 10
  `StepStarted`, línea `2605 passed in 236.22s` en el journal.
- **SHA-256** de `.pipeline.kts` =
  `224643595e637cb70bef837a4e083987581c15278ddad54bd7451c7a2bd6b3f9`
  (sin drift respecto al commit `7e43585`).
- **Lint/format**: limpios, 259 ficheros.
- **SemVer**: `derive_semver.py` → `b/f/x/n/d: 0/1/3/4/0` → **MINOR**.
- **Gobernanza**: `test_release_governance`,
  `test_state_release_integrity` y el guard del CHANGELOG verdes tras el
  bump a `.dev0`.

## 7. Corrida contaminada, registrada

Una corrida intermedia de `scripts/coverage.sh` dio 2 failed en
`test_wi89_audit_writes_outside_repo.py::TestTheTestHelpersThemselvesWriteOutside`.
**No se ha reproducido**: la suite sin instrumentar y la CI canónica (con
instrumentación) pasaron ambas.

Los dos tests comparan `git status --porcelain` antes y después de un
subproceso de ~1–2 s. La causa más probable es edición concurrente del agente
sobre `AGENTS.md` durante la corrida. Se registra como **corrida
contaminada**, no como flakiness del repo, y no se abre frente.

**Los dos únicos tests que fallaron eran, exacta y solamente, los dos que
leen el estado del árbol.**

## 8. Deuda registrada, no abierta

- `tests/test_wi41_cli_dispatch.py`: `pytest.skip("auditoria del dia no
  generada todavia")`. El gate D1 lee
  `audits/architecture-debt-<hoy>.md`; el último versionado es del
  `2026-10-01`. El gate sólo se ejecuta el día exacto en que se genera el
  informe. Mismo patrón que el skip arreglado aquí, pero fuera de la
  superficie.
- `src/skillgraph.egg-info/` y `dist/` con un wheel de la `v0.7.0`: residuo
  local, gitignored, y el contrato nuevo los excluiría si colaran en un
  artefacto. No son deuda.

## 9. Estado

**SIN PUSH.** 88 commits sin publicar; `origin/main` en `0ebbd58`.
