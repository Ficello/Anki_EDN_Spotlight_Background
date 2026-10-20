# -*- coding: utf-8 -*-
"""Base de données et gestionnaire des favoris/liste noire Spotlight."""

from __future__ import annotations
import hashlib
import json
import os
import random
import shutil
import time
from typing import Any, Dict, List, Optional


class SpotlightDB:
    def __init__(self, addon_dir: str):
        self.addon_dir = addon_dir
        self.user_files_dir = os.path.join(addon_dir, "user_files")
        self.favorites_dir = os.path.join(self.user_files_dir, "favorites")
        self.cache_dir = os.path.join(self.user_files_dir, "cache")
        self.default_dir = os.path.join(self.user_files_dir, "default")
        self.db_path = os.path.join(self.user_files_dir, "spotlight.json")

        os.makedirs(self.favorites_dir, exist_ok=True)
        os.makedirs(self.cache_dir, exist_ok=True)
        os.makedirs(self.default_dir, exist_ok=True)

        self.current: Optional[Dict[str, Any]] = None
        self.favorites: Dict[str, Dict[str, Any]] = {}
        self.blacklisted: List[str] = []
        self.history: List[str] = []
        self.load()

    def load(self) -> None:
        if not os.path.exists(self.db_path):
            self.save()
            return
        try:
            with open(self.db_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.current = data.get("current")
                self.favorites = data.get("favorites", {})
                self.blacklisted = data.get("blacklisted", [])
                self.history = data.get("history", [])
        except Exception:
            self.favorites = {}
            self.blacklisted = []
            self.history = []
        self.sync_favorites_folder()

    def save(self) -> None:
        temp_path = self.db_path + ".tmp"
        data = {
            "current": self.current,
            "favorites": self.favorites,
            "blacklisted": self.blacklisted[-1000:],  # Garder les 1000 derniers rejets
            "history": self.history[-100:],
        }
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            if os.path.exists(self.db_path):
                os.replace(temp_path, self.db_path)
            else:
                os.rename(temp_path, self.db_path)
        except Exception:
            pass

    def is_blacklisted(self, img_id: str, url: str = "") -> bool:
        return img_id in self.blacklisted or (bool(url) and url in self.blacklisted)

    def like_current(self) -> bool:
        """Marque l'image courante comme aimée : la stocke dans favorites/."""
        if not self.current:
            return False

        img_id = self.current.get("id")
        if not img_id:
            return False

        # Si l'image est dans le cache ou default, on la copie dans favorites
        current_path = self.current.get("local_path", "")
        if current_path and os.path.exists(current_path):
            filename = os.path.basename(current_path)
            dest_path = os.path.join(self.favorites_dir, filename)
            if current_path != dest_path:
                try:
                    shutil.copy2(current_path, dest_path)
                except Exception:
                    pass
            self.current["local_path"] = dest_path

        self.current["is_favorite"] = True
        self.current["liked_at"] = time.time()
        self.favorites[img_id] = dict(self.current)
        self.save()
        return True

    def dislike_current(self) -> bool:
        """Rejette l'image courante : l'ajoute à la liste noire et supprime son fichier."""
        if not self.current:
            return False

        img_id = self.current.get("id")
        if not img_id:
            return False

        self.blacklisted.append(img_id)
        if self.current.get("image_url"):
            self.blacklisted.append(self.current["image_url"])

        # Retirer des favoris si elle y était
        if img_id in self.favorites:
            del self.favorites[img_id]

        # Supprimer le fichier local s'il n'est pas dans le dossier par défaut
        current_path = self.current.get("local_path", "")
        if current_path and os.path.exists(current_path):
            if not current_path.startswith(self.default_dir):
                try:
                    os.remove(current_path)
                except Exception:
                    pass

        self.current = None
        self.save()
        return True

    def set_current(self, metadata: Dict[str, Any]) -> None:
        img_id = metadata.get("id", "")
        metadata["is_favorite"] = img_id in self.favorites
        self.current = metadata
        if img_id and img_id not in self.history:
            self.history.append(img_id)
        self.save()

    def sync_favorites_folder(self) -> int:
        """Scanne le dossier favorites/ pour synchroniser automatiquement les images ajoutées par l'utilisateur."""
        if not os.path.exists(self.favorites_dir):
            return 0

        valid_exts = (".jpg", ".jpeg", ".png", ".webp")
        added_count = 0

        try:
            filenames = os.listdir(self.favorites_dir)
        except Exception:
            return 0

        # Nettoyer les favoris dont le fichier local a été supprimé du disque
        for fid in list(self.favorites.keys()):
            lpath = self.favorites[fid].get("local_path", "")
            if lpath and not os.path.exists(lpath):
                del self.favorites[fid]

        # Indexer les chemins existants
        known_paths = {
            os.path.abspath(f.get("local_path", "")).lower()
            for f in self.favorites.values()
            if f.get("local_path")
        }

        for fname in filenames:
            if not fname.lower().endswith(valid_exts):
                continue
            full_path = os.path.join(self.favorites_dir, fname)
            if not os.path.isfile(full_path):
                continue

            norm_path = os.path.abspath(full_path).lower()
            if norm_path not in known_paths:
                file_hash = hashlib.md5(fname.encode("utf-8")).hexdigest()[:10]
                img_id = f"custom_fav_{file_hash}"
                if img_id in self.favorites:
                    img_id = f"custom_fav_{file_hash}_{int(time.time())}"

                if self.is_blacklisted(img_id):
                    continue

                clean_title = os.path.splitext(fname)[0].replace("_", " ").replace("-", " ").title()
                ctime = os.path.getctime(full_path) if os.path.exists(full_path) else time.time()
                self.favorites[img_id] = {
                    "id": img_id,
                    "title": clean_title,
                    "theme": "custom_personal",
                    "source_name": "Collection personnelle",
                    "author": "Utilisateur",
                    "date": "",
                    "description": "Photo personnelle ajoutée dans le dossier des favoris.",
                    "page_url": "",
                    "local_path": full_path,
                    "is_favorite": True,
                    "liked_at": ctime,
                }
                known_paths.add(norm_path)
                added_count += 1

        if added_count > 0:
            self.save()
        return added_count

    def get_random_favorite(self, exclude_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Sélectionne une image aimée au hasard."""
        self.sync_favorites_folder()
        valid_favs = [
            f for fid, f in self.favorites.items()
            if fid != exclude_id and os.path.exists(f.get("local_path", ""))
        ]
        if not valid_favs:
            # S'il n'y en a qu'une seule et qu'elle correspond à exclude_id
            all_favs = [f for f in self.favorites.values() if os.path.exists(f.get("local_path", ""))]
            return random.choice(all_favs) if all_favs else None
        return random.choice(valid_favs)

    def get_fallback_default(self) -> Optional[Dict[str, Any]]:
        """Sélectionne une image d'arrière-plan de secours locale."""
        if not os.path.exists(self.default_dir):
            return None
        valid_files = [
            f for f in os.listdir(self.default_dir)
            if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
        ]
        if not valid_files:
            return None
        chosen = random.choice(valid_files)
        path = os.path.join(self.default_dir, chosen)
        title = os.path.splitext(chosen)[0].replace("_", " ")
        return {
            "id": f"default_{chosen}",
            "title": title,
            "theme": "default",
            "source_name": "Collection locale",
            "page_url": "",
            "local_path": path,
            "is_favorite": False,
        }

    def cleanup_old_cache(self, keep_count: int = 5) -> None:
        """Nettoie le dossier temporaire de cache pour limiter strictement l'espace disque."""
        try:
            current_path = self.current.get("local_path", "") if self.current else ""
            all_entries = os.listdir(self.cache_dir)

            # 1. Nettoyer immédiatement tout fichier .tmp temporaire
            for name in all_entries:
                full_path = os.path.join(self.cache_dir, name)
                if name.endswith(".tmp") and os.path.isfile(full_path):
                    try:
                        os.remove(full_path)
                    except Exception:
                        pass

            # 2. Récupérer les vraies images de cache
            files = [
                os.path.join(self.cache_dir, f)
                for f in os.listdir(self.cache_dir)
                if os.path.isfile(os.path.join(self.cache_dir, f)) and not f.endswith(".tmp")
            ]

            if len(files) <= keep_count:
                return

            # Trier par date de modification croissante (les plus anciens d'abord)
            files.sort(key=lambda p: os.path.getmtime(p))

            # Supprimer les plus anciens au-delà du quota
            to_remove = files[:-keep_count]
            for old_file in to_remove:
                if old_file != current_path:
                    try:
                        os.remove(old_file)
                    except Exception:
                        pass
        except Exception:
            pass

    def get_disk_usage(self) -> Dict[str, Any]:
        """Calcule le nombre de photos et l'espace disque utilisé (en Mo)."""
        self.sync_favorites_folder()
        def dir_stats(folder: str) -> tuple[int, float]:
            if not os.path.exists(folder):
                return 0, 0.0
            count = 0
            total_bytes = 0
            for name in os.listdir(folder):
                p = os.path.join(folder, name)
                if os.path.isfile(p):
                    count += 1
                    total_bytes += os.path.getsize(p)
            return count, round(total_bytes / (1024 * 1024), 2)

        fav_count, fav_mb = dir_stats(self.favorites_dir)
        cache_count, cache_mb = dir_stats(self.cache_dir)
        return {
            "fav_count": fav_count,
            "fav_mb": fav_mb,
            "cache_count": cache_count,
            "cache_mb": cache_mb,
            "total_mb": round(fav_mb + cache_mb, 2),
        }

