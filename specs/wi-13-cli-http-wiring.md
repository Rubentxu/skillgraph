# WI-13: CLI wiring del HttpAgentAdapter en `sg run`

## Objetivo

Cerrar el bucle del Adapter real (WI-12): permitir invocar `sg run`
con `--adapter http` para usar `HttpAgentAdapter` contra Anthropic u
OpenAI, manteniendo `fake` como default determinista.

## Decision previa (D-46)

- Adapter como **drop-in replacement** via Protocol `AgentAdapter`
  (D-41). El CLI no conoce implementaciones concretas: solo el helper
  `_build_adapter(args, fixtures_root)`.
- Default sigue siendo `fake` (compatibilidad con UAT fixtures).
- `http` requiere variable de entorno del proveedor (`ANTHROPIC_API_KEY`
  o `OPENAI_API_KEY`). Sin credenciales -> `ValidationError` tipado
  (exit code `EXIT_VALIDATION`).
- argparse valida `choices=['fake','http']` en la CLI; el helper
  re-valida con `ValidationError` para uso programatico.

## Cambios

### `src/skillgraph/cli/runner.py`

1. **Argumentos nuevos** en `cmd_run`:
   - `--adapter {fake,http}` (default `fake`)
   - `--llm-provider {anthropic,openai}` (default `anthropic`)
   - `--llm-model <str>` (default `None` = modelo recomendado)
   - `--llm-timeout-s <float>` (default `30.0`)

2. **Helper `_build_adapter(args, fixtures_root) -> Any`**:
   ```python
   def _build_adapter(args, fixtures_root):
       kind = getattr(args, "adapter", "fake")
       if kind == "fake":
           return FakeAgentAdapter(fixtures_root)
       if kind == "http":
           adapter = http_adapter_from_env(provider, model=model)
           if timeout_s != 30.0:
               object.__setattr__(adapter, "timeout_s", timeout_s)
           return adapter
       raise ValidationError(...)
   ```

3. **Llamada en `cmd_run`**: reemplaza
   `adapter = FakeAgentAdapter(fixtures_root)` por
   `adapter = _build_adapter(args, fixtures_root)`.

4. **Output CLI**: nueva linea `Tipo de adapter: {adapter_kind}`.

### `tests/test_cli_adapter_wiring.py` (nuevo, 11 tests)

- `TestAdapterCliBuildFake` (2 tests): default + explicit fake.
- `TestAdapterCliBuildHttp` (5 tests): anthropic, openai, custom
  model, custom timeout, default timeout.
- `TestAdapterCliBuildHttpMissingKey` (3 tests): missing key,
  cross-provider key mismatch.
- `TestAdapterCliBuildRejectsInvalid` (1 test): valor fuera de
  {fake,http} -> ValidationError.

## Compatibilidad

- **100% backward-compatible**: el default `--adapter=fake` reproduce
  exactamente el comportamiento previo. Los UAT tests existentes
  (16/16) no cambian.
- El Protocol `AgentAdapter` (D-41) permite drop-in replacement
  sin tocar RunController.

## Evidencia

- `uv run pytest tests/test_cli_adapter_wiring.py` -> 11/11 PASS
- `uv run pytest` (suite completa) -> **1020/1020 PASS** en 238.73s
  (era 1009, +11 nuevos)
- `uv run ruff check src tests` -> All checks passed
- `uv run ruff format --check src tests` -> 146 files already formatted
- `sg run --help` muestra los 4 nuevos flags correctamente

## Pendiente tras WI-13

- **T3 Threat model** (STRIDE/abuse-cases sobre superficie HTTP)
- **T5 Backups CLI** + **T6 Observabilidad**
- Deuda arquitectonica: H-01..H-06/H-10
- Push a origin (regla WI-01, ahora 26 commits ahead)
