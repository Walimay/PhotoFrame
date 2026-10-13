"""Pagina di gestione della cornice.

Flask servito da waitress. Protetta da password, pensata per la rete di
casa: niente HTTPS, niente utenti multipli.

Gli upload non vengono elaborati dentro la richiesta HTTP: su un Pi Zero
una foto da 12 megapixel richiede piu' di un secondo, e venti foto
manderebbero il browser in timeout. I file arrivano in una cartella
temporanea, la risposta torna subito, e un thread di lavoro li elabora
uno alla volta mostrando l'avanzamento.
"""
import os
import queue
import secrets
import threading
import uuid
from pathlib import Path

from flask import (Flask, abort, flash, jsonify, redirect, render_template,
                   request, send_from_directory, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from common import db, images
from common.config import (DATA_DIR, PHOTO_DIR, THUMB_DIR, TMP_DIR,
                           ensure_dirs)

CONTROL_FILE = DATA_DIR / "control"
COMANDI_AMMESSI = {"next", "prev", "reload"}
MAX_UPLOAD_MB = 80

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024

_coda = queue.Queue()
_stato = {"in_attesa": 0, "elaborate": 0, "errori": []}
_lock = threading.Lock()


# --------------------------------------------------------------- impianto

def connessione():
    """Una connessione SQLite per thread: gli oggetti non sono condivisibili."""
    locale = threading.current_thread()
    con = getattr(locale, "_cornice_db", None)
    if con is None:
        con = db.connect()
        locale._cornice_db = con
    return con


def chiave_segreta(con):
    """Chiave di sessione persistente: se cambiasse a ogni avvio, ogni
    riavvio del servizio scollegherebbe l'utente."""
    chiave = db.get_setting(con, "secret_key")
    if not chiave:
        chiave = secrets.token_hex(32)
        db.set_setting(con, "secret_key", chiave)
    return chiave


def password_impostata(con):
    return bool(db.get_setting(con, "password_hash"))


def token_csrf():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(24)
    return session["csrf"]


@app.before_request
def controlla_accesso():
    if request.endpoint in ("static", "login", "setup"):
        return None

    con = connessione()
    if not password_impostata(con):
        return redirect(url_for("setup"))
    if not session.get("autenticato"):
        return redirect(url_for("login", prossima=request.path))

    if request.method == "POST":
        inviato = request.form.get("csrf") or request.headers.get("X-CSRF")
        if not inviato or inviato != session.get("csrf"):
            abort(400, "Token di sessione non valido. Ricarica la pagina.")
    return None


@app.context_processor
def variabili_comuni():
    return {"csrf": token_csrf()}


# ------------------------------------------------------------- lavorazione

def _worker():
    while True:
        voce = _coda.get()
        if voce is None:
            break
        percorso, nome_originale = voce
        con = connessione()
        try:
            modalita = db.get_setting(con, "photo_fit", "contain")
            dati = images.importa(percorso, nome_originale, modalita)
            db.add_photo(con, **dati)
            with _lock:
                _stato["elaborate"] += 1
        except Exception as errore:                      # noqa: BLE001
            with _lock:
                _stato["errori"].append(f"{nome_originale}: {errore}")
        finally:
            try:
                os.unlink(percorso)
            except OSError:
                pass
            with _lock:
                _stato["in_attesa"] = max(0, _stato["in_attesa"] - 1)
            _coda.task_done()


def avvia_worker():
    thread = threading.Thread(target=_worker, daemon=True, name="import")
    thread.start()
    return thread


# ----------------------------------------------------------------- accesso

@app.route("/setup", methods=["GET", "POST"])
def setup():
    con = connessione()
    if password_impostata(con):
        return redirect(url_for("login"))

    if request.method == "POST":
        password = request.form.get("password", "")
        conferma = request.form.get("conferma", "")
        if len(password) < 6:
            flash("La password deve avere almeno 6 caratteri.", "errore")
        elif password != conferma:
            flash("Le due password non coincidono.", "errore")
        else:
            db.set_setting(con, "password_hash", generate_password_hash(password))
            session["autenticato"] = True
            return redirect(url_for("index"))
    return render_template("setup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    con = connessione()
    if not password_impostata(con):
        return redirect(url_for("setup"))

    if request.method == "POST":
        atteso = db.get_setting(con, "password_hash")
        if check_password_hash(atteso, request.form.get("password", "")):
            session["autenticato"] = True
            session.permanent = True
            prossima = request.form.get("prossima") or url_for("index")
            return redirect(prossima)
        flash("Password errata.", "errore")
    return render_template("login.html", prossima=request.args.get("prossima", ""))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ----------------------------------------------------------------- galleria

@app.route("/")
def index():
    con = connessione()
    foto = db.all_photos(con)
    with _lock:
        stato = dict(_stato)
    return render_template("index.html", foto=foto, stato=stato,
                           totale_attive=db.count_active(con))


@app.route("/thumb/<path:nome>")
def miniatura(nome):
    nome = secure_filename(nome)
    if not (THUMB_DIR / nome).exists():
        try:
            images.genera_miniatura(nome)
        except Exception:                                 # noqa: BLE001
            abort(404)
    if not (THUMB_DIR / nome).exists():
        abort(404)
    return send_from_directory(THUMB_DIR, nome, max_age=86400)


@app.route("/foto/<path:nome>")
def foto_intera(nome):
    nome = secure_filename(nome)
    return send_from_directory(PHOTO_DIR, nome, max_age=86400)


@app.route("/upload", methods=["POST"])
def upload():
    ricevuti = 0
    for caricato in request.files.getlist("foto"):
        if not caricato or not caricato.filename:
            continue
        estensione = Path(caricato.filename).suffix.lower()
        if estensione not in images.ESTENSIONI:
            with _lock:
                _stato["errori"].append(
                    f"{caricato.filename}: formato non gestito")
            continue
        temporaneo = TMP_DIR / f"up_{uuid.uuid4().hex}{estensione}"
        caricato.save(temporaneo)
        with _lock:
            _stato["in_attesa"] += 1
        _coda.put((str(temporaneo), caricato.filename))
        ricevuti += 1

    if ricevuti:
        flash(f"{ricevuti} file in elaborazione.", "ok")
    else:
        flash("Nessun file valido selezionato.", "errore")
    return redirect(url_for("index"))


@app.route("/coda")
def coda():
    with _lock:
        return jsonify(dict(_stato))


@app.route("/coda/pulisci", methods=["POST"])
def pulisci_coda():
    with _lock:
        _stato["errori"] = []
        _stato["elaborate"] = 0
    return redirect(url_for("index"))


@app.route("/foto/<int:photo_id>/didascalia", methods=["POST"])
def modifica_didascalia(photo_id):
    testo = request.form.get("caption", "").strip()
    db.update_photo(connessione(), photo_id, caption=testo or None)
    return redirect(url_for("index") + f"#foto-{photo_id}")


@app.route("/foto/<int:photo_id>/visibile", methods=["POST"])
def cambia_visibilita(photo_id):
    con = connessione()
    riga = db.get_photo(con, photo_id)
    if riga is None:
        abort(404)
    db.update_photo(con, photo_id, active=0 if riga["active"] else 1)
    return redirect(url_for("index") + f"#foto-{photo_id}")


@app.route("/foto/<int:photo_id>/sposta", methods=["POST"])
def sposta(photo_id):
    db.move_photo(connessione(), photo_id, request.form.get("direzione", "up"))
    return redirect(url_for("index") + f"#foto-{photo_id}")


@app.route("/foto/<int:photo_id>/elimina", methods=["POST"])
def elimina(photo_id):
    nome = db.delete_photo(connessione(), photo_id)
    if nome:
        for cartella in (PHOTO_DIR, THUMB_DIR):
            try:
                os.unlink(cartella / nome)
            except OSError:
                pass
        flash("Foto eliminata.", "ok")
    return redirect(url_for("index"))


# ------------------------------------------------------------ impostazioni

CAMPI_NUMERICI = {
    "slide_seconds": (3, 3600),
    "fade_ms": (0, 5000),
    "splash_seconds": (0, 60),
    "pin_button_a": (0, 27),
    "pin_button_b": (0, 27),
    "hold_reboot": (1, 30),
    "hold_shutdown": (1, 30),
}
CAMPI_BOOLEANI = ("show_clock", "show_caption", "shuffle")


@app.route("/impostazioni", methods=["GET", "POST"])
def impostazioni():
    con = connessione()

    if request.method == "POST":
        for chiave, (minimo, massimo) in CAMPI_NUMERICI.items():
            grezzo = request.form.get(chiave)
            if grezzo is None:
                continue
            try:
                valore = int(grezzo)
            except ValueError:
                flash(f"Valore non numerico per {chiave}.", "errore")
                continue
            db.set_setting(con, chiave, max(minimo, min(massimo, valore)))

        for chiave in CAMPI_BOOLEANI:
            db.set_setting(con, chiave, "1" if request.form.get(chiave) else "0")

        fit = request.form.get("photo_fit")
        if fit in ("contain", "cover"):
            db.set_setting(con, "photo_fit", fit)

        nuova = request.form.get("nuova_password", "")
        if nuova:
            if len(nuova) < 6:
                flash("La password deve avere almeno 6 caratteri.", "errore")
            elif nuova != request.form.get("conferma_password", ""):
                flash("Le due password non coincidono.", "errore")
            else:
                db.set_setting(con, "password_hash",
                               generate_password_hash(nuova))
                flash("Password aggiornata.", "ok")

        flash("Impostazioni salvate. Il display le applica entro un minuto.",
              "ok")
        return redirect(url_for("impostazioni"))

    valori = {chiave: db.get_setting(con, chiave)
              for chiave in list(CAMPI_NUMERICI) + list(CAMPI_BOOLEANI)
              + ["photo_fit"]}
    return render_template("impostazioni.html", valori=valori)


@app.route("/controllo/<comando>", methods=["POST"])
def controllo(comando):
    if comando not in COMANDI_AMMESSI:
        abort(400)
    try:
        with open(CONTROL_FILE, "a") as handle:
            handle.write(comando + "\n")
    except OSError as errore:
        flash(f"Impossibile comandare il display: {errore}", "errore")
    return redirect(request.referrer or url_for("index"))


# ------------------------------------------------------------------ avvio

def crea_app():
    ensure_dirs()
    con = db.init()
    app.secret_key = chiave_segreta(con)
    avvia_worker()
    return app


if __name__ == "__main__":
    from waitress import serve

    applicazione = crea_app()
    porta = db.get_int(db.connect(), "web_port", 8080)
    print(f"Pagina di gestione su http://0.0.0.0:{porta}", flush=True)
    serve(applicazione, host="0.0.0.0", port=porta, threads=4)
