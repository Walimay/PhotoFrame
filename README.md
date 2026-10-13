# Cornice digitale — fasi 1, 2 e 3

Display: splash di avvio, slideshow con orologio e didascalia, schermata
di benvenuto finché l'archivio è vuoto.

Pagina web: caricamento foto, didascalie, ordine, visibilità,
impostazioni, comandi al display. Protetta da password.

Pulsanti fisici: due, su GPIO 24 e 25.

PIR, meteo, calendario e access point di emergenza arrivano nelle fasi
successive.

## Pulsanti

Cablaggio: un capo del pulsante al pin, l'altro a massa. La resistenza di
pull-up è quella interna del SoC, quindi non serve nulla di esterno.

| azione | effetto |
|---|---|
| click su A (GPIO 24) | foto successiva |
| click su B (GPIO 25) | foto precedente |
| A tenuto 3 s | riavvio |
| B tenuto 5 s | spegnimento |

Dopo circa un secondo di pressione compare un riquadro con il conto alla
rovescia; l'azione scatta al raggiungimento della soglia, con il pulsante
ancora premuto, e **rilasciare prima annulla**, riportando la schermata
esattamente com'era. È l'aspettativa naturale: tengo premuto e parte,
mollo e non succede niente.

Per provare i pin senza la cornice di mezzo — stampa pressioni, rilasci e
durate, e non riavvia mai nulla:

```bash
sudo systemctl stop cornice-ui
PYTHONPATH=/opt/cornice python3 /opt/cornice/scripts/test_buttons.py 22 23 24 25
```

Riavvio e spegnimento passano da una regola sudoers installata da
`install.sh`, che concede senza password esattamente due comandi:
`systemctl reboot` e `systemctl poweroff`. Nient'altro.

Pin e soglie si cambiano dalla pagina impostazioni, sezione Pulsanti. I
numeri sono quelli GPIO, non la posizione fisica sul connettore, e vengono
letti all'avvio: dopo averli cambiati va riavviato il servizio del display.

Se il GPIO non è utilizzabile il servizio parte lo stesso e lo scrive nel
log: la cornice resta pilotabile dalla pagina web.

Una trappola che vale la pena conoscere: `lgpio`, il backend usato da
gpiozero, crea i suoi file di notifica (`.lgd-nfy*`) nella **directory di
lavoro corrente**. Per il servizio quella è `/opt/cornice`, di proprietà
di root, quindi fallisce; gpiozero allora ripiega silenziosamente su
backend sempre peggiori fino a quello sperimentale, che non funziona, e
l'errore finale (`Invalid argument`) non ha più nulla a che vedere con la
causa. Si risolve con `LG_WD`, impostato sia nell'unità systemd sia nel
codice prima dell'import.

## Installazione sul Pi

Copia la cartella sul Pi e lancia:

```bash
sudo ./scripts/install.sh
```

Lo script copia il codice in `/opt/cornice`, prepara `/var/lib/cornice`,
crea il database e registra il servizio `cornice-ui`. È rilanciabile: un
secondo giro aggiorna solo il codice, lasciando foto e impostazioni.

## Prova

```bash
sudo systemctl start cornice-ui cornice-web
journalctl -fu cornice-ui -u cornice-web
```

Poi apri `http://<ip-del-pi>:8080` dal telefono o dal computer. Al primo
accesso la pagina chiede di scegliere una password: finché non ne esiste
una, è l'unica cosa che fa.

Avvio automatico al boot, quando sei soddisfatto:

```bash
sudo systemctl enable cornice-ui cornice-web
```

Le foto si possono caricare anche da riga di comando, con la stessa
elaborazione:

```bash
PYTHONPATH=/opt/cornice python3 /opt/cornice/scripts/import_photos.py ~/foto/
```

## Comandi (solo per le prove)

Si pilota scrivendo nel file di controllo, più comodo della tastiera
quando si lavora da SSH:

```bash
echo next   > /var/lib/cornice/control    # foto successiva
echo prev   > /var/lib/cornice/control    # foto precedente
echo reload > /var/lib/cornice/control    # rilegge l'archivio
echo quit   > /var/lib/cornice/control    # esce
```

Dalla fase 2 l'ingresso sarà il pulsante su GPIO; il file di controllo
resta comunque, utile per le prove.

## Console di testo

Prima di guardare il risultato sul serio, togli di mezzo la console:
altrimenti vedi il cursore lampeggiante sopra le foto e i messaggi del
kernel ci finiscono in mezzo.

```bash
sudo ./scripts/console_off.sh
sudo reboot
```

Sposta la console su tty3, spegne il cursore, toglie il logo e disattiva
il login su tty1. Si torna indietro con `sudo ./scripts/console_off.sh --undo`.
SSH non è toccato in nessun caso.

## Pagina web

Caricamento multiplo, didascalie modificabili, ordine con le frecce,
foto nascondibili senza cancellarle, eliminazione definitiva. In alto
tre pulsanti comandano il display (indietro, avanti, ricarica).

Gli upload non vengono elaborati dentro la richiesta HTTP: su un Pi Zero
una foto da 12 megapixel richiede più di un secondo e venti foto
manderebbero il browser in timeout. I file arrivano in una cartella
temporanea, la risposta torna subito, e un thread li elabora uno alla
volta mentre la pagina mostra l'avanzamento e si ricarica a fine coda.

Le impostazioni cambiate dalla pagina vengono applicate dal display entro
venti secondi, senza riavviare nulla. Fa eccezione l'adattamento delle
foto, che agisce al caricamento.

Se dimentichi la password:

```bash
sqlite3 /var/lib/cornice/cornice.db "DELETE FROM settings WHERE key='password_hash';"
```

Al prossimo accesso la pagina tornerà a chiederne una nuova.

## Struttura

```
common/     config, database, elaborazione immagini, date, info di rete
ui/         theme, le tre schermate, framebuffer, main.py con il loop
web/        applicazione Flask, template, foglio di stile
scripts/    install.sh, import, diagnostica, manutenzione
systemd/    unità dei due servizi
```

I dati stanno tutti sotto `/var/lib/cornice`, separati dal codice: quando
in fase 5 passeremo la root in sola lettura, sarà l'unica partizione
scrivibile.

## Impostazioni

Vivono nella tabella `settings` e si cambiano da SQL finché non c'è la
pagina web:

```bash
sqlite3 /var/lib/cornice/cornice.db \
  "UPDATE settings SET value='15' WHERE key='slide_seconds';"
```

| chiave | default | note |
|---|---|---|
| `slide_seconds` | 30 | durata di ogni foto |
| `fade_ms` | 450 | dissolvenza; `0` per il taglio netto |
| `splash_seconds` | 8 | durata dello splash |
| `photo_fit` | contain | `cover` riempie lo schermo ritagliando |
| `show_clock` | 1 | orologio in alto a sinistra |
| `show_caption` | 1 | didascalia in basso a destra |

`photo_fit` agisce all'import, non a runtime: cambiandolo vanno
reimportate le foto.

Se le didascalie dedotte dai nomi dei file sono sbagliate — capita con i
nomi fatti di sole cifre degli export Windows — si ricalcolano senza
reimportare:

```bash
PYTHONPATH=/opt/cornice python3 /opt/cornice/scripts/fix_captions.py
PYTHONPATH=/opt/cornice python3 /opt/cornice/scripts/fix_captions.py --applica
```

Tocca solo le didascalie che coincidono ancora con quelle generate in
automatico: quelle scritte a mano restano.

## Font

Con DejaVu funziona tutto. Per l'aspetto dei mockup metti i file di Inter
in `/opt/cornice/assets/fonts/` (`Inter-Regular.ttf` e `Inter-Medium.ttf`):
vengono rilevati da soli, senza toccare il codice.

## Perché il framebuffer e non SDL

Su Pi Zero W il percorso KMSDRM di SDL inizializza EGL, prende il DRM
master e fa il cambio di modo — la console sparisce — ma quello che
pygame disegna non arriva mai allo schermo, che resta nero. Non è un
problema di buffer: non cambia nulla nemmeno ridisegnando più volte.

Quindi SDL serve solo per font, decodifica immagini e superfici, con il
driver `dummy`, mentre il fotogramma finito viene riversato direttamente
su `/dev/fb0`. Niente EGL, niente GBM, nessuna contesa sul DRM master.
Il codice delle schermate non è cambiato: è cambiato solo come il
fotogramma arriva al pannello.

`ui/framebuffer.py` legge dimensioni e stride da
`/sys/class/graphics/fb0/`, e la disposizione dei canali direttamente dal
kernel con `FBIOGET_VSCREENINFO`: niente da indovinare fra RGB565 e
BGR565, fra XRGB e BGRX. Serve appartenere al gruppo `video`.

Per vedere il formato rilevato e una prova colore a schermo:

```bash
PYTHONPATH=/opt/cornice python3 /opt/cornice/scripts/fbinfo.py
```

Disegna tre bande (rosso, verde, blu dall'alto) e una scala di grigi. Se
le bande sono nell'ordine sbagliato o i grigi hanno una dominante, il
formato non corrisponde.

Per misurare quanto costa un fotogramma sul Pi:

```bash
PYTHONPATH=/opt/cornice python3 /opt/cornice/scripts/bench_present.py
```

Stampa il costo di un present e di un fotogramma di dissolvenza, e
suggerisce un valore per `fade_ms`.

## Note di implementazione

Le foto vengono portate a 1024×768 esatti una volta sola, all'import, con
`draft()` di Pillow che fa il downscale già durante la decodifica del
JPEG. A runtime non resta nessun ridimensionamento.

La foto successiva viene decodificata da un thread mentre quella corrente
è a video, così il cambio non ha pause.

L'orologio non ricompone l'intera scena: a ogni scatto di minuto ricopia
dalla superficie di base solo il rettangolo che occupa, poi riversa il
fotogramma.

Il colore del testo si adatta alla foto. All'import si misura la luminanza
media dei due angoli dove finiscono orologio e didascalia e la si salva nel
database; a runtime si sceglie testo chiaro su velo scuro o viceversa.

La dissolvenza è pilotata dal tempo e non dal numero di fotogrammi: su
hardware lento perde fotogrammi ma dura comunque `fade_ms`, invece di
trascinarsi.

## La geometria del framebuffer non è una costante

Al boot l'emulazione fbdev esiste già con una risoluzione provvisoria —
sul Pi Zero 1920×1080 a 32 bit, negoziata con lo schermo — e la modalità
forzata da `cmdline.txt` arriva qualche secondo più tardi. Un programma
che legga dimensioni e stride una volta sola all'avvio continua poi a
scrivere nella finestra sbagliata: nessun errore, schermo nero.

Per questo l'avvio aspetta che la geometria resti identica per due
secondi prima di mappare la memoria, e il loop la ricontrolla ogni due
secondi: se cambia, rimappa e ridisegna. Vale anche per il monitor
staccato e riattaccato a caldo.

Nel log compare `schermo rimappato: …` ogni volta che succede.

C'è un secondo motivo per cui l'avvio non può dare nulla per scontato:
al boot `/dev/fb0` esiste prima che udev gli assegni il gruppo `video`, e
in quella finestra l'apertura fallisce con permesso negato. Non è un
errore di configurazione, è solo presto. L'avvio insiste fino a trenta
secondi, e se anche così non riesce il loop continua a riprovare: appena
il permesso arriva, l'immagine compare.

## Problemi noti

Se il log dice `nessuna uscita video` e non compare mai `schermo
rimappato`, l'utente del servizio non appartiene al gruppo `video`
(`sudo usermod -aG video $USER`, poi riavvia il servizio). Lo stesso
messaggio all'avvio, seguito dopo pochi secondi da `schermo rimappato`,
è invece normale: significa solo che il servizio è partito prima di udev.

Lo spegnimento del monitor per il PIR, in fase 2, passerà da
`/sys/class/graphics/fb0/blank`, che su questo hardware funziona, e non da
`vcgencmd display_power`, che con il KMS completo non ha più effetto.
