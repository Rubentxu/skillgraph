# Verificación WI-103 — el gate de `main` solo existía los días con informe

- **Ciclo**: `p-b7740b96d79ec013/wi103-gate-conditional-al-artefacto`
- **Sesión**: `wi103-20261003T001100Z`
- **Fecha**: 2026-10-03
- **Run de certificación**: `9db8a440-1031-4c4a-98c9-3fee571c9999`
  — 8/8 stages, **2677 passed, 0 skipped**, 0 `StepFailed`, árbol quieto
- **SHA-256 de `.pipeline.kts`**: sin cambios (`d8658968…3ddcc`)

---

## 1. Cómo apareció

La re-certificación del estado final de WI-102 dio `2672 passed, **1 skipped**`
donde la certificación del código había dado `2673 passed` sin skips. El skip:

```
SKIPPED [1] tests/test_wi41_cli_dispatch.py:284: auditoria del dia no generada todavia
```

La fecha rolloveró a `2026-10-03` durante la sesión, y el informe de ese día
no existía. El gate pasó a ser un no-op.

## 2. El hallazgo, medido

`TestAuditGateForMain::test_main_no_esta_en_hotspots_publicos` declara una
propiedad sobre el **código** —«`main` no debe listarse como hotspot público,
cc≥20»— y la comprobaba leyendo `audits/architecture-debt-<HOY>.md`, con
`pytest.skip` si ese fichero no existía.

Script autocontrolado `.pipelinek/wi103_measure.sh`, con `audits/` (que está
versionado) restaurado y `sha256` verificado al salir:

| situación | resultado |
|---|---|
| sin informe de hoy | **SKIPPED, exit 0** |
| informe de hoy generado por el auditor | 1 **passed** (hoy `main` no es hotspot) |
| informe de hoy con `main` inyectado en la sección de hotspots | 1 **failed, exit 1** |

**La propiedad es real y el gate muerde cuando el artefacto está. El defecto
es la existencia del artefacto.**

| | |
|---|---|
| informes `architecture-debt-*` | **6** |
| rango | `2026-09-26` … `2026-10-02` |
| días transcurridos | 7 |
| días **sin** informe | 1 (`2026-09-30`) |
| hoy (`2026-10-03`) | sin informe → **gate inactivo** |

Un gate que solo corre cuando alguien se acuerda de correr el auditor no es
un gate: es un registro de que alguien lo corrió. Y `AGENTS.md §6.2` dice
literalmente: «NO usar `pytest.skip` para esconder fallos».

## 3. El arreglo: que el gate mida

`tests/_gate_main_hotspot.py::hotspots_publicos(arbol, *, out_dir)` ejecuta
`audits/audit_debt.py` con `--src-root` apuntando al árbol que se le pase y
`--out-dir` a un temporal, y devuelve los nombres públicos con `cc>=20`.

Ambos son parámetros desde WI-89, que los hizo parámetros precisamente para
que un test pudiera auditar sin mutar `audits/` — que tiene **51 ficheros
versionados**.

El análisis se hace con `audits/audit_debt.py`, no con una cuenta propia.
Reimplementar la métrica sería tener dos verdades sobre «qué es un hotspot»,
y la segunda dejaría de coincidir con la primera el día que el umbral cambie.

Tres propiedades que gana:

1. **Siempre activo** — no depende de que hoy alguien genere el informe.
2. **Siempre fresco** — antes validaba un snapshot de la última vez que se
   corrió; ahora valida el código como está.
3. **Sin efectos secundarios** — escribe en un temporal; `audits/` intacto
   (`test_no_escribe_en_audits` lo comprueba).

## 4. El contraejemplo es parte del arreglo

Sin un test que ponga un `main` real de `cc>=20` en un árbol y exija que la
medición lo vea, **una medición que devolviera siempre `()` habría pasado
todo verde** — indistinguible de la que no mide nada.

Es la diferencia entre un gate roto y un gate que no existe, y es
indistinguible por construcción hasta que se degrada a propósito. M2 es
exactamente esa degradación.

`test_la_medicion_detecta_un_main_realmente_hotspot` construye el árbol por
generación (25 `if` ⇒ cc=26, el algoritmo del auditor es
`1 + nº de If/For/While/With/Try`), así que el número no depende de contar
líneas a mano.

## 5. Un guard que se escribió mal de la primera

El guard que prohíbe el `skip` buscaba la cadena `skip` en el fuente del
módulo. Se puso en rojo **por su propio docstring**, que explica el defecto
que arregla:

```
E  'skip' is contained here:
E  n `pytest.skip` si ese fichero no
E  ?           ++++
```

Un guard que busca una palabra encuentra la palabra, no la propiedad. Es la
serie completa de este bloque en una línea, y la razón por la que el guard
se reescribió sobre el **árbol de sintaxis**: un módulo que no importa
`pytest` no puede llamar a `pytest.skip`. M3 introduce el `skip` por la puerta
de atrás —dentro del helper, un nivel más abajo— y el guard lo ve.

## 6. Mutaciones — 5/5 en rojo

`.pipelinek/wi103_mutate.sh` + `wi103_muts/m1..m5.py`.

| # | mutación | guard vigilado | resultado |
|---|---|---|---|
| M1 | umbral `20_000`, inalcanzable | `…detecta_un_main_realmente_hotspot` | ROJO |
| M2 | la medición devuelve siempre `()` | `…detecta_un_main_realmente_hotspot` | ROJO |
| M3 | la medición vuelve a saltarse | `…no_puede_saltarse_ninguna_vez` | ROJO |
| M4 | la medición vuelve a leer un snapshot fechado | `…arbol_real_no_tiene_main…` | ROJO |
| M5 | `out_dir` pasa a posicional | `…no_es_una_cadena_vacia` | ROJO |

**M1 y M2 son degradaciones por incapacidad, no por ignorancia**: el guard
sigue leyendo ficheros y ejecutando el auditor, y su veredicto es el
correcto para un umbral o una medición que nadie alcanza. Un guard que no
puede fallar es indistinguible de uno que aprueba todo.

**M5** deshace en una línea el parámetro de WI-89: con `out_dir` posicional,
un llamador nuevo puede auditar y escribir en `audits/`, que está versionado.

## 7. Certificación

| stage | outcome |
|---|---|
| `discover-repo` | success |
| `sync-deps` | success |
| `unit-tests` | success — **2677 passed in 231.72s** |
| `coverage-floors` | success |
| `package-build` | success |
| `ci-parity` | success |
| `lint` | success |
| `evidence` | success |

`Pipeline finished with SUCCESS`, **0 `StepFailed`**, 8/8, árbol quieto.

**2677 passed y 0 skipped.** Antes: 2672 passed + 1 skipped. La diferencia no
es un test nuevo: es el mismo test, que antes no se ejecutaba.

## 8. Criterios de aceptación

| # | criterio | estado |
|---|---|---|
| 1 | con `main` como hotspot, el gate **falla** (no se salta) | verificado (M1, M2) |
| 2 | sin hotspot, el gate **pasa** | verificado (`…arbol_real_no_tiene_main…`) |
| 3 | el gate **no se salta nunca** | verificado (M3, guard sobre AST) |
| 4 | el test **no escribe** en `audits/` | verificado (`test_no_escribe_en_audits`) |
| 5 | `test_wi40_audit_annals.py` intacto y verde | verificado (16 tests, `git diff` vacío) |
| 6 | mutaciones | **5/5 en rojo** |
| 7 | `ruff check` + `format --check` | verdes |
| 8 | receta canónica 8/8, **sin skips** | run `9db8a440` |

## 9. Lo que este bloque NO arregla

- **No genera el informe que falta.** Fabricar el artefacto para tapar el
  gate sería circular y además ensuciaría `audits/` con un fichero producido
  por un test.
- **No cambia la política de los 51 ficheros de `audits/`** ni los audita:
  decisión del mantenedor.
- **No audita el contenido de los informes ya escritos.** El gate vigila el
  código, que es lo que declara medir.
- **No toca** `.gitignore`, los 4 errores de `sddk lint`, los hooks sin
  instalar, ni las líneas CJK preexistentes.
- **No hay push.** Sin autorización del operador.
