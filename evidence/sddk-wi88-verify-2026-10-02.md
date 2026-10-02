# WI-88 — Verificación: los errores de uso devuelven `EXIT_USAGE` y el 2 queda libre

- **Ciclo**: `p-b7740b96d79ec013/wi-88-unify-usage-exit-code`
- **ADR**: ADR-0016
- **Commits**: `0a3fd1a` (config de lint,_atómico aparte), `fix(cli)` (el contrato)
- **Fecha**: 2026-10-02

## El error de medición que casi lo da por cerrado

La decisión (f) de `next_workitem` decía que «el exit code de argparse (2) frente al
canónico `EXIT_USAGE` (1)» estaba pendiente. Al medirlo, la primera ejecución dio
**1 en los tres casos** — lo que habría significado «ya corregido».

Era falso. `shutil.which('sg')` devuelve `/usr/bin/sg`, que es la herramienta Unix de
grupos, **no la CLI de SkillGraph**. El console script real se llama `skillgraph`
(`pyproject.toml:39`). Los tres `1` mediados eran de otro programa, y sus tres
mensajes de stderr lo decían (`sg: el grupo «no-existe-comando» no existe`) y pasaron
desapercibidos.

Sin ese desvío, WI-88 se habría cerrado como «la premisa estaba caducada», que es
exactamente el movimiento que este bloque se repetía a sí mismo no hacer.

## La medición correcta

Con el binario real:

```
skillgraph (sin args)          -> 0   imprime ayuda
skillgraph no-existe-comando   -> 2   argparse
skillgraph runs budget         -> 2   argparse
skillgraph --no-existe-flag    -> 2   argparse
skillgraph project create "NOMBRE INVALIDO"  -> 2   EXIT_BAD_NAME
```

Y `EXIT_BAD_NAME` está vivo en `runner.py:131`, en `cmd_project_create`, cuando
`is_safe_name(args.name)` falla.

**La colisión, demostrada**: tres fallos sin relación —un nombre inválido, un comando
inexistente y un subcomando sin argumentos— devuelven el mismo número. Un script que
comprobara `rc == 2` para detectar un nombre inválido recibe un falso positivo ante
cualquier error de uso, y `EXIT_USAGE` (1) no se produce nunca.

## Lo que ya se sabía, y lo que faltaba

La contradicción estaba registrada en
`tests/test_wi79_dispatch_exit_contract.py:200-218`, que la consignaba a propósito:

> HALLAZGO DE CONTRATO (as-built, no corregir sin ADR): argparse sale con codigo 2,
> mientras que el `EXIT_USAGE` canonico de la CLI es 1. […] la unificacion es una
> decision de producto, no un fix de test.

Hasta ahí era correcto pero **incompleto**: hablaba de dos números que no coincidían, no
de un 2 que ya tenía dueño. Ese matiz es el que cambia el diagnóstico. Y hay dos
docstrings que lo confirman:

- `test_wi41_cli_dispatch.py:209-211` — «el `EXIT_USAGE` (1) de main es **dead code en
  la practica** porque argparse declara choices para todos los subcomandos».
- `test_cli_branches.py:296-301` — «Mantenemos la constante por si en el futuro
  queremos reportar errores de uso propios; este test documenta la frontera actual con
  argparse».

No era código muerto. Era **código secuestrado**: un número que nunca se produce no se
parece a código muerto, se parece a código inalcanzable. La diferencia importa, porque
el código muerto es inocuo y el inalcanzable esconde un defecto.

## La corrección

`parser.py` usa `_UsageParser`, que sobrescribe `error()` para salir con `EXIT_USAGE`.
Se descartaron dos alternativas:

- **Envolver `main` en `except SystemExit`**: no distinguiría el 2 de `argparse` del 2
  de un handler. Es la ambigüedad que se quiere eliminar, y no se puede eliminar
  *después* del hecho.
- **Mover `EXIT_BAD_NAME` a un código libre**: mueve el problema. El 2 es la convención
  de todas las CLIs de Unix; lo que sobra en esta CLI es el 1 que nunca se emitía.

`argparse` propaga `type(self)` a los subparsers y sub-subparsers (verificado antes de
diseñar sobre ello: raíz, sub y sub-sub salen del mismo tipo), y sólo hay **una**
instancia de `ArgumentParser` en `src/` (`parser.py:26`). La red comprueba los tres
niveles **por comportamiento**, no mirando la clase.

### Por qué un módulo hoja

`parser.py` es autocontenido a propósito: su docstring declara que sus únicos nombres
libres son `argparse`, `Path`, `int` y `float`. Los exit codes estaban en
`cli/support.py`, que importa `Storage`, `BrickRegistry`, `pack_loader`, `catalog`,
`plan_loader` y `workflow`.

Las dos salidas eran: romper la autocontención, o duplicar el literal —que es
exactamente el antipatrón que WI-87 eliminó media hora antes. Se creó
`cli/exit_codes.py`, un módulo hoja de doce `Final[int]` sin imports, y `support.py` lo
reexporta.

**Y el reexport casi se pierde por el camino.** La forma `X as X` es la que ruff
reconoce como reexport intencional; sin ella, F401 borró ocho de los doce nombres.
Medido: `EXIT_DOMAIN` dejó de exportarse y `cli/commands/expansion.py` dejó de
importar. Con `X as X`, ruff pasa a partir el bloque en doce sentencias, lo que se
resolvió aparte en `0a3fd1a` con `combine-as-imports` —que también tocaba tres módulos
sin relación con WI-88, y por eso es un commit aparte.

## Tests afectados

**Corrección de una medición propia.** La primera redacción de esta tabla decía «medidos
uno a uno, no contados» y listaba **6** sitios. Eran **10**. El `grep` que loslocalizó
estaba limitado a 20 resultados y se leyó como lista completa — el fallo exacto que la
frase pretendía evitar. La lista sin truncar, uno a uno:

| Test | Qué mide realmente | ¿Cambia? |
|---|---|---|
| `test_wi79_dispatch_exit_contract.py:213` | consigna la contradicción | sí → 1, y se reescribe |
| `test_wi57_dispatch_coverage.py:128` | sub desconocido de comando anidado | sí → 1 |
| `test_wi41_cli_dispatch.py:214` | comando inexistente; su nombre ya decía «usage» | sí → 1 |
| `test_wi58_policy_runs_subprocess.py:78` | `invalid choice` | sí → 1 |
| `test_cli_branches.py:305` | comando inexistente | sí → 1 |
| `test_cli_branches.py:353` | flag global inexistente | sí → 1 |
| `test_cli_branches.py:371` | subcomando inválido de `project` | sí → 1 |
| `test_cli_branches.py:389` | posicional de más en `project list` | sí → 1 |
| `test_cli_uat.py:334` | `EXIT_BAD_NAME` legítimo | **no** — pasa a ser el guardián del 2 |
| `test_uat_audit.py:120` | `uat_audit.main()`, **otra herramienta** | **no** — fuera de alcance |

Ocho cambian, dos se quedan. Cuatro de los ocho están en un solo fichero
(`test_cli_branches.py`), y por eso un recuento superficial da seis: cuatro asertos
parecidos en un sitio se leen como uno.

De los ocho, **dos tienen el nombre diciendo una cosa y el cuerpo la otra**:
`test_wi41_cli_dispatch.py` se llama `test_comando_desconocido_devuelve_usage` y
`test_wi57_dispatch_coverage.py` `..._is_argparse_usage`. Los dos nombres eran
correctos; los dos cuerpos mentían.

## Mutaciones

| # | Mutación | Resultado |
|---|---|---|
| M1 | se vuelve a `argparse.ArgumentParser` | **cazada** |
| M2 | `error()` sale con 2 | **cazada** |
| M3 | se traga el diagnóstico (imprime usage, no el motivo) | **cazada** |
| M4 | la clase no llega a los subparsers | **cazada** |
| M5 | `EXIT_BAD_NAME` deja de ser 2 | **cazada** |

`cazadas=5  imposibles=0  no-cazadas=0`

M4 es la que más importa: una corrección aplicada sólo a la raíz deja los niveles
internos devolviendo 2 sin que nada lo note, porque los tres errores de uso del
contrato se parecen entre sí.

### Una mutación contaminó el staging

La primera versión de M5 editaba `support.py` buscando un `return EXIT_BAD_NAME` que
vive en `runner.py`. El `replace` no aplicó nada, y el `# noqa: F401` que la mutación
dejaba puesto **no se restauró**, porque el script respaldaba `parser.py` y `runner.py`
pero no `support.py`. El commit se paró en el hook por `ruff check`.

Es el fallo que un control final existe para cazar, y por eso `support.py` entró en el
conjunto de respaldo. Un fichero que una mutación toca y el script no respalda es un
commit contaminado esperando.

## Conocimiento negativo

- **Medir el programa equivocado es la forma más barata de cerrar un defecto por
  error.** `sg` existe en `/usr/bin` y no es lo que parece. Tres resultados
  aparentemente correctos («ya devuelve 1») medidos sobre la herramienta equivocada.
- **Un número que nunca se produce no parece código muerto, parece código
  inalcanzable.** El repo llamó «dead code» a `EXIT_USAGE` en dos docstrings. Lo era
  en apariencia; la causa era que nada podía emitirlo.
- **Consignar un comportamiento real es correcto mientras sea inocuo.** La nota de
  WI-79 era acertada al fijar el 2, y dejó de serlo cuando `EXIT_BAD_NAME` empezó a
  devolver ese mismo número. Y el propio test que consagra el comportamiento fue el
  que dejó pasar la colisión.
- **Un recuento sobre una salida truncada es una suposición con formato de dato.**
  «6 sitios, medidos uno a uno» salió de un `grep | head -20` leído como lista
  completa. El nombre y el cuerpo de dos tests discrepaban, y ambos apuntaban en la
  dirección contraria: el nombre decía «usage» cuando el cuerpo decía 2.
- **Una primera red puede afirmar algo falso sobre el programa.** La versión inicial
  esperaba que `--version` lanzara `SystemExit`; es `action="store_true"`
  (`parser.py:37-39`) y no aborta. El test solo habría pasado si alguien cambiara la
  declaración, y mientras tanto describía mal el programa.
- **El linter no puede ver un reexport si no se le dice cómo.** F401 borró 8 de 12
  nombres en el primer intento. Misma familia que WI-81 (alias muertos) y WI-86
  (capa de re-export muerta): un reexport que el linter no reconoce como intencional
  no es un reexport, es un accidente a la espera de ocurrir.
