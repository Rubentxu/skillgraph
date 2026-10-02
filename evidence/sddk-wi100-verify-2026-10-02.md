# WI-100 — los hooks de git decían una cosa y hacían otra

**Fecha**: 2026-10-02
**Ciclo**: `p-b7740b96d79ec013/wi100-pre-push-delegates`
**Serie**: «¿qué declara el repo que nada comprueba?»

---

## 1. De dónde salió el bloque

WI-99 cerró la reproducibilidad de la evidencia de auditoría y dejó
escrito, en dos sitios, que `scripts/hooks/pre-push` quedaba como **deuda
medida y no resuelta**: mide con un instrumento distinto del canónico y su
exclusión del invariante C4 estaba escrita en el checker y fijada por un
test.

Una deuda con dueño escrito es una promesa. Este bloque la paga.

---

## 2. La medición, con el mismo instrumento en los dos lados

Mismo commit, mismo `.coverage.rc`, misma suite. **Única variable**: el
hook `.pth` que `scripts/coverage.sh` instala para que los subprocesos se
midan.

| módulo | hooks (lo que ve el pre-push) | `coverage.sh` | Δ |
|---|---|---|---|
| `cli/commands/runs.py` | **39 %** | **88 %** | **−49** |
| `cli/runner.py` | 55 % | 79 % | −24 |
| `cli/support.py` | **69 %** | 86 % | **−17** |
| TOTAL | 90,79 % | 95,22 % | −4,4 |

`.coverage.parallel.*` = **0 ficheros** en la corrida sin hook: ningún
subproceso medido. Es exactamente el fallo que WI-98 había medido en el
runner remoto (39 %), reproducido aquí en local y sobre el estado actual.

**El dato que hace el hallazgo incontestable:** `cli/support.py` mide
**69 %** con el instrumento del pre-push, y el suelo que declara el propio
`AGENTS.md §6.3` para la CLI es **70 %**. El gate más cercano al push podía
dar **verde un paquete que no cumplía el suelo declarado**. Y no ejecutaba
ninguno de los cuatro contratos exigibles.

---

## 3. Lo que los hooks decían

El `pre-push` afirmaba en su cabecera:

> *«Si pasa aquí, el CI solo verifica que la ejecución es reproducible
> (mismo commit, mismas deps via uv.lock)»*

Eso describe un mundo anterior a WI-98, donde el CI remoto era un workflow
con sus propios pasos. Hoy el CI remoto **es** la receta canónica, con sus
ocho stages y sus cuatro contratos. El comentario afirmaba una capacidad
del gate que el gate no tenía.

El `pre-commit` afirmaba ser un smoke de ~10 s sobre los ficheros staged.
Medido:

| | anunciado | real |
|---|---|---|
| qué corre | «smoke, N files staged» | **la suite entera** |
| ficheros | los `.py` staged | los 2636 |
| duración | ~10 s | **124,29 s** |

Seleccionaba los `.py` staged en una línea y **no se los pasaba** a pytest.
El selector existía; la instrucción no. Doce veces el coste anunciado.

---

## 4. Qué se cambió

**1. `pre-push` delega.** Invoca `scripts/ci.sh`, que es el dueño de cómo
se llega a la receta canónica (resuelve `mise trust` y `.pipelinek/`). No
la reimplementa: la pide. El coste pasa de ~130 s a ~240 s, que es el de
la receta — y el bypass existe.

**2. `pre-commit` filtra de verdad.** `pytest -q $STAGED_PY`. Medido:
**0,83 s** frente a los 124,29 s anteriores.

**3. C4 se afina y la excepción desaparece.** La condición pasa de
«ejecuta pytest» a «**ejecuta pytest sobre el repo entero**»
(`check_ci_recipe_parity.py:452`, `filtra_por_ficheros` en
`check_ci_recipe_parity.py:306`). Un hook que filtra por paths no emite un
veredicto sobre el repo, y queda fuera sin necesitar una lista que lo diga.

> `DIRECTORIOS_NO_RECETA` **desaparece**. Una propiedad que hay que mantener
> al día no es una propiedad, es una suscripción — y la de WI-99 crecía
> cada vez que aparecía un caso.

**4. Siete guards de cadena pasan a medir propiedad.** Dos de ellos
**ejecutan** el hook sobre un repo de prueba con un `scripts/ci.sh` stub que
falla si se invoca: es la primera vez que este fichero comprueba
comportamiento y no forma. «El hook menciona el bypass» era indistinguible
de «el bypass funciona».

---

## 5. Dos fallos del propio guard, encontrados midiendo

Ninguno de los dos lo habría encontrado un test que pasara.

### 5.1 El guard no veía los hooks — por segunda vez

`rglob("*.sh")` no encuentra `pre-commit` ni `pre-push`: **no tienen
extensión**, se llaman así porque es como git los busca. El invariante daba
verde sin haber mirado nunca esos dos ficheros.

Es la **segunda vez** que pasa en este bloque. En WI-99, al inventariar,
`git ls-files | grep '\.sh$'` dejó fuera los dos hooks y no me di cuenta
hasta que conté cinco scripts donde había siete. Un guard que solo descubre
una sintaxis no vigila la otra: se esquiva cambiando de sintaxis, que es la
misma trampa de WI-98 por el otro lado.

Arreglo: descubrimiento por shebang (`es_script_shell`,
`check_ci_recipe_parity.py:286`).

### 5.2 Un `echo` hacía que el invariante diera verde

La mutación **M7 no cayó**. Degradar el `pre-commit` a su forma anterior —la
que corre el repo entero con el instrumento equivocado— dejaba el contrato
en verde.

El motivo: el hook tiene una línea de diagnóstico

```sh
echo "[pre-commit] smoke: pytest sobre $N_STAGED fichero(s) .py staged"
```

que tiene **las tres cosas** que el invariante miraba: la palabra `pytest`,
una variable que parece un path, y está en una orden ejecutable. Un guard
que confunde un **mensaje** con una **ejecución** no mide qué corre: mide
qué se dice.

C4 llevaba **dos commits dando verde por el motivo equivocado**, y lo
encontró una mutación, no un test.

La regla correcta resultó ser *qué comando lanza la línea*, no *qué palabra
hay antes de pytest*: en ese `echo` la palabra anterior es `smoke:`, no
`echo`, así que la regla de proximité tampoco servía. Se decide por el
primer token no estructural — y si es un verbo de shell que no ejecuta
programas, la línea no puede estar invocando pytest
(`_VERBOS_DE_MENCION`, `check_ci_recipe_parity.py:210`).

Es una lista de **palabras del lenguaje**, no de ficheros del repo. Esa es
la diferencia con la lista que WI-99 quitó: añadir un `verify.sh` nuevo no
la desactualiza.

De paso, `pytest src/` —un directorio— también selecciona. Reconocer solo
ficheros `.py` habría hecho que un directorio se contara como suite entera:
el falso verde opuesto.

---

## 6. Un bucle encontrado por el camino

El test que mide si el smoke es rápido usaba
`tests/test_hooks_system.py` como path. Ese fichero **contiene el test del
smoke**, así que el smoke corría un fichero que se llamaba a sí mismo:
106 s y tres fallos.

No era solo un test lento. Era un hook que, al tocar su propio fichero de
tests, se llama a sí mismo. Ahora el test mide con dos módulos triviales en
`tmp_path`.

---

## 7. Mutaciones: 10/10

`bash .pipelinek/wi100_mutate.sh`, con autocontrol (árbol limpio, control
previo verde), restauración byte a byte y `rc` real:

| | mutación | qué tiene que ponerse rojo |
|---|---|---|
| M1 | `pre-push` con `pytest` a pelo — **el fichero real de `2bbb49e`** | contrato + tests |
| M2 | `pre-push` ejecuta pytest en vez de delegar | contrato + tests |
| M3 | la invocación del dueño lleva `\| tail` | tests |
| M4 | el bypass se declara pero no salta nada | tests |
| M5 | el hook no aborta cuando el dueño falla | tests |
| M6 | el hook no resuelve la raíz antes de verificar | tests |
| M7 | `pre-commit` corre la suite entera (**el bug de las 12×**) | contrato + tests |
| M8 | `STAGED_PY` entrecomillado | tests |
| M9 | el predicado de paths es ciego a las variables | tests |
| M10 | el descubrimiento solo ve por extensión | tests |

M4 es la más representativa de la serie: **el hook sigue diciendo
`HOOK_SKIP_PUSH_TESTS` en la cabecera**, así que el guard de cadena de WI-99
la habría aprobado. M1 usa el contraejemplo real, no uno inventado.

**M7 es la que encontró el fallo de §5.2.** Sin ella, el invariante habría
dado verde por el motivo equivocado indefinidamente.

---

## 8. Cierre

| criterio | medido |
|---|---|
| CI canónica | `Pipeline finished with SUCCESS`, run `8ccd1f6a-6477-4ad6-9dd9-02e5cd59ebb7`, **0 `StepFailed`** |
| suite | **2647 passed in 233.06s** (2636 antes; +11) |
| cobertura | **95,22 %** (suelo global 80 %; `cli/` 86,91 % contra 70 %) |
| `ci-parity` | *«…y ninguna otra receta ejecuta pytest por su cuenta»*, con los **7** scripts en el informe |
| `package-build` | el paquete construye y cumple su contrato |
| SemVer | `b/f/x/n/d: 0/0/3/3/0` → **PATCH → v0.20.1** |

`DIRECTORIOS_NO_RECETA` no existe. `scripts/hooks/` entra en el contrato.

---

> **Sobre qué commit está medida la certificación.** La tabla de arriba da
> el run `8ccd1f6a`, que certifica el **código** del bloque. La trazabilidad
> se escribió después, así que el estado de cierre tiene su propio run:
> `051942ff-b46a-428e-b316-721c586c415a`, `Pipeline finished with SUCCESS`,
> 8/8 stages, 0 `StepFailed`, **2647 passed in 228,82 s**, cobertura 95,22 %.
> Se citan los dos, y con cuál, en vez de decir «la CI» sin decir de qué.

## 9. Lo que este bloque NO resolvió

| | por qué |
|---|---|
| **El hook no está instalado** | MEDIDO: en la máquina donde se operaba, `.git/hooks/` solo tiene `pre-commit`; `pre-push` no. Instalar el git local del operador es suyo: `bash scripts/install-hooks.sh`. |
| **El `pre-commit` instalado es la copia anterior** | por lo mismo. Sin actualizar, cada commit sigue pagando 124 s. |
| **Crédenciales Anthropic/OpenAI** | ausentes; bloquean el criterio de salida de **H9** desde WI-91. |
| **103+ commits sin publicar** | `origin/main` en `0ebbd58`. Push no autorizado. |
| **`release.complete` inalcanzable** | exige `Cargo.toml`. Se cierra con `cycle supersede`. |
| **`ADR-0015` designa dos documentos distintos** | decisión del mantenedor. Fuera de alcance. |
| **4 errores de `sddk lint`** | perfil *autor de pack*; este repo es perfil *consumidor*. Sin opt-out, no está en ningún stage. |
| **63 informes en `audits/`** | política de datos. |

---

## 10. Lo que se aprendió

1. **Un guard que confunde un mensaje con una ejecución no mide qué corre:
   mide qué se dice.** Y dos commits de verde pueden venir de eso.
2. **Un guard que solo descubre una sintaxis no vigila la otra.** Pasó dos
   veces en el mismo bloque, por la misma razón.
3. **La mutación es un instrumento distinto del test, y ve cosas que el test
   no ve.** M7 encontró un falso positivo que cuatro tests no suspected.
4. **Una lista de palabras del lenguaje no es una lista de excepciones.**
   No se desactualiza cuando el repo crece; la de WI-99 sí.
5. **Un smoke que tarda 124 s no es un smoke, y nadie lo nota si lo que se
   comprueba es la cadena que lo anuncia.** Y si se comprueba que **diga**
   «smoke», el defecto es invisible por construcción.
