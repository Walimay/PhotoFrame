# Cornice digitale per Raspberry Pi Zero W

Una cornice digitale che mostra le tue foto a schermo intero, si gestisce
dal telefono e si comanda con due pulsanti. Gira su un Raspberry Pi Zero W
— 512 MB di RAM, un core ARMv6 a 1 GHz — e su un monitor recuperato.

Niente servizi esterni, niente cloud, niente account: le foto restano sul
Pi e la pagina di gestione vive sulla rete di casa.

![stato: in sviluppo](https://img.shields.io/badge/stato-in%20sviluppo-orange)
![piattaforma: Raspberry Pi Zero W](https://img.shields.io/badge/piattaforma-Pi%20Zero%20W-c51a4a)
![licenza: MIT](https://img.shields.io/badge/licenza-MIT-blue)

## Cosa fa

- **Slideshow a schermo intero** con orologio e didascalia agli angoli
  opposti, e dissolvenza regolabile.
- **Il colore del testo si adatta alla foto**: la luminanza degli angoli
  viene misurata al caricamento, così l'orologio resta leggibile sia su un
  cielo bianco sia su una notte.
- **Pagina di gestione** protetta da password: caricamento multiplo,
  didascalie, ordine, foto nascoste senza cancellarle, impostazioni.
- **Due pulsanti fisici** per scorrere le foto; tenuti premuti riavviano o
  spengono, con conto alla rovescia annullabile.
- **Schermata di avvio** con SSID e indirizzo IP, che si aggiorna da sola
  quando il WiFi si associa.
- **Nessuna configurazione da tastiera**: si accende ed è pronta.

Le didascalie vengono dedotte dal nome del file, scartando i nomi che non
dicono nulla (`IMG_4821`, le lunghe sequenze di cifre degli export
Windows) e togliendo le date in coda, che compaiono comunque sotto, prese
dall'EXIF.

## Hardware

| Componente | Note |
| --- | --- |
| Raspberry Pi Zero W | Solo 32 bit: è ARMv6 |
| Alimentatore 5 V 2 A | Cavo corto e spesso |
| Scheda SD classe A1 | 8 GB bastano |
| Monitor 1024×768 | Qualsiasi risoluzione va bene, questa è la predefinita |
| Adattatore mini-HDMI | Per monitor VGA serve un adattatore **attivo** |
| 2 pulsanti normalmente aperti | Opzionali |

I pulsanti si collegano fra un pin GPIO e massa: il pull-up è quello
interno del SoC, non servono resistenze esterne. I pin predefiniti sono
GPIO 24 e 25, modificabili dalla pagina impostazioni.

## Installazione

Serve Raspberry Pi OS **Lite Bookworm a 32 bit**: il 64 bit non gira su
ARMv6 e la versione Desktop sprecherebbe RAM che non c'è.

```bash
sudo usermod -aG video,render,gpio $USER   # poi rifare login

sudo apt install -y --no-install-recommends \
  python3-pygame python3-pil python3-flask python3-waitress \
  python3-gpiozero python3-requests sqlite3 git \
  libegl1 libegl-mesa0 libgles2 libgl1-mesa-dri fonts-dejavu-core

git clone https://github.com/<utente>/<repo>.git cornice
cd cornice && sudo ./scripts/install.sh
sudo systemctl enable --now cornice-ui cornice-web
```

Poi apri `http://<ip-del-pi>:8080` dal telefono: al primo accesso la
pagina chiede di scegliere una password, e finché non ne esiste una è
l'unica cosa che fa.

> **Sul Pi Zero W, scarica e installa in due passaggi separati.** Il WiFi
> SDIO sotto carico sostenuto può mandare il kernel in panic, e scaricare
> mentre si scompatta è lo scenario peggiore. Prima
> `sudo apt-get -d -o Acquire::http::Dl-Limit=150 install …`, poi lo
> stesso comando senza `-d`. Non è un difetto del tuo esemplare: è un
> problema noto di brcmfmac.

`install.sh` copia il codice in `/opt/cornice` (sola lettura, di root),
prepara `/var/lib/cornice` per i dati, crea il database, registra i due
servizi systemd e installa una regola sudoers che concede senza password
esattamente `systemctl reboot` e `systemctl poweroff`, e nient'altro.

### Risoluzione dello schermo

Il codice si adatta a qualunque risoluzione, ma se il monitor non espone
un EDID valido conviene forzarla aggiungendo in coda alla riga unica di
`/boot/firmware/cmdline.txt`:

```
video=HDMI-A-1:1024x768@60D
```

Su Bookworm con KMS completo le vecchie direttive `hdmi_group` e
`hdmi_mode` in `config.txt` vengono ignorate.

### Font

Con DejaVu funziona tutto. Per l'aspetto previsto servono i file
**statici** di Inter in `assets/fonts/`: `Inter_24pt-Regular.ttf` e
`Inter_24pt-Medium.ttf`, nella cartella `static/` dello zip di Google
Fonts. I variable font vengono resi sempre nel peso Regular, quindi
orologio e titoli perderebbero il contrasto.

## Uso

Le foto si caricano dalla pagina web, oppure da riga di comando:

```bash
PYTHONPATH=/opt/cornice python3 /opt/cornice/scripts/import_photos.py ~/foto/
```

Vengono portate alla risoluzione esatta dello schermo una volta sola, al
caricamento, così a runtime non resta nessun ridimensionamento. È la
differenza fra un cambio foto istantaneo e una pausa di secondi.

| Azione | Effetto |
| --- | --- |
| Click su A | Foto successiva |
| Click su B | Foto precedente |
| A tenuto 3 s | Riavvio |
| B tenuto 5 s | Spegnimento |

Dalla pagina si regolano durata, dissolvenza, ordine casuale, visibilità
di orologio e didascalia, pin dei pulsanti e soglie. Le modifiche vengono
applicate dal display entro venti secondi, senza riavviare nulla.

Si pilota anche da SSH, utile per le prove:

```bash
echo next > /var/lib/cornice/control     # anche prev, reload, quit
```

## Diagnostica

```bash
# formato del framebuffer, verifica colori rileggendoli dal pannello,
# bande di prova a schermo
PYTHONPATH=/opt/cornice python3 /opt/cornice/scripts/fbinfo.py

# costo di un fotogramma, per scegliere la durata della dissolvenza
PYTHONPATH=/opt/cornice python3 /opt/cornice/scripts/bench_present.py

# pressioni, rilasci e durate dei pulsanti, senza il resto di mezzo
PYTHONPATH=/opt/cornice python3 /opt/cornice/scripts/test_buttons.py 22 23 24 25
```

Su Pi Zero W a 1024×768 a 16 bit: 35 ms per riversare un fotogramma, 83 ms
per un passaggio di dissolvenza. Una dissolvenza da 450 ms ha quindi
cinque passaggi e si vede a scatti; 900 ms la rendono fluida.

## Note tecniche

Due scelte che spiegano buona parte del codice.

**L'uscita video non passa da SDL.** Sul Pi Zero W il percorso KMSDRM di
SDL inizializza EGL, prende il DRM master e fa il cambio di modo — la
console sparisce — ma quello che pygame disegna non arriva mai allo
schermo. Non è un problema di buffering: non cambia nulla nemmeno
ridisegnando più volte. Il fotogramma viene quindi riversato direttamente
su `/dev/fb0`, e SDL resta solo per font, decodifica immagini e superfici,
con il driver `dummy`. Niente EGL, niente GBM, nessuna contesa sul DRM
master, e su questo hardware è anche più veloce.

La disposizione dei canali dentro il pixel viene letta dal kernel con
`FBIOGET_VSCREENINFO` invece di essere indovinata: niente ipotesi fra
RGB565 e BGR565, fra XRGB e BGRX.

**Al boot niente è pronto quando sembra.** La geometria del framebuffer
cambia dopo l'avvio — la risoluzione provvisoria lascia il posto a quella
forzata qualche secondo più tardi; `/dev/fb0` esiste prima che udev gli
assegni il gruppo `video`; il WiFi si associa dopo che il servizio è già
partito. Tutti e tre vengono riletti periodicamente invece di essere
campionati una volta sola. È la stessa lezione imparata tre volte, ed è il
motivo per cui il codice sembra più diffidente del necessario.

## Struttura

```
common/     configurazione, database, elaborazione immagini, date, rete
ui/         framebuffer, tema, schermate, loop principale
web/        applicazione Flask, template, foglio di stile
scripts/    installazione, import, diagnostica, manutenzione
systemd/    unità dei due servizi
```

I dati stanno tutti sotto `/var/lib/cornice`, separati dal codice: è la
premessa per passare la root in sola lettura, così uno stacco di corrente
non può corrompere il sistema.

## Stato

Funzionante e in uso, ma incompleto. Fatto: display, pulsanti, pagina web.

Da fare, in ordine:

- [ ] Pannello informativo: meteo, calendario iCal, lista della spesa
- [ ] Access point di emergenza con portale di configurazione WiFi
- [ ] Sensore PIR per spegnere il monitor quando non c'è nessuno
- [ ] Root in sola lettura

## Licenza

MIT — vedi [LICENSE](LICENSE).

Il codice, i commenti e l'interfaccia sono in italiano.

---

**In English:** a digital photo frame for the Raspberry Pi Zero W. Full
screen slideshow with clock and captions, a password-protected web page
for uploading and managing photos, and two GPIO buttons. Renders straight
to the Linux framebuffer because SDL's KMSDRM path silently fails on this
hardware. Code, comments and UI are in Italian; open an issue if an
English translation would be useful.
