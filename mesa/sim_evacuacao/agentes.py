"""Agentes ocupantes (tipos T01–T12).

* `OcupanteRegras` -> agente de simulação: escolhe a saída-alvo por utilidade
  (mesmos critérios do prompt) e se move pelo motor físico.
* `OcupanteLLM`    -> agente de IA (Mesa-LLM `LLMAgent`): a decisão da saída-alvo é
  produzida pelo LLM com o PROMPT_EVACUACAO_V8 e saída estruturada.

A ÚNICA ação do agente é escolher a saída-alvo. Ritmo, atraso de reação, erro e
percepção são controlados pelo motor (estados Normal -> Investigação -> Evacuação,
EDM, Ordered Logit, P_ij, herding, wall tracking, perda de velocidade por densidade).
"""
from __future__ import annotations

import json
import logging
import math

import numpy as np
from mesa import Agent

from cenario import MOORE
from decisao import PROMPT_EVACUACAO_V8, EscolhaSaida
from tipos import TIPOS

logger = logging.getLogger(__name__)

NORMAL, INVESTIGACAO, EVACUACAO, SEGURO = 0, 1, 2, 3
NOME_ESTADO = {NORMAL: "Normal", INVESTIGACAO: "Investigação",
               EVACUACAO: "Evacuação", SEGURO: "Seguro"}


def _sig(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-50.0, min(50.0, z))))


class _OcupanteMixin:
    # ------------------------------------------------------------------ init
    def _init_ocupante(self, pos, tipo: str):
        m, p = self.model, self.model.p
        rng = m.rng
        self.tipo = tipo
        self.T = TIPOS[tipo]
        self.pos = tuple(pos)
        self.estado = NORMAL
        self.R = 0.0
        self.alpha_i = float(np.clip(rng.normal(p.alpha, p.alpha_dp), 0.05, 1.0))
        self.v_i = float(np.clip(rng.normal(p.v_escuro_media, p.v_escuro_dp), 0.30, 0.60)
                         * self.T.v_fator)
        self.massa = float(max(25.0 if tipo == "T04" else 45.0,
                               rng.normal(p.massa_media, p.massa_dp)
                               * (0.5 if tipo == "T04" else 1.0)))
        self.t_choque = float(rng.uniform(*p.t_choque)) + self.T.atraso_reacao
        self.vies_esq = bool(rng.random() < p.p_vies_esquerdo)
        self.r_ac = max(1, int(round(p.r_acustico * self.T.alcance_acustico / p.celula)))
        self.porta_familiar = str(rng.choice(list(m.cen.portas)))
        self.alvo = None                       # saída-alvo atual (id da porta)
        self.memoria: list[dict] = []          # últimas decisões (máx. 3)
        self._ult_escolha = -10**9
        ang = rng.uniform(0, 2 * math.pi)
        self.h = (math.cos(ang), math.sin(ang))
        self.vel = (0.0, 0.0)
        self.credito = 0.0
        self.rho = 0.0
        self._apagao_sentido = False
        self.t_investigacao = self.t_evacuacao = self.t_seguro = None
        self.saida = None
        self.passos_bloqueado = 0
        self.trocas_alvo = 0
        self.decisoes = 0

    # --------------------------------------------------- EDM + Ordered Logit
    def atualizar_estado(self):
        m, p = self.model, self.model.p
        x, y = self.pos
        n = m.soma("pres", x, y, self.r_ac) - 1
        n_ev = m.soma("evac", x, y, self.r_ac) - (1 if self.estado == EVACUACAO else 0)
        f_evac = (n_ev / n) if n > 0 else 0.0

        if not self._apagao_sentido:                      # pista súbita  α·δ(t)
            self._apagao_sentido = True
            self.R += self.alpha_i
        dR = (p.beta * (1 - math.exp(-p.lam * m.t))       # urgência temporal
              + p.gamma_social * f_evac                   # influência social acústica
              - p.kappa * self.R)                         # acomodação
        self.R = float(np.clip(self.R + dR * p.dt, 0.0, 1.0))

        p_normal = _sig((p.R_I - self.R) / p.sigma_logit)
        p_ate_inv = _sig((p.R_E - self.R) / p.sigma_logit)
        u = m.rng.random()
        novo = NORMAL if u < p_normal else (INVESTIGACAO if u < p_ate_inv else EVACUACAO)
        if novo > self.estado:
            self.estado = novo
            if self.t_investigacao is None:
                self.t_investigacao = m.t
            if novo == EVACUACAO:
                self.t_evacuacao = m.t

    # ------------------------------------------------------------- velocidade
    def velocidade(self):
        p, m = self.model.p, self.model
        x, y = self.pos
        rho = m.soma("pres", x, y, 2) / (5 * p.celula) ** 2     # ped/m2
        v = self.v_i * (1.0 if self.estado == EVACUACAO else
                        p.fator_v_investigacao if self.estado == INVESTIGACAO
                        else p.fator_v_normal)
        if rho < p.rho_crit:
            f = 1.0
        elif rho <= p.rho_jam:
            f = 1.0 - math.exp(-p.gamma_v * (1.0 / rho - 1.0 / p.rho_jam))
        else:
            f = 0.0
        self.rho = rho
        return v * max(0.0, f)

    # ------------------------------------------------- escolha da saída-alvo
    def _opcoes(self):
        """Informação fornecida pelo motor (já com limites de percepção e erro)."""
        m, p = self.model, self.model.p
        x, y = self.pos
        rng = m.rng
        opcoes = []
        for i, pid in enumerate(m.cen.portas):
            S = m.cen.campos_S[pid][x, y]
            visivel = (self.T.conhece_todas or pid == self.porta_familiar
                       or m.dist_porta_id[pid][x, y] <= self.r_ac)
            dist = None
            if visivel and np.isfinite(S):
                dist = S * p.celula
                dist *= max(0.2, 1.0 + rng.normal(0, self.T.erro_percepcao))  # erro do motor
                dist = round(float(dist), 1)
            n_alvo = int(m.soma(f"alvo_{pid}", x, y, self.r_ac)
                         - (1 if self.alvo == pid else 0))
            opcoes.append({
                "indice": i, "nome": m.cen.nomes[pid], "distancia_m": dist,
                "pessoas_locais_mesmo_alvo": max(0, n_alvo),
                "familiar": bool(pid == self.porta_familiar or self.T.conhece_todas),
            })
        return opcoes

    def _contexto_decisao(self):
        m = self.model
        ids = list(m.cen.portas)
        return {
            "tempo_s": round(m.t, 1),
            "perfil_agente": {"tipo": self.tipo, "descricao": self.T.nome,
                              "papel_social": self.T.papel,
                              "estado": NOME_ESTADO[self.estado]},
            "perfil_decisorio": {
                "aversao_aglomeracao": self.T.aversao_aglomeracao,
                "preferencia_familiaridade": self.T.preferencia_familiaridade,
                "inercia_decisao": self.T.inercia_decisao,
                "cautela_incerteza": self.T.cautela_incerteza,
            },
            "alvo_atual": ids.index(self.alvo) if self.alvo else None,
            "saida_familiar": ids.index(self.porta_familiar),
            "opcoes": self._opcoes(),
            "memoria": self.memoria[-3:],
        }

    def escolher_saida(self):
        """Executa a ÚNICA ação do agente: define `self.alvo`."""
        m = self.model
        ctx = self._contexto_decisao()
        escolha, just = None, ""
        if getattr(self, "usa_llm", False):
            escolha, just = self._escolher_llm(ctx)
        if escolha is None:
            escolha, just = self._escolher_regras(ctx)
        ids = list(m.cen.portas)
        novo = ids[escolha]
        if self.alvo is not None and novo != self.alvo:
            self.trocas_alvo += 1
        self.alvo = novo
        self._ult_escolha = m.steps
        self.decisoes += 1
        self.memoria.append({"t_s": round(m.t, 1), "saida": escolha, "justificativa": just})
        self.memoria = self.memoria[-3:]

    def _escolher_regras(self, ctx):
        """Utilidade com os mesmos critérios do prompt (política de referência)."""
        pf = ctx["perfil_decisorio"]
        ops = ctx["opcoes"]
        conhecidas = [o["distancia_m"] for o in ops if o["distancia_m"] is not None]
        dmax = max(conhecidas) if conhecidas else 1.0
        dmed = float(np.mean(conhecidas)) if conhecidas else 1.0
        cong = max(1, max(o["pessoas_locais_mesmo_alvo"] for o in ops))
        u = []
        for o in ops:
            d = o["distancia_m"]
            val = -(d if d is not None else dmed) / max(dmax, 1e-6)
            val -= pf["aversao_aglomeracao"] * o["pessoas_locais_mesmo_alvo"] / cong * 0.6
            val += pf["preferencia_familiaridade"] * 0.5 * (o["indice"] == ctx["saida_familiar"])
            val += pf["inercia_decisao"] * 0.4 * (o["indice"] == ctx["alvo_atual"])
            val -= pf["cautela_incerteza"] * 0.5 * (d is None)
            u.append(val)
        u = np.array(u) / 0.15                          # softmax: decisão não determinística
        pr = np.exp(u - u.max()); pr /= pr.sum()
        k = int(self.model.rng.choice(len(ops), p=pr))
        return k, "regra de utilidade"

    def _escolher_llm(self, ctx):  # sobrescrito em OcupanteLLM
        return None, ""

    # ------------------------------------------------------------ movimento
    def decidir(self):
        """Retorna (célula-alvo, (dx,dy)) ou None. O modelo valida e executa."""
        m, p = self.model, self.model.p
        if (self.estado == EVACUACAO and (
                self.alvo is None or m.steps - self._ult_escolha >= p.reavaliacao_passos)):
            self.escolher_saida()
        if m.t < self.t_choque:                          # fase 1: choque/desorientação
            self.vel = (0.0, 0.0)
            return None
        self.credito = min(self.credito + self.velocidade() * p.dt / p.celula, 1.5)
        if self.credito < 1.0:
            return None
        return self._passo()

    def _candidatos(self):
        m = self.model
        x, y = self.pos
        bloq = m.cen.bloqueado
        w, h = bloq.shape
        for dx, dy in MOORE:
            nx, ny = x + dx, y + dy
            if not (0 <= nx < w and 0 <= ny < h) or bloq[nx, ny]:
                continue
            if dx and dy and (bloq[x + dx, y] or bloq[x, y + dy]):
                continue
            yield (nx, ny), (dx, dy)

    def _passo(self):
        m, p = self.model, self.model.p
        x, y = self.pos
        cands = list(self._candidatos())
        if not cands:
            return None
        # força de orientação ao alvo: depende da fase e do conhecimento da saída
        if self.estado == EVACUACAO and self.alvo is not None:
            S = m.cen.campos_S[self.alvo]
            if self.T.conhece_todas:
                guia = 1.0
            elif self.alvo == self.porta_familiar:
                guia = 0.85
            else:
                guia = 0.5
        elif self.estado == INVESTIGACAO:
            S, guia = m.cen.campos_S[self.porta_familiar], 0.12
        else:
            S, guia = m.cen.campos_S[self.porta_familiar], 0.0
        if m.dist_porta[x, y] <= p.raio_alcance_porta and self.estado >= INVESTIGACAO:
            S, guia = m.cen.campos_S["todas"], 1.0       # abertura ao alcance do tato
        vx = m.soma("vx", x, y, self.r_ac) - self.vel[0]
        vy = m.soma("vy", x, y, self.r_ac) - self.vel[1]
        nv = math.hypot(vx, vy)
        herd = (vx / nv, vy / nv) if nv > 1e-9 else (0.0, 0.0)
        omega = p.omega0 + (p.omega0_escuro - p.omega0) * min(1.0, self.R + 0.5)
        omega *= min(1.0, self.T.alcance_acustico + 0.2)  # audição reduz o herding
        s_here = S[x, y]
        pesos = []
        for (c, (dx, dy)) in cands:
            nrm = math.hypot(dx, dy)
            ux, uy = dx / nrm, dy / nrm
            dS = (S[c] - s_here) if np.isfinite(S[c]) and np.isfinite(s_here) else 0.0
            O = math.exp(-m.cen.d_parede[c] / (p.d_braco / p.celula))
            D = omega * (ux * herd[0] + uy * herd[1])
            cruz = self.h[0] * uy - self.h[1] * ux
            L = cruz if self.vies_esq else -cruz
            inercia = ux * self.h[0] + uy * self.h[1]
            z = (-p.k_S * guia * dS + p.k_O * O * (1 if self.estado > NORMAL else 0.5)
                 + p.k_D * D + p.k_L * L + p.k_I * inercia)
            w_ = math.exp(max(-30.0, min(30.0, z)))
            if c in m.ocupacao:
                w_ *= p.peso_ocupada
            pesos.append(w_)
        pesos = np.array(pesos)
        return cands[int(m.rng.choice(len(cands), p=pesos / pesos.sum()))]


class OcupanteRegras(_OcupanteMixin, Agent):
    """Agente de simulação clássico (sem LLM)."""
    usa_llm = False

    def __init__(self, model, pos, tipo="T01"):
        super().__init__(model)
        self._init_ocupante(pos, tipo)


try:  # Mesa-LLM
    from mesa_llm.llm_agent import LLMAgent
    from mesa_llm.memory.st_memory import ShortTermMemory
    from mesa_llm.reasoning.react import ReActReasoning
    MESA_LLM_OK = True
except Exception as exc:  # pragma: no cover
    logger.warning("mesa-llm indisponível: %s", exc)
    MESA_LLM_OK = False

if MESA_LLM_OK:

    class OcupanteLLM(_OcupanteMixin, LLMAgent):
        """Agente de IA: o LLM escolhe a saída-alvo (saída estruturada `EscolhaSaida`)."""
        usa_llm = True

        def __init__(self, model, pos, tipo="T01"):
            p = model.p
            LLMAgent.__init__(
                self, model=model, reasoning=ReActReasoning, llm_model=p.llm_model,
                system_prompt=PROMPT_EVACUACAO_V8, vision=0,
                internal_state=[], step_prompt=None, api_base=p.llm_api_base)
            self.memory = ShortTermMemory(agent=self, n=3, display=False)
            self._init_ocupante(pos, tipo)
            self.falhas_llm = 0
            self.chamadas_llm = 0
            self.respostas_invalidas = 0
            self.log_llm: list[dict] = []

        def _escolher_llm(self, ctx):
            p = self.model.p
            if self.falhas_llm >= p.llm_max_falhas:
                return None, ""
            try:
                resp = self.llm.generate(
                    prompt=[json.dumps(ctx, ensure_ascii=False)],
                    response_format=EscolhaSaida)
                bruto = resp.choices[0].message.content
                esc = EscolhaSaida.model_validate_json(bruto)
                if not any(o["indice"] == esc.saida for o in ctx["opcoes"]):
                    raise ValueError(f"índice fora de opcoes: {esc.saida}")
            except ValueError as exc:       # JSON/índice inválido
                self.respostas_invalidas += 1
                self.falhas_llm += 1
                logger.warning("Resposta inválida (agente %s): %s", self.unique_id, exc)
                return None, ""
            except Exception as exc:        # rede, cota...
                self.falhas_llm += 1
                logger.warning("LLM falhou (agente %s): %s", self.unique_id, exc)
                return None, ""
            self.falhas_llm = 0
            self.chamadas_llm += 1
            self.memory.add_to_memory(type="decision", content={
                "saida": esc.saida, "justificativa": esc.justificativa})
            self.log_llm.append({"t_s": self.model.t, "tipo": self.tipo, "contexto": ctx,
                                 "saida": esc.saida, "justificativa": esc.justificativa})
            return esc.saida, esc.justificativa
