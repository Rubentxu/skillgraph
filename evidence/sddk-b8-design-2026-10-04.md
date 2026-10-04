# B8 — Diseño: dónde vive el contrato y por qué no es una tabla más

**Ciclo**: `p-b7740b96d79ec013/b8`
**Fase**: design

---

## 1. Un paquete nuevo, y no una tabla más

```
packaging/
  manifest.py     el contrato
  __init__.py     la superficie pública
```

La alternativa era ampliar `domain/pack_loader.py`, que es donde vive el
`Brick`. Se descartó: `pack_loader` carga **tipos** dentro de un proceso que
ya está corriendo, y un manifiesto se **lee antes** de que exista nada que
cargar. Son dos momentos distintos del ciclo de vida, y meterlos en el mismo
módulo hace que cada uno tenga la mitad de la historia del otro.

Además, `pack_loader` es código de B3/H5 con su propia cobertura y sus
propios tests. Un bloque que añade el contrato de paquete a un módulo que
ya funciona, lo mezcla con el de tipos y luego no sabe cuál de los dos
rompió, es un bloque que mide mal dos cosas a la vez.

## 2. Tres tipos y dos funciones, y no más

```
PackManifest        nombre, versión, kind, requires, isolation, metadata
Requires            skillgraph + capabilities
CapabilityRequirement  type_name + version
```

`CapabilityRequirement` **no** lleva la versión dentro del nombre, y esa es
la decisión que R8 fijó. `CapabilitySpec` —el puerto de B3— ya la tiene
separada, y un contrato de paquete que no lo estuviera no se podría
comparar con nada.

## 3. `es_compatible` devuelve motivos y no un `bool`

La razón es de uso, no de gusto. Un `bool` obliga a quien pregunta a volver
a mirar el manifiesto para saber **por qué**, y en un pack que se está
instalando el «por qué» es la mitad del trabajo: `no encaja` no le dice al
operador si le falta una capability o si su SkillGraph es viejo.

`exigir_compatible` **no** vuelve a calcular los motivos: llama a
`es_compatible` y usa su resultado. Dos funciones que dicen «no» y «por
qué», calculadas por separado, son dos medidas del mismo hecho, y dos
medidas pueden discrepar.

## 4. Los requisitos se acumulan con AND, y lo ilegible no se cumple

`>=0.30,<1` son dos cláusulas y **las dos** tienen que cumplirse. Con `or`,
2.0 cumple `>=0.30` y por tanto cumple el requisito entero: es el error
clásico de un parser de especificadores.

Y una cláusula que no se puede interpretar hace que el requisito **no** se
cumple. Aceptarla en silencio sería peor que rechazarla: el pack se
instalaría sobre una base que el autor del requisito no quiso.

Se soportan `>=`, `<=`, `>`, `<` y `==`, y **no** `!=` ni `~=`. Un requisito
que se evalúa con una semántica que su autor no conoce se cumple o se
incumple por accidente.

## 5. El aislamiento es una tupla ordenada, y el orden es el contenido

`ISOLATION_LEVELS` es una **tupla**, no un `frozenset`. La razón no es el
tipo: un conjunto no puede expresar «cada nivel es al menos tan aislado como
el anterior», y eso es precisamente lo que el roadmap llama «aislamiento
progresivo según riesgo».

`es_al_menos` compara **índices**, no cadenas. Y un nivel que no exista
devuelve `False` en vez de reventar con `KeyError`: quien pregunta puede
tener una versión de SkillGraph cuyo vocabulario es otro, y eso es una
situación de despliegue, no un error de programación — y sale como
`IncompatiblePackError`, no como traza (WI-109).

## 6. Lo que este diseño NO cruza

**El aislamiento ejecutable.** `declarative`, `subprocess` y `sandbox` son
campos **declarados**, no mecanismos. Este bloque declara el vocabulario y
lo hace comparable; **ejecutarlo** es otro bloque.

Se dice explícitamente porque declarar un nivel sin ejecutarlo es la forma
más fácil de mentir sobre seguridad: un manifiesto que dice `sandbox` no
está en un sandbox hasta que lo esté.

## 7. La lista de operadores es una decisión, no una comodidad

`!=` y `~=` se rechazan. Se podrían implementar en diez líneas. No se
implementan porque un requisito que significa algo distinto de lo que su
autor cree es peor que un requisito que se rechaza: el primero falla en
producción y en silencio, el segundo falla al instalar y dice por qué.
