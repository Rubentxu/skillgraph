# B7 — Diseño: dónde vive la superficie de render y por qué

**Ciclo**: `p-b7740b96d79ec013/b7`
**Fase**: design

---

## 1. La decisión de estructura

**Un paquete nuevo, `src/skillgraph/presentation/`, con dos módulos.**

La alternativa era colgar las vistas de `cli/`, que es donde nació la
necesidad. Se descartó por una razón concreta: el gate pide widgets que
funcionen «sobre las mismas APIs», y una vista que vive **dentro** de la CLI
solo la puede usar la CLI. La TUI, que es el consumidor siguiente, tendría que
importar de `cli/`, y en ese momento la capa de presentación ya no es
compartida: es un detalle de la CLI que la TUI copia.

```
presentation/
  views.py     Column, TableView, DetailView   — la forma
  widgets.py   las diez proyecciones            — el contenido
  __init__.py  la superficie pública
```

`views.py` y `widgets.py` están separados porque son dos ejes distintos:
**la forma** (cómo se imprime) y **el contenido** (qué se imprime). Juntarlos
haría que cambiar un widget tocase la representación de los otros nueve.

## 2. Las dos formas y por qué no una

```python
TableView   filas, para lo que tiene Cardinalidad > 1
DetailView  campos + secciones, para lo que tiene Cardinalidad == 1
```

Una sola clase habría pedido el tipo (`isinstance` del contenido) y el
formateo por el valor, y una de las dos mitad de la clase habría sido código
muerto. Con dos, `to_text` de cada una significa lo mismo, y `to_json` de cada
una tiene la misma forma —que es lo que permite que un consumidor machine
trate las dos igual.

`DetailView` tiene `sections`: un panel con una tabla dentro. Es lo que hace
que `runs show` pueda llevar el timeline **dentro** del mismo objeto en vez de
imprimir dos cosas.

## 3. `_emit`: por qué recibe el texto como callable

```python
def _emit(vista, formato, texto: Callable[[], str]) -> str
```

Dos razones, y la segunda es la que manda.

**La primera** es la construcción: si `texto` fuera un `str` ya evaluado, el
punto de llamada tendría que construir la vista dos veces —una para el JSON y
otra para el texto—. Con un callable perezoso se construye una.

**La segunda** es que **qué es «el texto» lo sabe el comando, no la vista**:
`runs list` imprime una tabla y `runs show` imprime `clave=valor`, y son
contratos externos distintos. Un `_emit` que impusiera una única forma de
texto habría tenido que romper uno de los dos.

La alternativa descartada era un `isinstance` dentro de `_emit`. Se descartó
porque esconde la decisión en el helper: el comando deja de decir qué imprime,
y un `if` repartido por los comandos es exactamente el defecto que el gate
quiere cerrar.

## 4. Por qué `--format` solo en comandos de solo lectura

`--format` se declara en `runs list` y `runs show`, y en ninguno más.

En un comando que **muta**, el JSON no es una representación: es otro modo de
hacer la operación. Un `sg run start --format json` que devuelve un objeto no
está Mozilla dos veces el run —está cambiando qué se ejecuta según cómo se
pida el resultado—, y eso es una superficie nueva, no una presentación.

## 5. Inmutabilidad

`TableView` y `DetailView` son `frozen=True, slots=True` con tuplas, según
§1.1 de `AGENTS.md`. `find()` devuelve una vista **nueva**; no muta la
recibida. Una vista que se reescribiera a sí misma al filtrar haría imposible
que dos consumidores compartieran la misma construcción —que es la propiedad
que el gate pide.

## 6. El límite que este diseño no cruza

Las proyecciones son **puras**: reciben lo que el dominio ya devolvió y no
consultan nada. Se comprueba por AST, y no es una preferencia de estilo.

Una vista que abriera la base sería una segunda vía de consulta, y entonces
`runs show` y la TUI podrían **no** estar leyendo lo mismo aunque compartieran
el fichero: uno leería de la vista y el otro de la base, y divergirían sin
que nada lo notara. La alternativa —una vista que consulta— es la que hace el
gate imposible de satisfacer.

## 7. Qué queda fuera por diseño

**La TUI.** Este bloque entrega la pieza de la que la TUI depende. La TUI en
sí necesita un terminal y un humano, y el CI no tiene ninguno de los dos.
Medirla aquí daría un verde que no significaría nada.
