# Roadmap de implementación

## Principio de entrega

Construir vertical slices completos.

Cada hito debe incorporar una capacidad observable
sin obligar a desarrollar simultáneamente
todo el framework.

## Etapa 0 — Validación arquitectónica

Resultado: límites y contratos iniciales comprobados.

Trabajos:

- Ejecutar spikes de persistencia y ActiveGraph.
- Validar el contrato mínimo de brick.
- Comprobar un Domain Pack Markdown.
- Identificar un primer escenario end-to-end.

No implementar un motor de producción todavía.

Gate: arquitectura inicial delimitada y riesgos
documentados mediante evidencias.

## Etapa 1 — Núcleo declarativo local

Resultado: registrar e inspeccionar bricks.

Trabajos:

- CLI inicial.
- Directorios de datos.
- Catálogo de proyectos.
- Parser Markdown/YAML.
- Registro de tipos.
- Validación de recursos.
- SQLite y migraciones iniciales.

Gate: dos proyectos separados y una definición
reutilizable validada.

## Etapa 2 — Primer workflow determinista

Resultado: ejecutar y reanudar un subgrafo.

Trabajos:

- RunController.
- Frontera de dependencias.
- Instancias de nodos.
- FakeAgentAdapter.
- Handoff inmutable.
- Resultados y eventos.
- Recuperación después de interrupción.

Gate: UAT de recuperación e idempotencia superados.

## Etapa 3 — Conocimiento y contexto

Resultado: construir contexto desde fuentes
y relaciones del proyecto.

Trabajos:

- Fuentes y afirmaciones.
- Relaciones tipadas.
- ContextRecipe.
- Índice de Git.
- Invalidación incremental.
- Un OutcomeTrace de software.

Gate: un agente simulado puede completar
su trabajo sin historial conversacional.

## Etapa 4 — Evolución dinámica

Resultado: incorporar un subgrafo local
durante una ejecución activa.

Trabajos:

- GraphExpansion.
- Validación de patches.
- Control de revisiones.
- Políticas de autorización.
- Nuevas dependencias.
- Reanudación con handoff actualizado.

Gate: ampliación mínima y recuperación verificadas.

## Etapa 5 — Domain Packs y asimilación

Resultado: adoptar una skill convencional.

Trabajos:

- Registro de capacidades.
- Domain Packs declarativos.
- Activación progresiva.
- Importador encapsulado.
- Asimilación asistida por LLM.
- Informe de fidelidad.
- Comandos dinámicos.

Gate: una skill real puede ejecutarse primero
encapsulada y después parcialmente estructurada.

## Etapa 6 — Generalidad multipropósito

Resultado: ejecutar dos ámbitos diferentes
sobre el mismo núcleo.

Trabajos:

- Paquete de software.
- Paquete narrativo o educativo.
- Tipos de dominio extensibles.
- Composición de capacidades.
- Conocimiento independiente por proyecto.

Gate: no se modifica el núcleo para incorporar
los conceptos especializados del segundo dominio.

## Etapa 7 — Endurecimiento

Resultado: versión candidata para uso local real.

Trabajos:

- Adaptador real de agentes.
- Presupuestos y cancelación.
- Seguridad de extensiones.
- Concurrencia.
- Backups y migraciones.
- Observabilidad.
- UAT de aislamiento y recuperación.
- Benchmark de contexto y consultas.

Gate: escenario real completo, instalado,
con resultados y recuperación verificados.

## Orden de prioridades

P0: contratos, persistencia y recuperación.

P1: handoff, conocimiento y expansión dinámica.

P2: asimilación y Domain Packs especializados.

P3: extensiones avanzadas, múltiples proveedores
y optimizaciones del almacenamiento.

## Antiobjetivos

No introducir una base de grafos especializada,
scheduler distribuido o sistema de agentes
permanentes sin un requisito observado.
