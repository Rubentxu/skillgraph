# WI-89 — Verificación: la auditoría no escribe dentro del repositorio que audita

- **Ciclo**: `p-b7740b96d79ec013/wi-89-audit-writes-outside-repo`
- **Commit**: `64a28a8`
- **Fecha**: 2026-10-02
- **Suite**: 2463 passed (2451 antes; +12)

## La premisa registrada en WI-87 era condicional

El seguimiento que dejó el bloque anterior decía, con md5 como prueba, que «9 tests
verdes cambian el fichero». Re-medido en un árbol limpio **no se reproduce**:

```
=== ANTES ===   (vacio = limpio)
dc8ef675…  audits/architecture-debt-2026-10-02.md
=== RUN de test_audit_debt_smoke + test_audit_debt_accuracy ===
.........  9 passed in 4.09s
=== DESPUES ===  (vacio = limpio)
dc8ef675…  audits/architecture-debt-2026-10-02.md   ← md5 idéntico
```

El motivo: el informe commiteado estaba al día, y regenerarlo produce bytes
idénticos. Mi redacción presentó como incondicional algo que sólo ocurre cuando el
informe está caducado. La consigna lo llama «alerta de deuda sin verificar»: aquí la
alerta era real pero mi medición describía mal su alcance.

## El defecto real, y por qué es peor de lo que decía

`audit_debt.py` tomaba el destino de `AUDITS_DIR = pathlib.Path("audits")`, relativo
al cwd, y el nombre del fichero lleva la fecha de ejecución
(`today = datetime.now(UTC).date()`, línea 168). Como `audits/` está **trackeado**
(63 ficheros; sólo `audits/*-audit-bundle.tar.gz` está en `.gitignore`), hay dos modos
de fallo:

| Modo | Condición | Efecto en git |
|---|---|---|
| 1 | el código cambió desde la última generación | `M audits/architecture-debt-<hoy>.md` |
| 2 | no hay informe para hoy (primera corrida del día) | `?? audits/architecture-debt-<hoy>.md` |

El modo 2 **no requiere que cambie nada**. Demostrado con fecha `2099-01-01` sobre una
copia del script en un sandbox:

```
$ python3 audit_debt.py
audits/architecture-debt-2099-01-01.md
```

y su efecto en el repositorio real, creating y revirtiendo el fichero:

```
$ printf 'x\n' > audits/architecture-debt-2099-01-01.md
$ git status --porcelain
?? audits/architecture-debt-2099-01-01.md
```

El defecto no es «la suite ensucia el árbol»: es que **una herramienta de auditoría
escribe dentro del repositorio que audita**, con un nombre derivado de la fecha de
ejecución.

Había además un segundo defecto en el mismo fichero: `AUDITS_DIR.mkdir(exist_ok=True)`
estaba a **nivel de módulo**, luego importar el script ya creaba un directorio. Eso es
un efecto lateral del `import`, no de su trabajo.

## Por qué un sandbox no bastaba

`test_audit_debt_accuracy.py::_measure` recorre `_PROJECT_ROOT/src` y compara la cc
**medida** con las cifras **citadas en el informe**. Si se moviera también el origen,
el test compararía el árbol real contra un informe de otro árbol y pasaría sin comprobar
nada. De ahí que se parametricen origen y destino por separado, y que una red nueva
verifique que el informe sigue describiendo el árbol real comparando su recuento de
módulos con el de `src/`.

## La red, y por qué la primera versión no vigilaba nada

La primera red invocaba el auditor **con `--out-dir`** y comparaba `git status` antes y
después. Eso protege de nada: si alguien revierte los helpers de los tests, la
invocación del guard sigue siendo la que no se revirtió. Las dos mutaciones que lo
demostraron:

- **M4** (`--src-root` ignorado) no fue cazada porque el test usaba `cwd=tmp_path` y un
  `src/` de juguete que coincidía con el default cwd-relativo. Los dos caminos eran
  indistinguibles. Corregido: `cwd=REPO_ROOT` y `--src-root <juguete>`, y se compara el
  recuento de módulos.
- **M5** (helper revertido al camino viejo) no fue cazada por lo mismo, y además
  `git status` pasaba **inocente**: el informe estaba al día, así que la escritura
  dentro del repo no cambiaba nada. El guard sólo dispara si se recrea la precondición
  real.

La red final ejecuta los `_run_audit()` **de verdad** de los dos ficheros de test y
comprueba a dónde apuntan. Esa aserción —«la ruta impresa no está dentro del
repositorio»— no depende de que el informe esté caducado. La comparación de
`git status` queda como cobertura secundaria del modo 1.

## Mutaciones

| # | Mutación | Resultado |
|---|---|---|
| M1 | `--out-dir` se ignora, destino cwd-relativo | **cazada** |
| M2 | `mkdir` de vuelta a nivel de módulo | **cazada** |
| M3 | stdout imprime una ruta distinta de la escrita | **cazada** |
| M4 | `--src-root` se ignora | **cazada** |
| M5 | helper al camino viejo **+** informe caducado | **cazada** |

`cazadas=5  no-cazadas=0`

M5 es compuesta a propósito: el guard compara antes y después, así que con el informe
al día pasaría verde. Recrear la precondición es parte de la mutación.

## Conocimiento negativo

- **Un md5 que no cambia no es un «no pasa», es un «no se midió».** La primera vez que
  medí este defecto, el informe estaba caducado porque WI-87 había cambiado el código.
  Al re-measurearlo en un árbol limpio, la condición había desaparecido. La registré
  como incondicional porque la medición lo fue en su momento.
- **Una guarda que invoca su propia copia del código no guarda ese código.** El guard
  tiene que ejecutar el camino que otros ejecutan; si invoca el suyo, revertir el otro
  no lo mueve.
- **Un guard que compara antes/después solo ve lo que cambia.** Con el estado actual
  al día, la mitad de la propiedad es invisible. La aserción útil es sobre el
  *destino*, no sobre el efecto.
- **`ruff format audits/` reescribe recibos históricos.** Formatear el directorio
  reescribió bloques Python embebidos en `audits/release-v0.15.0-receipt.md` y
  `release-v0.16.0-receipt.md`. Son evidencia congelada de releases pasadas, así que
  se revirtieron. El alcance canónico del proyecto es `ruff format src tests`; salir
  de él reformatea documentos.
- **El conjunto de restauración de un script de mutación debe incluir lo que la
  mutación puede tocar, no solo el código fuente.** M5 escribe informes en `audits/`
  por diseño. Restaurarlos con `git checkout` habría destruido el fix sin commitear,
  así que se guardan por contenido.
- **Comparar contra HEAD en un árbol con trabajo sin commitear falla siempre.** El
  control de WI-88 ya lo había trippedado, y aquí volvió a aparecer: la línea base
  debe ser el estado de partida del script, no HEAD.

## Resultado

- 5 tests nuevos (`test_wi89_audit_writes_outside_repo.py`), 25 en la suite de
  auditoría.
- Suite completa: **2463 passed in 105.06s** (lo reportó el pre-commit).
- **El hook de pre-commit, que antes dejaba `M audits/architecture-debt-<hoy>.md`,
  deja ahora el árbol limpio.** Es la comprobación que importa: el defecto era visible
  en cada commit desde el propio hook.
