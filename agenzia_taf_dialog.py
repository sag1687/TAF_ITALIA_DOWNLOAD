# -*- coding: utf-8 -*-

import os
import json
import webbrowser
from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDialog, QCompleter
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QPixmap, QIcon

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'agenzia_taf_dialog_base.ui'))


class AgenziaTafDialog(QDialog, FORM_CLASS):
    def __init__(self, parent=None):
        super(AgenziaTafDialog, self).__init__(parent)
        self.setupUi(self)
        self.comuni_map = {}
        self.plugin_urls = {}

        self.load_comuni()
        self.setup_info_tab()

    def append_log(self, text):
        """Aggiunge una riga alla console di log."""
        self.txt_console.appendPlainText(text)
        # Scroll automatico alla fine
        self.txt_console.verticalScrollBar().setValue(
            self.txt_console.verticalScrollBar().maximum())

    def load_comuni(self):
        json_path = os.path.join(os.path.dirname(__file__), 'comuni.json')
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    self.comuni_map = json.load(f)
            except Exception as e:
                pass  # Errore gestito silenziosamente

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

        # Carica il logo SinoCloud (a destra)
        l_path = os.path.join(os.path.dirname(__file__),
                              'sinocloud-logo_real.png')
        if os.path.exists(l_path):
            pix = QPixmap(l_path)
            self.label_logo.setPixmap(pix.scaledToWidth(120, smooth_t))

        # Carica il logo TAF (a sinistra, più grande)
        t_path = os.path.join(os.path.dirname(__file__), 'TAF.png')
        if os.path.exists(t_path):
            pix_t = QPixmap(t_path)
            self.label_logo_taf.setPixmap(pix_t.scaledToHeight(70, smooth_t))

        # Carica i plugin esterni
        icon_dir = os.path.join(os.path.dirname(__file__), 'altri_plugin')
        el_path = os.path.join(icon_dir, 'elenco.txt')
        if os.path.exists(el_path):
            try:
                with open(el_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        url = line.strip()
                        if not url:
                            continue
                        p_name = url.strip('/').split('/')[-1]
                        p_disp = p_name.replace('_', ' ').title()
                        self.plugin_urls[p_disp] = url
                        i_path = None
                        for ex in ['.png', '.svg', '.jpg']:
                            if os.path.exists(os.path.join(icon_dir,
                                              f'{p_name}{ex}')):
                                i_path = os.path.join(icon_dir, f'{p_name}{ex}')
                                break
                            short = p_name.replace('_plugin', '')
                            if os.path.exists(os.path.join(icon_dir,
                                              f'{short}{ex}')):
                                i_path = os.path.join(icon_dir, f'{short}{ex}')
                                break
                        if i_path:
                            self.combo_altri_plugin.addItem(
                                QIcon(i_path), p_disp)
                        else:
                            self.combo_altri_plugin.addItem(p_disp)
            except Exception:
                pass

        self.btn_apri_plugin.clicked.connect(self.apri_link_plugin)

    def apri_link_plugin(self):
        selected_plugin = self.combo_altri_plugin.currentText()
        url = self.plugin_urls.get(selected_plugin)
        if url:
            webbrowser.open(url)
