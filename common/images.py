"""Elaborazione delle immagini, condivisa fra import da riga di comando e
upload da pagina web.

Ogni foto viene portata una volta sola alla risoluzione esatta dello
schermo: a runtime non resta nessun ridimensionamento, che su un Pi Zero
e' la differenza fra un cambio istantaneo e una pausa di secondi.
"""
import os
import re
import uuid

from PIL import Image, ImageOps

from .config import PHOTO_DIR, SCREEN_H, SCREEN_W, THUMB_DIR, TMP_DIR
from . import dates

ESTENSIONI = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".heic", ".tif", ".tiff"}

# Nomi che non dicono nulla e non vanno usati come didascalia.
NOMI_FOTOCAMERA = re.compile(
    r"^(img|dsc|dscn|dscf|pxl|p|photo|foto|image|screenshot|schermata)"
    r"[-_ ]?[\d\-_]*$", re.I)
SOLO_CIFRE = re.compile(r"^[\d\s\-_.]+$")
# Data in coda al nome: "Galibier 20200912" o "Gita 2020-09-12".
DATA_IN_CODA = re.compile(r"[\s_-]*\(?\d{4}[-_]?\d{2}[-_]?\d{2}\)?\s*$")
DUPLICATO = re.compile(r"\s*\(\d+\)\s*$")

THUMB_MAX = 320

BOX_ORARIO = (32, 32, 430, 190)
BOX_DIDASCALIA = (SCREEN_W - 600, SCREEN_H - 150, SCREEN_W - 32, SCREEN_H - 32)


def luminanza(canvas, box):
    """Luminanza media 0..1 di una zona, per scegliere testo chiaro o scuro."""
    zona = canvas.crop(box).convert("L")
    istogramma = zona.histogram()
    totale = sum(istogramma)
    if not totale:
        return None
    somma = sum(valore * conteggio for valore, conteggio in enumerate(istogramma))
    return round(somma / totale / 255.0, 4)


def data_scatto(image):
    try:
        exif = image.getexif()
    except Exception:
        return None
    grezza = exif.get(36867) or exif.get(306)   # DateTimeOriginal / DateTime
    if not grezza:
        return None
    try:
        anno, mese = str(grezza)[:10].split(":")[:2]
        return f"{dates.MESI[int(mese) - 1]} {anno}"
    except (ValueError, IndexError):
        return None


def didascalia_da_nome(nome_file):
    """Ricava una didascalia dal nome, o None se il nome non dice nulla.

    Scarta i nomi delle fotocamere, quelli fatti di sole cifre (tipici
    degli export da Windows o OneDrive) e toglie la data in coda, che
    comparirebbe comunque sotto, presa dall'EXIF.
    """
    stem = os.path.splitext(os.path.basename(nome_file))[0].strip()
    stem = DUPLICATO.sub("", stem)
    if SOLO_CIFRE.match(stem) or NOMI_FOTOCAMERA.match(stem):
        return None

    pulito = DATA_IN_CODA.sub("", stem)
    pulito = re.sub(r"[_]+", " ", pulito).strip(" -_")
    if len(pulito) < 3 or SOLO_CIFRE.match(pulito):
        return None
    return pulito


def prepara(percorso, modalita="contain"):
    """Restituisce (canvas 1024x768, data di scatto)."""
    with Image.open(percorso) as origine:
        # draft() fa il downscale gia' durante la decodifica del JPEG:
        # su ARMv6 taglia i tempi di un ordine di grandezza.
        if origine.format == "JPEG":
            origine.draft("RGB", (SCREEN_W * 2, SCREEN_H * 2))
        immagine = ImageOps.exif_transpose(origine)
        scatto = data_scatto(origine)
        immagine = immagine.convert("RGB")

        if modalita == "cover":
            canvas = ImageOps.fit(immagine, (SCREEN_W, SCREEN_H),
                                  method=Image.LANCZOS)
        else:
            adattata = immagine.copy()
            adattata.thumbnail((SCREEN_W, SCREEN_H), Image.LANCZOS)
            canvas = Image.new("RGB", (SCREEN_W, SCREEN_H), (0, 0, 0))
            canvas.paste(adattata, ((SCREEN_W - adattata.width) // 2,
                                    (SCREEN_H - adattata.height) // 2))
    return canvas, scatto


def salva_atomico(immagine, destinazione, qualita=88):
    """Temporaneo, fsync, rename: uno stacco di corrente non puo' lasciare
    un JPEG troncato nell'archivio."""
    destinazione.parent.mkdir(parents=True, exist_ok=True)
    temporaneo = TMP_DIR / f".{uuid.uuid4().hex}.jpg"
    with open(temporaneo, "wb") as handle:
        immagine.save(handle, "JPEG", quality=qualita, optimize=True)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporaneo, destinazione)
    cartella = os.open(destinazione.parent, os.O_RDONLY)
    try:
        os.fsync(cartella)
    finally:
        os.close(cartella)


def genera_miniatura(nome_file):
    """Crea la miniatura per la pagina web, se manca. Restituisce il path."""
    destinazione = THUMB_DIR / nome_file
    if destinazione.exists():
        return destinazione
    origine = PHOTO_DIR / nome_file
    if not origine.exists():
        return None
    with Image.open(origine) as immagine:
        immagine.draft("RGB", (THUMB_MAX * 2, THUMB_MAX * 2))
        miniatura = immagine.convert("RGB")
        miniatura.thumbnail((THUMB_MAX, THUMB_MAX), Image.LANCZOS)
        salva_atomico(miniatura, destinazione, qualita=78)
    return destinazione


def importa(percorso_origine, nome_originale=None, modalita="contain"):
    """Elabora un file e lo deposita nell'archivio.

    Restituisce il dizionario pronto per db.add_photo.
    """
    nome_originale = nome_originale or os.path.basename(percorso_origine)
    canvas, scatto = prepara(percorso_origine, modalita)

    nome = f"{uuid.uuid4().hex}.jpg"
    salva_atomico(canvas, PHOTO_DIR / nome)

    miniatura = canvas.copy()
    miniatura.thumbnail((THUMB_MAX, THUMB_MAX), Image.LANCZOS)
    salva_atomico(miniatura, THUMB_DIR / nome, qualita=78)

    return {
        "filename": nome,
        "original_name": nome_originale,
        "caption": didascalia_da_nome(nome_originale),
        "taken_at": scatto,
        "lum_topleft": luminanza(canvas, BOX_ORARIO),
        "lum_bottomright": luminanza(canvas, BOX_DIDASCALIA),
    }
