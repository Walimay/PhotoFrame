"""Uscita video diretta sul framebuffer Linux.

Su Pi Zero W il percorso KMSDRM di SDL inizializza EGL, prende il DRM
master e fa il cambio di modo, ma il contenuto disegnato non raggiunge
mai lo schermo. Scrivere su /dev/fb0 evita l'intero stack grafico: niente
EGL, niente GBM, nessuna contesa sul DRM master.

Pygame continua a comporre il fotogramma in memoria esattamente come
prima, su una superficie a 32 bit; qui lo si converte nel formato del
pannello e lo si riversa con una sola copia.
"""
import fcntl
import mmap
import time
import os
import struct
from pathlib import Path

import pygame

# Ripiego se il kernel non risponde: i formati piu' comuni.
MASCHERE_PREDEFINITE = {
    16: (0xF800, 0x07E0, 0x001F, 0),              # RGB565
    32: (0x00FF0000, 0x0000FF00, 0x000000FF, 0),  # XRGB8888
}

FBIOGET_VSCREENINFO = 0x4600

# Posizione dei campi dentro struct fb_var_screeninfo. Sono tutti __u32
# fino a 'transp' compreso, quindi gli offset non dipendono dall'essere a
# 32 o 64 bit. Ogni fb_bitfield e' (offset, length, msb_right).
_OFF_BPP = 24
_OFF_ROSSO = 32
_OFF_VERDE = 44
_OFF_BLU = 56
_OFF_ALFA = 68
_DIMENSIONE_VAR = 160


def _maschera(dati, offset):
    posizione, lunghezza, _msb = struct.unpack_from("<III", dati, offset)
    if lunghezza == 0:
        return 0
    return ((1 << lunghezza) - 1) << posizione


def formato_dal_kernel(fd):
    """Legge profondita' e disposizione dei canali con FBIOGET_VSCREENINFO.

    Evita di tirare a indovinare fra RGB565 e BGR565, fra XRGB e BGRX:
    il kernel dice posizione e ampiezza esatte di ogni canale.
    """
    buffer = bytearray(_DIMENSIONE_VAR)
    try:
        fcntl.ioctl(fd, FBIOGET_VSCREENINFO, buffer)
    except OSError:
        return None
    return formato_da_buffer(buffer)


def formato_da_buffer(buffer):
    """Parte pura di formato_dal_kernel, separata per poterla provare."""
    bpp = struct.unpack_from("<I", buffer, _OFF_BPP)[0]
    if bpp not in (16, 32):
        return None

    maschere = (_maschera(buffer, _OFF_ROSSO),
                _maschera(buffer, _OFF_VERDE),
                _maschera(buffer, _OFF_BLU),
                _maschera(buffer, _OFF_ALFA))
    if not all(maschere[:3]):
        return None
    # pygame non gestisce l'alfa su superfici senza canale alfa reale.
    return bpp, (maschere[0], maschere[1], maschere[2], 0)


class FramebufferNonDisponibile(RuntimeError):
    pass


def geometria(device="/dev/fb0"):
    """Dimensioni, profondita' e stride correnti, lette da sysfs.

    Non e' un dato stabile: all'avvio la emulazione fbdev esiste gia' con
    una geometria provvisoria, e la modalita' forzata da cmdline.txt viene
    applicata qualche secondo piu' tardi. Chi mappa la memoria deve
    accorgersene e rimapparla.
    """
    nome = Path(device).name
    dimensione = _leggi_sysfs(nome, "virtual_size")
    if not dimensione:
        return None
    try:
        larghezza, altezza = (int(v) for v in dimensione.split(","))
        bpp = int(_leggi_sysfs(nome, "bits_per_pixel") or 0)
    except (TypeError, ValueError):
        return None
    stride_grezza = _leggi_sysfs(nome, "stride")
    stride = int(stride_grezza) if stride_grezza else larghezza * (bpp // 8)
    return (larghezza, altezza, bpp, stride)


def attendi_stabile(device="/dev/fb0", quiete=2.0, massimo=25.0):
    """Aspetta che la geometria resti identica per `quiete` secondi.

    Evita di mappare la risoluzione provvisoria del boot. Restituisce
    l'ultima geometria vista, anche se il tempo massimo scade.
    """
    scadenza = time.monotonic() + massimo
    ultima = geometria(device)
    stabile_da = time.monotonic()

    while time.monotonic() < scadenza:
        time.sleep(0.4)
        corrente = geometria(device)
        if corrente != ultima:
            ultima = corrente
            stabile_da = time.monotonic()
        elif time.monotonic() - stabile_da >= quiete:
            return ultima
    return ultima


def _leggi_sysfs(nome_device, attributo):
    percorso = Path("/sys/class/graphics") / nome_device / attributo
    try:
        return percorso.read_text().strip()
    except OSError:
        return None


class Framebuffer:
    """Schermo di uscita. Si usa con `present(superficie)`."""

    def __init__(self, device="/dev/fb0", size=None, bpp=None, stride=None):
        self.device = device
        nome = Path(device).name

        if size is None:
            grezza = _leggi_sysfs(nome, "virtual_size")
            if not grezza:
                raise FramebufferNonDisponibile(
                    f"{device}: impossibile leggere virtual_size")
            larghezza, altezza = (int(v) for v in grezza.split(","))
        else:
            larghezza, altezza = size

        try:
            self._fd = os.open(device, os.O_RDWR)
        except OSError as errore:
            raise FramebufferNonDisponibile(
                f"{device}: {errore}. L'utente deve stare nel gruppo 'video'."
            ) from errore

        formato = formato_dal_kernel(self._fd)
        if formato is not None and bpp is None:
            bpp, maschere = formato
            self.origine_formato = "kernel"
        else:
            if bpp is None:
                grezza = _leggi_sysfs(nome, "bits_per_pixel")
                bpp = int(grezza) if grezza else 16
            if bpp not in MASCHERE_PREDEFINITE:
                os.close(self._fd)
                raise FramebufferNonDisponibile(
                    f"{device}: profondita' {bpp} bit non gestita")
            maschere = MASCHERE_PREDEFINITE[bpp]
            self.origine_formato = "predefinito"

        self.width = larghezza
        self.height = altezza
        self.bpp = bpp
        self.maschere = maschere
        self.bytes_per_pixel = bpp // 8

        if stride is None:
            grezza = _leggi_sysfs(nome, "stride")
            stride = int(grezza) if grezza else larghezza * self.bytes_per_pixel
        self.stride = stride

        self._riga = larghezza * self.bytes_per_pixel
        self._lunghezza = stride * altezza

        try:
            self._map = mmap.mmap(self._fd, self._lunghezza,
                                  mmap.MAP_SHARED,
                                  mmap.PROT_READ | mmap.PROT_WRITE)
        except (OSError, ValueError) as errore:
            os.close(self._fd)
            raise FramebufferNonDisponibile(f"{device}: {errore}") from errore

        # Superficie di appoggio nel formato esatto del pannello: la
        # conversione di profondita' la fa pygame in C, non Python.
        self._staging = pygame.Surface((larghezza, altezza), 0, bpp, maschere)

    def descrizione(self):
        rosso, verde, blu, _ = self.maschere
        return (f"{self.width}x{self.height} a {self.bpp} bit, "
                f"stride {self.stride}, maschere R={rosso:#x} V={verde:#x} "
                f"B={blu:#x} ({self.origine_formato})")

    @property
    def size(self):
        return (self.width, self.height)

    def fileno(self):
        return self._fd

    def present(self, surface):
        """Riversa una superficie a schermo intero sul pannello."""
        if surface.get_size() != (self.width, self.height):
            raise ValueError(
                f"superficie {surface.get_size()} diversa dallo schermo "
                f"{(self.width, self.height)}")

        self._staging.blit(surface, (0, 0))
        grezzi = self._staging.get_buffer().raw
        passo = self._staging.get_pitch()

        if passo == self._riga and self.stride == self._riga:
            # Caso normale: una sola copia per tutto il fotogramma.
            self._map.seek(0)
            self._map.write(grezzi)
            return

        # Allineamenti diversi fra superficie e pannello: riga per riga.
        for y in range(self.height):
            origine = y * passo
            destinazione = y * self.stride
            self._map[destinazione:destinazione + self._riga] = \
                grezzi[origine:origine + self._riga]

    def leggi_pixel(self, x, y):
        """Rilegge un pixel dal pannello e lo decodifica in (r, g, b).

        Serve a verificare la catena dei colori senza passare dagli occhi:
        se quello che si rilegge coincide con quello che si e' scritto, il
        software e' corretto e ogni differenza a video viene dal monitor.
        """
        offset = y * self.stride + x * self.bytes_per_pixel
        grezzi = bytes(self._map[offset:offset + self.bytes_per_pixel])
        valore = int.from_bytes(grezzi, "little")

        canali = []
        for maschera in self.maschere[:3]:
            posizione = (maschera & -maschera).bit_length() - 1
            ampiezza = bin(maschera).count("1")
            livello = (valore & maschera) >> posizione
            massimo = (1 << ampiezza) - 1
            canali.append(round(livello * 255 / massimo))
        return tuple(canali)

    def clear(self):
        self._map.seek(0)
        self._map.write(b"\x00" * self._lunghezza)

    def close(self):
        try:
            self._map.close()
        finally:
            os.close(self._fd)
