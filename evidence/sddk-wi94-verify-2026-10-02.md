# WI-94 — El contrato de cobertura que escribí en WI-93 sólo se cumplía donde yo miré

- **Ciclo**: `p-b7740b96d79ec013/wi-94-coverage-contract-symmetry`
- **Fecha**: 2026-10-02
- **Suite**: 2552 passed (2529 antes; +23)
- **Commits**: `11294ec` (test, rojo primero), `569f318` (refactor del checker)

## El bloque anterior, releido

WI-93 hizo exigible el contrato de AGENTS §6.3 y lo implemento con
`scripts/check_coverage_floors.py`. La medición que acompaña a este bloque
empezó por una pregunta que WI-93 no se hizo: **¿el contrato que escribí
cubre lo que §6.3 declara?**

Medido sobre el informe de cobertura real, no estimado:

| | WI-93 lo implemento como | Lo que §6.3 declara |
|---|---|---|
| `runtime/` | regla de «todo módulo tiene suelo» + lista de 11 | ≥ 90 % |
| `core/`, `resources/`, `platform/` | lista de 4 módulos | ≥ 90 % |
| `knowledge/`, `governance/`, `domain/` | **nada** | — (§6.3 no los nombra) |
| `cli/` | **sólo agregado** (70 % sobre el paquete) | ≥ 70 % |

Dos huecos, ambos reales:

1. **Siete de los ocho paquetes no tenían ninguna regla.** La regla de «todo
   módulo tiene suelo» —que WI-93 construyó precisamente para que un módulo
   nuevo no pasara inadvertido — se aplicaba **sólo a `runtime/`**. Un módulo
   nuevo al 40 % en `governance/` no lo vería nadie. Es el mismo fallo que
   WI-93 cerraba, sin cerrar en el resto.
2. **`cli/` se medía en agregado, con 16,91 puntos de holgura.** El paquete
   mide 86,91 % contra un suelo del 70 %. Un módulo de `cli/` podría caer al
   0 % y el contrato seguiría verde.

El segundo hueco es más grave de lo que parece, porque **la propia evidencia
de WI-93 lo advertía**:

> *La cobertura agregada puede tapar un módulo débil. `runtime/` estaba al
> 95,11 % — muy por encima de 90 — y contenía un módulo al 88 %.*

Ese texto se aplicó a `runtime/` y se pasó por alto en `cli/`. El principio
se aplicó a media mitad de su propio contrato.

## Que no es el problema

Ninguno de los ocho paquetes tiene hoy un módulo por debajo de su suelo. Los
mínimos medidos:

| Paquete | Módulos | min | suelo |
|---|---|---|---|
| `runtime/` | 11 | 90,62 % (`locks.py`) | 90 |
| `knowledge/` | 8 | 92,40 % (`context_controller.py`) | 90 |
| `platform/` | 21 | 80,85 % (`paths.py`) | **60** (excepción de §6.3) |
| `governance/` | 6 | 94,72 % (`backups.py`) | 90 |
| `core/` · `resources/` · `domain/` | 12 | 96,15 % | 90 |
| `cli/` | 11 | 78,16 % (`commands/pack.py`) | 70 |

O sea: **no había ningún incumplimiento real**. El defecto era del guard, no
del código. Y eso cambia el tipo de release: este bloque no arregla un
comportamiento roto, refuerza una red que estaba mal tejida.

## La decision de diseño: heredar, no listar

El contrato pasa de 21 entradas escritas a mano a 8 prefijos:

```python
SUELOS_POR_PAQUETE = {
    "src/skillgraph/core/": 90.0,       ...   # 8 prefijos
}
EXCEPCIONES = {"src/skillgraph/platform/paths.py": 60.0}
```

No es «menos mantenimiento». Es **un contrato más fuerte**: un módulo nuevo
en cualquier paquete cubierto queda vigilado en el momento de aparecer, y eso
ya no depende de que alguien recuerde añadirlo a una lista. La lista de
WI-93 era exactamente la clase de fuente que se desincroniza del código.

**`paths.py` es una excepción declarada, no una atribución.** §6.3 le da suelo
propio (`>= 60 %`); aplicarle el 90 % de `platform/` haría fallar al único
módulo que el propio contrato exonera. Sin la excepción, el contrato estaría
mintiendo sobre sí mismo — y la mutación **M2** lo comprueba.

**Los agregados se conservan, pero como comprobación adicional.** Nunca en
lugar de la por módulo.

### Lo que se pierde y lo que lo sustituye

Con la lista fuera, la detección de «módulo fantasma» que hacía WI-93
—la lista nombraba el módulo, así que si desaparecía del informe era un
fallo— desaparece. La sustituye una aserción mejor: **un paquete declarado que
no aporta ningún módulo es un fallo**, porque o se borró o se renombró, y en
los dos casos el contrato estaría midiendo sobre la nada.

### `evaluar()` pasa a ser pura

`evaluar(informe) -> (líneas, fallos)`, separada de `main()`. Sin esto, probar
el contrato exigiría disco y subprocess, y los tests sólo podrían leerse el
informe real — que no distingue «el contrato se cumple» de «el contrato no
mira aquí».

## Mutaciones: 4/4, y el reparto es el resultado

Dos gates: el **script** que corre en la CI, y el **test** que fija la
propiedad del script. Una mutación está cazada si alguno la rechaza.

| # | Mutación | Gate | Resultado |
|---|---|---|---|
| M1 | Suelo de `runtime/` 90 → 99,9 | checker | **cazada** |
| M2 | Borrar la excepción de `paths.py` | checker | **cazada** |
| M3 | `suelo_de` sólo reconoce `runtime/` (el bug de WI-93) | **test** | **cazada** |
| M4 | `suelo_de` nunca devuelve `None` | **test** | **cazada** |
| M5 | Control final: byte-idéntico | — | **OK** |

`cazadas=4  no-cazadas=0  no-aplicadas=0`

**M3 es la que importa, y por lo que está cazada por el test y no por el
script.** Reintroducir la asimetría exacta de WI-93 no produce ningún fallo
en el script sobre este árbol: el código cumple, luego todo verde. El
defecto era invisible para el propio guard que lo dejaba pasar. Sólo un test
con informes **sintéticos** —donde se puede construir el módulo flojo que el
árbol real no tiene— lo detecta.

> **Un guard que vigila el árbol real sólo detecta lo que ya está roto.**
> Por property propia hay que construir el contraejemplo a mano.

## El fallo que la CI encontró y el `pytest` a pelo no

La primera run de la CI con este trabajo dio **FAILURE con 9 rojos**, y los 9
eran tests de este bloque. La causa es una dependencia circular que
introduje al escribirlos:

`scripts/coverage.sh` corre pytest y **después** hace `coverage combine`.
Durante la ejecución de pytest los datos siguen en `.coverage.parallel.*` sin
combinar, y `coverage json` responde `No data to report` con rc=1. Los tests
leían ese informe para afirmar sobre él: **necesitaban un artefacto que el
pytest que los contiene todavía no había producido.**

Lo grave no es que fallaran en la CI. Es que **`pytest -q` a pelo daba
2552 passed**. Pasaban porque en local ya había un `scripts/coverage.sh`
anterior que había combinado los datos, de modo que el informe estaba
completo cuando los leían.

> El «2552 passed» era cierto, y las condiciones en las que era cierto **no
> eran las de la CI**. Es la misma familia de error que medir `/usr/bin/sg`
> (WI-88), que `wc -c` sobre una línea con `—` (WI-91), o que leer el `rc` de
> un `| tail` (WI-93): un número que parece confirmar cualquier premisa
> porque se midio en unas condiciones y se administro como si fueran otras.

La corrección tiene dos partes, y la segunda es una decisión:

1. `test_cada_paquete_declarado_tiene_modulos_de_verdad` ahora lee el
   **sistema de ficheros**. Que un paquete tenga módulos es una propiedad del
   *código fuente*, no de la medición: se le estaba preguntando al informe
   algo que el árbol ya sabe.
2. `test_el_informe_real_no_tiene_infracciones` se **elimina**, y el borrado
   es la decisión. Es circular por lo anterior, y además **redundante**: la
   garantía «el árbol real cumple el contrato» ya la da el stage
   `coverage-floors`, que corre en su propia pasada y con el informe ya
   combinado. *El sitio correcto para comprobar una propiedad de la medición
   es después de la medición.*

Resultado: 22 tests que corren en 0,09 s, sin disco ni subproceso, y en
cualquier orden respecto a la medición.

## Conocimiento negativo

- **Aplicar un principio a media mitad de su propio contrato es la forma más
  difícil de detectar el defecto**, porque la mitad donde sí se aplica
  funciona y da credibility al conjunto. La evidencia de WI-93 decía la
  verdad sobre `cli/` y nadie la conectó con el código de WI-93.
- **Una lista de módulos escrita a mano es una promesa de sincronía.** En el
  momento en que se escribe, es correcta; en el momento en que alguien añade
  un módulo, deja de serlo sin avisar. Los prefijos no tienen esa clase de
  deuda porque no hay nada que sincronizar.
- **Un fixture de test que dispara ruido propio esconde el fallo que
  apunta.** Los primeros `_informe()` sintéticos de este bloque tenían un
  solo módulo, así que los otros siete paquetes declarados aparecían como
  «sin ningún módulo» y tres tests fallaban por el motivo equivocado. La
  corrección fue `_base()`: un módulo sano por paquete declarado, para que el
  único fallo sea el que el test quiere observar.
- **`assert fallos` a secas es un test que puede pasar por un ruido ajeno.**
  `_fallos_de(informe, ruta)` exige que el fallo **nombre** al módulo bajo
  prueba. Sin eso, «el contrato se queja de algo» basta para dar verde.
- **Un comentario que dice dos cosas a la vez no informa de ninguna.** En el
  `__init__.py` de la release anterior quedaron concatenados el de v0.16.17 y
  el de v0.16.18 en la misma línea.

## Lo que sigue sin probarse

Igual que en WI-93: este bloque **no** prueba que Anthropic ni OpenAI
respondan. Requiere credenciales que este entorno no tiene, y el registro de
conformidad de H9 lo declara como hueco abierto. Lo que sí queda es local: el
contrato de cobertura ahora se cumple en todas partes donde dice cumplirse.
