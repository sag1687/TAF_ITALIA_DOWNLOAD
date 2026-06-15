# -*- coding: utf-8 -*-

import os
import json
import csv
import webbrowser
from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import (QDialog, QCompleter, QWidget, QVBoxLayout,
                                 QHBoxLayout, QPushButton, QLabel, QTableWidget,
                                 QTableWidgetItem, QHeaderView, QMessageBox, QFileDialog)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QPixmap, QIcon, QCursor, QColor

FORM_CLASS, _ = uic.loadUiType(
    os.path.join(os.path.dirname(__file__), "agenzia_taf_dialog_base.ui")
)


class AgenziaTafDialog(QDialog, FORM_CLASS):
    def __init__(self, parent=None):
        super(AgenziaTafDialog, self).__init__(parent)
        self.setupUi(self)
        self.comuni_map = {}
        self.plugin_urls = {}

        self.load_comuni()
        self.setup_info_tab()
        self.setup_fonti_tab()
        self.setup_origini_tab()

        # Checkbox per raw mode e try_convert
        from qgis.PyQt.QtWidgets import QCheckBox
        self.chk_raw_mode = QCheckBox("Scarica TAF Grezzi originali (No trasformazione WGS84)")
        self.chk_raw_mode.setStyleSheet("color: #ecf0f1; font-weight: bold; margin-bottom: 5px;")
        self.chk_try_convert = QCheckBox("Prova conversione WGS84 (usa Grande Origine se manca Piccola Origine)")
        self.chk_try_convert.setStyleSheet("color: #ecf0f1; font-weight: bold; margin-bottom: 5px;")
        self.chk_try_convert.setChecked(True)
        layout = self.groupBox_search.layout()
        if layout:
            layout.insertWidget(1, self.chk_raw_mode)
            layout.insertWidget(2, self.chk_try_convert)

        self.apply_styles()

        # Setup Mappa Interna
        from qgis.gui import QgsMapCanvas, QgsMapToolPan
        from qgis.core import QgsRasterLayer, QgsRectangle, QgsCoordinateReferenceSystem

        self.map_canvas = QgsMapCanvas(self.map_container)
        self.map_canvas.setCanvasColor(QColor("#1b2317"))
        self.map_canvas.enableAntiAliasing(True)
        self.verticalLayout_map.addWidget(self.map_canvas)

        # Load OSM layer by default (stored in self to prevent garbage collection)
        osm_url = "type=xyz&url=https://tile.openstreetmap.org/{z}/{x}/{y}.png&zmax=19&zmin=0&crs=EPSG3857"
        self.osm_layer = QgsRasterLayer(osm_url, "OpenStreetMap", "wms")
        if self.osm_layer.isValid():
            self.map_canvas.setDestinationCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
            self.map_canvas.setLayers([self.osm_layer])

            # Center on Italy (approx bounding box in EPSG:3857)
            italy_rect = QgsRectangle(752834, 4390000, 2061000, 5950000)
            self.map_canvas.setExtent(italy_rect)
            self.map_canvas.refresh()

        # Make map interactive
        self.tool_pan = QgsMapToolPan(self.map_canvas)
        self.map_canvas.setMapTool(self.tool_pan)

        # Inizializza log a scomparsa
        self.groupBox_log.setVisible(False)
        self.btn_toggle_log.clicked.connect(self.toggle_log)

    def toggle_log(self):
        visible = self.groupBox_log.isVisible()
        self.groupBox_log.setVisible(not visible)
        if not visible:
            self.btn_toggle_log.setText("🔼 Nascondi Console di Log")
        else:
            self.btn_toggle_log.setText("🔽 Mostra Console di Log")
        self.adjustSize()

    def apply_styles(self):
        """Applica lo stile Forest Theme (Dark Woodland e Olive)."""
        qss = """
        QDialog {
            background-color: #1f271b;
            color: #ecf0f1;
        }
        QTabWidget::pane {
            border: 1px solid #3f5231;
            border-radius: 4px;
            background: #2a3622;
        }
        QTabBar::tab {
            background: #1b2317;
            border: 1px solid #3f5231;
            padding: 8px 12px;
            margin-right: 2px;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
            color: #bdc3c7;
            font-weight: bold;
        }
        QTabBar::tab:selected {
            background: #2a3622;
            border-bottom-color: #2a3622;
            color: #ecf0f1;
        }
        QGroupBox {
            font-weight: bold;
            color: #ecf0f1;
            border: 1px solid #3f5231;
            border-radius: 6px;
            margin-top: 10px;
            background-color: #2a3622;
            padding: 10px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 0 5px;
            left: 10px;
        }
        QLabel {
            color: #ecf0f1;
        }
        QPushButton#btn_scarica {
            background-color: #6b8e23;
            color: white;
            font-weight: bold;
            font-size: 14px;
            border-radius: 5px;
            padding: 10px;
            border: none;
        }
        QPushButton#btn_scarica:hover {
            background-color: #556b2f;
        }
        QPushButton#btn_scarica:pressed {
            background-color: #3f5231;
        }
        QPushButton#btn_scarica:disabled {
            background-color: #3e4a36;
            color: #7f8c8d;
        }
        QPushButton#btn_toggle_log {
            background-color: transparent;
            color: #6b8e23;
            border: none;
            text-align: left;
            font-weight: bold;
            padding: 5px;
        }
        QPushButton#btn_toggle_log:hover {
            color: #808000;
            text-decoration: underline;
        }
        QPlainTextEdit#txt_console {
            background-color: #0b0f09;
            color: #6b8e23;
            font-family: Consolas, monospace;
            border-radius: 4px;
            padding: 5px;
            border: 1px solid #3f5231;
        }
        QComboBox {
            border: 1px solid #3f5231;
            border-radius: 4px;
            padding: 4px;
            background-color: #1f271b;
            color: #ecf0f1;
        }
        QComboBox QAbstractItemView {
            background-color: #1f271b;
            color: #ecf0f1;
            selection-background-color: #6b8e23;
        }
        QProgressBar {
            border: 1px solid #3f5231;
            border-radius: 4px;
            text-align: center;
            color: #ecf0f1;
            font-weight: bold;
            background-color: #1b2317;
        }
        QProgressBar::chunk {
            background-color: #6b8e23;
            width: 10px;
        }
        QWidget#map_container {
            border: 2px solid #3f5231;
            border-radius: 4px;
            background-color: #1b2317;
        }
        QTableWidget {
            background-color: #1b2317;
            color: #ecf0f1;
            gridline-color: #3f5231;
            border: 1px solid #3f5231;
            border-radius: 4px;
        }
        QHeaderView::section {
            background-color: #2a3622;
            color: #bdc3c7;
            padding: 4px;
            border: 1px solid #3f5231;
            font-weight: bold;
        }
        QTableWidget::item:selected {
            background-color: #6b8e23;
        }
        """
        self.setStyleSheet(qss)

    def append_log(self, text):
        """Aggiunge una riga alla console di log."""
        self.txt_console.appendPlainText(text)
        self.txt_console.verticalScrollBar().setValue(
            self.txt_console.verticalScrollBar().maximum()
        )

    def load_comuni(self):
        json_path = os.path.join(os.path.dirname(__file__), "comuni.json")
        if os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    self.comuni_map = json.load(f)
            except Exception:
                pass

        comuni_list = sorted(list(self.comuni_map.keys()))
        self.combo_comuni.addItems(comuni_list)

        try:
            case_insensitive = Qt.CaseInsensitive
            match_contains = Qt.MatchContains
        except AttributeError:
            case_insensitive = Qt.CaseSensitivity.CaseInsensitive
            match_contains = Qt.MatchFlag.MatchContains

        completer = QCompleter(comuni_list, self)
        completer.setCaseSensitivity(case_insensitive)
        completer.setFilterMode(match_contains)
        self.combo_comuni.setCompleter(completer)

    def setup_info_tab(self):
        try:
            smooth_t = Qt.SmoothTransformation
        except AttributeError:
            smooth_t = Qt.TransformationMode.SmoothTransformation

        try:
            pointing_cursor = Qt.PointingHandCursor
        except AttributeError:
            pointing_cursor = Qt.CursorShape.PointingHandCursor

        # Logo TAF (grande, prominente)
        t_path = os.path.join(os.path.dirname(__file__), "TAF.png")
        if os.path.exists(t_path):
            pix_t = QPixmap(t_path)
            self.label_logo_taf.setPixmap(pix_t.scaledToHeight(120, smooth_t))

        # Logo SinoCloud (piccolo, cliccabile -> sinocloud.it)
        l_path = os.path.join(os.path.dirname(__file__), "sinocloud-logo_real.png")
        if os.path.exists(l_path):
            pix = QPixmap(l_path)
            self.label_logo.setPixmap(pix.scaledToWidth(70, smooth_t))
            self.label_logo.setCursor(QCursor(pointing_cursor))
            self.label_logo.setToolTip("Visita sinocloud.it")
            self.label_logo.mousePressEvent = self._open_sinocloud

        # Carica i plugin esterni
        icon_dir = os.path.join(os.path.dirname(__file__), "altri_plugin")
        el_path = os.path.join(icon_dir, "elenco.txt")
        if os.path.exists(el_path):
            try:
                with open(el_path, "r", encoding="utf-8") as f:
                    for line in f:
                        url = line.strip()
                        if not url:
                            continue
                        p_name = url.strip("/").split("/")[-1]
                        p_disp = p_name.replace("_", " ").title()
                        self.plugin_urls[p_disp] = url
                        i_path = None
                        for ex in [".png", ".svg", ".jpg"]:
                            if os.path.exists(os.path.join(icon_dir, f"{p_name}{ex}")):
                                i_path = os.path.join(icon_dir, f"{p_name}{ex}")
                                break
                            short = p_name.replace("_plugin", "")
                            if os.path.exists(os.path.join(icon_dir, f"{short}{ex}")):
                                i_path = os.path.join(icon_dir, f"{short}{ex}")
                                break
                        if i_path:
                            self.combo_altri_plugin.addItem(QIcon(i_path), p_disp)
                        else:
                            self.combo_altri_plugin.addItem(p_disp)
            except Exception:
                pass

        self.btn_apri_plugin.clicked.connect(self.apri_link_plugin)

    def setup_fonti_tab(self):
        REGIONI = [
            ("Abruzzo", [("AQ", "L'Aquila"), ("CH", "Chieti"), ("PE", "Pescara"), ("TE", "Teramo")]),
            ("Basilicata", [("MT", "Matera"), ("PZ", "Potenza")]),
            ("Calabria", [("CS", "Cosenza"), ("CZ", "Catanzaro"), ("KR", "Crotone"), ("RC", "Reggio Calabria"), ("VV", "Vibo Valentia")]),
            ("Campania", [("AV", "Avellino"), ("BN", "Benevento"), ("CE", "Caserta"), ("NA", "Napoli"), ("SA", "Salerno")]),
            ("Emilia-Romagna", [("BO", "Bologna"), ("FE", "Ferrara"), ("FC", "Forlì-Cesena"), ("MO", "Modena"), ("PC", "Piacenza"), ("PR", "Parma"), ("RA", "Ravenna"), ("RE", "Reggio Emilia"), ("RN", "Rimini")]),
            ("Friuli-Venezia Giulia", [("GO", "Gorizia"), ("PN", "Pordenone"), ("TS", "Trieste"), ("UD", "Udine")]),
            ("Lazio", [("FR", "Frosinone"), ("LT", "Latina"), ("RI", "Rieti"), ("RM", "Roma"), ("VT", "Viterbo")]),
            ("Liguria", [("GE", "Genova"), ("IM", "Imperia"), ("SP", "La Spezia"), ("SV", "Savona")]),
            ("Lombardia", [("BG", "Bergamo"), ("BS", "Brescia"), ("CO", "Como"), ("CR", "Cremona"), ("LC", "Lecco"), ("LO", "Lodi"), ("MB", "Monza-Brianza"), ("MI", "Milano"), ("MN", "Mantova"), ("PV", "Pavia"), ("SO", "Sondrio"), ("VA", "Varese")]),
            ("Marche", [("AN", "Ancona"), ("AP", "Ascoli Piceno"), ("FM", "Fermo"), ("MC", "Macerata"), ("PU", "Pesaro-Urbino")]),
            ("Molise", [("CB", "Campobasso"), ("IS", "Isernia")]),
            ("Piemonte", [("AL", "Alessandria"), ("AT", "Asti"), ("BI", "Biella"), ("CN", "Cuneo"), ("NO", "Novara"), ("TO", "Torino"), ("VB", "Verbano-Cusio-Ossola"), ("VC", "Vercelli")]),
            ("Puglia", [("BA", "Bari"), ("BT", "Barletta-Andria-Trani"), ("BR", "Brindisi"), ("FG", "Foggia"), ("LE", "Lecce"), ("TA", "Taranto")]),
            ("Sardegna", [("CA", "Cagliari"), ("NU", "Nuoro"), ("OR", "Oristano"), ("SS", "Sassari"), ("SU", "Sud Sardegna")]),
            ("Sicilia", [("AG", "Agrigento"), ("CL", "Caltanissetta"), ("CT", "Catania"), ("EN", "Enna"), ("ME", "Messina"), ("PA", "Palermo"), ("RG", "Ragusa"), ("SR", "Siracusa"), ("TP", "Trapani")]),
            ("Toscana", [("AR", "Arezzo"), ("FI", "Firenze"), ("GR", "Grosseto"), ("LI", "Livorno"), ("LU", "Lucca"), ("MS", "Massa-Carrara"), ("PI", "Pisa"), ("PO", "Prato"), ("PT", "Pistoia"), ("SI", "Siena")]),
            ("Trentino-Alto Adige", [("BZ", "Bolzano"), ("TN", "Trento")]),
            ("Umbria", [("PG", "Perugia"), ("TR", "Terni")]),
            ("Valle d'Aosta", [("AO", "Aosta")]),
            ("Veneto", [("BL", "Belluno"), ("PD", "Padova"), ("RO", "Rovigo"), ("TV", "Treviso"), ("VE", "Venezia"), ("VI", "Vicenza"), ("VR", "Verona")]),
        ]

        BASE = "https://www1.agenziaentrate.gov.it/servizi/TafDis/download.php?tipofile=TAF&iduff="
        SUFFISSI = ["", "1", "2", "3", "4", "5"]

        html = """
        <html>
        <body style="color:#ecf0f1; background-color:#1f271b; font-family:sans-serif;">
        <h2 style="color:#6b8e23;">Fonti Originali - Agenzia delle Entrate</h2>
        <p>Di seguito i link ufficiali per il download diretto dei file TAF (.zip)
        dai server dell'Agenzia delle Entrate, organizzati per regione.</p>
        <p style="font-size:small; color:#a1af91;">
        Ogni provincia può avere fino a 6 uffici: sigla (es. BA), BA1, BA2, ..., BA5.
        </p>
        <hr style="border:1px solid #3f5231;">
        """

        for regione, province in REGIONI:
            html += f'<h3 style="color:#6b8e23; margin-top:16px;">{regione}</h3><ul style="margin:0; padding-left:20px;">'
            for sigla, nome in province:
                links = []
                for s in SUFFISSI:
                    iduff = f"{sigla}{s}"
                    label = f"{sigla}{s}" if s else sigla
                    links.append(f'<a href="{BASE}{iduff}" style="color:#88b04b;">{label}</a>')
                html += f'<li><b>{sigla}</b> - {nome}: {", ".join(links)}</li>'
            html += "</ul>"

        html += """
        <hr style="border:1px solid #3f5231;">
        <p style="font-size:small; color:#a1af91;">
        Fonte: <a href="https://www1.agenziaentrate.gov.it/servizi/TafDis/download.php"
        style="color:#88b04b;">Agenzia delle Entrate - TAF</a> |
        Licenza Open Data CC-BY
        </p>
        </body>
        </html>
        """

        self.txt_fonti.setHtml(html)

    def _open_sinocloud(self, event):
        """Apre il sito sinocloud.it al click sul logo."""
        webbrowser.open("https://sinocloud.it")

    def apri_link_plugin(self):
        selected_plugin = self.combo_altri_plugin.currentText()
        url = self.plugin_urls.get(selected_plugin)
        if url:
            webbrowser.open(url)

    def setup_origini_tab(self):
        # Crea il nuovo widget per il tab
        self.tab_origini = QWidget()
        self.tab_origini.setObjectName("tab_origini")
        layout = QVBoxLayout(self.tab_origini)

        # Etichetta informativa
        info_label = QLabel(
            "<b>Configurazione Piccole Origini (Cassini-Soldner)</b><br>"
            "Inserisci qui i parametri locali (Centri di Emanazione) per i comuni di tuo interesse.<br>"
            "<i>I codici devono essere esatti (es. H501). Il plugin aggiornerà la trasformazione a caldo.</i><br><br>"
            "<span style='color:#e67e22;'><b>⚠️ IMPORTANTE:</b> Le 818 piccole origini non sono censite interamente di default. "
            "Se un comune manca, i suoi punti verranno scaricati grezzi (senza proiezione) per evitarne lo spostamento errato. "
            "Inserisci l'origine qui per abilitare la conversione esatta.</span>"
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #a1af91; font-size: 9pt; margin-bottom: 10px;")
        layout.addWidget(info_label)

        btn_style = "QPushButton { background-color: #3f5231; padding: 6px; border-radius: 3px; font-weight: bold; } QPushButton:hover { background-color: #556b2f; }"

        # Bottoni Import / Export in alto
        btn_layout_top = QHBoxLayout()
        self.btn_export_modello = QPushButton("📥 Scarica Modello Vuoto")
        self.btn_import_file = QPushButton("📤 Importa da File")
        self.btn_export_modello.setStyleSheet(btn_style)
        self.btn_import_file.setStyleSheet(btn_style)
        btn_layout_top.addWidget(self.btn_import_file)
        btn_layout_top.addWidget(self.btn_export_modello)
        btn_layout_top.addStretch()
        layout.addLayout(btn_layout_top)

        # Tabella
        self.table_origini = QTableWidget(0, 6)
        self.table_origini.setHorizontalHeaderLabels(["Cod. Comune", "Nota/Nome", "Latitudine (WGS84)", "Longitudine (WGS84)", "Falso Est (m)", "Falso Nord (m)"])

        try:
            stretch_mode = QHeaderView.Stretch
        except AttributeError:
            stretch_mode = QHeaderView.ResizeMode.Stretch

        self.table_origini.horizontalHeader().setSectionResizeMode(stretch_mode)
        layout.addWidget(self.table_origini)

        # Pulsanti
        btn_layout = QHBoxLayout()
        self.btn_add_orig = QPushButton("➕ Aggiungi Origine")
        self.btn_rem_orig = QPushButton("🗑️ Rimuovi Selezionata")
        self.btn_save_orig = QPushButton("💾 Salva Configurazione")

        # Stile bottoni
        self.btn_add_orig.setStyleSheet(btn_style)
        self.btn_rem_orig.setStyleSheet(btn_style)
        self.btn_save_orig.setStyleSheet("QPushButton { background-color: #6b8e23; padding: 6px; border-radius: 3px; font-weight: bold; color: white;} QPushButton:hover { background-color: #808000; }")

        btn_layout.addWidget(self.btn_add_orig)
        btn_layout.addWidget(self.btn_rem_orig)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_save_orig)
        layout.addLayout(btn_layout)

        # Aggiungi tab
        self.tabWidget.addTab(self.tab_origini, "Origini Locali")

        # Connessioni
        self.btn_export_modello.clicked.connect(self.export_origini_template)
        self.btn_import_file.clicked.connect(self.import_origini_file)
        self.btn_add_orig.clicked.connect(self.add_origine_row_empty)
        self.btn_rem_orig.clicked.connect(self.remove_origine_row)
        self.btn_save_orig.clicked.connect(self.save_origini_table)

        self.load_origini_table()

    def load_origini_table(self):
        json_path = os.path.join(os.path.dirname(__file__), "origini_cassini.json")
        self.table_origini.setRowCount(0)
        if os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    piccole = data.get("piccole_origini", {})
                    for codice, params in piccole.items():
                        self.add_origine_row(codice, params.get("nota", ""), params.get("lat", 0.0), params.get("lon", 0.0), params.get("falso_est", 0), params.get("falso_nord", 0))
            except Exception as e:
                self.append_log(f"Errore caricamento origini JSON: {e}")

    def add_origine_row_empty(self):
        self.add_origine_row("", "", 0.0, 0.0, 0, 0)

    def add_origine_row(self, codice="", nota="", lat=0.0, lon=0.0, fe=0, fn=0):
        row = self.table_origini.rowCount()
        self.table_origini.insertRow(row)
        self.table_origini.setItem(row, 0, QTableWidgetItem(str(codice)))
        self.table_origini.setItem(row, 1, QTableWidgetItem(str(nota)))
        self.table_origini.setItem(row, 2, QTableWidgetItem(str(lat)))
        self.table_origini.setItem(row, 3, QTableWidgetItem(str(lon)))
        self.table_origini.setItem(row, 4, QTableWidgetItem(str(fe)))
        self.table_origini.setItem(row, 5, QTableWidgetItem(str(fn)))

    def remove_origine_row(self):
        current_row = self.table_origini.currentRow()
        if current_row >= 0:
            self.table_origini.removeRow(current_row)

    def save_origini_table(self):
        try:
            from . import taf_core
        except ImportError:
            import taf_core

        json_path = os.path.join(os.path.dirname(__file__), "origini_cassini.json")

        # Legge il file esistente per mantenere le grandi origini
        data = {"grandi_origini": {}, "piccole_origini": {}}
        if os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                pass

        # Ricostruisce le piccole origini dalla tabella
        piccole = {}
        for row in range(self.table_origini.rowCount()):
            item0 = self.table_origini.item(row, 0)
            if not item0:
                continue
            codice = item0.text().strip().upper()
            if not codice:
                continue
            try:
                piccole[codice] = {
                    "nota": self.table_origini.item(row, 1).text().strip() if self.table_origini.item(row, 1) else "",
                    "lat": float(self.table_origini.item(row, 2).text().replace(',','.')),
                    "lon": float(self.table_origini.item(row, 3).text().replace(',','.')),
                    "falso_est": float(self.table_origini.item(row, 4).text().replace(',','.')),
                    "falso_nord": float(self.table_origini.item(row, 5).text().replace(',','.'))
                }
            except (ValueError, AttributeError):
                self.append_log(f"Errore di formato nei numeri per il comune {codice}. Non salvato.")

        data["piccole_origini"] = piccole

        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)

            # Ricarica in memoria su taf_core
            if hasattr(taf_core, 'reload_origini'):
                taf_core.reload_origini()

            self.append_log("Configurazione Origini Cassini-Soldner salvata con successo!")
            QMessageBox.information(self, "Successo", "Origini salvate correttamente. Il plugin è aggiornato e pronto.")
        except Exception as e:
            self.append_log(f"Errore durante il salvataggio: {e}")
            QMessageBox.critical(self, "Errore", f"Impossibile salvare il file JSON:\\n{e}")

    def export_origini_template(self):
        filepath, _ = QFileDialog.getSaveFileName(self, "Salva Modello Origini", os.path.expanduser("~/Scrivania/modello_origini.csv"), "CSV Files (*.csv)")
        if filepath:
            try:
                with open(filepath, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(["Codice_Comune", "Nota_Nome", "Latitudine", "Longitudine", "Falso_Est", "Falso_Nord"])
                    writer.writerow(["H501", "Roma (Esempio)", "41.92439", "12.452333", "0", "0"])
                QMessageBox.information(self, "Successo", f"Modello salvato in:\n{filepath}\n\nCompilalo e ricaricalo tramite 'Importa da File'.")
            except Exception as e:
                QMessageBox.critical(self, "Errore", f"Impossibile salvare il modello:\n{e}")

    def import_origini_file(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "Seleziona File Origini", os.path.expanduser("~"), "CSV/JSON Files (*.csv *.json)")
        if not filepath:
            return

        importati = 0
        try:
            if filepath.endswith('.csv'):
                with open(filepath, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        codice = row.get("Codice_Comune", "").strip()
                        if not codice:
                            continue
                        nota = row.get("Nota_Nome", "")
                        lat = float(row.get("Latitudine", 0))
                        lon = float(row.get("Longitudine", 0))
                        fe = float(row.get("Falso_Est", 0))
                        fn = float(row.get("Falso_Nord", 0))
                        self.add_origine_row(codice, nota, lat, lon, fe, fn)
                        importati += 1
            elif filepath.endswith('.json'):
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    piccole = data.get("piccole_origini", {})
                    for codice, p in piccole.items():
                        self.add_origine_row(codice, p.get("nota",""), p.get("lat",0), p.get("lon",0), p.get("falso_est",0), p.get("falso_nord",0))
                        importati += 1

            if importati > 0:
                QMessageBox.information(self, "Importazione completata", f"Importate {importati} origini nella tabella.\n\nRICORDATI DI CLICCARE SU 'SALVA CONFIGURAZIONE' per renderle effettive.")
            else:
                QMessageBox.warning(self, "Nessun dato", "Il file non conteneva dati validi o aveva un formato non riconosciuto.")
        except Exception as e:
            QMessageBox.critical(self, "Errore di Importazione", f"Errore durante la lettura del file:\n{e}")

