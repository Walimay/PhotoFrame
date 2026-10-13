"""Schermata mostrata finche' non c'e' nessuna foto in archivio.

Resta visibile a tempo indeterminato: e' l'unico momento in cui l'utente
ha bisogno di sapere dove collegarsi. Appena arriva la prima foto il loop
principale passa allo slideshow e questa schermata non si rivede piu'.
"""
import pygame

from common import dates
from ui import theme


def draw(screen, info, web_port, now):
    w, h = screen.get_size()
    screen.fill(theme.BG_DARK)

    clock_img = theme.font(theme.CLOCK_SIZE + 24, "medium").render(
        now.strftime("%H:%M"), True, theme.WHITE)
    screen.blit(clock_img, clock_img.get_rect(center=(w // 2, int(h * 0.30))))

    date_img = theme.font(theme.BODY_SIZE).render(
        dates.long_date(now), True, theme.MUTED)
    screen.blit(date_img, date_img.get_rect(center=(w // 2, int(h * 0.30) + 72)))

    line_y = int(h * 0.52)
    pygame.draw.line(screen, (54, 59, 66),
                     (w // 2 - 170, line_y), (w // 2 + 170, line_y), 1)

    msg = theme.font(theme.BODY_SIZE, "medium").render(
        "Nessuna foto caricata", True, theme.WHITE)
    screen.blit(msg, msg.get_rect(center=(w // 2, line_y + 50)))

    if info.get("ip"):
        url = f"http://{info['ip']}:{web_port}"
        url_img = theme.font(theme.BODY_SIZE + 4, "medium").render(
            url, True, theme.ACCENT)
        screen.blit(url_img, url_img.get_rect(center=(w // 2, line_y + 112)))

        if info.get("mdns"):
            alt = theme.font(theme.SMALL_SIZE).render(
                f"oppure http://{info['mdns']}:{web_port}", True, theme.MUTED)
            screen.blit(alt, alt.get_rect(center=(w // 2, line_y + 152)))
    else:
        warn = theme.font(theme.BODY_SIZE).render(
            "In attesa della connessione WiFi", True, (239, 159, 39))
        screen.blit(warn, warn.get_rect(center=(w // 2, line_y + 112)))

