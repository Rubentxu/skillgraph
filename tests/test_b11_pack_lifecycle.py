"""B11 — el ciclo de vida de los packs, y la pregunta de si se puede mentir.

QUE MIDE ESTE FICHERO
---------------------
El gate de 1.0 mide `pack/controller lifecycle` con un predicado que mira
los subcomandos de `sg pack`. Eso, solo, se cerraba escribiendo tres lineas
de parser: el mismo atajo que B10 cerro para las superficies, y por eso
aqui no se repite.

Estos tests fijan seis cosas, y las seis se ejecutan de verdad:

1. **El ciclo de vida EXISTE y hace lo que dice.** Se corre `install`,
   `update`, `remove` y `list` por la CLI de verdad, en un proyecto de
   verdad, y se mira lo que sale. Un test que mira el parser no ve que
   `update` este imposible por el storage, que es exactamente lo que
   pasaba antes de este bloque.

2. **La compatibilidad se comprueba y el motivo SUBE.** `es_compatible` de
   B8 devuelve motivos; aqui se comprueba que llegan hasta el operador, con
   la clausula nombrada. «No encaja» sin mas no le dice al usuario si le
   falta una capability o si su SkillGraph es viejo.

3. **`update` exige que la version SUBE, y por numero.** `0.10.0` > `0.9.0`
   como numero y `<` como texto. Un update que comparase por cadena
   rechazaria una actualizacion legitima; uno que no comparase nada
   degradaria el entorno sin avisar.

4. **`remove` marca, no borra.** Un `DELETE` perderia la unica respuesta que
   existe a «¿este proyecto ha tenido alguna vez este pack?».

5. **El registro esta AISLADO por tenant y proyecto.** Un `list` que
   enseñara packs de otro proyecto no es un `list`: es una fuga.

6. **La migracion funciona contra una base VIEJA.** B6 demostro que
   `CREATE TABLE IF NOT EXISTS` no anade columnas y que un test que
   construye la base desde cero cada vez no lo ve nunca. Aqui hay una tabla
   NUEVA, luego no hay columnas que anadir —pero eso se comprueba, no se
   supone—.

POR QUE LOS CONTRA-SALTOS SON DISJUNTOS
--------------------------------------
Cada guarda mira algo distinto y ninguno comparte la asercion con otro. Un
guard con seis comprobaciones iguales mide una sola cosa seis veces, y si
`instalar()` devolviera siempre un registro vacio pasaria cinco de seis.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from skillgraph.core.errors import NotFoundError, ValidationError
from skillgraph.packaging import (
    ESTADO_INSTALADO,
    ESTADO_RETIRADO,
    PackManifest,
    RegistroDePacks,
    Requires,
    actualizar,
    instalar,
    retirar,
)
from skillgraph.packaging.registry import FilaDePack
from skillgraph.platform.storage import Storage

RAIZ = Path(__file__).resolve().parent.parent
VERSION_AQUI = "0.29.0"


def manifiesto(
    version: str = "0.1.0", *, requiere: str = ">=0.1.0", nombre: str = "acme"
) -> PackManifest:
    return PackManifest(
        name=nombre, version=version, kind="DomainPack", requires=Requires(skillgraph=requiere)
    )


# =====================================================================
# 1. El ciclo de vida, ejecutado
# =====================================================================


class TestElCicloSeEjecuta:
    """Conjunto A. Corre la CLI de verdad; mira la salida de verdad."""

    @staticmethod
    def _cli(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "skillgraph", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
            env={"PYTHONPATH": str(RAIZ / "src"), "PATH": "/usr/bin:/bin", "HOME": str(cwd)},
        )

    @staticmethod
    def _pack(directorio: Path, nombre: str, version: str, requiere: str = ">=0.1.0") -> Path:
        directorio.mkdir(parents=True, exist_ok=True)
        ruta = directorio / f"{nombre}.md"
        ruta.write_text(
            f"---\napiVersion: skillgraph.dev/v1alpha1\nkind: DomainPack\n"
            f"metadata:\n  namespace: packs\n  name: {nombre}\n"
            f"spec:\n  version: {version}\n  manifest:\n    name: {nombre}\n"
            f"    version: {version}\n    kind: DomainPack\n    isolation: declarative\n"
            f'    requires:\n      skillgraph: "{requiere}"\n---\n# {nombre}\n',
            encoding="utf-8",
        )
        return ruta

    def test_el_ciclo_completo_corre_de_punta_a_punta(self, tmp_path: Path) -> None:
        """install -> list -> update -> remove -> list, sobre un proyecto real.

        Es el test que mira el DEFECTO que el bloque vino a cerrar: antes,
        `update` era estructuralmente imposible porque `upsert_resource`
        rechaza cambiar el `spec` bajo la misma identidad. Un test que
        comprobase el parser no lo habria visto nunca.
        """
        cli = self._cli
        assert cli(["project", "create", "p"], tmp_path).returncode == 0
        v1 = self._pack(tmp_path / "packs", "acme", "0.1.0")
        v2 = self._pack(tmp_path / "packs2", "acme", "0.2.0")

        r = cli(["pack", "install", "p", str(v1)], tmp_path)
        assert r.returncode == 0, r.stdout + r.stderr
        assert "0.1.0" in r.stdout

        r = cli(["pack", "list", "p"], tmp_path)
        assert r.returncode == 0
        assert "acme@0.1.0" in r.stdout and "declarative" in r.stdout

        r = cli(["pack", "update", "p", str(v2)], tmp_path)
        assert r.returncode == 0, f"update fallo: {r.stdout}{r.stderr}"
        assert "0.1.0 -> 0.2.0" in r.stdout, f"no dice el delta: {r.stdout}"

        r = cli(["pack", "remove", "p", "acme"], tmp_path)
        assert r.returncode == 0, r.stdout + r.stderr

        r = cli(["pack", "list", "p"], tmp_path)
        assert r.returncode == 0
        assert "acme" not in r.stdout, "tras retirar, list no deberia enseñarlo"

    def test_el_guard_de_la_superficie_se_pone_rojo_si_falta_un_comando(
        self, tmp_path: Path
    ) -> None:
        """Contra-salto: quitar `update` del parser tiene que notarse.

        No se comprueba en el arbol de verdad —eso seria romper el repo—
        sino sobre un informe FABRICADO, que es lo que permite preguntarle
        al evaluador «que haces cuando falta un comando?» sin tocar nada.
        """
        import importlib.util

        espec = importlib.util.spec_from_file_location(
            "_b11_medidor", RAIZ / "scripts" / "measure_b11_pack_lifecycle.py"
        )
        assert espec is not None and espec.loader is not None
        mod = importlib.util.module_from_spec(espec)
        sys.modules[espec.name] = mod
        espec.loader.exec_module(mod)

        informe = mod.Informe(
            subcomandos=("import", "install", "list", "load", "remove"),
            install_incompatible=mod.Respuesta(12, "", "no encaja: skillgraph"),
            update_menor=mod.Respuesta(12, "", "no sube"),
            update_mayor=mod.Respuesta(0, "0.1.0 -> 0.2.0", ""),
            remove_inexistente=mod.Respuesta(12, "", "no esta instalado"),
            list_con_un_pack=mod.Respuesta(0, "acme@0.2.0 [declarative] installed", ""),
            list_vacio=mod.Respuesta(0, "(nada)", ""),
            install_valido=mod.Respuesta(0, "instalado 0.1.0", ""),
            version_esperada_en_list="0.2.0",
        )
        veredictos = {p: v for p, v, _ in mod.evaluar(informe)}
        assert veredictos["el ciclo de vida existe como comandos de sg pack"] == "OPEN", (
            "un `sg pack` sin `update` paso por completo: el gate volveria a cerrarse "
            "escribiendo los nombres en el parser"
        )

    def test_el_evaluador_no_devuelve_verde_ante_un_informe_que_no_mide(
        self, tmp_path: Path
    ) -> None:
        """Contra-salto del evaluador: un informe Vacio no es «todo bien».

        Es el M2 de la sonda de mutacion con otro disfraz: una medicion que
        devolviera una respuesta vacia pasaria los cinco predicados, y
        diria que el ciclo existe sin haber mirado nada.
        """
        import importlib.util

        espec = importlib.util.spec_from_file_location(
            "_b11_medidor_vacio", RAIZ / "scripts" / "measure_b11_pack_lifecycle.py"
        )
        mod = importlib.util.module_from_spec(espec)
        sys.modules[espec.name] = mod
        espec.loader.exec_module(mod)

        vacio = mod.Respuesta(0, "", "")
        informe = mod.Informe(
            subcomandos=(),
            install_incompatible=vacio,
            update_menor=vacio,
            update_mayor=vacio,
            remove_inexistente=vacio,
            list_con_un_pack=vacio,
            list_vacio=vacio,
            install_valido=vacio,
            version_esperada_en_list="",
        )
        veredictos = {p: v for p, v, _ in mod.evaluar(informe)}
        assert set(veredictos.values()) != {"PASS"}, (
            f"un informe sin datos dio todo PASS: {veredictos}"
        )


# =====================================================================
# 2. El nucleo, en memoria
# =====================================================================


class TestElNucleoDelCiclo:
    """Conjunto B. Funciones puras sobre el registro; sin disco."""

    def test_instalar_rechaza_incompatible_con_el_motivo(self) -> None:
        with pytest.raises(ValidationError) as exc:
            instalar(
                RegistroDePacks(),
                manifiesto(requiere=">=99.0.0"),
                version_skillgraph=VERSION_AQUI,
            )
        mensaje = str(exc.value)
        assert ">=99.0.0" in mensaje, f"el motivo no nombra la clausula: {mensaje}"
        assert VERSION_AQUI in mensaje, f"el motivo no dice que hay instalada: {mensaje}"

    def test_update_exige_que_la_version_suba(self) -> None:
        r, _ = instalar(RegistroDePacks(), manifiesto("0.1.0"), version_skillgraph=VERSION_AQUI)
        with pytest.raises(ValidationError, match="no sube"):
            actualizar(r, manifiesto("0.1.0"), version_skillgraph=VERSION_AQUI)

    def test_update_compara_por_numero_y_no_por_texto(self) -> None:
        """`0.10.0` es mayor que `0.9.0` como numero y MENOR como cadena.

        Una comparacion lexicografica rechazaria esta actualizacion, que es
        legitima; una que no comparase nada aceptaria una version anterior.
        El numero es el que decide, y esta es la prueba de que decide el.
        """
        r, _ = instalar(RegistroDePacks(), manifiesto("0.9.0"), version_skillgraph=VERSION_AQUI)
        assert "0.10.0" < "0.9.0", "el supuesto de este test es que el orden textual es al reves"
        nuevo, delta = actualizar(r, manifiesto("0.10.0"), version_skillgraph=VERSION_AQUI)
        assert delta == "0.9.0 -> 0.10.0"
        assert nuevo.buscar("acme").manifiesto.version == "0.10.0"

    def test_update_sobre_lo_que_no_esta_dice_que_hay(self) -> None:
        with pytest.raises(NotFoundError) as exc:
            actualizar(RegistroDePacks(), manifiesto(), version_skillgraph=VERSION_AQUI)
        assert "no esta instalado" in str(exc.value)

    def test_remove_de_lo_que_no_esta_lista_lo_que_si(self) -> None:
        """El motivo de un `remove` fallido incluye lo que SI hay.

        «No esta instalado» sin la lista deja al operador adivinando si se
        equivoco de nombre, y ese es justo el caso en el que mas le
        conviene saberlo.
        """
        r, _ = instalar(RegistroDePacks(), manifiesto(), version_skillgraph=VERSION_AQUI)
        with pytest.raises(NotFoundError) as exc:
            retirar(r, "otro")
        assert "acme" in str(exc.value)

    def test_una_version_ilegible_no_llega_ni_a_compararse(self) -> None:
        """La garantia real es de `PackManifest`, y es mas fuerte.

        `_sube` tiene una rama para versiones que no se pueden leer, pero
        esa rama es INALCANZABLE por la API publica: `PackManifest.__post_init__`
        exige `MAJOR.MINOR.PATCH` y una version como `alfa` revienta al
        construirse, antes de que exista un registro que comparar.

        Por eso lo que se comprueba aqui es la garantia de verdad —que una
        version ilegible no llega a existir— y no la rama muerta. Vigilar una
        verdad que ya no puede violarse es la peor version de un guard: da
        cobertura aparente y no mide nada.
        """
        with pytest.raises(ValidationError, match=r"PackManifest\.version invalido"):
            manifiesto("alfa")


# =====================================================================
# 3. `remove` marca, no borra
# =====================================================================


class TestRetirarMarcaNoBorra:
    """Conjunto C. Solo mira la historia del registro."""

    def test_la_fila_sigue_ahi_despues_de_retirar(self) -> None:
        r, _ = instalar(RegistroDePacks(), manifiesto("0.2.0"), version_skillgraph=VERSION_AQUI)
        retirado, _ = retirar(r, "acme")

        assert retirado.nombres_instalados() == (), "retirado no puede seguir instalado"
        assert len(retirado) == 1, "retirar BORRO la fila: y la fila era la unica historia"
        assert retirado.filas[0].estado == ESTADO_RETIRADO
        assert retirado.filas[0].manifiesto.version == "0.2.0", (
            "la fila retirada debe conservar la version que habia: sin ella, «que habia "
            "antes» no tiene respuesta"
        )

    def test_reinstalar_despues_de_retirar_es_un_install(self) -> None:
        r, _ = instalar(RegistroDePacks(), manifiesto("0.2.0"), version_skillgraph=VERSION_AQUI)
        retirado, _ = retirar(r, "acme")
        de_nuevo, delta = instalar(retirado, manifiesto("0.3.0"), version_skillgraph=VERSION_AQUI)
        assert de_nuevo.nombres_instalados() == ("acme",)
        assert delta == "instalado 0.3.0"

    def test_el_registro_es_inmutable(self) -> None:
        """Operar devuelve un registro NUEVO; el viejo no se toca.

        No es purismo: es lo que hace que un `install` que falla a mitad no
        deje el registro a medias. Con mutacion en sitio, el registro viejo
        que el llamante ya tiene seria el que se ha modificado por debajo.
        """
        r = RegistroDePacks()
        r2, _ = instalar(r, manifiesto(), version_skillgraph=VERSION_AQUI)
        assert r.nombres_instalados() == (), "instalar modifico el registro de origen"
        assert r2.nombres_instalados() == ("acme",)


# =====================================================================
# 4. Persistencia y aislamiento
# =====================================================================


class TestElRegistroPersisteYAisla:
    """Conjunto D. Contra una base de verdad, en `tmp_path`."""

    def test_el_registro_sobrevive_a_reabrir_la_base(self, tmp_path: Path) -> None:
        db = tmp_path / "p.db"
        st = Storage(db)
        st.installed_packs_repository().guardar(
            FilaDePack(pack="acme", estado=ESTADO_INSTALADO, manifiesto=manifiesto("0.2.0")),
            tenant_id="t1",
            project_id="p1",
        )
        st.close()

        st2 = Storage(db)
        registro = st2.installed_packs_repository().listar(tenant_id="t1", project_id="p1")
        st2.close()
        assert registro.nombres_instalados() == ("acme",)
        assert registro.buscar("acme").manifiesto.version == "0.2.0"

    def test_update_persiste_la_version_nueva(self, tmp_path: Path) -> None:
        """El defecto que el bloque vino a cerrar, medido sobre la base.

        Con el registro encima de `resources`, esto no tendria donde
        escribir: `upsert_resource` rechaza cambiar el `spec` bajo la misma
        identidad. Aqui la version nueva se guarda y se relee.
        """
        db = tmp_path / "p.db"
        st = Storage(db)
        repo = st.installed_packs_repository()
        repo.guardar(
            FilaDePack(pack="acme", estado=ESTADO_INSTALADO, manifiesto=manifiesto("0.1.0")),
            tenant_id="t1",
            project_id="p1",
        )
        repo.guardar(
            FilaDePack(pack="acme", estado=ESTADO_INSTALADO, manifiesto=manifiesto("0.2.0")),
            tenant_id="t1",
            project_id="p1",
        )
        registro = repo.listar(tenant_id="t1", project_id="p1")
        st.close()
        assert len(registro) == 1, "una fila por pack, no una fila por instalacion"
        assert registro.buscar("acme").manifiesto.version == "0.2.0"

    def test_el_registro_no_enseña_packs_de_otro_proyecto(self, tmp_path: Path) -> None:
        """Aislamiento. Un `list` que cruza proyectos es una fuga."""
        st = Storage(tmp_path / "p.db")
        repo = st.installed_packs_repository()
        for proyecto in ("p1", "p2"):
            repo.guardar(
                FilaDePack(
                    pack=f"de-{proyecto}",
                    estado=ESTADO_INSTALADO,
                    manifiesto=manifiesto(nombre=f"de-{proyecto}"),
                ),
                tenant_id="t1",
                project_id=proyecto,
            )
        p1 = repo.listar(tenant_id="t1", project_id="p1")
        st.close()
        assert p1.nombres_instalados() == ("de-p1",), p1.nombres_instalados()

    def test_el_registro_no_enseña_packs_de_otro_tenant(self, tmp_path: Path) -> None:
        st = Storage(tmp_path / "p.db")
        repo = st.installed_packs_repository()
        repo.guardar(
            FilaDePack(
                pack="t1pack", estado=ESTADO_INSTALADO, manifiesto=manifiesto(nombre="t1pack")
            ),
            tenant_id="t1",
            project_id="p1",
        )
        otro = repo.listar(tenant_id="t2", project_id="p1")
        st.close()
        assert otro.nombres_instalados() == (), "un pack cruzo de tenant"

    def test_retirar_no_borra_la_fila_en_disco(self, tmp_path: Path) -> None:
        """La marca sobrevive a reabrir: no es un estado en memoria."""
        db = tmp_path / "p.db"
        st = Storage(db)
        repo = st.installed_packs_repository()
        repo.guardar(
            FilaDePack(pack="acme", estado=ESTADO_INSTALADO, manifiesto=manifiesto()),
            tenant_id="t1",
            project_id="p1",
        )
        retirado, _ = retirar(
            repo.listar(tenant_id="t1", project_id="p1", solo_instalados=False), "acme"
        )
        repo.guardar(retirado.filas[0], tenant_id="t1", project_id="p1")
        st.close()

        st2 = Storage(db)
        vivos = st2.installed_packs_repository().listar(tenant_id="t1", project_id="p1")
        todos = st2.installed_packs_repository().listar(
            tenant_id="t1", project_id="p1", solo_instalados=False
        )
        st2.close()
        assert vivos.nombres_instalados() == ()
        assert len(todos) == 1, (
            "la fila retirada desaparecio de la base: no es una marca, es un borrado"
        )


# =====================================================================
# 5. La migracion contra una base VIEJA
# =====================================================================


class TestLaMigracionContraUnaBaseVieja:
    """Conjunto E. B6 demostro que esto NO lo ve un test que crea la base
    desde cero. Aqui hay una tabla NUEVA — luego no hay columnas que
    anadir — pero eso se comprueba contra una base creada con el esquema
    anterior, no se supone."""

    def test_la_tabla_nace_en_una_base_creada_por_el_esquema_anterior(self, tmp_path: Path) -> None:
        """Se crea la base con el esquema de ANTES de B11 y se abre con el de ahora.

        `CREATE TABLE IF NOT EXISTS` sobre una base vieja no anade nada, y
        por eso un test que construye la base desde cero cada vez no lo ve
        nunca. Aqui la base se crea con las tablas viejas y solo.
        """
        import sqlite3

        from skillgraph.platform.schema import SCHEMA_SQL

        db = tmp_path / "vieja.db"
        con = sqlite3.connect(db)
        # El esquema SIN la tabla de instalaciones: se quita la sentencia.
        sin_instalaciones = "\n\n".join(
            bloque for bloque in SCHEMA_SQL.split("\n\n") if "installed_packs" not in bloque
        )
        con.executescript(sin_instalaciones)
        con.commit()
        tablas_antes = {
            f[0] for f in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        con.close()
        assert "installed_packs" not in tablas_antes, "la base no se creo sin la tabla nueva"

        st = Storage(db)
        try:
            st.installed_packs_repository().guardar(
                FilaDePack(pack="acme", estado=ESTADO_INSTALADO, manifiesto=manifiesto()),
                tenant_id="t1",
                project_id="p1",
            )
            registro = st.installed_packs_repository().listar(tenant_id="t1", project_id="p1")
        finally:
            st.close()
        assert registro.nombres_instalados() == ("acme",), (
            "abrir una base vieja no creo la tabla de instalaciones: la migracion no migra"
        )
