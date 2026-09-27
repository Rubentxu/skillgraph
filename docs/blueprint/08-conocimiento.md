# Modelo de conocimiento y actualización incremental

## 1. Objetivo

Mantener conocimiento verificable, relacionable
y reutilizable sobre el proyecto sin convertir
la conversación en la fuente de verdad.

## 2. Entidades generales

Source
Entity
Relation
Claim
Evidence
Contract
Rule
Finding
OutcomeTrace

Los Domain Packs especializan estos tipos.

## 3. Separación semántica

### Observación

Dato obtenido de una fuente o una medición.

### Interpretación

Evaluación de observaciones mediante criterios.

### Decisión

Elección registrada con motivos y alcance.

### Acción

Trabajo autorizado a partir de una decisión.

Una observación no se convierte automáticamente
en una directiva de implementación.

## 4. Procedencia

Toda afirmación verificable registra:

- Fuentes utilizadas.
- Revisiones o hashes pertinentes.
- Método de extracción.
- Versión del analizador, si aplica.
- Fecha o revisión de comprobación.
- Estado de vigencia.
- Limitaciones conocidas.

## 5. Git

Para un proyecto Git registrar:

- Identidad lógica del proyecto.
- Identidad del workspace o worktree.
- Commit de referencia.
- Estado del índice y working tree.
- Ruta de la fuente.
- Hash de contenido.
- Identificador de objeto Git cuando proceda.

No utilizar únicamente HEAD para representar
archivos modificados sin commit.

No confundir el hash de un commit con el
identificador de contenido de un archivo.

## 6. Otros orígenes

Un proyecto puede utilizar documentos locales,
fuentes externas y artefactos no gestionados por Git.

Cada adaptador debe declarar qué garantías ofrece
sobre identidad, revisión y detección de cambios.

## 7. Invalidación

Una afirmación puede necesitar revisión cuando cambia:

- Su fuente.
- Una dependencia relevante.
- Una regla aplicada.
- Un analizador.
- El esquema con el que se interpretó.
- Una decisión que determina su aplicabilidad.

## 8. Algoritmo

```text
detect_source_change
  -> locate_direct_claims
  -> traverse_relevant_dependencies
  -> mark_affected_claims_stale
  -> identify_active_consumers
  -> schedule_required_refresh
  -> verify_new_claims
  -> publish_new_revisions
```

No regenerar todo el grafo tras cada cambio.

La invalidación puede ser inmediata; la actualización
puede realizarse bajo demanda.

## 9. OutcomeTrace

Un recorrido transversal representa cómo varios
elementos contribuyen a un resultado.

Especializaciones:

- SoftwareExecutionSlice.
- NarrativeArgumentTrace.
- LearningPath.

Cada recorrido referencia componentes y contratos;
no duplica todos sus resúmenes.

## 10. Conocimiento normativo y descriptivo

Normativo: arquitectura declarada, reglas o intención.

Descriptivo: comportamiento, estructura y relaciones
observadas en las fuentes.

La evaluación compara ambos sin confundirlos.

## 11. Hallazgos

Un hallazgo debe conservar:

- Entidad evaluada.
- Observación.
- Criterio utilizado.
- Evidencia.
- Versión de la regla.
- Resultado.
- Estado de vigencia.

Ejemplo: una función de 145 líneas frente a un
umbral de proyecto de 80 líneas.

El umbral es una configuración del proyecto,
no una ley universal de ingeniería.

## 12. Aprendizaje

Los descubrimientos de una ejecución pueden generar:

- Nuevas afirmaciones.
- Nuevas relaciones.
- Nuevos recorridos.
- Preguntas abiertas.
- Propuestas de ampliación.
- Propuestas de mejora del contexto.

La promoción a un Domain Pack compartido requiere
una revisión independiente.
