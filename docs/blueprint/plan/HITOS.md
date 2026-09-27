# Hitos verificables

## H0 — Blueprint validado

Entregables:

- Contratos iniciales.
- ADR revisados.
- Resultado de spikes críticos.
- Primer escenario de referencia.

Criterio de salida:

El equipo puede describir las responsabilidades
del núcleo, los agentes y el almacenamiento
sin contradicciones esenciales.

## H1 — Recursos persistentes

Entregables:

- Parser.
- Validador.
- Registro de tipos.
- Persistencia SQLite.
- CLI de inspección.

UAT:

Crear dos proyectos y registrar un mismo
Domain Pack sin mezclar sus datos privados.

## H2 — Ejecución recuperable

Entregables:

- Motor de transiciones.
- Registro de eventos.
- Handoff.
- FakeAgentAdapter.
- Recuperación.

UAT:

Interrumpir el proceso y continuar sin repetir
una acción ya confirmada.

## H3 — Conocimiento incremental

Entregables:

- Sources.
- Claims.
- Evidence.
- Relaciones.
- Git fingerprinting.
- OutcomeTrace.
- ContextRecipe.

UAT:

Modificar una fuente, detectar qué afirmaciones
requieren revisión y reconstruir el contexto.

## H4 — Expansión controlada

Entregables:

- GraphExpansion.
- Validación de GraphPatches.
- Política de autorización.
- Revisión del grafo.

UAT:

Añadir una investigación imprevista a una ejecución
sin alterar el resultado de nodos anteriores.

## H5 — Adopción de skills

Entregables:

- Importación.
- Paquete encapsulado.
- Informe de asimilación.
- Registro de capacidades.
- Comandos dinámicos.

UAT:

Adoptar una skill real y conservar una referencia
verificable a sus instrucciones originales.

## H6 — Multipropósito

Entregables:

- Domain Pack de software.
- Domain Pack narrativo o educativo.
- Tipos y relaciones extensibles.

UAT:

Incorporar nuevos tipos de dominio sin modificar
el núcleo de persistencia ni el de ejecución.

## H7 — Release candidate

Entregables:

- Adaptador real.
- Seguridad.
- Recuperación.
- Documentación operativa.
- Suite UAT.

Criterio de salida:

El sistema completa escenarios reales con
trazabilidad, aislamiento y recuperación.

## Disciplina de hitos

Cada hito debe terminar con:

- Evidencia.
- Tests.
- Limitaciones conocidas.
- Decisiones pendientes.
- Estado GO o STOP.

No declarar un hito completo por haber escrito
únicamente sus interfaces.
