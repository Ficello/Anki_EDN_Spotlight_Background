# -*- coding: utf-8 -*-
"""Moteur d'injection CSS pour l'application du fond d'écran dans Anki."""

from __future__ import annotations
import os
import shutil
import time
from typing import Any, Callable, Dict, Optional

CSS_FILES_TO_INJECT = {
    "deckbrowser.css",
    "overview.css",
    "reviewer.css",
    "reviewer-bottom.css",
    "toolbar.css",
    "toolbar-bottom.css",
}


class CSSEngine:
    def __init__(self, addon_package: str, addon_dir: str, get_config: Callable[[], Dict[str, Any]]):
        self.addon_package = addon_package
        self.addon_dir = addon_dir
        self.get_config = get_config
        self.current_web_url: str = ""
        self.last_update_ts: int = 0

    def update_current_image(self, local_path: str) -> None:
        """Définit l'image d'arrière-plan active et prépare l'URL web Anki."""
        if not local_path or not os.path.exists(local_path):
            self.current_web_url = ""
            return

        dest_path = os.path.join(self.addon_dir, "user_files", "current_background.jpg")
        try:
            # Optimisation haute performance : redimensionner a la resolution cible de l'ecran (QHD, Retina, 4K)
            optimized = False
            try:
                target_w = 2560
                target_h = 1440
                try:
                    from .sources import get_screen_target_resolution
                    target_w = get_screen_target_resolution(default_width=2560)
                    target_h = int(target_w * 10 / 16) if target_w == 2880 else int(target_w * 9 / 16)
                except Exception:
                    pass

                from aqt.qt import QImage, QSize, Qt
                qimg = QImage(local_path)
                if not qimg.isNull():
                    if qimg.width() > target_w or qimg.height() > target_h:
                        qimg = qimg.scaled(
                            QSize(target_w, target_h),
                            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                            Qt.TransformationMode.SmoothTransformation,
                        )
                    qimg.save(dest_path, "JPEG", 85)
                    optimized = True
            except Exception:
                pass

            if not optimized:
                shutil.copy2(local_path, dest_path)

            self.last_update_ts = int(time.time())
            self.current_web_url = f"/_addons/{self.addon_package}/user_files/current_background.jpg?v={self.last_update_ts}"
        except Exception:
            # Fallback vers chemin relatif direct
            rel = os.path.relpath(local_path, self.addon_dir).replace("\\", "/")
            self.last_update_ts = int(time.time())
            self.current_web_url = f"/_addons/{self.addon_package}/{rel}?v={self.last_update_ts}"

    def build_css(self, is_reviewer: bool = False, location: str = "body") -> str:
        """Génère le bloc CSS body::before adapté au contexte."""
        if not self.current_web_url:
            return ""

        conf = self.get_config()
        if not conf.get("enabled", True):
            return "body::before { display: none !important; }"

        if is_reviewer and not conf.get("reviewer_image", True):
            return "body::before { display: none !important; }"

        if location in ("top", "bottom") and not conf.get("toolbar_image", True):
            return "body::before { display: none !important; }"

        # En mode review, la barre du haut doit adopter l'opacité configurée pour le reviewer
        use_reviewer_opacity = is_reviewer
        if location in ("top", "bottom"):
            try:
                from aqt import mw
                if mw and getattr(mw, "state", None) == "review":
                    use_reviewer_opacity = True
            except Exception:
                pass

        opacity = conf.get("opacity_reviewer" if use_reviewer_opacity else "opacity_main", 0.9)
        blur = conf.get("blur_radius", 0)
        size = conf.get("background_size", "cover")

        if location == "top":
            position = "top center"
        elif location == "bottom":
            position = "bottom center"
        else:
            position = conf.get("background_position", "center")

        filter_css = f"filter: blur({blur}px);" if blur > 0 else ""

        # Styles pour les barres d'outils (transparentes) vs le corps principal (html opaque, body transparent)
        if location in ("top", "bottom"):
            return f"""
html, body {{
    background: transparent !important;
    background-color: transparent !important;
    opacity: 1 !important;
}}
#outer, #header, .header {{
    background: transparent !important;
}}
body::before {{
    content: "";
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background-image: url("{self.current_web_url}");
    background-size: {size} !important;
    background-repeat: no-repeat;
    background-position: {position} !important;
    opacity: {opacity};
    {filter_css}
    z-index: -1;
    pointer-events: none;
}}
"""
        else:
            # Pour deck browser, overview et reviewer :
            # La racine html conserve un fond solide pour que Chromium ne bascule pas
            # en passe de composition alpha transparente qui corrompt le dessin des cartes.
            return f"""
html {{
    background-color: var(--canvas, #2f2f31) !important;
}}
body {{
    position: relative !important;
    isolation: isolate !important;
    background: transparent !important;
    background-color: transparent !important;
    opacity: 1 !important;
}}
body::before {{
    content: "";
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background-image: url("{self.current_web_url}");
    background-size: {size} !important;
    background-repeat: no-repeat;
    background-position: {position} !important;
    opacity: {opacity};
    {filter_css}
    z-index: -1;
    pointer-events: none;
}}
"""

    def update_all_views(self) -> None:
        """Met a jour instantanement le style injecte dans toutes les vues web actives sans rechargement lourd."""
        from aqt import mw
        if not mw or not self.current_web_url:
            return

        conf = self.get_config()
        is_review = getattr(mw, "state", None) == "review"

        def _inject(web: Any, css: str) -> None:
            if not web:
                return
            js = f"""
(() => {{
    let head = document.head || document.getElementsByTagName('head')[0] || document.documentElement;
    if (!head) return;
    let el = document.getElementById('anki-spotlight-bg');
    if (!el) {{
        el = document.createElement('style');
        el.id = 'anki-spotlight-bg';
        head.appendChild(el);
    }}
    el.textContent = {repr(css)};
    if (document.body) {{
        document.body.style.opacity = '';
    }}
}})();
"""
            try:
                web.eval(js)
            except Exception:
                pass

        # 1. Barres d'outils haut et bas
        if is_review and not conf.get("reviewer_image", True):
            top_css = "body::before { display: none !important; }"
            bottom_css = "body::before { display: none !important; }"
        elif not conf.get("toolbar_image", True):
            top_css = "body::before { display: none !important; }"
            bottom_css = "body::before { display: none !important; }"
        else:
            top_css = self.build_css(is_reviewer=is_review, location="top")
            bottom_css = self.build_css(is_reviewer=is_review, location="bottom")

        if hasattr(mw, "toolbarWeb") and mw.toolbarWeb:
            _inject(mw.toolbarWeb, top_css)
        if hasattr(mw, "bottomWeb") and mw.bottomWeb:
            _inject(mw.bottomWeb, bottom_css)

        # 2. Reviewer : mettre a jour instantanement le fond de la carte sans recharger uniquement en mode review
        if is_review and hasattr(mw, "reviewer") and mw.reviewer and hasattr(mw.reviewer, "web") and mw.reviewer.web:
            rev_css = self.build_css(is_reviewer=True, location="body")
            _inject(mw.reviewer.web, rev_css)

        # 3. DeckBrowser (si actif)
        if getattr(mw, "state", None) == "deckBrowser" and hasattr(mw, "deckBrowser") and hasattr(mw.deckBrowser, "web"):
            db_css = self.build_css(is_reviewer=False, location="body")
            _inject(mw.deckBrowser.web, db_css)

        # 4. Overview (si actif)
        if getattr(mw, "state", None) == "overview" and hasattr(mw, "overview") and hasattr(mw.overview, "web"):
            ov_css = self.build_css(is_reviewer=False, location="body")
            _inject(mw.overview.web, ov_css)

    def update_toolbar_styles(self) -> None:
        """Alias pour update_all_views."""
        self.update_all_views()

    def on_webview_will_set_content(self, web_content: Any, context: Any) -> None:
        """Hook pour injecter le CSS dans les vues web d'Anki."""
        if not self.current_web_url:
            return

        context_name = type(context).__name__.lower() if context else ""
        css_files = [os.path.basename(f).lower() for f in getattr(web_content, "css", [])]

        # Ne pas injecter dans l'editeur ou les fenetres de saisie/dialogues
        if "editor" in context_name or any("editor" in f for f in css_files):
            return

        # S'assurer que la vue fait bien partie des cibles prevues
        allowed_contexts = ("deckbrowser", "overview", "reviewer", "toptoolbar", "bottomtoolbar", "toolbar")
        has_allowed_context = any(c in context_name for c in allowed_contexts)
        has_allowed_css = any(f in CSS_FILES_TO_INJECT for f in css_files)

        if not (has_allowed_context or has_allowed_css):
            return

        is_reviewer = "reviewer" in context_name or any("reviewer" in f for f in css_files)

        is_bottom = (
            "bottom" in context_name
            or any("bottom" in f for f in css_files)
        )
        is_top = (
            not is_bottom
            and ("top" in context_name or any(f in ("toolbar.css", "toolbar") for f in css_files))
        )

        location = "bottom" if is_bottom else ("top" if is_top else "body")

        css = self.build_css(is_reviewer=is_reviewer, location=location)
        if css:
            web_content.head += f"<style id='anki-spotlight-bg'>{css}</style>"
            if is_reviewer:
                web_content.head += """
<script id="anki-spotlight-repaint-hook">
(function() {
    function triggerRepaint() {
        if (typeof bridgeCommand === 'function') {
            bridgeCommand('repaintNeeded');
        }
    }
    function setupObserver() {
        var qa = document.getElementById('qa');
        if (!qa) {
            setTimeout(setupObserver, 20);
            return;
        }
        var obs = new MutationObserver(function(mutations) {
            for (var i = 0; i < mutations.length; i++) {
                var m = mutations[i];
                if (m.type === 'attributes' && m.attributeName === 'style') {
                    if (qa.style.opacity === '1' || qa.style.opacity === '') {
                        requestAnimationFrame(triggerRepaint);
                    }
                } else if (m.type === 'childList') {
                    requestAnimationFrame(triggerRepaint);
                }
            }
        });
        obs.observe(qa, { attributes: true, attributeFilter: ['style'], childList: true });
    }
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', setupObserver);
    } else {
        setupObserver();
    }
})();
</script>
"""

    def on_webview_did_inject_style(self, web: Any) -> None:
        """Injecte le style dans les pages Congrats / SvelteKit / TypeScript d'Anki."""
        from aqt import mw
        if not self.current_web_url or not web:
            return
        try:
            is_main_web = bool(mw and hasattr(mw, "web") and web is mw.web)
            page_obj = web.page()
            url = page_obj.url() if page_obj else None
            url_str = url.toString().lower() if url else ""
            path = url.path().lower() if url else ""
            page = os.path.basename(path.rstrip("/"))

            is_congrats = "congrats" in url_str or page == "congrats"

            # Ne cibler que congrats ou la fenetre principale mw.web hors reviewer
            if not (is_congrats or (is_main_web and getattr(mw, "state", None) in ("overview", "deckBrowser"))):
                return
        except Exception:
            return

        css = self.build_css(is_reviewer=False, location="body")
        if css:
            js_code = f"""
(() => {{
    function injectBg() {{
        let head = document.head || document.getElementsByTagName('head')[0] || document.documentElement;
        if (!head) return;
        let el = document.getElementById('anki-spotlight-bg');
        if (!el) {{
            el = document.createElement('style');
            el.id = 'anki-spotlight-bg';
            head.appendChild(el);
        }}
        el.textContent = {repr(css)};
        if (document.body) {{
            document.body.style.opacity = '';
        }}
    }}
    injectBg();
    if (document.readyState === 'loading') {{
        document.addEventListener('DOMContentLoaded', injectBg);
    }}
    window.addEventListener('load', injectBg);
}})();
"""
            try:
                web.eval(js_code)
            except Exception:
                pass
