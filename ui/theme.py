"""Colori, font e metriche. Unico posto in cui toccare l'aspetto."""
import pygame

from common.config import FONT_DIR

# Palette. Su foto il testo sta sempre su un velo, quindi servono due set.
WHITE = (255, 255, 255)
WHITE_DIM = (255, 255, 255, 185)
INK = (20, 23, 27)
INK_DIM = (20, 23, 27, 190)

BG_DARK = (14, 16, 19)
BG_PANEL = (22, 25, 30)
ACCENT = (93, 202, 165)
ACCENT_COOL = (133, 183, 235)
MUTED = (150, 155, 163)
HAIRLINE = (255, 255, 255, 36)

SCRIM_DARK = (10, 12, 15, 150)
SCRIM_LIGHT = (245, 246, 248, 165)

# Nomi di file cercati in assets/fonts, in ordine di preferenza.
_FAMILIES = {
    "regular": ["Inter-Regular.ttf", "Inter_24pt-Regular.ttf", "Roboto-Regular.ttf"],
    "medium": ["Inter-Medium.ttf", "Inter_24pt-Medium.ttf", "Roboto-Medium.ttf"],
}
_FALLBACK = {
    "regular": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "medium": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
}

_cache = {}
_percorsi = {}


def _cerca(weight):
    """Trova il file del font, scendendo nelle sottocartelle.

    Ordine: i nomi preferiti, poi qualsiasi file statico del peso giusto,
    poi come ultima spiaggia un variable font. Quest'ultimo viene reso da
    FreeType sempre nella sua istanza predefinita, cioe' Regular: in quel
    caso i due pesi coinciderebbero, e il chiamante lo compensa con un
    inspessimento sintetico.
    """
    if weight in _percorsi:
        return _percorsi[weight]

    candidati = []
    if FONT_DIR.exists():
        file_disponibili = [p for p in FONT_DIR.rglob("*")
                            if p.suffix.lower() in (".ttf", ".otf")
                            and "italic" not in p.name.lower()]

        per_nome = {p.name: p for p in file_disponibili}
        for nome in _FAMILIES.get(weight, []):
            if nome in per_nome:
                candidati.append(per_nome[nome])

        parola = "medium" if weight == "medium" else "regular"
        candidati += sorted(p for p in file_disponibili
                            if parola in p.name.lower()
                            and "variable" not in p.name.lower())

        candidati += sorted(p for p in file_disponibili
                            if "variable" in p.name.lower())

    percorso = str(candidati[0]) if candidati else _FALLBACK[weight]
    _percorsi[weight] = percorso
    return percorso


def font(size, weight="regular"):
    """Font con cache: pygame.font.Font rilegge il file a ogni chiamata."""
    key = (size, weight)
    if key in _cache:
        return _cache[key]

    percorso = _cerca(weight)
    try:
        caricato = pygame.font.Font(percorso, size)
    except OSError:
        caricato = pygame.font.Font(None, size)

    # Nessun file distinto per il peso medio: si inspessisce a mano, cosi'
    # orologio e titoli restano distinguibili dal testo normale.
    if weight == "medium" and percorso == _cerca("regular"):
        caricato.set_bold(True)

    _cache[key] = caricato
    return caricato


def font_in_uso():
    """Per il log di avvio: quali file sono stati scelti davvero."""
    return {peso: _cerca(peso) for peso in ("regular", "medium")}


# Metriche, in pixel su 1024x768.
MARGIN = 32
GAP = 14
RADIUS = 10

CLOCK_SIZE = 72
CLOCK_DATE_SIZE = 21
CAPTION_SIZE = 22
CAPTION_META_SIZE = 17
TITLE_SIZE = 42
BODY_SIZE = 24
SMALL_SIZE = 18


def scrim(size, light=False):
    """Rettangolo arrotondato semitrasparente da mettere sotto al testo."""
    surface = pygame.Surface(size, pygame.SRCALPHA)
    color = SCRIM_LIGHT if light else SCRIM_DARK
    pygame.draw.rect(surface, color, surface.get_rect(), border_radius=RADIUS)
    return surface


def text_colors(luminance):
    """Sceglie testo chiaro o scuro in base a quanto e' luminosa la zona.

    luminance e' 0..1 e arriva dal database, calcolata all'import della foto.
    None significa 'non lo sappiamo': si assume scuro, che e' il caso piu'
    frequente e comunque leggibile grazie al velo.
    """
    light_background = luminance is not None and luminance > 0.58
    if light_background:
        return INK, INK_DIM, True
    return WHITE, WHITE_DIM, False
