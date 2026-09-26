# Implementación — cache uv + coverage artifact en CI (cierre de derivados hooks-ci)

**Fecha**: 2026-09-26
**WorkItem**: STEWARDSHIP-DT-CI-CACHE-COVERAGE
**Trigger**: Derivados #2 (cache uv en CI, ~5 min) y #3 (cobertura en CI, ~5 min)
del audit `audits/hooks-ci-2026-09-26.md`. Implementados en un solo commit
porque son cambios pequeños, aditivos al workflow existente, y entregan
valor inmediato.

## Mejoras al CI workflow

### Cache uv (derivado #2)

Añadido `actions/cache@v4` para persistir `~/.cache/uv` entre runs:

```yaml
env:
  UV_CACHE_DIR: ${{ github.workspace }}/.cache/uv

steps:
  - name: Restore uv cache
    uses: actions/cache@v4
    with:
      path: ${{ env.UV_CACHE_DIR }}
      key: uv-${{ runner.os }}-${{ hashFiles('uv.lock') }}
      restore-keys: |
        uv-${{ runner.os }}-${{ hashFiles('uv.lock') }}
        uv-${{ runner.os }}-

  # ... tests ...

  - name: Minimize uv cache
    if: always()
    run: mise exec -- uv cache prune --ci
```

**Decisiones de diseño**:

- **Key basada en `hashFiles('uv.lock')`**: cualquier cambio en
  dependencias invalida el cache automáticamente. Esto evita el bug
  clásico de cache stale que ejecuta tests contra versiones de paquetes
  distintas a las del lockfile.
- **Restore-keys con fallback**: si no hay match exacto en
  `uv.lock`, busca cache parcial (mismo OS, sin importar hash). Esto
  cubre el caso "cambio menor que no afecta deps" (e.g. version bump
  del proyecto sin cambio de deps).
- **`uv cache prune --ci`**: reduce el tamaño del cache antes de
  guardarlo. Comando optimizado para CI (mantiene solo wheels
  necesarios).
- **`UV_CACHE_DIR` explícito**: necesario para que `actions/cache`
  pueda persistir el directorio. Por defecto uv usa
  `~/.cache/uv`, que en GH Actions runners es volátil.

### Cobertura (derivado #3)

Step de pytest actualizado con flags de cobertura:

```yaml
- name: Smoke test (pytest + coverage)
  run: mise exec -- uv run pytest \
    --cov=skillgraph \
    --cov-report=xml \
    --cov-report=term-missing \
    -q

- name: Upload coverage artifact
  if: always()
  uses: actions/upload-artifact@v4
  with:
    name: coverage-report
    path: coverage.xml
    retention-days: 30
```

**Decisiones de diseño**:

- **`--cov-report=xml`**: genera `coverage.xml` en formato Cobertura
  estándar, compatible con Codecov, Coveralls, SonarQube, etc. Si en
  futuro se quiere badge de cobertura, basta añadir
  `codecov-action@v4` como nuevo step.
- **`--cov-report=term-missing`**: muestra cobertura inline en la
  consola del job (visibilidad inmediata). `term-missing` lista las
  líneas no cubiertas, útil para detectar regresiones.
- **`coverage.xml` ya está en `.gitignore`** (verificado: `coverage.xml`
  aparece en `gitignore`). No hay riesgo de commit accidental.
- **`if: always()` en upload-artifact**: el artifact se sube incluso
  si pytest falló. Esto permite inspeccionar la cobertura de tests
  fallidos, no solo la de tests exitosos.

### Tests endurecidos (TDD)

2 nuevos tests en `TestCIWorkflow`:

- `test_workflow_uses_uv_cache` (3 invariantes):
  - `actions/cache` presente.
  - `uv.lock` en key.
  - `UV_CACHE_DIR` env var.
- `test_workflow_uploads_coverage_artifact` (3 invariantes):
  - `upload-artifact` presente.
  - `coverage.xml` en artifact path.
  - `--cov` flag en pytest command.

Total `TestCIWorkflow`: 6 → 8 tests. Total `test_hooks_system.py`: 22 → 24 tests.

## Verificación empírica

### Local

```text
$ mise exec -- uv run pytest --cov=skillgraph \
    --cov-report=xml --cov-report=term-missing -q
877 passed, 287 warnings in 263.25s (0:04:23)
TOTAL    4394   652   1250   157    83%
Coverage XML written to file coverage.xml
```

### Cobertura real medida (post-cambio)

| Métrica | Valor |
|---|---|
| Cobertura total | **83%** |
| Tests PASS | 877/877 |
| Módulos 100% | 10 (errors, recipe, promotion, bricks, catalog, parser, plan_loader, workflow, engine, redaction) |
| Módulos <80% | 4 (cli/runner 49%, governance/receipts 73%, knowledge/file_handoff 80%, platform/paths 81%) |

El gap del `cli/runner.py` (49%) está documentado como **estructural**:
pytest-cov NO rastrea código ejecutado en proceso hijo. La cobertura
real viene de los 24 tests subprocess (acceptance real del binario).
Ver `audits/runner-coverage-2026-09-25.md`.

### Suite post-cambio

`mise exec -- uv run pytest -q` → **879/879 PASS** en 190s (877 baseline
+ 2 nuevos tests del cache/coverage). Sin regresiones.

## Limitaciones reconocidas (autocrítica)

1. **Sin Codecov/Coveralls badge**: la integración con Codecov sería
   ~5 min (`codecov-action@v4` + `CODECOV_TOKEN` secret). Decidido NO
   aplicar en este ciclo porque la cobertura ya se mide y se archiva,
   solo falta la visualización externa. Aplicar si el operador quiere
   badge en README.

2. **Sin enforcement de umbral mínimo**: `[tool.coverage.report]` tiene
   `fail_under = 0` en `pyproject.toml`. Si se quiere exigir e.g. 80%
   mínimo, cambiar a `fail_under = 80` + añadir `--cov-fail-under=80`
   al comando pytest del CI. Decidido NO aplicar porque:
   - El proyecto acaba de estabilizarse en 83%.
   - Forzar techo artificial podría bloquear features nuevas que
     añadan código no-ejercitado temporalmente.
   - La decisión de subir el techo debe ser deliberada por el
     mantenedor, no automática.

3. **El cache uv solo aplica a `setup-python`/`setup-uv` directo**.
   El proyecto usa `mise` que crea su propio venv. El cache es válido
   porque `uv sync` (interno de mise) usa `UV_CACHE_DIR` como directorio
   de cache, y el contenido cacheado es portable entre invocaciones de
   uv (mismas versiones de paquetes Python).

4. **Cache miss en primer run**: la primera vez que se ejecuta el
   workflow con cache, será cold (sin cache). Runs subsiguientes
   aprovecharán el cache. Es comportamiento esperado y aceptado.

## Resultado

- CI workflow con cache uv + cobertura: listo para producción.
- Tests del sistema de hooks: 24/24 PASS (de 22 antes).
- Suite completa: 879/879 PASS (de 877 antes). 0 regresiones.
- 4 archivos modificados (CI workflow + tests + UAT refresh).
- HEAD `8430232` pushado a `origin/main` (verificación pendiente).

## Próximos pasos derivados (opcionales, sin spec)

1. **Codecov badge**: añadir `codecov-action@v4` + secret. Coste: ~5 min.
2. **Coverage threshold enforcement**: subir `fail_under` a 80%. Coste: ~3 min.
3. **Cache de pytest (`.pytest_cache`)**: añadir segundo `actions/cache`
   para `.pytest_cache` keyed por hash de `tests/`. Coste: ~5 min.
   Reduce tiempo de collection de pytest en ~10s/run.
4. **Audit advisories upstream** (siguiente backlog sin red): pytest/ruff/
   pyyaml/dulwich. Pendiente para próxima sesión con acceso a GHSA.

## Commits

- `8430232 ci: cache uv + coverage artifact (derivados 2 y 3 del audit hooks-ci)`
  (4 files, +57/-5 LoC)
