import csv
import re
import tkinter as tk
import xml.etree.ElementTree as ET
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path
from tkinter import filedialog, messagebox, ttk


class GeneradorCSV(tk.Tk):
    ENCABEZADOS = [
        "Area (mm2)", "Combinacion", "Energia (J)",
        "Presion (b)", "Amplitud (mu)", "Ancho (mm)"
    ]

    def __init__(self):
        super().__init__()
        self.title("Generador de datos para carta de parametros de US")
        self.geometry("780x280")
        self.minsize(680, 280)

        self.ruta_nodos = tk.StringVar()
        self.ruta_parametros = tk.StringVar()
        self.estacion = tk.StringVar()
        self.estado = tk.StringVar(
            value="Seleccione las carpetas e ingrese la estacion."
        )

        self._crear_interfaz()
        for variable in (self.ruta_nodos, self.ruta_parametros, self.estacion):
            variable.trace_add("write", self._validar_formulario)

    def _crear_interfaz(self):
        marco = ttk.Frame(self, padding=18)
        marco.pack(fill="both", expand=True)
        marco.columnconfigure(1, weight=1)
        marco.rowconfigure(5, weight=1)

        ttk.Label(marco, text="Ruta para los nodos:").grid(
            row=0, column=0, sticky="w", pady=7
        )
        ttk.Entry(marco, textvariable=self.ruta_nodos).grid(
            row=0, column=1, sticky="ew", padx=10, pady=7
        )
        ttk.Button(
            marco, text="Browse",
            command=lambda: self._seleccionar_carpeta(self.ruta_nodos)
        ).grid(row=0, column=2, pady=7)

        ttk.Label(marco, text="Ruta para parametros:").grid(
            row=1, column=0, sticky="w", pady=7
        )
        ttk.Entry(marco, textvariable=self.ruta_parametros).grid(
            row=1, column=1, sticky="ew", padx=10, pady=7
        )
        ttk.Button(
            marco, text="Browse",
            command=lambda: self._seleccionar_carpeta(self.ruta_parametros)
        ).grid(row=1, column=2, pady=7)

        ttk.Label(marco, text="Estacion:").grid(
            row=2, column=0, sticky="w", pady=7
        )
        ttk.Entry(marco, textvariable=self.estacion).grid(
            row=2, column=1, sticky="ew", padx=10, pady=7
        )

        self.boton_generar = ttk.Button(
            marco, text="Generar", command=self._generar_csv, state="disabled"
        )
        self.boton_generar.grid(row=3, column=1, pady=(15, 7))

        ttk.Label(
            marco, textvariable=self.estado, foreground="#555555"
        ).grid(row=4, column=0, columnspan=3, sticky="w", pady=(8, 0))

        ttk.Label(
            marco,
            text=(
                "Dev: David Solis Hurtado • "
                "Concepto: Steve Irving Garner Macazani"
            ),
            foreground="#808080",
            font=("TkDefaultFont", 8),
            anchor="e"
        ).grid(
            row=5, column=0, columnspan=3, sticky="se", pady=(12, 0)
        )

    def _seleccionar_carpeta(self, variable):
        ruta = filedialog.askdirectory(title="Seleccione una carpeta")
        if ruta:
            variable.set(ruta)

    def _validar_formulario(self, *_):
        valido = (
            Path(self.ruta_nodos.get().strip()).is_dir()
            and Path(self.ruta_parametros.get().strip()).is_dir()
            and len(self.estacion.get().strip()) >= 3
        )
        self.boton_generar.configure(
            state="normal" if valido else "disabled"
        )

    @staticmethod
    def _clave_archivo(ruta):
        partes = ruta.name.split(".")
        return partes[1] if len(partes) > 2 and partes[1] else None

    @staticmethod
    def _indexar_xml(carpeta, prefijo):
        indice = {}
        duplicados = set()
        for ruta in carpeta.iterdir():
            if not ruta.is_file() or ruta.suffix.lower() != ".xml":
                continue
            if not ruta.name.upper().startswith(prefijo.upper()):
                continue
            clave = GeneradorCSV._clave_archivo(ruta)
            if not clave:
                continue
            if clave in indice:
                duplicados.add(clave)
            else:
                indice[clave] = ruta
        return indice, duplicados

    @staticmethod
    def _buscar(raiz, nombre):
        return raiz.find(f".//{{*}}{nombre}")

    @staticmethod
    def _texto(raiz, nombre):
        elemento = GeneradorCSV._buscar(raiz, nombre)
        if elemento is None or elemento.text is None:
            return ""
        return elemento.text.strip()

    @staticmethod
    def _normalizar_numero(valor):
        try:
            return Decimal(str(valor).strip().replace(",", ".")).normalize()
        except (InvalidOperation, ValueError):
            return None

    @staticmethod
    def _ruta_tabla_conversion():
        junto_script = Path(__file__).resolve().parent / "tabla_conversion.csv"
        if junto_script.is_file():
            return junto_script
        carpeta_actual = Path.cwd() / "tabla_conversion.csv"
        return carpeta_actual if carpeta_actual.is_file() else junto_script

    @staticmethod
    def _cargar_tabla_conversion(ruta):
        with open(ruta, "r", encoding="utf-8-sig", newline="") as archivo:
            muestra = archivo.read(4096)
            archivo.seek(0)
            try:
                dialecto = csv.Sniffer().sniff(muestra, delimiters=",;\t")
                lector = csv.DictReader(archivo, dialect=dialecto)
            except csv.Error:
                lector = csv.DictReader(archivo)

            if not lector.fieldnames:
                raise ValueError("La tabla no contiene encabezados.")

            encabezados = {
                nombre.strip().lower().replace("\\_", "_"): nombre
                for nombre in lector.fieldnames if nombre
            }
            columna_calibre = encabezados.get("calibre")
            columna_cross = encabezados.get("cross_section")
            if not columna_calibre or not columna_cross:
                raise ValueError(
                    "La tabla debe incluir las columnas "
                    "'calibre' y 'cross_section'."
                )

            conversion = {}
            for fila in lector:
                calibre = (fila.get(columna_calibre) or "").strip()
                cross_section = GeneradorCSV._normalizar_numero(
                    fila.get(columna_cross, "")
                )
                if calibre and cross_section is not None:
                    conversion[cross_section] = calibre

        if not conversion:
            raise ValueError("La tabla no contiene conversiones validas.")
        return conversion

    @staticmethod
    def _combinacion(raiz_nodo, tabla_conversion):
        lados = {"0": Counter(), "1": Counter()}
        faltantes = []

        for wire in raiz_nodo.findall(".//{*}Wire"):
            posicion = GeneradorCSV._buscar(wire, "Position")
            if posicion is None or posicion.get("h") not in lados:
                continue
            lado = posicion.get("h")

            ext_txt = GeneradorCSV._texto(wire, "ExtTxt")
            coincidencia = re.search(r"\d+(?:[.,]\d+)?", ext_txt)
            if coincidencia:
                calibre = coincidencia.group(0).replace(",", ".")
            else:
                cross_texto = GeneradorCSV._texto(wire, "CrossSection")
                cross_section = GeneradorCSV._normalizar_numero(cross_texto)
                calibre = (
                    tabla_conversion.get(cross_section)
                    if cross_section is not None else None
                )
                if not calibre:
                    faltantes.append(cross_texto or "sin CrossSection")
                    continue

            lados[lado][str(calibre)] += 1

        def clave_calibre(valor):
            try:
                return (0, float(valor))
            except ValueError:
                return (1, valor)

        def formatear(contador):
            return ", ".join(
                f"{cantidad}/{calibre}"
                for calibre, cantidad in sorted(
                    contador.items(), key=lambda x: clave_calibre(x[0])
                )
            )

        izquierda = formatear(lados["0"])
        derecha = formatear(lados["1"])
        combinacion = (
            f"{izquierda} = {derecha}"
            if izquierda and derecha
            else izquierda or derecha
        )

        # Las comillas son parte del texto para evitar conversiones a fecha.
        return f'"{combinacion}"', faltantes

    @staticmethod
    def _fila(archivo_nodo, archivo_parametros, tabla_conversion):
        nodo = ET.parse(archivo_nodo).getroot()
        parametros = ET.parse(archivo_parametros).getroot()
        validacion = GeneradorCSV._buscar(parametros, "Validation")
        energia = GeneradorCSV._buscar(parametros, "E")
        combinacion, faltantes = GeneradorCSV._combinacion(
            nodo, tabla_conversion
        )

        fila = {
            "Area (mm2)": (
                validacion.get("TCS", "") if validacion is not None else ""
            ),
            "Combinacion": combinacion,
            "Energia (J)": (
                energia.get("SetValue", "") if energia is not None else ""
            ),
            "Presion (b)": GeneradorCSV._texto(parametros, "Force1"),
            "Amplitud (mu)": GeneradorCSV._texto(parametros, "Amplitude1"),
            "Ancho (mm)": GeneradorCSV._texto(parametros, "NodeWidth")
        }
        return fila, faltantes

    @staticmethod
    def _clave_orden_area(fila):
        area = GeneradorCSV._normalizar_numero(fila.get("Area (mm2)", ""))
        return (1, Decimal("0")) if area is None else (0, area)

    @staticmethod
    def _nombre_seguro(texto):
        texto = re.sub(r'[<>:"/\\|?*\x00-\x1F]', "_", texto.strip())
        return texto.rstrip(". ") or "resultado"

    def _generar_csv(self):
        carpeta_nodos = Path(self.ruta_nodos.get().strip())
        carpeta_parametros = Path(self.ruta_parametros.get().strip())
        ruta_tabla = self._ruta_tabla_conversion()

        try:
            tabla_conversion = self._cargar_tabla_conversion(ruta_tabla)
        except (OSError, ValueError) as error:
            messagebox.showerror(
                "Error en tabla de conversion",
                f"No fue posible cargar:\n{ruta_tabla}\n\n{error}\n\n"
                "Coloque tabla_conversion.csv junto al script."
            )
            return

        nodos, duplicados_n = self._indexar_xml(carpeta_nodos, "N.")
        parametros, duplicados_p = self._indexar_xml(
            carpeta_parametros, "P."
        )
        claves = sorted(set(nodos) & set(parametros))
        if not claves:
            messagebox.showwarning(
                "Sin pares",
                "No se encontraron pares XML con el mismo valor "
                "en split('.')[1]."
            )
            return

        destino = filedialog.asksaveasfilename(
            title="Guardar archivo CSV",
            initialdir=str(carpeta_nodos),
            initialfile=self._nombre_seguro(self.estacion.get()) + ".csv",
            defaultextension=".csv",
            filetypes=[("Archivo CSV", "*.csv")]
        )
        if not destino:
            return

        filas = []
        errores = []
        faltantes_conversion = []
        for clave in claves:
            try:
                fila, faltantes = self._fila(
                    nodos[clave], parametros[clave], tabla_conversion
                )
                filas.append(fila)
                faltantes_conversion.extend(
                    f"{clave}: {valor}" for valor in faltantes
                )
            except (ET.ParseError, OSError, ValueError) as error:
                errores.append(f"{clave}: {error}")

        if not filas:
            messagebox.showerror(
                "No se pudo generar",
                "Todos los pares produjeron errores:\n\n"
                + "\n".join(errores[:10])
            )
            return

        filas.sort(key=self._clave_orden_area)

        try:
            with open(destino, "w", newline="", encoding="utf-8-sig") as archivo:
                escritor = csv.DictWriter(archivo, fieldnames=self.ENCABEZADOS)
                escritor.writeheader()
                escritor.writerows(filas)
        except OSError as error:
            messagebox.showerror("Error al guardar", str(error))
            return

        avisos = []
        sin_parametros = len(set(nodos) - set(parametros))
        sin_nodos = len(set(parametros) - set(nodos))
        if sin_parametros:
            avisos.append(f"Nodos sin parametros: {sin_parametros}")
        if sin_nodos:
            avisos.append(f"Parametros sin nodo: {sin_nodos}")
        if duplicados_n or duplicados_p:
            avisos.append(
                "Se detectaron claves duplicadas; se uso el primer archivo."
            )
        if errores:
            avisos.append(f"Pares omitidos por error: {len(errores)}")
        if faltantes_conversion:
            avisos.append(
                "Cables omitidos por no tener calibre ni conversion: "
                f"{len(faltantes_conversion)}"
            )

        self.estado.set(f"CSV generado: {destino}")
        mensaje = f"Se generaron {len(filas)} filas.\n\n{destino}"
        if avisos:
            mensaje += "\n\n" + "\n".join(avisos)
        messagebox.showinfo("Proceso terminado", mensaje)


if __name__ == "__main__":
    GeneradorCSV().mainloop()
