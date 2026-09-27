# Referencias y procedencia

Fecha de consulta de referencia: 2026-09-22.

Estas fuentes orientan la arquitectura.
No sustituyen las pruebas de integración
sobre versiones concretas.

## Material aportado durante la exploración

### Evidence-Driven Implementation Decision

Método aportado por el usuario.

Principios utilizados:

- Autoridad real.
- Trazado end-to-end.
- Caracterización del comportamiento.
- Evidencia verificable.
- Cambios mínimos y reversibles.
- GO/STOP.
- Invalidación de suposiciones.
- Arquitectura emergente.

### Wayfinder

https://github.com/mattpocock/skills

Conceptos utilizados:

- Destino.
- Mapa canónico.
- Fichas de decisión.
- Dependencias.
- Frontera.
- Incertidumbre todavía no especificable.

### Teach

https://github.com/mattpocock/skills

Conceptos utilizados:

- Misión persistente.
- Recursos.
- Registros de aprendizaje.
- Componentes reutilizables.
- Consolidación progresiva de conocimiento.

## Workflows dinámicos de Claude Code

https://claude.com/blog/introducing-dynamic-workflows-in-claude-code

Aporta el contraste entre orquestación programática,
subagentes, verificación y continuidad fuera
de la conversación principal.

SkillGraph conserva su propio modelo declarativo.

## ActiveGraph

https://github.com/yoheinakajima/activegraph

Conceptos relevantes:

- Grafo reactivo.
- Registro de eventos.
- Vistas acotadas.
- Patches.
- Relaciones tipadas.
- Frames.
- Replay y fork.

La integración concreta queda pendiente de spike.

## Agit / agent-git

https://github.com/Einsia/agent-git

Posible uso auxiliar:

- Trazabilidad de sesiones.
- Historial de conversaciones.
- Continuidad opcional de sesiones.

No se adopta su modelo como persistencia
canónica de bricks o workflows.

## Kubernetes

https://kubernetes.io/docs/concepts/extend-kubernetes/api-extension/custom-resources/

Inspiración para:

- Definiciones de tipos.
- Recursos declarativos.
- Separación spec/status.
- Controladores.
- Reconciliación.

SkillGraph no necesita ejecutar Kubernetes.

## SQLite

https://www.sqlite.org/wal.html

https://www.sqlite.org/lang_attach.html

https://www.sqlite.org/lang_with.html

Referencias para concurrencia local,
bases adjuntas y consultas recursivas.

## Git

https://git-scm.com/docs/git-hash-object

https://git-scm.com/docs/git-rev-parse

Referencias para identidad de contenidos,
revisiones y worktrees.

## Política de investigación

Las decisiones arquitectónicas se basan
en casos concretos y pruebas reproducibles.

Una característica documentada de una dependencia
no demuestra por sí sola que su integración
satisfaga nuestros contratos.
