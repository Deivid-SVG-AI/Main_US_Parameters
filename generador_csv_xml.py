import csv
import re
import tkinter as tk
from collections import Counter
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
import xml.etree.ElementTree as ET


class GeneradorCSV(tk.Tk):
    """Interfaz para emparejar XML de nodos y parametros y generar un CSV."""

    def __init__(self):
        super().__init__()
        self.title("Generador CSV de nodos y parametros")
        self.geometry("780x255")
        self.minsize(680, 255)

        self.ruta_nodos = tk.StringVar()
        self.ruta_parametros = tk.StringVar()
        self.estacion = tk.StringVar()
        self.estado = tk.StringVar(value="Seleccione las carpetas e ingrese la estacion.")

        self._crear_interfaz()

        for variable in (self.ruta_nodos, self.ruta_parametros, self.estacion):
            variable.trace_add("write", self._validar_formulario)

    def _crear_interfaz(self):
        marco = ttk.Frame(self, padding=18)
        marco.pack(fill="both", expand=True)
        marco.columnconfigure(1, weight=1)

        ttk.Label(marco, text="Ruta para los nodos:").grid(row=0, column=0, sticky="w", pady=7)
        ttk.Entry(marco, textvariable=self.ruta_nodos).grid(
            row=0, column=1, sticky="ew", padx=10, pady=7
        )
        ttk.Button(
            marco, text="Browse", command=lambda: self._seleccionar_carpeta(self.ruta_nodos)
        ).grid(row=0, column=2, pady=7)

        ttk.Label(marco, text="Ruta para parametros:").grid(row=1, column=0, sticky="w", pady=7)
        ttk.Entry(marco, textvariable=self.ruta_parametros).grid(
            row=1, column=1, sticky="ew", padx=10, pady=7
        )
        ttk.Button(
            marco, text="Browse", command=lambda: self._seleccionar_carpeta(self.ruta_parametros)
        ).grid(row=1, column=2, pady=7)

        ttk.Label(marco, text="Estacion:").grid(row=2, column=0, sticky="w", pady=7)
        ttk.Entry(marco, textvariable=self.estacion).grid(
            row=2, column=1, sticky="ew", padx=10, pady=7
        )

        self.boton_generar = ttk.Button(
            marco, text="Generar", command=self._generar_csv, state="disabled"
        )
        self.boton_generar.grid(row=3, column=1, pady=(15, 7))

        ttk.Label(marco, textvariable=self.estado, foreground="#555555").grid(
            row=4, column=0, columnspan=3, sticky="w", pady=(8, 0)
        )

    def _seleccionar_carpeta(self, variable):
        ruta = filedialog.askdirectory(title="Seleccione una carpeta")
        if ruta:
            variable.set(ruta)

    def _validar_formulario(self, *_):
        nodos_validos = Path(self.ruta_nodos.get().strip()).is_dir()
        parametros_validos = Path(self.ruta_parametros.get().strip()).is_dir()
        estacion_valida = len(self.estacion.get().strip()) >= 3
        estado = "normal" if nodos_validos and parametros_validos and estacion_valida else "disabled"
        self.boton_generar.configure(state=estado)

    @staticmethod
    def _clave_archivo(ruta):
        """Devuelve filename.split('.')[1], o None si el nombre no cumple el formato."""
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
            if clave:
                if clave in indice:
                    duplicados.add(clave)
                else:
                    indice[clave] = ruta
        return indice, duplicados

    @staticmethod
    def _raiz_xml(ruta):
        return ET.parse(ruta).getroot()

    @staticmethod
    def _buscar(raiz, nombre):
        # { * } permite encontrar el elemento sin depender del namespace del XML.
        return raiz.find(f".//{{*}}{nombre}")

    @staticmethod
    def _texto(raiz, nombre):
        elemento = GeneradorCSV._buscar(raiz, nombre)
        if elemento is None or elemento.text is None:
            return ""
        return elemento.text.strip()

    @staticmethod
    def _combinacion(raiz_nodo):
        lados = {"0": Counter(), "1": Counter()}

        for wire in raiz_nodo.findall(".//{*}Wire"):
            ext_txt = GeneradorCSV._texto(wire, "ExtTxt")
            posicion = GeneradorCSV._buscar(wire, "Position")
            if posicion is None:
                continue

            lado = posicion.get("h")
            if lado not in lados:
                continue

            # Obtiene el primer valor numerico. Ej.: 20TXL -> 20.
            coincidencia = re.search(r"\d+(?:[.,]\d+)?", ext_txt)
            if not coincidencia:
                continue
            calibre = coincidencia.group(0).replace(",", ".")
            lados[lado][calibre] += 1

        def ordenar_calibre(valor):
            try:
                return (0, float(valor))
            except ValueError:
                return (1, valor)

        def formatear(contador):
            return ", ".join(
                f"{cantidad}/{calibre}"
                for calibre, cantidad in sorted(contador.items(), key=lambda item: ordenar_calibre(item[0]))
            )

        izquierda = formatear(lados["0"])
        derecha = formatear(lados["1"])
        # Se conservan ambos lados; si uno no tiene cables quedara vacio.
        return f"{izquierda} = {derecha}"

    @staticmethod
    def _fila(archivo_nodo, archivo_parametros):
        nodo = GeneradorCSV._raiz_xml(archivo_nodo)
        parametros = GeneradorCSV._raiz_xml(archivo_parametros)

        validacion = GeneradorCSV._buscar(parametros, "Validation")
        energia = GeneradorCSV._buscar(parametros, "E")

        return {
            "Area (mm2)": validacion.get("TCS", "") if validacion is not None else "",
            "Combinacion": GeneradorCSV._combinacion(nodo),
            "Energia (J)": energia.get("SetValue", "") if energia is not None else "",
            "Presion (b)": GeneradorCSV._texto(parametros, "Force1"),
            "Amplitud (mu)": GeneradorCSV._texto(parametros, "Amplitude1"),
            "Ancho (mm)": GeneradorCSV._texto(parametros, "NodeWidth"),
        }

    @staticmethod
    def _nombre_seguro(texto):
        texto = re.sub(r'[<>:"/\\|?*\x00-\x1F]', "_", texto.strip())
        return texto.rstrip(". ") or "resultado"

    def _generar_csv(self):
        carpeta_nodos = Path(self.ruta_nodos.get().strip())
        carpeta_parametros = Path(self.ruta_parametros.get().strip())

        nodos, duplicados_n = self._indexar_xml(carpeta_nodos, "N.")
        parametros, duplicados_p = self._indexar_xml(carpeta_parametros, "P.")
        claves = sorted(set(nodos) & set(parametros))

        if not claves:
            messagebox.showwarning(
                "Sin pares",
                "No se encontraron pares XML con el mismo valor en split('.')[1].",
            )
            return

        nombre = self._nombre_seguro(self.estacion.get()) + ".csv"
        destino = filedialog.asksaveasfilename(
            title="Guardar archivo CSV",
            initialdir=str(carpeta_nodos),
            initialfile=nombre,
            defaultextension=".csv",
            filetypes=[("Archivo CSV", "*.csv")],
        )
        if not destino:
            return

        filas = []
        errores = []
        for clave in claves:
            try:
                filas.append(self._fila(nodos[clave], parametros[clave]))
            except (ET.ParseError, OSError, ValueError) as error:
                errores.append(f"{clave}: {error}")

        if not filas:
            messagebox.showerror(
                "No se pudo generar",
                "Todos los pares produjeron errores:\n\n" + "\n".join(errores[:10]),
            )
            return

        encabezados = [
            "Area (mm2)", "Combinacion", "Energia (J)",
            "Presion (b)", "Amplitud (mu)", "Ancho (mm)"
        ]
        try:
            # utf-8-sig facilita que Excel reconozca acentos y simbolos correctamente.
            with open(destino, "w", newline="", encoding="utf-8-sig") as archivo:
                escritor = csv.DictWriter(archivo, fieldnames=encabezados)
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
            avisos.append("Se detectaron claves duplicadas; se uso el primer archivo de cada clave.")
        if errores:
            avisos.append(f"Pares omitidos por error: {len(errores)}")

        detalle = "\n".join(avisos)
        self.estado.set(f"CSV generado: {destino}")
        messagebox.showinfo(
            "Proceso terminado",
            f"Se generaron {len(filas)} filas.\n\n{destino}" + (f"\n\n{detalle}" if detalle else ""),
        )


if __name__ == "__main__":
    app = GeneradorCSV()
    app.mainloop()
