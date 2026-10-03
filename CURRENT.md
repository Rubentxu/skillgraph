# CURRENT — puntero operativo

> **Bloque 2026-10-03 (decimonovena tanda) — WI-107, en curso de cierre.**
> Versión activa `0.21.0.dev0`; último tag `v0.21.0`. 2718 passed, **0 skipped**.
>
> **WI-107 — la lista que se salva cambiando de eje no deja de ser una lista.**
> Novena vía de la serie «qué declara el repo que nada comprueba», y la
> tercera vez que la misma idea se salva a sí misma con otra forma.
>
> `AGENTS.md §6.3` declara suelos de cobertura. WI-93 lo implementó con una
> lista de 21 módulos; WI-94 la cambió por un suelo por paquete, con **ocho
> prefijos escritos a mano**, y su docstring afirmaba que con eso «no se
> puede olvidar uno». Es falso: cambiar el eje de una lista no la deshace.
>
> **Medido antes de tocar nada**, con un paquete nuevo (`telepatia/`) con
> código que nadie importa y **ya versionado en git**:
>
> ```
> pytest                    2709 passed in 234.75s
> check_coverage_floors.py  exit 0, «todos los suelos se cumplen»
> cobertura de oracular.py  0 %  (18 sentencias, 10 ramas, 0 cubiertas)
> suelo global              94.85 %   (fail_under = 80)
> ```
>
> Se midió **dos veces** y la segunda es la que se cita, porque la primera
> daba un resultado más fuerte y falso: con el paquete sin versionar, la
> suite daba `1 failed`, y el rojo era `sg_build_sdist_no_versionado`
> (WI-97), que lo delata por otra propiedad y con otro mensaje. Un paquete
> nuevo se versiona; ese aviso no es el contrato de §6.3.
>
> **Ahora el suelo es la norma y las listas son las desviaciones.**
> `tests/test_wi107_coverage_package_symmetry.py:220::TestTodoPaqueteTieneSuelo`
> exige que un paquete que no figura en ninguna lista herede el suelo por
> defecto. Lo escrito son dos entradas —`cli/` al 70 % y
> `platform/paths.py` al 60 %— porque son datos que el código no puede
> deducir. De ocho, dos. Y `§6.3` deja de enumerar módulos: `runtime` no es
> un módulo sino un paquete, `runtime.py` no existe, y nueve de los diez
> enumerados vivían fuera de `core/`.
>
> **El mismo dato, el otro veredicto.** Antes `exit 0`; ahora `exit 1` con
> `BAJO 0.00 % (suelo 90.0 %) src/skillgraph/telepatia/oracular.py`. Mismo
> dato, distinto veredicto: lo que cambió fue el instrumento, no la
> medición.
>
> **Dos hallazgos que salieron de las propias mediciones**, no de un test:
> (1) El primer guard de `§6.3` **pasaba por la rama equivocada**: buscaba
> `nombre.py` y `§6.3` escribe los módulos sin extensión, así que no
> encontraba nada. Se sustituyó por un predicado puro probado antes contra
> un texto escrito en la forma real del doc. (2) Un contraejemplo mío
> usaba como «paquete que no existe» el nombre del paquete de la medición,
> así que con él presente el test se ponía rojo: un guard que depende del
> árbol sin decirlo es una coincidencia. Lo destapó la medición post.
>
> **La mutación que a veces sobrevivía, y por qué el harness cambió.**
> Primera pasada: 6/8 con `m2` sobrevivida. Segunda, del **mismo** código:
> 7/8 con `m2` cazada. Una mutación que a veces sobrevive no es un guard
> que no muerde: es un experimento que no sabe qué midió. Con
> `PYTHONDONTWRITEBYTECODE=1` y una **sonda por mutación** —una expresión
> que tiene que cambiar de valor con el código ya mutado— las tres salidas
> tienen nombre: *cazada*, *inválida* (la sonda no cambió: la mutación no
> degradaba nada) y *el entorno no vio la mutación*. **8/8 en tres pasadas
> consecutivas**, árbol restaurado byte a byte en las tres.
>
> **2718 passed y 0 SKIPPED** (+15: 22 tests nuevos de WI-107 menos los 7
> que pierde el parametrize de WI-94, que pasa de ocho paquetes a uno).
> Mutaciones 8/8. Run canónico `332e09e6` verificado por `run_id`.
>
> **Sin push**: 147 commits sin publicar, `origin/main` en `0ebbd58`.

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
