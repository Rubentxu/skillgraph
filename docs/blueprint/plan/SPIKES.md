# Spikes arquitectónicos

Los spikes son experimentos delimitados.
Su resultado puede modificar los ADR propuestos.

## S0 — Brick mínimo

Pregunta:

¿Puede un recurso Markdown/YAML declararse,
validarse y registrarse sin código especializado?

Experimento:

Crear un DecisionNode, un ActionNode
y un Domain Pack mínimo.

Evidencia:

Validación de esquema, resolución de referencias
y rechazo de recursos inválidos.

Salida:

Contrato mínimo aceptado o revisión del esquema.

## S1 — SQLite y relaciones

Pregunta:

¿SQLite convencional soporta las consultas
necesarias para los primeros workflows?

Experimento:

Crear recursos, relaciones y dependencias.

Ejecutar consultas de frontera, dependencias inversas
y recuperación de conocimiento.

Medir latencia sobre un conjunto representativo.

Salida:

Continuar con SQLite o justificar una extensión.

## S2 — ActiveGraph

Pregunta:

¿Qué primitivas concretas pueden reutilizarse
sin alterar nuestros contratos?

Experimento:

Implementar un flujo con eventos, patches,
persistencia y reanudación.

Comparar con un núcleo propio mínimo.

Criterios:

Compatibilidad, complejidad del adaptador,
control de estado y recuperación.

Salida:

Reutilizar un componente concreto o descartarlo.

No adoptar el framework completo por defecto.

## S3 — Recuperación de ejecuciones

Pregunta:

¿Puede reanudarse una ejecución sin duplicar efectos?

Experimento:

Interrumpir el proceso antes y después
de registrar una operación.

Simular resultado externo incierto.

Salida:

Protocolo de idempotencia y recuperación.

## S4 — Conocimiento incremental

Pregunta:

¿Podemos invalidar afirmaciones relevantes
sin reconstruir todo el conocimiento?

Experimento:

Indexar varios archivos relacionados.

Modificar uno y comprobar propagación selectiva.

Modificar también una regla sin tocar las fuentes.

Salida:

Modelo de dependencias y vigencia.

## S5 — Contexto mínimo

Pregunta:

¿Puede completarse un trabajo sin historial completo?

Experimento:

Ejecutar un nodo con contexto delimitado.

Registrar las consultas adicionales del agente.

Comparar resultado y consumo de contexto
con un baseline que reciba información extensa.

Salida:

ContextRecipe inicial y limitaciones observadas.

## S6 — Expansión mínima

Pregunta:

¿Puede incorporarse un subgrafo durante una ejecución
sin invalidar las instancias ya completadas?

Experimento:

Crear una problemática inesperada mediante fixture.

Proponer y aplicar un GraphPatch.

Reanudar desde una revisión nueva.

Salida:

Contrato de expansión, concurrencia y autorización.

## S7 — Asimilación de skills

Pregunta:

¿Puede adoptarse una skill convencional
sin perder sus reglas esenciales?

Experimento:

Importar una skill metodológica y otra con recursos.

Comparar comportamientos originales y estructurados.

Salida:

Informe de fidelidad y estrategia de activación.

## S8 — Extensión multipropósito

Pregunta:

¿Puede incorporarse un dominio narrativo
sin modificar el núcleo?

Experimento:

Registrar Character, StoryArc y NarrativeEvent.

Crear relaciones y un workflow editorial.

Salida:

Validación del registro de tipos extensibles.

## Registro de resultados

Cada spike debe documentar:

- Hipótesis.
- Preparación.
- Experimento reproducible.
- Evidencia.
- Limitaciones.
- Consecuencia arquitectónica.
- ADR afectado.
- Decisión GO/STOP o necesidad de investigación.
