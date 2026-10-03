# Verificación WI-106 — la causa de un bump, contrastada

- **Ciclo**: `p-b7740b96d79ec013/wi106-semver-bump-afirmacion-sin-verificador`
- **Sesión**: `wi106-20261003T034000Z`
- **Fecha**: 2026-10-03
- **Release**: **ninguna**, y por regla (ver §3)
- **Run que cierra**: `33795b8d-8b2b-4434-bc0f-3b501af49ce6`
  — 8/8 stages `success`, **2703 passed, 0 skipped**, 0 `StepFailed`,
  `VEREDICTO: todos los suelos declarados se cumplen`, árbol quieto.
  Es el run que certifica **el estado final**, con esta evidencia escrita.
- **Run del código** (antes de escribir la evidencia):
  `c1124ff5-d4a1-424d-8abd-d67785931598` — las mismas cifras. Fue el que
  destapó el `2702` escrito a mano (§5).
- **SHA-256 de `.pipeline.kts`**: `7541ced5…dd42`, sin drift desde WI-105.

> El commit posterior a `33795b8d` sólo toca la cabecera de este fichero
> para anotar el identificador. Es la convención que el repo viene usando
> desde WI-101: el run certifica el estado, y el commit posterior es el
> que *cuenta* esa certificación. Editar el árbol **con el run en marcha**
> sí lo invalidaría — eso costó una certificación descartada en WI-102.

---

## 1. El defecto

`STATE.yaml` declara **por qué** se movió la versión
(`release.semver_bump`). `scripts/derive_semver.py` la **calcula**. Nadie
los comparaba: el campo aparecía en `STATE.yaml:1131` y en dos informes de
`audits/`, y ningún test lo leía.

Medido con `.pipelinek/wi106_measure2.sh`, con `STATE.yaml` restaurado byte
a byte y sha verificado:

| | antes del guard | con el guard |
|---|---|---|
| `semver_bump: MINOR` → `MAJOR` (el release fue MINOR) | **18 passed, exit 0** | **2 failed, exit 1** |
| `check_ci_recipe_parity` | exit 0 | exit 0 |
| `check_coverage_floors` | exit 0 | exit 0 |
| `check_package_build` | exit 0 | exit 0 |
| bundle de auditoría | exit 0 | exit 0 |

Una afirmación falsa sobre la causa de un bump, invisible para todo el repo.

**Lo que ya estaba verificado** es que el *nivel* de la versión es correcto:
`test_wi96_semver_rule.py::TestLasDivergenciasHistoricasEstanRegistradas`
vigila que la lista de divergencias históricas no crezca. Lo que no exigía
nadie es que el campo **diga la verdad**.

## 2. El arreglo, y las dos trampas que lo atravessaban

Tres tests, cada uno sobre una propiedad distinta. La primera versión tenía
cuatro y daba **4/6** mutaciones, y las dos que la atravesaban eran las que
importan:

1. **Comparar contra una constante escrita a mano** en vez de la
   herramienta. Hoy la copia dice lo mismo que la verdad y el test pasa
   verde; el día que la regla cambie dirá lo contrario, con toda la autoridad
   de un test. *Un guard que compara contra su propia copia de la verdad no
   vigila nada.* Se corrige exigiendo que el cálculo acierte en **dos bumps
   distintos**, cosa que un literal no puede.
2. **Comprobar el dominio sobre el valor de hoy.** Que `MINOR` sea válido no
   es que el dominio exista: anulada esa comprobación, el test seguía verde
   porque el valor real es válido. Se extraen `_bump_valido` y
   `_etiqueta_existe` como predicados puros y se les llama con `RELLENO`, la
   cadena vacía, `minor` y `v9.9.9`.
3. El tercer test **duplicaba** al primero. Dos copias de la misma aserción no
   son redundancia, son decoración: una sobrevive a que borren la otra. Se
   sustituyó por una propiedad distinta.

**M1 —borrar la aserción que manda— no se cuenta como fallo.** Es
indetectable por construcción: un test que comprueba que el estado coincide
con la herramienta no puede comprobar que sigue ahí. Lo que se mide es su
**interacción con M6**, y con M1 puesta el estado puede mentir y nadie lo
ve, que es la demostración de que era el **único** punto de aplicación.
Contarlo como fallo sería inventar una propiedad que no existe; esconderlo
sería mentir sobre la cobertura.

M6 muta el `STATE.yaml` **real**. Un invariante que solo sabe fallar con
entradas inventadas está limpio en las pruebas y ciego en el repo.

## 3. Sin release, y por regla

Los cinco commits desde `v0.21.0` clasifican como `neutro` —ni `feat` ni
`fix`— así que `derive_semver.py` dice **SIN RELEASE**, y `AGENTS.md §12` es
explícito: *«Si la regla dice "sin bump", no se emite etiqueta: el trabajo se
acumula»*.

Es el primer bloque de la serie que no libera. Es la regla siguiendo, no la
regla saltándose: forzar una `v0.22.0` para «cerrar el bloque» habría sido
exactamente la decisión a mano que la propia §12 prohíbe — y `semver_bump` es
el campo que este bloque acaba de poner bajo contraste.

`release.tag` sigue en `v0.21.0` y `release.semver_bump` en `MINOR`, que es lo
que el guard exige y lo que la herramienta dice para esa etiqueta.

## 4. Dos hipótesis medidas y falsas

Publicarlas es parte del resultado: el camino descartado también es evidencia.

1. *El `pre-push` comprueba el CI con un `grep` sobre el stdout.* **Falso.**
   Usa el exit code de `scripts/ci.sh`, y ese script pasa `--rerun`, así que
   es inmune al veredicto cacheado. No hay workitem ahí.
2. *Los cuatro UAT stub de `_STUB_UATS` pueden desaparecer en verde.*
   **Falso.** WI-101 lo cerró: apartando `UAT-08/09/12/13.json`, `--verify`
   imprime `UAT-08: persistido=MISSING ejecutado=BLOCKED` y sale con **1**.

## 5. Una cifra que me corregí a mí mismo

Escribí `2702` en `STATE.yaml` y `CURRENT.md` contando `+3`. La
certificación dio **2703**: la clase tiene **cuatro** tests, no tres. La
cifra que manda es la del run, no la cuenta, y se corrigió en los tres
ficheros.

## 6. Cifras finales

- **2703 passed, 0 skipped** (+4 sobre 2699).
- SemVer: **sin bump** derivado, por tanto sin etiqueta.
- `ruff check src tests scripts` y `format --check` verdes.
- Mutaciones 6/6 (`.pipelinek/wi106_mutate.sh`), tercera tanda consecutiva
  que sale a la primera.

Sin push: 143 commits sin publicar, `origin/main` en `0ebbd58`. Push no
autorizado.
