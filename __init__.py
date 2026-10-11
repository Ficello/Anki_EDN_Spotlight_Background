# -*- coding: utf-8 -*-
"""Arrière-plan HD Spotlight (Windows à la une) pour Anki.

Moteur moderne d'arrière-plan haute définition sans émojis ni dépendances externes.
Tire des images exceptionnelles depuis Flickr (NASA Hubble) et Wikimedia Commons
(Cartographie, Géographie, Animaux marins et terrestres).
"""

from __future__ import annotations
import os
import random
from typing import Any, Dict, Optional

from aqt import gui_hooks, mw
from aqt.qt import QTimer
from aqt.utils import tooltip

from .downloader import BackgroundPrefetcher
from .engine_css import CSSEngine
from .settings_dialog import SpotlightSettingsDialog
from .spotlight_db import SpotlightDB
from .ui_spotlight import SpotlightUI

addon_package = __name__
addon_dir = os.path.dirname(__file__)

# Exposer le dossier user_files aux webviews d'Anki si mw est initialisé
if mw and getattr(mw, "addonManager", None):
    mw.addonManager.setWebExports(addon_package, r"(user_files.*)")


def get_config() -> Dict[str, Any]:
    default_conf = {
        "enabled_themes": [
            "nasa_hubble",
            "maps",
            "geography",
            "marine_animals",
            "land_animals",
        ],
        "session_mode": "launch",
        "favorites_ratio": 0.5,
        "opacity_main": 0.9,
        "opacity_reviewer": 0.85,
        "reviewer_image": True,
        "toolbar_image": True,
        "blur_radius": 0,
        "background_position": "center",
        "background_size": "cover",
        "show_deckbrowser_bar": True,
        "max_cached_images": 5,
        "adapt_screen_resolution": True,
        "custom_flickr_sources": [],
    }
    user_conf = {}
    if mw and getattr(mw, "addonManager", None):
        user_conf = mw.addonManager.getConfig(addon_package) or {}
    for k, v in default_conf.items():
        if k not in user_conf:
            user_conf[k] = v
    return user_conf


def save_config(new_conf: Dict[str, Any]) -> None:
    if mw and getattr(mw, "addonManager", None):
        mw.addonManager.writeConfig(addon_package, new_conf)


# Instanciation des composants
db = SpotlightDB(addon_dir)
prefetcher = BackgroundPrefetcher(db, get_config)
css_engine = CSSEngine(addon_package, addon_dir, get_config)


def _force_active_view_update() -> None:
    if not mw:
        return
    try:
        active_web = None
        state = getattr(mw, "state", None)
        if state == "deckBrowser" and hasattr(mw, "deckBrowser"):
            active_web = getattr(mw.deckBrowser, "web", None)
        elif state == "overview" and hasattr(mw, "overview"):
            active_web = getattr(mw.overview, "web", None)
        elif state == "review" and hasattr(mw, "reviewer"):
            active_web = getattr(mw.reviewer, "web", None)

        if not active_web and hasattr(mw, "web") and mw.web:
            active_web = mw.web

        if active_web:
            active_web.update()
            active_web.eval("if (document.body) { if (document.body.style.opacity) { document.body.style.opacity = ''; } void document.body.offsetHeight; }")
    except Exception:
        pass


def refresh_anki_views() -> None:
    """Rafraichit l'affichage de la fenetre principale d'Anki et injecte le nouveau fond dans toutes les vues."""
    css_engine.update_all_views()
    if getattr(mw, "toolbar", None):
        mw.toolbar.draw()
    if mw.state == "deckBrowser":
        mw.deckBrowser.show()
    elif mw.state == "overview":
        mw.overview.refresh()
    for delay in (50, 150, 300):
        QTimer.singleShot(delay, _force_active_view_update)


def apply_image(metadata: Dict[str, Any], refresh: bool = True) -> None:
    """Applique une nouvelle image d'arrière-plan."""
    local_path = metadata.get("local_path", "")
    if not local_path or not os.path.exists(local_path):
        return

    db.set_current(metadata)
    css_engine.update_current_image(local_path)
    if refresh:
        refresh_anki_views()


def rotate_to_next(force_discovery: bool = False, notify: bool = False) -> None:
    """Bascule vers une nouvelle image (favori ou nouvelle découverte)."""
    conf = get_config()
    ratio = float(conf.get("favorites_ratio", 0.5))
    current_id = db.current.get("id") if db.current else None

    candidate: Optional[Dict[str, Any]] = None

    # Choisir parmi les favoris selon la probabilité configurée
    if db.favorites and not force_discovery and random.random() < ratio:
        candidate = db.get_random_favorite(exclude_id=current_id)

    # Si pas de favori sélectionné ou file vide, tenter la découverte préchargée
    if not candidate:
        candidate = prefetcher.get_ready_candidate()

    # Si la file de découverte n'est pas encore prête, fallback vers un favori ou local
    if not candidate and db.favorites:
        candidate = db.get_random_favorite(exclude_id=current_id)

    if not candidate:
        candidate = db.get_fallback_default()

    if candidate:
        apply_image(candidate, refresh=True)
        if notify:
            tooltip("Nouvelle photo chargée.")

    # Relancer le préchargement en tâche de fond pour la suite
    prefetcher.trigger_prefetch()


def on_action_like() -> None:
    """Action utilisateur : Aimer la photo courante."""
    if db.like_current():
        tooltip("Photo ajoutée à vos favoris permanents.")
        # Rafraîchir pour mettre à jour le bouton dans le bandeau
        refresh_anki_views()
    else:
        tooltip("Aucune photo courante à ajouter.")


def on_action_dislike() -> None:
    """Action utilisateur : Rejeter la photo courante et passer à la suivante."""
    if db.dislike_current():
        rotate_to_next(force_discovery=True)
        tooltip("Photo retirée. Passage à la suivante.")
    else:
        tooltip("Aucune photo courante à retirer.")


def on_action_next() -> None:
    """Action utilisateur : Passer manuellement à la photo suivante."""
    rotate_to_next(force_discovery=False, notify=True)


# Timer de rotation automatique
rotation_timer: Optional[QTimer] = None


def setup_rotation_timer() -> None:
    """Configure et démarre le timer de rotation selon le réglage de session_mode."""
    global rotation_timer
    if rotation_timer is not None:
        rotation_timer.stop()
        rotation_timer = None

    conf = get_config()
    session_mode = conf.get("session_mode", "launch")

    interval_ms = 0
    if session_mode == "interval_30":
        interval_ms = 30 * 60 * 1000  # 30 minutes
    elif session_mode == "interval_60":
        interval_ms = 60 * 60 * 1000  # 60 minutes

    if interval_ms > 0:
        rotation_timer = QTimer(mw)
        rotation_timer.timeout.connect(lambda: rotate_to_next(force_discovery=False, notify=False))
        rotation_timer.start(interval_ms)


def on_open_settings() -> None:
    """Ouvre la boîte de dialogue de réglages."""
    def on_save(new_conf: Dict[str, Any]) -> None:
        save_config(new_conf)
        # Réappliquer le CSS avec les nouveaux paramètres d'opacité/flou
        if db.current and db.current.get("local_path"):
            css_engine.update_current_image(db.current["local_path"])
        refresh_anki_views()
        prefetcher.trigger_prefetch()
        # Mettre à jour le timer avec le nouveau mode de rotation
        setup_rotation_timer()

    from . import settings_dialog
    import importlib
    importlib.reload(settings_dialog)
    dlg = settings_dialog.SpotlightSettingsDialog(mw, db, get_config(), on_save)
    dlg.exec()


# Interface utilisateur
ui = SpotlightUI(
    db=db,
    get_config=get_config,
    on_like=on_action_like,
    on_dislike=on_action_dislike,
    on_next=on_action_next,
    on_open_settings=on_open_settings,
)


def on_deck_browser_render(deck_browser: Any, content: Any) -> None:
    """Injecte la barre de contrôle sobre dans le Deck Browser."""
    content.tree = ui.render_deckbrowser_toolbar(content.tree)


_web_load_connected = False


def _on_web_load_finished(ok: bool) -> None:
    if mw and hasattr(mw, "state") and mw.state in ("overview", "deckBrowser"):
        try:
            mw.web.eval("if (document.body) { document.body.style.opacity = ''; }")
        except Exception:
            pass
        css_engine.update_all_views()
        _force_active_view_update()


def on_profile_did_open() -> None:
    """Déclenché à l'ouverture du profil Anki."""
    ui.setup_menubar()

    conf = get_config()
    session_mode = conf.get("session_mode", "launch")

    # Si aucune image n'est définie ou si le mode session est 'launch', on fait tourner
    if not db.current or session_mode == "launch":
        rotate_to_next(force_discovery=False, notify=False)
    elif db.current and db.current.get("local_path") and os.path.exists(db.current["local_path"]):
        css_engine.update_current_image(db.current["local_path"])
    else:
        rotate_to_next(force_discovery=False, notify=False)

    # Nettoyer le cache au démarrage selon le quota configuré
    db.cleanup_old_cache(keep_count=int(conf.get("max_cached_images", 5)))

    # Déclencher le préchargement
    prefetcher.trigger_prefetch()

    # Démarrer le timer périodique si sélectionné
    setup_rotation_timer()

    # Connecter la notification de fin de chargement du webview principal
    global _web_load_connected
    if not _web_load_connected and hasattr(mw, "web") and mw.web:
        try:
            mw.web.loadFinished.connect(_on_web_load_finished)
            _web_load_connected = True
        except Exception:
            pass


def on_state_did_change(new_state: str, old_state: str) -> None:
    """Met a jour l'opacite et les styles lors des transitions d'ecran."""
    if mw and hasattr(mw, "web") and mw.web:
        try:
            mw.web.eval("if (document.body) { document.body.style.opacity = ''; }")
        except Exception:
            pass
    css_engine.update_all_views()
    for delay in (0, 50, 150, 300, 600):
        QTimer.singleShot(delay, _force_active_view_update)


def on_sync_did_finish() -> None:
    """Restaure l'opacite, rafraichit la vue active et revalide le fond apres synchronisation."""
    if not mw:
        return
    if hasattr(mw, "web") and mw.web:
        try:
            mw.web.eval("if (document.body) { document.body.style.opacity = ''; }")
        except Exception:
            pass

    try:
        state = getattr(mw, "state", None)
        if state == "overview" and hasattr(mw, "overview"):
            if getattr(mw.overview, "_refresh_needed", False):
                mw.overview.refresh()
        elif state == "deckBrowser" and hasattr(mw, "deckBrowser"):
            if getattr(mw.deckBrowser, "_refresh_needed", False):
                mw.deckBrowser.refresh()
        elif state == "review" and hasattr(mw, "reviewer"):
            if getattr(mw.reviewer, "_refresh_needed", False):
                mw.reviewer.refresh_if_needed()
    except Exception:
        pass

    css_engine.update_all_views()
    for delay in (0, 50, 150, 300, 600):
        QTimer.singleShot(delay, _force_active_view_update)


def on_overview_did_refresh(overview: Any) -> None:
    """Assure que le fond et l'affichage sont restaures apres chaque rafraichissement d'overview."""
    if mw and hasattr(mw, "web") and mw.web:
        try:
            mw.web.eval("if (document.body) { document.body.style.opacity = ''; }")
        except Exception:
            pass
    css_engine.update_all_views()
    for delay in (0, 50, 150, 300):
        QTimer.singleShot(delay, _force_active_view_update)


def on_deck_browser_did_render(deck_browser: Any) -> None:
    """Assure que le fond et l'affichage sont restaures apres chaque rendu du deck browser."""
    if mw and hasattr(mw, "web") and mw.web:
        try:
            mw.web.eval("if (document.body) { document.body.style.opacity = ''; }")
        except Exception:
            pass
    css_engine.update_all_views()
    for delay in (0, 50, 150, 300):
        QTimer.singleShot(delay, _force_active_view_update)


def on_state_did_reset() -> None:
    """Restaure l'affichage apres mw.reset() ou CollectionOp."""
    if mw and hasattr(mw, "web") and mw.web:
        try:
            mw.web.eval("if (document.body) { document.body.style.opacity = ''; }")
        except Exception:
            pass
    css_engine.update_all_views()
    for delay in (0, 50, 150):
        QTimer.singleShot(delay, _force_active_view_update)


def on_operation_did_execute(changes: Any, handler: Any) -> None:
    """Annule toute tentative d'Anki de figer la page a 0.3 d'opacite lors d'operations en arriere-plan."""
    if mw and hasattr(mw, "web") and mw.web:
        try:
            mw.web.eval("if (document.body && document.body.style.opacity === '0.3') { document.body.style.opacity = ''; }")
        except Exception:
            pass


def on_reviewer_did_show_question(card: Any) -> None:
    """Assure que le rafraichissement d'affichage Qt est declenche a chaque nouvelle carte."""
    conf = get_config()
    if not conf.get("reviewer_image", True):
        return
    try:
        if hasattr(mw, "reviewer") and mw.reviewer and hasattr(mw.reviewer, "web"):
            mw.reviewer.web.update()
            for delay in (50, 150, 300, 500):
                QTimer.singleShot(delay, lambda: getattr(mw.reviewer, "web", None) and mw.reviewer.web.update())
    except Exception:
        pass


def on_reviewer_did_show_answer(card: Any) -> None:
    """Assure que le rafraichissement d'affichage Qt est declenche lors du retournement vers la reponse."""
    conf = get_config()
    if not conf.get("reviewer_image", True):
        return
    try:
        if hasattr(mw, "reviewer") and mw.reviewer and hasattr(mw.reviewer, "web"):
            mw.reviewer.web.update()
            for delay in (50, 150, 300, 500):
                QTimer.singleShot(delay, lambda: getattr(mw.reviewer, "web", None) and mw.reviewer.web.update())
    except Exception:
        pass


# Enregistrement des hooks GUI Anki
gui_hooks.profile_did_open.append(on_profile_did_open)
gui_hooks.state_did_change.append(on_state_did_change)
gui_hooks.sync_did_finish.append(on_sync_did_finish)
gui_hooks.overview_did_refresh.append(on_overview_did_refresh)
gui_hooks.deck_browser_did_render.append(on_deck_browser_did_render)
gui_hooks.state_did_reset.append(on_state_did_reset)
gui_hooks.operation_did_execute.append(on_operation_did_execute)
gui_hooks.reviewer_did_show_question.append(on_reviewer_did_show_question)
gui_hooks.reviewer_did_show_answer.append(on_reviewer_did_show_answer)
gui_hooks.webview_will_set_content.append(css_engine.on_webview_will_set_content)
gui_hooks.webview_did_inject_style_into_page.append(css_engine.on_webview_did_inject_style)
gui_hooks.deck_browser_will_render_content.append(on_deck_browser_render)
gui_hooks.webview_did_receive_js_message.append(ui.handle_js_message)
