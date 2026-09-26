# Implementación — pre-push hook (cierre de derivado DT-HOOKS-CI #4)

**Fecha**: 2026-09-26
**WorkItem**: STEWARDSHIP-DT-PRE-PUSH-HOOK
**Trigger**: Derivado #4 del audit `audits/hooks-ci-2026-09-26.md`
("añadir pre-push hook que ejecute la suite completa de pytest antes
del push para evitar push que rompan CI"). Coste estimado: ~20 min.

## Problema resuelto

Hoy la defensa en profundidad del proyecto tiene 2 capas:

1. **Pre-commit hook** (`scripts/hooks/pre-commit`): ejecuta
   `ruff check` + `ruff format --check` + `pytest -q` (smoke) cuando
   hay `.py` staged. Atrapa regresiones triviales en commits.
2. **CI workflow** (`.github/workflows/ci.yml`): ejecuta la suite
   completa de pytest en cada push/PR a main.

**Gap**: entre el commit y el push no hay validación con la suite
completa. Si el dev pushea con tests flaky o con tests que requieren
el suite completo (concurrencia, UAT, integración), el CI detecta el
fallo **después** del push y tras esperar ~3 min de CI. Esto:

- Ensucia `main` con HEAD que rompen tests (necesita revert + fix).
- Rompe la confianza en el flujo "FF push → CI verde" (a veces falla).
- Reduce la velocidad efectiva del equipo (espera + fix + re-push).

## Solución implementada

**3ª capa: pre-push hook** (`scripts/hooks/pre-push`).

Shell POSIX (mismo patrón que `pre-commit`) que ejecuta la **suite
completa de pytest** (~190s) antes de aceptar el push. Si falla,
aborta el push con un error claro y muestra las últimas 30 líneas del
output de pytest.

### Capas de defensa (ahora 3)

```text
┌──────────────────────────────────────────────────────────────────┐
│ Local                                                            │
│                                                                  │
│  commit ──▶ pre-commit (lint + format + smoke pytest)            │
│     │                                                             │
│     ▼                                                             │
│  push   ──▶ pre-push (suite completa pytest, NUEVO)              │
│     │                                                             │
└─────┼────────────────────────────────────────────────────────────┘
      │
      ▼
┌──────────────────────────────────────────────────────────────────┐
│ Remoto (GitHub)                                                   │
│                                                                  │
│  CI workflow (lint + format + suite completa + cobertura)        │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### Bypass

- `git push --no-verify`: bypass completo (estándar de git).
- `HOOK_SKIP_PUSH_TESTS=1 git push`: salta la suite completa pero
  mantiene los demás gates. Útil para:
  - Ramas experimentales sin tests listos.
  - Smoke tests del propio sistema de hooks (e.g. verificar el installer).
  - Push de cambios puramente cosméticos (CI config, docs, .github/).

### Toolchain-aware

Mismo dispatcher `run_in_toolchain` que `pre-commit`: prefiere
`mise exec -- uv` (toolchain pinned en `mise.toml`), fallback a `uv`.

### Install (sin cambios)

El installer `scripts/install-hooks.sh` ya iteraba sobre
`scripts/hooks/*` (glob), así que copia automáticamente el nuevo
hook. Test `test_installer_copies_all_hooks` añadido para garantizar
que ningún hook futuro quede excluido por error.

## Bug encontrado durante implementación (autocrítica)

**Bug del `set -e` con pipe**: en la primera versión usé
`run_in_toolchain run pytest -q 2>&1 | tail -30 || { ... exit 1 }`.
El problema es que con `set -e` el exit code de un pipe es el del
**último** comando (`tail` siempre exit 0), así que la rama `|| { exit 1 }`
**nunca se ejecutaba**. Mismo bug documentado en `.pipeline.kts` (líneas 3-6).

**Fix**: capturar output a un tempfile con `mktemp` y mostrar las
últimas 30 líneas solo en la rama de error:

```sh
_log="$(mktemp)"
if ! run_in_toolchain run pytest -q >"$_log" 2>&1; then
    echo ""
    tail -30 "$_log"
    echo ""
    echo "ERROR: pytest failed (suite completa)."
    rm -f "$_log"
    exit 1
fi
rm -f "$_log"
```

**Lección**: aplicar siempre el patrón de `.pipeline.kts` cuando
haya que capturar output de un comando cuyo exit code importa.

## Limitaciones reconocidas

1. **Pre-push completo añade ~3 min por push**. En el bucle
   RED/GREEN del dev, esto se nota. Trade-off explícito: el coste
   local se paga para evitar el coste mayor de un CI fallido (espera
   + revert + re-push).

2. **Entorno del agente con `core.hooksPath` global**: el hook local
   no se ejecuta automáticamente en este entorno. Workaround: wrapper
   en `~/.git-hooks/pre-push` que delega al hook commiteable
   (mismo patrón que el pre-commit, ya documentado en
   `audits/hooks-ci-2026-09-26.md`).

3. **CI duplica la verificación**: el workflow también corre la
   suite completa en cada push. La duplicación es deliberada:
   defensa en profundidad. Si pre-push pasa, el CI solo verifica
   reproducibilidad (mismo commit, mismas deps via `uv.lock`).

4. **No hay smart-cache**: pre-push siempre corre la suite completa,
   incluso si solo cambió un doc. Trade-off vs simplicidad. Si se
   quiere cache, ver "Derivados opcionales" abajo.

5. **No detecta rama**: el hook corre siempre que se hace push,
   independientemente de la rama. Si se quiere skip para
   `push origin feature/foo`, ver "Derivados opcionales".

## Verificación empírica

### Suite final

```text
$ mise exec -- uv run pytest -q
........................................................................ [ 40%]
........................................................................ [ 48%]
........................................................................ [ 56%]
........................................................................ [ 64%]
........................................................................ [ 72%]
........................................................................ [ 81%]
........................................................................ [ 89%]
........................................................................ [ 97%]
........................                                                 [100%]
888 passed in 253.45s (0:04:13)
```

**888/888 PASS** en 253s (879 baseline + 9 nuevos: 8 TestPrePushHook +
1 test_installer_copies_all_hooks). 0 regresiones.

### Ruff

```text
$ mise exec -- uv run ruff check src tests
All checks passed!

$ mise exec -- uv run ruff format --check src tests
138 files already formatted
```

### E2E caso bypass OK

```text
$ HOOK_SKIP_PUSH_TESTS=1 bash scripts/hooks/pre-push
[pre-push] HOOK_SKIP_PUSH_TESTS=1 -> saltando suite completa
[pre-push] OK
```

### E2E caso fallo (simulado)

```text
$ # Patch temporal del hook para usar un fake pytest que exit 1
$ bash /tmp/pre-push-test
[pre-push] pytest -q (suite completa, puede tardar ~3min)...

fake pytest output line 1
fake pytest output line 2
FAILED tests/test_fake.py::test_x - assertion failed

ERROR: pytest failed (suite completa).
Bypass para ramas experimentales: HOOK_SKIP_PUSH_TESTS=1 git push
Bypass siempre: git push --no-verify
exit=1
PASS: hook aborta con exit 1
```

### E2E installer copia pre-push

```text
$ # En tmpdir con git init + scripts/hooks/{pre-commit,pre-push}
$ bash install-hooks.sh
Installed: /tmp/.../.git/hooks/pre-commit
Installed: /tmp/.../.git/hooks/pre-push

$ ls -la .git/hooks/pre-*
-rwxr-xr-x  .git/hooks/pre-commit
-rwxr-xr-x  .git/hooks/pre-push
```

Ambos quedan ejecutables tras install.

## Derivados opcionales

1. **Smart-cache por diff**: si el push no toca `.py` files, saltar
   la suite completa. Más complejo (requiere diff entre local y
   remote), ahorra ~3min en pushes solo-docs. Coste ~30 min.

2. **Skip por rama**: añadir `SKIP_PRE_PUSH_BRANCHES=feature/*,docs/*`
   como env var para saltar el hook en ramas conocidas. Riesgo: el
   dev puede olvidar borrar la rama y mergear a main sin tests.
   No recomendado sin ADR.

3. **Coverage pre-push**: ejecutar `pytest --cov` antes del push
   para tener feedback local de cobertura antes del CI. Trade-off:
   pytest con cobertura tarda ~30% más. Coste ~10 min.

4. **Pre-push paralelo con CI**: ejecutar el hook en background y
   mostrar el resultado al final. Avanzado, requiere async/await
   no disponible en shell POSIX. Coste >2h, sin valor claro.

## Conclusión

3ª capa de defensa operativa implementada y verificada end-to-end.
**Sin bump de release**: dev-infra, sin cambio de contrato observable.
Commits atómicos (código + state sync).

Defensa en profundidad completa:

```text
Local:  pre-commit (smoke) → pre-push (full) → push
Remoto: CI (full + coverage + cache uv)
```

Próximo ciclo opcional (sin spec del operador): cualquiera de los
4 derivados arriba, o spec del operador para S7+ (E1 Adapter real,
T5 Backups, T6 Observabilidad).
