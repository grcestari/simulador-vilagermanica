"""Parâmetros do modelo de evacuação em blackout (Parque Vila Germânica).

Os valores seguem a "Tabela de Parâmetros Calibrados" do trabalho
(`Trabalho_Evacuacao_Vila_Germanica_Blackout.pdf`), coluna "Blackout Noturno".
A tipologia dos atores (T01-T12) está em `tipos.py`.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Parametros:
    # ------------------------------------------------------------ tempo / espaço
    dt: float = 0.5              # s por passo do Mesa
    celula: float = 0.4          # m (célula de tamanho corporal 0.4 x 0.4 m)
    t_max: float = 900.0         # s (limite de segurança da simulação)

    # ------------------------------------------------------------ população
    n_ocupantes: int = 300       # composição por tipo: ver tipos.py

    # ------------------------------------------------------------ cinemática
    v_escuro_media: float = 0.45      # m/s  (faixa 0.35 - 0.55), antes do fator do tipo
    v_escuro_dp: float = 0.05
    fator_v_investigacao: float = 0.67  # ~0.3 m/s na fase de investigação
    fator_v_normal: float = 0.50        # deambulação ainda sem perceber o risco
    r_tatil: float = 0.5              # m   (0.0 - 0.5)
    r_acustico: float = 10.0          # m   (5 - 15)
    rho_crit: float = 0.5             # ped/m2
    rho_jam: float = 5.5              # ped/m2
    gamma_v: float = 1.5              # curvatura da perda de velocidade
    t_choque: tuple = (3.0, 15.0)     # s, fase 1 (choque / desorientação)

    # ------------------------------------------------------------ EDM (risco)
    alpha: float = 0.36               # pista súbita (apagão), média
    alpha_dp: float = 0.08
    beta: float = 0.010               # urgência temporal
    lam: float = 0.03                 # 1/s
    gamma_social: float = 0.03        # influência social acústica
    kappa: float = 0.020              # acomodação / dissipação
    R_I: float = 0.30                 # limiar Normal -> Investigação
    R_E: float = 0.60                 # limiar Investigação -> Evacuação
    sigma_logit: float = 0.05

    # ------------------------------------------------------------ movimento (P_ij)
    k_S: float = 2.5                  # atração ao campo de piso estático
    k_O: float = 1.0                  # atração tátil por paredes (wall tracking)
    k_D: float = 2.5                  # herding
    k_L: float = 0.4                  # viés lateral
    k_I: float = 0.8                  # inércia direcional
    d_braco: float = 0.7              # m (alcance do braço)
    omega0: float = 0.15              # susceptibilidade a herding (luz)
    omega0_escuro: float = 0.75       # (escuro: 0.70 - 0.85)
    p_vies_esquerdo: float = 0.875    # 85-90 % tateiam pelo lado esquerdo
    peso_ocupada: float = 0.15        # penalidade p/ tentar célula ocupada
    raio_alcance_porta: float = 3.0   # células: abertura perceptível ao tato

    # ------------------------------------------------------------ conflito / porta
    massa_media: float = 75.0
    massa_dp: float = 10.0
    delta_P: float = 5.0
    k_compressao: float = 5.0
    fluxo_porta: float = 1.0          # ped/s por metro de porta (escuro)

    # ------------------------------------------------------------ Mesa-LLM
    n_llm: int = 0                    # nº de agentes de IA (distribuídos entre os 12 tipos)
    llm_model: str = "gemini/gemini-3-flash-preview"
    llm_api_base: str | None = None
    reavaliacao_passos: int = 30      # reavalia a saída-alvo a cada 15 s (inércia)
    llm_max_falhas: int = 3           # falhas seguidas -> volta às regras

    semente: int | None = 42
    cenario_exp: str = "C2"           # Plano 2x2 (Slide 13): C1, C2, C3, C4
    portas_bloqueadas: tuple = ()     # ex.: ("S2",) em C3 e C4
    extra: dict = field(default_factory=dict)


CENARIOS_EXPERIMENTAIS = {
    "C1": {
        "titulo": "C1 – Controle (Iluminação de Emergência + Todas as Saídas)",
        "iluminacao": "emergencia",
        "v_escuro_media": 0.95,
        "omega0_escuro": 0.30,
        "t_choque": (1.0, 5.0),
        "portas_bloqueadas": (),
    },
    "C2": {
        "titulo": "C2 – Blackout Total (Sem Iluminação + Todas as Saídas)",
        "iluminacao": "blackout",
        "v_escuro_media": 0.45,
        "omega0_escuro": 0.75,
        "t_choque": (3.0, 15.0),
        "portas_bloqueadas": (),
    },
    "C3": {
        "titulo": "C3 – Saída Bloqueada (Iluminação de Emergência + S2 Bloqueada)",
        "iluminacao": "emergencia",
        "v_escuro_media": 0.95,
        "omega0_escuro": 0.30,
        "t_choque": (1.0, 5.0),
        "portas_bloqueadas": ("S2",),
    },
    "C4": {
        "titulo": "C4 – Cenário Crítico (Blackout Total + S2 Bloqueada)",
        "iluminacao": "blackout",
        "v_escuro_media": 0.45,
        "omega0_escuro": 0.75,
        "t_choque": (3.0, 15.0),
        "portas_bloqueadas": ("S2",),
    },
}


def parametros_por_cenario(codigo: str = "C2", **overrides) -> Parametros:
    cfg = CENARIOS_EXPERIMENTAIS.get(codigo.upper(), CENARIOS_EXPERIMENTAIS["C2"])
    kw = {
        "cenario_exp": codigo.upper(),
        "v_escuro_media": cfg["v_escuro_media"],
        "omega0_escuro": cfg["omega0_escuro"],
        "t_choque": cfg["t_choque"],
        "portas_bloqueadas": cfg["portas_bloqueadas"],
    }
    kw.update(overrides)
    return Parametros(**kw)
