"""Modelo Mesa: evacuação do Parque Vila Germânica em blackout noturno.

Ciclo de cada passo (model.step, dt = 0.5 s):
  1. campos sociais (imagens integrais de presença / evacuação / velocidade)
  2. cada agente atualiza R_i(t) (EDM) e seu estado (Ordered Logit)
  3. cada agente decide uma intenção (regras P_ij  ou  LLM via Mesa-LLM)
  4. o MODELO resolve conflitos (pressão), aplica gargalo de porta e move
  5. coleta de dados
Atualização: x(t+1) = F(x(t), a(1,t), ..., a(n,t), ξ(t))   (Aula 14)
"""
from __future__ import annotations

import logging
import math

import numpy as np
from mesa import Model
from mesa.datacollection import DataCollector

from agentes import (EVACUACAO, INVESTIGACAO, MESA_LLM_OK, NORMAL, SEGURO,
                     OcupanteRegras)
from cenario import construir_cenario
from config import Parametros
from tipos import CODIGOS, TIPOS, sortear_composicao

if MESA_LLM_OK:
    from agentes import OcupanteLLM

logger = logging.getLogger(__name__)


class EvacuacaoModel(Model):
    def __init__(self, params: Parametros | None = None, **kwargs):
        p = params or Parametros(**kwargs)
        super().__init__(rng=p.semente)
        self.p = p
        self.cen = construir_cenario(p.celula, getattr(p, "portas_bloqueadas", ()))
        self.t = 0.0
        self.ocupacao: dict[tuple, object] = {}
        self.fichas = {k: 1.0 for k in self.cen.portas}
        self.saidas = {k: 0 for k in self.cen.portas}
        self.conflitos = 0
        self.calor = np.zeros((self.cen.largura, self.cen.altura))      # ocupação acumulada
        self.calor_parado = np.zeros_like(self.calor)                   # agentes retidos
        self.historico_seguros: list[tuple[float, int]] = []
        self.agentes_total = []
        self.ult_erro_llm: str | None = None
        self.abortar_llm: bool = False

        # distância euclidiana (células) à porta mais próxima (abertura ao alcance do tato)
        xs, ys = np.meshgrid(np.arange(self.cen.largura), np.arange(self.cen.altura),
                             indexing="ij")
        self.dist_porta_id = {}
        for pid, cells in self.cen.portas.items():
            dd = np.full(xs.shape, np.inf)
            for (cx, cy) in cells:
                dd = np.minimum(dd, np.hypot(xs - cx, ys - cy))
            self.dist_porta_id[pid] = dd
        self.dist_porta = np.minimum.reduce(list(self.dist_porta_id.values()))

        self._popular()
        self._campos_sociais()

        self.datacollector = DataCollector(
            model_reporters={
                "t": lambda m: m.t,
                "Normal": lambda m: m._conta(NORMAL),
                "Investigacao": lambda m: m._conta(INVESTIGACAO),
                "Evacuacao": lambda m: m._conta(EVACUACAO),
                "Seguros": lambda m: m.n_seguros,
                "RiscoMedio": lambda m: m._risco_medio(),
                "Retidos": lambda m: m._retidos,
                "Conflitos": lambda m: m.conflitos,
                **{f"Porta_{k}": (lambda m, k=k: m.saidas[k]) for k in self.cen.portas},
            })
        self._retidos = 0
        self.datacollector.collect(self)
        self.running = True

    # ------------------------------------------------------------------ setup
    @property
    def n_seguros(self):
        return sum(self.saidas.values())

    def _popular(self):
        p = self.p
        livres = [(int(x), int(y)) for x, y in zip(*np.nonzero(
            self.cen.interior & ~self.cen.bloqueado))]
        idx = self.rng.choice(len(livres), size=p.n_ocupantes, replace=False)
        tipos = sortear_composicao(p.n_ocupantes, self.rng)
        # agentes de IA: round-robin entre T01..T12 para que todos os tipos apareçam
        por_tipo = {c: [i for i, t in enumerate(tipos) if t == c] for c in CODIGOS}
        llm_idx, r = set(), 0
        while len(llm_idx) < min(p.n_llm, len(tipos)):
            c = CODIGOS[r % len(CODIGOS)]
            if por_tipo[c]:
                llm_idx.add(por_tipo[c].pop(0))
            r += 1
            if r > 10 * len(tipos) + 12:
                break
        llm_ok = MESA_LLM_OK and p.n_llm > 0
        for i, k in enumerate(idx):
            pos = livres[int(k)]
            func = tipos[i]
            ag = None
            if llm_ok and i in llm_idx:
                try:
                    ag = OcupanteLLM(self, pos, func)
                except Exception as exc:
                    self.ult_erro_llm = f"Não foi possível iniciar agente LLM: {exc}"
                    logger.error("Não foi possível criar agente LLM (%s). Usando regras. "
                                 "Defina a chave de API em .env ou no Dashboard.", exc)
                    llm_ok = False
            if ag is None:
                ag = OcupanteRegras(self, pos, func)
            self.ocupacao[pos] = ag
            self.agentes_total.append(ag)

    # -------------------------------------------------------- campos sociais
    def _campos_sociais(self):
        w, h = self.cen.largura, self.cen.altura
        arrs = {k: np.zeros((w, h)) for k in ("pres", "evac", "vx", "vy")}
        for pid in self.cen.portas:
            arrs[f"alvo_{pid}"] = np.zeros((w, h))
        for (x, y), a in self.ocupacao.items():
            arrs["pres"][x, y] = 1
            if a.alvo is not None:
                arrs[f"alvo_{a.alvo}"][x, y] = 1
            if a.estado == EVACUACAO:
                arrs["evac"][x, y] = 1
            arrs["vx"][x, y], arrs["vy"][x, y] = a.vel
        self._ii = {}
        for k, A in arrs.items():
            ii = np.zeros((w + 1, h + 1))
            ii[1:, 1:] = A.cumsum(0).cumsum(1)
            self._ii[k] = ii

    def soma(self, nome, x, y, r):
        ii = self._ii[nome]
        w, h = self.cen.largura, self.cen.altura
        x0, x1 = max(0, x - r), min(w, x + r + 1)
        y0, y1 = max(0, y - r), min(h, y + r + 1)
        return ii[x1, y1] - ii[x0, y1] - ii[x1, y0] + ii[x0, y0]

    # ------------------------------------------------------------ métricas
    def _conta(self, estado):
        return sum(1 for a in self.ocupacao.values() if a.estado == estado)

    def _risco_medio(self):
        v = [a.R for a in self.ocupacao.values()]
        return float(np.mean(v)) if v else 0.0

    # ------------------------------------------------------------------ passo
    def step(self):
        p, cen = self.p, self.cen
        for k, cells in cen.portas.items():                  # gargalo de porta (token bucket)
            self.fichas[k] = min(2.0, self.fichas[k]
                                 + p.fluxo_porta * cen.largura_porta_m[k] * p.dt)
        self._campos_sociais()

        agentes = list(self.ocupacao.values())
        self.rng.shuffle(agentes)
        for a in agentes:
            a.atualizar_estado()

        intencoes = []
        for a in agentes:
            r = a.decidir()
            if r is None:
                a.vel = (0.0, 0.0)
            else:
                intencoes.append((a, r[0], r[1]))

        # ---- resolução de conflitos: várias intenções na mesma célula
        grupos: dict[tuple, list] = {}
        for it in intencoes:
            grupos.setdefault(it[1], []).append(it)
        vencedores = []
        for alvo, grp in grupos.items():
            if len(grp) == 1:
                vencedores.append(grp[0])
                continue
            pres = []
            for (a, _, _) in grp:
                x, y = a.pos
                comp = self.soma("pres", x, y, 1) - 1
                pres.append(a.massa * a.v_i + p.k_compressao * comp)
            pmax = max(pres)
            empate = [i for i, v in enumerate(pres) if pmax - v <= p.delta_P]
            w = grp[int(self.rng.choice(empate))]
            vencedores.append(w)
            self.conflitos += 1
            for it in grp:
                if it is not w:
                    it[0].vel = (0.0, 0.0)
                    it[0].credito = 0.0
                    it[0].passos_bloqueado += 1

        # ---- execução: quem está mais perto da saída move primeiro (filas fluem)
        S = cen.campos_S["todas"]
        vencedores.sort(key=lambda it: S[it[0].pos])
        retidos = 0
        for (a, alvo, d) in vencedores:
            pid = cen.mapa_porta.get(alvo)
            ocupada = alvo in self.ocupacao and self.ocupacao[alvo] is not a
            sem_ficha = pid is not None and self.fichas[pid] < 1.0
            if ocupada or sem_ficha:
                a.vel = (0.0, 0.0)
                a.credito = 0.0
                a.passos_bloqueado += 1
                retidos += 1
                continue
            del self.ocupacao[a.pos]
            a.credito -= math.hypot(*d)
            a.vel = (float(d[0]), float(d[1]))
            n = math.hypot(*d)
            a.h = (d[0] / n, d[1] / n)
            if pid is not None:                              # cruzou a porta -> seguro
                self.fichas[pid] -= 1.0
                self.saidas[pid] += 1
                a.estado, a.t_seguro, a.saida, a.pos = SEGURO, self.t + p.dt, pid, alvo
                a.remove()
            else:
                a.pos = alvo
                self.ocupacao[alvo] = a
        self._retidos = retidos

        for (x, y), a in self.ocupacao.items():
            self.calor[x, y] += 1
            if a.estado == EVACUACAO and a.vel == (0.0, 0.0):
                self.calor_parado[x, y] += 1

        self.t += p.dt
        self.historico_seguros.append((self.t, self.n_seguros))
        self.datacollector.collect(self)
        if not self.ocupacao or self.t >= p.t_max:
            self.running = False

    # -------------------------------------------------------------- resumo
    def resumo(self) -> dict:
        ag = self.agentes_total
        seg = sorted(a.t_seguro for a in ag if a.t_seguro is not None)

        def pct(q):
            return seg[min(len(seg) - 1, int(math.ceil(q * len(ag))) - 1)] \
                if len(seg) >= q * len(ag) and seg else None
        t_ev = [a.t_evacuacao for a in ag if a.t_evacuacao is not None]
        llm = [a for a in ag if getattr(a, "usa_llm", False)]
        por_tipo = {}
        for c in CODIGOS:
            grp = [a for a in ag if a.tipo == c]
            ts = [a.t_seguro for a in grp if a.t_seguro is not None]
            por_tipo[c] = {"nome": TIPOS[c].nome, "n": len(grp),
                           "t_seguro_medio_s": round(float(np.mean(ts)), 1) if ts else None,
                           "t_seguro_max_s": max(ts) if ts else None}
        return {
            "ocupantes": len(ag), "seguros": len(seg),
            "t_50%_s": pct(0.5), "t_90%_s": pct(0.9), "t_ultimo_s": seg[-1] if seg else None,
            "t_inicio_evacuacao_medio_s": float(np.mean(t_ev)) if t_ev else None,
            "saidas": dict(self.saidas), "conflitos": self.conflitos,
            "trocas_de_alvo": int(sum(a.trocas_alvo for a in ag)),
            "agentes_llm": len(llm),
            "chamadas_llm": int(sum(a.chamadas_llm for a in llm)),
            "respostas_llm_invalidas": int(sum(a.respostas_invalidas for a in llm)),
            "por_tipo": por_tipo,
        }
