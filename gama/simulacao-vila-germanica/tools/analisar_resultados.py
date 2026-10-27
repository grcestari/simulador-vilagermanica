"""
Script: analisar_resultados.py
Descrição: Processamento estatístico e geração de gráficos a partir das saídas do GAMA.
Projeto: Simulação de Evacuação no Parque Vila Germânica (Oktoberfest de Blumenau)
Autores: Gabriel Cestari e Thomas Haskel
Disciplina: Optativa I (Simulação) - Prof. Dr. Marcos Mattedi (FURB)
"""

import os
import sys
import pandas as pd
import matplotlib.pyplot as plt

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(BASE_DIR, "results")

def analisar_historico():
    csv_path = os.path.join(RESULTS_DIR, "historico_evacuacao.csv")
    if not os.path.exists(csv_path):
        print(f"[AVISO] Arquivo {csv_path} ainda não existe. Execute a simulação no GAMA primeiro.")
        return

    df = pd.read_csv(csv_path)
    print(f"Lendo histórico com {len(df)} registros...")

    plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")

    # 1. Gráfico de Percentual Evacuado e Restantes
    fig, ax1 = plt.subplots(figsize=(10, 5))
    ax1.set_xlabel("Tempo decorrido (s)")
    ax1.set_ylabel("Evacuados (%)", color="forestgreen", fontsize=12)
    line1 = ax1.plot(df["tempo_s"], df["pct_evacuados"], color="forestgreen", linewidth=2.5, label="Evacuados (%)")
    ax1.tick_params(axis="y", labelcolor="forestgreen")
    ax1.set_ylim(0, 105)

    ax2 = ax1.twinx()
    ax2.set_ylabel("Visitantes Restantes", color="crimson", fontsize=12)
    line2 = ax2.plot(df["tempo_s"], df["restantes"], color="crimson", linestyle="--", linewidth=2, label="Restantes")
    ax2.tick_params(axis="y", labelcolor="crimson")

    # Linhas de referência para T90 e T95
    ax1.axhline(90, color="gray", linestyle=":", alpha=0.7)
    ax1.axhline(95, color="gray", linestyle=":", alpha=0.7)

    plt.title("Dinâmica Temporal da Evacuação - Parque Vila Germânica", fontsize=14, fontweight="bold")
    fig.tight_layout()
    out1 = os.path.join(RESULTS_DIR, "curva_evacuacao_acumulada.png")
    plt.savefig(out1, dpi=300)
    plt.close()
    print(f"[OK] Gráfico salvo: {out1}")

    # 2. Gráfico de Fluxo por Saída (S1 a S6)
    fig, ax = plt.subplots(figsize=(11, 5))
    cores = {"fluxo_S1": "red", "fluxo_S2": "blue", "fluxo_S3": "green", "fluxo_S4": "purple", "fluxo_S5": "orange", "fluxo_S6": "cyan"}
    labels = {"fluxo_S1": "S1 (Stein)", "fluxo_S2": "S2 (Campos Oeste)", "fluxo_S3": "S3 (Pátio Leste)", "fluxo_S4": "S4 (Acesso Sul)", "fluxo_S5": "S5 (Galegão)", "fluxo_S6": "S6 (Biergarten)"}
    
    for col, c in cores.items():
        if col in df.columns:
            # Média móvel suave para melhor visualização
            suave = df[col].rolling(window=3, min_periods=1).mean()
            ax.plot(df["tempo_s"], suave, color=c, label=labels.get(col, col), linewidth=1.8)

    ax.set_xlabel("Tempo (s)", fontsize=12)
    ax.set_ylabel("Pessoas por segundo (Vazão)", fontsize=12)
    ax.set_title("Vazão Instantânea por Portão de Saída", fontsize=14, fontweight="bold")
    ax.legend(loc="upper right")
    fig.tight_layout()
    out2 = os.path.join(RESULTS_DIR, "vazao_por_saida.png")
    plt.savefig(out2, dpi=300)
    plt.close()
    print(f"[OK] Gráfico salvo: {out2}")

    # 3. Gráfico de Congestionamento (Fila proxy / agentes impedidos)
    if "impedidos" in df.columns:
        fig, ax = plt.subplots(figsize=(10, 4.5))
        ax.plot(df["tempo_s"], df["impedidos"], color="darkorange", linewidth=2.0)
        ax.fill_between(df["tempo_s"], df["impedidos"], color="orange", alpha=0.3)
        ax.set_xlabel("Tempo (s)", fontsize=12)
        ax.set_ylabel("Agentes impedidos / esperando", fontsize=12)
        ax.set_title("Evolução do Congestionamento nos Gargalos (Portões)", fontsize=14, fontweight="bold")
        fig.tight_layout()
        out3 = os.path.join(RESULTS_DIR, "evolucao_congestionamento.png")
        plt.savefig(out3, dpi=300)
        plt.close()
        print(f"[OK] Gráfico salvo: {out3}")

if __name__ == "__main__":
    analisar_historico()
