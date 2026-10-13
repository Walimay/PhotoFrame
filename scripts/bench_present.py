#!/usr/bin/env python3
"""Misura il costo di un fotogramma sul framebuffer.

Serve a decidere la durata della dissolvenza: se un present costa 80 ms,
una dissolvenza da 450 ms ha una decina di passaggi ed e' fluida; se ne
costa 300, conviene allungarla o toglierla.

    PYTHONPATH=/opt/cornice python3 /opt/cornice/scripts/bench_present.py
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

from ui.display import Schermo  # noqa: E402


def cronometra(etichetta, operazione, giri=20):
    operazione()
    inizio = time.monotonic()
    for _ in range(giri):
        operazione()
    medio = (time.monotonic() - inizio) / giri * 1000
    print(f"  {etichetta:38} {medio:7.1f} ms")
    return medio


def main():
    schermo = Schermo(attendi=False)
    if not schermo.attivo:
        print(f"Framebuffer non disponibile: {schermo.errore}")
        return 1

    fb = schermo.framebuffer
    print(f"Framebuffer {fb.width}x{fb.height} a {fb.bpp} bit, "
          f"stride {fb.stride}\n")

    canvas = schermo.canvas
    foto = pygame.Surface(schermo.size).convert()
    foto.fill((40, 70, 110))
    altra = pygame.Surface(schermo.size).convert()
    altra.fill((150, 90, 40))

    cronometra("riempimento della tela", lambda: canvas.fill((20, 20, 20)))
    cronometra("copia di una foto sulla tela", lambda: canvas.blit(foto, (0, 0)))
    present = cronometra("present (conversione + framebuffer)", schermo.present)

    altra.set_alpha(128)

    def fotogramma_dissolvenza():
        canvas.blit(foto, (0, 0))
        canvas.blit(altra, (0, 0))
        schermo.present()

    fade = cronometra("fotogramma di dissolvenza completo",
                      fotogramma_dissolvenza, giri=10)

    print(f"\nA 450 ms la dissolvenza avrebbe circa "
          f"{max(1, round(450 / fade))} passaggi.")
    if fade > 150:
        print("Consiglio: fade_ms a 0 (taglio netto) oppure 900 ms.")
    else:
        print("Consiglio: 450 ms va bene.")

    schermo.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
