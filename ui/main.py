"""Loop principale dell'interfaccia.

Splash di avvio, slideshow, schermata di benvenuto quando non ci sono
ancora foto. Pulsante e PIR arrivano nella fase 2; intanto si comanda
scrivendo nel file di controllo, cosa piu' comoda della tastiera quando
si lavora da SSH:

    echo next   > /var/lib/cornice/control    foto successiva
    echo prev   > /var/lib/cornice/control    foto precedente
    echo reload > /var/lib/cornice/control    rilegge l'archivio
    echo quit   > /var/lib/cornice/control    esce
"""
import os
import signal
import subprocess
import sys
import time
from datetime import datetime

# Da impostare prima di importare pygame: SDL sceglie il driver all'import.
# 'dummy' perche' l'uscita video non passa da SDL ma dal framebuffer.
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

from common import db, netinfo  # noqa: E402
from common.config import DATA_DIR, PHOTO_DIR, ensure_dirs  # noqa: E402
from ui import theme  # noqa: E402
from ui.buttons import Pulsanti  # noqa: E402
from ui.display import Schermo  # noqa: E402
from ui.screens import photo as photo_screen  # noqa: E402
from ui.screens import overlay, splash, welcome  # noqa: E402

RUNNING = True
RELOAD_SECONDS = 20          # ogni quanto si cercano foto nuove
GEOMETRIA_SECONDS = 2        # ogni quanto si ricontrolla il pannello
CONTROL_FILE = DATA_DIR / "control"


def _stop(signum, frame):
    global RUNNING
    RUNNING = False


def leggi_comandi():
    """Svuota il file di controllo e restituisce i comandi trovati."""
    try:
        if not CONTROL_FILE.exists():
            return []
        testo = CONTROL_FILE.read_text()
        CONTROL_FILE.write_text("")
    except OSError:
        return []
    return [riga.strip().lower() for riga in testo.splitlines() if riga.strip()]


def applica_comandi(comandi, show, fade_ms):
    """Restituisce True se la foto e' cambiata."""
    global RUNNING
    cambiata = False
    for comando in comandi:
        if comando in ("quit", "stop", "exit"):
            RUNNING = False
        elif comando in ("next", "avanti") and show.has_photos:
            show.advance(1, fade_ms)
            cambiata = True
        elif comando in ("prev", "indietro") and show.has_photos:
            show.advance(-1, fade_ms)
            cambiata = True
        elif comando in ("reload", "ricarica"):
            show.reload()
            cambiata = True
    return cambiata


def esegui(comando):
    """Riavvio o spegnimento. Richiede la regola sudoers installata."""
    try:
        subprocess.Popen(["sudo", "-n", "/usr/bin/systemctl", comando])
        return True
    except OSError as errore:
        print(f"impossibile eseguire {comando}: {errore}", flush=True)
        return False


class PressioneProlungata:
    """Conto alla rovescia mentre un pulsante resta premuto.

    L'azione scatta al raggiungimento della soglia, con il pulsante ancora
    premuto; rilasciando prima si annulla. E' l'aspettativa naturale —
    tengo premuto e parte, mollo e non succede niente — ed e' l'opposto di
    come l'avevo fatta all'inizio.

    Lo sfondo viene salvato una volta sola: finche' il riquadro e' a video
    la schermata sotto non cambia, e annullando si ripristina senza doverla
    ricomporre.
    """

    # Sotto questa soglia non si disegna nulla: altrimenti ogni click
    # farebbe lampeggiare il riquadro.
    ATTESA_PRIMA_DEL_RIQUADRO = 0.8

    def __init__(self, schermo, azioni):
        """azioni: {nome_pulsante: (secondi, comando, titolo)}."""
        self.schermo = schermo
        self.azioni = azioni
        self.sfondo = None

    def _ripristina(self):
        if self.sfondo is not None:
            self.schermo.canvas.blit(self.sfondo, (0, 0))
            self.schermo.present()
            self.sfondo = None

    def aggiorna(self, nome, durata):
        """Restituisce il comando da eseguire, oppure None."""
        azione = self.azioni.get(nome) if nome else None
        if azione is None or durata is None:
            self._ripristina()
            return None

        soglia, comando, titolo = azione
        if durata >= soglia:
            return comando

        if durata < self.ATTESA_PRIMA_DEL_RIQUADRO:
            self._ripristina()
            return None

        if self.sfondo is None:
            self.sfondo = self.schermo.canvas.copy()

        rimanente = soglia - durata
        self.schermo.canvas.blit(self.sfondo, (0, 0))
        overlay.conto_alla_rovescia(
            self.schermo.canvas, titolo,
            f"rilascia per annullare · {rimanente:.0f}s",
            durata / soglia)
        self.schermo.present()
        return None

    def mostra_azione(self, titolo):
        if self.sfondo is not None:
            self.schermo.canvas.blit(self.sfondo, (0, 0))
        overlay.conto_alla_rovescia(self.schermo.canvas, titolo, "attendi…", 1.0)
        self.schermo.present()


def costruisci_slideshow(schermo, con, indice=0):
    show = photo_screen.PhotoScreen(
        schermo.canvas, con, PHOTO_DIR, schermo.present)
    show.reload()
    if show.has_photos:
        show.show(indice, fade_ms=0)
    return show


def main():
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    ensure_dirs()
    con = db.init()
    try:
        CONTROL_FILE.write_text("")
    except OSError:
        pass

    # L'attesa dentro Schermo lascia che la risoluzione forzata da
    # cmdline.txt prenda il posto di quella provvisoria del boot.
    schermo = Schermo()
    print(f"framebuffer {schermo.descrizione()}", flush=True)
    for peso, percorso in theme.font_in_uso().items():
        print(f"font {peso}: {percorso}", flush=True)

    info = netinfo.snapshot()
    web_port = db.get_setting(con, "web_port", "8080")

    splash.draw(schermo.canvas, info, web_port)
    schermo.present()
    print("splash a video", flush=True)

    # Lo stato della rete va riletto mentre lo splash e' a video: al boot
    # il WiFi spesso non e' ancora associato quando la schermata compare,
    # e l'indirizzo mostrato e' proprio quello che serve all'utente.
    splash_until = time.monotonic() + db.get_int(con, "splash_seconds", 8)
    prossimo_controllo = time.monotonic() + 1.5
    while RUNNING and time.monotonic() < splash_until:
        if leggi_comandi():
            break
        if time.monotonic() >= prossimo_controllo:
            prossimo_controllo = time.monotonic() + 1.5
            aggiornato = netinfo.snapshot()
            if aggiornato != info:
                info = aggiornato
                splash.draw(schermo.canvas, info, web_port)
                schermo.present()
                # Se la rete e' arrivata tardi, si concede qualche secondo
                # in piu' per leggere l'indirizzo.
                if info.get("ip"):
                    splash_until = max(splash_until, time.monotonic() + 4)
        time.sleep(0.2)

    show = costruisci_slideshow(schermo, con)
    slide_seconds = db.get_int(con, "slide_seconds", 30)
    fade_ms = db.get_int(con, "fade_ms", 450)

    pulsanti = Pulsanti(db.get_int(con, "pin_button_a", 22),
                        db.get_int(con, "pin_button_b", 23))
    if pulsanti.disponibile:
        print(f"pulsanti su GPIO {db.get_int(con, 'pin_button_a', 22)} "
              f"e {db.get_int(con, 'pin_button_b', 23)}", flush=True)
    else:
        print(f"nessun pulsante: {pulsanti.errore}", flush=True)

    pressione = PressioneProlungata(schermo, {
        "a": (db.get_int(con, "hold_reboot", 3), "reboot", "Riavvio"),
        "b": (db.get_int(con, "hold_shutdown", 5), "poweroff", "Spegnimento"),
    })

    last_change = time.monotonic()
    last_reload = time.monotonic()
    last_geometria = time.monotonic()
    last_welcome_minute = None
    frame_clock = pygame.time.Clock()

    while RUNNING:
        now_mono = time.monotonic()
        now = datetime.now()

        # Il pannello puo' cambiare sotto i piedi: al boot, oppure
        # staccando e riattaccando il monitor. Se succede, la tela e' nuova
        # e tutto va ridisegnato.
        if now_mono - last_geometria >= GEOMETRIA_SECONDS:
            last_geometria = now_mono
            if schermo.controlla_geometria():
                print(f"schermo rimappato: {schermo.descrizione()}", flush=True)
                indice = max(0, show.index)
                show = costruisci_slideshow(schermo, con, indice)
                last_welcome_minute = None
                last_change = now_mono

        # Pressione prolungata: ha la precedenza su tutto il resto, e
        # finche' il riquadro e' a video lo slideshow resta fermo.
        nome_premuto, durata = pulsanti.pressione_piu_lunga()
        azione = pressione.aggiorna(nome_premuto, durata if nome_premuto else None)
        if azione:
            if nome_premuto:
                pulsanti.dimentica_pressione(nome_premuto)
            pressione.mostra_azione(
                "Riavvio in corso" if azione == "reboot" else "Spegnimento")
            esegui(azione)
            break
        if pressione.sfondo is not None:
            frame_clock.tick(5)
            continue

        comandi = leggi_comandi()
        for nome in pulsanti.click():
            comandi.append("next" if nome == "a" else "prev")

        if applica_comandi(comandi, show, fade_ms):
            last_change = now_mono
            last_welcome_minute = None

        if now_mono - last_reload >= RELOAD_SECONDS:
            aveva_foto = show.has_photos
            show.aggiorna_impostazioni()
            show.reload()
            slide_seconds = db.get_int(con, "slide_seconds", 30)
            fade_ms = db.get_int(con, "fade_ms", 450)
            last_reload = now_mono
            # Prima foto appena arrivata: si lascia subito la schermata di
            # benvenuto, senza aspettare il prossimo giro.
            if show.has_photos and not aveva_foto:
                show.show(0, fade_ms)
                last_change = now_mono
            elif not show.has_photos and aveva_foto:
                last_welcome_minute = None

        if show.has_photos:
            show.tick_clock(now)
            if now_mono - last_change >= slide_seconds:
                show.advance(1, fade_ms)
                last_change = now_mono
        elif now.minute != last_welcome_minute:
            if info.get("ip") is None or info.get("ssid") is None:
                info = netinfo.snapshot()
            welcome.draw(schermo.canvas, info, web_port, now)
            schermo.present()
            last_welcome_minute = now.minute

        frame_clock.tick(5)

    pulsanti.chiudi()
    schermo.close()
    pygame.quit()
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
