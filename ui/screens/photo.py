"""Slideshow: composizione della foto piu' orologio e didascalia.

Due accorgimenti pensati per il Pi Zero:

- la foto composita viene tenuta in una superficie `base`; a ogni scatto
  dell'orologio si ricopia solo il rettangolo interessato invece di
  ridisegnare lo schermo intero;
- la foto successiva viene decodificata da un thread mentre quella
  corrente e' a video, quindi il cambio non ha pause.
"""
import random
import threading
import time
from datetime import datetime

import pygame

from common import db, dates
from ui import theme


def _fit(image, size, mode):
    """Riporta l'immagine alla dimensione dello schermo.

    contain: tutta la foto visibile, bande nere dove serve.
    cover:   riempie lo schermo ritagliando i bordi.
    """
    sw, sh = size
    iw, ih = image.get_size()
    if iw == sw and ih == sh:
        return image

    scale = min(sw / iw, sh / ih) if mode == "contain" else max(sw / iw, sh / ih)
    new_size = (max(1, round(iw * scale)), max(1, round(ih * scale)))
    return pygame.transform.smoothscale(image, new_size)


def _truncate(font_obj, text, max_width):
    if font_obj.size(text)[0] <= max_width:
        return text
    while text and font_obj.size(text + "...")[0] > max_width:
        text = text[:-1]
    return text.rstrip() + "..."


class PhotoScreen:
    def __init__(self, screen, con, photo_dir, present):
        self.screen = screen
        self._present = present
        self.con = con
        self.photo_dir = photo_dir
        self.size = screen.get_size()

        self.rows = []
        self.index = -1
        self.base = pygame.Surface(self.size).convert()
        self.base.fill((0, 0, 0))

        self._fit_mode = db.get_setting(con, "photo_fit", "contain")
        self._show_clock = db.get_bool(con, "show_clock", True)
        self._show_caption = db.get_bool(con, "show_caption", True)
        self._shuffle = db.get_bool(con, "shuffle", False)
        # Un seme fisso per sessione: l'ordine casuale resta stabile fra una
        # rilettura e l'altra, altrimenti a ogni controllo dell'archivio le
        # foto si rimescolerebbero sotto i piedi.
        self._seme = random.randrange(1 << 30)

        self._clock_rect = None
        self._caption_rect = None
        self._last_minute = None

        self._lock = threading.Lock()
        self._pending = None          # (indice, superficie non convertita)
        self._thread = None

    # ---------------------------------------------------------------- dati

    def aggiorna_impostazioni(self):
        """Rilegge le preferenze dal database: cambiate dalla pagina web,
        devono avere effetto senza riavviare il servizio."""
        prima = (self._show_clock, self._show_caption)
        self._show_clock = db.get_bool(self.con, "show_clock", True)
        self._show_caption = db.get_bool(self.con, "show_caption", True)
        self._shuffle = db.get_bool(self.con, "shuffle", False)
        if (self._show_clock, self._show_caption) != prima and self.has_photos:
            self.screen.blit(self.base, (0, 0))
            self._clock_rect = self._caption_rect = None
            self.draw_overlays(datetime.now())

    def reload(self):
        """Rilegge l'elenco foto. Chiamato all'avvio e dopo ogni upload."""
        previous = self.current_filename()
        self.rows = db.active_photos(self.con)
        if getattr(self, "_shuffle", False):
            random.Random(self._seme).shuffle(self.rows)
        if not self.rows:
            self.index = -1
            return
        if previous:
            for position, row in enumerate(self.rows):
                if row["filename"] == previous:
                    self.index = position
                    return
        self.index = min(max(self.index, 0), len(self.rows) - 1)

    def current_filename(self):
        if 0 <= self.index < len(self.rows):
            return self.rows[self.index]["filename"]
        return None

    @property
    def has_photos(self):
        return bool(self.rows)

    # -------------------------------------------------------------- carico

    def _load_raw(self, position):
        row = self.rows[position]
        path = self.photo_dir / row["filename"]
        try:
            return pygame.image.load(str(path))
        except (pygame.error, OSError):
            return None

    def _prefetch(self, position):
        """Decodifica in background. Niente convert(): va fatto nel thread
        principale, perche' dipende dal formato della superficie video."""
        def work():
            image = self._load_raw(position)
            with self._lock:
                self._pending = (position, image)

        self._thread = threading.Thread(target=work, daemon=True)
        self._thread.start()

    def _take_pending(self, position):
        with self._lock:
            pending = self._pending
            self._pending = None
        if pending and pending[0] == position:
            return pending[1]
        return self._load_raw(position)

    def _compose(self, image):
        base = pygame.Surface(self.size).convert()
        base.fill((0, 0, 0))
        if image is not None:
            fitted = _fit(image, self.size, self._fit_mode).convert()
            base.blit(fitted, fitted.get_rect(center=base.get_rect().center))
        return base

    # ------------------------------------------------------------ disegno

    def _panel(self, lines, light, max_width):
        """Blocco di testo su velo arrotondato. lines = [(testo, size, peso)]."""
        primary, secondary, _ = theme.text_colors(1.0 if light else 0.0)
        rendered = []
        for position, (text, size, weight) in enumerate(lines):
            font_obj = theme.font(size, weight)
            color = primary if position == 0 else secondary
            rendered.append(font_obj.render(
                _truncate(font_obj, text, max_width), True, color))

        pad_x, pad_y = 18, 12
        width = max(img.get_width() for img in rendered) + pad_x * 2
        height = sum(img.get_height() for img in rendered) + pad_y * 2 + \
            4 * (len(rendered) - 1)

        panel = theme.scrim((width, height), light=light)
        y = pad_y
        for img in rendered:
            panel.blit(img, (pad_x, y))
            y += img.get_height() + 4
        return panel

    def _clock_panel(self, now, light):
        return self._panel(
            [(now.strftime("%H:%M"), theme.CLOCK_SIZE, "medium"),
             (dates.long_date(now), theme.CLOCK_DATE_SIZE, "regular")],
            light, self.size[0] // 2)

    def _caption_panel(self, row, light):
        caption = (row["caption"] or "").strip()
        if not caption:
            return None
        lines = [(caption, theme.CAPTION_SIZE, "medium")]
        meta = (row["taken_at"] or "").strip()
        if meta:
            lines.append((meta, theme.CAPTION_META_SIZE, "regular"))
        return self._panel(lines, light, int(self.size[0] * 0.55))

    def draw_overlays(self, now, flip=True):
        """Ridisegna orologio e didascalia sopra la base. Restituisce i
        rettangoli toccati, per un update parziale."""
        if not self.has_photos:
            return []

        row = self.rows[self.index]
        dirty = []

        for rect in (self._clock_rect, self._caption_rect):
            if rect:
                self.screen.blit(self.base, rect, rect)
                dirty.append(rect)
        self._clock_rect = self._caption_rect = None

        if self._show_clock:
            _, _, light = theme.text_colors(row["lum_topleft"])
            panel = self._clock_panel(now, light)
            rect = panel.get_rect(topleft=(theme.MARGIN, theme.MARGIN))
            self.screen.blit(panel, rect)
            self._clock_rect = rect
            dirty.append(rect)

        if self._show_caption:
            _, _, light = theme.text_colors(row["lum_bottomright"])
            panel = self._caption_panel(row, light)
            if panel is not None:
                rect = panel.get_rect(bottomright=(
                    self.size[0] - theme.MARGIN, self.size[1] - theme.MARGIN))
                self.screen.blit(panel, rect)
                self._caption_rect = rect
                dirty.append(rect)

        self._last_minute = now.minute
        if flip:
            self._present()
        return dirty

    def _crossfade(self, new_base, fade_ms):
        if fade_ms <= 0:
            self.screen.blit(new_base, (0, 0))
            return

        # Pilotata dal tempo, non dal numero di fotogrammi: su hardware
        # lento la dissolvenza perde fotogrammi ma dura comunque fade_ms,
        # invece di trascinarsi per secondi.
        # time.monotonic e non pygame.time.get_ticks: quest'ultimo richiede
        # il sottosistema timer di SDL, che qui non viene inizializzato e
        # restituirebbe sempre zero, mandando il ciclo all'infinito.
        old_base = self.base
        duration = fade_ms / 1000.0
        start = time.monotonic()
        while True:
            progress = (time.monotonic() - start) / duration
            if progress >= 1.0:
                break
            new_base.set_alpha(round(255 * progress))
            self.screen.blit(old_base, (0, 0))
            self.screen.blit(new_base, (0, 0))
            self._present()
        new_base.set_alpha(None)

    def show(self, position, fade_ms=0):
        if not self.rows:
            return
        position %= len(self.rows)
        image = self._take_pending(position)
        new_base = self._compose(image)

        self._crossfade(new_base, fade_ms)
        self.base = new_base
        self.index = position

        self._clock_rect = self._caption_rect = None
        self.screen.blit(self.base, (0, 0))
        self.draw_overlays(datetime.now(), flip=False)
        self._present()

        if len(self.rows) > 1:
            self._prefetch((position + 1) % len(self.rows))

    def advance(self, step=1, fade_ms=0):
        self.show(self.index + step, fade_ms)

    def tick_clock(self, now):
        """Da chiamare ogni secondo: ridisegna solo se il minuto e' cambiato."""
        if self._show_clock and now.minute != self._last_minute:
            self.draw_overlays(now)
