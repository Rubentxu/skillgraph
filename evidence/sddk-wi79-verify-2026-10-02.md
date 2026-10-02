# WI-79 — el contrato de exit code de la CLI no lo fijaba ningún test

**Fecha**: 2026-10-02
**Ciclo SDDK**: `p-b7740b96d79ec013/wi-79-cli-exit-contract`
**Estado**: verificado, sin cambios en `src/`
**Suite**: 2260 → **2362 passed**

---

## 1. Hipótesis

`main()` termina en `sys.exit(main())`:

```python
# src/skillgraph/cli/runner.py
if __name__ == "__main__":
    sys.exit(main())
```

Si un handler de la tabla `_DISPATCH` devolviera `None` —porque su
último `return` se perdió, porque alguien escribió `return None`
explícito, o porque el cuerpo cae por el final— entonces
`sys.exit(None)` es **exit code 0**. El operador ve la ejecución como
correcta cuando el comando no cumplió nada.

Es la forma más silenciosa de falso éxito que puede tener este CLI: no
hay traceback, no hay stderr, no hay nada. Solo un `0`.

**No había un solo test que lo mirara.** `runner.py` está bien cubierto
en líneas, pero ninguna afirmación versa sobre la *forma* del retorno
de los handlers. `tests/test_wi57_dispatch_coverage.py` camina el árbol
del parser y afirma que `_DISPATCH` cubre todos los comandos
declarados: eso fija la **completitud** de la tabla, no la **forma** de
lo que devuelve cada handler. Son invariantes distintas y la segunda no
existía.

## 2. Construcción del instrumento

El hallazgo se buscó con un escáner AST, no por lectura. Su historia es
la parte instructive de este workitem, porque **el instrumento falló
dos veces antes de decir nada cierto**.

### v1 — filtro por anotación

Escaneaba todo `src/skillgraph` buscando funciones anotadas `-> int`
con un `return` que no devuelve valor.

**Resultado**: 3 candidatos, los tres en
`src/skillgraph/platform/ports/repositories.py`. Los tres son stubs de
`Protocol` cuyo cuerpo es `...` (`recover_interrupted_node_executions`
y dos `record_event`). Un método de `Protocol` nunca se invoca sobre la
clase stub, así que son **falsos positivos**. La v1 no vio ningún
handler del CLI porque el filtro era demasiado estrecho.

### v2 — extracción de la tabla rota

Se rehízo para partir de la tabla real `_DISPATCH` en vez de la
anotación. **Devolvió `handlers: []`**.

Un resultado vacío ahí parecería "nada sospechoso". No lo era: la
tabla se declara como

```python
_DISPATCH: Final[Mapping[str | tuple[str, str], Handler]] = MappingProxyType({...})
```

o sea un `AnnAssign` cuyo valor es un `Call` que envuelve un `Dict`. El
extractor buscaba un `Assign` con `Dict` directo, no encontraba nada, y
no llevaba la cuenta. **Ceguera del instrumento presentada como
resultado.** La v2 lleva ahora una guarda que aborta si la tabla no se
extrae:

```python
if not dispatch:
    raise SystemExit("!! _DISPATCH no extraida: el escaner no vio ningun handler.")
```

### v3 — el escáner era ciego al caso que buscaba

Con la extracción arreglada: 31 handlers, 0 sospechosos. Antes de
aceptarlo se validó el instrumento por mutación en las dos
direcciones — con `return None` en `cmd_runs_budget` y sin ella.

**La mutación no fue detectada.** Causa: en AST, `return None` es
`Return(value=Constant(None))`, es decir un `return` **con expresión**.
La v2 buscaba `Return.value is None`, que es el `return` a secas. El
escáner era ciego exactamente al caso interesante.

Reparado con `none_returns()`, que cubre las dos formas. Nueva
validación:

| Estado del árbol | Sospechosos |
|---|---|
| con `return None` (línea 201) | **1** — `('runs','budget') → cmd_runs_budget`, línea 201 |
| sin mutación | **0** |

## 3. Resultado del barrido

Con el instrumento validado en ambas direcciones:

| Métrica | Valor |
|---|---|
| Handlers en `_DISPATCH` | **31** |
| Anotados `-> int` | 31 / 31 |
| Con un `return` que produce `None` | **0** |
| Con cuerpo que cae por el final | **0** |
| `main` anotada `-> int` | sí |

**La hipótesis queda REFUTADA en el estado actual del código**: no hay
ningún handler capaz de producir exit 0 por devolver `None`.

Eso no significa que no pudiera haberlo. Significa que hoy no lo hay y
que **nada lo impediría mañana**. La red de tests es lo que convierte
"hoy no pasa" en "no puede pasar sin que la suite se ponga roja".

## 4. El oráculo: `tests/test_wi79_dispatch_exit_contract.py`

102 tests, parametrizados sobre `runner._DISPATCH` — la tabla es la
fuente de verdad, así que un handler nuevo queda cubierto por
construcción — más una clase conductual que invoca `main([...])` de
verdad.

| Test | Qué fija |
|---|---|
| `test_dispatch_table_is_not_empty` | Guarda de ceguera: si la tabla se vacía, el barrido aborta en vez de "pasar". |
| `test_handler_is_annotated_int` | Los 31 devuelven `int`. |
| `test_handler_never_returns_none` | Ni `return` vacío ni `return None` explícito. |
| `test_handler_body_terminates` | El cuerpo no cae por el final. |
| `test_failed_subcommand_does_not_report_success` | **Conductual**: un comando fallido no devuelve 0. |
| `test_skillgraph_error_is_translated_to_exit_domain` | Un `sg_*` llega a stderr con su código estable y sale como `EXIT_DOMAIN`. |
| `test_file_not_found_is_translated_to_project_not_found` | La rama `FileNotFoundError` sale como `EXIT_PROJECT_NOT_FOUND`. |

Los tres tests estáticos recorren la tabla entera en milisegundos. El
conductual es el que importa: es el que fallaría si alguien rompe el
comportamiento de verdad y el AST sigue verde.

## 5. Mutaciones

Seis mutaciones. Las seis acabaron cazadas, cada una por el test que le
corresponde. Sin mutación, una red verde no demuestra nada.

| # | Mutación | Resultado | Test que la caza |
|---|---|---|---|
| M1 | `return None` explícito en `cmd_runs_budget` | CAZADA | `test_handler_never_returns_none` |
| M2 | Quitar la anotación `-> int` de `cmd_runs_budget` | CAZADA | `test_handler_is_annotated_int` |
| M3 | Borrar el `return` final (el cuerpo cae por el final) | CAZADA | `test_handler_body_terminates` |
| M4 | `_open_project_storage` devuelve `EXIT_OK` en vez del error de `resolve_project` | CAZADA | `test_failed_subcommand_does_not_report_success` |
| M5 | `main` traduce `FileNotFoundError` a `EXIT_OK` | **NO cazada al principio** | → §6 |
| M6 | `resolve_project` devuelve `EXIT_OK` en vez de `EXIT_PROJECT_NOT_FOUND` | CAZADA | `test_failed_subcommand_does_not_report_success` |

### Una mutación que no aplicó

La primera versión de M4 fue un `sed` buscando
`    return EXIT_PROJECT_NOT_FOUND` en `support.py`. **No aplicó nada**:
la línea real es `support.py:90`, con 8 espacios y la forma
`return {}, EXIT_PROJECT_NOT_FOUND`, además dentro de
`_open_project_or_error` y no del camino que usa `cmd_runs_budget`.
`git diff` salió vacío y el "102 passed" era el árbol intacto.

Mutar una línea que no existe no prueba nada. El script de mutación
comprobó a partir de entonces con `git diff --quiet` que la mutación
aplicó **antes** de correr los tests, y aborta con
`MUTACION NO APLICO` si no.

## 6. El hallazgo real: una rama sin oráculo

M5 no la cazó nada. La causa no era el test: era que **la rama no la
ejercitaba nadie**.

`main` tiene dos `except`:

```python
    try:
        return handler(args)
    except SkillGraphError as exc:          # -> EXIT_DOMAIN
        ...
    except FileNotFoundError as exc:        # -> EXIT_PROJECT_NOT_FOUND
        ...
```

El test conductual usa `runs budget` sobre un proyecto inexistente. Ese
camino **no pasa por el segundo `except`**: `_open_project_storage`
resuelve el proyecto antes y devuelve su código de error. M4 y M6 lo
confirman: ambas mutan precisamente ese camino y las caza el mismo
test.

Para medir si **algún** test del proyecto vigilaba esa rama, se aplicó
M5 y se corrió la suite completa **sin** el fichero de WI-79:

```
2260 passed, 102 deselected in 92.70s
```

Cero fallos. `runner.py:254` podía convertirse en `return EXIT_OK` y
**los 2260 tests del proyecto se quedaban verdes**. El falso éxito más
grave del contrato de exit codes estaba en una rama sin vigilancia, y
no se habría detectado con el instrumento de cobertura: la línea está
en el fichero, y lo que falta no es ejecución, es la *afirmación*
sobre su valor.

Se añadió `test_file_not_found_is_translated_to_project_not_found`, que
sustituye `_resolve_handler` por un handler que lanza
`FileNotFoundError` y afirma la traducción. Con él, **M5 pasa a ser
cazada**.

Se sustituye `_resolve_handler` y no la entrada de `_DISPATCH` porque
la tabla es un `MappingProxyType`: es inmutable, y el contrato que
importa es el de la frontera de `main`.

## 7. Hallazgo lateral: `EXIT_USAGE` no es el código de un error de uso

`argparse` sale con **2**. El `EXIT_USAGE` canónico de la CLI es **1**
(`src/skillgraph/cli/support.py:47`).

Un operador o un script que clasifique los fallos por `EXIT_USAGE` no ve
los errores de invocación: caen en una categoría que el CLI no nombra.

No se corrige aquí. Los errores de `argparse` no son
`SkillGraphError`, así que AGENTS §1.2 no los cubre, y unificar los dos
códigos cambia el contrato externo de todos los tests de subproceso.
**Se fija el comportamiento real**, y el test falla si `argparse`
empieza a devolver `EXIT_USAGE`, de modo que el cambio tendría que ser
deliberado. Es una decisión de producto.

## 8. Lo que este workitem no hace

- **No toca `src/`.** Cero cambios de comportamiento. El código ya
  cumplía el contrato; lo que faltaba era que nadie lo comprobara.
- **No corrige el `EXIT_USAGE` de §7.** Reportado, no "arreglado".
- **No unifica** la red con `test_wi57_dispatch_coverage.py`. Son
  invariantes distintas (completitud de la tabla vs forma del retorno) y
  fusionarlas haría que un fallo dijera menos.
- **No mide cobertura con `coverage run`.** Con la instrumentación de
  WI-75 activa (`parallel = true` + hook `.pth`), el intento de aislar
  un `COVERAGE_FILE` no recoge `runner.py`. La medición por mutación
  contra la suite completa es aquí el oráculo correcto, y no depende del
  instrumento de cobertura.

## 9. Verificación

```
2260 passed in 94.33s        (CI canónica post-WI-78, sobre HEAD 40d78ae)
2362 passed                  (suite con la red WI-79)
ruff check: All checks passed!
ruff format --check: limpio
src/ sin modificar: 0 ficheros
```

Ciclo SDDK `p-b7740b96d79ec013/wi-79-cli-exit-contract` en
`RELEASE_PENDING` con 6 artefactos, a la espera de
`approval-system-cycle_supersede` como los demás.
