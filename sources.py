# -*- coding: utf-8 -*-
"""Moteur de récupération des sources d'images HD pour l'arrière-plan Spotlight."""

from __future__ import annotations
import json
import random
import re
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

USER_AGENT = "AnkiSpotlightBackground/1.0 (Mozilla/5.0 compatible; educational desktop use)"

THEME_LABELS = {
    "nasa_hubble": "NASA Hubble & Espace",
    "maps": "Cartes & Cartographie historique",
    "geography": "Géographie & Grands Paysages",
    "marine_animals": "Faune marine & Océans",
    "land_animals": "Faune terrestre & Mammifères",
    "architecture": "Architecture & Monuments du Monde",
    "paintings": "Peintures classiques & Beaux-Arts",
    "deep_space": "Ciel profond & Nébuleuses (JWST)",
    "social_movements": "Mouvements sociaux & Histoire des luttes",
    "botanical": "Botanique & Flore macro",
    "microscopy": "Microscopie & Monde miniature",
}

WIKI_QUERIES = {
    "maps": "filetype:bitmap map OR cartography OR atlas incategory:Featured_pictures_on_Wikimedia_Commons",
    "geography": "filetype:bitmap landscape OR mountain OR valley OR fjord OR glacier OR desert incategory:Featured_pictures_on_Wikimedia_Commons",
    "marine_animals": "filetype:bitmap underwater OR marine OR reef OR dolphin OR whale OR coral OR fish incategory:Featured_pictures_on_Wikimedia_Commons",
    "land_animals": "filetype:bitmap mammal OR wildlife OR lion OR tiger OR bear OR deer OR fox incategory:Featured_pictures_on_Wikimedia_Commons",
    "architecture": "filetype:bitmap architecture OR cathedral OR palace OR castle OR monument OR bridge incategory:Featured_pictures_on_Wikimedia_Commons",
    "paintings": "filetype:bitmap painting OR oil_painting OR \"fine art\" incategory:Featured_pictures_on_Wikimedia_Commons",
    "deep_space": "filetype:bitmap nebula OR galaxy OR supernova OR \"deep space\" OR \"james webb\" incategory:Featured_pictures_on_Wikimedia_Commons",
    "social_movements": "filetype:bitmap protest OR demonstration OR strike OR activist OR suffragette OR \"civil rights\" incategory:Featured_pictures_on_Wikimedia_Commons",
    "botanical": "filetype:bitmap botanical OR flora OR flower OR orchid OR \"plant anatomy\" incategory:Featured_pictures_on_Wikimedia_Commons",
    "microscopy": "filetype:bitmap microscopy OR \"scanning electron microscope\" OR micrograph incategory:Featured_pictures_on_Wikimedia_Commons",
}


def get_screen_target_resolution(default_width: int = 2560) -> int:
    """Détecte la résolution horizontale native de l'écran (avec ratio HiDPI/Retina)."""
    try:
        from aqt.qt import QGuiApplication
        screen = QGuiApplication.primaryScreen()
        if screen:
            geom = screen.size()
            dpr = screen.devicePixelRatio()
            w = int(geom.width() * dpr)
            # Échelonner par paliers standard (1080p, 2K/1440p, Retina 2.8K, 4K/UHD)
            if w >= 3400:
                return 3840
            elif w >= 2600:
                return 2880
            elif w >= 2100:
                return 2560
            elif w >= 1700:
                return 1920
            elif w > 0:
                return max(1280, w)
    except Exception:
        pass
    return default_width


def _clean_title(raw_title: str) -> str:
    cleaned = re.sub(r"^File:", "", raw_title)
    cleaned = re.sub(r"\.(jpg|jpeg|png|webp)$", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.replace("_", " ")
    return cleaned.strip()


def resolve_flickr_feed_url(user_input: str) -> Optional[str]:
    """Résout une saisie utilisateur (URL profil, album, tags ou NSID) en flux JSON Flickr public."""
    if not user_input:
        return None
    val = user_input.strip()

    # Si c'est déjà une URL de flux direct
    if "photos_public.gne" in val:
        if "format=json" not in val:
            sep = "&" if "?" in val else "?"
            val += f"{sep}format=json&nojsoncallback=1"
        return val

    # Si c'est un NSID direct (ex: 144614754@N02)
    if re.match(r"^[0-9]+@N[0-9]+$", val):
        return f"https://www.flickr.com/services/feeds/photos_public.gne?id={val}&format=json&nojsoncallback=1"

    # Si c'est une liste de tags sans slash ni schéma HTTP (ex: "landscape,japan")
    if not val.startswith("http://") and not val.startswith("https://") and "/" not in val:
        enc_tags = urllib.parse.quote(val)
        return f"https://www.flickr.com/services/feeds/photos_public.gne?tags={enc_tags}&format=json&nojsoncallback=1"

    # Si c'est une URL Flickr de profil (ex: https://www.flickr.com/photos/nasahubble/)
    if "flickr.com" in val:
        # Essayer de résoudre l'identifiant via l'oEmbed officiel Flickr
        try:
            oembed_url = f"https://www.flickr.com/services/oembed/?format=json&url={urllib.parse.quote(val)}"
            req = urllib.request.Request(oembed_url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                html_snippet = data.get("html", "")
                m = re.search(r"photos/([0-9]+@N[0-9]+)", html_snippet)
                if m:
                    nsid = m.group(1)
                    return f"https://www.flickr.com/services/feeds/photos_public.gne?id={nsid}&format=json&nojsoncallback=1"
        except Exception:
            pass

        # Extraction par regex directe du NSID si présent dans l'URL
        m_nsid = re.search(r"([0-9]+@N[0-9]+)", val)
        if m_nsid:
            return f"https://www.flickr.com/services/feeds/photos_public.gne?id={m_nsid.group(1)}&format=json&nojsoncallback=1"

    return None


def _clean_html(raw_html: str) -> str:
    """Nettoie le HTML pour en extraire un texte brut lisible et aéré."""
    if not raw_html:
        return ""
    # Retirer l'en-tête Flickr spécifique 'posted a photo:'
    text = re.sub(r"<p><a[^>]+>.*?posted a photo:.*?</p>", "", raw_html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<p><a[^>]+title=[^>]+><img[^>]+/></a></p>", "", text, flags=re.DOTALL | re.IGNORECASE)
    # Retirer les liens vers les réseaux sociaux en pied de message
    text = re.sub(r"<b>Find us on.*", "", text, flags=re.DOTALL | re.IGNORECASE)
    # Remplacer les balises de saut de ligne par des retours chariots
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n\n", text, flags=re.IGNORECASE)
    # Retirer les balises HTML restantes
    text = re.sub(r"<[^>]+>", "", text)
    # Décoder les entités HTML (&amp;, &eacute;, etc.)
    import html
    text = html.unescape(text)
    # Normaliser les sauts de lignes consécutifs
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def fetch_flickr_feed(feed_url: str, theme_name: str = "custom_flickr", source_label: str = "Flickr", count: int = 20) -> List[Dict[str, Any]]:
    """Récupère les photos depuis une URL de flux Flickr public avec métadonnées enrichies."""
    results: List[Dict[str, Any]] = []
    req = urllib.request.Request(feed_url, headers={"User-Agent": USER_AGENT})

    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            items = data.get("items", [])
            feed_title = data.get("title", source_label)
            for item in items:
                m_url = item.get("media", {}).get("m", "")
                if not m_url:
                    continue
                hd_url = m_url.replace("_m.", "_b.")
                img_id = "flickr_" + re.sub(r"\W+", "_", item.get("link", m_url))
                title = item.get("title", "").strip() or feed_title
                desc = _clean_html(item.get("description", ""))
                author = item.get("author", "")
                # Nettoyer 'nobody@flickr.com ("NASA Hubble")' -> 'NASA Hubble'
                m_author = re.search(r'\("([^"]+)"\)', author)
                if m_author:
                    author = m_author.group(1)

                results.append({
                    "id": img_id,
                    "title": title,
                    "theme": theme_name,
                    "description": desc,
                    "author": author,
                    "date": item.get("published", "")[:10],
                    "image_url": hd_url,
                    "source_name": feed_title,
                    "page_url": item.get("link", "https://www.flickr.com"),
                })
    except Exception:
        pass

    return results[:count]


def fetch_flickr_hubble(count: int = 20) -> List[Dict[str, Any]]:
    """Récupère les photos récentes de l'album officiel Flickr NASA Hubble."""
    url = "https://www.flickr.com/services/feeds/photos_public.gne?id=144614754@N02&format=json&nojsoncallback=1"
    candidates = fetch_flickr_feed(url, theme_name="nasa_hubble", source_label="NASA Hubble (Flickr)", count=count)
    if not candidates:
        return fetch_nasa_image_library(count=count)
    return candidates


def fetch_nasa_image_library(query: str = "Hubble", count: int = 25) -> List[Dict[str, Any]]:
    """Recherche dans la bibliothèque publique officielle NASA Images."""
    results: List[Dict[str, Any]] = []
    url = f"https://images-api.nasa.gov/search?q={urllib.parse.quote(query)}&media_type=image"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            items = data.get("collection", {}).get("items", [])
            random.shuffle(items)
            for item in items[:count]:
                data_list = item.get("data", [])
                links = item.get("links", [])
                if not data_list or not links:
                    continue
                info = data_list[0]
                nasa_id = info.get("nasa_id", "")
                title = info.get("title", "NASA Deep Space")
                desc = _clean_html(info.get("description", ""))
                photographer = info.get("photographer", "") or info.get("center", "NASA")
                date_created = info.get("date_created", "")[:10]
                href = links[0].get("href", "")
                hd_url = re.sub(r"~(thumb|small)\.", "~medium.", href)
                results.append({
                    "id": f"nasa_{nasa_id}",
                    "title": title,
                    "theme": "nasa_hubble",
                    "description": desc,
                    "author": photographer,
                    "date": date_created,
                    "image_url": hd_url,
                    "source_name": "NASA Image Library",
                    "page_url": f"https://images.nasa.gov/details/{nasa_id}",
                })
    except Exception:
        pass

    return results


def fetch_wikimedia(theme: str, count: int = 25, width: int = 1920) -> List[Dict[str, Any]]:
    """Récupère des images labellisées 'Featured pictures' sur Wikimedia Commons avec description."""
    query = WIKI_QUERIES.get(theme)
    if not query:
        return []

    # Décalage aléatoire pour varier les découvertes
    sroffset = random.choice([0, 10, 20, 30])
    encoded_query = urllib.parse.quote(query)
    url = (
        f"https://commons.wikimedia.org/w/api.php?action=query"
        f"&generator=search&gsrsearch={encoded_query}&gsrnamespace=6"
        f"&gsrlimit={count}&gsroffset={sroffset}"
        f"&prop=imageinfo&iiprop=url|size|extmetadata&iiurlwidth={width}&format=json"
    )
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    results: List[Dict[str, Any]] = []
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            pages = data.get("query", {}).get("pages", {})
            for page in pages.values():
                imageinfo = page.get("imageinfo", [])
                if not imageinfo:
                    continue
                info = imageinfo[0]
                img_url = info.get("thumburl") or info.get("url")
                if not img_url:
                    continue
                page_id = str(page.get("pageid", ""))
                title = _clean_title(page.get("title", "Image"))
                desc_url = info.get("descriptionurl", "")

                extmeta = info.get("extmetadata", {})
                raw_desc = extmeta.get("ImageDescription", {}).get("value", "")
                desc = _clean_html(raw_desc)
                raw_artist = extmeta.get("Artist", {}).get("value", "")
                artist = _clean_html(raw_artist)
                date_orig = extmeta.get("DateTimeOriginal", {}).get("value", "")[:10]

                # Remplacer le titre générique par ObjectName si disponible
                obj_name = extmeta.get("ObjectName", {}).get("value", "")
                if obj_name and len(obj_name.strip()) > 3:
                    title = _clean_html(obj_name.strip())

                results.append({
                    "id": f"wiki_{page_id}",
                    "title": title,
                    "theme": theme,
                    "description": desc,
                    "author": artist,
                    "date": date_orig,
                    "image_url": img_url,
                    "source_name": "Wikimedia Commons (Featured)",
                    "page_url": desc_url,
                })
    except Exception:
        pass

    return results


def fetch_candidates_for_theme(
    theme: str,
    count: int = 20,
    target_width: int = 1920,
    custom_sources: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Récupère les candidats pour un thème donné selon la résolution visée."""
    if theme == "nasa_hubble":
        candidates = fetch_flickr_hubble(count=count)
        if len(candidates) < 5:
            candidates += fetch_nasa_image_library(count=count)
        return candidates
    elif theme in WIKI_QUERIES:
        return fetch_wikimedia(theme=theme, count=count, width=target_width)
    elif theme.startswith("custom_") and custom_sources:
        for src in custom_sources:
            if src.get("id") == theme:
                feed_url = src.get("feed_url") or resolve_flickr_feed_url(src.get("input", ""))
                if feed_url:
                    return fetch_flickr_feed(
                        feed_url=feed_url,
                        theme_name=theme,
                        source_label=src.get("name", "Flickr personnalisé"),
                        count=count,
                    )
    return []

