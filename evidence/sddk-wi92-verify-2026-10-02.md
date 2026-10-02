# WI-92 — Lo que WI-90 registró como deuda, medido: era falso

- **Ciclo**: `p-b7740b96d79ec013/wi-92-retract-measured-false`
- **Fecha**: 2026-10-02

## Qué decía el registro

WI-90 cerró el round-trip de `FileSignature` y dejó anotados **sin medir**
dos sitios con «el mismo patrón de inverso manual»:

> `governance/receipts.py:473-480` y `runtime/agent.py:57-64` replican el
> mismo patrón de inverso escrito a mano. Registrado, no ejecutado.

Es exactamente el patrón que la consigna del proyecto marca: *«Alerta
"deuda" sin verificar, si sus criterios iniciales no siguen vigentes, no
es deuda real»*.

## La medición

### 1. `runtime/agent.py` — falso

`AgentResult.from_fixture` **no** es el inverso de un `to_dict`. Su
primera instrucción valida la forma:

```python
if not isinstance(payload, dict):
    raise ValidationError(...)
```

y las que siguen comprueban `outcome` (str), `result` (dict) y
`evidence_ref` (str | ausente). Los errores son **tipados**
(`ValidationError`, `OutcomeInvalidError`), no `KeyError`/`TypeError`. Es
un cargador de fixtures, no un deserializador a mano.

### 2. `governance/receipts.py` — la premise era falsa, el riesgo no

Aquí sí hay un par asimétrico real:

| Pieza | Visibilidad |
|---|---|
| `ValidationReceipt.to_payload()` (línea 165) | **público**, emite 11 claves |
| `_payload_to_receipt()` (línea 466) | **privado**, lee 11 claves a mano |

Pero las tres listas **cuadran hoy**, 11 = 11 = 11:

| Lista | Nº | Contenido |
|---|---|---|
| campos del dataclass | 11 | `receipt_id`…`extra_metadata` |
| `to_payload` | 11 | las mismas |
| `_payload_to_receipt` | 11 | las mismas |

Y el caller (`receipts.py:435-437`) hace exactamente lo que promete el
docstring:

```python
try:
    receipt = _payload_to_receipt(payload)
except (KeyError, ValueError, TypeError):
    continue
```

Además `_declared_counter` (WI-49) ya cerró el agujero del bool en
`tests_run`/`tests_passed`.

## Lo que no es un defecto pero sí un riesgo

Nada verificaba que las tres listas siguieran siendo la misma. Y el modo
de fallo silencioso es real:

- **una clave de más** → el campo se pierde en silencio;
- **una clave de menos** → `KeyError`, el caller hace `continue`, y el
  receipt que debería aplicarse **no aplica sin dejar rastro**.

Un guard de contrato cierra las dos.

## El segundo guard: las citas del puntero operativo

Antes de construirle un guard a esta clase se medió. De **57 citas**
`fichero.py:NNN` en `STATE.yaml` + `CHANGELOG.md` + `CURRENT.md`:

- **52 resuelven**
- **3 no**, y **las 3 están en registros históricos** que describen
  código ya refactorizado (`platform/storage.py` pasó de 1807 a 600
  líneas en WI-65/68)

Corregirlas habría sido **falsificar la historia**: decir que una
auditoría de 2026-09-25 encontró problemas en líneas que no existían
entonces. Así que el guard cubre **el bloque vivo** de `CURRENT.md` — el
puntero que lee primero la próxima sesión — y deja los bloques
anteriores como la foto que son.

## Dos errores de medición, ambos propios

**El resolver estaba mal y el dato parecía una catástrofe.** La primera
versión resolvió `run_repository.py` contra
`src/skillgraph/run_repository.py`, que no existe —el fichero está en
`platform/`— y reportó 19 referencias «sin fichero» en `STATE.yaml`. Un
resultado alarmantemente malo por un resolver roto, no por los datos.
Lo mismo que medir `/usr/bin/sg` en WI-88.

**Un assert sobre una subcadena no comprueba una propiedad.** El primer
guard de `from_fixture` decía «`isinstance` aparece en el cuerpo», y la
mutación M4 lo esquivó: el fichero tiene **cuatro** comprobaciones
`isinstance` en esa función, así que borrar una deja tres y la palabra
sigue ahí. Se reescribió sobre el AST para exigir que **la primera
instrucción** valide que `payload` es un `dict`.

## Mutaciones

| # | Mutación | Resultado |
|---|---|---|
| M1 | `to_payload` deja de emitir una clave | **cazada** |
| M2 | el lector deja de leer una obligatoria | **cazada** |
| M3 | el lector lee una clave que no existe | **cazada** |
| M4 | `from_fixture` deja de validar que el payload es un dict | **cazada** (tras reescribir el guard) |
| M5 | el bloque vivo cita una línea fuera de rango | **cazada** |
| M6 | el bloque vivo cita un módulo inexistente | **cazada** (tras corregir el patrón) |

`cazadas=6  no-cazadas=0`

M6 no se aplicó en la primera pasada porque el patrón buscado omitía el
rango (`473` en vez de `473-480`) y las comillas invertidas. **El
autocontrol de aplicación lo reportó como `MUTACION NO APLICO`, no como
«no cazada».** Es la quinta vez en tres bloques que una medición necesita
autocontrol: sin él, «no cazada» y «no medí» se reportan igual y el
resultado es verde y falso.

## Conocimiento negativo

- **Medir una hipótesis antes de construirle un guard la habría
  convertido en deuda que nunca existió.** Las dos entradas que WI-90
  dejó abiertas eran falsas; el trabajo real no era arreglarlas, era
  saber que no había nada que arreglar, y eso solo se sabe midiendo.
- **La asimetría privado/público no es el defecto.** Hay un escritor
  público y un lector privado a mano, y aun así el módulo es correcto:
  el lector es interno, el caller lo protege y las claves cuadran. Lo
  que faltaba era la **verificación**, no la simetría.
- **Un guard que protege una afirmación tiene que probarse
  invirtiéndola.** Estos dos no arreglan un fallo: mantienen cierta una
  afirmación que hoy lo es. Sin mutación que laerie, serían
  decorativos.
- **Corregir una referencia histórica no es restaurarla: es
  reescribirla.** Una cita que apuntaba a una línea en 2026 no se
  «arregla» apuntándola a la línea equivalente de 2026.
