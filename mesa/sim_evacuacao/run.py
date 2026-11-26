"""Executa a simulação e gera resultados (CSV + gráficos).

Exemplos:
    python run.py                         # só regras (sem custo de API)
    python run.py --n 500 --seed 7
    python run.py --llm 3                 # 3 agentes de IA (precisa de chave em .env)
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import ListedColormap  # noqa: E402

from agentes import EVACUACAO, INVESTIGACAO, NORMAL  # noqa: E402
from config import CENARIOS_EXPERIMENTAIS, Parametros, parametros_por_cenario  # noqa: E402
from modelo import EvacuacaoModel  # noqa: E402
from tipos import TIPOS  # noqa: E402

COR = {NORMAL: "#1f77b4", INVESTIGACAO: "#ff7f0e", EVACUACAO: "#d62728"}


def desenhar(model, ax, titulo=""):
    cen = model.cen
    img = np.zeros((cen.largura, cen.altura))
    img[cen.bloqueado] = 1
    ax.imshow(img.T, origin="lower", cmap=ListedColormap(["#f5f5f0", "#222222"]),
              interpolation="nearest")
    for pid, cells in cen.portas.items():
        xs, ys = zip(*cells)
        ax.scatter(xs, ys, marker="s", s=14, c="#2ca02c")
        cx, cy = np.mean(xs), np.mean(ys)
        if cy >= cen.altura - 1:
            tx, ty = cx + 1, cy - 2
        elif cy <= 0:
            tx, ty = cx + 1, cy + 2
        elif cx <= 0:
            tx, ty = cx + 2, cy
        elif cx >= cen.largura - 1:
            tx, ty = cx - 3, cy
        else:
            tx, ty = cx + 2, cy + 2
        ax.text(tx, ty, pid, color="#2ca02c", fontsize=8, weight="bold")
    for est, cor in COR.items():
        pts = [a.pos for a in model.ocupacao.values() if a.estado == est]
        if pts:
            xs, ys = zip(*pts)
            ax.scatter(xs, ys, s=7, c=cor, label=["Normal", "Investigação", "Evacuação"][est])
    llm = [a.pos for a in model.ocupacao.values() if getattr(a, "usa_llm", False)]
    if llm:
        xs, ys = zip(*llm)
        ax.scatter(xs, ys, s=60, facecolors="none", edgecolors="k", label="Agente LLM")
    ax.set_title(titulo)
    ax.set_xticks([]); ax.set_yticks([])
    ax.legend(loc="upper right", fontsize=7)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=None, help="número de ocupantes")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--llm", type=int, default=0, help="nº de agentes de IA (Mesa-LLM)")
    ap.add_argument("--gemini-key", default=None, help="chave GEMINI_API_KEY para testar via CLI")
    ap.add_argument("--modelo-llm", default=None, help="ex.: gemini/gemini-2.0-flash")
    ap.add_argument("--saida", default="resultados")
    ap.add_argument("--comparar-2x2", action="store_true",
                    help="compara os 4 cenários (C1-C4) Sem LLM vs. Com LLM")
    ap.add_argument("--snap", type=float, nargs="*", default=[0, 30, 90, 180, 300],
                    help="instantes (s) dos instantâneos")
    a = ap.parse_args()

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    import os
    if a.gemini_key:
        os.environ["GEMINI_API_KEY"] = a.gemini_key.strip()
        if a.llm == 0:
            a.llm = 3
    logging.basicConfig(level=logging.WARNING)

    p = Parametros(n_llm=a.llm)
    if a.n:
        p.n_ocupantes = a.n
    if a.seed is not None:
        p.semente = a.seed
    p.llm_model = a.modelo_llm or os.getenv("LLM_MODEL", p.llm_model)

    out = Path(a.saida)
    out.mkdir(exist_ok=True)

    if a.comparar_2x2:
        n_llm_comp = max(1, a.llm or 3)
        comp = {}
        fig, ax = plt.subplots(figsize=(10, 4.8))
        cores_c = {"C1": "#22c55e", "C2": "#38bdf8", "C3": "#f59e0b", "C4": "#ef4444"}
        for cod in ("C1", "C2", "C3", "C4"):
            comp[cod] = {"titulo": CENARIOS_EXPERIMENTAIS[cod]["titulo"]}
            for rotulo, qtd_llm, estilo in (("sem_llm", 0, "-"), ("com_llm", n_llm_comp, "--")):
                pc = parametros_por_cenario(
                    cod, n_ocupantes=p.n_ocupantes, n_llm=qtd_llm,
                    semente=p.semente, llm_model=p.llm_model, reavaliacao_passos=999999,
                )
                mc = EvacuacaoModel(pc)
                ts, segs = [0.0], [0]
                while mc.running:
                    mc.step()
                    ts.append(mc.t)
                    segs.append(mc.n_seguros)
                rc = mc.resumo()
                comp[cod][rotulo] = rc
                ax.plot(ts, segs, ls=estilo, c=cores_c[cod],
                        label=f"{cod} {'Com LLM' if qtd_llm else 'Sem LLM'} ({rc['t_ultimo_s']}s)")
                print(f"[{cod} | {rotulo}] t_50={rc['t_50%_s']}s | t_90={rc['t_90%_s']}s | "
                      f"t_fim={rc['t_ultimo_s']}s | chamadas_llm={rc['chamadas_llm']}")
        ax.set(xlabel="t (s)", ylabel="ocupantes seguros",
               title=f"Comparação 2×2 (C1–C4): Sem LLM (contínua) vs. Com LLM ({n_llm_comp} ag., tracejada)")
        ax.legend(fontsize=8, ncol=2)
        fig.tight_layout()
        fig.savefig(out / "comparacao_2x2.png", dpi=130)
        plt.close(fig)
        (out / "comparacao_2x2.json").write_text(
            json.dumps(comp, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"Comparação 2x2 salva em {(out / 'comparacao_2x2.json').resolve()} e comparacao_2x2.png")
        return

    m = EvacuacaoModel(p)
    snaps = sorted(a.snap)
    quadros = []
    t0 = time.time()
    while m.running:
        if snaps and m.t >= snaps[0]:
            quadros.append((m.t, [(ag.pos, ag.tipo, getattr(ag, "usa_llm", False))
                                  for ag in m.ocupacao.values()]))
            snaps.pop(0)
        m.step()
    print(f"Simulação concluída em {time.time() - t0:.1f}s (tempo simulado {m.t:.0f}s)")

    res = m.resumo()
    print(json.dumps(res, indent=2, ensure_ascii=False))
    (out / "resumo.json").write_text(json.dumps(res, indent=2, ensure_ascii=False),
                                     encoding="utf-8")
    df = m.datacollector.get_model_vars_dataframe()
    df.to_csv(out / "serie_temporal.csv", index=False)

    import pandas as pd
    pd.DataFrame([{
        "id": ag.unique_id, "tipo": ag.tipo, "tipo_nome": ag.T.nome, "llm": getattr(ag, "usa_llm", False),
        "porta_familiar": ag.porta_familiar, "alvo_final": ag.alvo, "trocas_alvo": ag.trocas_alvo, "t_investigacao": ag.t_investigacao,
        "t_evacuacao": ag.t_evacuacao, "t_seguro": ag.t_seguro, "saida": ag.saida,
        "passos_bloqueado": ag.passos_bloqueado} for ag in m.agentes_total]
    ).to_csv(out / "agentes.csv", index=False)

    # --- curvas
    fig, ax = plt.subplots(1, 3, figsize=(16, 4.2))
    ax[0].plot(df.t, df.Normal, label="Normal", c=COR[NORMAL])
    ax[0].plot(df.t, df.Investigacao, label="Investigação", c=COR[INVESTIGACAO])
    ax[0].plot(df.t, df.Evacuacao, label="Evacuação", c=COR[EVACUACAO])
    ax[0].plot(df.t, df.Seguros, label="Seguros", c="#2ca02c")
    ax[0].set(xlabel="t (s)", ylabel="ocupantes", title="Estados dos agentes"); ax[0].legend()
    ax[1].plot(df.t, df.RiscoMedio, c="k"); ax[1].axhline(p.R_I, ls="--", c=COR[INVESTIGACAO])
    ax[1].axhline(p.R_E, ls="--", c=COR[EVACUACAO])
    ax[1].set(xlabel="t (s)", ylabel="R médio", title="Risco percebido (EDM)")
    for k in m.cen.portas:
        ax[2].plot(df.t, df[f"Porta_{k}"], label=k)
    ax[2].set(xlabel="t (s)", ylabel="saídas acumuladas", title="Fluxo por porta"); ax[2].legend()
    fig.tight_layout(); fig.savefig(out / "curvas.png", dpi=130); plt.close(fig)

    # --- mapa de gargalos
    fig, ax = plt.subplots(figsize=(9, 6))
    ax.imshow(np.where(m.cen.bloqueado, np.nan, m.calor_parado).T, origin="lower", cmap="hot")
    ax.imshow(np.where(m.cen.bloqueado, 1.0, np.nan).T, origin="lower", cmap="gray_r", vmin=0, vmax=1.5)
    ax.set_title("Gargalos: tempo acumulado de agentes em evacuação retidos")
    ax.set_xticks([]); ax.set_yticks([])
    fig.tight_layout(); fig.savefig(out / "gargalos.png", dpi=130); plt.close(fig)

    # --- instantâneos
    if quadros:
        fig, axs = plt.subplots(1, len(quadros), figsize=(4.6 * len(quadros), 3.6))
        axs = np.atleast_1d(axs)
        cen = m.cen
        for axi, (t, lista) in zip(axs, quadros):
            img = np.where(cen.bloqueado, 1.0, 0.0)
            axi.imshow(img.T, origin="lower", cmap=ListedColormap(["#f5f5f0", "#222222"]))
            for cod, T in TIPOS.items():
                pts = [pp for pp, tp, _ in lista if tp == cod]
                if pts:
                    xs, ys = zip(*pts); axi.scatter(xs, ys, s=6, c=T.cor)
            ll = [pp for pp, _, isl in lista if isl]
            if ll:
                xs, ys = zip(*ll); axi.scatter(xs, ys, s=40, facecolors="none", edgecolors="k")
            axi.set_title(f"t = {t:.0f} s  ({len(lista)} no pavilhão)", fontsize=9)
            axi.set_xticks([]); axi.set_yticks([])
        from matplotlib.lines import Line2D
        axs[-1].legend(handles=[Line2D([], [], marker="o", ls="", c=T.cor, label=f"{c} {T.nome}")
                                for c, T in TIPOS.items()], fontsize=6, loc="upper left",
                       bbox_to_anchor=(1.01, 1.0))
        fig.tight_layout(); fig.savefig(out / "instantaneos.png", dpi=130, bbox_inches="tight"); plt.close(fig)

    # --- tempo até a segurança por tipo (T01-T12)
    fig, ax = plt.subplots(figsize=(11, 4.2))
    dados = [[ag.t_seguro for ag in m.agentes_total if ag.tipo == c and ag.t_seguro is not None]
             for c in TIPOS]
    bp = ax.boxplot(dados, tick_labels=list(TIPOS), patch_artist=True)
    for patch, T in zip(bp["boxes"], TIPOS.values()):
        patch.set_facecolor(T.cor); patch.set_alpha(0.8)
    ax.set(xlabel="tipo de ator", ylabel="tempo até a porta (s)", title="Evacuação por tipo")
    fig.tight_layout(); fig.savefig(out / "por_tipo.png", dpi=130); plt.close(fig)

    if p.n_llm:
        logs = {ag.unique_id: ag.log_llm for ag in m.agentes_total if getattr(ag, "usa_llm", False)}
        (out / "log_llm.json").write_text(json.dumps(logs, indent=2, ensure_ascii=False,
                                                     default=str), encoding="utf-8")
    print(f"Resultados em {out.resolve()}")


if __name__ == "__main__":
    main()
