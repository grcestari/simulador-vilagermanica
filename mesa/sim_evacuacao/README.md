# Simulação Agêntica de Evacuação em Blackout — Parque Vila Germânica (`Mesa` + `Mesa-LLM`)

Este documento explica **como o projeto foi construído** (fundamentação teórica, arquitetura de código, formalismo matemático e integração com IA via `Mesa-LLM`) e **como executá-lo** (via Dashboard Visual no navegador ou via linha de comando).

---

## 1. Como o Projeto Foi Feito

O simulador integra os três pilares definidos no esquema da disciplina:
1. **Plano / Formalismo do Experimento** (*Formalização e Modelagem Físico-Computacional de Evacuação de Emergência em Blackout Noturno: Parque Vila Germânica*).
2. **Aula 14 — Simulação Agêntica com `Mesa-LLM`** (ciclo *Observação $\to$ Decisão $\to$ Atualização*, distinção entre agente de simulação e agente de IA, memória curta, autonomia delimitada e Plano Experimental $2 \times 2$).
3. **Artigo Base do Framework `Mesa`** (*Mesa: An Agent-Based Modeling Framework* — modularidade entre `Model`, `Agent`, `DataCollector` e visualização web).

Além disso, implementa a **Tipologia de 12 Atores (`T01` a `T12`)** e o prompt estruturado **`PROMPT_EVACUACAO_V8`**.

---

### 1.1. Estrutura de Arquivos do Projeto

| Arquivo | Função no Sistema |
|---|---|
| `config.py` | Parâmetros físicos, cinemáticos e comportamentais calibrados ("Blackout Noturno") e definição dos 4 cenários do **Plano Experimental $2 \times 2$ (`C1`, `C2`, `C3`, `C4`)**. |
| `cenario.py` | Leitura de `../PVG_shapefile-20261123`, rasterização das geometrias do salão em malha de células ($0{,}4\,\text{m} \times 0{,}4\,\text{m}$), posicionamento das nove saídas perimetrais e cálculo dos campos de navegação. |
| `../PVG_shapefile-20261123/` | Shapefiles de geometrias e textos usados pelo cenário do Mesa. A pasta precisa permanecer ao lado de `sim_evacuacao/`. |
| `tipos.py` | Definição dos **12 tipos de atores (`T01`–`T12`)**, suas cores oficiais, proporções populacionais, parâmetros físicos controlados pelo motor e parâmetros do perfil decisório ($[0, 1]$). |
| `decisao.py` | Prompt **`PROMPT_EVACUACAO_V8`** e schema Pydantic **`EscolhaSaida(saida, justificativa)`** que valida a resposta estruturada do LLM. |
| `agentes.py` | Implementação do corpo físico/comportamental (`_OcupanteMixin`), do agente baseado em regras (`OcupanteRegras`) e do agente de IA (`OcupanteLLM`, subclasse de `mesa_llm.LLMAgent`). |
| `modelo.py` | Classe `EvacuacaoModel` (`mesa.Model`): gerencia o ciclo de tempo ($\Delta t = 0{,}5\,\text{s}$), imagens integrais para consultas espaciais $O(1)$, resolução de conflitos por pressão física, gargalo nas portas e coleta de indicadores (`DataCollector`). |
| `run.py` | Executor em lote via terminal (CLI): roda a simulação até o fim e exporta gráficos (`.png`), tabelas (`.csv`) e métricas (`.json`) na pasta `resultados/`. |
| `dashboard.py` | Servidor web interativo (`Starlette` + `Uvicorn`) que expõe a simulação passo a passo em tempo real e executa a comparação automática dos cenários `C1`–`C4`. |
| `dashboard.html` | Interface visual interativa (HTML5 Canvas + gráficos em tempo real + inspetor de agentes + feed de decisões do `PROMPT_EVACUACAO_V8`). |

---

### 1.2. Espaço Físico e Campos de Navegação (`cenario.py`)

- **Planta de origem**: o cenário lê `pvg_geometrias.shp` e `pvg_textos.shp` da pasta `PVG_shapefile-20261123`, no nível acima de `sim_evacuacao/`. As linhas arquitetônicas do recorte do salão principal são rasterizadas como paredes e obstáculos; os nove rótulos perimetrais `SAÍDA DE EMERGÊNCIA` geram as saídas `S1` a `S9`. A marcação interna não é tratada como uma porta.
- **Malha Discreta (Multi-grid corporal)**: grade de $52 \times 122$ células, na mesma orientação vertical da planta, com borda de parede e área interna nominal de $50 \times 120$ células ($960\,\text{m}^2$) a $0{,}4\,\text{m} \times 0{,}4\,\text{m}$. A área interna aproxima os $964\,\text{m}^2$ indicados na planta.
- **Limite de escala**: o shapefile usa coordenadas cartesianas locais, sem calibração geográfica. O formato do salão e os obstáculos vêm da planta; a conversão para metros continua seguindo a célula de $0{,}4\,\text{m}$ já adotada pelo modelo.
- **Portas de Evacuação**:
  - `S1` a `S9`: saídas de emergência perimetrais marcadas na planta ($1{,}6\,\text{m}$ de largura no grid); `S2` continua bloqueada nos cenários `C3` e `C4`.
- **Campo de Piso Estático ($S_{ij}$)**: distância geodésica em células até cada porta (`S1` a `S9` e `todas`), calculada com algoritmo de Dijkstra desviando das paredes e dos obstáculos rasterizados da planta.
- **Campo de Obstáculos ($O_{ij}$)**: distância à parede/obstáculo mais próximo, usada para guiar o tateamento no escuro (*wall tracking* / tigmotaxia).

---

### 1.3. Tipologia dos 12 Atores (`tipos.py`)

Cada ocupante pertence a um dos 12 tipos da legenda, combinando **parâmetros físicos controlados pelo motor** e **parâmetros explícitos de perfil decisório** (de $0$ a $1$):

| Código | Descrição | Papel Social | Cor | Fator Vel. | Atraso Reação (s) | Erro Percepção | Aversão Aglom. | Pref. Famil. | Inércia Decisão | Cautela Incerteza |
|---|---|---|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `T01` | Adulto sóbrio | visitante | `#2f6fe4` | 1.00 | +0.0 | 0.03 | 0.50 | 0.40 | 0.40 | 0.40 |
| `T02` | Álcool: comprometimento moderado | visitante | `#f07b1d` | 0.90 | +3.0 | 0.10 | 0.35 | 0.50 | 0.60 | 0.25 |
| `T03` | Álcool: comprometimento acentuado | visitante | `#b82025` | 0.75 | +8.0 | 0.25 | 0.20 | 0.60 | 0.75 | 0.15 |
| `T04` | Criança | visitante | `#e6ac00` | 0.75 | +2.0 | 0.12 | 0.60 | 0.80 | 0.50 | 0.70 |
| `T05` | Pessoa idosa autônoma | visitante | `#7a47e0` | 0.80 | +3.0 | 0.06 | 0.60 | 0.70 | 0.60 | 0.60 |
| `T06` | Mobilidade reduzida | visitante | `#8a5a14` | 0.60 | +3.0 | 0.05 | 0.70 | 0.60 | 0.60 | 0.60 |
| `T07` | Pessoa em cadeira de rodas | visitante | `#1590b0` | 0.65 | +3.0 | 0.05 | 0.75 | 0.60 | 0.60 | 0.60 |
| `T08` | Pessoa com baixa visão | visitante | `#e0307e` | 0.80 | +3.0 | 0.12 | 0.50 | 0.80 | 0.60 | 0.70 |
| `T09` | Pessoa com deficiência auditiva | visitante | `#1fb5a0` | 1.00 | +4.0 | 0.06 | 0.50 | 0.50 | 0.50 | 0.50 |
| `T10` | Necessidade de apoio à orientação | visitante | `#667488` | 0.90 | +4.0 | 0.20 | 0.50 | 0.80 | 0.70 | 0.80 |
| `T11` | Acompanhante / cuidador | cuidador | `#5a8a1e` | 0.95 | +1.0 | 0.04 | 0.50 | 0.50 | 0.50 | 0.60 |
| `T12` | Funcionário / brigadista | brigadista | `#1d2b3d` | 1.00 | +0.0 | 0.01 | 0.60 | 0.30 | 0.40 | 0.30 |

---

### 1.4. Ciclo de Simulação Agêntica e `Mesa-LLM` (`agentes.py` e `decisao.py`)

Seguindo a formulação da **Aula 14**:
1. **Observação**: $o(i,t) = O_i(x(t))$
2. **Decisão**: $a(i,t) \sim \pi_i(\cdot \mid o(i,t), m(i,t), g_i)$
3. **Atualização**: $x(t+1) = F(x(t), a(1,t), \dots, a(n,t), \xi(t))$

#### Como o Agente Decide a Saída-Alvo (`PROMPT_EVACUACAO_V8`)
De acordo com o prompt especificado, **a única ação decisória do agente é escolher o índice da saída-alvo** (`saida: int` e `justificativa: str` com até 240 caracteres):
- O motor constrói o pacote JSON de observação contendo:
  - `perfil_agente`: tipo (`T01`–`T12`), descrição, papel social e estado atual.
  - `perfil_decisorio`: `aversao_aglomeracao`, `preferencia_familiaridade`, `inercia_decisao` e `cautela_incerteza`.
  - `alvo_atual` e `saida_familiar`.
  - `opcoes`: lista das portas disponíveis com `indice`, `nome`, `distancia_m` (afetada pelo erro perceptual do tipo ou `null` quando a saída está fora do alcance/conhecimento do agente), `pessoas_locais_mesmo_alvo` (vizinhos no raio perceptual que buscam aquela mesma saída) e `familiar`.
  - `memoria`: até 3 decisões anteriores (`t_s`, `saida`, `justificativa`) armazenadas em `ShortTermMemory` do `Mesa-LLM`.
- **Agente de IA (`OcupanteLLM`)**: herda de `mesa_llm.llm_agent.LLMAgent`, envia o contexto ao modelo de linguagem com `PROMPT_EVACUACAO_V8` como `system_prompt` e valida o retorno via Pydantic (`EscolhaSaida`). Se a API falhar ou não houver chave configurada, faz fallback transparente para a política de regras.
- **Agente de Regras (`OcupanteRegras`)**: avalia exatamente os mesmos 5 critérios do prompt (distância conhecida, aversão à aglomeração local, familiaridade, inércia do alvo atual e penalidade de incerteza para `distancia_m == null`) via função de utilidade com seleção *softmax*.

---

### 1.5. Dinâmica Física e Comportamental Controlada pelo Motor (`agentes.py` e `modelo.py`)

Enquanto a escolha da saída-alvo é delegada à política decisória (LLM ou utilidade), o **motor físico do Mesa** governa:
1. **Acúmulo de Risco Percebido (EDM)**:
   $$\frac{dR_i(t)}{dt} = \alpha_i \delta(t) + \beta_T(1 - e^{-\lambda t}) + \gamma_S \frac{1}{|\mathcal{N}_i^{\text{acoust}}|}\sum_{j} \mathbb{I}(S_j = \text{Evacuação}) - \kappa_D R_i(t)$$
2. **Transição de Estados (Ordered Logit)**:
   Com base em $R_i(t)$ e nos limiares $R_I = 0{,}30$ e $R_E = 0{,}60$, o ocupante avança pelos estados `Normal` $\to$ `Investigação` $\to$ `Evacuação` $\to$ `Seguro`.
3. **Escolha de Célula na Vizinhança de Moore ($P_{i \to k}$)**:
   Combina a redução da distância geodésica $S_{ij}$ até a **saída-alvo escolhida**, a atração tátil pelas paredes $O_k = \exp(-d(k,\text{parede})/d_{\text{braço}})$ (*wall tracking*), o alinhamento acústico com os passos dos vizinhos $D_k(t)$ (*acoustic herding*), o viés motor lateral esquerdo ($87{,}5\%$) $L_{i,k}$ e a inércia direcional.
4. **Leis de Degradação da Velocidade por Densidade**:
   - Para $\rho_i < 0{,}5\,\text{ped/m}^2$: velocidade livre no escuro ($v_i$).
   - Para $0{,}5 \le \rho_i \le 5{,}5\,\text{ped/m}^2$: decaimento exponencial $v_i [1 - \exp(-\gamma(1/\rho_i - 1/\rho_{\text{jam}}))]$.
   - Para $\rho_i > 5{,}5\,\text{ped/m}^2$: colapso de fluxo (*jamming*, $v_i = 0$).
5. **Resolução de Conflitos e Gargalo nas Portas**:
   Quando dois ou mais agentes disputam a mesma célula em $t + \Delta t$, vence o agente com maior pressão física $P_k = m_k v_k + k_{\text{comp}} \cdot \text{vizinhos}$ (ou sorteio estocástico se $|P_i - P_j| \le \Delta P$), bloqueando os demais e formando arcos de retenção nas portas.

---

## 2. Bibliotecas Utilizadas e Instalação

### 2.1. Para que serve cada biblioteca (`requirements.txt`)

| Biblioteca | Versão / Pacote | Papel no Projeto |
|---|---|---|
| **Mesa** | `mesa>=3.5` | Framework principal de Modelagem Baseada em Agentes (ABM): fornece as classes base `Model`, `Agent` e o coletor de métricas `DataCollector`. |
| **Mesa-LLM** | `mesa-llm>=0.3.2` | Extensão agêntica do Mesa que integra Grandes Modelos de Linguagem (`LLMAgent`, `ShortTermMemory`, `ReActReasoning` e interface LiteLLM para múltiplos provedores como Gemini, OpenAI e Ollama). |
| **NumPy** | `numpy` | Cálculo matricial de alta velocidade: malha espacial do pavilhão, imagens integrais $O(1)$ de densidade/vizinhança, campos geodésicos ($S_{ij}$) e sorteios estocásticos. |
| **Pandas** | `pandas` | Estruturação e exportação dos resultados coletados pelo `DataCollector` para arquivos `.csv` (`serie_temporal.csv` e `agentes.csv`). |
| **Matplotlib** | `matplotlib` | Geração dos gráficos científicos estáticos (`curvas.png`, `gargalos.png`, `instantaneos.png` e `por_tipo.png`). |
| **Python-Dotenv** | `python-dotenv` | Carregamento seguro das chaves de API (`GEMINI_API_KEY`, `OPENAI_API_KEY`, `LLM_MODEL`) a partir do arquivo `.env`. |
| **Starlette** | `starlette` | Framework web ASGI leve que serve as rotas da API em tempo real (`/api/init`, `/api/step`, `/api/reset`, `/api/agente`, `/api/comparar`) e a página do Dashboard Visual. |
| **Uvicorn** | `uvicorn` | Servidor ASGI de alta performance utilizado para hospedar o Dashboard Visual localmente (`http://127.0.0.1:8765`). |

*(Dependência transitiva importante instalada automaticamente pelo `mesa-llm`: **Pydantic**, usada em `decisao.py` para validar o JSON estruturado `EscolhaSaida(saida, justificativa)` exigido pelo `PROMPT_EVACUACAO_V8`).*

### 2.2. Como Instalar as Bibliotecas

> **Recomendação de versão do Python:** Utilize **Python 3.12** (ou 3.11/3.13 estável). Evite versões pré-lançamento (como Python 3.15 alpha), pois algumas dependências do `mesa-llm` ainda não possuem *wheels* pré-compiladas para elas.

No PowerShell, dentro da pasta do projeto:

```powershell
cd "C:\Users\bielc\OneDrive\Documentos\trabalhos\2026_2\Sim\simulador-vilagermanica\mesa\sim_evacuacao"

# 1. Criar o ambiente virtual (.venv) com Python 3.12
py -3.12 -m venv .venv

# 2. Instalar todas as bibliotecas listadas no requirements.txt
.\.venv\Scripts\pip install -r requirements.txt
```

Ou, caso queira instalar manualmente com um único comando `pip`:
```powershell
.\.venv\Scripts\pip install -U mesa mesa-llm numpy pandas matplotlib python-dotenv starlette uvicorn
```

---

## 3. Como Rodar o Projeto

---

### 3.1. Opção 1: Rodar o Dashboard Visual Interativo (Recomendado)

Para abrir o painel visual no navegador:
```powershell
.\.venv\Scripts\python dashboard.py
```
O terminal exibirá `Dashboard iniciado em: http://127.0.0.1:8765` e abrirá o navegador automaticamente.

**Recursos disponíveis no Dashboard:**
- **Seletor de Cenário ($2 \times 2$)**: alterne entre `C1 (Controle)`, `C2 (Blackout Total)`, `C3 (Saída S2 Bloqueada)` e `C4 (Cenário Crítico)`. A troca reinicia e aplica o cenário automaticamente; para comparar o movimento em `C1`/`C2`, inicie a simulação.
- **Controles de Execução**: `▶ Executar / ⏸ Pausar`, `⏭ +0.5s`, `⏩ +10s`, `🏁 Fim`, `🔄 Reiniciar` e seletor de velocidade (`1×` a `10×`).
- **Camadas Visuais do Mapa**: alterne a cor dos agentes entre **Tipologia (`T01`–`T12`)**, **Estado Comportamental** ou **Saída-Alvo (`S1`–`S9`)**, e o mapa de calor entre **Densidade Local ($\text{pessoas/m}^2$)**, **Gargalos Acumulados** e **Campo Geodésico $S_{ij}$**.
- **Filtro por Tipo (`T01`–`T12`)**: clique em qualquer um dos 12 tipos abaixo do mapa para destacar apenas os agentes daquele grupo.
- **Inspetor de Agente (`PROMPT_EVACUACAO_V8`)**: clique sobre qualquer agente no mapa (ou no feed lateral) para ver suas opções observadas, perfil decisório e memória de justificativas.
- **Botão `📊 Comparar 2×2 (C1–C4)`**: executa os 4 cenários do plano experimental e plota a tabela comparativa e as curvas de evacuação.

---

### 3.2. Opção 2: Rodar em Lote via Terminal (`run.py`)

Para rodar a simulação completa via terminal e salvar todos os relatórios e figuras na pasta `resultados/`:

```powershell
# Execução padrão (300 ocupantes T01..T12, modo regras, sem custo de API)
.\.venv\Scripts\python run.py

# Alterando o número de ocupantes e a semente aleatória
.\.venv\Scripts\python run.py --n 500 --seed 7
```

**Arquivos gerados em `resultados/`:**
- `resumo.json`: métricas globais ($t_{50\%}$, $t_{90\%}$, $t_{\text{último}}$, saídas por porta, conflitos, trocas de alvo e tempos por tipo `T01`–`T12`).
- `serie_temporal.csv`: evolução passo a passo dos estados, risco médio, retidos, conflitos e fluxo em cada porta.
- `agentes.csv`: dados individuais de cada ocupante (ID, tipo `T01`–`T12`, porta familiar, alvo final, trocas de alvo, instantes de transição e porta de saída).
- `instantaneos.png`: quadros espaciais do pavilhão em $t = 0, 30, 90, 180\,\text{s}$ coloridos pelos 12 tipos de atores.
- `por_tipo.png`: boxplot comparando o tempo de evacuação de cada tipo (`T01` a `T12`).
- `curvas.png`: gráficos de evolução dos estados, risco percebido (EDM) e fluxo por porta.
- `gargalos.png`: mapa de calor das zonas de retenção e fila nas portas.

---

### 3.3. Como Ativar Agentes com IA (`Mesa-LLM`)

Por padrão (`--llm 0`), todos os ocupantes usam a política de utilidade calibrada com os critérios do `PROMPT_EVACUACAO_V8` (execução rápida em ~1,2 s e sem custo de API). Para que `N` ocupantes (distribuídos em rodízio entre `T01`..`T12`) consultem um modelo de linguagem real via `Mesa-LLM`:

1. Copie o arquivo `.env.example` para `.env`:
   ```powershell
   copy .env.example .env
   ```
2. Edite o arquivo `.env` e informe sua chave de API (formato `provedor/modelo` do LiteLLM):
   ```env
   GEMINI_API_KEY=sua_chave_aqui
   LLM_MODEL=gemini/gemini-2.0-flash
   ```
   *(Alternativamente, você pode usar OpenAI com `OPENAI_API_KEY=...` e `LLM_MODEL=openai/gpt-4o-mini`, ou rodar localmente sem chave usando Ollama com `LLM_MODEL=ollama/llama3.1`)*.
3. Execute no terminal passando `--llm N` (ou defina o campo **LLM** no topo do Dashboard Visual e clique em **Reiniciar**):
   ```powershell
   # 12 agentes via Mesa-LLM (1 de cada tipo T01..T12)
   .\.venv\Scripts\python run.py --llm 12
   ```
4. As decisões estruturadas (`saida` e `justificativa`) tomadas pelo LLM ficam salvas em `resultados/log_llm.json` e aparecem ao vivo no **Feed de Decisões** do Dashboard.
