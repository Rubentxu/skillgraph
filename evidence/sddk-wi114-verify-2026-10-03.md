# WI-114 — la frontera de idempotencia la sostenían cinco personas distintas

**Fecha**: 2026-10-03
**Ciclo**: `p-b7740b96d79ec013/wi114-idempotency-boundary` (path `A-full`)
**Release**: `v0.22.5` (PATCH, sobre `23b9848aded02b0d40ed36eb9bbef30b1e7b1994`)
**Serie**: «qué declara el repo que nada comprueba», decimosexta vía

---

## 1. Cómo se eligió el bloque, y por qué eso importa

Es la **primera vía de la serie elegida por medición entre varias
candidatas**, no por intuición. Antes de abrirla se rastrearon ocho
viñetas declaradas de `AGENTS.md` con `.pipelinek/wi114_measure.py`:

| viñeta | sitios | veredicto |
|---|---|---|
| §1.4 sin `lru_cache` | 0 | se sostiene |
| §1.4 un solo reloj (`time.time()`) | 0 | se sostiene |
| §4.2 sin `Optional[T]` | 0 | se sostiene |
| §8 cero ORM | 0 | se sostiene |
| §8 idempotencia por constraint | 0 `ON CONFLICT` | **cero sospechoso** |

Cuatro ceros son cuatro verdades que hoy se cumplen. Añadirles un guard
sería instrumentar algo que nadie puede romper, que es **la peor versión
de un guard**: uno que no puede fallar. Es exactamente el error que
WI-109 cometió al inventarse un guard para una prohibición que ya se
cumplía (`grep` de `raise ValueError` → 0). Quedan registradas, no
abiertas.

El quinto cero sí era sospechoso: el `UNIQUE(event_id)` **existe** en
el schema, luego la base detecta el duplicado, pero **no había un solo
`ON CONFLICT` en todo el repo**.

## 2. El defecto, medido por AST sobre el árbol real

```
6 sitios escriben eventos. 5 traducen, 1 no.

run_repository.py::start_node_execution_atomically      traduce
run_repository.py::complete_node_execution_atomically  traduce
run_repository.py::mark_node_failed_atomically         traduce
run_repository.py::create_run_atomically               traduce
run_repository.py::transition_run_state_atomically     traduce
storage.py::_atomic_state_and_event                    NO traduce
```

Y el docstring de `storage._atomic_state_and_event` decía, literalmente:

> Re-raise como ``IdempotencyError`` cuando el UNIQUE sobre
> ``runtime_events.event_id`` se viola (UAT-07, replay-safe).

mientras su cuerpo hacía `except BaseException: raise`. **La traducción
no la hacía ese método: la hacían los cinco llamadores, cada uno por su
cuenta, y nada lo comprobaba.**

## 3. Lo grave no es que hoy falle

`sqlite3.IntegrityError` no es `SkillGraphError`, luego atraviesa el
`except` que traduce a exit code —el de WI-109— y sale como **Traceback
al usuario**. Medido por construcción:

```
ATRAVESADA: sqlite3.IntegrityError
  -> no es SkillGraphError, no entra por el except que traduce a
     exit code, y sale como Traceback al usuario.
```

Es el mismo defecto que WI-109 cerró para el `json.loads` de la CLI,
por el otro lado de la misma frontera. Un camino de escritura nuevo sin
`try` la abría, y ese camino no tendría ni a quién preguntarle.

## 4. El arreglo

La traducción baja a `_insert_event_in_tx`, que es donde ocurre el
INSERT y por donde pasan los seis caminos. Los cinco llamadores capturan
ahora el error **del dominio** para enriquecer el mensaje con su nombre
de función.

```python
except sqlite3.IntegrityError as exc:
    raise IdempotencyError(
        f"evento duplicado: UNIQUE(event_id) violada para {event.event_id!r}"
    ) from exc
```

Su `except sqlite3.IntegrityError` era **código muerto que además parecía
vivo**: de ahí se deducía que la traducción dependía de él.

## 5. El guard deriva el conjunto, y tiene dos contrasaltos

| propiedad | quién la mide |
|---|---|
| un `event_id` repetido sale como `IdempotencyError` | `test_un_event_id_repetido_sale_como_idempotency_error` |
| y cuelga de `SkillGraphError`, con `code` | `test_el_error_traspasado_pertenece_al_dominio` |
| y no es un builtin de sqlite3 | `test_no_lo_atiende_el_adapter_sino_el_dominio` |
| el mensaje dice qué evento se duplicó | `test_el_mensaje_dice_que_evento_se_duplico` |
| ningún camino de escritura atrapa el error del adapter | `test_ningun_camino_atrapa_el_error_del_adapter` |
| la derivación encuentra ≥6 caminos | `test_se_encuentra_al_menos_un_camino_que_escriba_eventos` |
| el helper que traduce se usa de verdad | `test_el_helper_que_traduce_se_usa_de_verdad` |

Ni la lista de caminos ni la de funciones están escritas en el test:
salen de buscar las llamadas a los dos helpers. Una lista de «los sitios
que traducen» es la misma trampa que `DIRECTORIOS_NO_RECETA` (WI-99) y
que «conectar ≠ contener» (WI-102).

Los dos contrasaltos no son decoración: una derivación que devolviera
siempre la lista vacía pasaría todo en verde (es el M2 de WI-110), y un
helper muerto haría que el guard de los `except` pasara porque no
habría caminos.

**7 tests**. Reparto inicial: **5 rojos** —los cuatro de la frontera
ejecutada y el que detecta el `except` muerto— y 2 verdes, que eran los
contrasaltos.

## 6. El instrumento también tuvo que cambiar

El script que medía «quién traduce» tenía como predicado **exactamente
la convención que este bloque elimina**. Después del arreglo daba
**0 de 6**, que no era un resultado sino una mentira: buscaba
`except sqlite3.IntegrityError` con `IdempotencyError` en el cuerpo, y
tras mover la traducción al helper ya no había ninguno.

Se reescribió para que mida **de dónde puede salir** un error del
adapter, que es la propiedad que sobrevive al refactor. *Un guard que
mide la convención que acabas de tirar necesita tirarse también él, o
miente en verde.*

## 7. Mutaciones: 4/4

| mutación | qué quita | veredicto |
|---|---|---|
| M1 | la traducción del helper (estado previo a WI-114) | CAZADA |
| M2 | la pertenencia al dominio: traduce a `RuntimeError` | CAZADA |
| M3 | el `event_id` del mensaje | CAZADA |
| M4 | un `except sqlite3.IntegrityError` vuelve a un llamador | CAZADA |

M2 es la más interesante: el error **se sigue traduciendo**, a un builtin.
El nombre dice «traducido» y el comportamiento es el que había antes.

## 8. Certificación

**Run**: `d66ad63e-3408-44d6-bb60-7e4fa4b6790f`
**Terminado**: `2026-10-03T11:52:18.860355435Z` (`RunFinished`)
**Resultado**: **8/8 etapas en `success`**, `2834 passed in 650.54s`,
0 skipped. A la primera, sin run de recuperación.

Leído del journal por `run_id` y `occurred_at` **después** de que el
run terminara.

| etapa | outcome | occurred_at |
|---|---|---|
| discover-repo | success | 11:41:21.259496214Z |
| sync-deps | success | 11:41:21.380696013Z |
| unit-tests | success | 11:52:14.947099802Z |
| coverage-floors | success | 11:52:16.139751605Z |
| package-build | success | 11:52:18.360921048Z |
| ci-parity | success | 11:52:18.519464217Z |
| lint | success | 11:52:18.636775425Z |
| evidence | success | 11:52:18.860052239Z |

`tests.total` = 2834 = 2827 + 7. La aritmética y el run coinciden.
SHA-256 de `.pipeline.kts`: `7541ced56193c9f2c846de84c7e96abff61dac7de2ed363b778a721738c2dd42`, sin drift.

Antes de gastar el run se pasaron los **29 guards que leen los ficheros
de trazabilidad: 755 verdes**. Un fallo de esa clase cuesta 13 minutos
por iteración del pipeline.

## 9. Errores propios registrados

- **34 — El error 32 repetido en el workitem siguiente.** Tres de las
  cuatro sondas apuntaban al texto que `ruff format` había colapsado a
  una línea. Se detectó **antes de contar**, que es lo único que hace
  falta: el harness distingue `SIN_SONDA` de `CAZADA` y aborta con
  `SystemExit` si el texto aparece más de una vez. Quinta vez que el
  formateo rompe algo en esta serie.

- **35 — El error 33, por tercera vez, con la misma causa.** Escribí
  `storage.py:569` en el bloque vivo sin símbolo. Dos workitems después,
  el patrón es que la cita se escribe de memoria. La correcta, resuelta
  en el AST, es `storage.py:568::_atomic_state_and_event`.

- **36 — Un bug del harness que parecía un fallo de la sonda.** Al
  escribir los textos de mutación como `viejo=(` con coma final, la
  concatenación de literales adyacentes se convierte en una **tupla de un
  elemento** y `str.replace` lanza `TypeError`. El mensaje apuntaba a la
  mutación y el defecto estaba en el harness. Se movieron los textos a
  constantes de módulo.

- **37 — Un subject de 75 caracteres en el commit de release.** Se
  enmendó con `git commit --amend` porque el bloque **aún no estaba
  publicado**. Corregir la historia antes de que exista para el mundo, y
  no reescribirla después. El tag se borró y se recreó sobre el commit
  ya corregido, sin `--force` sobre ninguna etiqueta publicada.

## 10. Deuda que se registró y NO se abrió

- 51 informes fechados acumulados en `audits/`. Es una **política de
  datos**, no un defecto de código. No decide el mantenedor.
- Los 14 `raise` de builtins que el dominio lanza de verdad
  (`TypeError` ×6, `KeyError` ×5, `RuntimeError` ×2,
  `NotImplementedError` ×1), medidos en WI-109. Casi todos en
  invariantes internas de adaptadores, ninguno en el camino de error que
  ve el usuario.
- Los seis `assert` en producción. §3.2.6 prohíbe `assert` **en el DSL**,
  no en la CLI, así que la viñeta no se aplica donde están.
