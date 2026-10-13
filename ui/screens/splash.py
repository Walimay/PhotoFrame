"""Schermata di avvio: stato rete e indirizzo a cui collegarsi."""
import pygame

from ui import theme


def _dot(surface, center, color):
    pygame.draw.circle(surface, color, center, 7)


def draw(screen, info, web_port):
    w, h = screen.get_size()
    screen.fill(theme.BG_DARK)

    title = theme.font(theme.TITLE_SIZE, "medium").render(
        "Cornice digitale", True, theme.WHITE)
    screen.blit(title, (theme.MARGIN * 2, int(h * 0.26)))

    y = int(h * 0.26) + title.get_height() + theme.GAP * 3
    left = theme.MARGIN * 2
    body = theme.font(theme.BODY_SIZE)
    small = theme.font(theme.SMALL_SIZE)

    rows = []
    if info.get("ssid"):
        rows.append((theme.ACCENT, "WiFi", info["ssid"]))
    else:
        rows.append(((226, 75, 74), "WiFi", "non connesso"))

    if info.get("ip"):
        rows.append((theme.ACCENT_COOL, "Indirizzo", info["ip"]))
    if info.get("mdns"):
        rows.append((theme.MUTED, "Nome rete", info["mdns"]))

    for color, label, value in rows:
        _dot(screen, (left + 7, y + body.get_height() // 2), color)
        label_img = small.render(label, True, theme.MUTED)
        screen.blit(label_img, (left + 30, y + 5))
        value_img = body.render(value, True, theme.WHITE)
        screen.blit(value_img, (left + 30 + 170, y))
        y += body.get_height() + theme.GAP

    y += theme.GAP * 2
    if info.get("ip"):
        url = f"http://{info['ip']}:{web_port}"
        hint = theme.font(theme.BODY_SIZE, "medium").render(url, True, theme.ACCENT)
        screen.blit(hint, (left + 30, y))
        y += hint.get_height() + 6
        note = small.render("pagina di gestione e caricamento foto",
                            True, theme.MUTED)
        screen.blit(note, (left + 30, y))

    if info.get("ntp") is False:
        warn = small.render("orologio non ancora sincronizzato",
                            True, (239, 159, 39))
        screen.blit(warn, (left + 30, h - theme.MARGIN * 2))

