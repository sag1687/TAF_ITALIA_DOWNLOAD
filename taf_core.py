# -*- coding: utf-8 -*-
"""
Modulo core per il download e la conversione dei dati TAF.
Le dipendenze pesanti (geopandas, shapely) sono importate in modo lazy
per evitare crash nel Python di QGIS dove potrebbero non essere installate.
"""

import os
import csv
import json
import shutil
import zipfile
import traceback
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

# Dipendenze sempre disponibili nel Python di QGIS
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# pyproj è distribuito con QGIS
import pyproj

BASE_URL = "https://www1.agenziaentrate.gov.it/servizi/TafDis/download.php"
SUFFISSI_UFFICI = ["", "1", "2", "3", "4", "5"]

# Mappatura province → Grande Origine (fallback quando manca la Piccola
# Origine)
PROVINCIA_GRANDE_ORIGINE = {
    "VC": "1 Vercelli (Punto ideale)",
    "BI": "1 Vercelli (Punto ideale)",
    "NO": "1 Vercelli (Punto ideale)",
    "VB": "1 Vercelli (Punto ideale)",
    "AO": "1 Vercelli (Punto ideale)",
    "TO": "1 Vercelli (Punto ideale)",
    "CN": "1 Vercelli (Punto ideale)",
    "PN": "2 Pordenone",
    "UD": "2 Pordenone",
    "BL": "2 Pordenone",
    "VE": "2 Pordenone",
    "PD": "2 Pordenone",
    "TV": "2 Pordenone",
    "VR": "2 Pordenone",
    "VI": "2 Pordenone",
    "BG": "3 Monte Bronzone",
    "BS": "3 Monte Bronzone",
    "SO": "3 Monte Bronzone",
    "CR": "3 Monte Bronzone",
    "MN": "3 Monte Bronzone",
    "LO": "4 Lodi",
    "MI": "4 Lodi",
    "CO": "4 Lodi",
    "PC": "4 Lodi",
    "PR": "4 Lodi",
    "LC": "4 Lodi",
    "MB": "4 Lodi",
    "VA": "4 Lodi",
    "PV": "4 Lodi",
    "AL": "5 Alessandria",
    "AT": "5 Alessandria",
    "IM": "6 Monte Bignone",
    "GE": "7 Forte Diamante",
    "SV": "7 Forte Diamante",
    "SP": "7 Forte Diamante",
    "BO": "8 Portonovo",
    "FE": "8 Portonovo",
    "RA": "8 Portonovo",
    "FC": "8 Portonovo",
    "RN": "8 Portonovo",
    "RO": "8 Portonovo",
    "MO": "8 Portonovo",
    "RE": "8 Portonovo",
    "SI": "9 Siena (T. del Mangia)",
    "FI": "9 Siena (T. del Mangia)",
    "AR": "9 Siena (T. del Mangia)",
    "GR": "9 Siena (T. del Mangia)",
    "PI": "9 Siena (T. del Mangia)",
    "LI": "9 Siena (T. del Mangia)",
    "PT": "9 Siena (T. del Mangia)",
    "LU": "9 Siena (T. del Mangia)",
    "MS": "9 Siena (T. del Mangia)",
    "PO": "9 Siena (T. del Mangia)",
    "PU": "10 Urbino",
    "PG": "11 Monte Pennino",
    "MC": "11 Monte Pennino",
    "AN": "11 Monte Pennino",
    "AP": "11 Monte Pennino",
    "FM": "11 Monte Pennino",
    "RM": "12 Roma (Monte Mario)",
    "VT": "12 Roma (Monte Mario)",
    "TR": "12 Roma (Monte Mario)",
    "RI": "12 Roma (Monte Mario)",
    "LT": "12 Roma (Monte Mario)",
    "FR": "12 Roma (Monte Mario)",
    "AQ": "13 Monte Ocre",
    "TE": "13 Monte Ocre",
    "CH": "13 Monte Ocre",
    "PE": "13 Monte Ocre",
    "CB": "14 Valle Palombo",
    "IS": "14 Valle Palombo",
    "AV": "15 Monte Terminio",
    "BN": "15 Monte Terminio",
    "SA": "15 Monte Terminio",
    "TA": "16 Taranto",
    "LE": "17 Lecce",
    "BR": "17 Lecce",
    "CS": "18 Monte Brutto",
    "CZ": "18 Monte Brutto",
    "RC": "18 Monte Brutto",
    "VV": "18 Monte Brutto",
    "KR": "18 Monte Brutto",
    "AG": "19 Torre Titone",
    "CL": "19 Torre Titone",
    "CT": "20 Monte Etna (P. Lucia)",
    "ME": "20 Monte Etna (P. Lucia)",
    "EN": "20 Monte Etna (P. Lucia)",
    "SR": "22 Mineo",
    "RG": "22 Mineo",
    "PA": "19 Torre Titone",
    "TP": "19 Torre Titone",
    "CA": "23 Sardegna (Punto ideale)",
    "SS": "23 Sardegna (Punto ideale)",
    "NU": "23 Sardegna (Punto ideale)",
    "OR": "23 Sardegna (Punto ideale)",
    "SU": "23 Sardegna (Punto ideale)",
    "BZ": "24 Innsbruck",
    "TN": "24 Innsbruck",
    "TS": "25 Krimberg",
    "GO": "25 Krimberg",
    "CE": "26 Monte Cairo",
    "NA": "28 Cancello",
    "PZ": "14 Valle Palombo",
    "MT": "14 Valle Palombo",
    "FG": "16 Taranto",
    "BA": "16 Taranto",
    "BT": "16 Taranto",
}


def get_fallback_origine(sigla_provincia):
    """Cerca la Grande Origine di fallback per una provincia."""
    nome_go = PROVINCIA_GRANDE_ORIGINE.get(sigla_provincia)
    if nome_go:
        return ORIGINI_CASSINI.get("grandi_origini", {}).get(nome_go)
    return None


def get_configured_session() -> requests.Session:
    session = requests.Session()
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:122.0) "
            "Gecko/20100101 Firefox/122.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;"
            "q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "it-IT,it;q=0.8,en-US;q=0.5,en;q=0.3",
            "Connection": "keep-alive",
        }
    )
    return session


# Mappa in memoria per i Codici Belfiore
BELFIORE_MAP = None


def load_origini_cassini():
    json_path = os.path.join(os.path.dirname(__file__), "origini_cassini.json")
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:  # nosec B110
            pass
    return {"grandi_origini": {}, "piccole_origini": {}}


ORIGINI_CASSINI = load_origini_cassini()


def reload_origini():
    global ORIGINI_CASSINI
    ORIGINI_CASSINI = load_origini_cassini()


def get_cassini_transformer(lon_0, lat_0, x_0=0, y_0=0):
    # Trasformazione custom Cassini-Soldner su ellissoide Bessel -> WGS84
    # Parametri Bursa-Wolf approssimati per l'Italia (Roma 40 -> WGS84)
    proj4_str = (
        f"+proj=cass +lat_0={lat_0} +lon_0={lon_0} +x_0={x_0} +y_0={y_0} "
        "+ellps=bessel +towgs84=-104.1,-49.1,-9.9,0.971,-2.917,0.714,-11.68 "
        "+units=m +no_defs"
    )
    return pyproj.Transformer.from_crs(proj4_str, "EPSG:4326", always_xy=True)


def get_belfiore_map():
    global BELFIORE_MAP
    if BELFIORE_MAP is None:
        BELFIORE_MAP = {}
        json_path = os.path.join(os.path.dirname(__file__), "belfiore.json")
        if os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    BELFIORE_MAP = json.load(f)
            except Exception:  # nosec B110
                pass
    return BELFIORE_MAP


def convert_taf_to_csv(
    taf_file_path,
    csv_file_path,
    sigla_provincia,
    nome_provincia,
    raw_mode=False,
    try_convert=False,
):
    """Converte un file .TAF a spaziatura fissa in CSV con coordinate
    (WGS84 o originali)."""
    fields = [
        ("Codice_Comune", 0, 4),
        ("Sezione", 4, 5),
        ("Foglio", 6, 10),
        ("Allegato", 11, 12),
        ("PF_ID", 13, 17),
        ("Particella", 18, 29),
        ("Monografia_Planimetrica", 30, 100),
        ("Coord_Nord_Y", 101, 113),
        ("Coord_Est_X", 114, 126),
        ("Attendibilita_Plan", 127, 129),
        ("Data_Aggiornamento", 142, 148),
        ("Quota", 239, 251),
    ]

    transformer_gb_ovest = pyproj.Transformer.from_crs(
        "EPSG:3003", "EPSG:4326", always_xy=True
    )
    transformer_gb_est = pyproj.Transformer.from_crs(
        "EPSG:3004", "EPSG:4326", always_xy=True
    )

    belfiore = get_belfiore_map()

    try:
        with open(taf_file_path, "r", encoding="latin-1") as f_in, open(
            csv_file_path, "w", newline="", encoding="utf-8"
        ) as f_out:

            writer = csv.writer(f_out, delimiter=",")
            header = ["Codice_Comune", "Nome_Comune"]
            header.extend(f[0] for f in fields[1:])
            header += [
                "Sistema_Riferimento_Origine",
                "Lon_WGS84",
                "Lat_WGS84",
                "EPSG_Destinazione",
                "Link_Monografia",
            ]
            writer.writerow(header)

            for line in f_in:
                if len(line) < 150:
                    continue
                row = [line[f[1]:f[2]].strip() for f in fields]

                est_str = row[8]
                nord_str = row[7]
                codice_comune = row[0].upper()
                nome_comune = belfiore.get(codice_comune, "Sconosciuto")

                sr_origine = "Sconosciuto"
                lon_wgs84 = ""
                lat_wgs84 = ""
                epsg_dest = ""

                if est_str and nord_str:
                    try:
                        est_val = float(est_str)
                        nord_val = float(nord_str)

                        if 1300000 < est_val < 1900000:
                            sr_origine = "Gauss-Boaga Ovest (3003)"
                            if not raw_mode:
                                epsg_dest = "EPSG:4326"
                                lon_wgs84, lat_wgs84 = (
                                    transformer_gb_ovest.transform(
                                        est_val, nord_val
                                    )
                                )
                        elif 2300000 < est_val < 2900000:
                            sr_origine = "Gauss-Boaga Est (3004)"
                            if not raw_mode:
                                epsg_dest = "EPSG:4326"
                                lon_wgs84, lat_wgs84 = (
                                    transformer_gb_est.transform(
                                        est_val, nord_val
                                    )
                                )
                        elif abs(est_val) < 500000:
                            origine = None
                            if codice_comune in ORIGINI_CASSINI.get(
                                "piccole_origini", {}
                            ):
                                origine = ORIGINI_CASSINI["piccole_origini"][
                                    codice_comune
                                ]
                                sr_origine = (
                                    f"Cassini-Soldner (Locale: "
                                    f"{codice_comune})")
                            elif try_convert:
                                origine = get_fallback_origine(sigla_provincia)
                                if origine:
                                    sr_origine = (
                                        f"Cassini-Soldner (Approssimata: "
                                        f"{sigla_provincia})")
                                else:
                                    sr_origine = (
                                        "Cassini-Soldner (Origine sconosciuta)"
                                    )
                            else:
                                sr_origine = (
                                    "Cassini-Soldner (Origine sconosciuta)"
                                )

                            if not raw_mode:
                                if not origine:
                                    epsg_dest = (
                                        "Manca configurazione in "
                                        "origini_cassini.json")
                                else:
                                    epsg_dest = "EPSG:4326"
                                    transformer_cassini = (
                                        get_cassini_transformer(
                                            origine["lon"],
                                            origine["lat"],
                                            origine.get("falso_est", 0),
                                            origine.get("falso_nord", 0),
                                        )
                                    )
                                    lon_wgs84, lat_wgs84 = (
                                        transformer_cassini.transform(
                                            est_val, nord_val
                                        )
                                    )

                        if lon_wgs84 and lat_wgs84:
                            lon_wgs84 = f"{lon_wgs84:.6f}"
                            lat_wgs84 = f"{lat_wgs84:.6f}"
                    except ValueError:
                        pass

                url_provincia = urllib.parse.quote(nome_provincia)
                url_comune = urllib.parse.quote(nome_comune)
                url_co = urllib.parse.quote(codice_comune)
                url_foglio = urllib.parse.quote(row[2])
                link_mono = (
                    "https://www1.agenziaentrate.gov.it/servizi/Monografie/"
                    f"risultato.php?provincia={url_provincia}"
                    f"&comune={url_comune}&co={url_co}&foglio={url_foglio}"
                )

                row.insert(1, nome_comune)
                row.extend(
                    [sr_origine, lon_wgs84, lat_wgs84, epsg_dest, link_mono]
                )
                writer.writerow(row)
        return True
    except Exception:
        traceback.print_exc()
        return False


def create_geopackage(csv_filepath, gpkg_filepath, raw_mode=False):
    """Crea un GeoPackage dal CSV utilizzando le API native di QGIS."""
    try:
        from qgis.core import (
            QgsVectorLayer,
            QgsVectorFileWriter,
            QgsCoordinateTransformContext,
        )

        if raw_mode:
            uri = (
                f"file:///{csv_filepath}?delimiter=,&"
                f"xField=Coord_Est_X&yField=Coord_Nord_Y&crs=EPSG:3003"
            )
        else:
            uri = (
                f"file:///{csv_filepath}?delimiter=,&"
                f"xField=Lon_WGS84&yField=Lat_WGS84&crs=EPSG:4326"
            )

        layer = QgsVectorLayer(uri, "taf_layer", "delimitedtext")

        if not layer.isValid():
            return False

        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "GPKG"
        options.layerName = "Punti_Fiduciali"

        error_code, _ = QgsVectorFileWriter.writeAsVectorFormatV3(
            layer, gpkg_filepath, QgsCoordinateTransformContext(), options
        )

        return error_code == QgsVectorFileWriter.NoError
    except Exception:
        import traceback

        traceback.print_exc()
        return False


def _check_office(sigla, suffisso, download_dir):
    """Verifica se un ufficio ha dati.

    Restituisce il suffisso se valido, None altrimenti.
    """
    iduff = f"{sigla}{suffisso}"
    zip_filepath = os.path.join(download_dir, f"TAF_{iduff}.zip")
    if os.path.exists(zip_filepath) and os.path.getsize(zip_filepath) > 0:
        return suffisso
    session = get_configured_session()
    params = {"tipofile": "TAF", "iduff": iduff}
    try:
        resp = session.get(BASE_URL, params=params, stream=False, timeout=15)
        resp.raise_for_status()
        if "text/html" not in resp.headers.get("Content-Type", "").lower():
            return suffisso
    except Exception:  # nosec B110
        pass
    return None


def _download_office(sigla, suffisso, download_dir, raw_mode=False):
    """Scarica lo zip di un ufficio valido.

    Restituisce il suffisso se OK, None altrimenti.
    """
    iduff = f"{sigla}{suffisso}"
    zip_filepath = os.path.join(download_dir, f"TAF_{iduff}.zip")
    if os.path.exists(zip_filepath) and os.path.getsize(zip_filepath) > 0:
        return suffisso
    session = get_configured_session()
    params = {"tipofile": "TAF", "iduff": iduff}
    try:
        resp = session.get(BASE_URL, params=params, stream=True, timeout=30)
        resp.raise_for_status()
        with open(zip_filepath, "wb") as fd:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    fd.write(chunk)
        return suffisso
    except Exception:
        if os.path.exists(zip_filepath):
            try:
                os.remove(zip_filepath)
            except OSError:
                pass
        return None


def download_and_convert_province(
    sigla,
    nome_provincia,
    download_dir,
    progress_callback=None,
    raw_mode=False,
    try_convert=False,
):
    """Scarica e converte i dati TAF per una provincia.

    Usa chiamate parallele (ThreadPoolExecutor) per verificare e scaricare
    tutti gli uffici (suffissi) simultaneamente. Il primo che risponde
    non blocca gli altri: ogni ufficio valido viene scaricato e convertito.

    Se try_convert=True, per i punti Cassini-Soldner senza Piccola Origine
    configurata si usa la Grande Origine della provincia come fallback.

    Ritorna una lista di file generati (GPKG o CSV).
    """
    os.makedirs(download_dir, exist_ok=True)
    generated_files = []

    if progress_callback:
        progress_callback(0, f"--- AVVIO PROVINCIA: {sigla} ---")

    # Fase 1: verifica parallela di tutti i suffissi ufficio
    if progress_callback:
        progress_callback(5, "Verifica uffici in parallelo...")

    validi = []
    with ThreadPoolExecutor(max_workers=6) as executor:
        fut_map = {
            executor.submit(_check_office, sigla, s, download_dir): s
            for s in SUFFISSI_UFFICI
        }
        for future in as_completed(fut_map):
            s = fut_map[future]
            try:
                if future.result() is not None:
                    validi.append(s)
            except Exception:  # nosec B110
                pass

    validi.sort(key=SUFFISSI_UFFICI.index)
    if not validi:
        if progress_callback:
            progress_callback(
                100, "Nessun ufficio valido trovato per questa provincia."
            )
        return generated_files

    if progress_callback:
        uff_str = ", ".join(f"{sigla}{s}" for s in validi)
        progress_callback(10, f"Uffici validi trovati: {uff_str}")

    # Fase 2: download parallelo di tutti gli uffici validi
    if progress_callback:
        progress_callback(15, "Download in parallelo...")

    with ThreadPoolExecutor(max_workers=6) as executor:
        fut_map = {
            executor.submit(
                _download_office, sigla, s, download_dir, raw_mode
            ): s
            for s in validi
        }
        for future in as_completed(fut_map):
            s = fut_map[future]
            try:
                if future.result() is None:
                    if progress_callback:
                        progress_callback(
                            15, f"   Download fallito per {sigla}{s}"
                        )
            except Exception:  # nosec B110
                pass

    if progress_callback:
        progress_callback(
            50, "Download completato. Estrazione e conversione..."
        )

    # Fase 3: estrazione e conversione sequenziale
    for i, suffisso in enumerate(validi):
        iduff = f"{sigla}{suffisso}"
        zip_filepath = os.path.join(download_dir, f"TAF_{iduff}.zip")
        csv_filepath = os.path.join(
            download_dir, f"Tabella_Punti_Fiduciali_Prov_{iduff}.csv"
        )
        gpkg_filepath = os.path.join(
            download_dir, f"Tabella_Punti_Fiduciali_Prov_{iduff}.gpkg"
        )

        if not (
            os.path.exists(zip_filepath) and os.path.getsize(zip_filepath) > 0
        ):
            continue

        try:
            if progress_callback:
                pct = 50 + int((i / len(validi)) * 40)
                progress_callback(pct, f"   Estrazione {iduff}...")

            with zipfile.ZipFile(zip_filepath, "r") as zip_ref:
                taf_files = [
                    f for f in zip_ref.namelist() if f.lower().endswith(".taf")
                ]
                if not taf_files:
                    continue

                taf_member = taf_files[0]
                # Estrazione con nome sanificato: il nome dentro lo zip
                # potrebbe contenere sottocartelle o ".." e uscire dalla
                # cartella di download (zip slip)
                taf_filename = os.path.basename(
                    taf_member.replace("\\", "/")
                )
                taf_filepath = os.path.join(download_dir, taf_filename)
                with zip_ref.open(taf_member) as src, \
                        open(taf_filepath, "wb") as dst:
                    shutil.copyfileobj(src, dst)

                csv_ok = convert_taf_to_csv(
                    taf_filepath,
                    csv_filepath,
                    sigla,
                    nome_provincia,
                    raw_mode,
                    try_convert,
                )

                if csv_ok:
                    gpkg_ok = create_geopackage(
                        csv_filepath, gpkg_filepath, raw_mode
                    )
                    if gpkg_ok:
                        generated_files.append(gpkg_filepath)
                    else:
                        generated_files.append(csv_filepath)

                if os.path.exists(taf_filepath):
                    os.remove(taf_filepath)

        except Exception:
            try:
                os.remove(zip_filepath)
            except OSError:
                pass

    if progress_callback:
        progress_callback(100, "--- ELABORAZIONE TERMINATA ---")
        progress_callback(100, f"    File generati: {len(generated_files)}")

    return generated_files
