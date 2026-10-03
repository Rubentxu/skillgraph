# CURRENT — puntero operativo

> **Bloque 2026-10-03 (vigésima tanda) cerrado — WI-108, release `v0.21.2`.**
> Versión activa `0.21.2.dev0`; último tag `v0.21.2`. 2735 passed, **0 skipped**.
>
> **WI-108 — la regla que se escribe con tu letra y no se comprueba con ninguna.**
> Décima vía de la serie «qué declara el repo que nada comprueba», y la más
> pequeña en código: una prohibición de siete palabras con su «por qué»
> escrito al lado.
>
> `AGENTS.md §6.2` dice: **NO usar `pytest.skip` para esconder fallos**,
> y que *un skip por falta de artefacto es el mismo defecto, con otra
> forma*. La segunda línea la escribió WI-103 midiendo un gate que se
> saltaba por falta de informe. De todo el repo, los instrumentos que
> miran skips: **0**. Las etapas de la receta que los miran: **0**.
>
> **Medido antes de tocar nada**, con un run sintético cuyo único cambio es
> la línea de resumen del journal:
>
> ```
> run sin skips:   0 problemas []
> run con 3 skips: 0 problemas []
> veredicto: «OK: el run cumple los criterios que declara AGENTS.md»
> ```
>
> **El detalle grave no es el regex.** Es que el **criterio 2** —el que
> existe para separar un run real de un veredicto cacheado— acepta un
> resumen con skips: `2715 passed, 3 skipped` casa con su regex igual que
> `2718 passed`. No es un bug del regex: es que **la pregunta no se había
> hecho**. Una regla y el criterio que la vigila no se contradicen cuando
> nunca se cruzan.
>
> **Y la regla la incumplía el autor de la regla.** De los cinco skips,
> dos son de plataforma (`fcntl` no existe en Windows: no esconden un
> fallo) y **tres de artefacto** —«sin journal: clon nuevo»—, que es
> literalmente lo que la segunda línea prohíbe. Los escribí yo en WI-105,
> en el guard que construí para no esconder nada.
>
> **Ahora**, `tests/test_wi108_zero_skips.py:301::TestTodoSkipEstaDeclarado`
> exige que no haya skip de ejecución y que los legítimos estén
> declarados, y `scripts/check_pipeline_receipt.py:240::resumen_sin_skips`
> es el predicado puro que la etapa `evidence` mide vía
> `sg_pipeline_tests_skipped`. Pregunta por el **valor**, no por la
> presencia: `0 skipped` es un run limpio.
>
> **Los 3 skips se fueron y no se sustituyeron por nada**, que es la
> decisión que hay que defender: medían el **entorno** —qué pasó en esta
> máquina— y no el **entregable**. El journal no está versionado, así que
> en un clon nuevo se saltaban en silencio y la suite pasaba en verde con
> skips. La tabla de dónde vive ahora cada propiedad está en el fichero
> donde estaban, en `TestLaClaseDeTestQueVivioAQui`.
>
> **El guard que mira el código mira el AST, no el texto.** La primera
> versión buscaba `pytest.skip(` con regex y se puso roja **por su propia
> documentación**: un docstring que cita el patrón es indistinguible de una
> llamada. Segunda vez en dos semanas, mismo repositorio, mismo motivo.
>
> **Mutaciones 9/9 en tres pasadas.** Una de las nueve no la cazó la
> primera sonda porque medía la forma de retorno de un árbol sin llamadas,
> donde esa forma nunca se ejerce: la mutación era inválida, y el harness
> lo dijo en vez de acusar al guard.
>
> **2735 passed y 0 SKIPPED** (+17: 20 tests nuevos de WI-108 menos los 3
> de WI-105 que se fueron). La aritmética y el run coinciden:
> `2718 + 20 − 3 = 2735`. Run canónico `2387c4cc`, verificado por `run_id`.
>
> **Release `v0.21.2`**: PATCH derivado con `scripts/derive_semver.py`
> (`b/f/x/n/d 0/0/1/4/0`). Commit `841a075`, etiqueta anotada sobre él,
> post-release `4eb56af`.
>
> **Sin push**: 156 commits sin publicar, `origin/main` en `0ebbd58`.

---
---

<details>
<summary>Bloques anteriores (WI-106 y anteriores)</summary>

> **Bloque 2026-10-03 (decimoctava tanda) cerrado — WI-106, SIN RELEASE.**
> Versión activa `0.21.0.dev0`; último tag `v0.21.0`. 2703 passed, **0 skipped**.
>
> **WI-106 — la causa de un bump era una afirmación sin verificar.**
> Octava vía de la serie «qué declara el repo que nada comprueba», y la
> más pequeña: un solo campo.
>
> `STATE.yaml` declara **por qué** se movió la versión
> (`release.semver_bump`). `scripts/derive_semver.py` la **calcula**.
> Nadie los comparaba: el campo aparecía en un sitio y en dos informes de
> `audits/`, y ningún test lo leía.
>
> **Medido**, con `STATE.yaml` restaurado byte a byte y sha verificado:
> puesto el campo a `MAJOR` cuando el release fue `MINOR`, la suite de
> gobernanza de release daba **18 passed, exit 0**, y los tres checkers
> de la receta y el bundle de auditoría, también `exit 0`. Con el guard
> puesto, la misma mentira da **2 failed, exit 1**.
>
> **Ahora se contrasta:**
> `tests/test_wi96_semver_rule.py:380::TestLaDeclaracionDelBumpCoincideConLaHerramienta`
> exige que el campo sea lo que la regla dice para `release.tag`. El
> **nivel** de la versión ya estaba verificado —la lista de divergencias
> históricas no puede crecer—; lo que no exigía nadie es que el campo
> dijera la verdad.
>
> **Dos trampas, y las dos las encontré porque las mutaciones
> sobrevivieron.** La primera versión daba 4/6. (1) Comparar contra una
> **constante escrita a mano**: hoy la copia dice lo mismo que la verdad,
> y el día que la regla cambie dirá lo contrario — se exige que el cálculo
> acierte en **dos bumps distintos**, cosa que un literal no puede. (2)
> Comprobar el dominio sobre el valor de hoy: que `MINOR` sea válido no
> es que el dominio exista, así que `RELLENO` y `v9.9.9` tienen que ser
> rechazados por entrada, no por el valor real.
>
> **M1 —borrar la aserción que manda— NO se cuenta como fallo.** Es
> indetectable por construcción: un test que comprueba que el estado
> coincide con la herramienta no puede comprobar que sigue ahí. Lo que
> se mide es su interacción con M6, y con M1 puesta el estado puede
> mentir y nadie lo ve: la demostración de que era el **único** punto de
> aplicación. Mutaciones 6/6.
>
> **SIN RELEASE, y por regla.** Los cinco commits desde `v0.21.0`
> clasifican como `neutro` —ni `feat` ni `fix`— así que
> `derive_semver.py` dice **SIN RELEASE**, y `AGENTS.md §12` es
> explícito: *«Si la regla dice “sin bump”, no se emite etiqueta: el
> trabajo se acumula»*. Es el primer bloque de la serie que no libera, y
> es la regla siguiendo en vez de la regla saltándose.
>
> **Dos hipótesis que medí y resultaron falsas**, antes de llegar a esta:
> que el `pre-push` comprobara el CI con un `grep` sobre el stdout —falso:
> usa el exit code, y `ci.sh` pasa `--rerun`— y que los cuatro UAT stub
> pudieran desaparecer en verde —falso: WI-101 lo cerró, `--verify` da
> exit 1 con `persistido=MISSING`.
>
> **Sin push**: 143 commits sin publicar, `origin/main` en `0ebbd58`.

</details>
