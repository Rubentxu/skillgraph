# WI-90 — Verificación: `FileSignature` tiene round-trip cerrado

- **Ciclo**: `p-b7740b96d79ec013/wi-90-signature-round-trip`
- **Commit**: `e4fefb0`
- **Fecha**: 2026-10-02
- **Suite**: 2479 passed (2463 antes; +16)

## Qué decía el item y qué se midió

El roadmap tenía (a) como último seguimiento técnico abierto:
«`list_file_signatures_for_source` (cc 10, 58 LoC) es el único punto ciego
del audit y ningún umbral lo captura. SIN MEDIR».

Medido, **la complejidad no era el asunto**. El asunto es que
`FileSignature` sabía serializarse y no sabía deserializarse:

| Pieza | Estado |
|---|---|
| `FileSignature.to_dict()` | existe (`file_signature.py`) |
| `FileSignature.from_dict()` | **no existía** |
| el inverso, escrito a mano | `knowledge_controller.py:329-336`, campo a campo, con subíndices crudos |

Es decir: la mitad de arriba de un round-trip estaba, la mitad de abajo
estaba escrita a mano, y nadie verificaba que encajaran.

## Los tres fallos, medidos

Reproducidos ejecutando exactamente lo que hacía el lector:

| Payload | Comportamiento |
|---|---|
| campo de más | **se perdía en silencio** |
| falta una clave | `KeyError` — no tipado |
| `procedencia` incompleta | `TypeError` — no tipado |

## El radio de impacto

Los tres call sites (`governance/improvement.py:208, 268, 324`) llaman
**sin proteger**. El `KeyError` sale del Knowledge layer y revienta en la
capa de governance, que tiene otro vocabulario de errores. AGENTS §1.2 pide
`SkillGraphError` o subclase en código de dominio, nunca genéricos.

## El caso que más duele: el del silencio

Un campo de más no da error: **se pierde**. Y el escenario futuro es
concreto. Si mañana `FileSignature` gana un campo obligatorio, el lector
actual construye sin él y la lectura de lo ya persistido se rompe. No al
escribir —que es cuando se nota—, sino meses después, al leer, en otra
capa.

## La corrección

`from_dict` en las tres clases, con la validación de forma concentrada en
seis helpers (`_require_mapping`, `_require_keys`, `_require_str`,
`_require_int`, `_require_bool`, `_require_optional_mapping`).

La jerarquía de errores se respeta y no se aplana:

- `ParseError` (`sg_parse`) → «el registro no se puede leer». Forma.
- `ValidationError` (`sg_validation`) → «la forma vale pero los valores
  violan política». Lo lanza `__post_init__` y se deja propagar.

Por eso `SignatureVigencia.from_dict` **no** comprueba que `state` esté en
`EXTRACTION_STATES`: esa comprobación ya vive en `__post_init__`, y
duplicarla sería inventarse un segundo sitio que puede desincronizarse del
primero. Es exactamente el criterio de WI-87 aplicado a una decisión
distinta: no duplicar un invariante para «estar más seguro».

## La red

- `from_dict(to_dict(s)) == s` para los cinco estados de `EXTRACTION_STATES`.
- Las claves de `to_dict` y los campos del dataclass son los mismos — una
  aserción sobre las dos fuentes, porque un campo que las dos olviden a la
  vez no lo caza ningún test.
- Los tres modos de fallo medidos lanzan `SkillGraphError`, no
  `KeyError`/`TypeError`.
- El lector no vuelve a leer claves literales: se buscan subíndices cuyo
  *slice* sea una constante de string, que es lo que significa
  `payload["foco"]`. Una anotación de tipo (`tuple[FileSignature, ...]`)
  no cuenta, porque no lee nada.

## Mutaciones

| # | Mutación | Resultado |
|---|---|---|
| M1 | claves desconocidas en silencio (el defecto) | **cazada** |
| M2 | clave que falta → `KeyError` crudo | **cazada** |
| M3 | sin comprobación de tipo en `_require_int` | **cazada** |
| M4 | el lector vuelve a subíndices | **cazada** |
| M5 | campo que `to_dict` no emite | **cazada** |

`cazadas=5  no-cazadas=0`

M5 es la deriva que el round-trip compra: sin él, el campo extra sería
verde.

## Conocimiento negativo

- **Una mutación que no se aplica se reporta como «no cazada».** El `replace`
  de M3 no coincidía porque `ruff format` había partido el `raise` en tres
  líneas. El script decía «NO CAZADA» y la verdad era que la mutación no
  había corrido — que es la dirección peligrosa: hace parecer que la red
  tiene un hueco donde en realidad el script está roto. Es la **tercera
  vez** que pasa (WI-88 M1/M5, WI-89 M4). El script ahora comprueba, con
  md5 antes y después, que la mutación cambió el fichero, y reporta
  `MUTACION NO APLICO` como fallo propio si no.
- **Un guard demasiado blunt se equivoca en la dirección contraria.** Mi
  primera versión buscaba *cualquier* subíndice en el lector y marcaba las
  anotaciones de tipo. La aserción correcta es sobre el *slice*: lo que
  distingue una lectura de payload de un `tuple[X, ...]`.
- **Escribir una rama que hace lo mismo que su `fallthrough` es un fallo
  que compila y se lee bien.** La primera versión de
  `SignatureVigencia.from_dict` tenía un `if state not in EXTRACTION_STATES`
  cuyas dos ramas construían exactamente lo mismo. Se retiró.
- **El patrón es una clase, no un caso.** `governance/receipts.py:473-480` y
  `runtime/agent.py:57-64` tienen el mismo defecto: escritor con
  serializador, lector con el inverso escrito a mano. Registrado como deuda
  tangencial; no se abre otro frente aquí (AGENTS §4, scope discipline).
- **El subject de este commit pasó de 72 columnas** (85), contra AGENTS
  §7, después de haberlo respetado en los commits anteriores.
  **Corregido con `commit --amend` antes de publicar.** El razonamiento
  inicial —«un amend por tres caracteres cuesta más que el
  incumplimiento»— era además una cuenta falsa: la diferencia eran 13
  columnas, no tres. El amend es legítimo porque el commit **no está
  publicado** y su árbol es **byte-idéntico** (`git diff <sha-antiguo>
  <sha-nuevo>` sale vacío), así que la certificación de 2479 passed
  sigue siendo válida para el mismo contenido. Reescribir un commit ya
  publicado sí sería una falta de provenance; reescribir uno local, cuyo
  árbol no ha cambiado, es sólo corregir el mensaje.

## Deuda tangencial registrada

- **`governance/receipts.py:473-480`** — lee `payload["receipt_id"]`,
  `["command"]`, `["revision"]`, `["timestamp"]`, `["verdict"]`,
  `["artifact_path"]` a mano. Mismo patrón.
- **`runtime/agent.py:57-64`** — valida presencia antes de leer, que es
  mejor que el caso de `file_signature`, pero sigue siendo un inverso
  escrito a mano.

Ninguno está medido en ejecución, así que quedan como registro y no como
deuda cuantificada.
