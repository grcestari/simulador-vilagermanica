"""Tipologia dos atores (legenda T01–T12 do esquema fornecido).

Cada tipo traz *capacidades* (controladas pelo motor: ritmo, atraso de reação,
erro e percepção) e *perfil decisório* (0-1, usado na escolha da saída-alvo):
aversao_aglomeracao, preferencia_familiaridade, inercia_decisao, cautela_incerteza.

Os valores numéricos são hipóteses de modelagem (intensidades relativas, não
probabilidades calibradas) e devem ser calibrados/justificados no trabalho.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TipoAtor:
    codigo: str
    nome: str
    cor: str                      # cor da legenda
    proporcao: float              # composição da população (soma = 1)
    papel: str                    # papel social contextual (sem ações de resgate)
    v_fator: float                # multiplicador da velocidade no escuro
    atraso_reacao: float          # s somados à fase de choque/desorientação
    erro_percepcao: float         # 0-1: ruído na estimativa de distância/ocupação
    alcance_acustico: float       # multiplicador de r_acustico (herding / info social)
    aversao_aglomeracao: float
    preferencia_familiaridade: float
    inercia_decisao: float
    cautela_incerteza: float
    conhece_todas: bool = False   # funcionário/brigadista conhece todas as saídas


TIPOS: dict[str, TipoAtor] = {t.codigo: t for t in [
    TipoAtor("T01", "Adulto sóbrio", "#2f6fe4", 0.46, "visitante", 1.00, 0.0, 0.03, 1.0, 0.50, 0.40, 0.40, 0.40),
    TipoAtor("T02", "Álcool: comprometimento moderado", "#f07b1d", 0.12, "visitante", 0.90, 3.0, 0.10, 1.0, 0.35, 0.50, 0.60, 0.25),
    TipoAtor("T03", "Álcool: comprometimento acentuado", "#b82025", 0.05, "visitante", 0.75, 8.0, 0.25, 0.8, 0.20, 0.60, 0.75, 0.15),
    TipoAtor("T04", "Criança", "#e6ac00", 0.05, "visitante", 0.75, 2.0, 0.12, 1.0, 0.60, 0.80, 0.50, 0.70),
    TipoAtor("T05", "Pessoa idosa autônoma", "#7a47e0", 0.08, "visitante", 0.80, 3.0, 0.06, 1.0, 0.60, 0.70, 0.60, 0.60),
    TipoAtor("T06", "Mobilidade reduzida", "#8a5a14", 0.03, "visitante", 0.60, 3.0, 0.05, 1.0, 0.70, 0.60, 0.60, 0.60),
    TipoAtor("T07", "Pessoa em cadeira de rodas", "#1590b0", 0.02, "visitante", 0.65, 3.0, 0.05, 1.0, 0.75, 0.60, 0.60, 0.60),
    TipoAtor("T08", "Pessoa com baixa visão", "#e0307e", 0.03, "visitante", 0.80, 3.0, 0.12, 1.0, 0.50, 0.80, 0.60, 0.70),
    TipoAtor("T09", "Pessoa com deficiência auditiva", "#1fb5a0", 0.03, "visitante", 1.00, 4.0, 0.06, 0.3, 0.50, 0.50, 0.50, 0.50),
    TipoAtor("T10", "Necessidade de apoio à orientação", "#667488", 0.03, "visitante", 0.90, 4.0, 0.20, 1.0, 0.50, 0.80, 0.70, 0.80),
    TipoAtor("T11", "Acompanhante / cuidador", "#5a8a1e", 0.04, "cuidador", 0.95, 1.0, 0.04, 1.0, 0.50, 0.50, 0.50, 0.60),
    TipoAtor("T12", "Funcionário / brigadista", "#1d2b3d", 0.06, "brigadista", 1.00, 0.0, 0.01, 1.0, 0.60, 0.30, 0.40, 0.30, True),
]}

CODIGOS = list(TIPOS)


def sortear_composicao(n: int, rng) -> list[str]:
    """Lista de n códigos de tipo (maior resto); garante ao menos 1 de cada se n >= 12."""
    brutos = {c: TIPOS[c].proporcao * n for c in CODIGOS}
    cont = {c: int(v) for c, v in brutos.items()}
    if n >= len(CODIGOS):
        for c in CODIGOS:
            cont[c] = max(1, cont[c])
    falta = n - sum(cont.values())
    resto = sorted(CODIGOS, key=lambda c: brutos[c] - int(brutos[c]), reverse=True)
    i = 0
    while falta != 0:
        c = resto[i % len(resto)]
        if falta > 0:
            cont[c] += 1; falta -= 1
        elif cont[c] > 1:
            cont[c] -= 1; falta += 1
        i += 1
    lista = [c for c in CODIGOS for _ in range(cont[c])]
    rng.shuffle(lista)
    return lista
