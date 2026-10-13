"""Schermo dell'applicazione.

SDL viene inizializzato con il driver 'dummy': serve solo per avere font,
decodifica immagini e superfici, non per l'uscita video. Il fotogramma si
compone su `canvas` e `present()` lo riversa sul framebuffer.

La geometria del framebuffer non e' una costante. Al boot la emulazione
fbdev esiste gia' con una risoluzione provvisoria e la modalita' forzata
da cmdline.txt arriva qualche secondo dopo; staccando e riattaccando il
monitor puo' cambiare di nuovo. Chi ha mappato la memoria con i vecchi
valori continuerebbe a scrivere fuori bersaglio, senza alcun errore e con
lo schermo nero. Per questo l'avvio aspetta che la geometria si assesti e
`controlla_geometria()` la rivede periodicamente.

Se il framebuffer non e' raggiungibile si resta comunque in piedi, con
l'uscita a vuoto: utile per provare la logica da SSH senza schermo.
"""
import os
import time

import pygame

from ui import framebuffer as fbmod
from ui.framebuffer import Framebuffer, FramebufferNonDisponibile


class Schermo:
    def __init__(self, fallback_size=(1024, 768), device="/dev/fb0",
                 attendi=True):
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

        pygame.display.init()
        pygame.font.init()

        self.device = device
        self.fallback_size = fallback_size
        self.framebuffer = None
        self.errore = None
        self.canvas = None
        self.size = fallback_size

        if attendi:
            fbmod.attendi_stabile(device)
            self._apri_con_attesa()
        else:
            self._apri()

    def _apri(self):
        """(Ri)apre il framebuffer e rifa' la tela della misura giusta."""
        if self.framebuffer is not None:
            self.framebuffer.close()
            self.framebuffer = None

        try:
            self.framebuffer = Framebuffer(self.device)
            self.errore = None
            size = self.framebuffer.size
        except FramebufferNonDisponibile as errore:
            self.errore = str(errore)
            size = self.fallback_size

        self.size = size
        self.canvas = pygame.display.set_mode(size)
        self._geometria = fbmod.geometria(self.device)

    def _apri_con_attesa(self, massimo=30.0, passo=0.5):
        """Riprova finche' il device non diventa apribile.

        Al boot /dev/fb0 esiste prima che udev gli assegni il gruppo
        'video': in quella finestra l'apertura fallisce con permesso
        negato. Non e' un errore di configurazione, e' solo presto.
        """
        scadenza = time.monotonic() + massimo
        while True:
            self._apri()
            if self.framebuffer is not None or time.monotonic() >= scadenza:
                return
            time.sleep(passo)

    @property
    def attivo(self):
        return self.framebuffer is not None

    def descrizione(self):
        if self.framebuffer is None:
            return f"nessuna uscita video ({self.errore})"
        return self.framebuffer.descrizione()

    def controlla_geometria(self):
        """Rimappa se il pannello e' cambiato, o se non era disponibile.

        Restituisce True quando lo schermo e' stato ricostruito: il
        chiamante deve ridisegnare tutto, perche' la tela e' nuova e
        vuota.
        """
        if self.framebuffer is None:
            # Non era apribile prima: si continua a riprovare, perche' il
            # permesso puo' arrivare dopo l'avvio.
            self._apri()
            return self.framebuffer is not None

        corrente = fbmod.geometria(self.device)
        if corrente is None or corrente == self._geometria:
            return False
        self._apri()
        return True

    def present(self):
        if self.framebuffer is None:
            return
        try:
            self.framebuffer.present(self.canvas)
        except (ValueError, OSError):
            # Il pannello e' cambiato fra un fotogramma e l'altro: si
            # rimappa e si lascia ridisegnare al giro successivo.
            self._apri()

    def close(self):
        if self.framebuffer is not None:
            self.framebuffer.close()
            self.framebuffer = None
        pygame.display.quit()
