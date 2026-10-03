# WI-113 — el `AgentResult` del Adapter era un alias del dict externo

**Fecha**: 2026-10-03
**Ciclo**: `p-b7740b96d79ec013/wi113-agentresult-alias` (path `A-full`)
**Release**: `v0.22.4` (PATCH, sobre `f8b33389b6385716287e621fa96c6836a085475c`)
**Serie**: «qué declara el repo que nada comprueba», decimoquinta vía

---

## 1. La afirmación que no se sostenía

`AGENTS.md §1.1` dice, desde la primera versión de la viñeta:

> Colecciones: `tuple` (no `list`), `frozenset` (no `set`),
> `MappingProxyType` si hay que envolver un dict externo.

**WI-111** aplicó esa instrucción al `budget` del Handoff y dejó
constancia de once campos `dict`/`list`/`set` dentro de dataclasses
`frozen` como deuda registrada. El criterio del descarte era
explícito: *no participaban en el hash firmado*.

Ese criterio era correcto **para el hash** y equivocado **para el
resto**. Uno de los once no tenía un dict mutable: tenía un
**alias**.

## 2. Lo medido, antes de tocar nada

`AgentResult.from_fixture` validaba que `result` fuera un dict y lo
guardaba **tal cual**:

```python
result = payload["result"]
return AgentResult(outcome=outcome_raw, result=result, evidence_ref=evidence_ref)
```

Con ejecución real:

```
externo = {"outcome": "ok", "result": {"dato": 1}}
r = AgentResult.from_fixture(externo)
externo["result"]["dato"] = 999
r.result  ->  {'dato': 999, 'inyectado': 'tras la construccion'}
```

El `AgentResult` cambió sin que nadie lo tocara. Y no era cosmético:
`node_execution_delegations.py:443::_finalize_node_success`
serializa ese dict a disco, así que lo persistido era el del Adapter.

Quien produce ese dict es el **Adapter**, que es código externo al
repo. El Core creía compartir memoria con su propio dato y no la
compartía.

## 3. El arreglo, y por qué no es el de WI-111

```python
result=deepcopy(payload["result"]),
```

- **`deepcopy` y no `dict()`**: el payload tiene niveles anidados, y
  una copia de primer nivel deja los hijos compartidos.
- **Sin `MappingProxyType`**: en `HandoffExecution.budget` el dict
  solo se leía. Aquí el motor **serializa** el resultado, y
  `json.dumps` no acepta un `mappingproxy`: envolverlo rompería la
  frontera. La inmutabilidad de este campo no la aporta el tipo, la
  aporta que el Core ya no comparte memoria con el exterior.

## 4. Las propiedades que vigila el guard

El guard **ejecuta**, no lee. Por AST se vería que el campo está
anotado `dict[str, Any]`, que es exactamente lo que la regla permite;
la propiedad «el valor no se aliasa al llamante» solo se mide
construyendo el objeto y mutando el origen.

| propiedad | quién la mide |
|---|---|
| mutar el origen no altera el resultado | `test_mutar_el_dict_externo_no_altera_el_resultado` |
| una clave nueva externa no aparece | `test_una_clave_nueva_externa_no_aparece_dentro` |
| la copia es real, no de primer nivel | `test_mutar_el_dict_anidado_tampoco_altera` |
| la copia no escribe de vuelta | `test_el_payload_fuente_no_se_ve_afectado_por_cualquier_cosa` |
| el resultado sigue siendo serializable | `test_el_resultado_es_un_dict_plano_y_serializable` |

**15 tests** en `tests/test_wi113_agentresult_alias.py`.
**Mutaciones 3/3 cazadas** (`.pipelinek/wi113_mutate.py`), con cada
sonda verificada por ejecución real antes de contar.

## 5. Lo que NO se abrió, y por qué

Los otros diez dicts —`procedencia_por_firma`, `revisiones_por_fuente`,
`limites`, `metadatos`— se buscaron uno a uno y hay **cero** sitios
que los muten. Son dicts mutables dentro de un frozen, pero nadie los
cambia: es deuda de estilo, no defecto de comportamiento. Arreglarlos
sería tocar código correcto sin prueba de que está mal.

## 6. Certificación

**Run**: `f18d3817-a116-4ccc-91e2-34edd322462b`
**Terminado**: `2026-10-03T11:02:41.070400488Z` (`RunFinished`)
**Resultado**: **8/8 etapas en `success`**, `2827 passed in 590.83s`,
0 skipped.

Leído del journal por `run_id` y `occurred_at` **después** de que el
run terminara, no de la línea de salida.

| etapa | outcome | occurred_at |
|---|---|---|
| discover-repo | success | 10:52:41.390849662Z |
| sync-deps | success | 10:52:41.520191916Z |
| unit-tests | success | 11:02:36.093760010Z |
| coverage-floors | success | 11:02:37.649672383Z |
| package-build | success | 11:02:40.482594782Z |
| ci-parity | success | 11:02:40.707036917Z |
| lint | success | 11:02:40.828894854Z |
| evidence | success | 11:02:41.069807723Z |

`tests.total` = 2827 = 2812 + 15. La aritmética y el run coinciden.
SHA-256 de `.pipeline.kts`: `7541ced56193c9f2c846de84c7e96abff61dac7de2ed363b778a721738c2dd42`, sin drift.

## 7. Los dos runs anteriores, que también se registran

Un run descartado sigue siendo evidencia.

**`74fce920-d17a-41c4-aeef-70013056ceeb`** (10:17:58Z, `failure`) —
`1 failed, 2826 passed`. El fallo no fue de WI-113: 2826 + 1 = 2827 =
2812 + 15, luego los quince tests nuevos estaban todos colectados. Falló
un guard de **WI-104**:

```
TestBlockCitationsDelCurrentVivoResuelven::
    test_toda_cita_del_bloque_vivo_apunta_a_lo_que_dice
AssertionError: node_execution_delegations.py:443 — la cita no dice a qué símbolo apunta
```

WI-104 cambió el formato de cita a `fichero.py:LINEA::simbolo` porque
con solo el número no hay manera de distinguir «he abierto el
fichero» de «he escrito un número que me sonaba». La cita se escribió
sin el símbolo, en el bloque vivo y en siete sitios más.

El símbolo se resolvió en el AST, no a ojo: la línea 443 cae dentro de
`_finalize_node_success` (L407-444) y es el
`result_json=json.dumps(result_to_jsonable(result), sort_keys=True)`.

**`74bdb295-2dba-4c1a-9fb2-db4666aa3e88`** (10:51:22Z, `failure`) —
las **siete etapas de código pasaron** con `2827 passed`, y solo
falló `evidence`, que evalúa el run **anterior**:

```
[sg_pipeline_run_failure] el run 74fce920 terminó en 'failure'
[sg_pipeline_step_failed] 1 StepFailed (último: unit-tests/sh-0)
```

No es un defecto: es el comportamiento que **WI-110** construyó a
propósito, cuando se midió que «un fallo ya corregido no devuelve la
cadena a verde, porque el fallo deja de estar en el código pero sigue
en el veredicto». La exculpación es mínima y se lee explícitamente en
`scripts/check_pipeline_receipt.py:354::evaluar`:

```python
solo_autoevaluada = (
    informe.step_failed == 1
    and paso is not None
    and paso.startswith(f"{ETAPA_AUTOEVALUADA}/")
)
```

Antes de lanzar el tercer run, esa condición se comprobó con el propio
script en lugar de suponerla:

```
$ python scripts/check_pipeline_receipt.py --run-id 74bdb295-...
OK: el run cumple los criterios que declara AGENTS.md.
run 74bdb295: 7/7 etapas, 9 pasos, veredicto 'failure'.
exit=0
```

## 8. Errores propios registrados

- **32 — Una mutación que no era una mutación.** La sonda M3 apuntaba
  a un texto que `ruff format` había colapsado a una sola línea. Una
  sonda `INVALIDA` no mide nada, y contarla habría hecho creer que el
  guard cazaba menos de lo que caza. Por eso el harness distingue
  cuatro salidas con nombre —`CAZADA` / `NO_DETECTADA` / `SIN_SONDA` /
  `INVALIDA`— y verifica cada sonda con ejecución real **antes** de
  contar. Cuarta vez que el formateo rompe una sonda: el formateo es
  parte del código, y un guard que se rompe con `ruff format` no está
  midiendo el código.

- **33 — El guard existía, funcionaba, y su autor escribió mal la
  cita.** WI-104 cerró en WI-101..WI-104 un defecto que yo mismo
  cometí otra vez en WI-113. Un guard detecta el defecto de quien
  escribe; no evita escribirlo. La lección no es «arreglar el guard»
  —el guard hizo su trabajo— sino que la cita tiene que salir del
  verificador, no de la memoria.

## 9. Descarte que se midió antes de decidir

Se buscó mutación sobre los diez dicts restantes y el resultado fue
**cero sitios**. Registrado y no abierto: es deuda de estilo, y
arreglarla sin prueba de que está mal sería tocar código correcto.

Del mismo modo se descartó, por medición, que `tests.total` desalineado
fuera la causa del primer fallo: no existe ningún guard que compare
ese campo con el recuento real (`grep` de `2812`, `2827` y `collected`
sobre todo el Python del repo: cero coincidencias), y
`test_wi85_state_yaml_integrity.py` solo comprueba que el valor sea un
`int`.
