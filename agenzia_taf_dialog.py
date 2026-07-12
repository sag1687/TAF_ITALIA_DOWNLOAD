# -*- coding: utf-8 -*-
"""Main dialog for the TAF Italia QGIS plugin.

IT: finestra principale bilingue (italiano/inglese, selettore con
bandiera) con il tema scuro condiviso della famiglia di plugin
SinoCloud. EN: bilingual main window (Italian/English, flag toggle)
using the shared dark theme of the SinoCloud plugin family.
"""

import os
import json
import csv
import webbrowser

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import (
    QDialog,
    QCompleter,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QPixmap, QCursor, QColor

try:
    from qgis.core import QgsSettings
except ImportError:
    QgsSettings = None

from . import plugin_hub

FORM_CLASS, _ = uic.loadUiType(
    os.path.join(os.path.dirname(__file__), "agenzia_taf_dialog_base.ui")
)

_SETTINGS_BASE = "GeoFusion/TafItalia"


def _t(lang, it, en):
    """Return the Italian or English string based on lang."""
    return en if lang == "en" else it


class AgenziaTafDialog(QDialog, FORM_CLASS):
    def __init__(self, parent=None):
        super(AgenziaTafDialog, self).__init__(parent)
        self.setupUi(self)
        self.comuni_map = {}
        self.lang = self._load_lang()

        self.load_comuni()
        self.setup_lang_toggle()
        self.setup_info_tab()
        self.setup_origini_tab()

        # Checkbox per raw mode e try_convert
        self.chk_raw_mode = QCheckBox()
        self.chk_try_convert = QCheckBox()
        self.chk_try_convert.setChecked(True)
        layout = self.groupBox_search.layout()
        if layout:
            layout.insertWidget(1, self.chk_raw_mode)
            layout.insertWidget(2, self.chk_try_convert)

        self.apply_styles()

        # Setup Mappa Interna
        from qgis.gui import QgsMapCanvas, QgsMapToolPan
        from qgis.core import (
            QgsRasterLayer, QgsRectangle, QgsCoordinateReferenceSystem,
        )

        self.map_canvas = QgsMapCanvas(self.map_container)
        self.map_canvas.setCanvasColor(QColor("#1b2430"))
        self.map_canvas.enableAntiAliasing(True)
        self.verticalLayout_map.addWidget(self.map_canvas)

        # Load OSM layer by default (stored in self to prevent GC)
        osm_url = (
            "type=xyz&url=https://tile.openstreetmap.org/{z}/{x}/{y}.png"
            "&zmax=19&zmin=0&crs=EPSG3857"
        )
        self.osm_layer = QgsRasterLayer(osm_url, "OpenStreetMap", "wms")
        if self.osm_layer.isValid():
            self.map_canvas.setDestinationCrs(
                QgsCoordinateReferenceSystem("EPSG:3857")
            )
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

        self._update_ui_lang()

    # ------------------------------------------------------------------
    # Language
    # ------------------------------------------------------------------

    def _load_lang(self):
        if QgsSettings is not None:
            saved = QgsSettings().value(_SETTINGS_BASE + "/lang", "") or ""
            if saved in ("it", "en"):
                return saved
        return "it"

    def setup_lang_toggle(self):
        """Add the flag language toggle next to the app title."""
        self.btn_lang = QPushButton(plugin_hub.LANG_LABEL_EN)
        self.btn_lang.setObjectName("btnLang")
        self.btn_lang.clicked.connect(self.toggle_lang)
        self.layout_logos.addWidget(self.btn_lang)

    def toggle_lang(self):
        self.lang = "en" if self.lang == "it" else "it"
        if QgsSettings is not None:
            QgsSettings().setValue(_SETTINGS_BASE + "/lang", self.lang)
        self._update_ui_lang()

    def _update_ui_lang(self):
        L = self.lang
        self.btn_lang.setText(plugin_hub.lang_button_label(L))
        self.setWindowTitle(_t(
            L,
            "TAF Italia - Punti Fiduciali Downloader",
            "TAF Italia - Fiducial Points Downloader",
        ))
        self.tabWidget.setTabText(0, _t(L, "Download e Mappa",
                                        "Download and Map"))
        self.tabWidget.setTabText(1, _t(L, "Informazioni e Licenza",
                                        "Information and License"))
        self.tabWidget.setTabText(2, _t(L, "Fonti Originali TAF",
                                        "Original TAF Sources"))
        idx = self.tabWidget.indexOf(self.tab_origini)
        if idx >= 0:
            self.tabWidget.setTabText(idx, _t(L, "Origini Locali",
                                              "Local Origins"))

        self.label_app_title.setText(_t(
            L,
            '<html><head/><body><p align="center">'
            '<span style="font-size:16pt; font-weight:700; '
            'color:#f2f5f8;">TAF Italia</span><br/>'
            '<span style="font-size:9pt; color:#8a97a5;">'
            'Punti Fiduciali Downloader per QGIS</span></p>'
            '</body></html>',
            '<html><head/><body><p align="center">'
            '<span style="font-size:16pt; font-weight:700; '
            'color:#f2f5f8;">TAF Italia</span><br/>'
            '<span style="font-size:9pt; color:#8a97a5;">'
            'Fiducial Points Downloader for QGIS</span></p>'
            '</body></html>',
        ))
        self.groupBox_search.setTitle(_t(
            L, "Ricerca Comune", "Municipality Search"))
        self.btn_scarica.setText(_t(
            L,
            "SCARICA E MOSTRA IN MAPPA (OSM)",
            "DOWNLOAD AND SHOW ON MAP (OSM)",
        ))
        self.groupBox_log.setTitle(_t(L, "Log Attività", "Activity Log"))
        self._update_toggle_log_text()

        self.chk_raw_mode.setText(_t(
            L,
            "Scarica TAF Grezzi originali (No trasformazione WGS84)",
            "Download original raw TAF (no WGS84 transformation)",
        ))
        self.chk_try_convert.setText(_t(
            L,
            "Prova conversione WGS84 (usa Grande Origine se manca "
            "Piccola Origine)",
            "Try WGS84 conversion (use the Great Origin when the "
            "Small Origin is missing)",
        ))

        self.groupBox_info.setTitle(_t(
            L, "Info, Disclaimer & Avvertenze",
            "Info, Disclaimer & Warnings"))
        self.label_format_info.setText(_t(
            L,
            "<html><head/><body><p><b>📄 Formato Output:</b> I dati "
            "vengono scaricati e convertiti in formato <b>CSV/GPKG</b> "
            "con coordinate <b>WGS84 (EPSG:4326)</b>, caricati "
            "automaticamente come layer in QGIS.</p></body></html>",
            "<html><head/><body><p><b>📄 Output format:</b> data is "
            "downloaded and converted to <b>CSV/GPKG</b> with "
            "<b>WGS84 (EPSG:4326)</b> coordinates, automatically "
            "loaded as a layer in QGIS.</p></body></html>",
        ))
        self.label_disclaimer_outlier.setText(_t(
            L, _OUTLIER_HTML_IT, _OUTLIER_HTML_EN))
        self.label_disclaimer.setText(_t(
            L,
            "<html><head/><body><p align=\"justify\"><b>[ITA]</b> I "
            "dati scaricati tramite TAF Italia provengono direttamente "
            "dai server ufficiali dell'<b>Agenzia delle Entrate</b>."
            "</p></body></html>",
            "<html><head/><body><p align=\"justify\"><b>[ENG]</b> the "
            "data downloaded through TAF Italia comes directly from "
            "the official servers of the <b>Italian Revenue Agency</b>."
            "</p></body></html>",
        ))
        self.label_author.setText(
            '<html><head/><body><p align="center">'
            "<b>Sviluppo / Development:</b> Dott. Sarino Alfonso "
            "Grande | <b>Email:</b> sino.grande@gmail.com | "
            '<b>Web:</b> <a href="https://sinocloud.it">sinocloud.it'
            "</a></p></body></html>"
        )
        self.btn_apri_plugin.setText(_t(
            L, "Apri Repository GitHub", "Open GitHub Repository"))
        self.lbl_altri_plugin.setText(_t(
            L,
            "<b>Altri plugin dell'autore:</b> seleziona un plugin dal "
            "menù a tendina e apri il suo repository.",
            "<b>More plugins by the author:</b> pick a plugin from "
            "the drop-down and open its repository.",
        ))
        self._refresh_plugin_combo()

        self.setup_fonti_tab()
        self._retranslate_origini()

    def _update_toggle_log_text(self):
        if self.groupBox_log.isVisible():
            self.btn_toggle_log.setText(_t(
                self.lang,
                "🔼 Nascondi Console di Log",
                "🔼 Hide Log Console",
            ))
        else:
            self.btn_toggle_log.setText(_t(
                self.lang,
                "🔽 Mostra Console di Log",
                "🔽 Show Log Console",
            ))

    def toggle_log(self):
        self.groupBox_log.setVisible(not self.groupBox_log.isVisible())
        self._update_toggle_log_text()
        self.adjustSize()

    # ------------------------------------------------------------------
    # Style
    # ------------------------------------------------------------------

    def apply_styles(self):
        """Shared SinoCloud family dark theme + TAF tweaks."""
        self.setStyleSheet(plugin_hub.FAMILY_STYLE + """
        QPushButton#btn_scarica {
            font-size: 14px;
            padding: 10px;
        }
        QPushButton#btn_toggle_log {
            background: transparent;
            color: #5b9bd5;
            border: none;
            text-align: left;
            font-weight: bold;
            padding: 5px;
        }
        QPushButton#btn_toggle_log:hover {
            color: #8ab4e0;
            text-decoration: underline;
        }
        QPlainTextEdit#txt_console {
            background-color: #10151c;
            color: #5b9bd5;
            font-family: Consolas, monospace;
        }
        QWidget#map_container {
            border: 2px solid #2c3a48;
            border-radius: 4px;
            background-color: #1b2430;
        }
        QTableWidget {
            gridline-color: #2c3a48;
        }
        QTableWidget::item:selected {
            background-color: #2c4f70;
        }
        """)

    # ------------------------------------------------------------------
    # Log & data helpers
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Info tab
    # ------------------------------------------------------------------

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
            self.label_logo_taf.setPixmap(
                pix_t.scaledToHeight(120, smooth_t))

        # Logo SinoCloud (piccolo, cliccabile -> sinocloud.it)
        l_path = os.path.join(
            os.path.dirname(__file__), "sinocloud-logo_real.png")
        if os.path.exists(l_path):
            pix = QPixmap(l_path)
            self.label_logo.setPixmap(pix.scaledToWidth(70, smooth_t))
            self.label_logo.setCursor(QCursor(pointing_cursor))
            self.label_logo.setToolTip("Visita sinocloud.it")
            self.label_logo.mousePressEvent = self._open_sinocloud

        # Menù a tendina con gli altri plugin della famiglia (repo
        # GitHub dal catalogo condiviso plugin_hub, TAF escluso).
        self.lbl_altri_plugin = QLabel()
        self.lbl_altri_plugin.setWordWrap(True)
        info_layout = self.groupBox_info.layout()
        if info_layout is not None:
            info_layout.insertWidget(
                info_layout.count() - 1, self.lbl_altri_plugin)

        self._refresh_plugin_combo()
        self.btn_apri_plugin.clicked.connect(self.apri_link_plugin)

    def _refresh_plugin_combo(self):
        current = self.combo_altri_plugin.currentData()
        self.combo_altri_plugin.blockSignals(True)
        self.combo_altri_plugin.clear()
        for entry in plugin_hub.other_plugins("taf_italia"):
            desc = entry["en"] if self.lang == "en" else entry["it"]
            self.combo_altri_plugin.addItem(entry["name"], entry["repo"])
            self.combo_altri_plugin.setItemData(
                self.combo_altri_plugin.count() - 1, desc,
                Qt.ItemDataRole.ToolTipRole
                if hasattr(Qt, "ItemDataRole") else Qt.ToolTipRole,
            )
        if current is not None:
            idx = self.combo_altri_plugin.findData(current)
            if idx >= 0:
                self.combo_altri_plugin.setCurrentIndex(idx)
        self.combo_altri_plugin.blockSignals(False)

    def apri_link_plugin(self):
        url = self.combo_altri_plugin.currentData()
        if url:
            webbrowser.open(url)

    def _open_sinocloud(self, event):
        """Apre il sito sinocloud.it al click sul logo."""
        webbrowser.open("https://sinocloud.it")

    # ------------------------------------------------------------------
    # Fonti tab
    # ------------------------------------------------------------------

    def setup_fonti_tab(self):
        regioni = _REGIONI
        base = (
            "https://www1.agenziaentrate.gov.it/servizi/TafDis/"
            "download.php?tipofile=TAF&iduff="
        )
        suffissi = ["", "1", "2", "3", "4", "5"]
        L = self.lang

        html = """
        <html>
        <body style="color:#f2f5f8; background-color:#141a22;
                     font-family:sans-serif;">
        """
        html += _t(
            L,
            '<h2 style="color:#5b9bd5;">Fonti Originali - Agenzia '
            "delle Entrate</h2>"
            "<p>Di seguito i link ufficiali per il download diretto "
            "dei file TAF (.zip) dai server dell'Agenzia delle "
            "Entrate, organizzati per regione.</p>"
            '<p style="font-size:small; color:#8a97a5;">Ogni provincia '
            "può avere fino a 6 uffici: sigla (es. BA), BA1, BA2, ..., "
            "BA5.</p>",
            '<h2 style="color:#5b9bd5;">Original Sources - Italian '
            "Revenue Agency</h2>"
            "<p>Below are the official links for the direct download "
            "of the TAF (.zip) files from the Italian Revenue Agency "
            "servers, grouped by region.</p>"
            '<p style="font-size:small; color:#8a97a5;">Each province '
            "can have up to 6 offices: code (e.g. BA), BA1, BA2, ..., "
            "BA5.</p>",
        )
        html += '<hr style="border:1px solid #2c3a48;">'

        for regione, province in regioni:
            html += (
                f'<h3 style="color:#5b9bd5; margin-top:16px;">{regione}'
                '</h3><ul style="margin:0; padding-left:20px;">'
            )
            for sigla, nome in province:
                links = []
                for s in suffissi:
                    iduff = f"{sigla}{s}"
                    label = f"{sigla}{s}" if s else sigla
                    links.append(
                        f'<a href="{base}{iduff}" '
                        f'style="color:#8ab4e0;">{label}</a>'
                    )
                html += (
                    f"<li><b>{sigla}</b> - {nome}: "
                    f'{", ".join(links)}</li>'
                )
            html += "</ul>"

        html += '<hr style="border:1px solid #2c3a48;">'
        html += _t(
            L,
            '<p style="font-size:small; color:#8a97a5;">Fonte: '
            '<a href="https://www1.agenziaentrate.gov.it/servizi/'
            'TafDis/download.php" style="color:#8ab4e0;">Agenzia '
            "delle Entrate - TAF</a> | Licenza Open Data CC-BY</p>",
            '<p style="font-size:small; color:#8a97a5;">Source: '
            '<a href="https://www1.agenziaentrate.gov.it/servizi/'
            'TafDis/download.php" style="color:#8ab4e0;">Italian '
            "Revenue Agency - TAF</a> | Open Data CC-BY license</p>",
        )
        html += "</body></html>"

        self.txt_fonti.setHtml(html)

    # ------------------------------------------------------------------
    # Origini tab
    # ------------------------------------------------------------------

    def setup_origini_tab(self):
        # Crea il nuovo widget per il tab
        self.tab_origini = QWidget()
        self.tab_origini.setObjectName("tab_origini")
        layout = QVBoxLayout(self.tab_origini)

        # Etichetta informativa
        self.origini_info_label = QLabel()
        self.origini_info_label.setWordWrap(True)
        self.origini_info_label.setStyleSheet(
            "color: #8a97a5; font-size: 9pt; margin-bottom: 10px;")
        layout.addWidget(self.origini_info_label)

        # Bottoni Import / Export in alto
        btn_layout_top = QHBoxLayout()
        self.btn_export_modello = QPushButton()
        self.btn_import_file = QPushButton()
        btn_layout_top.addWidget(self.btn_import_file)
        btn_layout_top.addWidget(self.btn_export_modello)
        btn_layout_top.addStretch()
        layout.addLayout(btn_layout_top)

        # Tabella
        self.table_origini = QTableWidget(0, 6)

        try:
            stretch_mode = QHeaderView.Stretch
        except AttributeError:
            stretch_mode = QHeaderView.ResizeMode.Stretch

        self.table_origini.horizontalHeader().setSectionResizeMode(
            stretch_mode)
        layout.addWidget(self.table_origini)

        # Pulsanti
        btn_layout = QHBoxLayout()
        self.btn_add_orig = QPushButton()
        self.btn_rem_orig = QPushButton()
        self.btn_save_orig = QPushButton()

        btn_layout.addWidget(self.btn_add_orig)
        btn_layout.addWidget(self.btn_rem_orig)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_save_orig)
        layout.addLayout(btn_layout)

        # Aggiungi tab
        self.tabWidget.addTab(self.tab_origini, "Origini Locali")

        # Connessioni
        self.btn_export_modello.clicked.connect(
            self.export_origini_template)
        self.btn_import_file.clicked.connect(self.import_origini_file)
        self.btn_add_orig.clicked.connect(self.add_origine_row_empty)
        self.btn_rem_orig.clicked.connect(self.remove_origine_row)
        self.btn_save_orig.clicked.connect(self.save_origini_table)

        self._retranslate_origini()
        self.load_origini_table()

    def _retranslate_origini(self):
        if not hasattr(self, "origini_info_label"):
            return
        L = self.lang
        self.origini_info_label.setText(_t(
            L,
            "<b>Configurazione Piccole Origini (Cassini-Soldner)</b>"
            "<br>Inserisci qui i parametri locali (Centri di "
            "Emanazione) per i comuni di tuo interesse.<br><i>I codici "
            "devono essere esatti (es. H501). Il plugin aggiornerà la "
            "trasformazione a caldo.</i><br><br>"
            "<span style='color:#f59e0b;'><b>⚠️ IMPORTANTE:</b> le 818 "
            "piccole origini non sono censite interamente di default. "
            "Se un comune manca, i suoi punti verranno scaricati "
            "grezzi (senza proiezione) per evitarne lo spostamento "
            "errato. Inserisci l'origine qui per abilitare la "
            "conversione esatta.</span>",
            "<b>Small Origins configuration (Cassini-Soldner)</b><br>"
            "Enter here the local parameters (origin centres) for the "
            "municipalities you care about.<br><i>Codes must be exact "
            "(e.g. H501). The plugin hot-reloads the transformation."
            "</i><br><br>"
            "<span style='color:#f59e0b;'><b>⚠️ IMPORTANT:</b> the 818 "
            "small origins are not fully catalogued by default. If a "
            "municipality is missing, its points are downloaded raw "
            "(no projection) to avoid moving them wrongly. Enter the "
            "origin here to enable the exact conversion.</span>",
        ))
        self.btn_export_modello.setText(_t(
            L, "📥 Scarica Modello Vuoto", "📥 Download Empty Template"))
        self.btn_import_file.setText(_t(
            L, "📤 Importa da File", "📤 Import from File"))
        self.btn_add_orig.setText(_t(
            L, "➕ Aggiungi Origine", "➕ Add Origin"))
        self.btn_rem_orig.setText(_t(
            L, "🗑️ Rimuovi Selezionata", "🗑️ Remove Selected"))
        self.btn_save_orig.setText(_t(
            L, "💾 Salva Configurazione", "💾 Save Configuration"))
        self.table_origini.setHorizontalHeaderLabels([
            _t(L, "Cod. Comune", "Municipality Code"),
            _t(L, "Nota/Nome", "Note/Name"),
            _t(L, "Latitudine (WGS84)", "Latitude (WGS84)"),
            _t(L, "Longitudine (WGS84)", "Longitude (WGS84)"),
            _t(L, "Falso Est (m)", "False Easting (m)"),
            _t(L, "Falso Nord (m)", "False Northing (m)"),
        ])

    def load_origini_table(self):
        json_path = os.path.join(
            os.path.dirname(__file__), "origini_cassini.json")
        self.table_origini.setRowCount(0)
        if os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    piccole = data.get("piccole_origini", {})
                    for codice, params in piccole.items():
                        self.add_origine_row(
                            codice,
                            params.get("nota", ""),
                            params.get("lat", 0.0),
                            params.get("lon", 0.0),
                            params.get("falso_est", 0),
                            params.get("falso_nord", 0),
                        )
            except Exception as e:
                self.append_log(_t(
                    self.lang,
                    f"Errore caricamento origini JSON: {e}",
                    f"Error loading origins JSON: {e}",
                ))

    def add_origine_row_empty(self):
        self.add_origine_row("", "", 0.0, 0.0, 0, 0)

    def add_origine_row(self, codice="", nota="", lat=0.0, lon=0.0,
                        fe=0, fn=0):
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

        json_path = os.path.join(
            os.path.dirname(__file__), "origini_cassini.json")

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

            def _cell(col):
                item = self.table_origini.item(row, col)
                return item.text().replace(",", ".") if item else ""

            try:
                piccole[codice] = {
                    "nota": (
                        self.table_origini.item(row, 1).text().strip()
                        if self.table_origini.item(row, 1) else ""
                    ),
                    "lat": float(_cell(2)),
                    "lon": float(_cell(3)),
                    "falso_est": float(_cell(4)),
                    "falso_nord": float(_cell(5)),
                }
            except (ValueError, AttributeError):
                self.append_log(_t(
                    self.lang,
                    f"Errore di formato nei numeri per il comune "
                    f"{codice}. Non salvato.",
                    f"Number format error for municipality {codice}. "
                    f"Not saved.",
                ))

        data["piccole_origini"] = piccole

        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)

            # Ricarica in memoria su taf_core
            if hasattr(taf_core, "reload_origini"):
                taf_core.reload_origini()

            self.append_log(_t(
                self.lang,
                "Configurazione Origini Cassini-Soldner salvata con "
                "successo!",
                "Cassini-Soldner origins configuration saved "
                "successfully!",
            ))
            QMessageBox.information(
                self,
                _t(self.lang, "Successo", "Success"),
                _t(self.lang,
                   "Origini salvate correttamente. Il plugin è "
                   "aggiornato e pronto.",
                   "Origins saved correctly. The plugin is updated "
                   "and ready."),
            )
        except Exception as e:
            self.append_log(_t(
                self.lang,
                f"Errore durante il salvataggio: {e}",
                f"Error while saving: {e}",
            ))
            QMessageBox.critical(
                self,
                _t(self.lang, "Errore", "Error"),
                _t(self.lang,
                   f"Impossibile salvare il file JSON:\n{e}",
                   f"Unable to save the JSON file:\n{e}"),
            )

    def export_origini_template(self):
        filepath, _f = QFileDialog.getSaveFileName(
            self,
            _t(self.lang, "Salva Modello Origini",
               "Save Origins Template"),
            os.path.expanduser("~/modello_origini.csv"),
            "CSV Files (*.csv)",
        )
        if filepath:
            try:
                with open(filepath, "w", newline="",
                          encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        "Codice_Comune", "Nota_Nome", "Latitudine",
                        "Longitudine", "Falso_Est", "Falso_Nord",
                    ])
                    writer.writerow([
                        "H501", "Roma (Esempio)", "41.92439",
                        "12.452333", "0", "0",
                    ])
                QMessageBox.information(
                    self,
                    _t(self.lang, "Successo", "Success"),
                    _t(self.lang,
                       f"Modello salvato in:\n{filepath}\n\nCompilalo "
                       "e ricaricalo tramite 'Importa da File'.",
                       f"Template saved to:\n{filepath}\n\nFill it in "
                       "and load it back through 'Import from File'."),
                )
            except Exception as e:
                QMessageBox.critical(
                    self,
                    _t(self.lang, "Errore", "Error"),
                    _t(self.lang,
                       f"Impossibile salvare il modello:\n{e}",
                       f"Unable to save the template:\n{e}"),
                )

    def import_origini_file(self):
        filepath, _f = QFileDialog.getOpenFileName(
            self,
            _t(self.lang, "Seleziona File Origini",
               "Select Origins File"),
            os.path.expanduser("~"),
            "CSV/JSON Files (*.csv *.json)",
        )
        if not filepath:
            return

        importati = 0
        try:
            if filepath.endswith(".csv"):
                with open(filepath, "r", encoding="utf-8") as f:
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
                        self.add_origine_row(codice, nota, lat, lon,
                                             fe, fn)
                        importati += 1
            elif filepath.endswith(".json"):
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    piccole = data.get("piccole_origini", {})
                    for codice, p in piccole.items():
                        self.add_origine_row(
                            codice, p.get("nota", ""), p.get("lat", 0),
                            p.get("lon", 0), p.get("falso_est", 0),
                            p.get("falso_nord", 0),
                        )
                        importati += 1

            if importati > 0:
                QMessageBox.information(
                    self,
                    _t(self.lang, "Importazione completata",
                       "Import complete"),
                    _t(self.lang,
                       f"Importate {importati} origini nella tabella."
                       "\n\nRICORDATI DI CLICCARE SU 'SALVA "
                       "CONFIGURAZIONE' per renderle effettive.",
                       f"Imported {importati} origins into the table."
                       "\n\nREMEMBER TO CLICK 'SAVE CONFIGURATION' to "
                       "make them effective."),
                )
            else:
                QMessageBox.warning(
                    self,
                    _t(self.lang, "Nessun dato", "No data"),
                    _t(self.lang,
                       "Il file non conteneva dati validi o aveva un "
                       "formato non riconosciuto.",
                       "The file contained no valid data or had an "
                       "unrecognized format."),
                )
        except Exception as e:
            QMessageBox.critical(
                self,
                _t(self.lang, "Errore di Importazione", "Import Error"),
                _t(self.lang,
                   f"Errore durante la lettura del file:\n{e}",
                   f"Error while reading the file:\n{e}"),
            )


# ---------------------------------------------------------------------
# Static data & long HTML blocks
# ---------------------------------------------------------------------

_REGIONI = [
    ("Abruzzo", [("AQ", "L'Aquila"), ("CH", "Chieti"),
                 ("PE", "Pescara"), ("TE", "Teramo")]),
    ("Basilicata", [("MT", "Matera"), ("PZ", "Potenza")]),
    ("Calabria", [("CS", "Cosenza"), ("CZ", "Catanzaro"),
                  ("KR", "Crotone"), ("RC", "Reggio Calabria"),
                  ("VV", "Vibo Valentia")]),
    ("Campania", [("AV", "Avellino"), ("BN", "Benevento"),
                  ("CE", "Caserta"), ("NA", "Napoli"),
                  ("SA", "Salerno")]),
    ("Emilia-Romagna", [("BO", "Bologna"), ("FE", "Ferrara"),
                        ("FC", "Forlì-Cesena"), ("MO", "Modena"),
                        ("PC", "Piacenza"), ("PR", "Parma"),
                        ("RA", "Ravenna"), ("RE", "Reggio Emilia"),
                        ("RN", "Rimini")]),
    ("Friuli-Venezia Giulia", [("GO", "Gorizia"), ("PN", "Pordenone"),
                               ("TS", "Trieste"), ("UD", "Udine")]),
    ("Lazio", [("FR", "Frosinone"), ("LT", "Latina"), ("RI", "Rieti"),
               ("RM", "Roma"), ("VT", "Viterbo")]),
    ("Liguria", [("GE", "Genova"), ("IM", "Imperia"),
                 ("SP", "La Spezia"), ("SV", "Savona")]),
    ("Lombardia", [("BG", "Bergamo"), ("BS", "Brescia"),
                   ("CO", "Como"), ("CR", "Cremona"), ("LC", "Lecco"),
                   ("LO", "Lodi"), ("MB", "Monza-Brianza"),
                   ("MI", "Milano"), ("MN", "Mantova"), ("PV", "Pavia"),
                   ("SO", "Sondrio"), ("VA", "Varese")]),
    ("Marche", [("AN", "Ancona"), ("AP", "Ascoli Piceno"),
                ("FM", "Fermo"), ("MC", "Macerata"),
                ("PU", "Pesaro-Urbino")]),
    ("Molise", [("CB", "Campobasso"), ("IS", "Isernia")]),
    ("Piemonte", [("AL", "Alessandria"), ("AT", "Asti"),
                  ("BI", "Biella"), ("CN", "Cuneo"), ("NO", "Novara"),
                  ("TO", "Torino"), ("VB", "Verbano-Cusio-Ossola"),
                  ("VC", "Vercelli")]),
    ("Puglia", [("BA", "Bari"), ("BT", "Barletta-Andria-Trani"),
                ("BR", "Brindisi"), ("FG", "Foggia"), ("LE", "Lecce"),
                ("TA", "Taranto")]),
    ("Sardegna", [("CA", "Cagliari"), ("NU", "Nuoro"),
                  ("OR", "Oristano"), ("SS", "Sassari"),
                  ("SU", "Sud Sardegna")]),
    ("Sicilia", [("AG", "Agrigento"), ("CL", "Caltanissetta"),
                 ("CT", "Catania"), ("EN", "Enna"), ("ME", "Messina"),
                 ("PA", "Palermo"), ("RG", "Ragusa"),
                 ("SR", "Siracusa"), ("TP", "Trapani")]),
    ("Toscana", [("AR", "Arezzo"), ("FI", "Firenze"),
                 ("GR", "Grosseto"), ("LI", "Livorno"), ("LU", "Lucca"),
                 ("MS", "Massa-Carrara"), ("PI", "Pisa"),
                 ("PO", "Prato"), ("PT", "Pistoia"), ("SI", "Siena")]),
    ("Trentino-Alto Adige", [("BZ", "Bolzano"), ("TN", "Trento")]),
    ("Umbria", [("PG", "Perugia"), ("TR", "Terni")]),
    ("Valle d'Aosta", [("AO", "Aosta")]),
    ("Veneto", [("BL", "Belluno"), ("PD", "Padova"), ("RO", "Rovigo"),
                ("TV", "Treviso"), ("VE", "Venezia"), ("VI", "Vicenza"),
                ("VR", "Verona")]),
]

_OUTLIER_HTML_IT = """<html><head/><body>
<p style="color:#f59e0b;"><b>Avvertenza Tecnica - Sistemi di
Riferimento:</b></p>
<p style="color:#f2f5f8; font-size:9pt;">
Il plugin determina automaticamente il sistema di riferimento
originale dal valore della coordinata Est presente nel file TAF:
</p>
<ul style="color:#c3ccd6; font-size:9pt; margin-left:10px;">
<li><b>1.300.000 &lt; Est &lt; 1.900.000</b> = Gauss-Boaga Fuso Ovest
(EPSG:3003), trasformato in WGS84.</li>
<li><b>2.300.000 &lt; Est &lt; 2.900.000</b> = Gauss-Boaga Fuso Est
(EPSG:3004), trasformato in WGS84.</li>
<li><b>|Est| &lt; 500.000</b> = Cassini-Soldner, trasformato in WGS84
con origine catastale locale.</li>
</ul>
<p style="color:#f59e0b; font-size:9pt;">
<b>Nota sulle Origini Catastali:</b> il Catasto italiano storico usa
il sistema Cassini-Soldner con origini specifiche per ogni comune
catastale. Per ragioni pratiche, il plugin adotta il modello delle 31
Grandi Origini nazionali, che raggruppano pi&ugrave; province sotto
un'unica origine approssimata. Per comuni lontani dall'origine
"grande" assegnata, lo scostamento pu&ograve; raggiungere decine di
metri. Per precisione millimetrica servono le coordinate esatte
dell'origine d'impianto del singolo comune. Si raccomanda verifica
visiva dei punti prima dell'uso professionale.
</p>
<p style="color:#f59e0b; font-size:9pt;">
I dati potrebbero inoltre contenere <b>punti outlier</b> (coordinate
anomale) generati da errori intrinseci nella trasformazione
matematica dai sistemi di riferimento storici.
</p>
</body></html>"""

_OUTLIER_HTML_EN = """<html><head/><body>
<p style="color:#f59e0b;"><b>Technical Warning - Reference
Systems:</b></p>
<p style="color:#f2f5f8; font-size:9pt;">
The plugin automatically detects the original reference system from
the Easting value found in the TAF file:
</p>
<ul style="color:#c3ccd6; font-size:9pt; margin-left:10px;">
<li><b>1,300,000 &lt; East &lt; 1,900,000</b> = Gauss-Boaga West zone
(EPSG:3003), transformed to WGS84.</li>
<li><b>2,300,000 &lt; East &lt; 2,900,000</b> = Gauss-Boaga East zone
(EPSG:3004), transformed to WGS84.</li>
<li><b>|East| &lt; 500,000</b> = Cassini-Soldner, transformed to
WGS84 with the local cadastral origin.</li>
</ul>
<p style="color:#f59e0b; font-size:9pt;">
<b>Note on cadastral origins:</b> the historical Italian cadastre
uses the Cassini-Soldner system with specific origins for every
cadastral municipality. For practical reasons the plugin adopts the
model of the 31 national Great Origins, which group several provinces
under a single approximated origin. For municipalities far from their
assigned "great" origin the offset can reach tens of metres.
Millimetre precision requires the exact coordinates of the original
origin of the single municipality. Visual verification of the points
is recommended before professional use.
</p>
<p style="color:#f59e0b; font-size:9pt;">
The data may also contain <b>outlier points</b> (anomalous
coordinates) produced by intrinsic errors in the mathematical
transformation from the historical reference systems.
</p>
</body></html>"""
