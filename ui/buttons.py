"""Pulsanti fisici su GPIO.

Cablaggio: un capo del pulsante al pin, l'altro a massa. La resistenza di
pull-up e' quella interna del SoC, quindi non serve nulla di esterno.

I callback di gpiozero girano in un thread loro, ma disegnare a schermo
deve restare nel thread principale: qui si registrano solo gli istanti di
pressione e rilascio, e il loop principale li interpreta. Cosi' il conto
alla rovescia del riavvio puo' essere disegnato mentre il pulsante e'
ancora premuto.
"""
import os
import threading
import time

from common.config import DATA_DIR

PRESSIONE_MASSIMA_CLICK = 1.0     # oltre, non e' piu' un click


def _prepara_ambiente():
    """Da fare prima di importare gpiozero.

    lgpio crea dei file di notifica (.lgd-nfy*) nella directory di lavoro
    corrente. Per il servizio quella e' /opt/cornice, che appartiene a
    root: lgpio fallisce, gpiozero ripiega su backend via via peggiori e
    si finisce sulla fabbrica sperimentale, che non funziona. LG_WD gli
    dice dove scrivere.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("LG_WD", str(DATA_DIR))
    # Senza questo, un fallimento momentaneo farebbe scivolare gpiozero
    # su un backend diverso invece di segnalare l'errore vero.
    os.environ.setdefault("GPIOZERO_PIN_FACTORY", "lgpio")


class Pulsanti:
    """Due pulsanti. Se il GPIO non e' disponibile resta tutto inerte."""

    def __init__(self, pin_a=22, pin_b=23):
        self.disponibile = False
        self.errore = None
        self._lock = threading.Lock()
        self._premuto_da = {"a": None, "b": None}
        self._click = []
        self._oggetti = {}

        try:
            _prepara_ambiente()
            from gpiozero import Button
        except Exception as errore:                       # noqa: BLE001
            self.errore = f"gpiozero non disponibile: {errore}"
            return

        try:
            for nome, pin in (("a", pin_a), ("b", pin_b)):
                if pin is None:
                    continue
                pulsante = Button(pin, pull_up=True, bounce_time=0.05)
                pulsante.when_pressed = self._fai_premuto(nome)
                pulsante.when_released = self._fai_rilasciato(nome)
                self._oggetti[nome] = pulsante
        except Exception as errore:                       # noqa: BLE001
            self.errore = f"GPIO non utilizzabile: {errore}"
            self.chiudi()
            return

        self.disponibile = bool(self._oggetti)

    # ------------------------------------------------------------ eventi

    def _fai_premuto(self, nome):
        def gestore():
            with self._lock:
                self._premuto_da[nome] = time.monotonic()
        return gestore

    def _fai_rilasciato(self, nome):
        def gestore():
            with self._lock:
                inizio = self._premuto_da.get(nome)
                self._premuto_da[nome] = None
                if inizio is None:
                    return
                durata = time.monotonic() - inizio
                if durata <= PRESSIONE_MASSIMA_CLICK:
                    self._click.append(nome)
        return gestore

    def click(self):
        """Click accumulati dall'ultima chiamata, in ordine."""
        with self._lock:
            trovati, self._click = self._click, []
        return trovati

    def premuto_da(self, nome):
        """Da quanti secondi il pulsante e' premuto, o None se e' libero."""
        with self._lock:
            inizio = self._premuto_da.get(nome)
        return None if inizio is None else time.monotonic() - inizio

    def pressione_piu_lunga(self):
        """(nome, secondi) del pulsante premuto da piu' tempo, o (None, 0)."""
        with self._lock:
            premuti = [(nome, inizio) for nome, inizio
                       in self._premuto_da.items() if inizio is not None]
        if not premuti:
            return None, 0.0
        nome, inizio = min(premuti, key=lambda voce: voce[1])
        return nome, time.monotonic() - inizio

    def dimentica_pressione(self, nome):
        """Annulla la pressione in corso senza generare un click.

        Serve dopo aver eseguito un'azione da pressione prolungata: il
        rilascio successivo non deve contare come click.
        """
        with self._lock:
            self._premuto_da[nome] = None

    def chiudi(self):
        for pulsante in self._oggetti.values():
            try:
                pulsante.close()
            except Exception:                             # noqa: BLE001
                pass
        self._oggetti = {}
        self.disponibile = False
