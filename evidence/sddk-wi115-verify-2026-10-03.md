# WI-115 — el estado declara una cifra y nadie la comprobaba

**Fecha**: 2026-10-03
**Ciclo**: `p-b7740b96d79ec013/wi115-state-total-truthfulness` (path `A-full`)
**Release**: **NINGUNA, Y POR REGLA** (ver §6)
**Serie**: «qué declara el repo que nada comprueba», decimoséptima vía

---

## 1. De dónde salió el workitem

De una línea que escribió el autor de WI-113, al registrar un descarte.
Decía, textualmente, que no existía ningún guard que comparase
`tests.total` con el recuento real, y lo anotó como una precisión sobre
por qué ese campo no había causado el fallo que se investigaba entonces.

Era cierto, y era exactamente el siguiente hueco. **La serie se había
puesto a tiro su propio siguiente workitem sin verlo**, y lo había
hecho su propio autor.

## 2. La medición, en las dos direcciones

`.pipelinek/wi115_measure.py`, con `STATE.yaml` restaurado byte a byte,
sha verificado antes y después, y el borrado en el `finally`:

```
STATE.yaml tests.total : 2834
tests colectados       : 2834
hoy coinciden: True

M1  tests.total = 2834 -> 2971:  governance rc=0  VERDE (NO LO VE)
M2  añadido 1 test (2835 colectados, estado en 2834):  rc=0  VERDE
```

Que hoy coincidan **no es la propiedad**. La propiedad es: si dejaran de
coincidir, ¿algo se pone rojo? La respuesta era no, por exceso y por
defecto.

## 3. Lo que le da gravedad, medido también

En WI-109 la primera certificación dio `2753 passed + 1 failed`, y **el
fallo era este campo**: el post-release bumpeaba `__init__.py` a
`0.22.0.dev0` y dejó `tests.package_version` en `0.21.2.dev0`, que es
justo el par que cruza
`test_release_governance.py::test_current_version_is_documented_in_state`.

El hermano pequeño quedó vigilado desde entonces. El grande no, y M1
dice que hoy tampoco.

## 4. El guard

El recuento se deriva del **árbol** con `pytest --collect-only` en un
subproceso, nunca del estado. Un guard que comparase contra una copia
escrita en el propio test sería el guard que compara contra su propia
copia —el error de WI-106—, que hoy acierta y el día que la verdad se
mueva dirá lo contrario con toda la autoridad de un test.

| propiedad | quién la mide |
|---|---|
| la cifra declarada es la que colecta el árbol | `test_el_total_declarado_es_el_total_colectado`, y el fallo **dice cuál es la buena** |
| el campo existe y es un entero | `test_el_campo_existe_y_es_un_entero` |
| el estado sigue parseando como YAML | `test_el_estado_sigue_leyendose_como_yaml` — WI-85 demostró que la sección `tests:` se puede tapar con un snapshot anidado por error |
| el recuento real se puede leer y es plausible | `test_el_recuento_real_se_puede_leer` |

**Tres de los cuatro son contrasaltos, y no es decoración.** Sin los dos
primeros, borrar el campo daría un `KeyError` que parece un fallo del
guard. Sin el último, el patrón de la salida de pytest podría dejar de
coincidir y el guard compararía contra un **cero silencioso** el día que
pytest cambie una cadena. De todo el guard depende esa cuarta propiedad,
y hay una mutación que la rompe a propósito.

**Por qué un test y no una etapa de la receta.** `.pipeline.kts` tiene un
SHA-256 declarado invariante desde WI-110 (`7541ced5…`). Añadir una
etapa sería cambiar ese invariante por un fallo que se cierra dentro de
la suite. Un test es un test; una etapa nueva es un contrato de CI.

**El recuento se cachea por sesión.** Sin cache el fichero lanzaría
cuatro subprocesos de colecta completa para leer siempre el mismo
número. Medido: **4,10 s → 2,34 s**.

## 5. Mutaciones: 3/3

| mutación | qué quita | veredicto |
|---|---|---|
| M1 | la aserción que manda | CAZADA |
| M2 | el patrón de la salida de pytest | CAZADA |
| M3 | el recuento se vuelve cero sin avisar | CAZADA |

**M2 es la que da sentido al guard entero.** Simula una actualización de
pytest que cambie el texto de su salida. El guard tiene que **fallar por
no poder medirse**, no pasar comparando un cero contra un número. Si
sobreviviera, el guard mentiría en verde el día que una dependencia
cambie una cadena.

M3 no apuntaba al principio: tenía ocho espacios de indentación donde el
texto real tenía cuatro. Se comprobó **antes** de mutar, que es la
diferencia con WI-113 y WI-114, donde la comprobación vino después.

## 6. SIN RELEASE, Y POR REGLA

```
== desde v0.22.5 hasta HEAD ==
  b/f/x/n/d: 0/0/0/4/4
  la regla dice SIN BUMP: no hay release que emitir, se acumula
```

Cero `feat`, cero `fix`. `AGENTS.md §12` es explícito: si la regla dice
sin bump **no se emite etiqueta**, el trabajo se acumula. Es el
**segundo** bloque de la serie que no libera, después de WI-106, y es
**la regla siguiendo, no la regla saltándose**.

`release.tag` y `release.semver_bump` **no se mueven**: describen la
última release real, no el workitem en curso. El guard de WI-96 compara
`semver_bump` contra lo que la herramienta calcula *para esa etiqueta*,
así que moverlos habría hecho que el estado describiera una release que
no existe.

## 7. Certificación

**Run**: `d934558a-4590-4b43-97c6-591c3cf1d7ce`
**Terminado**: `2026-10-03T12:27:22.445355477Z` (`RunFinished`)
**Resultado**: **8/8 etapas en `success`**, `2838 passed in 544.61s`,
0 skipped. A la primera, sin run de recuperación.

| etapa | outcome | occurred_at |
|---|---|---|
| discover-repo | success | 12:18:10.095613598Z |
| sync-deps | success | 12:18:10.216454139Z |
| unit-tests | success | 12:27:18.124417520Z |
| coverage-floors | success | 12:27:19.450390826Z |
| package-build | success | 12:27:21.873342499Z |
| ci-parity | success | 12:27:22.096653340Z |
| lint | success | 12:27:22.215223641Z |
| evidence | success | 12:27:22.445046938Z |

**La propiedad nueva se ve en el propio run**: `2838 passed` es
exactamente lo que `STATE.yaml` declaraba y lo que `--collect-only`
colecta. Por primera vez la cifra del estado no es una anotación sino
algo que el run comprueba de paso.

Antes de gastar el run se pasaron los **29 guards que leen los ficheros
de trazabilidad: 759 verdes**.

## 8. Errores propios registrados

- **38 — El subject de 74 caracteres, segunda vez en dos workitems.** En
  WI-114 fue el mismo error y lo enmendé. Aquí lo **medí** con
  `awk '{print length($0)}'`, salía 74, leí el número, y seguí. El
  instrumento estaba ahí y la lectura falló, que no es lo mismo que el
  instrumento. Enmendado porque el bloque no estaba publicado.

- **39 — Una sonda que no apuntaba, comprobada antes de contar.** M3 tenía
  ocho espacios donde el texto real tenía cuatro. El error 34 de WI-114
  por tercera vez, con la diferencia de que la comprobación de sondas
  está **antes** de mutar: el harness imprime `SOBLA`/`FALTA` para cada
  sonda y solo entonces cuenta. Esa es la forma correcta.

- **40 — El guard de WI-104 exigiendo una cita en el bloque vivo.** El
  bloque nuevo no tenía ninguna cita `fichero.py:LINEA::simbolo`, y el
  guard dijo `test_el_bloque_vivo_tiene_al_una_cita_que_verificar`. No es
  un defecto del guard: un bloque vivo que no señala nada comprobable es
  un bloque que no se puede auditar. La cita se resolvió en el AST:
  `tests/test_wi115_state_total_truthfulness.py:113::test_el_total_declarado_es_el_total_colectado`.

- **41 — La premisa de release escrita desde la convicción y no desde la
  herramienta.** Escribí «la regla pide PATCH → v0.22.6», avancé
  `release.tag`, añadí la entrada de `releases[]` y abrí la sección
  `[0.22.6]` del CHANGELOG **antes** de derivar la versión. En los
  quince workitems anteriores la herramienta se consultaba primero; aquí
  se dio por buena la regla de memoria. Lo dijo la herramienta al medir:
  `0/0/0/4/4`, SIN BUMP. Es exactamente el defecto que WI-106 vino a
  cerrar, repetido a unas pocas líneas de aquel mismo commit.

- **42 — El clasificador de la serie equivocándose sobre sí mismo.** El
  commit de corrección de 41 llevaba `fix(state)` porque «corrige», y eso
  bastó para que la herramienta pidiera PATCH — es decir, para que un
  commit **sin una línea de código** fabricara una release. Su contenido
  es trazabilidad, luego el tipo es `docs`. Enmendado, y el tramo vuelve
  a `0/0/0/5/0` SIN BUMP. Es el primer caso de la serie donde el commit
  que cierra una vía decide por error si esa vía libera. **El tipo se
  elige por lo que el commit contiene, nunca por la emoción del verbo que
  lo describe.**

## 9. Deuda registrada y NO abierta

Inalterada de los bloques anteriores, y con los mismos criterios ya
medidos: 51 informes fechados en `audits/` (política de datos), 14
`raise` de builtins en el dominio (medidos en WI-109, casi todos en
invariantes internas de adaptadores) y seis `assert` en producción
(§3.2.6 prohíbe `assert` en el DSL, no en la CLI).
