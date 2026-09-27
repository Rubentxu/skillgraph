# Mapa Wayfinder — SkillGraph

Estado: mapa para iniciar implementación incremental.

## Destino

Definir y validar una plataforma local-first en Python
que convierta skills en Domain Packs declarativos,
componga workflows agenticos dinámicos, gestione
conocimiento verificable y ejecute trabajos mediante
handoffs contractuales y bricks reutilizables.

## Notas

La arquitectura debe evolucionar a partir de
evidencias obtenidas durante los spikes y UAT.

No introducir infraestructura general antes de
demostrar un caso concreto que la necesite.

El objetivo inicial es un vertical slice operativo,
no una plataforma completa.

## Decisiones tomadas

- Núcleo determinista en Python: ADR-0001.
- Bricks como recursos declarativos: ADR-0002.
- Domain Packs Markdown/YAML: ADR-0003.
- Contexto mediante handoffs: ADR-0006.
- Conocimiento vinculado a fuentes: ADR-0007.
- Datos internos fuera de los proyectos: ADR-0008.

Estos documentos establecen la dirección de diseño.
Sus contratos detallados pueden refinarse durante
la implementación.

## Decisiones propuestas pendientes

- Modelo definitivo de GraphPatch: ADR-0004.
- Backend de persistencia inicial: ADR-0005.
- Estrategia de asimilación: ADR-0009.
- Integración con ActiveGraph y agit: ADR-0010.
- Contrato de controladores: ADR-0011.
- Política de autoridad y capacidades: ADR-0012.

## Fichas abiertas

### Contrato de brick

Tipo: prototipo.

Pregunta:

¿Qué esquema mínimo permite registrar, validar,
versionar y relacionar un brick declarativo?

Dependencias: ninguna.

### Persistencia local

Tipo: investigación y prototipo.

Pregunta:

¿SQLite convencional resuelve las consultas,
transacciones y recuperación necesarias
para el primer vertical slice?

Dependencias: ninguna para la investigación inicial.

### Integración con ActiveGraph

Tipo: investigación y prototipo.

Pregunta:

¿Qué primitivas de ActiveGraph reducen realmente
el trabajo de SkillGraph sin imponerle
un modelo de dominio o workflow incompatible?

Dependencias: contrato mínimo de brick.

### Ejecución recuperable

Tipo: prototipo.

Pregunta:

¿Puede una instancia de nodo recuperarse desde
estado persistido sin repetir efectos confirmados?

Dependencias: contrato de brick y persistencia.

### Contexto contractual

Tipo: prototipo.

Pregunta:

¿Puede construirse un handoff suficiente desde
referencias tipadas sin historial conversacional?

Dependencias: contrato de brick y conocimiento.

### Expansión mínima

Tipo: prototipo.

Pregunta:

¿Puede un subgrafo incorporarse a una ejecución
sin modificar los resultados anteriores?

Dependencias: contrato de brick, ejecución recuperable
y política de autoridad.

### Asimilación de skills

Tipo: prototipo.

Pregunta:

¿Puede una skill importarse encapsulada y
estructurarse progresivamente conservando
sus instrucciones esenciales?

Dependencias: contrato de brick y capacidades.

## Aún por especificar

- Migraciones complejas de esquemas de dominio.
- Distribución multiusuario.
- Extensiones avanzadas del SDK.
- Optimización de grafos de gran escala.
- Compatibilidad con múltiples proveedores LLM.

## Fuera de alcance

- Reproducir Kubernetes.
- Desarrollar un clúster distribuido.
- Implementar todos los Domain Packs posibles.
- Garantizar conversión perfecta de cualquier skill.
- Introducir servidores externos obligatorios.

## Frontera inicial

Pueden abordarse en paralelo:

- Contrato mínimo de brick.
- Investigación de SQLite.
- Delimitación de la integración con ActiveGraph.

Las dependencias se revisarán después de los
resultados de esos trabajos.

## Regla de recorrido

Resolver una ficha de decisión por intervención,
salvo investigaciones independientes.

Registrar cada decisión y sus motivos en su ADR
o ficha correspondiente.

Actualizar este índice sin duplicar
todo el razonamiento de las fichas.
