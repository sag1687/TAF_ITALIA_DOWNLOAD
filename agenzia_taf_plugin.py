# -*- coding: utf-8 -*-

import os
import traceback
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.core import (QgsApplication, QgsProject, QgsVectorLayer,
                       QgsTask, QgsMessageLog, Qgis)

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

    def __init__(self, sigla, download_dir, description):
        super().__init__(description, QgsTask.CanCancel)
        self.sigla = sigla
        self.download_dir = download_dir
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
                """Callback invocata da taf_core per comunicare il progresso."""
                self.setProgress(float(val))
                if text:
                    self.log_messages.append(text)

            self.generated_files = download_and_convert_province(
                self.sigla,
                self.download_dir,
                local_progress
            )
            return True
        except Exception as e:
            self.exception = e
            self.log_messages.append(f"ERRORE CRITICO: {str(e)}")
            QgsMessageLog.logMessage(
                f"TAF Task crash:\n{traceback.format_exc()}",
                'TAF Italia', level=Qgis.Critical)
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

                if filepath.endswith('.gpkg'):
                    # Carica GeoPackage
                    layer = QgsVectorLayer(filepath, layer_name, "ogr")
                elif filepath.endswith('.csv'):
                    # Carica CSV come layer di testo delimitato con coordinate
                    uri = (f"file:///{filepath}?delimiter=,&"
                           f"xField=Lon_WGS84&yField=Lat_WGS84&crs=EPSG:4326")
                    layer = QgsVectorLayer(uri, layer_name, "delimitedtext")
                else:
                    continue

                if layer.isValid():
                    QgsProject.instance().addMapLayer(layer)
                    loaded += 1
                    QgsMessageLog.logMessage(
                        f"Layer caricato: {layer_name}",
                        "TAF Italia", level=Qgis.Success)
                else:
                    QgsMessageLog.logMessage(
                        f"Layer non valido: {filepath}",
                        "TAF Italia", level=Qgis.Warning)

            QgsMessageLog.logMessage(
                f"TAF {self.sigla}: {loaded} layer caricati su "
                f"{len(self.generated_files)} file generati.",
                "TAF Italia", level=Qgis.Success)
        else:
            QgsMessageLog.logMessage(
                f"Errore TAF {self.sigla}: {self.exception}",
                "TAF Italia", level=Qgis.Critical)


class AgenziaTafPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.actions = []
        self.menu = u'&TAF Italia'
        self.dlg = None
        self.active_tasks = []

    def add_action(self, icon_path, text, callback, enabled_flag=True,
                   add_to_menu=True, add_to_toolbar=True, status_tip=None):
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
        icon_path = os.path.join(self.plugin_dir, 'icon.png')
        self.add_action(icon_path, text=u'TAF Italia - Scarica Punti Fiduciali', callback=self.run)

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
            QMessageBox.warning(self.dlg, "Attenzione", "Seleziona un comune valido.")
            return

        sigla = self.dlg.comuni_map[com_sel]
        project_path = QgsProject.instance().fileName()
        base_dir = os.path.dirname(project_path) if project_path else os.path.expanduser('~')
        download_dir = os.path.join(base_dir, "dataset_taf")

        try:
            self.dlg.txt_console.clear()
            self.dlg.progress_bar.setValue(0)
            self.dlg.btn_scarica.setEnabled(False)
            self.dlg.append_log(f"Avvio download TAF per provincia: {sigla}")
            self.dlg.append_log(f"Directory output: {download_dir}")

            task = DownloadTafTask(sigla, download_dir, f"TAF Italia: {sigla}")

            # Collegamento del progresso nativo di QgsTask alla progress bar
            task.progressChanged.connect(self._on_progress_changed)

            def on_complete():
                """Chiamato quando il task termina con successo."""
                self._flush_task_logs(task)
                self.dlg.progress_bar.setValue(100)
                n = len(task.generated_files)
                if n > 0:
                    self.dlg.append_log(f"✅ Completato! {n} file caricati in QGIS.")
                else:
                    self.dlg.append_log(
                        "⚠️ Completato ma nessun dato trovato per questa provincia. "
                        "Il server potrebbe non avere dati TAF disponibili.")
                self.dlg.btn_scarica.setEnabled(True)
                if task in self.active_tasks:
                    self.active_tasks.remove(task)

            def on_terminated():
                """Chiamato quando il task fallisce o viene cancellato."""
                self._flush_task_logs(task)
                err_msg = str(task.exception) if task.exception else "Errore sconosciuto"
                self.dlg.append_log(f"❌ Elaborazione fallita: {err_msg}")
                self.dlg.append_log(
                    "Controlla il Log Messaggi di QGIS (Vista > Pannelli > Log Messaggi) "
                    "per dettagli.")
                self.dlg.btn_scarica.setEnabled(True)
                if task in self.active_tasks:
                    self.active_tasks.remove(task)

            task.taskCompleted.connect(on_complete)
            task.taskTerminated.connect(on_terminated)

            self.active_tasks.append(task)
            QgsApplication.taskManager().addTask(task)

        except Exception as e:
            QgsMessageLog.logMessage(traceback.format_exc(), 'TAF Italia', level=Qgis.Critical)
            self.dlg.btn_scarica.setEnabled(True)
            QMessageBox.critical(self.dlg, "Errore", f"Impossibile avviare il download: {e}")

    def _on_progress_changed(self, progress):
        """Aggiorna la progress bar della dialog dal segnale nativo di QgsTask."""
        if self.dlg:
            self.dlg.progress_bar.setValue(int(progress))
            # Flush dei messaggi di log accumulati dal worker thread
            for task in self.active_tasks:
                self._flush_task_logs(task)

    def _flush_task_logs(self, task):
        """Scrive nella console i messaggi accumulati dal task worker."""
        if self.dlg and hasattr(task, 'log_messages'):
            while task.log_messages:
                msg = task.log_messages.pop(0)
                self.dlg.append_log(msg)
