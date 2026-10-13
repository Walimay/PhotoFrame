"""Riquadri temporanei disegnati sopra la schermata corrente.

Non sono stati della macchina: compaiono e spariscono senza che la
schermata sotto cambi. Chi li disegna conserva una copia di cio' che
c'era prima e la ripristina.
"""
import pygame

from ui import theme


def conto_alla_rovescia(screen, titolo, sottotitolo, progresso):
    """Riquadro centrale con barra di avanzamento.

    progresso va da 0 a 1 ed e' quanto manca al compimento dell'azione.
    Restituisce il rettangolo toccato, per ripristinare solo quello.
    """
    larghezza_schermo, altezza_schermo = screen.get_size()
    larghezza = min(560, larghezza_schermo - theme.MARGIN * 4)
    altezza = 188

    riquadro = pygame.Surface((larghezza, altezza), pygame.SRCALPHA)
    pygame.draw.rect(riquadro, (10, 12, 15, 232), riquadro.get_rect(),
                     border_radius=16)
    pygame.draw.rect(riquadro, theme.HAIRLINE, riquadro.get_rect(),
                     width=1, border_radius=16)

    testo = theme.font(theme.TITLE_SIZE - 6, "medium").render(
        titolo, True, theme.WHITE)
    riquadro.blit(testo, testo.get_rect(center=(larghezza // 2, 58)))

    nota = theme.font(theme.SMALL_SIZE).render(
        sottotitolo, True, theme.MUTED)
    riquadro.blit(nota, nota.get_rect(center=(larghezza // 2, 100)))

    margine = 36
    barra = pygame.Rect(margine, altezza - 48, larghezza - margine * 2, 6)
    pygame.draw.rect(riquadro, (255, 255, 255, 46), barra, border_radius=3)
    riempita = barra.copy()
    riempita.width = max(3, int(barra.width * max(0.0, min(1.0, progresso))))
    pygame.draw.rect(riquadro, theme.ACCENT, riempita, border_radius=3)

    posizione = riquadro.get_rect(
        center=(larghezza_schermo // 2, altezza_schermo // 2))
    screen.blit(riquadro, posizione)
    return posizione
