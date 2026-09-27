# Especificación de producto

## Visión

SkillGraph convierte skills basadas en instrucciones
en capacidades agenticas estructuradas que pueden
componerse, ejecutarse, verificarse y evolucionar.

La aplicación debe servir para proyectos de software,
escritura, enseñanza, investigación y combinaciones
de diferentes ámbitos.

## Actor principal

Persona que crea, importa o utiliza skills para realizar
trabajos mediante agentes especializados.

## Actores secundarios

- Autor de Domain Packs.
- Desarrollador de extensiones Python.
- Agente orquestador.
- Agente ejecutor especializado.
- Controlador determinista.
- Responsable de revisión humana.

## Concepto de proyecto

Un proyecto es un espacio persistente que contiene
objetivos, fuentes, artefactos, conocimiento, decisiones
y ejecuciones relacionadas.

No equivale necesariamente a un repositorio Git.

Un proyecto puede contener varios ámbitos de conocimiento
y utilizar múltiples Domain Packs.

## Requisitos funcionales

### RF-01: gestión de proyectos

Crear, listar, seleccionar y archivar proyectos.

Registrar fuentes externas sin introducir archivos
internos de SkillGraph en esas fuentes.

### RF-02: bricks declarativos

Crear, importar, validar, consultar y versionar bricks
definidos mediante Markdown/YAML.

### RF-03: Domain Packs

Registrar tipos, capacidades y workflows especializados
sin requerir programación Python.

### RF-04: ejecución

Activar un workflow y registrar todas sus instancias,
transiciones y resultados.

### RF-05: handoffs

Construir paquetes de contexto a partir del contrato
de un nodo y del conocimiento autorizado.

### RF-06: conocimiento

Representar fuentes, entidades, relaciones, afirmaciones,
contratos, evidencias y recorridos transversales.

### RF-07: evolución dinámica

Permitir propuestas de ampliación de grafos durante
una ejecución, con validación y control de autoridad.

### RF-08: recuperación

Reanudar ejecuciones después de interrumpir el proceso,
sin depender de conversaciones anteriores.

### RF-09: asimilación

Importar skills convencionales y convertirlas
progresivamente en Domain Packs.

### RF-10: inspección

Consultar recursos, dependencias, estado, resultados,
evidencias, contexto y revisiones desde la CLI.

### RF-11: aislamiento

Separar los datos de tenants y proyectos.

### RF-12: extensibilidad

Permitir tipos y relaciones especializados sin modificar
el código central de SkillGraph.

## Requisitos no funcionales

- Funcionamiento local sin servidor obligatorio.
- Soporte inicial para Python 3.11 o posterior.
- SQLite como candidato de persistencia inicial.
- Validación estructural sin invocar un LLM.
- Definiciones versionadas e identificables.
- Operaciones de estado idempotentes.
- Recuperación documentada ante interrupciones.
- Presupuesto explícito de contexto y ejecución.
- Proyectos físicamente separados.
- Ausencia de escritura interna en repositorios fuente.
- Dependencias externas limitadas y justificadas.

## No objetivos iniciales

No se pretende:

- Reproducir Kubernetes.
- Crear una plataforma distribuida.
- Implementar todos los ámbitos posibles.
- Garantizar la conversión perfecta de cualquier skill.
- Ejecutar código de terceros durante su importación.
- Crear una interfaz gráfica completa.
- Sustituir Git o los runtimes de agentes existentes.

## Criterio de aceptación global

El núcleo debe completar un workflow representativo
con ampliación dinámica, recuperación, conocimiento
trazable y aislamiento entre proyectos.

La validación debe realizarse con agentes simulados
antes de introducir un proveedor LLM real.
