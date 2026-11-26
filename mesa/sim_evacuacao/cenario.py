"""Planta do pavilhão obtida do shapefile do Parque Vila Germânica.

As linhas arquitetônicas do arquivo local são rasterizadas no grid do Mesa.
O recorte cobre o salão principal (indicado como 964 m² na planta); as
marcações ``SAÍDA DE EMERGÊNCIA`` no perímetro em ``pvg_textos`` posicionam S1 a S9.
"""
from __future__ import annotations

import heapq
import struct
import unicodedata
from collections import deque
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np


# 50 x 120 células internas a 0,4 m por célula representam aproximadamente
# a área de 964 m² anotada para o salão principal na própria planta.
LARGURA, ALTURA = 52, 122

_PASTA_PADRAO = Path(__file__).resolve().parent.parent / "PVG_shapefile-20261123"
_PASTA_GAMA = Path(__file__).resolve().parents[2] / "gama" / "simulacao-vila-germanica" / "includes"
PASTA_MAPA = _PASTA_PADRAO if _PASTA_PADRAO.is_dir() else _PASTA_GAMA
ARQUIVO_GEOMETRIAS = PASTA_MAPA / "pvg_geometrias.shp"
ARQUIVO_ATRIBUTOS_GEOMETRIAS = PASTA_MAPA / "pvg_geometrias.dbf"
ARQUIVO_TEXTOS = PASTA_MAPA / "pvg_textos.shp"
ARQUIVO_ATRIBUTOS_TEXTOS = PASTA_MAPA / "pvg_textos.dbf"

# Coordenadas cartesianas locais do recorte do salão principal.
MAPA_X0, MAPA_X1 = 1094.0, 2018.0
MAPA_Y0, MAPA_Y1 = 425.0, 2559.0

# Camadas que representam paredes, esquadrias, elementos de concreto e
# componentes arquitetônicos. A camada 0 contém blocos arquitetônicos do CAD.
CAMADAS_ESTRUTURAIS = {
    "0",
    "ARQ-VISTA 0",
    "ARQ-ESQUADRIAS",
    "ARQ-ALV-ALT",
    "ARQ-ALV-BXA",
    "ARQ-ALV-TRACEJADO",
    "ARQ-CONC-VISTA",
    "ARQ-EQUIPAMENTO",
    "ARQ-ESTR-CONCRETO",
    "ARQ-VIDRO TEMP",
    "P-CINZA252",
    "P-CINZA253",
    "Paredes",
}

MOORE = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]


@dataclass
class Cenario:
    largura: int
    altura: int
    bloqueado: np.ndarray               # True = parede ou obstáculo da planta
    interior: np.ndarray                # True = célula interna do pavilhão
    portas: dict[str, list[tuple]]      # id -> células da porta
    largura_porta_m: dict[str, float]
    campos_S: dict[str, np.ndarray] = field(default_factory=dict)
    d_parede: np.ndarray | None = None
    mapa_porta: dict[tuple, str] = field(default_factory=dict)
    nomes: dict[str, str] = field(default_factory=dict)
    portas_bloqueadas: dict[str, list[tuple]] = field(default_factory=dict)


def _ler_dbf(caminho: Path, campo_procurado: str):
    """Retorna a tabela DBF e os offsets do campo solicitado."""
    if not caminho.is_file():
        raise FileNotFoundError(f"Arquivo DBF do mapa não encontrado: {caminho}")

    dados = caminho.read_bytes()
    if len(dados) < 33:
        raise ValueError(f"Arquivo DBF inválido: {caminho}")

    quantidade = struct.unpack_from("<I", dados, 4)[0]
    cabecalho, tamanho_registro = struct.unpack_from("<HH", dados, 8)
    pos = 32
    deslocamento = 1  # cada registro começa com o marcador de exclusão
    encontrado = None
    while pos < cabecalho and dados[pos] != 0x0D:
        descritor = dados[pos:pos + 32]
        nome = descritor[:11].split(b"\0", 1)[0].decode("ascii", errors="ignore").strip()
        tamanho = descritor[16]
        if nome.casefold() == campo_procurado.casefold():
            encontrado = (deslocamento, tamanho)
        deslocamento += tamanho
        pos += 32

    if encontrado is None:
        raise ValueError(f"Campo {campo_procurado!r} não existe em {caminho.name}")
    if cabecalho + quantidade * tamanho_registro > len(dados):
        raise ValueError(f"Tabela DBF truncada: {caminho}")
    return dados, quantidade, cabecalho, tamanho_registro, encontrado


def _normalizar_texto(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in sem_acento if not unicodedata.combining(c)).strip().upper()


def _tem_rotulo_saida(textos, ponto_emergencia: tuple[float, float]) -> bool:
    """Confirma que EMERGÊNCIA está associado à palavra SAÍDA na planta."""
    ex, ey = ponto_emergencia
    letras = [item for item in textos if item[0] in {"S", "A", "I", "D"}]
    for _, sx, sy in (item for item in letras if item[0] == "S"):
        if (sx - ex) ** 2 + (sy - ey) ** 2 > 22.0 ** 2:
            continue

        vertical = sorted(
            (item for item in letras if abs(item[1] - sx) <= 4.0 and 0 <= sy - item[2] <= 24.0),
            key=lambda item: item[2], reverse=True,
        )
        horizontal = sorted(
            (item for item in letras if abs(item[2] - sy) <= 4.0 and 0 <= item[1] - sx <= 24.0),
            key=lambda item: item[1],
        )
        for linha in (vertical, horizontal):
            caracteres = [item[0] for item in linha]
            if any(caracteres[i:i + 5] == ["S", "A", "I", "D", "A"]
                   for i in range(len(caracteres) - 4)):
                return True
    return False


def _coordenada_grade(x: float, y: float) -> tuple[int, int]:
    """Transforma coordenadas locais para a malha, sem girar a planta."""
    gx = round((x - MAPA_X0) / (MAPA_X1 - MAPA_X0) * (LARGURA - 1))
    gy = round((y - MAPA_Y0) / (MAPA_Y1 - MAPA_Y0) * (ALTURA - 1))
    return (
        min(LARGURA - 1, max(0, int(gx))),
        min(ALTURA - 1, max(0, int(gy))),
    )


def _marcacoes_de_saida() -> dict[str, list[tuple[int, int]]]:
    """Lê os rótulos SAÍDA DE EMERGÊNCIA e os converte em portas de 1,6 m."""
    dbf, quantidade, cabecalho, tamanho_registro, campo_texto = _ler_dbf(
        ARQUIVO_ATRIBUTOS_TEXTOS, "TEXT"
    )
    if not ARQUIVO_TEXTOS.is_file():
        raise FileNotFoundError(f"Shapefile de textos não encontrado: {ARQUIVO_TEXTOS}")

    dados = ARQUIVO_TEXTOS.read_bytes()
    textos = []
    pos = 100
    indice = 0
    while pos + 8 <= len(dados):
        tamanho = struct.unpack_from(">i", dados, pos + 4)[0] * 2
        inicio = pos + 8
        fim = inicio + tamanho
        if tamanho < 20 or fim > len(dados):
            raise ValueError(f"Registro inválido no shapefile {ARQUIVO_TEXTOS.name}")

        tipo = struct.unpack_from("<i", dados, inicio)[0]
        if indice < quantidade and tipo == 1:
            registro = cabecalho + indice * tamanho_registro
            if dbf[registro:registro + 1] != b"*":
                deslocamento_texto, tamanho_texto = campo_texto
                texto = dbf[
                    registro + deslocamento_texto:registro + deslocamento_texto + tamanho_texto
                ].decode("utf-8", errors="replace")
                x, y = struct.unpack_from("<2d", dados, inicio + 4)
                textos.append((_normalizar_texto(texto), x, y))

        indice += 1
        pos = fim

    marcacoes = [
        (x, y) for texto, x, y in textos
        if texto == "EMERGENCIA"
        and MAPA_X0 <= x <= MAPA_X1 and MAPA_Y0 <= y <= MAPA_Y1
        and _tem_rotulo_saida(textos, (x, y))
    ]

    def lado_da_parede(ponto):
        x, y = ponto
        distancias = {
            "esquerda": x - MAPA_X0,
            "direita": MAPA_X1 - x,
            "inferior": y - MAPA_Y0,
            "superior": MAPA_Y1 - y,
        }
        lado = min(distancias, key=distancias.get)
        return lado if distancias[lado] <= 100.0 else "interno"

    por_lado = {lado: [] for lado in ("superior", "direita", "inferior", "esquerda", "interno")}
    for ponto in marcacoes:
        por_lado[lado_da_parede(ponto)].append(ponto)

    # Mantém S1/S2 na parede superior e S3 na saída mais ao norte da lateral;
    # considera apenas saídas no perímetro. Rótulos internos não são portas.
    ordenadas = (
        sorted(por_lado["superior"], key=lambda p: p[0])
        + sorted(por_lado["direita"], key=lambda p: (-p[1], -p[0]))
        + sorted(por_lado["esquerda"], key=lambda p: -p[1])
        + sorted(por_lado["inferior"], key=lambda p: p[0])
    )
    if len(por_lado["superior"]) < 2 or not por_lado["direita"] or len(ordenadas) < 3:
        raise ValueError(
            "Não foram encontrados os rótulos de saída esperados no recorte do pavilhão."
        )

    def faixa(centro: int, limite: int) -> range:
        tamanho = 4
        inicio = min(max(1, centro - tamanho // 2), limite - 1 - tamanho)
        return range(inicio, inicio + tamanho)

    portas = {}
    for indice, ponto in enumerate(ordenadas, start=1):
        pid = f"S{indice}"
        gx, gy = _coordenada_grade(*ponto)
        lado = lado_da_parede(ponto)
        if lado == "superior":
            portas[pid] = [(x, ALTURA - 1) for x in faixa(gx, LARGURA)]
        elif lado == "inferior":
            portas[pid] = [(x, 0) for x in faixa(gx, LARGURA)]
        elif lado == "esquerda":
            portas[pid] = [(0, y) for y in faixa(gy, ALTURA)]
        elif lado == "direita":
            portas[pid] = [(LARGURA - 1, y) for y in faixa(gy, ALTURA)]
        else:
            portas[pid] = [(x, gy) for x in faixa(gx, LARGURA)]
    return portas


def _recortar_segmento(x0: float, y0: float, x1: float, y1: float):
    """Recorte de Liang-Barsky para ignorar a planta fora do salão."""
    dx, dy = x1 - x0, y1 - y0
    entrada, saida = 0.0, 1.0
    limites = (
        (-dx, x0 - MAPA_X0),
        (dx, MAPA_X1 - x0),
        (-dy, y0 - MAPA_Y0),
        (dy, MAPA_Y1 - y0),
    )
    for p, q in limites:
        if p == 0:
            if q < 0:
                return None
            continue
        razao = q / p
        if p < 0:
            entrada = max(entrada, razao)
        else:
            saida = min(saida, razao)
        if entrada > saida:
            return None
    return (
        x0 + entrada * dx,
        y0 + entrada * dy,
        x0 + saida * dx,
        y0 + saida * dy,
    )


def _desenhar_segmento(bloqueado: np.ndarray, x0: float, y0: float, x1: float, y1: float):
    segmento = _recortar_segmento(x0, y0, x1, y1)
    if segmento is None:
        return
    x0, y0, x1, y1 = segmento
    ix, iy = _coordenada_grade(x0, y0)
    fx, fy = _coordenada_grade(x1, y1)

    dx = abs(fx - ix)
    sx = 1 if ix < fx else -1
    dy = -abs(fy - iy)
    sy = 1 if iy < fy else -1
    erro = dx + dy
    while True:
        bloqueado[ix, iy] = True
        if ix == fx and iy == fy:
            break
        dobro = 2 * erro
        if dobro >= dy:
            erro += dy
            ix += sx
        if dobro <= dx:
            erro += dx
            iy += sy


def _rasterizar_geometrias(bloqueado: np.ndarray):
    if not ARQUIVO_GEOMETRIAS.is_file():
        raise FileNotFoundError(f"Shapefile de geometrias não encontrado: {ARQUIVO_GEOMETRIAS}")

    dbf, quantidade, cabecalho, tamanho_registro, campo_layer = _ler_dbf(
        ARQUIVO_ATRIBUTOS_GEOMETRIAS, "LAYER"
    )
    dados = ARQUIVO_GEOMETRIAS.read_bytes()
    pos = 100
    indice = 0
    while pos + 8 <= len(dados):
        tamanho = struct.unpack_from(">i", dados, pos + 4)[0] * 2
        inicio = pos + 8
        fim = inicio + tamanho
        if tamanho < 4 or fim > len(dados):
            raise ValueError(f"Registro inválido no shapefile {ARQUIVO_GEOMETRIAS.name}")

        tipo = struct.unpack_from("<i", dados, inicio)[0]
        if indice < quantidade and tipo in {3, 13, 23} and tamanho >= 44:
            xmin, ymin, xmax, ymax = struct.unpack_from("<4d", dados, inicio + 4)
            cruza_recorte = (
                xmax >= MAPA_X0 and xmin <= MAPA_X1
                and ymax >= MAPA_Y0 and ymin <= MAPA_Y1
            )
            extensao = max(xmax - xmin, ymax - ymin)
            registro = cabecalho + indice * tamanho_registro
            deslocamento_layer, tamanho_layer = campo_layer
            layer = dbf[
                registro + deslocamento_layer:registro + deslocamento_layer + tamanho_layer
            ].decode("utf-8", errors="replace").strip()
            limite_extensao = 4.0 if layer == "ARQ-ESQUADRIAS" else 8.0
            if (
                cruza_recorte
                and layer in CAMADAS_ESTRUTURAIS
                and extensao >= limite_extensao
                and dbf[registro:registro + 1] != b"*"
            ):
                partes, pontos = struct.unpack_from("<2i", dados, inicio + 36)
                inicio_partes = inicio + 44
                inicio_pontos = inicio_partes + partes * 4
                if partes > 0 and pontos > 1 and inicio_pontos + pontos * 16 <= fim:
                    indices_partes = struct.unpack_from(f"<{partes}i", dados, inicio_partes)
                    finais = (*indices_partes[1:], pontos)
                    for primeiro, ultimo in zip(indices_partes, finais):
                        anterior = None
                        for i in range(primeiro, ultimo):
                            x, y = struct.unpack_from("<2d", dados, inicio_pontos + i * 16)
                            if anterior is not None:
                                _desenhar_segmento(bloqueado, *anterior, x, y)
                            anterior = (x, y)

        indice += 1
        pos = fim


@lru_cache(maxsize=1)
def _cenario_base():
    bloqueado = np.zeros((LARGURA, ALTURA), dtype=bool)
    interior = np.zeros_like(bloqueado)
    interior[1:-1, 1:-1] = True

    _rasterizar_geometrias(bloqueado)

    # Fecha o perímetro do recorte; as aberturas reais são reabertas abaixo.
    bloqueado[0, :] = True
    bloqueado[-1, :] = True
    bloqueado[:, 0] = True
    bloqueado[:, -1] = True
    portas = _marcacoes_de_saida()
    for cells in portas.values():
        for x, y in cells:
            if 0 < x < LARGURA - 1 and 0 < y < ALTURA - 1:
                interior[x, y] = False
    return bloqueado, interior, portas


def construir_cenario(celula: float = 0.4, bloqueadas: tuple[str, ...] = ()) -> Cenario:
    bloqueado_base, interior_base, portas_todas = _cenario_base()
    b = bloqueado_base.copy()
    interior = interior_base.copy()
    bloq_set = {str(pid).upper() for pid in (bloqueadas or ())}

    portas = {k: v for k, v in portas_todas.items() if k not in bloq_set}
    portas_bloq = {k: v for k, v in portas_todas.items() if k in bloq_set}
    for pid, cells in portas_todas.items():
        for c in cells:
            if c[0] not in (0, LARGURA - 1) and c[1] not in (0, ALTURA - 1):
                continue
            bloqueada = pid in bloq_set
            b[c] = bloqueada
            if not bloqueada:
                if c[0] == 0:
                    direcao_interna = (1, 0)
                    direcao_lateral = (0, 1)
                elif c[0] == LARGURA - 1:
                    direcao_interna = (-1, 0)
                    direcao_lateral = (0, 1)
                elif c[1] == 0:
                    direcao_interna = (0, 1)
                    direcao_lateral = (1, 0)
                elif c[1] == ALTURA - 1:
                    direcao_interna = (0, -1)
                    direcao_lateral = (1, 0)

                # Os shapefiles representam a espessura das paredes com linhas
                # paralelas. Abre um corredor curto e transversal à parede para
                # conectar a porta ao salão, inclusive quando o traço rasterizado
                # fica deslocado uma célula em relação ao rótulo da esquadria.
                for lateral in (-1, 0, 1):
                    for profundidade in range(1, 5):
                        vizinha = (
                            c[0] + direcao_lateral[0] * lateral
                            + direcao_interna[0] * profundidade,
                            c[1] + direcao_lateral[1] * lateral
                            + direcao_interna[1] * profundidade,
                        )
                        if 0 <= vizinha[0] < LARGURA and 0 <= vizinha[1] < ALTURA:
                            b[vizinha] = False

    nomes = {k: f"Saída de emergência {k}" for k in portas}
    larg = {k: len(v) * celula for k, v in portas.items()}
    mapa = {c: k for k, v in portas.items() for c in v}

    cen = Cenario(
        LARGURA, ALTURA, b, interior, portas, larg,
        mapa_porta=mapa, nomes=nomes, portas_bloqueadas=portas_bloq,
    )
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
    """Campos geodésicos até as portas e distância até a parede mais próxima."""
    for pid, cells in cen.portas.items():
        cen.campos_S[pid] = _dijkstra(cen.bloqueado, cells)
    cen.campos_S["todas"] = np.minimum.reduce([cen.campos_S[k] for k in cen.portas])

    inacessivel = cen.interior & ~cen.bloqueado & ~np.isfinite(cen.campos_S["todas"])
    cen.bloqueado[inacessivel] = True

    # Distância de Chebyshev à superfície sólida (BFS multi-fonte).
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
