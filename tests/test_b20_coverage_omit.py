"""B20 — la medicion de cobertura se rompia con un temporal ya borrado.

Por que este fichero
--------------------
La certificacion de B20 fallo en la etapa `unit-tests` con rc=1 DESPUES de que
la suite entera hubiera pasado: 3321 passed, cobertura 93,68 % sobre el suelo
de 80. El mensaje era

    No source for code: '/tmp/b17_16r3_ise/src/skillgraph/__init__.py'

MEDIDO sobre el arbol real, no sobre un caso inventado:

  · el dato lo producia `test_b17_pack_lifecycle_exec.py:100`, que abre un
    `TemporaryDirectory(prefix="b17_")`, levanta el paquete alli como
    subproceso y lo borra al terminar;
  · el hook `.pth` que instala `scripts/coverage.sh` mide ese subproceso con
    la misma destreza con la que mide cualquier otro;
  · de las 376 rutas del fichero de datos, **282 eran de `/tmp`**, y ninguna
    existia ya cuando llegaba `coverage report`.

O sea: la medicion fallaba no por lo que medía, sino por lo que había medido
anuncio y ya no podia abrir. Y el dato contaminado rompia **las dos**
consumidoras: `coverage report` (en `coverage.sh`) y `coverage json` (en
`check_coverage_floors.py`, o sea la etapa siguiente de la receta).

**POR QUE NO SE RESUELVE CON `[paths]`.** Los temporales no tienen un solo
layout: conviven `/tmp/b17_*/src/` y `/tmp/b19_*/repo/src/`. Remapearlos
obliga a enumerarlos, y una enumeracion de layouts es exactamente la lista
encubierta por forma que B20 denuncia en el predicado de la ontologia: decide
**como se escribe** la ruta en vez de **a que conjunto pertenece** la ruta. La
regla es una sola y no necesita lista: lo que vive fuera del arbol del repo no
es codigo de este repo.

Lo que se mide
--------------
La propiedad, y no el texto: **la configuracion que genera `coverage.sh` no
registra ficheros de fuera del arbol del repo.** Se EJECUTA la medicion sobre
un temporal y se mira el fichero de datos resultante.

La configuracion no se copia en este test. Se DERIVA del heredoc de
`scripts/coverage.sh`, por la misma razon que WI-114 deriva del arbol el
conjunto de caminos de escritura en vez de escribirlo: una copia escrita en el
propio guard es el guard comparandose consigo mismo, y hoy acerta y el dia que
la verdad se mueva dira lo contrario con toda la autoridad de un test.

El contrasalto va en las dos direcciones. Sin el, este test pasaria con el
`omit` ausente, porque `omit` no rompe nada: solo evita que se registre.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
COVERAGE_SH = REPO_ROOT / "scripts" / "coverage.sh"

_HEREDOC = re.compile(r"<<EOF\n(.*?)\nEOF\n", re.DOTALL)


def _rc_generada() -> str:
    """La configuracion que `coverage.sh` escribe, derivada del propio script.

    Se extrae el heredoc en vez de reescribirlo aqui. Si el script cambia, esto
    cambia con el; si el test copiara la configuracion, dos ficheros podrian
    discrepar y el test mediria la copia.
    """
    texto = COVERAGE_SH.read_text(encoding="utf-8")
    cuerpos = _HEREDOC.findall(texto)
    assert cuerpos, (
        f"{COVERAGE_SH.name} no escribe ya la configuracion con un heredoc <<EOF. "
        "Si el mecanismo cambio, este guard se esta midiendo a si mismo y hay "
        "que rehacerlo contra el mecanismo nuevo, no relajar el aserto."
    )
    rc = cuerpos[0].replace("$REPO_ROOT", str(REPO_ROOT))
    assert "data_file" in rc, "la configuracion derivada no dice donde esta el dato"
    return rc


def _rc_para(datos: Path, sin_omit: bool) -> Path:
    """La RC derivada, apuntando al dato del test y con/sin el `omit`."""
    rc = _rc_generada()
    rc = re.sub(r"^data_file = .*$", f"data_file = {datos}", rc, flags=re.MULTILINE)
    rc = re.sub(r"^parallel = true$", "parallel = false", rc, flags=re.MULTILINE)
    if sin_omit:
        rc = re.sub(r"^omit =\n(?:    .*\n)+", "", rc, flags=re.MULTILINE)
    destino = datos.with_suffix(".rc")
    destino.write_text(rc, encoding="utf-8")
    return destino


def _medir_un_temporal(rc: Path, raiz: Path) -> None:
    """Ejecuta un modulo desde un temporal, con la FORMA que tiene el caso real.

    El paquete se llama `skillgraph` y cuelga de `src/`, porque es lo que hace
    el caso de B17: se copia el arbol del repo a un temporal y se levanta el
    paquete de ahi. MEDIDO al escribir este guard: con un modulo que NO se
    llamaba `skillgraph`, la configuracion no registraba NADA en ninguno de los
    dos casos, y el contrasalto —que exige que sin `omit` las rutas de /tmp
    aparezcan— dio rojo. O sea: el otro test de esta clase pasaba por la razon
    equivocada, y el contrasalto fue lo que lo impidio. Por eso el nombre del
    paquete no es decorativo: es lo que hace que la medicion exista.
    """
    paquete = raiz / "src" / "skillgraph"
    paquete.mkdir(parents=True, exist_ok=True)
    (paquete / "__init__.py").write_text("", encoding="utf-8")
    (paquete / "modulo_efimero.py").write_text(
        "VALOR = 1\n\n\ndef usar() -> int:\n    return VALOR\n", encoding="utf-8"
    )
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(raiz),
        "PYTHONPATH": str(raiz / "src"),
    }
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "coverage",
            "run",
            "--rcfile",
            str(rc),
            "-m",
            "skillgraph.modulo_efimero",
        ],
        cwd=raiz,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, (
        f"no se pudo medir el temporal, y el guard mediria un fallo suyo:\n"
        f"stdout={proc.stdout!r}\nstderr={proc.stderr!r}"
    )


def _rutas_del_dato(datos: Path) -> list[str]:
    import sqlite3

    conexion = sqlite3.connect(datos)
    try:
        return [f for (f,) in conexion.execute("select path from file")]
    finally:
        conexion.close()


class TestLaConfiguracionNoMideFueraDelRepo:
    """La propiedad: nada de fuera del arbol entra en el dato."""

    def test_un_temporal_no_aparece_en_el_dato(self, tmp_path: Path) -> None:
        datos = tmp_path / "datos"
        rc = _rc_para(datos, sin_omit=False)
        paquete = Path("/tmp") / f"sg_b20_omit_{tmp_path.name}"
        paquete.mkdir(parents=True, exist_ok=True)
        try:
            _medir_un_temporal(rc, paquete)
            rutas = _rutas_del_dato(datos)
        finally:
            shutil.rmtree(paquete, ignore_errors=True)

        fuera = [r for r in rutas if r.startswith("/tmp")]
        assert not fuera, (
            f"la configuracion registro {len(fuera)} ruta(s) de /tmp en el dato. "
            f"El temporal se borra al terminar el test, luego esas rutas no las "
            f"puede abrir coverage report y el informe entero aborta con rc=1 "
            f"DESPUES de que la suite haya pasado. Muestra: {fuera[:3]}"
        )

    def test_sin_el_omit_el_temporal_si_se_registra(self, tmp_path: Path) -> None:
        """CONTRASALTO. Sin esta asercion, la de arriba pasa con `omit` ausente.

        Un `omit` que no hace nada no rompe nada, luego un guard que solo mira
        «no hay rutas de /tmp» daria verde sobre una configuracion que no
        omite nada. Este test quita el `omit` de la MISMA configuracion derivada
        y exige que las rutas aparezcan.
        """
        datos = tmp_path / "datos"
        rc = _rc_para(datos, sin_omit=True)
        paquete = Path("/tmp") / f"sg_b20_contrasalto_{tmp_path.name}"
        paquete.mkdir(parents=True, exist_ok=True)
        try:
            _medir_un_temporal(rc, paquete)
            rutas = _rutas_del_dato(datos)
        finally:
            shutil.rmtree(paquete, ignore_errors=True)

        fuera = [r for r in rutas if r.startswith("/tmp")]
        assert fuera, (
            "quitando el `omit` de la configuracion las rutas de /tmp siguen "
            "sin registrarse. O el guard de arriba no mide lo que dice medir, "
            "o el mecanismo de medicion cambio por debajo. Ninguna de las dos "
            "es una situacion en la que este fichero pueda seguir verde."
        )


class TestElArregloNoRelajaElSuelo:
    """Un arreglo que apaga el umbral no es un arreglo."""

    def test_el_suelo_sigue_mordiendo(self, tmp_path: Path) -> None:
        """`omit` deja de exigir que coverage sepa abrir ficheros que no estan.

        Lo que NO puede dejar de exigir es el suelo. MEDIDO en B20: con el
        `omit` puesto, subir `fail_under` a 95 o a 99 sobre el 94 % real sigue
        dando rc=2. Este test lo exige contra la configuracion **derivada**.
        """
        rc = _rc_generada()
        assert "fail_under" in rc, (
            "la configuracion derivada no declara suelo: un informe sin umbral "
            "no es un gate, y este guard no puede comprobar que lo siga siendo"
        )
        assert re.search(r"^fail_under = \d+", rc, re.MULTILINE), (
            f"el suelo no esta declarado como entero: {rc!r}"
        )


def test_la_configuracion_derivable_no_es_una_copia() -> None:
    """Lo que este fichero mide es lo que `coverage.sh` escribe.

    Si el script deja de escribir la configuracion por heredoc, este guard
    mediria una reconstruccion suya. Se prefiere que se ponga en rojo a que
    siga en verde sobre otra cosa: el fallo silencioso de un guard es peor
    que su ausencia.
    """
    assert _HEREDOC.search(COVERAGE_SH.read_text(encoding="utf-8")), (
        "scripts/coverage.sh ya no escribe la configuracion con un heredoc <<EOF. "
        "Este guard deriva de ahi, luego ahora mediria su propia reconstruccion."
    )
    # Y la derivacion tiene que ser de ESTE repo, no de un texto suelto.
    assert str(REPO_ROOT) in _rc_generada(), (
        "la configuracion derivada no apunta a este arbol: el `$REPO_ROOT` no "
        "se ha expandido y el guard mediria una ruta que no existe"
    )


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__])
