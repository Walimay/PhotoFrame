#!/usr/bin/env python3
"""Prova i pulsanti senza la cornice di mezzo.

Stampa ogni pressione e ogni rilascio con la durata misurata, e lo stato
iniziale dei pin. Non riavvia e non spegne mai nulla: serve a capire se un
comportamento strano viene dal software della cornice o dal cablaggio.

    sudo systemctl stop cornice-ui
    PYTHONPATH=/opt/cornice python3 /opt/cornice/scripts/test_buttons.py
    PYTHONPATH=/opt/cornice python3 /opt/cornice/scripts/test_buttons.py 22 23 24 25

Ctrl+C per uscire.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ui.buttons import _prepara_ambiente  # noqa: E402

PIN_PREDEFINITI = [22, 23, 24, 25]


def main():
    pin = [int(v) for v in sys.argv[1:]] or PIN_PREDEFINITI

    _prepara_ambiente()
    try:
        from gpiozero import Button
    except Exception as errore:                           # noqa: BLE001
        print(f"gpiozero non disponibile: {errore}")
        return 1

    pulsanti = {}
    premuti = {}

    for numero in pin:
        try:
            pulsante = Button(numero, pull_up=True, bounce_time=0.05)
        except Exception as errore:                       # noqa: BLE001
            print(f"GPIO {numero:>2}: non utilizzabile ({errore})")
            continue
        pulsanti[numero] = pulsante

        def alla_pressione(numero=numero):
            premuti[numero] = time.monotonic()
            print(f"  GPIO {numero:>2}  premuto")

        def al_rilascio(numero=numero):
            inizio = premuti.pop(numero, None)
            durata = 0.0 if inizio is None else time.monotonic() - inizio
            print(f"  GPIO {numero:>2}  rilasciato dopo {durata:.2f}s")

        pulsante.when_pressed = alla_pressione
        pulsante.when_released = al_rilascio

    if not pulsanti:
        print("Nessun pin utilizzabile.")
        return 1

    print("Stato iniziale (a riposo dovrebbe essere 'libero'):")
    for numero, pulsante in pulsanti.items():
        stato = "PREMUTO" if pulsante.is_pressed else "libero"
        print(f"  GPIO {numero:>2}  {stato}")

    print("\nPremi i pulsanti. Ctrl+C per uscire.\n")
    try:
        while True:
            time.sleep(0.5)
            for numero, inizio in list(premuti.items()):
                durata = time.monotonic() - inizio
                if durata > 1 and round(durata * 2) % 2 == 0:
                    print(f"  GPIO {numero:>2}  tenuto da {durata:.1f}s")
    except KeyboardInterrupt:
        print("\nFine.")
    finally:
        for pulsante in pulsanti.values():
            pulsante.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
