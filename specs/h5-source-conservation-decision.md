# Decisión de diseño: H5 "conservar el material original"

> Status: **DECIDED** (firmada en este turno, 2026-09-23).
> Afecta a `src/skillgraph/skill_importer.py` y al contrato `Source`.

## Pregunta

UAT-11 dice literalmente: _"se conserva la fuente original"_ (al importar
una skill). El blueprint §10 §6 dice: _"El informe debe contener referencias
a su fuente"_, y §10 §5 dice: _"La skill original se conserva como
comportamiento ejecutable sujeto a un contrato externo"_ (nivel Encapsulado).

¿La frase "conserva la fuente original" exige persistir los bytes del
material en el store de SkillGraph, o basta con una referencia (path +
content_hash)?

## Decisión

**Basta con referencia (path + content_hash). NO se duplican bytes en el
store de SkillGraph.**

## Justificación literal (blueprint §10)

1. **§6 "referencias a su fuente":** el blueprint usa el término _referencia_,
   no _copia_ ni _snapshot_. La "fuente" en el sentido de provenance es
   metadato + locator, no contenido duplicado.

2. **§6 "La validez del YAML no demuestra equivalencia del comportamiento":**
   el blueprint separa _metadata_ (lo que registramos) de _comportamiento_
   (lo que la skill podría ejecutar, bajo control). Copiar bytes no
   resuelve esa separación.

3. **§5 Encapsulado: "comportamiento ejecutable sujeto a un contrato externo":**
   la skill conserva su ejecutabilidad gracias a que reside en su path
   original + el contrato SKILLGRAPH la invoca de manera controlada. NO
   copia interna.

4. **§4 "datos internos fuera del repositorio" + §4 "no ejecuta código del
   paquete":** SkillGraph está diseñado para mantener sus DATOS internos
   (catalogos, indices, sources) separados del workspace. El material de
   la skill NO es dato interno: es entrada externa referenciada.

5. **§4 Procedencia (blueprint §08):** _"Toda afirmación verificable
   registra: fuentes utilizadas, revisiones o hashes pertinentes,
   método de extracción"_. La fuente se registra como referencia + hash;
   el contenido verbatim vive en otra parte.

## Implementación actual conforme a la decisión

En `src/skillgraph/skill_importer.py`:

- `SkillImportReport.original_path` = path original (referencia).
- `SkillImportReport.content_hash` = sha256 de los bytes agregados del pack.
- `Source` registrado con `locator.path`, `content_hash`, `kind="skill_pack"`.
- NO se copian bytes a `.skillgraph/` ni a storage interno.
- Si el path original desaparece o muta, `content_hash` lo detecta en el
  siguiente refresh; el source puede pasar a `archived` o `stale`.

## Trade-offs aceptados

- **Pro:** No se duplica almacenamiento. La skill es referenciada, no
  capturada. Cumple §10 §4 (SkillGraph no retiene contenido que no
  necesita).
- **Pro:** Si el usuario borra la skill del disco, SkillGraph NO la
  "recuerda" como contenido pero sí como referencia. Coherente con §11
  seguridad: la autoridad sobre el código sigue siendo del usuario.
- **Con:** Si el path original desaparece, `Source.refresh()` falla o
  detecta cambio. Eso es DESEABLE: el blueprint exige provenance, no
  independencia del usuario.

## Variantes que NO adoptamos

- **NO** copiamos bytes al data_root (`~/.local/share/skillgraph/...`).
  Eso sería snapshot duplicado, contradice §4 (datos internos separados).
- **NO** creamos un `_packs/<hash>` que reescriba el material. Eso lo
  convierte en dato interno, viola §10 §4.
- **NO** exigimos un contrato tipo "bytea exactos" en Source: `Source`
  registra _content_hash_ (sha256), pero los bytes viven en su sitio.

## Cuándo re-abrir esta decisión

Si una futura UAT exige auditar contenido exacto de la skill SIN acceso
al path original (por ejemplo: regulator de la industria que exige
reproducibilidad bit-a-bit), entonces:
- O bien se cambia la interpretación B (duplicar bytes),
- O bien se documenta una nueva ADR con la justificación regulatoria
  específica.

Hoy, esa exigencia NO existe ni en UAT-11 ni en el blueprint.

## Relación con UATs

- **UAT-11 (PASS):** "conserva la fuente original" se cumple vía
  `Source(kind=skill_pack, locator=path, content_hash=sha256)`. Sin
  duplicación.
- **UAT-14 (PASS):** el script NUNCA se ejecuta, el path se reporta
  en `scripts_detected`.
- **UAT-15 (PASS):** la fuente queda registrada con `content_hash` que
  cambia si el contenido cambia. Si la fuente intenta alterar permisos
  o transiciones, NO se ejecuta (ver §10 §4 + §11).

## Cierre

La decisión es **definitiva para H5**. Cualquier cambio material
(copy-bytes, snapshot interno, claim de reproducibilidad bit-a-bit)
requiere una ADR separada con justificación regulatoria o de seguridad.
