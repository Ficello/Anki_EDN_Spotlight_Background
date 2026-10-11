# -*- coding: utf-8 -*-
"""Gestionnaire de téléchargement asynchrone et préchargement (prefetch)."""

from __future__ import annotations
import hashlib
import os
import random
import re
import threading
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, List, Optional

from .sources import USER_AGENT, fetch_candidates_for_theme
from .spotlight_db import SpotlightDB


def download_image(url: str, dest_path: str, timeout: int = 15) -> bool:
    """Télécharge une image de manière sécurisée avec remplacement atomique."""
    temp_path = dest_path + ".tmp"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content = resp.read()
            if len(content) < 5000:  # Moins de 5 Ko : probablement une erreur ou image tronquée
                return False
            with open(temp_path, "wb") as f:
                f.write(content)
        if os.path.exists(dest_path):
            os.replace(temp_path, dest_path)
        else:
            os.rename(temp_path, dest_path)
        return True
    except Exception:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        return False


class BackgroundPrefetcher:
    """Télécharge à l'avance des images candidates en arrière-plan."""

    def __init__(self, db: SpotlightDB, get_config: Callable[[], Dict[str, Any]]):
        self.db = db
        self.get_config = get_config
        self.queue: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self._is_running = False
        self._thread: Optional[threading.Thread] = None

    def get_ready_candidate(self) -> Optional[Dict[str, Any]]:
        """Extrait une image fraîche pré-téléchargée de la file d'attente."""
        with self._lock:
            while self.queue:
                candidate = self.queue.pop(0)
                local_path = candidate.get("local_path", "")
                if os.path.exists(local_path) and not self.db.is_blacklisted(candidate.get("id", "")):
                    # Déclencher le réapprovisionnement de la file
                    self.trigger_prefetch()
                    return candidate
        # Si la file est vide, déclencher un chargement
        self.trigger_prefetch()
        return None

    def trigger_prefetch(self) -> None:
        """Lance le préchargement en arrière-plan si ce n'est pas déjà en cours."""
        if self._is_running:
            return
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def _worker(self) -> None:
        self._is_running = True
        try:
            with self._lock:
                q_len = len(self.queue)
            if q_len >= 2:
                return

            config = self.get_config()
            themes = config.get("enabled_themes", ["nasa_hubble", "geography", "maps", "marine_animals", "land_animals"])
            if not themes:
                return

            # Détection de la résolution d'écran cible si configuré
            adapt_res = config.get("adapt_screen_resolution", True)
            target_width = 2560
            if adapt_res:
                from .sources import get_screen_target_resolution
                target_width = get_screen_target_resolution(default_width=2560)

            custom_sources = config.get("custom_flickr_sources", [])

            # Choisir un thème au hasard parmi les thèmes activés
            theme = random.choice(themes)
            candidates = fetch_candidates_for_theme(
                theme=theme,
                count=15,
                target_width=target_width,
                custom_sources=custom_sources,
            )
            if not candidates:
                return

            # Filtrer les candidats déjà vus ou en liste noire
            valid_candidates = [
                c for c in candidates
                if not self.db.is_blacklisted(c["id"], c.get("image_url", ""))
                and c["id"] not in self.db.history[-25:]
            ]

            if not valid_candidates:
                valid_candidates = candidates

            random.shuffle(valid_candidates)
            for cand in valid_candidates[:2]:
                url = cand.get("image_url")
                if not url:
                    continue

                # Générer un nom de fichier propre basé sur le hash de l'URL
                url_hash = hashlib.md5(url.encode("utf-8")).hexdigest()[:12]
                ext = ".jpg"
                if ".png" in url.lower():
                    ext = ".png"
                elif ".webp" in url.lower():
                    ext = ".webp"

                filename = f"spotlight_{cand['theme']}_{url_hash}{ext}"
                target_path = os.path.join(self.db.cache_dir, filename)

                if os.path.exists(target_path) or download_image(url, target_path):
                    cand_copy = dict(cand)
                    cand_copy["local_path"] = target_path
                    with self._lock:
                        if len(self.queue) < 3:
                            self.queue.append(cand_copy)
                    # Si on en a assez, on s'arrête
                    with self._lock:
                        if len(self.queue) >= 2:
                            break

            # Nettoyer les fichiers de cache au-delà du quota strict configuré
            max_cached = int(config.get("max_cached_images", 5))
            self.db.cleanup_old_cache(keep_count=max_cached)
        except Exception:
            pass
        finally:
            self._is_running = False
