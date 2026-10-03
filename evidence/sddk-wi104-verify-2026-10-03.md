# Verificación WI-104 — la cita de `CURRENT.md` dice a qué apunta

- **Ciclo**: `p-b7740b96d79ec013/wi104-la-cita-debe-decir-a-que-simbolo-apunta`
- **Sesión**: `wi104-20261003T025000Z`
- **Fecha**: 2026-10-03
- **Release**: `v0.20.5` (PATCH, derivado con `scripts/derive_semver.py`)
- **Run que cierra**: `88d16828-4b9c-4c80-be16-52dcc78c220e`
  — 8/8 stages `success`, **2684 passed, 0 skipped**, 0 `StepFailed`,
  `VEREDICTO: todos los suelos declarados se cumplen`, árbol quieto.
- **Run descartado**: `7d68ca93-ded4-4a14-a265-e4d5c2b81cd2`
  — `RunFinished/failure`, 1 `StepFailed`, `1 failed, 2683 passed`.
- **SHA-256 de `.pipeline.kts`**: `d8658968…3ddcc`, sin drift desde WI-98.

---

## 1. El defecto, medido antes de tocar nada

`tests/test_wi92_measured_claims.py::TestBlockCitationsDelCurrentVivoResuelven::test_toda_cita_del_bloque_vivo_resuelve`
daba por buena **cualquier línea que existiera**: su único predicado era
`linea <= total_lineas`.

Es **resolubilidad, no verdad**, y la diferencia ya había salido cara en
WI-102: se escribieron las líneas 352 y 479 de
`scripts/check_ci_recipe_parity.py` donde las reales eran la 421
(`checkers_de`) y la 589 (`evaluar_contratos_de_la_receta`).

`.pipelinek/wi104_measure.py` (solo lectura, cinco casos con la verdad al
lado):

```
fichero:linea                                   hoy  propuesta   real
tests/_gate_main_hotspot.py:73                 True       True   True  [OK]
scripts/check_ci_recipe_parity.py:421          True       True   True  [OK]
scripts/check_ci_recipe_parity.py:589          True       True   True  [OK]
scripts/check_ci_recipe_parity.py:352          True      False  False  [MAL]
scripts/check_ci_recipe_parity.py:479          True      False  False  [MAL]

El predicado ACTUAL falla en 2 caso(s)
El predicado PROPUESTO falla en 0
```

**Por qué se separan tan limpiamente:** 352 y 479 son prosa dentro de un
docstring (`filtra_por_ficheros`, `evaluar_portabilidad`); 421 y 589 son
líneas `def`. Una cita dice «aquí está X», y X tiene que **introducirse** en
esa línea.

## 2. La causa raíz no es el número

Con sólo `fichero.py:N` no hay manera de distinguir *«he abierto el
fichero»* de *«he escrito un número que me sonaba»*. Por eso el error se
colaba sin que nada lo notara, y por eso el arreglo no es añadir una
comprobación más sino **cambiar el formato**:

```text
ruta/fichero.py:LINEA::simbolo
```

El símbolo se resuelve en el AST del fichero **que la cita nombra** —no en
cualquiera del repo, que es el fallo de resolver por basename— y `LINEA`
tiene que caer dentro de su definición. Cuando una cita envejece porque
alguien insertó una línea arriba, el error **dice dónde está el símbolo
ahora**: un verificador que dice «falso» sin decir «está aquí» deja al que
corrige en un callejón sin salida.

## 3. Mutaciones: 6/6, pero el contraejemplo hubo que arreglarlo dos veces

`.pipelinek/wi104_mutate.sh` + `wi104_muts/m1..m6.py`, autocontrolado
(backup byte a byte, trap, sha256 verificado al salir).

**La primera pasada dio 3/6**, y las tres que sobrevivieron no eran
contraejemplos débiles: **pasaban por el motivo equivocado**.

| mutación | degradación | quién la detectó |
|---|---|---|
| M1 | el verificador devuelve siempre `()` | la prueba de desalineación, **corregida** |
| M2 | basta con que el símbolo exista | `test_linea_de_prosa_dentro_de_un_docstring_falla` |
| M3 | el ancla pasa a ser opcional | la regla del ancla, **corregida** |
| M4 | el símbolo se busca en todo el repo | la prueba del fichero ajeno, **corregida** |
| M5 | el error no dice dónde está el símbolo | `test_el_error_dice_donde_esta_el_simbolo` |
| M6 | la cita del `CURRENT.md` **real** pasa a `:70` | guard de extremo a extremo |

Las tres correcciones:

1. `test_linea_real_con_simbolo_equivocado_falla` usaba `cargar_auditor`,
   que **no es un símbolo** —se llama `_cargar_auditor`—, así que la prueba
   pasaba por la rama de «no lo define» y no medía la desalineación. M1
   apagaba justo esa comprobación y pasaba verde. Ahora usa
   `_cargar_auditor` y además exige que el mensaje diga `53`.
2. La regla del ancla se comprobaba sobre `_citas_vivo()`, que **nunca**
   produce una cita sin ancla. Relajarla *dentro* del verificador —M3, la
   más probable porque no rompe nada visible— pasaba sin que nada lo notara.
   Se extrajo `_problemas_del_bloque`, que verifica cualquier lista de
   citas, y por ahí se pasa una cita sin ancla.
3. Resolver el símbolo en todo el repo (M4) daba el error equivocado sin que
   ninguna prueba lo notara. Ahora el test exige que el error señale **el
   fichero** que debería definirlo.

> Un contraejemplo que no degrada nada no prueba que el guard funcione, y
> tres de seis no medían lo que decían medir. **La señal de que algo va
> mal es que la mutación sobrevive**, no que el test esté en verde.

## 4. El guard atrapó al autor

Al escribir el bloque vivo de `CURRENT.md` se contó el fallo anterior
usando el patrón `fichero.py:352`, y el guard lo leyó como una afirmación y
lo rechazó:

```
tests/test_wi92_measured_claims.py::TestBlockCitationsDelCurrentVivoResuelven::test_toda_cita_del_bloque_vivo_apunta_a_lo_que_dice
E   AssertionError: el bloque vivo de CURRENT.md cita codigo que no esta donde dice:
E       scripts/check_ci_recipe_parity.py:352 — la cita no dice a que simbolo apunta
```

Es lo correcto: un bloque que cuenta un error usando el formato del error se
contradice a sí mismo. La regla queda escrita en `AGENTS.md` — el bloque vivo
cita el código de hoy; la arqueología va al `CHANGELOG.md`.

## 5. La primera certificación falló, y lo que atrapó ya existía

Run `7d68ca93` → `1 failed, 2683 passed`:
`test_every_semver_tag_is_listed_exactly_once` — la etiqueta `v0.20.5` no
estaba en `release.releases[0]` de `STATE.yaml`, que seguía siendo
`v0.20.4`. Se había actualizado `release.tag` y no `release.releases[]`.

**El guard no es de este bloque**: existe desde WI-99 y habría pillado el
mismo error entonces. Lo que falló fue el recorrido de release. Y el
testing quirúrgico no podía verlo: los tres ficheros tocados no consultan
`STATE.yaml`. Solo la suite entera —que es lo que corre la receta— lo ve.

## 6. Cifras finales

- **2684 passed, 0 skipped** (+7 sobre 2677).
- Cobertura global **95.22 %** (suelo 80 %); `cli/` 86.91 % (suelo 70 %);
  `runtime/` 97.98 % (suelo 90 %).
- SemVer **PATCH** derivado: `derive_semver.py` → «la regla pide PATCH ->
  v0.20.5» (0 `feat`, 1 `fix`, 1 `docs`, 0 breaking).
- `ruff check src tests scripts` y `format --check` verdes.

## 7. Lo que NO se comprueba, declarado

Que la prosa describa de verdad el símbolo **no es machine-checkable**. El
guard baja la afirmación de «esta línea existe» a «esta línea introduce el
símbolo que la cita nombra y el símbolo existe en ese fichero» — una
propiedad real y verificable, pero no la prosa.

Sin push: 130 commits sin publicar, `origin/main` en `0ebbd58`. Push no
autorizado.
