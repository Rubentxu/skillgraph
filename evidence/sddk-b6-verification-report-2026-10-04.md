# B6 — Informe de verificación

Fecha: 2026-10-04
Ciclo: `p-b7740b96d79ec013/b6`
Release: `v0.26.0` en `259d723`
Veredicto: **cerrado en alcance, con una pregunta registrada fuera**

## Qué entrega el bloque

El gate del roadmap pide que cada afirmación del Knowledge Graph distinga
`observed` · `derived-deterministically` · `agent-inferred` ·
`human-asserted` y conserve su provenance. Medido antes de escribir nada:
**4 de 4 preguntas abiertas**.

El hueco no era un campo que faltara. `Claim.extraction_method` existía y
guardaba **métodos de extracción** (`static_analysis`, `regex_def`,
`manual`), que es un eje ortogonal al del origen epistémico: con
`regex_def` no se sabe si lo afirmó la máquina o una persona.

## Verificación, en dos instrumentos que se vigilan entre sí

### El medidor: 0 de 5 huecos en alcance

```
$ .venv/bin/python scripts/measure_b6_provenance.py
huecos ABIERTOS EN ALCANCE: 0 de 5
VEREDICTO: el hueco de este bloque esta cerrado. Salida 0.
```

Las cinco preguntas: el vocabulario cerrado existe; el origen está tipado;
la base lo impone con `CHECK`; los dos ejes están separados; y un valor
fuera del vocabulario se rechaza al construir.

### El harness: 8 de 8 sondas, con 8 causas **distintas**

```
$ .venv/bin/python scripts/mutate_b6_provenance.py
cazadas 8/8   NO cazadas 0   sin sonda 0   rotas 0
arbol restaurado byte a byte: True
```

Lo que importa aquí no es el 8/8 sino que **cada sonda rompe su propia
propiedad**. Comprobado explícitamente:

| sonda | qué rompe | primer test que cae |
|---|---|---|
| M1 | la validación de `__post_init__` | `test_el_error_es_del_dominio_y_tiene_code_propio` |
| M2 | el `CHECK` de la DDL | `test_el_medidor_da_verde_en_el_arbol_real` |
| M3 | el origen al releer de la base | `test_el_origen_va_en_el_select_no_solo_en_el_insert` |
| M4 | el guard busca la mención, no la comparación | `test_el_medidor_ve_rojo_si_se_rompe_la_validacion` |
| M5 | los dos ejes vuelven a ser un campo | `test_cada_origen_del_gate_se_acepta[agent-inferred]` |
| M6 | la promoción revierte el origen | `test_la_promocion_no_revierte_el_origen_a_observed` |
| M7 | desaparece la migración | `test_una_base_previa_se_migra_y_conserva_el_check` |
| M8 | el conjunto derivado se escribe a mano | `test_el_conjunto_derivado_cubre_todo_el_literal` |

**8 causas distintas de 8 sondas.** Un harness donde las ocho fallan por el
mismo aserto estaría midiendo una cosa ocho veces.

## Los cuatro agujeros que encontró, y que no eran sondas malas

1. **El guard de P6 buscaba la *mención*** de los dos nombres con
   `ast.dump`, y pasaba en verde con la validación gutiada: el mensaje del
   `raise` sigue nombrando el conjunto. Un guard que mide la prosa del
   error no mide la validación. Corregido para exigir un `not in` real.

2. **El harness llevaba `-x`.** Sin `-x`, **M3, M6, M7 y M8 no cazaban**:
   sus mutaciones dejaban la suite en verde. El «8/8» era un número que no
   se podía desarmar, con cuatro sondas heredando el fallo de la anterior.
   Añadidos los cuatro tests que faltaban.

3. **El harness guardaba el `sha` y «restauraba»** reescribiendo el fichero
   con sus propios bytes, que es no hacer nada. Ahora restaura bytes
   guardados.

4. **El guard de WI-92** («un guard sobre cero citas no vigila nada») cazó
   el bloque vivo de `CURRENT.md` dos veces: primero porque no citaba
   ninguna línea, después porque el formato es `fichero.py:LÍNEA::Símbolo`
   con **dos** puntos y se escribieron tres. Se corrigieron las citas, no el
   guard: relajar el verificador para que acepte lo que se escribió habría
   sido quitarle la única función que tiene.

## La suite

- **23 tests** en `tests/test_b6_provenance.py`, más 2 en
  `test_b0_truth_convergence.py` (ver más abajo).
- `tests.total` **3055**, medido después del run: 3053 → 3055 con los dos
  tests nuevos. A diferencia de B4 y B5, este bloque **no creó módulos
  nuevos** en `src/`, así que el guard de `wi47` no generó casos: sigue en
  255.
- Cobertura: `core/errors.py` 100 %, `core/runtime_types.py` 98 %,
  `knowledge/graph.py` 96 %.

## Un defecto del repo, encontrado al liberar

Al liberar `v0.26.0` apareció un estado **inalcanzable**: los dos guards
de release se exigían cosas incompatibles.

- `scripts/project_truth.py` decía que `__version__` es siempre
  `<tag>.dev0`.
- `test_release_governance.py::test_version_matches_git_tag` dice que con
  HEAD **en la etiqueta** tiene que ser el SemVer **puro**.

Los dos son del repo y los dos se ejecutan, luego ninguna versión
satisfacía a los dos. Se corrigió la regla de `project_truth.py`, no la
del guard de release, porque el de release ya distinguía los tres casos y
el otro funcionaba con uno solo. Y el hecho «HEAD está en la etiqueta» se
expuso como **parámetro**, no como una llamada a git dentro, para que el
test pueda construir los dos casos sin depender del checkout.

## Gates del ciclo

| gate | outcome | por qué |
|---|---|---|
| `exploration-sufficient` | passed | 4 de 4 preguntas abiertas medidas antes de escribir nada |

El ciclo `b6` **no puede avanzar de `explore`**: la transición exige el
artefacto `exploration-report` vinculado al ciclo, y
`sddk artifact store` lo escribe con un `sha256` correcto pero **no deja
la vinculación** — el ciclo sigue con `artifacts: 0`. Es la tercera
manifestación del mismo defecto del framework, documentada en
`evidence/blocker-B5-ciclo-id-no-cualificado-2026-10-03.md`.

La evidencia de todas formas está commiteada en `evidence/`, que es donde
se puede leer y verificar. **No se forzó la transición ni se dio el
artefacto por registrado.**

## Fuera de alcance, y registrado

**P5 — ¿el proveedor real *puebla* conocimiento o lo *consume*?** Depende
de una credencial de proveedor real que este entorno no tiene. El medidor
la mantiene abierta y **no baja el veredicto**: es deuda, no un olvido.
Medirla sin credencial sería medir el entorno, no el bloque.
