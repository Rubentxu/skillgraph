# release-failure-evidence — WI-45

Cycle: `p-74299cf88f51dab9/wi-45-uow-coverage`
WorkItem: `e01ff5ba-754c-4c27-8b60-a73056c9f6d3`
Phase: release · Status: RELEASE_PENDING
Date: 2026-09-27

## Resultado

**El release NO se puede ejecutar.** No por falta de calidad del trabajo
(verificado: ver `wi-45-verification-report.md`), sino por dos
incompatibilidades entre SDDK y los proyectos Python.

## Bloqueantes

### B1 — `VERSION LOCKSTEP ERROR`

```
$ sddk release plan --tag v0.16.2
error: VERSION LOCKSTEP ERROR: could not read
  /var/mnt/DiscoChino2-fast/Proyectos/python/skillgraph/Cargo.toml:
  No such file or directory (os error 2)
```

SDDK exige leer la versión de un `Cargo.toml`. Este proyecto es Python
(hatchling + uv) y su única fuente de verdad de versión es
`src/skillgraph/__init__.py:__version__`, tal y como establece la regla 12
de `AGENTS.md`.

Comprobado: el binario de SDDK contiene **0 referencias a `pyproject`**.
No hay ruta de lockstep para Python.

### B2 — `permissions.yaml` ausente

```
$ sddk release apply --tag v0.16.2
error: failed to read permissions registry
  /var/mnt/DiscoChino2-fast/Proyectos/python/skillgraph/permissions.yaml:
  No such file or directory (os error 2)
```

> **CORREGIDO el 2026-09-28.** Este diagnóstico era falso. `permissions.yaml`
> es un archivo **del proyecto**, en la raíz del repositorio, no del framework:
> el binario dice literalmente `create permissions.yaml at the repository root
> with an 'agents' mapping`, y la ruta del error es el cwd del repo. El
> `find $FRAMEWORK` de abajo buscó en el sitio equivocado y por eso no lo
> encontró. No es un defecto del framework. Ver
> `evidence/b1-b2-diagnosis-correction.md`. La conclusión operativa (no
> fabricarlo a ciegas) se mantiene, pero por otro motivo: es un registro
> default-deny y redactarlo para desbloquear el release sería fabricar la
> autorización.

El framework 1.171.2 **no provee** `permissions.yaml`
(`find $FRAMEWORK -name permissions.yaml` → sin resultados).

## Acciones rechazadas explícitamente

Ninguna de estas se ejecutó, y no deben ejecutarse:

| Acción | Por qué se rechaza |
|---|---|
| Fabricar un `Cargo.toml` | Mentiría sobre la naturaleza del proyecto: no hay Rust en el bootstrap (regla 8 de `AGENTS.md`) |
| Fabricar un `permissions.yaml` | Un registro de permisos inventado autoriza operaciones que nadie ha autorizado |
| `git tag` manual | La regla 12 prohíbe `tag --force` y exige que la etiqueta la fije el release |
| Bypass con `--no-verify` | El gate de SDDK existe para esto |
| Push a `origin/main` | Fuera de la autorización de esta sesión |

## Estado del código (completo y verificado, pero no liberado)

- 2 commits atómicos: `8ec0645`, `3237a94`
- 14 commits por delante de `origin/main`, **sin push**
- Árbol limpio
- Suite completa 1209 passed, 0 regresiones
- `platform/uow.py` al 100%

## Acción de recuperación

Requiere una decisión **del mantenedor**, no del agente:

1. **Reportar B1 y B2 al proyecto SDDK upstream**: el lockstep de
   versión debería admitir `pyproject.toml`/`hatch.version`, y el
   registro de permisos debería existir o ser opcional.
2. Hasta entonces, el release de SkillGraph queda bloqueado. La
   alternativa sería una release manual, que la regla 12 prohíbe.
