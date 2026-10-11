# -*- coding: utf-8 -*-
"""Boîte de dialogue de configuration sobre et ergonomique pour l'arrière-plan Spotlight."""

from __future__ import annotations
import os
import re
from typing import Any, Callable, Dict, List

from aqt import mw
from aqt.qt import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSlider,
    QSpinBox,
    QTabWidget,
    Qt,
    QVBoxLayout,
    QWidget,
)
from aqt.utils import openFolder, showInfo, showWarning

from .sources import THEME_LABELS, get_screen_target_resolution, resolve_flickr_feed_url
from .spotlight_db import SpotlightDB


class SpotlightSettingsDialog(QDialog):
    def __init__(
        self,
        parent: QWidget,
        db: SpotlightDB,
        config: Dict[str, Any],
        on_save_callback: Callable[[Dict[str, Any]], None],
    ):
        super().__init__(parent)
        self.db = db
        self.config = dict(config)
        self.on_save_callback = on_save_callback
        self.custom_flickr_list: List[Dict[str, Any]] = list(self.config.get("custom_flickr_sources", []))

        self.setWindowTitle("Configuration — Arrière-plan Spotlight")
        self.setMinimumWidth(560)
        self.setMinimumHeight(480)

        self.setup_ui()
        self.load_values()

    def setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(16, 16, 16, 16)

        self.tabs = QTabWidget()

        # Onglet 1 : Thèmes d'images
        tab_themes = QWidget()
        themes_layout = QVBoxLayout(tab_themes)
        themes_layout.setSpacing(10)

        themes_group = QGroupBox("Banques d'images officielles et sélectionnées")
        themes_inner = QVBoxLayout(themes_group)
        themes_inner.setSpacing(6)

        self.chk_nasa = QCheckBox("NASA Hubble & Espace (Flickr officiel et archives NASA)")
        self.chk_deep_space = QCheckBox("Ciel profond & Nébuleuses (James Webb & Télescopes mondiaux)")
        self.chk_maps = QCheckBox("Cartes & Cartographie historique (Wikimedia Commons)")
        self.chk_geography = QCheckBox("Géographie & Grands Paysages (Fjords, montagnes, déserts)")
        self.chk_marine = QCheckBox("Faune marine & Océans (Récifs, poissons, cétacés)")
        self.chk_land = QCheckBox("Faune terrestre & Mammifères sauvages")
        self.chk_architecture = QCheckBox("Architecture & Monuments du Monde (Cathédrales, palais, ponts)")
        self.chk_paintings = QCheckBox("Peintures classiques & Beaux-Arts (Musées internationaux)")
        self.chk_social_movements = QCheckBox("Mouvements sociaux & Histoire des luttes (Manifestations, droits civiques, grèves)")
        self.chk_botanical = QCheckBox("Botanique & Flore macro (Fleurs sauvages, forêts)")
        self.chk_microscopy = QCheckBox("Microscopie & Monde miniature (Microscopie électronique, cristaux)")

        self.all_built_in_checks = [
            ("nasa_hubble", self.chk_nasa),
            ("deep_space", self.chk_deep_space),
            ("maps", self.chk_maps),
            ("geography", self.chk_geography),
            ("marine_animals", self.chk_marine),
            ("land_animals", self.chk_land),
            ("architecture", self.chk_architecture),
            ("paintings", self.chk_paintings),
            ("social_movements", self.chk_social_movements),
            ("botanical", self.chk_botanical),
            ("microscopy", self.chk_microscopy),
        ]

        for _, chk in self.all_built_in_checks:
            themes_inner.addWidget(chk)

        themes_layout.addWidget(themes_group)
        themes_layout.addStretch()
        self.tabs.addTab(tab_themes, "Thèmes")

        # Onglet 2 : Banques personnalisées Flickr
        tab_flickr = QWidget()
        flickr_layout = QVBoxLayout(tab_flickr)
        flickr_layout.setSpacing(10)

        lbl_flickr_desc = QLabel(
            "Ajoutez vos propres flux et banques d'images Flickr.\n"
            "Vous pouvez coller l'adresse d'un profil (ex: https://www.flickr.com/photos/nasa/),\n"
            "un identifiant NSID ou des mots-clés séparés par des virgules (ex: japon,architecture)."
        )
        lbl_flickr_desc.setWordWrap(True)
        flickr_layout.addWidget(lbl_flickr_desc)

        self.list_flickr = QListWidget()
        flickr_layout.addWidget(self.list_flickr)

        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(8)
        self.btn_add_flickr = QPushButton("Ajouter une banque Flickr...")
        self.btn_add_flickr.clicked.connect(self._on_add_flickr)
        self.btn_remove_flickr = QPushButton("Supprimer la sélection")
        self.btn_remove_flickr.clicked.connect(self._on_remove_flickr)
        btn_bar.addWidget(self.btn_add_flickr)
        btn_bar.addWidget(self.btn_remove_flickr)
        btn_bar.addStretch()
        flickr_layout.addLayout(btn_bar)

        self.tabs.addTab(tab_flickr, "Banques Flickr")

        # Onglet 3 : Rotation & Résolution
        tab_rotation = QWidget()
        rot_layout = QVBoxLayout(tab_rotation)
        rot_layout.setSpacing(12)

        rot_group = QGroupBox("Comportement du roulement")
        rot_form = QFormLayout(rot_group)
        rot_form.setSpacing(10)

        self.combo_session = QComboBox()
        self.combo_session.addItem("À chaque lancement d'Anki (par session)", "launch")
        self.combo_session.addItem("Toutes les 30 minutes", "interval_30")
        self.combo_session.addItem("Toutes les 60 minutes", "interval_60")
        self.combo_session.addItem("Changement manuel uniquement", "manual")
        rot_form.addRow("Changement d'image :", self.combo_session)

        # Ratio favoris
        self.slider_ratio = QSlider(Qt.Orientation.Horizontal)
        self.slider_ratio.setRange(0, 100)
        self.slider_ratio.setSingleStep(5)
        self.lbl_ratio = QLabel("50 % favoris / 50 % découverte")
        self.slider_ratio.valueChanged.connect(self._on_ratio_changed)

        ratio_layout = QVBoxLayout()
        ratio_layout.addWidget(self.slider_ratio)
        ratio_layout.addWidget(self.lbl_ratio)
        rot_form.addRow("Équilibre de rotation :", ratio_layout)

        # Quota de cache
        self.spin_max_cache = QSpinBox()
        self.spin_max_cache.setRange(2, 20)
        self.spin_max_cache.setSuffix(" photos")
        rot_form.addRow("Quota de cache temporaire :", self.spin_max_cache)

        self.chk_deckbrowser_bar = QCheckBox("Afficher la barre de contrôle sur l'écran d'accueil")
        rot_form.addRow("", self.chk_deckbrowser_bar)

        # Résolution d'écran
        res_target = get_screen_target_resolution(1920)
        self.chk_adapt_res = QCheckBox(f"Adapter la résolution au format d'écran (détecté : {res_target}px de large)")
        rot_form.addRow("", self.chk_adapt_res)

        rot_layout.addWidget(rot_group)

        # Gestion des favoris et stockage
        fav_group = QGroupBox("Stockage et Collection locale")
        fav_inner = QVBoxLayout(fav_group)
        fav_inner.setSpacing(8)

        self.lbl_storage_stats = QLabel()
        fav_inner.addWidget(self.lbl_storage_stats)

        btn_box = QHBoxLayout()
        btn_open_favs = QPushButton("Ouvrir le dossier des favoris")
        btn_open_favs.clicked.connect(lambda: openFolder(self.db.favorites_dir))
        btn_clean_cache = QPushButton("Vider le cache temporaire")
        btn_clean_cache.clicked.connect(self._on_clean_cache)

        btn_box.addWidget(btn_open_favs)
        btn_box.addWidget(btn_clean_cache)
        fav_inner.addLayout(btn_box)

        rot_layout.addWidget(fav_group)
        rot_layout.addStretch()
        self.tabs.addTab(tab_rotation, "Rotation")

        # Onglet 4 : Affichage & Rendu
        tab_display = QWidget()
        disp_layout = QVBoxLayout(tab_display)
        disp_layout.setSpacing(12)

        disp_group = QGroupBox("Opacité et Lisibilité")
        disp_form = QFormLayout(disp_group)
        disp_form.setSpacing(10)

        # Opacité principale
        self.slider_opacity_main = QSlider(Qt.Orientation.Horizontal)
        self.slider_opacity_main.setRange(10, 100)
        self.lbl_opacity_main = QLabel("90 %")
        self.slider_opacity_main.valueChanged.connect(lambda v: self.lbl_opacity_main.setText(f"{v} %"))
        h_op_main = QHBoxLayout()
        h_op_main.addWidget(self.slider_opacity_main)
        h_op_main.addWidget(self.lbl_opacity_main)
        disp_form.addRow("Opacité (Accueil & Listes) :", h_op_main)

        # Reviewer activé
        self.chk_reviewer = QCheckBox("Activer l'arrière-plan pendant les révisions")
        disp_form.addRow("", self.chk_reviewer)

        # Opacité révision
        self.slider_opacity_rev = QSlider(Qt.Orientation.Horizontal)
        self.slider_opacity_rev.setRange(10, 100)
        self.lbl_opacity_rev = QLabel("85 %")
        self.slider_opacity_rev.valueChanged.connect(lambda v: self.lbl_opacity_rev.setText(f"{v} %"))
        h_op_rev = QHBoxLayout()
        h_op_rev.addWidget(self.slider_opacity_rev)
        h_op_rev.addWidget(self.lbl_opacity_rev)
        disp_form.addRow("Opacité (Révisions) :", h_op_rev)

        # Barres d'outils (haut / bas)
        self.chk_toolbar = QCheckBox("Activer l'arrière-plan sur les barres supérieure et inférieure")
        disp_form.addRow("", self.chk_toolbar)

        # Flou de fond
        self.spin_blur = QSpinBox()
        self.spin_blur.setRange(0, 20)
        self.spin_blur.setSuffix(" px")
        disp_form.addRow("Flou d'arrière-plan :", self.spin_blur)

        disp_layout.addWidget(disp_group)
        disp_layout.addStretch()
        self.tabs.addTab(tab_display, "Affichage")

        main_layout.addWidget(self.tabs)

        # Boutons Standard
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)

    def _refresh_flickr_list(self) -> None:
        self.list_flickr.clear()
        enabled_themes = self.config.get("enabled_themes", [])
        for item in self.custom_flickr_list:
            src_id = item.get("id", "")
            name = item.get("name", "Banque")
            feed_url = item.get("feed_url", "")
            list_item = QListWidgetItem(f"{name} — {feed_url}")
            list_item.setData(Qt.ItemDataRole.UserRole, src_id)
            list_item.setFlags(list_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            is_checked = src_id in enabled_themes
            list_item.setCheckState(Qt.CheckState.Checked if is_checked else Qt.CheckState.Unchecked)
            self.list_flickr.addItem(list_item)

    def _on_add_flickr(self) -> None:
        text, ok = QInputDialog.getText(
            self,
            "Ajouter une banque Flickr",
            "Entrez l'URL d'un profil Flickr, un album, un NSID ou des mots-clés :",
            QLineEdit.EchoMode.Normal,
            ""
        )
        if not ok or not text.strip():
            return

        raw_input = text.strip()
        feed_url = resolve_flickr_feed_url(raw_input)
        if not feed_url:
            showWarning("Impossible de résoudre ce lien Flickr. Vérifiez l'adresse ou les mots-clés.", parent=self)
            return

        name, ok_name = QInputDialog.getText(
            self,
            "Nom de la banque d'images",
            "Nommez cette collection pour l'affichage :",
            QLineEdit.EchoMode.Normal,
            "Flickr — " + raw_input.split("/")[-1].replace("@", "_") if "/" in raw_input else f"Flickr ({raw_input})"
        )
        if not ok_name or not name.strip():
            name = "Flickr personnalisé"

        clean_id = "custom_" + re.sub(r"\W+", "_", raw_input).strip("_")[:20]
        new_entry = {
            "id": clean_id,
            "name": name.strip(),
            "input": raw_input,
            "feed_url": feed_url,
        }

        # Ajouter ou mettre à jour
        self.custom_flickr_list = [s for s in self.custom_flickr_list if s.get("id") != clean_id]
        self.custom_flickr_list.append(new_entry)

        # Activer ce nouveau thème par défaut
        themes = self.config.get("enabled_themes", [])
        if clean_id not in themes:
            themes.append(clean_id)
            self.config["enabled_themes"] = themes

        THEME_LABELS[clean_id] = name.strip()
        self._refresh_flickr_list()
        showInfo(f"La banque '{name.strip()}' a été ajoutée et activée avec succès.", parent=self)

    def _on_remove_flickr(self) -> None:
        current_item = self.list_flickr.currentItem()
        if not current_item:
            showWarning("Veuillez sélectionner une banque Flickr dans la liste à supprimer.", parent=self)
            return

        src_id = current_item.data(Qt.ItemDataRole.UserRole)
        self.custom_flickr_list = [s for s in self.custom_flickr_list if s.get("id") != src_id]
        themes = self.config.get("enabled_themes", [])
        if src_id in themes:
            themes.remove(src_id)
            self.config["enabled_themes"] = themes

        self._refresh_flickr_list()

    def _update_storage_label(self) -> None:
        if not hasattr(self, "lbl_storage_stats") or self.lbl_storage_stats is None:
            return
        try:
            stats = self.db.get_disk_usage()
            self.lbl_storage_stats.setText(
                f"Favoris : {stats['fav_count']} photo(s) ({stats['fav_mb']} Mo)\n"
                f"Cache temporaire : {stats['cache_count']} photo(s) ({stats['cache_mb']} Mo)\n"
                f"Espace disque total : {stats['total_mb']} Mo"
            )
        except Exception:
            pass

    def _on_ratio_changed(self, value: int) -> None:
        self.lbl_ratio.setText(f"{value} % favoris / {100 - value} % découverte")

    def _on_clean_cache(self) -> None:
        self.db.cleanup_old_cache(keep_count=0)
        self._update_storage_label()
        showInfo("Le cache temporaire des photos a été vidé.", parent=self)

    def load_values(self) -> None:
        themes = self.config.get("enabled_themes", [])
        for key, chk in self.all_built_in_checks:
            chk.setChecked(key in themes)

        self._refresh_flickr_list()

        session_mode = self.config.get("session_mode", "launch")
        idx = self.combo_session.findData(session_mode)
        if idx >= 0:
            self.combo_session.setCurrentIndex(idx)

        ratio = int(self.config.get("favorites_ratio", 0.5) * 100)
        self.slider_ratio.setValue(ratio)
        self._on_ratio_changed(ratio)

        self.spin_max_cache.setValue(int(self.config.get("max_cached_images", 5)))
        self.chk_deckbrowser_bar.setChecked(self.config.get("show_deckbrowser_bar", True))
        self.chk_adapt_res.setChecked(self.config.get("adapt_screen_resolution", True))

        op_main = int(float(self.config.get("opacity_main", 0.9)) * 100)
        self.slider_opacity_main.setValue(op_main)
        self.lbl_opacity_main.setText(f"{op_main} %")

        self.chk_reviewer.setChecked(self.config.get("reviewer_image", True))
        self.chk_toolbar.setChecked(self.config.get("toolbar_image", True))

        op_rev = int(float(self.config.get("opacity_reviewer", 0.85)) * 100)
        self.slider_opacity_rev.setValue(op_rev)
        self.lbl_opacity_rev.setText(f"{op_rev} %")

        self.spin_blur.setValue(int(self.config.get("blur_radius", 0)))
        self._update_storage_label()

    def save_values(self) -> Dict[str, Any]:
        themes = []
        for key, chk in self.all_built_in_checks:
            if chk.isChecked():
                themes.append(key)

        for i in range(self.list_flickr.count()):
            item = self.list_flickr.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                src_id = item.data(Qt.ItemDataRole.UserRole)
                if src_id not in themes:
                    themes.append(src_id)

        if not themes:
            themes = ["nasa_hubble", "geography"]

        self.config["enabled_themes"] = themes
        self.config["custom_flickr_sources"] = self.custom_flickr_list
        self.config["adapt_screen_resolution"] = self.chk_adapt_res.isChecked()
        self.config["session_mode"] = self.combo_session.currentData()
        self.config["favorites_ratio"] = self.slider_ratio.value() / 100.0
        self.config["max_cached_images"] = self.spin_max_cache.value()
        self.config["show_deckbrowser_bar"] = self.chk_deckbrowser_bar.isChecked()
        self.config["opacity_main"] = round(self.slider_opacity_main.value() / 100.0, 2)
        self.config["reviewer_image"] = self.chk_reviewer.isChecked()
        self.config["toolbar_image"] = self.chk_toolbar.isChecked()
        self.config["opacity_reviewer"] = round(self.slider_opacity_rev.value() / 100.0, 2)
        self.config["blur_radius"] = self.spin_blur.value()

        return self.config

    def accept(self) -> None:
        new_config = self.save_values()
        self.on_save_callback(new_config)
        super().accept()
