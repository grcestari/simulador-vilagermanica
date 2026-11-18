"""Cenário: pavilhão interno (zona cega), obstáculos, portas e campos de piso.

Espaço discreto em malha de células 0.4 x 0.4 m (abordagem Multi-grid do PDF).
Coordenadas (x, y), y cresce para o Norte.
"""
from __future__ import annotations

import heapq
from collections import deque
from dataclasses import dataclass, field

import numpy as np

LARGURA, ALTURA = 90, 60
X0, X1 = 6, 76      # paredes oeste / leste
Y0, Y1 = 6, 54      # paredes sul / norte

MOORE = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]


@dataclass
class Cenario:
    largura: int
    altura: int
    bloqueado: np.ndarray               # True = parede/pilar/estande
    interior: np.ndarray                # True = dentro do pavilhão (zona cega)
    portas: dict[str, list[tuple]]      # id -> células da porta
    largura_porta_m: dict[str, float]
    campos_S: dict[str, np.ndarray] = field(default_factory=dict)  # distância às portas
    d_parede: np.ndarray | None = None  # distância (células) à superfície mais próxima
    mapa_porta: dict[tuple, str] = field(default_factory=dict)
    nomes: dict[str, str] = field(default_factory=dict)
    portas_bloqueadas: dict[str, list[tuple]] = field(default_factory=dict)


def _retangulo(b, x0, x1, y0, y1):
    b[x0:x1 + 1, y0:y1 + 1] = True


def construir_cenario(celula: float = 0.4, bloqueadas: tuple[str, ...] = ()) -> Cenario:
    b = np.zeros((LARGURA, ALTURA), dtype=bool)
    interior = np.zeros_like(b)
    interior[X0 + 1:X1, Y0 + 1:Y1] = True

    # paredes externas
    _retangulo(b, X0, X1, Y0, Y0)
    _retangulo(b, X0, X1, Y1, Y1)
    _retangulo(b, X0, X0, Y0, Y1)
    _retangulo(b, X1, X1, Y0, Y1)

    # estandes / balcões (retângulos), como no esquema gráfico do PDF
    for (xa, xb, ya, yb) in [
        (12, 20, 12, 16), (12, 20, 44, 48), (30, 38, 28, 32), (50, 58, 28, 32),
        (30, 38, 46, 50), (50, 58, 10, 14), (66, 70, 8, 16), (28, 36, 10, 12),
    ]:
        _retangulo(b, xa, xb, ya, yb)
    # pilares 2x2
    for (px, py) in [(24, 20), (24, 40), (44, 20), (44, 40), (64, 22), (64, 38), (70, 26)]:
        _retangulo(b, px, px + 1, py, py + 1)

    # portas (abertura na parede)
    todas_portas = {
        "S1": [(X1, y) for y in range(18, 22)],   # leste superior-ish
        "S2": [(X1, y) for y in range(38, 42)],   # leste
        "S3": [(x, Y1) for x in range(20, 24)],   # norte
    }
    nomes_todos = {"S1": "Porta S1 (leste)", "S2": "Porta S2 (leste)", "S3": "Porta S3 (norte)"}
    bloq_set = set(bloqueadas or ())
    portas = {k: v for k, v in todas_portas.items() if k not in bloq_set}
    portas_bloq = {k: v for k, v in todas_portas.items() if k in bloq_set}
    nomes = {k: nomes_todos[k] for k in portas}
    for cells in portas.values():
        for c in cells:
            b[c] = False
    larg = {k: len(v) * celula for k, v in portas.items()}
    mapa = {c: k for k, v in portas.items() for c in v}

    cen = Cenario(LARGURA, ALTURA, b, interior, portas, larg, mapa_porta=mapa,
                  nomes=nomes, portas_bloqueadas=portas_bloq)
    _calcular_campos(cen)
    return cen


def _dijkstra(bloq, fontes):
    w, h = bloq.shape
    d = np.full((w, h), np.inf)
    pq = []
    for c in fontes:
        d[c] = 0.0
        heapq.heappush(pq, (0.0, c))
    while pq:
        dist, (x, y) = heapq.heappop(pq)
        if dist > d[x, y]:
            continue
        for dx, dy in MOORE:
            nx, ny = x + dx, y + dy
            if not (0 <= nx < w and 0 <= ny < h) or bloq[nx, ny]:
                continue
            if dx and dy and (bloq[x + dx, y] or bloq[x, y + dy]):
                continue  # sem atravessar quina
            nd = dist + (1.41421356 if dx and dy else 1.0)
            if nd < d[nx, ny]:
                d[nx, ny] = nd
                heapq.heappush(pq, (nd, (nx, ny)))
    return d


def _calcular_campos(cen: Cenario):
    """Campo de Piso Estático S_ij (por porta) e campo de obstáculos (dist. à parede)."""
    for pid, cells in cen.portas.items():
        cen.campos_S[pid] = _dijkstra(cen.bloqueado, cells)
    cen.campos_S["todas"] = np.minimum.reduce([cen.campos_S[k] for k in cen.portas])

    # bolsões inacessíveis dentro do pavilhão viram obstáculo (evita agentes presos)
    inacessivel = cen.interior & ~cen.bloqueado & ~np.isfinite(cen.campos_S["todas"])
    cen.bloqueado[inacessivel] = True

    # distância de Chebyshev à superfície sólida (BFS multi-fonte)
    w, h = cen.bloqueado.shape
    d = np.full((w, h), 99.0)
    dq = deque()
    for x, y in zip(*np.nonzero(cen.bloqueado)):
        d[x, y] = 0
        dq.append((int(x), int(y)))
    while dq:
        x, y = dq.popleft()
        for dx, dy in MOORE:
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h and d[nx, ny] > d[x, y] + 1:
                d[nx, ny] = d[x, y] + 1
                dq.append((nx, ny))
    cen.d_parede = d
