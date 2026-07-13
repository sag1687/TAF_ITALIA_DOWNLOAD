# -*- coding: utf-8 -*-

import os
import traceback
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.core import (
    QgsApplication,
    QgsProject,
    QgsVectorLayer,
    QgsTask,
    QgsMessageLog,
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsRectangle,
    QgsMarkerSymbol,
    QgsSingleSymbolRenderer,
    QgsPalLayerSettings,
    QgsVectorLayerSimpleLabeling,
    QgsTextFormat,
    QgsAction,
)

# Gestione compatibilità QAction (QGIS 3: QtWidgets, QGIS 4: QtGui)
try:
    from qgis.PyQt.QtGui import QAction
except ImportError:
    from qgis.PyQt.QtWidgets import QAction

from .agenzia_taf_dialog import AgenziaTafDialog


class DownloadTafTask(QgsTask):
    """Task asincrono per il download e la conversione dei dati TAF.

    Usa self.setProgress() (nativo di QgsTask) per il progresso e raccoglie
    i messaggi di log in una lista, scritti nella UI dal main thread.
    """

    def __init__(
        self,
        sigla,
        nome_prov,
        download_dir,
        description,
        raw_mode=False,
        try_convert=False,
    ):
        super().__init__(description, QgsTask.CanCancel)
        self.sigla = sigla
        self.nome_prov = nome_prov
        self.download_dir = download_dir
        self.raw_mode = raw_mode
        self.try_convert = try_convert
        self.exception = None
        self.generated_files = []
        # Lista per raccogliere i messaggi di log dal worker thread
        self.log_messages = []

    def run(self):
        """Eseguito in un thread separato dal QgsTaskManager."""
        try:
            # Import DENTRO il try per catturare eventuali errori di dipendenze
            from .taf_core import download_and_convert_province

            def local_progress(val, text):
                """Callback invocata da taf_core per comunicare il
                progresso."""
                self.setProgress(float(val))
                if text:
                    self.log_messages.append(text)

            self.generated_files = download_and_convert_province(
                self.sigla,
                self.nome_prov,
                self.download_dir,
                local_progress,
                self.raw_mode,
                self.try_convert,
            )
            return True
        except Exception as e:
            self.exception = e
            self.log_messages.append(f"ERRORE CRITICO: {str(e)}")
            QgsMessageLog.logMessage(
                f"TAF Task crash:\n{traceback.format_exc()}",
                "TAF Italia",
                level=Qgis.Critical,
            )
            return False

    def finished(self, result):
        """Eseguito nel MAIN thread dopo che run() è terminato.
        Qui è sicuro interagire con la UI di QGIS."""
        if result:
            loaded = 0
            for filepath in self.generated_files:
                if not os.path.exists(filepath):
                    continue

                base_name = os.path.basename(filepath)
                layer_name = os.path.splitext(base_name)[0]

                if filepath.endswith(".gpkg"):
                    # Carica GeoPackage
                    layer = QgsVectorLayer(filepath, layer_name, "ogr")
                elif filepath.endswith(".csv"):
                    # Carica CSV come layer di testo delimitato con coordinate
                    if getattr(self, "raw_mode", False):
                        uri = (
                            f"file:///{filepath}?delimiter=,&"
                            f"xField=Coord_Est_X&yField=Coord_Nord_Y&"
                            f"crs=EPSG:3003"
                        )
                    else:
                        uri = (
                            f"file:///{filepath}?delimiter=,&"
                            f"xField=Lon_WGS84&yField=Lat_WGS84&crs=EPSG:4326"
                        )
                    layer = QgsVectorLayer(uri, layer_name, "delimitedtext")
                else:
                    continue

                if layer.isValid():
                    QgsProject.instance().addMapLayer(layer)

                    # 1. Stile (Marker Triangolare Verde)
                    symbol = QgsMarkerSymbol.createSimple(
                        {
                            "name": "triangle",
                            "color": "#88b04b",
                            "outline_color": "black",
                            "size": "3",
                        }
                    )
                    layer.setRenderer(QgsSingleSymbolRenderer(symbol))
                    # 2. Labeling (PFXX/FGYY/COMZZZ)
                    label_settings = QgsPalLayerSettings()
                    label_settings.fieldName = (
                        "concat('PF', \"PF_ID\", '/FG', \"Foglio\", '/COM', "
                        "\"Codice_Comune\")")
                    label_settings.isExpression = True
                    try:
                        # QGIS 4.0+
                        label_settings.placement = (
                            Qgis.LabelPlacement.OverPoint
                        )
                        label_settings.quadOffset = (
                            Qgis.LabelQuadrantPosition.AboveRight
                        )
                    except AttributeError:
                        try:
                            label_settings.placement = (
                                QgsPalLayerSettings.Placement.OverPoint
                            )
                            label_settings.quadOffset = (
                                QgsPalLayerSettings.Quadrant.QuadrantAboveRight
                            )
                        except AttributeError:
                            try:
                                label_settings.placement = (
                                    QgsPalLayerSettings
                                    .LabelPlacement.OverPoint
                                )
                                label_settings.quadOffset = (
                                    QgsPalLayerSettings
                                    .QuadrantPosition.QuadrantAboveRight
                                )
                            except AttributeError:
                                label_settings.placement = (
                                    QgsPalLayerSettings.OverPoint
                                )
                                label_settings.quadOffset = (
                                    QgsPalLayerSettings.QuadrantAboveRight
                                )
                    label_settings.xOffset = 1
                    label_settings.yOffset = 1
                    text_format = QgsTextFormat()
                    text_format.setFont("Arial")
                    text_format.setSize(8)
                    label_settings.setFormat(text_format)
                    labeling = QgsVectorLayerSimpleLabeling(label_settings)
                    layer.setLabelsEnabled(True)
                    layer.setLabeling(labeling)
                    # 3. Action Monografia
                    action = QgsAction(
                        QgsAction.OpenUrl,
                        "Apri Monografia PF",
                        "[%Link_Monografia%]",
                        "",
                        False,
                        "Apri Monografia ufficiale dell'Agenzia delle Entrate",
                    )
                    action.setActionScopes({"Feature", "Canvas"})
                    layer.actions().addAction(action)
                    layer.triggerRepaint()

                    loaded += 1
                    QgsMessageLog.logMessage(
                        f"Layer caricato: {layer_name}",
                        "TAF Italia",
                        level=Qgis.Success,
                    )
                else:
                    QgsMessageLog.logMessage(
                        f"Layer non valido: {filepath}",
                        "TAF Italia",
                        level=Qgis.Warning,
                    )

            QgsMessageLog.logMessage(
                f"TAF {self.sigla}: {loaded} layer caricati su "
                f"{len(self.generated_files)} file generati.",
                "TAF Italia",
                level=Qgis.Success,
            )
        else:
            QgsMessageLog.logMessage(
                f"Errore TAF {self.sigla}: {self.exception}",
                "TAF Italia",
                level=Qgis.Critical,
            )


class AgenziaTafPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.actions = []
        self.menu = "&TAF Italia"
        self.dlg = None
        self.active_tasks = []

    def add_action(
        self,
        icon_path,
        text,
        callback,
        enabled_flag=True,
        add_to_menu=True,
        add_to_toolbar=True,
        status_tip=None,
    ):
        icon = QIcon(icon_path)
        action = QAction(icon, text, self.iface.mainWindow())
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)
        if status_tip:
            action.setStatusTip(status_tip)
        if add_to_toolbar:
            self.iface.addToolBarIcon(action)
        if add_to_menu:
            self.iface.addPluginToVectorMenu(self.menu, action)
        self.actions.append(action)
        return action

    def initGui(self):
        icon_path = os.path.join(self.plugin_dir, "icon.png")
        self.add_action(
            icon_path,
            text="TAF Italia - Scarica Punti Fiduciali",
            callback=self.run,
        )

    def unload(self):
        for action in self.actions:
            self.iface.removePluginVectorMenu(self.menu, action)
            self.iface.removeToolBarIcon(action)

    def run(self):
        if not self.dlg:
            self.dlg = AgenziaTafDialog()
            self.dlg.btn_scarica.clicked.connect(self.start_download)
        self.dlg.show()
        self.dlg.raise_()
        self.dlg.activateWindow()

    def start_download(self):
        com_sel = self.dlg.combo_comuni.currentText()
        if not com_sel or com_sel not in self.dlg.comuni_map:
            QMessageBox.warning(
                self.dlg, "Attenzione", "Seleziona un comune valido."
            )
            return

        sigla = self.dlg.comuni_map[com_sel]
        project_path = QgsProject.instance().fileName()
        base_dir = (
            os.path.dirname(project_path)
            if project_path
            else os.path.expanduser("~")
        )
        download_dir = os.path.join(base_dir, "dataset_taf")

        try:
            self.dlg.txt_console.clear()
            self.dlg.progress_bar.setValue(0)
            self.dlg.btn_scarica.setEnabled(False)
            self.dlg.append_log(f"Avvio elaborazione per provincia: {sigla}")
            self.dlg.append_log(f"Directory output: {download_dir}")

            # -----------------------------------------------------------------
            # GEOCODING OSM E POSIZIONAMENTO MAPPA
            # -----------------------------------------------------------------
            import requests

            self.dlg.append_log(
                f"Ricerca coordinate per {com_sel} su OSM Nominatim..."
            )
            try:
                # Forza il refresh della UI per mostrare il log
                QgsApplication.processEvents()
                resp = requests.get(
                    "https://nominatim.openstreetmap.org/search",
                    params={
                        "city": com_sel,
                        "country": "Italy",
                        "format": "json",
                    },
                    headers={"User-Agent": "QGIS_TAF_Plugin"},
                    timeout=5,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data:
                        # Ottieni bounding box e fai lo zoom
                        bbox = data[0].get("boundingbox")
                        if bbox:
                            minLat, maxLat, minLon, maxLon = map(float, bbox)
                            crs_src = QgsCoordinateReferenceSystem("EPSG:4326")
                            crs_dest = QgsCoordinateReferenceSystem(
                                "EPSG:3857"
                            )
                            transform = QgsCoordinateTransform(
                                crs_src, crs_dest, QgsProject.instance()
                            )

                            rect = QgsRectangle(minLon, minLat, maxLon, maxLat)
                            try:
                                rect = transform.transformBoundingBox(rect)
                                self.dlg.map_canvas.setExtent(rect)
                                self.dlg.map_canvas.refresh()
                                self.dlg.append_log(
                                    f"Mappa centrata su {com_sel}."
                                )
                            except Exception as e:
                                self.dlg.append_log(
                                    f"Errore trasformazione coordinate: {e}"
                                )
                    else:
                        self.dlg.append_log(
                            f"Comune '{com_sel}' non trovato su OSM."
                        )
            except Exception as e:
                self.dlg.append_log(
                    f"Impossibile connettersi a OSM Nominatim: {e}"
                )

            self.dlg.append_log("Avvio download dati TAF...")
            # -----------------------------------------------------------------

            raw_mode = self.dlg.chk_raw_mode.isChecked()
            try_convert = self.dlg.chk_try_convert.isChecked()
            task = DownloadTafTask(
                sigla,
                com_sel,
                download_dir,
                f"TAF Italia: {sigla}",
                raw_mode,
                try_convert,
            )

            # Collegamento del progresso nativo di QgsTask alla progress bar
            task.progressChanged.connect(self._on_progress_changed)

            def on_complete():
                """Chiamato quando il task termina con successo."""
                self._flush_task_logs(task)
                self.dlg.progress_bar.setValue(100)
                n = len(task.generated_files)
                if n > 0:
                    self.dlg.append_log(
                        f"✅ Completato! {n} file caricati in QGIS."
                    )
                else:
                    self.dlg.append_log(
                        "⚠️ Completato ma nessun dato trovato per questa "
                        "provincia. "
                        "Il server potrebbe non avere dati TAF disponibili."
                    )
                self.dlg.btn_scarica.setEnabled(True)
                if task in self.active_tasks:
                    self.active_tasks.remove(task)

            def on_terminated():
                """Chiamato quando il task fallisce o viene cancellato."""
                self._flush_task_logs(task)
                err_msg = (
                    str(task.exception)
                    if task.exception
                    else "Errore sconosciuto"
                )
                self.dlg.append_log(f"❌ Elaborazione fallita: {err_msg}")
                self.dlg.append_log(
                    "Controlla il Log Messaggi di QGIS (Vista > Pannelli > "
                    "Log Messaggi) "
                    "per dettagli."
                )
                self.dlg.btn_scarica.setEnabled(True)
                if task in self.active_tasks:
                    self.active_tasks.remove(task)

            task.taskCompleted.connect(on_complete)
            task.taskTerminated.connect(on_terminated)

            self.active_tasks.append(task)
            QgsApplication.taskManager().addTask(task)

        except Exception as e:
            QgsMessageLog.logMessage(
                traceback.format_exc(), "TAF Italia", level=Qgis.Critical
            )
            self.dlg.btn_scarica.setEnabled(True)
            QMessageBox.critical(
                self.dlg, "Errore", f"Impossibile avviare il download: {e}"
            )

    def _on_progress_changed(self, progress):
        """Aggiorna la progress bar della dialog dal segnale nativo di
        QgsTask."""
        if self.dlg:
            self.dlg.progress_bar.setValue(int(progress))
            # Flush dei messaggi di log accumulati dal worker thread
            for task in self.active_tasks:
                self._flush_task_logs(task)

    def _flush_task_logs(self, task):
        """Scrive nella console i messaggi accumulati dal task worker."""
        if self.dlg and hasattr(task, "log_messages"):
            while task.log_messages:
                msg = task.log_messages.pop(0)
                self.dlg.append_log(msg)
