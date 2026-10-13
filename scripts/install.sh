#!/usr/bin/env bash
# Installa la cornice in /opt/cornice e prepara /var/lib/cornice.
# Rilanciabile: aggiorna il codice senza toccare dati e impostazioni.
set -euo pipefail

SORGENTE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DESTINAZIONE=/opt/cornice
DATI=/var/lib/cornice
UTENTE="${SUDO_USER:-$USER}"

if [[ $EUID -ne 0 ]]; then
  echo "Serve sudo." >&2
  exit 1
fi

echo "Installo il codice in $DESTINAZIONE"
mkdir -p "$DESTINAZIONE"
cp -r "$SORGENTE"/{common,ui,web,scripts,systemd} "$DESTINAZIONE"/
mkdir -p "$DESTINAZIONE"/assets/fonts
chown -R root:root "$DESTINAZIONE"
chmod -R a+rX "$DESTINAZIONE"

echo "Preparo i dati in $DATI (utente $UTENTE)"
mkdir -p "$DATI"/{photos,thumbs,cache,uploads_tmp}
chown -R "$UTENTE":"$UTENTE" "$DATI"

echo "Inizializzo il database"
sudo -u "$UTENTE" env PYTHONPATH="$DESTINAZIONE" \
  python3 -c "from common import db; db.init(); print('  schema pronto')"

echo "Permesso di riavvio e spegnimento per il pulsante"
cat > /etc/sudoers.d/cornice <<SUDO
# Solo questi due comandi, senza password: servono alla pressione
# prolungata del pulsante. Nessun altro privilegio.
$UTENTE ALL=(root) NOPASSWD: /usr/bin/systemctl reboot, /usr/bin/systemctl poweroff
SUDO
chmod 0440 /etc/sudoers.d/cornice
if ! visudo -cf /etc/sudoers.d/cornice >/dev/null; then
  echo "Regola sudoers non valida, la rimuovo." >&2
  rm -f /etc/sudoers.d/cornice
fi

echo "Registro i servizi"
for unita in cornice-ui cornice-web; do
  sed "s/^User=.*/User=$UTENTE/" "$SORGENTE/systemd/$unita.service" \
    > "/etc/systemd/system/$unita.service"
done
systemctl daemon-reload

cat <<FINE

Fatto.

  Avvio manuale per provare:   sudo systemctl start cornice-ui
  Log:                         journalctl -fu cornice-ui -u cornice-web
  Avvio automatico al boot:    sudo systemctl enable cornice-ui

  Caricare foto di prova:
    PYTHONPATH=$DESTINAZIONE python3 $DESTINAZIONE/scripts/import_photos.py ~/foto/

FINE
