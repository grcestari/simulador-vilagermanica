r"""Dashboard visual interativo para a simulação de evacuação (Parque Vila Germânica).

Executa um servidor web local (Starlette + Uvicorn) com visualização em tempo real:
    - Mapa espacial do pavilhão rasterizado a partir do shapefile (células 0,4 x 0,4 m, saídas da planta)
- 12 tipos de atores (T01-T12) com filtro interativo e cores oficiais da legenda
- Camadas de mapa de calor: Densidade (pessoas/m²), Gargalos e Campo de Piso Estático (S_ij)
- Medidor de Congestão, Tempo de Evacuação, Risco Percebido (EDM) e Fluxo por Porta
- Inspetor de Agente + Feed de Decisões (PROMPT_EVACUACAO_V8: saída e justificativa)
- Comparador automático do Plano Experimental 2x2 (Cenários C1, C2, C3 e C4 da Aula 14)

Uso:
    .\.venv\Scripts\python dashboard.py
    .\.venv\Scripts\python dashboard.py --porta 8765 --sem-abrir
"""
from __future__ import annotations

import argparse
import os
import threading
import webbrowser
from pathlib import Path

import numpy as np
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route

from agentes import EVACUACAO, INVESTIGACAO, NORMAL, NOME_ESTADO
from config import CENARIOS_EXPERIMENTAIS, parametros_por_cenario
from modelo import EvacuacaoModel
from tipos import CODIGOS, TIPOS

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class EstadoSimulacao:
    """Mantém a instância ativa do modelo e histórico leve para o dashboard."""

    def __init__(self):
        self.lock = threading.Lock()
        self.cenario_codigo = "C2"
        self.n_ocupantes = 300
        self.n_llm = 0
        self.seed = 42
        self.reiniciar("C2", 300, 0, 42)

    def reiniciar(
        self,
        cenario: str = "C2",
        n: int = 300,
        n_llm: int = 0,
        seed: int = 42,
        gemini_api_key: str | None = None,
    ):
        with self.lock:
            if gemini_api_key is not None:
                chave = gemini_api_key.strip()
                if chave:
                    os.environ["GEMINI_API_KEY"] = chave
            self.cenario_codigo = cenario.upper()
            self.n_ocupantes = int(max(12, min(800, n)))
            self.n_llm = int(max(0, min(self.n_ocupantes, n_llm)))
            self.seed = int(seed)
            p = parametros_por_cenario(
                self.cenario_codigo,
                n_ocupantes=self.n_ocupantes,
                n_llm=self.n_llm,
                semente=self.seed,
            )
            self.model = EvacuacaoModel(p)
            self.serie = [self._ponto_serie()]
            self._estatico = self._gerar_estatico()

    def _gerar_estatico(self) -> dict:
        m = self.model
        cen = m.cen
        S = cen.campos_S["todas"]
        s_limpo = np.where(np.isfinite(S) & cen.interior, np.round(S * m.p.celula, 1), -1.0)
        return {
            "largura": cen.largura,
            "altura": cen.altura,
            "celula_m": m.p.celula,
            "bloqueado": cen.bloqueado.astype(int).tolist(),
            "interior": cen.interior.astype(int).tolist(),
            "portas": {k: [list(c) for c in v] for k, v in cen.portas.items()},
            "portas_bloqueadas": {k: [list(c) for c in v] for k, v in cen.portas_bloqueadas.items()},
            "nomes_portas": cen.nomes,
            "campo_S": s_limpo.tolist(),
            "tipos": {
                c: {
                    "codigo": c,
                    "nome": TIPOS[c].nome,
                    "cor": TIPOS[c].cor,
                    "papel": TIPOS[c].papel,
                    "v_fator": TIPOS[c].v_fator,
                    "atraso_reacao": TIPOS[c].atraso_reacao,
                    "erro_percepcao": TIPOS[c].erro_percepcao,
                    "aversao_aglomeracao": TIPOS[c].aversao_aglomeracao,
                    "preferencia_familiaridade": TIPOS[c].preferencia_familiaridade,
                    "inercia_decisao": TIPOS[c].inercia_decisao,
                    "cautela_incerteza": TIPOS[c].cautela_incerteza,
                }
                for c in CODIGOS
            },
            "cenarios": {
                k: {"titulo": v["titulo"], "iluminacao": v["iluminacao"],
                    "portas_bloqueadas": list(v["portas_bloqueadas"])}
                for k, v in CENARIOS_EXPERIMENTAIS.items()
            },
            "limiares": {"R_I": m.p.R_I, "R_E": m.p.R_E, "rho_jam": m.p.rho_jam},
        }

    def _ponto_serie(self) -> dict:
        m = self.model
        return {
            "t": round(m.t, 1),
            "Normal": m._conta(NORMAL),
            "Investigacao": m._conta(INVESTIGACAO),
            "Evacuacao": m._conta(EVACUACAO),
            "Seguros": m.n_seguros,
            "RiscoMedio": round(m._risco_medio(), 3),
            "Retidos": int(m._retidos),
            "Conflitos": int(m.conflitos),
            "Portas": {k: int(v) for k, v in m.saidas.items()},
        }

    def avancar(self, passos: int = 1, ate_fim: bool = False):
        with self.lock:
            m = self.model
            limite = 2500 if ate_fim else max(1, min(200, int(passos)))
            n = 0
            while m.running and n < limite:
                m.step()
                self.serie.append(self._ponto_serie())
                n += 1

    def snapshot(self) -> dict:
        with self.lock:
            m = self.model
            cen = m.cen
            # grade de densidade local (ped/m2) em blocos 3x3 células para envio leve
            w, h = cen.largura, cen.altura
            dens = np.zeros((w, h), dtype=np.float32)
            area_viz = (5 * m.p.celula) ** 2
            for (x, y), ag in m.ocupacao.items():
                dens[x, y] = round(float(getattr(ag, "rho", m.soma("pres", x, y, 2) / area_viz)), 2)

            agentes_ativos = []
            for ag in m.ocupacao.values():
                ult_just = ag.memoria[-1]["justificativa"] if ag.memoria else ""
                agentes_ativos.append({
                    "id": ag.unique_id,
                    "x": int(ag.pos[0]),
                    "y": int(ag.pos[1]),
                    "tipo": ag.tipo,
                    "estado": int(ag.estado),
                    "estado_nome": NOME_ESTADO[ag.estado],
                    "R": round(float(ag.R), 2),
                    "rho": round(float(getattr(ag, "rho", 0.0)), 2),
                    "v": round(float(ag.v_i), 2),
                    "alvo": ag.alvo,
                    "familiar": ag.porta_familiar,
                    "llm": bool(getattr(ag, "usa_llm", False)),
                    "hx": round(float(ag.h[0]), 2),
                    "hy": round(float(ag.h[1]), 2),
                    "trocas": int(ag.trocas_alvo),
                    "bloqueado": int(ag.passos_bloqueado),
                    "justificativa": ult_just,
                })

            # estatísticas por tipo T01..T12
            por_tipo = {}
            for c in CODIGOS:
                tot = [a for a in m.agentes_total if a.tipo == c]
                seg = [a.t_seguro for a in tot if a.t_seguro is not None]
                ativos = sum(1 for a in tot if a.t_seguro is None)
                por_tipo[c] = {
                    "total": len(tot),
                    "ativos": ativos,
                    "seguros": len(seg),
                    "t_medio": round(float(np.mean(seg)), 1) if seg else None,
                }

            # feed de decisões recentes (prioriza agentes LLM + últimas decisões)
            decisoes_recentes = []
            for ag in m.agentes_total:
                if ag.memoria:
                    u = ag.memoria[-1]
                    decisoes_recentes.append({
                        "id": ag.unique_id,
                        "tipo": ag.tipo,
                        "tipo_nome": ag.T.nome,
                        "cor": ag.T.cor,
                        "llm": bool(getattr(ag, "usa_llm", False)),
                        "t_s": u["t_s"],
                        "saida_idx": u["saida"],
                        "alvo": ag.alvo,
                        "justificativa": u["justificativa"],
                    })
            decisoes_recentes.sort(key=lambda d: (d["llm"], d["t_s"]), reverse=True)

            # métricas globais (Slide 5)
            tempos_seg = sorted(a.t_seguro for a in m.agentes_total if a.t_seguro is not None)
            n_tot = len(m.agentes_total)
            t_mediano = tempos_seg[len(tempos_seg) // 2] if tempos_seg else None
            t_medio = round(float(np.mean(tempos_seg)), 1) if tempos_seg else None
            # fluxo nos últimos 10 s (pessoas/min)
            fluxo_min = 0.0
            if len(self.serie) >= 2:
                janela = min(20, len(self.serie) - 1)
                ds = self.serie[-1]["Seguros"] - self.serie[-1 - janela]["Seguros"]
                dt_s = max(0.5, self.serie[-1]["t"] - self.serie[-1 - janela]["t"])
                fluxo_min = round(ds * 60.0 / dt_s, 1)

            rhos = [a["rho"] for a in agentes_ativos]
            rho_max = round(float(max(rhos)), 2) if rhos else 0.0
            rho_p90 = round(float(np.percentile(rhos, 90)), 2) if rhos else 0.0

            agentes_llm = [a for a in m.agentes_total if getattr(a, "usa_llm", False)]
            chamadas_llm = int(sum(getattr(a, "chamadas_llm", 0) for a in agentes_llm))
            falhas_llm = int(sum(getattr(a, "falhas_llm", 0) for a in agentes_llm))
            chave_atual = os.environ.get("GEMINI_API_KEY", "").strip()
            mascara_key = (
                f"...{chave_atual[-4:]}"
                if len(chave_atual) >= 4
                else ("configurada" if chave_atual else "")
            )

            return {
                "cenario": self.cenario_codigo,
                "titulo_cenario": CENARIOS_EXPERIMENTAIS[self.cenario_codigo]["titulo"],
                "t": round(m.t, 1),
                "steps": int(m.steps),
                "running": bool(m.running),
                "n_total": n_tot,
                "n_seguros": int(m.n_seguros),
                "n_ativos": len(agentes_ativos),
                "tem_gemini_key": bool(chave_atual),
                "gemini_key_mascara": mascara_key,
                "n_llm_config": int(self.n_llm),
                "n_llm_ativos": len(agentes_llm),
                "chamadas_llm": chamadas_llm,
                "falhas_llm": falhas_llm,
                "ult_erro_llm": getattr(m, "ult_erro_llm", None),
                "llm_model": m.p.llm_model,
                "estados": {
                    "Normal": m._conta(NORMAL),
                    "Investigacao": m._conta(INVESTIGACAO),
                    "Evacuacao": m._conta(EVACUACAO),
                    "Seguros": int(m.n_seguros),
                },
                "portas": {k: int(v) for k, v in m.saidas.items()},
                "risco_medio": round(m._risco_medio(), 3),
                "retidos": int(m._retidos),
                "conflitos": int(m.conflitos),
                "trocas_alvo": int(sum(a.trocas_alvo for a in m.agentes_total)),
                "t_mediano": round(float(t_mediano), 1) if t_mediano is not None else None,
                "t_medio": t_medio,
                "fluxo_ped_min": fluxo_min,
                "rho_max": rho_max,
                "rho_p90": rho_p90,
                "agentes": agentes_ativos,
                "calor_parado": np.round(m.calor_parado, 1).tolist(),
                "por_tipo": por_tipo,
                "serie": self.serie[-360:],
                "decisoes": decisoes_recentes[:25],
            }

    def detalhe_agente(self, agent_id: int) -> dict | None:
        with self.lock:
            m = self.model
            for ag in m.agentes_total:
                if ag.unique_id == agent_id:
                    ctx = ag._contexto_decisao() if ag.pos in m.ocupacao else None
                    return {
                        "id": ag.unique_id,
                        "tipo": ag.tipo,
                        "tipo_nome": ag.T.nome,
                        "cor": ag.T.cor,
                        "papel": ag.T.papel,
                        "llm": bool(getattr(ag, "usa_llm", False)),
                        "estado": NOME_ESTADO[ag.estado],
                        "pos": list(ag.pos),
                        "R": round(float(ag.R), 3),
                        "v_i": round(float(ag.v_i), 2),
                        "rho": round(float(getattr(ag, "rho", 0.0)), 2),
                        "t_choque": round(float(ag.t_choque), 1),
                        "t_investigacao": ag.t_investigacao,
                        "t_evacuacao": ag.t_evacuacao,
                        "t_seguro": ag.t_seguro,
                        "porta_familiar": ag.porta_familiar,
                        "alvo_atual": ag.alvo,
                        "saida_real": ag.saida,
                        "trocas_alvo": ag.trocas_alvo,
                        "passos_bloqueado": ag.passos_bloqueado,
                        "perfil_decisorio": {
                            "aversao_aglomeracao": ag.T.aversao_aglomeracao,
                            "preferencia_familiaridade": ag.T.preferencia_familiaridade,
                            "inercia_decisao": ag.T.inercia_decisao,
                            "cautela_incerteza": ag.T.cautela_incerteza,
                        },
                        "opcoes": ctx["opcoes"] if ctx else [],
                        "memoria": ag.memoria,
                    }
            return None


ESTADO = EstadoSimulacao()


async def pagina_principal(request: Request):
    html_path = Path(__file__).with_name("dashboard.html")
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


async def api_init(request: Request):
    return JSONResponse({"estatico": ESTADO._estatico, "estado": ESTADO.snapshot()})


async def api_step(request: Request):
    body = await request.json()
    passos = int(body.get("passos", 1))
    ate_fim = bool(body.get("ate_fim", False))
    ESTADO.avancar(passos=passos, ate_fim=ate_fim)
    return JSONResponse(ESTADO.snapshot())


async def api_reset(request: Request):
    body = await request.json()
    ESTADO.reiniciar(
        cenario=str(body.get("cenario", ESTADO.cenario_codigo)),
        n=int(body.get("n_ocupantes", ESTADO.n_ocupantes)),
        n_llm=int(body.get("n_llm", ESTADO.n_llm)),
        seed=int(body.get("seed", ESTADO.seed)),
        gemini_api_key=body.get("gemini_api_key"),
    )
    return JSONResponse({"estatico": ESTADO._estatico, "estado": ESTADO.snapshot()})


async def api_agente(request: Request):
    aid = int(request.query_params.get("id", 1))
    det = ESTADO.detalhe_agente(aid)
    return JSONResponse(det or {"erro": "Agente não encontrado"})


def _indices_referencia_llm(agentes_total: list, n_llm_ref: int) -> list[int]:
    por_tipo = {c: [i for i, ag in enumerate(agentes_total) if ag.tipo == c] for c in CODIGOS}
    llm_idx, r = [], 0
    while len(llm_idx) < min(max(0, n_llm_ref), len(agentes_total)):
        c = CODIGOS[r % len(CODIGOS)]
        if por_tipo[c]:
            llm_idx.append(por_tipo[c].pop(0))
        r += 1
        if r > 10 * len(agentes_total) + 12:
            break
    return sorted(llm_idx)


def _executar_cenario_comparacao(
    cod: str, n: int, seed: int, n_llm: int, n_llm_ref: int, reavaliacao_passos: int
) -> dict:
    p = parametros_por_cenario(
        cod,
        n_ocupantes=n,
        n_llm=n_llm,
        semente=seed,
        reavaliacao_passos=reavaliacao_passos,
    )
    m = EvacuacaoModel(p)
    curva = [(0.0, 0)]
    while m.running:
        m.step()
        if m.steps % 4 == 0 or not m.running:
            curva.append((round(m.t, 1), int(m.n_seguros)))
    res = m.resumo()
    idx_ref = _indices_referencia_llm(m.agentes_total, n_llm_ref)
    ag_ref = [m.agentes_total[i] for i in idx_ref]
    ts_ref = [a.t_seguro for a in ag_ref if a.t_seguro is not None]
    t_grupo_ia = round(float(np.mean(ts_ref)), 1) if ts_ref else None
    trocas_grupo_ia = int(sum(a.trocas_alvo for a in ag_ref))
    saidas_grupo_ia = [f"#{a.unique_id}({a.tipo})→{a.saida or a.alvo or '-'}" for a in ag_ref]
    exemplo_just = next(
        (
            f"#{a.unique_id} ({a.tipo}): \"{a.memoria[-1]['justificativa']}\""
            for a in ag_ref
            if a.memoria and a.memoria[-1].get("justificativa") not in ("", "regra de utilidade")
        ),
        None,
    )
    return {
        "codigo": cod,
        "titulo": CENARIOS_EXPERIMENTAIS[cod]["titulo"],
        "usa_llm": n_llm > 0,
        "n_llm": res["agentes_llm"],
        "chamadas_llm": res["chamadas_llm"],
        "ult_erro_llm": m.ult_erro_llm,
        "t_50": res["t_50%_s"],
        "t_90": res["t_90%_s"],
        "t_ultimo": res["t_ultimo_s"],
        "t_grupo_ia": t_grupo_ia,
        "trocas_grupo_ia": trocas_grupo_ia,
        "saidas_grupo_ia": saidas_grupo_ia,
        "exemplo_justificativa": exemplo_just,
        "conflitos": res["conflitos"],
        "trocas_alvo": res["trocas_de_alvo"],
        "saidas": res["saidas"],
        "fluxo_medio_min": round(res["seguros"] * 60.0 / max(1.0, res["t_ultimo_s"] or 1.0), 1),
        "curva": curva,
    }


async def api_comparar_2x2(request: Request):
    """Executa o Plano Experimental 2x2 (C1, C2, C3, C4) Sem LLM, Com LLM ou Ambos."""
    body = await request.json()
    if body.get("gemini_api_key"):
        chave = str(body["gemini_api_key"]).strip()
        if chave:
            os.environ["GEMINI_API_KEY"] = chave
    n = int(body.get("n_ocupantes", ESTADO.n_ocupantes))
    seed = int(body.get("seed", ESTADO.seed))
    modo = str(body.get("modo", "sem_llm")).lower()
    n_llm_ref = max(1, int(body.get("n_llm", ESTADO.n_llm or 3)))
    reavaliacao_passos = max(10, int(body.get("reavaliacao_passos", 60)))
    lista_cenarios = body.get("cenarios") or ["C1", "C2", "C3", "C4"]
    lista_cenarios = [c.upper() for c in lista_cenarios if c.upper() in CENARIOS_EXPERIMENTAIS]

    resultados = {}
    for cod in lista_cenarios:
        sem_llm = None
        com_llm = None
        if modo in ("sem_llm", "ambos"):
            sem_llm = _executar_cenario_comparacao(cod, n, seed, 0, n_llm_ref, reavaliacao_passos)
        if modo in ("com_llm", "ambos"):
            com_llm = _executar_cenario_comparacao(
                cod, n, seed, n_llm_ref, n_llm_ref, reavaliacao_passos
            )
        base = sem_llm or com_llm
        resultados[cod] = {
            **base,
            "sem_llm": sem_llm,
            "com_llm": com_llm,
        }
    return JSONResponse({
        "n_ocupantes": n,
        "seed": seed,
        "modo": modo,
        "n_llm": n_llm_ref,
        "tem_gemini_key": bool(os.environ.get("GEMINI_API_KEY", "").strip()),
        "cenarios": resultados,
    })


app = Starlette(
    routes=[
        Route("/", pagina_principal),
        Route("/api/init", api_init),
        Route("/api/step", api_step, methods=["POST"]),
        Route("/api/reset", api_reset, methods=["POST"]),
        Route("/api/agente", api_agente),
        Route("/api/comparar", api_comparar_2x2, methods=["POST"]),
    ]
)


def main():
    ap = argparse.ArgumentParser(description="Dashboard visual da simulação Vila Germânica")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--porta", type=int, default=8765)
    ap.add_argument("--sem-abrir", action="store_true", help="não abre o navegador automaticamente")
    args = ap.parse_args()

    url = f"http://{args.host}:{args.porta}"
    print(f"Dashboard iniciado em: {url}")
    if not args.sem_abrir:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host=args.host, port=args.porta, log_level="warning")


if __name__ == "__main__":
    main()
