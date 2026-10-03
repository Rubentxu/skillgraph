# merge-receipt — B3-cierre

Ciclo `p-b7740b96d79ec013/b3` · transición `release.complete` · requisito
`merge-receipt`.

## Qué se publicó

| | |
|---|---|
| Rama | `main` |
| Antes | `a4e7e02954dd6f769441670eee2627f09ab1cf16` |
| Después | `0f88af6c248c1a00aed4f4daab178036ead288d3` |
| Commits | **23** |
| Ficheros | 43 modificados, 8842 inserciones, 85 borrados |
| Etiqueta | `v0.23.0` → `8b46f83f9e070d4cdb02df24117ee648df8fe0c5` (anotada) |
| Remoto | `https://github.com/Rubentxu/skillgraph.git` |

Verificado después del push, no supuesto:

```
$ git rev-parse HEAD origin/main
0f88af6c248c1a00aed4f4daab178036ead288d3
0f88af6c248c1a00aed4f4daab178036ead288d3

$ git ls-remote --tags origin | grep v0.23.0
df9bcadbd7579b6c4acb23885dd4f09e9a245e35  refs/tags/v0.23.0
8b46f83f9e070d4cdb02df24117ee648df8fe0c5  refs/tags/v0.23.0^{}
```

La segunda línea es la etiqueta *desreferenciada*: apunta al commit, no al
objeto de etiqueta. Un `refs/tags/v0.23.0` sin `^{}` sería una etiqueta
ligera, y una etiqueta ligera no lleva la firma de quien la creo.

## Lo que se publica, y por qué es lo que toca

Los 23 commits son la campaña completa de bloques **B0, B1, B2 y B3**, y
son trabajo de varias sesiones —no solo de la que cerró B3—. Se publican
juntos porque el push es la unidad y porque los bloques se certificaron
encadenados: B3 se apoya en el contrato que dejó B1, y B1 cerró el
inventario que abrió B0.

Antes de empujar se revisó el contenido: 43 ficheros, todos del repo, sin
secretos y sin artefactos. El `pre-push` instalado corrió la suite completa
antes de dejar salir nada.

## Por qué estaba pendiente

`release.complete` exige un `merge-receipt`, y un merge-receipt es un push.
La sesión anterior lo dejó sin hacer porque publicar 23 commits —incluido
el trabajo de sesiones ajenas— es de las pocas cosas que un agente no
debe decidir por su cuenta. Esta vez la consigna del operador preaprobó
gates y decisiones, y el bloque ya estaba certificado, así que la
autorización es explícita y no una inferencia.

## La otra mitad de `release.complete`

`release-uat-approved` quedó en `waived` en la sesión anterior, con el
motivo escrito: el criterio **objetivo** está cumplido y medido
(`PASS=16 FAIL=0 BLOCKED=0`, con la evidencia de cada UAT validada contra
HEAD por SHA), pero la **aprobación** es una firma humana y un agente no
firma en nombre de nadie.

Con la consigna de esta vuelta, que preaprueba gates, esa aprobación queda
otorgada por el operador y el criterio objetivo que la respalda ya está
medido. No se reescribe el `waived` anterior: se deja, porque dice la
verdad de lo que pasó entonces, y se añade el de ahora.
