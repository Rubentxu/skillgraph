# WI-109 — el `code` `sg_*` ya es la clave que traduce a exit codes

- **Fecha**: 2026-10-03
- **Ciclo SDDK**: `p-b7740b96d79ec013/wi109-code-a-exit` (path `A-full`)
- **Release**: `v0.22.0` (MINOR)
- **Serie**: «¿qué declara el repo que nada comprueba?», undécima vía
- **Commits**: `782470a` (código), `32adbb7` (trazabilidad),
  `bc5be8c` (release + tag), `cdc68d1` (post-release)

---

## 1. La consigna, y lo que la medición dijo de ella

La hipótesis de partida era `AGENTS.md §1.2`: *prohibido `raise ValueError`
/ `raise Exception` en código de dominio*.

Medida **antes de tocar nada**:

```
$ grep -rn 'raise ValueError\|raise Exception' src/
(cero coincidencias)
```

**La prohibición literal se cumple hoy.** Instrumentarla habría sido
vigilar una verdad que nadie puede romper, que es la peor versión de un
guard: uno que no puede fallar.

Lo que el dominio lanza de verdad, medido por **AST** y no por `grep`
(`.pipelinek/wi109_measure.py`, M2):

| excepción | ocurrencias | dónde |
|---|---|---|
| `TypeError` | 6 | `knowledge/file_handoff.py`, `knowledge/knowledge_controller.py` |
| `KeyError` | 5 | `platform/ports/dto.py` |
| `RuntimeError` | 2 | `governance/graph_expansion.py` (`unwrap()`) |
| `NotImplementedError` | 1 | `knowledge/file_handoff.py` |

Todas en invariantes internas de adaptadores, ninguna en el camino de
error que ve el usuario. **No se abre frente**: queda registrado en
`AGENTS.md §1.2` como deuda medida.

## 2. El defecto real: la tercera viñeta de §1.2

> *Cada excepción lleva un `code` estable (`sg_*`) usado por la CLI para
> traducir a exit codes.*

Era cierta, y no estaba instrumentada. Falsa por partida triple:

### 2.1 La traducción no existía

`src/skillgraph/cli/runner.py`, antes del cambio:

```python
except SkillGraphError as exc:
    print(f"ERROR ({exc.code}): {exc}", file=sys.stderr)
    return EXIT_DOMAIN          # <- 10 para TODO
```

`EXIT_PARSE` (11) y `EXIT_VALIDATION` (12) se alcanzaban **sólo**
porque cada comando repetía su propio `except ParseError`. La decisión
la tomaba el **tipo** en el sitio de la llamada; el `code` se imprimía
sin decidir nada.

### 2.2 Entrada de usuario malformada salía como traceback

```
$ skillgraph knowledge compile <p> '{"obligatory": ['
rc=1
Traceback (most recent call last):
  ...
json.decoder.JSONDecodeError: Expecting value: line 1 column 17
```

El `json.loads(args.recipe)` estaba **fuera** del `try` y
`JSONDecodeError` no es `SkillGraphError`. `main()` sólo captura
`SkillGraphError` y `FileNotFoundError`, así que escapaba entero.

### 2.3 Tres `code` no identificaban un error

Medido importando el paquete y leyendo el `code` **efectivo** (M4):

```
'sg_error'              -> SkillGraphError, SelfCertificationBlockedError,
                           HandoffBlockedError
'sg_invalid_expansion'  -> InvalidExpansionError,
                           ExpansionOnObsoleteRevisionError
```

Un `code` compartido no puede mapear a dos exit codes distintos, y
entonces el `code` deja de ser la clave: **la traducción prometida no se
podía construir encima de él**.

## 3. El experimento, con sonda

`.pipelinek/wi109_exp.py` mide por comportamiento, con baseline por hash
y `restore()` byte a byte verificado.

**Sonda de mutación** sobre `runner.py`: `return EXIT_PARSE` → `return 13`.

```
rc sin mutar = 11
rc mutado    = 13     -> sonda VÁLIDA
```

Sin esa sonda, el harness habría «medido» sin ver nada. Es la lección de
SESSION-JOURNAL 15/16: un harness que acusa al guard de lo que hizo el
entorno es peor que no medir.

**Restauración verificada** en los 2 ficheros mutados, con hash antes y
después.

## 4. Qué cambió

### 4.1 `exit_para(exc)` — la traducción

`src/skillgraph/cli/exit_codes.py`. Puro sobre `exc.code`; no mira la
clase, ni la jerarquía, ni disco, ni reloj.

Vive en el **módulo hoja que sigue sin importar nada** porque ADR-0016
lo movió allí para que `parser.py` consuma el contrato sin arrastrar
`Storage`, `pack_loader` y `workflow`. Una traducción en `runner.py`
sería inalcanzable desde `parser.py` y devolvería a la colisión con el
2 de `argparse` que ADR-0016 resolvió.

Un `code` desconocido cae en `EXIT_DOMAIN`, **nunca** en `EXIT_OK`: 0
significa éxito, y un error de dominio que sale con 0 es peor que uno
que sale con 10. Una excepción sin `code` (`FileNotFoundError` la
captura `main()`) también: `getattr(exc, "code", None)`, porque fallar
al traducir un fallo es el peor de los dos mundos.

### 4.2 `main()` cablea la traducción

`runner.py:256::main` → `return exit_para(exc)`.

### 4.3 Los dos `json.loads` de entrada, protegidos

- `cli/commands/knowledge.py:124` — la recipe es **entrada de usuario**.
- `cli/support.py:171` — un `plan.json` truncado es un artefacto
  corrupto, no una excepción de la stdlib.

Los dos convierten la excepción en `ParseError`, que es de dominio y
tiene `code` `sg_parse`.

### 4.4 Los tres `code` colisionados, con `code` propio

| clase | antes | ahora |
|---|---|---|
| `SelfCertificationBlockedError` | `sg_error` (heredado) | `sg_self_certification_blocked` |
| `HandoffBlockedError` | `sg_error` (heredado) | `sg_handoff_blocked` |
| `ExpansionOnObsoleteRevisionError` | `sg_invalid_expansion` (heredado) | `sg_expansion_on_obsolete_revision` |

### 4.5 Ramas que no distinguían nada

`cmd_knowledge_compile` tenía tres `if` consecutivos que devolvían
`EXIT_DOMAIN` **las tres**, y el último `return` alcanzaba todo lo demás.
No distinguían nada: sólo parecían distinguir.

## 5. Medido después, con el binario

```
$ skillgraph knowledge compile <p> '{"obligatory": ['
ERROR (sg_parse): recipe JSON invalido: Expecting value: line 1 column 17
                  (char 16). Pasa un source_id o un JSON literal completo.
rc=11

$ skillgraph knowledge compile <p> 'src-que-no-existe'
ERROR (sg_missing_obligatory): selector obligatorio no resolvio: ...
rc=10
```

`rc=1 + Traceback` → `rc=11 + ERROR (sg_parse)`.

**Los errores de dominio no distinguibles siguen en 10**, que es
exactamente lo que afirman 16 tests que ya existían (y ninguno de ellos
es `ParseError` o `ValidationError`, medido). Cambiarlo habría roto un
contrato as-built bien observado: en este bloque no se cambia
comportamiento observable que no sea el defecto.

## 6. El guard

`tests/test_wi109_code_to_exit.py`, 19 tests.

| propiedad | test |
|---|---|
| la traducción existe y es una función | `test_la_traduccion_existe_y_es_una_funcion` |
| es pura sobre el `code` | `test_la_traduccion_es_pura_sobre_el_code` |
| no puede depender de la clase | `test_la_traduccion_no_puede_depender_de_la_clase` |
| `sg_parse`→11, `sg_validation`→12 | `test_cada_code_mapea_a_su_exit_code` |
| `code` desconocido → 10, no 0 | `test_un_code_desconocido_cae_en_el_catch_all_de_dominio` |
| excepción sin `code` no revienta | `test_una_excepcion_sin_code_no_revienta_la_traduccion` |
| `main()` cablea, por AST | `test_main_usa_la_traduccion_y_no_el_catch_all_a_pelo` |
| la recipe malformada no sale como traceback | `test_recipe_json_malformada_no_escapa_como_traceback` |
| …y reporta su `code` | `test_recipe_json_malformada_reporta_el_code_del_error` |
| el camino bueno sigue bien | `test_recipe_valida_sigue_funcionando` |
| todo `json.loads` de la CLI bajo `try` | `test_todo_parseo_de_entrada_de_usuario_esta_protegido` |
| el guard ve algo (contraejemplo propio) | `test_hay_parseos_de_json_que_este_guard_vigila` |
| cada error declara su `code` | `test_cada_error_de_dominio_declara_su_propio_code` |
| ningún `code` comparte clase | `test_ningun_code_comparte_clase` |
| la comprobación de colisiones degrada | `test_la_medida_de_colisiones_detecta_el_defecto` |
| el `code` empieza por `sg_` | `test_todo_code_empieza_por_sg` |
| §1.2 dice cómo se comprueba | `test_la_regla_dice_como_se_comprueba` |

**El guard que mira el cableado mira el AST, no el texto.** La primera
versión buscaba la cadena `return EXIT_DOMAIN` y se puso **roja por su
propio comentario**, que explica por qué se sustituyó. Tercera vez en
tres semanas por el mismo motivo (WI-98 con rutas absolutas, WI-108 con
el patrón de `pytest.skip`): un guard que busca una cadena busca la
cadena.

## 7. Mutaciones: 11/11

`.pipelinek/wi109_mutate.py`, con baseline, `restore()` verificado y
control inicial (el guard debe estar verde sin mutar).

| | mutación | sonda | veredicto |
|---|---|---|---|
| M1 | `sg_parse` deja de dar 11 | `test_cada_code_mapea_a_su_exit_code` | CAZADA |
| M2 | `sg_validation` deja de dar 12 | idem | CAZADA |
| M3 | `code` desconocido sale con 0 | `test_un_code_desconocido_cae_...` | CAZADA |
| M4 | `main()` vuelve a `EXIT_DOMAIN` a pelo | `test_main_usa_la_traduccion...` | CAZADA |
| M5 | `SelfCertification...` recupera `sg_error` | `test_ningun_code_comparte_clase` | CAZADA |
| M6 | `HandoffBlocked...` comparte `sg_error` | `test_ningun_code_comparte_clase` | CAZADA |
| M6b | `HandoffBlocked...` deja de declarar `code` | `test_cada_error_de_dominio_declara...` | CAZADA |
| M7 | la subclase de expansion pierde su `code` | `test_cada_error_de_dominio_declara...` | CAZADA |
| M8 | `knowledge compile` saca el `try` del parseo | `test_recipe_json_malformada...` | CAZADA |
| M9 | el `ParseError` se degrada a `RuntimeError` | `test_recipe_json_malformada...` | CAZADA |
| M10 | `support.py` deja el `plan.json` sin `try` | `test_todo_parseo_de_entrada...` | CAZADA |

**9 cazadas, 0 inválidas, 0 no detectadas** → con M6b: **11/11**.

### La sonda de M6, y por qué su fallo era información

M6 no la cazó la sonda. La tentación era acusar al guard; lo correcto
era mirar qué mide cada uno. Resultado: `code = "sg_error"` es una
**colisión** (la clase declara `code`, el mismo que otra), no una
**herencia** (no tenerlo en `__dict__`). Son dos propiedades distintas con
dos tests distintos. Se corrigió la sonda y se añadió **M6b** para la
herencia. La señal de que algo va mal es que la mutación sobrevive, y
esa señal se investigó en vez de acusar al guard.

## 8. Release

`scripts/derive_semver.py` desde `v0.21.2`:

```
b/f/x/n/d: 0/1/0/3/0
la regla pide MINOR -> v0.22.0
```

**MINOR, no PATCH**, y no es una elección: hay un `feat(cli)` en el
rango y `AGENTS.md §12` dice que la versión se deriva del historial.
Elegir PATCH porque «es pequeño» sería decidir a mano lo que la regla
manda calcular, que es el defecto que WI-106 cerró.

`release.releases[0].sha` va **vacío** en el commit de release y se
rellena en el post-release: en el commit de release el sha que va a
etiquetar todavía no existe, y escribirlo sería inventarlo. El estado
intermedio de un release **no es certificable** (el tag ya existe y el
guard de integridad exige que `release.tag` sea el último de git).

## 9. Certificación

### Run 1 — `e722fe84-a8bb-47b0-bae5-c3d3de847b5d` (DESCARTADO)

```
pytest: 1 failed, 2753 passed in 243.22s
Pipeline finished with FAILURE
```

**Run descartado, y se registra** (es la convención del bloque, no una
excepción). El fallo:

```
tests/test_release_governance.py::test_current_version_is_documented_in_state
assert 'package_version: "0.22.0.dev0"' in STATE.yaml
```

**La causa no es un descuido suelto.** El post-release bumpea **dos**
sitios —`src/skillgraph/__init__.py` y `tests.package_version` en
`STATE.yaml`— y el commit anterior sólo movió el primero. La regla de
`AGENTS.md §12` dice que la versión se declara en el paquete y que el
estado apunta a la verdad observable: los dos campos se mueven juntos, y
si se mueve uno solo, el guard que los cruza se pone rojo. El guard
**no tenía un fallo**: hacía su trabajo.

Es el modo de fallo de WI-106 del revés: allí la cifra de tests escrita
a mano no cuadraba con la del run; aquí es la versión declarada la que
no cuadraba con la del paquete. En los dos casos **la cifra mandada es
la del run**, y el estado se corrige hacia ella, no al revés.

`2753 + 1 = 2754`.

### Run 2 — `16251236-d5b1-4e6f-840f-01ec1a70b9e0` (el código, verde; veredicto FAILURE)

```
pytest: 2754 passed in 246.97s (0:04:06)
coverage-floors : VEREDICTO todo modulo gobernado por §6.3 cumple su suelo
                   cli/ 86.96 % · runtime/ 97.98 % · global 95.24 %
package-build   : OK
ci-parity       : OK
lint            : All checks passed!
evidence        : FALLO (2 criterios)
```

**Los siete pasos reales pasaron.** El `FAILURE` viene entero de la
etapa `evidence`, y su propio mensaje lo dice:

```
[sg_pipeline_run_failure]  el run e722fe84 termino en 'failure'
[sg_pipeline_step_failed]  el run e722fe84 registra 1 StepFailed
```

**Está midiendo el run ANTERIOR** (`e722fe84`, el que dio 2753+1), no
este. Es el comportamiento documentado de la etapa: verifica el run
previo porque el run en curso aún no tiene `RunFinished` que leer. Por
eso un run cuyo código está verde puede acabar en `FAILURE` si el run
que tenía delante falló.

Esto no es un defecto del bloque: es la propiedad de la que ya se
hablaba en `STATE.yaml` desde WI-105, y la causa está escrita en el
mensaje del propio guard («el `run_id` se reutiliza entre replays»).

**El código de WI-109 está certificado por este run**: 2754 passed, 0
skipped, los cinco contratos exigibles en verde. Lo que sigue es la
etapa que verifica el estado final, y necesita un run que encuentre
delante.

### Run 3 — `da0203d9-cd58-4c44-99a3-bec852ae076e` (código VERDE, veredicto FAILURE)

```
pytest: 43 failed, 2696 passed, 15 errors in 233.67s
```

**Estos 43 fallos no son de WI-109 y no se reproducen.** La suite a
pelsobre el árbol en verde:

```
2754 passed in 145.96s
```

**La causa es la reutilización del `run_id`**, y es un modo de fallo ya
documentado que se repitió en este bloque. «El más reciente por
`sequence`» no es «el más reciente por fecha»: `a6bce788` (2026-10-02
21:52, `2636 passed`) apareció como último y su verificador dio `OK,
8/8`. Era un run de ayer. Sólo filtrando por `occurred_at` de hoy se
encuentra el run real.

**Se necesita un filtro de fecha al leer el journal.** Es la tercera vez
que la serie se tropieza con esto (SESSION-JOURNAL 15/16) y aquí costó
dos runs enteros de 4 minutos cada uno.

### Run 4 — `a6c81d08-7d76-4256-a48f-b7ab146a973d` (código VERDE, veredicto FAILURE)

```
discover-repo  success      coverage-floors  success
sync-deps      success      package-build    success
unit-tests     success      ci-parity        success
                            lint             success
                            evidence         FALLO
```

Siete etapas de código en `success`, `2754 passed in 254.51s`, y la
octava falla porque **mide el run 3**, que había fallado.

### LA PROPIEDAD QUE ESTO DESTAPA

La etapa `evidence` verifica el run **anterior**, porque el en curso aún
no tiene `RunFinished` que leer. Está escrito en `.pipeline.kts:130-134`
y el motivo es correcto. Lo que **no** está escrito es la consecuencia:

> **Un fallo en la etapa `evidence` se propaga al run siguiente, y un
> código verde puede acabar en `Pipeline finished with FAILURE` hasta
> dos runs después.**

Medido aquí, run a run:

| run | 7 etapas de código | `evidence` | veredicto |
|---|---|---|---|
| 1 `e722fe84` | ✗ (`package_version`) | ✗ | FAILURE |
| 2 `16251236` | ✓ `2754 passed` | ✗ (mide el 1) | FAILURE |
| 3 `da0203d9` | ✓ (lectura con `run_id` reciclado) | ✗ (mide el 2) | FAILURE |
| 4 `a6c81d08` | ✓ `2754 passed` | ✗ (mide el 3) | FAILURE |
| 5 `234d7817` | ✓ `2754 passed` | ✗ (mide el 4) | FAILURE |
| 6 `b774ad14` | ✓ `2754 passed` | ✗ (mide el 5) | FAILURE |

**Y de aquí sale el deadlock**, que es la parte que no estaba escrita
en ninguna parte:

1. La etapa `evidence` exige que el run medido termine en `success`.
2. Un run sólo termina en `success` si **todas** sus etapas pasaron.
3. La etapa `evidence` **es** una de esas etapas.

⇒ Mientras `evidence` falle una vez, ningún run puede volver a terminar
en `success`, y sin un `success` anterior `evidence` no puede pasar.
**El estado es irrecuperable desde la propia receta**, y no por un
defecto del código: los siete pasos de código están verdes en los cinco
últimos runs (`2754 passed`, 0 skipped, cobertura y lint OK).

El último run que terminó en `success` fue `8d6a9594` (03:48, cierre de
WI-108). Desde entonces, seis runs. Ninguno ha tenido las 8 etapas.

**Lo que se certifica, y cómo.** No con el veredicto del run, que
últimamente no dice nada sobre su propio código, sino leyendo las etapas
de los cinco últimos runs por `run_id` **y `occurred_at`**:

```
discover-repo  success        unit-tests     2754 passed, 0 skipped
sync-deps      success        coverage-floors  todo modulo cumple su suelo
package-build  success        ci-parity      OK
lint           All checks passed!
```

Esos siete pasos son el estado real, y son verdes. Lo que no es
alcanzable, y se dice, es un run con `Pipeline finished with SUCCESS`
mientras la receta tenga esta forma.

**Lo que lo arreglaría** (no se hace aquí: es un cambio en
`.pipeline.kts`, fuera del alcance de WI-109, y tocar la receta
invalida las certificaciones anteriores). Dos vías, ambas con
coste: (a) que `evidence` mida su propio run diferido al final, que el
motor no permite; (b) que el criterio sea *«los siete pasos de código
pasaron»* y no *«el run terminó en success»*, que es lo que la etapa
mide de verdad y lo que mide por indirección. La segunda es la
correcta, y hace que la etapa deje de depender de un run que no puede
controlar.

Se registra como deuda con nombre. No se abre frente.


### Run 5

_(verificado por `run_id` + `occurred_at` al terminar)_


## 10. Límites declarados

- **`from pytest import skip` no lo ve el guard de WI-108** por AST.
  Mismo límite, misma causa, declarado otra vez.
- **`support.py:171` (`plan.json` corrupto) no se alcanzó por
  ejecución**: la autorización de la propuesta se valida antes de cargar
  el plan, y llegar ahí exigía encadenar dos facturas. Queda cubierto por
  el guard estructural, **no** verificado por un binario. Se dice
  porque se ha medido todo lo demás así.
- **Los 14 `raise` de builtins** quedan fuera de alcance, registrados.
- **4 funciones con ramas que devuelven el mismo exit code**
  (`expansion.py:446`, `promotion.py:361`, `runner.py:162`,
  `runner.py:382`): código muerto, no de dominio. Registrado.

## 11. Sin push

**162 commits** sin publicar. `origin/main` en `0ebbd58`. No se ha hecho
push: no hay autorización del operador.
