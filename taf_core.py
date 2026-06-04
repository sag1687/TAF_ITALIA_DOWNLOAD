# -*- coding: utf-8 -*-
"""
Modulo core per il download e la conversione dei dati TAF.
Le dipendenze pesanti (geopandas, shapely) sono importate in modo lazy
per evitare crash nel Python di QGIS dove potrebbero non essere installate.
"""

import os
import csv
import time
import zipfile
import traceback

# Dipendenze sempre disponibili nel Python di QGIS
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# pyproj è distribuito con QGIS
import pyproj

# Mappatura delle Origini Catastali (Lat, Lon in WGS84)
ORIGINI_CASSINI = {
    "VC": (45.45, 8.2041), "BI": (45.45, 8.2041), "NO": (45.45, 8.2041),
    "VB": (45.45, 8.2041), "PN": (45.9541, 12.6602), "UD": (45.9541, 12.6602),
    "BL": (45.9541, 12.6602), "VE": (45.9541, 12.6602), "BG": (45.7086, 9.9902),
    "BS": (45.7086, 9.9902), "SO": (45.7086, 9.9902), "CR": (45.7086, 9.9902),
    "LO": (45.3136, 9.5025), "MI": (45.3136, 9.5025), "CO": (45.3136, 9.5025),
    "PC": (45.3136, 9.5025), "PR": (45.3136, 9.5025), "AL": (44.9141, 8.6105),
    "AT": (44.9141, 8.6105), "IM": (43.8727, 7.7327), "GE": (44.4605, 8.9386),
    "SV": (44.4605, 8.9386), "SP": (44.4605, 8.9386), "BO": (44.5319, 11.753),
    "FE": (44.5319, 11.753), "RA": (44.5319, 11.753), "FC": (44.5319, 11.753),
    "RN": (44.5319, 11.753), "RO": (44.5319, 11.753), "SI": (43.3175, 11.3316),
    "FI": (43.3175, 11.3316), "AR": (43.3175, 11.3316), "GR": (43.3175, 11.3316),
    "PI": (43.3175, 11.3316), "LI": (43.3175, 11.3316), "PT": (43.3175, 11.3316),
    "PU": (43.7241, 12.6361), "PG": (43.1005, 12.8886), "MC": (43.1005, 12.8886),
    "AN": (43.1005, 12.8886), "AP": (43.1005, 12.8886), "FM": (43.1005, 12.8886),
    "RM": (41.9233, 12.4522), "VT": (41.9233, 12.4522), "TR": (41.9233, 12.4522),
    "RI": (41.9233, 12.4522), "LT": (41.9233, 12.4522), "FR": (41.9233, 12.4522),
    "AV": (40.8402, 14.9372), "BN": (40.8402, 14.9372), "SA": (40.8402, 14.9372),
    "PZ": (40.9502, 15.6363), "MT": (40.9502, 15.6363), "FG": (41.7063, 15.9538),
    "BA": (41.0927, 16.7577), "BT": (41.0927, 16.7577), "LE": (40.3505, 18.1694),
    "BR": (40.3505, 18.1694), "TA": (40.3505, 18.1694), "CS": (39.1394, 16.4219),
    "CZ": (39.1394, 16.4219), "RC": (39.1394, 16.4219), "VV": (39.1394, 16.4219),
    "KR": (39.1394, 16.4219), "CT": (37.7513, 14.9955), "ME": (37.7513, 14.9955),
    "EN": (37.7513, 14.9955), "AG": (37.6175, 13.5883), "CL": (37.6175, 13.5883),
    "SR": (37.265, 14.6905), "RG": (37.265, 14.6905), "PA": (37.9569, 14.0208),
    "TP": (37.9569, 14.0208), "BZ": (47.2666, 11.4), "TN": (47.2666, 11.4),
    "TS": (45.928, 14.4708), "GO": (45.928, 14.4708), "CE": (41.5461, 13.7661),
    "NA": (41.0002, 14.4308), "PV": (45.186, 9.154), "CA": (39.2238, 9.1116),
    "SS": (40.7259, 8.5556), "NU": (40.3167, 9.3333), "OR": (39.9, 8.5833),
    "AO": (45.45, 8.2041), "TO": (45.45, 8.2041), "CN": (45.45, 8.2041),
    "LC": (45.3136, 9.5025), "MB": (45.3136, 9.5025), "VA": (45.3136, 9.5025),
    "MN": (45.7086, 9.9902), "PD": (45.9541, 12.6602), "TV": (45.9541, 12.6602),
    "VR": (45.9541, 12.6602), "VI": (45.9541, 12.6602), "MO": (44.5319, 11.753),
    "RE": (44.5319, 11.753), "LU": (43.3175, 11.3316), "MS": (43.3175, 11.3316),
    "PO": (43.3175, 11.3316), "AQ": (41.9233, 12.4522), "TE": (41.9233, 12.4522),
    "CH": (41.9233, 12.4522), "PE": (41.9233, 12.4522), "CB": (40.9502, 15.6363),
    "IS": (40.9502, 15.6363), "SU": (39.2238, 9.1116)
}

BASE_URL = "https://www1.agenziaentrate.gov.it/servizi/TafDis/download.php"
# Suffissi uffici: il caso base ("") è primo come nello script originale funzionante
SUFFISSI_UFFICI = ["", "1", "2", "3", "4", "5"]


def get_configured_session() -> requests.Session:
    session = requests.Session()
    retry_strategy = Retry(
        total=5,
        backoff_factor=2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:122.0) '
                      'Gecko/20100101 Firefox/122.0',
        'Accept': 'text/html,application/xhtml+xml,application/xml;'
                  'q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'it-IT,it;q=0.8,en-US;q=0.5,en;q=0.3',
        'Connection': 'keep-alive'
    })
    return session


def get_cassini_transformer(lat_0, lon_0):
    proj_string = f"+proj=cass +lat_0={lat_0} +lon_0={lon_0} +x_0=0 +y_0=0 " \
                  f"+ellps=bessel +units=m +no_defs"
    return pyproj.Transformer.from_proj(proj_string, "EPSG:4326",
                                        always_xy=True)


def convert_taf_to_csv(taf_file_path, csv_file_path, sigla_provincia):
    """Converte un file .TAF a spaziatura fissa in CSV con coordinate WGS84."""
    fields = [
        ("Codice_Comune", 0, 4), ("Sezione", 4, 5), ("Foglio", 6, 10),
        ("Allegato", 11, 12), ("PF_ID", 13, 17), ("Particella", 18, 29),
        ("Monografia_Planimetrica", 30, 100), ("Coord_Nord_Y", 101, 113),
        ("Coord_Est_X", 114, 126), ("Attendibilita_Plan", 127, 129),
        ("Data_Aggiornamento", 142, 148), ("Quota", 239, 251)
    ]

    transformer_gb_ovest = pyproj.Transformer.from_crs(
        "EPSG:3003", "EPSG:4326", always_xy=True)
    transformer_gb_est = pyproj.Transformer.from_crs(
        "EPSG:3004", "EPSG:4326", always_xy=True)

    transformer_cassini = None
    if sigla_provincia in ORIGINI_CASSINI:
        lat_0, lon_0 = ORIGINI_CASSINI[sigla_provincia]
        transformer_cassini = get_cassini_transformer(lat_0, lon_0)

    try:
        with open(taf_file_path, 'r', encoding='latin-1') as f_in, \
                open(csv_file_path, 'w', newline='', encoding='utf-8') as f_out:

            writer = csv.writer(f_out, delimiter=',')
            header = [f[0] for f in fields] + \
                ["Sistema_Riferimento_Origine", "Lon_WGS84",
                 "Lat_WGS84", "EPSG_Destinazione"]
            writer.writerow(header)

            for line in f_in:
                if len(line) < 150:
                    continue
                row = [line[f[1]:f[2]].strip() for f in fields]

                est_str = row[8]
                nord_str = row[7]
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
                            epsg_dest = "EPSG:4326"
                            lon_wgs84, lat_wgs84 = \
                                transformer_gb_ovest.transform(
                                    est_val, nord_val)
                        elif 2300000 < est_val < 2900000:
                            sr_origine = "Gauss-Boaga Est (3004)"
                            epsg_dest = "EPSG:4326"
                            lon_wgs84, lat_wgs84 = \
                                transformer_gb_est.transform(est_val, nord_val)
                        elif abs(est_val) < 500000:
                            sr_origine = "Cassini-Soldner"
                            if transformer_cassini:
                                epsg_dest = "EPSG:4326 (Cassini)"
                                lon_wgs84, lat_wgs84 = \
                                    transformer_cassini.transform(
                                        est_val, nord_val)
                            else:
                                epsg_dest = "Origine non definita"

                        if lon_wgs84 and lat_wgs84:
                            lon_wgs84 = f"{lon_wgs84:.6f}"
                            lat_wgs84 = f"{lat_wgs84:.6f}"
                    except ValueError:
                        pass

                row.extend([sr_origine, lon_wgs84, lat_wgs84, epsg_dest])
                writer.writerow(row)
        return True
    except Exception as e:
        traceback.print_exc()
        return False


def create_geopackage(csv_filepath, gpkg_filepath):
    """Crea un GeoPackage dal CSV. Richiede geopandas e shapely.
    Se non sono installati, ritorna False senza crash."""
    try:
        import pandas as pd
        import geopandas as gpd
        from shapely.geometry import Point
    except ImportError:
        # geopandas/shapely non disponibili nel Python di QGIS
        # Il CSV è già stato creato, il GPKG viene saltato
        return False

    try:
        df = pd.read_csv(csv_filepath, dtype=str)
        mask = df['Lon_WGS84'].notna() & df['Lat_WGS84'].notna() & \
            (df['Lon_WGS84'] != "")
        df_valid = df[mask].copy()
        if df_valid.empty:
            return False

        df_valid['Lon'] = pd.to_numeric(df_valid['Lon_WGS84'], errors='coerce')
        df_valid['Lat'] = pd.to_numeric(df_valid['Lat_WGS84'], errors='coerce')
        df_valid = df_valid.dropna(subset=['Lon', 'Lat'])

        geometry = [Point(xy) for xy in zip(df_valid['Lon'], df_valid['Lat'])]
        df_valid = df_valid.drop(columns=['Lon', 'Lat'])

        gdf = gpd.GeoDataFrame(df_valid, geometry=geometry, crs="EPSG:4326")
        gdf.to_file(gpkg_filepath, driver="GPKG")
        return True
    except Exception:
        traceback.print_exc()
        return False


def download_and_convert_province(sigla, download_dir, progress_callback=None):
    """Scarica e converte i dati TAF per una provincia.

    Per ogni provincia, prova tutti gli uffici: sigla pura (es. PD),
    poi sigla+numero (PD1, PD2, ..., PD5).

    Se geopandas non è disponibile, produce CSV con coordinate WGS84
    che QGIS può caricare come layer di testo delimitato.

    Ritorna una lista di file generati (GPKG o CSV).
    """
    os.makedirs(download_dir, exist_ok=True)
    session = get_configured_session()
    generated_files = []
    total_steps = len(SUFFISSI_UFFICI)

    if progress_callback:
        progress_callback(0, f"--- AVVIO PROVINCIA: {sigla} ---")
        progress_callback(0, f"    Uffici da verificare: {', '.join(f'{sigla}{s}' for s in SUFFISSI_UFFICI)}")

    for i, suffisso in enumerate(SUFFISSI_UFFICI):
        iduff = f"{sigla}{suffisso}"
        zip_filename = f"TAF_{iduff}.zip"
        zip_filepath = os.path.join(download_dir, zip_filename)
        csv_filepath = os.path.join(
            download_dir, f"Tabella_Punti_Fiduciari_Area_{iduff}.csv")
        gpkg_filepath = os.path.join(
            download_dir, f"Tabella_Punti_Fiduciari_Area_{iduff}.gpkg")

        pct = int((i / total_steps) * 100)

        if progress_callback:
            progress_callback(pct, f">> Verifica ufficio {iduff}...")

        # Se il file esiste già e non è vuoto, saltiamo il download
        if not (os.path.exists(zip_filepath) and
                os.path.getsize(zip_filepath) > 0):
            params = {'tipofile': 'TAF', 'iduff': iduff}
            try:
                # Piccolo sleep per evitare blocchi WAF
                time.sleep(0.5)

                if progress_callback:
                    progress_callback(pct, f"   Richiesta download {iduff}...")

                response = session.get(BASE_URL, params=params,
                                       stream=True, timeout=30)
                response.raise_for_status()
                content_type = response.headers.get('Content-Type', '').lower()

                if progress_callback:
                    progress_callback(pct,
                                      f"   Risposta server: HTTP {response.status_code}, "
                                      f"Content-Type: {content_type[:40]}")

                if 'text/html' in content_type:
                    if progress_callback:
                        progress_callback(pct,
                                          f"   [!] {iduff} non disponibile sul server.")
                    continue

                total_size = int(response.headers.get('content-length', 0))
                downloaded = 0
                with open(zip_filepath, 'wb') as fd:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            fd.write(chunk)
                            downloaded += len(chunk)
                            if progress_callback and total_size > 0:
                                step_start = (i / total_steps) * 100
                                step_span = (0.5 / total_steps) * 100
                                chunk_p = (downloaded / total_size) * step_span
                                dl_mb = downloaded / (1024 * 1024)
                                tot_mb = total_size / (1024 * 1024)
                                progress_callback(
                                    int(step_start + chunk_p),
                                    f"   Downloading {iduff}: "
                                    f"{dl_mb:.1f}/{tot_mb:.1f} MB...")

                if progress_callback:
                    size_kb = downloaded / 1024
                    progress_callback(int(((i + 0.5) / total_steps) * 100),
                                      f"   [OK] {iduff} scaricato ({size_kb:.0f} KB).")

            except Exception as e:
                if progress_callback:
                    progress_callback(pct,
                                      f"   [ERRORE RETE] {iduff}: {str(e)[:60]}")
                continue

        # Estrazione e conversione
        if os.path.exists(zip_filepath) and os.path.getsize(zip_filepath) > 0:
            try:
                if progress_callback:
                    progress_callback(int(((i + 0.6) / total_steps) * 100),
                                      f"   Estrazione e conversione {iduff}...")

                with zipfile.ZipFile(zip_filepath, 'r') as zip_ref:
                    taf_files = [f for f in zip_ref.namelist()
                                 if f.lower().endswith('.taf')]
                    if not taf_files:
                        if progress_callback:
                            progress_callback(pct,
                                              f"   [!] Nessun file .taf in {zip_filename}")
                        continue

                    taf_filename = taf_files[0]
                    taf_filepath = os.path.join(download_dir, taf_filename)
                    zip_ref.extract(taf_filename, download_dir)

                    csv_ok = convert_taf_to_csv(
                        taf_filepath, csv_filepath, sigla)

                    if csv_ok:
                        if progress_callback:
                            progress_callback(int(((i + 0.7) / total_steps) * 100),
                                              f"   [OK] CSV creato per {iduff}.")

                        # Tenta GPKG (richiede geopandas)
                        gpkg_ok = create_geopackage(csv_filepath, gpkg_filepath)

                        if gpkg_ok:
                            generated_files.append(gpkg_filepath)
                            if progress_callback:
                                progress_callback(
                                    int(((i + 0.9) / total_steps) * 100),
                                    f"   [SUCCESSO] {iduff} -> GPKG creato.")
                        else:
                            # Fallback: usiamo il CSV (caricabile in QGIS)
                            generated_files.append(csv_filepath)
                            if progress_callback:
                                progress_callback(
                                    int(((i + 0.9) / total_steps) * 100),
                                    f"   [OK] {iduff} -> CSV con coordinate WGS84 "
                                    f"(GPKG non creato, geopandas non disponibile).")
                    else:
                        if progress_callback:
                            progress_callback(pct,
                                              f"   [ERRORE] Conversione CSV fallita per {iduff}.")

                    if os.path.exists(taf_filepath):
                        os.remove(taf_filepath)

            except zipfile.BadZipFile:
                if progress_callback:
                    progress_callback(pct,
                                      f"   [ERRORE] {zip_filename} corrotto, eliminato.")
                # Rimuovi file corrotto così al prossimo tentativo si riscarica
                try:
                    os.remove(zip_filepath)
                except OSError:
                    pass

            except Exception as e:
                if progress_callback:
                    progress_callback(pct,
                                      f"   [ERRORE] {iduff}: {str(e)[:60]}")

    if progress_callback:
        progress_callback(100, f"--- ELABORAZIONE TERMINATA ---")
        progress_callback(100, f"    File generati: {len(generated_files)}")

    return generated_files
