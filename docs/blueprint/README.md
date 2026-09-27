# SkillGraph — Blueprint de arquitectura e implementación

Versión del documento: 1.0-draft

Fecha: 2026-09-22

Estado: especificación inicial para implementación incremental.

## 1. Propósito

SkillGraph es una plataforma local-first para convertir skills
de agentes en workflows declarativos, dinámicos, verificables
y extensibles.

Una skill tradicional describe una capacidad mediante
instrucciones. SkillGraph permite representar esas instrucciones
como recursos tipados —bricks— conectados mediante relaciones,
contratos, dependencias y transiciones.

Durante la ejecución, los agentes pueden descubrir nuevas
problemáticas y proponer ampliaciones mínimas de los grafos.

El sistema distingue:

- Definiciones reutilizables.
- Estado de ejecuciones concretas.
- Conocimiento del proyecto.
- Evidencias y decisiones.
- Contexto entregado a cada agente.
- Cambios temporales y permanentes de comportamiento.

La evolución de una ejecución no modifica automáticamente
la definición reutilizable de una skill.

## 2. Principios

1. Markdown/YAML como interfaz declarativa principal.
2. Python para la capa determinista mínima.
3. El agente razona; el núcleo valida y conserva el estado.
4. Cada nodo recibe contexto suficiente y delimitado.
5. La conversación completa no es el mecanismo de memoria.
6. El conocimiento conserva procedencia, vigencia y relaciones.
7. Los workflows evolucionan mediante cambios mínimos.
8. Las definiciones y sus ejecuciones son objetos diferentes.
9. Los Domain Packs son extensibles sin modificar el núcleo.
10. Los datos internos viven fuera de los proyectos analizados.
11. Ninguna ampliación adquiere capacidades implícitamente.
12. Toda ejecución conserva trazabilidad de sus resultados.

## 3. Decisiones ya establecidas

- Lenguaje del núcleo: Python.
- Interfaz principal: CLI.
- Formato de autoría: Markdown con YAML front matter.
- Modelo conceptual: bricks inspirados en recursos declarativos.
- Domain Packs: declarativos por defecto; Python opcional.
- Arquitectura: multipropósito y especializada por proyecto.
- Persistencia: local, separada por tenant y proyecto.
- Almacenamiento interno: directorios de datos del usuario.
- Evolución: cambios mínimos sobre revisiones versionadas.
- Handoff: contrato explícito entre procesos o agentes.

## 4. Hipótesis pendientes de validación

- SQLite convencional como almacenamiento inicial.
- Un único proceso Python con controladores internos.
- Registro de eventos y proyecciones reconstruibles.
- ActiveGraph como posible proveedor de primitivas.
- Conversión progresiva de skills convencionales.
- Esquemas de conocimiento extensibles por Domain Pack.

Estas hipótesis no deben tratarse como decisiones irreversibles.

## 5. Estructura de la documentación

### Especificación

- docs/01-producto.md
- docs/02-arquitectura.md
- docs/03-bricks-y-tipos.md
- docs/04-contratos-de-recursos.md
- docs/05-workflows-y-ciclo-de-vida.md
- docs/06-controladores.md
- docs/07-contexto-y-handoff.md
- docs/08-conocimiento.md
- docs/09-persistencia.md
- docs/10-cli-y-asimilacion.md
- docs/11-seguridad-y-recuperacion.md
- docs/12-integraciones.md

### Decisiones arquitectónicas

Consultar adr/.

### Ejecución del proyecto

- plan/ROADMAP.md
- plan/HITOS.md
- plan/SPIKES.md
- plan/UAT.md
- plan/ESTRATEGIA-DE-TESTS.md
- plan/MAPA-WAYFINDER.md

### Referencias

- references/FUENTES.md

## 6. Cómo utilizar este paquete

1. Incorporar los documentos a la carpeta de documentación
   del nuevo proyecto.

2. Revisar los ADR propuestos y registrar su aceptación
   o modificación cuando corresponda.

3. Ejecutar los spikes de la primera fase.

4. Implementar el primer vertical slice sin LLM real.

5. Añadir el primer adaptador de agente después de verificar
   persistencia, contratos y recuperación.

6. Evolucionar el diseño utilizando las evidencias obtenidas.

No comenzar implementando simultáneamente todos los
controladores, Domain Packs e integraciones.

## 7. Criterio de éxito del primer producto

Una persona puede importar un Domain Pack Markdown,
registrarlo en un proyecto, ejecutar un workflow,
inspeccionar el handoff y el resultado, introducir una
ampliación mínima y reanudar la ejecución.

Todo el estado debe sobrevivir al reinicio del proceso
sin depender del historial completo de conversaciones.
