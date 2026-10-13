#!/usr/bin/env bash
# Toglie di mezzo la console di testo, che altrimenti disegna il cursore
# lampeggiante e i messaggi del kernel sopra le foto.
#
# Cosa fa:
#   - sposta la console di sistema da tty1 a tty3
#   - spegne il cursore lampeggiante
#   - toglie il logo del lampone e lo spegnimento automatico dello schermo
#   - disattiva il login su tty1
#
# Reversibile: salva una copia di cmdline.txt e la ripristina con --undo.
set -euo pipefail

CMDLINE=/boot/firmware/cmdline.txt
[[ -f $CMDLINE ]] || CMDLINE=/boot/cmdline.txt
BACKUP="$CMDLINE.prima-console-off"

if [[ $EUID -ne 0 ]]; then
  echo "Serve sudo." >&2
  exit 1
fi

if [[ "${1:-}" == "--undo" ]]; then
  if [[ -f $BACKUP ]]; then
    cp "$BACKUP" "$CMDLINE"
    echo "Ripristinato $CMDLINE"
  else
    echo "Nessun backup trovato, $CMDLINE lasciato com'e'." >&2
  fi
  systemctl enable --now getty@tty1 >/dev/null 2>&1 || true
  echo "Console riattivata. Riavvia per applicare."
  exit 0
fi

[[ -f $BACKUP ]] || cp "$CMDLINE" "$BACKUP"

riga="$(tr -d '\n' < "$CMDLINE")"
riga="${riga/console=tty1/console=tty3}"
for parametro in vt.global_cursor_default=0 logo.nologo consoleblank=0; do
  chiave="${parametro%%=*}"
  if [[ $riga != *"$chiave"* ]]; then
    riga="$riga $parametro"
  fi
done
printf '%s\n' "$riga" > "$CMDLINE"

systemctl disable --now getty@tty1 >/dev/null 2>&1 || true

echo "Nuovo $CMDLINE:"
echo "  $riga"
echo
echo "Login su tty1 disattivato. Riavvia per applicare tutto."
echo "Per tornare indietro: sudo $0 --undo"
