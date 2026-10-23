# -*- coding: utf-8 -*-
"""Composants d'interface utilisateur sobres pour Spotlight (Menus, Raccourcis, Bandeau)."""

from __future__ import annotations
import html
import re
from typing import Any, Callable, Dict, Optional, Tuple

from aqt import mw
from aqt.qt import (
    QAction,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QKeySequence,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)
from aqt.utils import openLink, tooltip

from .sources import THEME_LABELS
from .spotlight_db import SpotlightDB


class SpotlightInfoDialog(QDialog):
    """Boîte de dialogue affichant les détails et la description complète de l'image courante."""

    def __init__(self, parent: QWidget, metadata: Dict[str, Any], get_config: Optional[Callable[[], Dict[str, Any]]] = None):
        super().__init__(parent)
        self.metadata = metadata
        self.get_config = get_config
        self.setWindowTitle("Détails de l'image — Arrière-plan Spotlight")
        self.setMinimumWidth(540)
        self.setMinimumHeight(420)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(18, 18, 18, 18)

        form = QFormLayout()
        form.setSpacing(8)

        title = metadata.get("title", "Image d'arrière-plan")
        theme_key = metadata.get("theme", "")
        theme_label = THEME_LABELS.get(theme_key)
        if not theme_label and self.get_config:
            conf = self.get_config()
            for src in conf.get("custom_flickr_sources", []):
                if src.get("id") == theme_key:
                    theme_label = src.get("name")
                    break
        if not theme_label:
            theme_label = theme_key.replace("custom_", "Flickr ").replace("_", " ").title()

        source = metadata.get("source_name", "Source inconnue")
        author = metadata.get("author", "").strip()
        date = metadata.get("date", "").strip()
        description = metadata.get("description", "").strip()
        page_url = metadata.get("page_url", "")
        is_fav = metadata.get("is_favorite", False)

        lbl_title = QLabel(f"<b style='font-size: 13px;'>{html.escape(title)}</b>")
        lbl_title.setWordWrap(True)
        form.addRow("Titre :", lbl_title)

        form.addRow("Thème :", QLabel(theme_label))
        form.addRow("Banque / Source :", QLabel(source))

        if author:
            lbl_author = QLabel(html.escape(author))
            lbl_author.setWordWrap(True)
            form.addRow("Auteur / Artiste :", lbl_author)

        if date:
            form.addRow("Date :", QLabel(html.escape(date)))

        form.addRow("Statut :", QLabel("Conservée dans les favoris" if is_fav else "En cours de découverte"))
        layout.addLayout(form)

        # Section Description si présente
        if description:
            lbl_desc_title = QLabel("<b>Description :</b>")
            layout.addWidget(lbl_desc_title)

            txt_desc = QTextBrowser()
            txt_desc.setPlainText(description)
            txt_desc.setReadOnly(True)
            txt_desc.setOpenExternalLinks(True)
            txt_desc.setStyleSheet(
                "QTextBrowser { border: 1px solid rgba(128,128,128,0.25); border-radius: 4px; padding: 6px; font-size: 12px; }"
            )
            txt_desc.setMinimumHeight(140)
            layout.addWidget(txt_desc)
        else:
            lbl_no_desc = QLabel("<i style='color: gray;'>Aucune description textuelle fournie par la source pour cette image.</i>")
            layout.addWidget(lbl_no_desc)

        btn_row = QHBoxLayout()
        if page_url:
            btn_link = QPushButton("Consulter la page source d'origine")
            btn_link.clicked.connect(lambda: openLink(page_url))
            btn_row.addWidget(btn_link)

        btn_row.addStretch()
        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btn_box.rejected.connect(self.close)
        btn_row.addWidget(btn_box)

        layout.addLayout(btn_row)


class SpotlightUI:
    def __init__(
        self,
        db: SpotlightDB,
        get_config: Callable[[], Dict[str, Any]],
        on_like: Callable[[], None],
        on_dislike: Callable[[], None],
        on_next: Callable[[], None],
        on_open_settings: Callable[[], None],
        on_toggle_enabled: Callable[[], None],
        on_open_favorites_folder: Callable[[], None],
        on_add_photos: Callable[[], None],
    ):
        self.db = db
        self.get_config = get_config
        self.on_like = on_like
        self.on_dislike = on_dislike
        self.on_next = on_next
        self.on_open_settings = on_open_settings
        self.on_toggle_enabled = on_toggle_enabled
        self.on_open_favorites_folder = on_open_favorites_folder
        self.on_add_photos = on_add_photos

    def setup_menubar(self) -> None:
        """Crée le menu supérieur 'Arrière-plan' dans Anki."""
        menubar = mw.form.menubar

        menu_name = "&Arrière-plan"
        menu = None
        for action in menubar.actions():
            if action.text() == menu_name:
                menu = action.menu()
                break

        if not menu:
            menu = menubar.addMenu(menu_name)
        else:
            menu.clear()

        # Action : Activer / Désactiver
        is_enabled = self.get_config().get("enabled", True)
        act_enabled = QAction("Arrière-plan activé", mw)
        act_enabled.setCheckable(True)
        act_enabled.setChecked(is_enabled)
        act_enabled.triggered.connect(self.on_toggle_enabled)
        menu.addAction(act_enabled)

        menu.addSeparator()

        # Action : J'aime
        act_like = QAction("J'aime cette photo (Garder en favori)", mw)
        act_like.setShortcut(QKeySequence("Ctrl+J"))
        act_like.triggered.connect(self.on_like)
        menu.addAction(act_like)

        # Action : Je n'aime pas
        act_dislike = QAction("Je n'aime pas (Ne plus afficher)", mw)
        act_dislike.setShortcut(QKeySequence("Ctrl+K"))
        act_dislike.triggered.connect(self.on_dislike)
        menu.addAction(act_dislike)

        # Action : Suivante
        act_next = QAction("Photo suivante", mw)
        act_next.setShortcut(QKeySequence("Ctrl+;"))
        act_next.triggered.connect(self.on_next)
        menu.addAction(act_next)

        menu.addSeparator()

        # Action : Informations
        act_info = QAction("Détails de la photo...", mw)
        act_info.triggered.connect(self.show_current_info)
        menu.addAction(act_info)

        # Action : Ouvrir le dossier favoris
        act_folder = QAction("Ouvrir le dossier des photos favorites (Ajouter les vôtres)", mw)
        act_folder.triggered.connect(self.on_open_favorites_folder)
        menu.addAction(act_folder)

        # Action : Ajouter des photos directement
        act_add = QAction("Ajouter des photos aux favoris...", mw)
        act_add.triggered.connect(self.on_add_photos)
        menu.addAction(act_add)

        menu.addSeparator()

        # Action : Paramètres
        act_settings = QAction("Thèmes et Paramètres...", mw)
        act_settings.triggered.connect(self.on_open_settings)
        menu.addAction(act_settings)

    def show_current_info(self) -> None:
        """Affiche les détails de la photo en cours."""
        if not self.db.current:
            tooltip("Aucune photo n'est actuellement chargée.")
            return
        dlg = SpotlightInfoDialog(mw, self.db.current, get_config=self.get_config)
        dlg.exec()

    def render_deckbrowser_toolbar(self, content_tree: str) -> str:
        """Injecte une carte Spotlight sobre à gauche du sélectionneur de decks."""
        conf = self.get_config()
        if not conf.get("show_deckbrowser_bar", True):
            return content_tree

        if not conf.get("enabled", True):
            toolbar_html = f"""
<style>
#spotlight-deck-container {{
  display: flex;
  justify-content: center;
  width: 100%;
  margin: 24px auto 16px auto;
  box-sizing: border-box;
  isolation: isolate;
}}

#spotlight-deck-card {{
  width: 100%;
  max-width: 580px;
  box-sizing: border-box;
  padding: 12px 16px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.90);
  border: 1px solid rgba(0, 0, 0, 0.12);
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.05);
  font-size: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  text-align: left;
  color: var(--fg, #222);
}}

:root[class*="night_mode"] #spotlight-deck-card,
:root.night-mode #spotlight-deck-card,
body.night_mode #spotlight-deck-card,
body.nightMode #spotlight-deck-card {{
  background: rgba(34, 34, 34, 0.90);
  border-color: rgba(255, 255, 255, 0.14);
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.25);
  color: var(--fg, #e0e0e0);
}}

.spotlight-card-header-line {{
  display: flex;
  justify-content: space-between;
  align-items: center;
}}

.spotlight-card-label {{
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.8px;
  opacity: 0.6;
  text-transform: uppercase;
}}

.spotlight-card-status-badge {{
  font-size: 10px;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 4px;
  background: rgba(128, 128, 128, 0.18);
  color: var(--fg, #444);
}}

.spotlight-card-actions {{
  display: flex;
  flex-direction: row;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 4px;
}}

.spotlight-card-btn {{
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 8px;
  font-size: 11px;
  font-weight: 500;
  cursor: pointer;
  border-radius: 4px;
  border: 1px solid var(--border-subtle, rgba(128, 128, 128, 0.25));
  background: var(--button-bg, rgba(255, 255, 255, 0.7));
  color: var(--fg, #222);
  box-sizing: border-box;
}}

:root[class*="night_mode"] .spotlight-card-btn,
:root.night-mode .spotlight-card-btn,
body.night_mode .spotlight-card-btn,
body.nightMode .spotlight-card-btn {{
  background: var(--button-bg, rgba(50, 50, 50, 0.75));
  border-color: var(--border-subtle, rgba(255, 255, 255, 0.2));
  color: var(--fg, #eee);
}}

.spotlight-card-btn:hover {{
  background: var(--button-gradient-start, #fff);
  border-color: var(--button-hover-border, #999);
}}

:root[class*="night_mode"] .spotlight-card-btn:hover,
:root.night-mode .spotlight-card-btn:hover,
body.night_mode .spotlight-card-btn:hover,
body.nightMode .spotlight-card-btn:hover {{
  background: var(--button-gradient-start, #383838);
  border-color: rgba(255, 255, 255, 0.35);
}}
</style>

<div id="spotlight-deck-container">
  <div id="spotlight-deck-card">
    <div class="spotlight-card-header-line">
      <span class="spotlight-card-label">Arriere-plan</span>
      <span class="spotlight-card-status-badge">Desactive</span>
    </div>
    <div style="font-size: 11.5px; opacity: 0.8; margin-top: 2px;">
      L'arriere-plan Spotlight est desactive.
    </div>
    <div class="spotlight-card-actions">
      <button class="spotlight-card-btn" onclick="pycmd('spotlight:toggle_enabled')" title="Reactiver l'arriere-plan Spotlight">
        <span>Activer</span>
      </button>
    </div>
  </div>
</div>
"""
            return f"{content_tree}\n{toolbar_html}"

        if not self.db.current:
            return content_tree

        meta = self.db.current
        title = meta.get("title", "Image active")
        if len(title) > 65:
            title = title[:62] + "..."
        safe_title = html.escape(title)

        theme_key = meta.get("theme", "")
        theme_label = THEME_LABELS.get(theme_key)
        if not theme_label:
            for src in conf.get("custom_flickr_sources", []):
                if src.get("id") == theme_key:
                    theme_label = src.get("name")
                    break
        if not theme_label:
            theme_label = theme_key.replace("custom_", "Flickr ").replace("_", " ").title()
        safe_theme = html.escape(theme_label)

        # Nettoyage et préparation de la description
        desc_raw = meta.get("description", "").strip()
        desc_clean = re.sub(r"<[^>]+>", " ", desc_raw)
        desc_clean = " ".join(desc_clean.split())

        desc_html = ""
        if desc_clean:
            max_desc_len = 160
            if len(desc_clean) > max_desc_len:
                cut_text = desc_clean[:max_desc_len].rsplit(" ", 1)[0]
                desc_html = f"""
<div class="spotlight-card-desc" onclick="pycmd('spotlight:info')" title="Cliquez pour afficher tous les détails de la photo">
  <span>{html.escape(cut_text)}...</span> <span class="spotlight-more-link">plus de détails</span>
</div>
"""
            else:
                desc_html = f"""
<div class="spotlight-card-desc" onclick="pycmd('spotlight:info')" title="Cliquez pour afficher les informations détaillées">
  <span>{html.escape(desc_clean)}</span>
</div>
"""

        # Métadonnées complémentaires : Auteur, Date, Source
        author_raw = meta.get("author", "").strip()
        author_clean = re.sub(r"<[^>]+>", " ", author_raw)
        if "\n" in author_clean:
            author_clean = author_clean.split("\n")[0].strip()
        author_clean = " ".join(author_clean.split())
        if len(author_clean) > 36:
            author_clean = author_clean[:33] + "..."

        date_raw = meta.get("date", "").strip()
        date_clean = " ".join(date_raw.split())
        if len(date_clean) > 22:
            date_clean = date_clean[:20] + "..."

        source_raw = meta.get("source_name", "").strip()
        source_clean = " ".join(source_raw.split())
        if len(source_clean) > 32:
            source_clean = source_clean[:29] + "..."

        meta_rows = []
        if author_clean:
            meta_rows.append(
                f'<div class="spotlight-meta-row"><span class="spotlight-meta-label">Auteur</span><span class="spotlight-meta-val" title="{html.escape(author_raw)}">{html.escape(author_clean)}</span></div>'
            )
        if date_clean:
            meta_rows.append(
                f'<div class="spotlight-meta-row"><span class="spotlight-meta-label">Date</span><span class="spotlight-meta-val">{html.escape(date_clean)}</span></div>'
            )
        if source_clean:
            meta_rows.append(
                f'<div class="spotlight-meta-row"><span class="spotlight-meta-label">Source</span><span class="spotlight-meta-val">{html.escape(source_clean)}</span></div>'
            )

        meta_list_html = (
            f'<div class="spotlight-meta-list">{"".join(meta_rows)}</div>'
            if meta_rows
            else ""
        )

        if not desc_html and not meta_list_html:
            desc_html = """
<div class="spotlight-card-desc spotlight-card-desc-empty" onclick="pycmd('spotlight:info')" title="Cliquez pour ouvrir la fiche complète">
  <span class="spotlight-more-link">Consulter les détails de la photo...</span>
</div>
"""

        is_fav = meta.get("is_favorite", False)
        status_text = "Favori" if is_fav else "Découverte"
        fav_badge_class = "is-fav" if is_fav else ""
        like_btn_text = "Aimée (Favori)" if is_fav else "J'aime"
        fav_btn_class = "is-fav-active" if is_fav else ""

        toolbar_html = f"""
<style>
#spotlight-deck-container {{
  display: flex;
  justify-content: center;
  width: 100%;
  margin: 24px auto 16px auto;
  box-sizing: border-box;
  isolation: isolate;
}}

#spotlight-deck-card {{
  width: 100%;
  max-width: 580px;
  box-sizing: border-box;
  padding: 12px 16px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.90);
  border: 1px solid rgba(0, 0, 0, 0.12);
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.05);
  font-size: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  text-align: left;
  color: var(--fg, #222);
}}

:root[class*="night_mode"] #spotlight-deck-card,
:root.night-mode #spotlight-deck-card,
body.night_mode #spotlight-deck-card,
body.nightMode #spotlight-deck-card {{
  background: rgba(34, 34, 34, 0.90);
  border-color: rgba(255, 255, 255, 0.14);
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.25);
  color: var(--fg, #e0e0e0);
}}

.spotlight-card-top {{
  display: flex;
  flex-direction: column;
  gap: 3px;
}}

.spotlight-card-header-line {{
  display: flex;
  justify-content: space-between;
  align-items: center;
}}

.spotlight-card-label {{
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.8px;
  opacity: 0.6;
  text-transform: uppercase;
}}

.spotlight-card-status-badge {{
  font-size: 10px;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 4px;
  background: rgba(128, 128, 128, 0.18);
  color: var(--fg, #444);
}}

.spotlight-card-status-badge.is-fav {{
  background: rgba(33, 150, 243, 0.2);
  color: #1976d2;
}}

:root[class*="night_mode"] .spotlight-card-status-badge.is-fav,
:root.night-mode .spotlight-card-status-badge.is-fav,
body.night_mode .spotlight-card-status-badge.is-fav,
body.nightMode .spotlight-card-status-badge.is-fav {{
  background: rgba(33, 150, 243, 0.3);
  color: #90caf9;
}}

.spotlight-card-title {{
  font-size: 13px;
  font-weight: 700;
  line-height: 1.35;
  cursor: pointer;
  color: var(--fg, #111);
  word-break: break-word;
}}

:root[class*="night_mode"] .spotlight-card-title,
:root.night-mode .spotlight-card-title,
body.night_mode .spotlight-card-title,
body.nightMode .spotlight-card-title {{
  color: var(--fg, #eee);
}}

.spotlight-card-title:hover {{
  text-decoration: underline;
  opacity: 0.85;
}}

.spotlight-card-theme {{
  font-size: 11px;
  opacity: 0.7;
  line-height: 1.3;
}}

.spotlight-card-middle {{
  display: flex;
  flex-direction: column;
  gap: 4px;
}}

.spotlight-card-desc {{
  font-size: 11.5px;
  line-height: 1.4;
  opacity: 0.88;
  cursor: pointer;
  padding: 6px 8px;
  border-radius: 4px;
  background: rgba(128, 128, 128, 0.07);
  border: 1px solid rgba(128, 128, 128, 0.12);
  word-break: break-word;
}}

.spotlight-card-desc:hover {{
  background: rgba(128, 128, 128, 0.12);
  border-color: rgba(128, 128, 128, 0.22);
}}

:root[class*="night_mode"] .spotlight-card-desc,
:root.night-mode .spotlight-card-desc,
body.night_mode .spotlight-card-desc,
body.nightMode .spotlight-card-desc {{
  background: rgba(255, 255, 255, 0.05);
  border-color: rgba(255, 255, 255, 0.1);
}}

.spotlight-more-link {{
  color: var(--fg-link, #2563eb);
  font-weight: 600;
  text-decoration: underline;
  cursor: pointer;
  margin-left: 3px;
  white-space: nowrap;
}}

:root[class*="night_mode"] .spotlight-more-link,
:root.night-mode .spotlight-more-link,
body.night_mode .spotlight-more-link,
body.nightMode .spotlight-more-link {{
  color: #90caf9;
}}

.spotlight-meta-list {{
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 0 2px;
}}

.spotlight-meta-row {{
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 8px;
  font-size: 11px;
  line-height: 1.35;
}}

.spotlight-meta-label {{
  opacity: 0.6;
  font-weight: 600;
  font-size: 9.5px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  flex-shrink: 0;
}}

.spotlight-meta-val {{
  opacity: 0.85;
  text-align: right;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 11px;
}}

.spotlight-card-actions {{
  display: flex;
  flex-direction: row;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 4px;
}}

.spotlight-card-btn {{
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 8px;
  font-size: 11px;
  font-weight: 500;
  cursor: pointer;
  border-radius: 4px;
  border: 1px solid var(--border-subtle, rgba(128, 128, 128, 0.25));
  background: var(--button-bg, rgba(255, 255, 255, 0.7));
  color: var(--fg, #222);
  box-sizing: border-box;
}}

:root[class*="night_mode"] .spotlight-card-btn,
:root.night-mode .spotlight-card-btn,
body.night_mode .spotlight-card-btn,
body.nightMode .spotlight-card-btn {{
  background: var(--button-bg, rgba(50, 50, 50, 0.75));
  border-color: var(--border-subtle, rgba(255, 255, 255, 0.2));
  color: var(--fg, #eee);
}}

.spotlight-card-btn:hover {{
  background: var(--button-gradient-start, #fff);
  border-color: var(--button-hover-border, #999);
}}

:root[class*="night_mode"] .spotlight-card-btn:hover,
:root.night-mode .spotlight-card-btn:hover,
body.night_mode .spotlight-card-btn:hover,
body.nightMode .spotlight-card-btn:hover {{
  background: var(--button-gradient-start, #383838);
  border-color: rgba(255, 255, 255, 0.35);
}}

.spotlight-card-btn.is-fav-active {{
  background: rgba(33, 150, 243, 0.22) !important;
  border-color: rgba(33, 150, 243, 0.55) !important;
  font-weight: 600;
}}

.spotlight-shortcut-badge {{
  font-size: 10px;
  opacity: 0.65;
  font-family: monospace;
  padding: 1px 4px;
  border-radius: 2px;
  background: rgba(128, 128, 128, 0.16);
}}
</style>

<div id="spotlight-deck-container">
  <div id="spotlight-deck-card">
    <div class="spotlight-card-top">
      <div class="spotlight-card-header-line">
        <span class="spotlight-card-label">Arriere-plan</span>
        <span class="spotlight-card-status-badge {fav_badge_class}">{status_text}</span>
      </div>
      <div class="spotlight-card-title" onclick="pycmd('spotlight:info')" title="Cliquez pour afficher les informations detaillees de la photo">
        {safe_title}
      </div>
      <div class="spotlight-card-theme">
        {safe_theme}
      </div>
    </div>

    <div class="spotlight-card-middle">
      {desc_html}
      {meta_list_html}
    </div>

    <div class="spotlight-card-actions">
      <button class="spotlight-card-btn {fav_btn_class}" onclick="pycmd('spotlight:like')" title="Garder en favori permanent (Ctrl+J)">
        <span>{like_btn_text}</span>
        <span class="spotlight-shortcut-badge">Ctrl+J</span>
      </button>
      <button class="spotlight-card-btn" onclick="pycmd('spotlight:dislike')" title="Ne plus afficher cette photo (Ctrl+K)">
        <span>Ne plus afficher</span>
        <span class="spotlight-shortcut-badge">Ctrl+K</span>
      </button>
      <button class="spotlight-card-btn" onclick="pycmd('spotlight:next')" title="Photo suivante (Ctrl+;)">
        <span>Suivante</span>
        <span class="spotlight-shortcut-badge">Ctrl+;</span>
      </button>
      <button class="spotlight-card-btn" onclick="pycmd('spotlight:toggle_enabled')" title="Desactiver l'arriere-plan Spotlight">
        <span>Desactiver</span>
      </button>
    </div>
  </div>
</div>
"""
        return f"{content_tree}\n{toolbar_html}"

    def handle_js_message(
        self, handled: Tuple[bool, Any], message: str, context: Any
    ) -> Tuple[bool, Any]:
        """Intercepte les clics depuis le bandeau DeckBrowser."""
        if not message.startswith("spotlight:"):
            return handled

        cmd = message[len("spotlight:"):]
        if cmd == "like":
            self.on_like()
            return (True, None)
        elif cmd == "dislike":
            self.on_dislike()
            return (True, None)
        elif cmd == "next":
            self.on_next()
            return (True, None)
        elif cmd == "info":
            self.show_current_info()
            return (True, None)
        elif cmd == "open_folder":
            self.on_open_favorites_folder()
            return (True, None)
        elif cmd == "add_photos":
            self.on_add_photos()
            return (True, None)
        elif cmd == "toggle_enabled":
            self.on_toggle_enabled()
            return (True, None)

        return handled
