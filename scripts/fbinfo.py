#!/usr/bin/env python3
"""Mostra il formato del framebuffer e disegna una prova colore.

Serve a confermare che rosso, verde e blu finiscano davvero nei canali
giusti. Disegna tre bande piene e una striscia di grigi: se le bande sono
nell'ordine sbagliato o i grigi hanno una dominante, il formato letto dal
kernel non corrisponde a quello che il pannello si aspetta.

    PYTHONPATH=/opt/cornice python3 /opt/cornice/scripts/fbinfo.py
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
from ui.framebuffer import formato_dal_kernel  # noqa: E402


def main():
    schermo = Schermo(attendi=False)
    if not schermo.attivo:
        print(f"Framebuffer non disponibile: {schermo.errore}")
        return 1

    fb = schermo.framebuffer
    print(f"Formato: {fb.descrizione()}")

    grezzo = formato_dal_kernel(fb.fileno())
    if grezzo is None:
        print("Il kernel non ha risposto a FBIOGET_VSCREENINFO: "
              "si usano le maschere predefinite.")
    else:
        bpp, maschere = grezzo
        nomi = ("rosso", "verde", "blu")
        print(f"Dal kernel: {bpp} bit")
        for nome, maschera in zip(nomi, maschere[:3]):
            posizione = (maschera & -maschera).bit_length() - 1
            ampiezza = bin(maschera).count("1")
            print(f"  {nome:6} bit {posizione:2}..{posizione + ampiezza - 1:2} "
                  f"({ampiezza} bit, maschera {maschera:#x})")

    larghezza, altezza = schermo.size
    canvas = schermo.canvas

    # Verifica automatica: scrive colori noti e li rilegge dal pannello.
    # Toglie di mezzo monitor e fotocamera dal giudizio.
    campioni = [("nero", (0, 0, 0)), ("bianco", (255, 255, 255)),
                ("rosso", (255, 0, 0)), ("verde", (0, 255, 0)),
                ("blu", (0, 0, 255)), ("grigio medio", (128, 128, 128)),
                ("verde acqua", (93, 202, 165))]

    canvas.fill((0, 0, 0))
    for indice, (_nome, colore) in enumerate(campioni):
        pygame.draw.rect(canvas, colore, (indice * 8, 0, 8, 8))
    schermo.present()

    print("\nRiletto dal framebuffer (atteso -> letto):")
    tolleranza = 255 // (2 ** min(bin(m).count("1")
                                  for m in fb.maschere[:3])) + 1
    tutti_ok = True
    for indice, (nome, atteso) in enumerate(campioni):
        letto = fb.leggi_pixel(indice * 8 + 4, 4)
        ok = all(abs(a - b) <= tolleranza for a, b in zip(atteso, letto))
        tutti_ok = tutti_ok and ok
        print(f"  {nome:13} {str(atteso):18} -> {str(letto):18} "
              f"{'ok' if ok else 'DIVERSO'}")

    if tutti_ok:
        print(f"\nCatena dei colori corretta "
              f"(scarto entro {tolleranza}, dovuto ai 16 bit).")
        print("Se a video i colori sembrano diversi, dipende dal monitor:")
        print("controlla temperatura colore e modalita' immagine.")
    else:
        print("\nIl pannello rilegge valori diversi da quelli scritti: "
              "il formato non corrisponde.")

    canvas.fill((0, 0, 0))

    terzo = altezza // 4
    for indice, (nome, colore) in enumerate(
            (("rosso", (255, 0, 0)), ("verde", (0, 255, 0)),
             ("blu", (0, 0, 255)))):
        pygame.draw.rect(canvas, colore, (0, indice * terzo, larghezza, terzo))
        etichetta = pygame.font.Font(None, 48).render(nome, True, (0, 0, 0))
        canvas.blit(etichetta, (24, indice * terzo + 16))

    # Striscia di grigi: se ha una dominante, le ampiezze dei canali sono
    # giuste ma le posizioni no.
    passi = 16
    larghezza_passo = larghezza // passi
    for indice in range(passi):
        livello = round(255 * indice / (passi - 1))
        pygame.draw.rect(canvas, (livello, livello, livello),
                         (indice * larghezza_passo, 3 * terzo,
                          larghezza_passo, altezza - 3 * terzo))

    schermo.present()
    print("\nTre bande: rosso in alto, verde al centro, blu in basso, "
          "poi una scala di grigi.")
    print("Dieci secondi.")
    time.sleep(10)

    fb.clear()
    schermo.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
