# WI-74 — Exploración: el drift entre `STATE.yaml` y la realidad de git

> Ciclo `p-b7740b96d79ec013/wi-74-state-release-drift`. Base: `da1d7a5`.

## Por qué este workitem y no otro

El frente P3 está agotado: quedan 4 funciones y ninguna tiene cc alto
(`build_parser` es una tabla declarativa, las otras tres son lineales o
marginales). Antes de abrir un frente nuevo, se miró qué **auditorías
abiertas** quedaban en el repo, que es parte del objetivo original
("cerrando auditorías").

`audits/state-sync-gap-2026-09-25.md` sigue marcando hallazgos abiertos.
Comprobado hoy contra git, **sigue abierto y ha empeorado**.

## 1. Medición (`git` como única fuente de verdad)

| Métrica | Valor |
|---|---|
| tags SemVer en git | 37 (última: `v0.16.10`) |
| releases listadas en `STATE.yaml` | 35 |
| `release.tag` declarado | `v0.16.8` |
| `release.tag` real | **`v0.16.10`** |
| tags ausentes de `STATE.yaml` | 2 (`v0.16.9`, `v0.16.10`) |
| tags inventados en `STATE.yaml` | 0 |
| entradas con SHA divergente | 9 |

## 2. Los cuatro hallazgos, por gravedad

### H-1: cuatro SHA **no existen en el repo** (grave)

`v0.14.1` a `v0.14.4` declaran `1947df6`, `7413f0c`, `d8ec98a` y `9e1cd12`.
`git cat-file -e <sha>^{commit}` falla en los cuatro: **no son commits de
este repositorio**.

Lo más probable es que el historial se reescribió en algún momento y
estas entradas se escribieron con los SHA anteriores. El efecto es
directo: `STATE.yaml` es el **punto de recuperación durable** (su
encabezado dice "apunta a la verdad observable"), y Restaurar desde él
lleva a commits que no existen.

### H-2: dos SHA existen pero apuntan al commit equivocado

- `v0.14.8`: STATE dice `4a297ad1` ("docs(release): v0.14.8 release-receipt"),
  la etiqueta apunta a `c5c405e3`.
- `v0.16.8`: STATE dice `8eda4ea4` ("chore(repo): ignora .jcode-scratch"),
  la etiqueta apunta a `df72bcc0`.

Peeeeor: parecen el commit de la *documentación* del release, no el del
tag. El campo no significa lo que su nombre dice.

### H-3: tres entradas usan el campo `sha` para prosa libre

`"0.14.5 housekeeping rollup"`, `"WI-11 release bundle"`,
`"WI-12..WI-17 release bundle"`. Un campo llamado `sha` con texto en
prosa hace que cualquier validación automática que lo compare con git
falle de forma incomprensible, en vez de detectar un error de datos.

### H-4: dos releases sin registrar y `release.tag` desfasado

`v0.16.9` y `v0.16.10` no están. `v0.16.10` es la release que se acaba de
publicar en esta sesión.

## 3. Por qué nadie lo notó

La auditoría de deuda arquitectónica **sí** tiene red que ata su prosa a
la medición (`tests/test_audit_debt_accuracy.py`, WI-69). `STATE.yaml`
no tiene nada equivalente: nadie compara su sección de releases con
`git tag`.

Y el repo tiene el patrón ya, repetido dos veces: un documento de deuda
que miente es peor que no tenerlo, porque genera confianza falsa. El
`release_governance` cubre `__version__` contra la etiqueta de HEAD, pero
no el historial.

## 4. Qué NO se hace aquí

- **No se reescribe historia.** Los cuatro SHA de H-1 no se "arreglan"
  inventando un valor: se sustituyen por el que git dice y se registra
  que el anterior no resolvía. La diferencia importa y hay que poder
  leerla después.
- **No se corrige `__version__`**: ya es correcto
  (`0.16.10.dev0`, rama 2 del gate de release).
- **No se toca la divergencia de la etiqueta `v0.7.1`**: es histórica y
  AGENTS.md prohíbe `tag --force`. Ya está reportada.

## 5. Veredicto

Exploración suficiente. Dos acciones: **reconciliar** `STATE.yaml` con
git (H-1..H-4) y **añadir la red que falta** para que no vuelva a
diverger sin que nadie lo note. La red es la parte durable; sin ella la
reconciliación es una fotografía.

Sin cambio de código de producto: solo estado y tests. Por tanto **sin
ADR** (no hay contrato ni arquitectura que mover), y el tipo de commit
será `fix(state)` + `test`.
