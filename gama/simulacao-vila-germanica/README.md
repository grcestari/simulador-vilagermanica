# Simulação de Evacuação no Parque Vila Germânica (GAMA Platform)

**Disciplina:** Optativa I (Simulação) — Prof. Dr. Marcos Mattedi  
**Autores:** Gabriel Cestari e Thomas Haskel  
**Instituição:** FURB — Universidade Regional de Blumenau (2026)  
**Tema:** Módulo III (Simulação Baseada em Regras) — Aula 13: Dados + GAMA  

---

## 📁 Estrutura do Projeto

O projeto segue a padronização oficial da plataforma GAMA (conforme apresentado na Aula 13, Slide 30):

```
simulacao-vila-germanica/
├── includes/                      # Dados de entrada GIS, CSVs e arquivos auxiliares
│   ├── pvg_geometrias.*          # Linhas e plantas arquiteturais originais do PVG
│   ├── pvg_textos.*              # Textos e marcos espaciais identificados no AutoCAD
│   ├── setores.*                 # Polígonos dos pavilhões (Setor 1, Setor 2, Setor 3, Setor 4)
│   ├── saidas.*                  # Portões de saída externa do parque (S1 a S6 e emergências)
│   ├── passagens.*               # Portas de passagem interna entre os setores (P1 a P3)
│   ├── caminhos.*                # Vias e eixos principais de circulação interna
│   ├── visitantes.csv            # Tabela sintética de população (3.000 agentes parametrizados)
│   └── PREVIA_geometrias_extraidas.png
├── models/                        # Modelos GAML executáveis
│   ├── Oktoberfest_Evacuacao_3D.gaml  # Modelo principal completo com 3D, gráficos e monitores
│   ├── evacuacao.gaml            # Modelo de referência padrão
│   └── New Model.gaml            # Atalho de inicialização rápida
├── results/                       # Diretório de exportação dos experimentos
│   ├── historico_evacuacao.csv   # Série temporal ciclo a ciclo
│   ├── resumo_cenarios.csv       # Tabela síntese dos indicadores (C1 a C4)
│   ├── curva_evacuacao_acumulada.png
│   ├── vazao_por_saida.png
│   └── evolucao_congestionamento.png
└── tools/                         # Scripts auxiliares em Python
    ├── preparar_dados.py         # Validador e gerador de novas populações/camadas
    └── analisar_resultados.py    # Gerador de gráficos estatísticos pós-simulação
```

---

## 🚀 Como Executar no GAMA IDE

1. **Abrir o GAMA:**
   - Com o GAMA aberto no workspace `C:\Users\thomh\Gama_Workspace`, o projeto `simulacao-vila-germanica` já estará visível no painel **Models Manager** (lado esquerdo).
   - Se necessário, clique com o botão direito no painel e selecione **Refresh** (`F5`).

2. **Abrir o Modelo:**
   - Navegue até `simulacao-vila-germanica` > `models` > `Oktoberfest_Evacuacao_3D.gaml`.
   - Dê um duplo clique no arquivo para abrir o editor GAML.

3. **Iniciar o Experimento:**
   - No topo do editor ou no painel de experimentos, selecione o experimento:
     - `Evacuacao_Oktoberfest` (GUI interativa com renderizador 3D/OpenGL e gráficos em tempo real).
     - `Cenarios_Aula11` (Modo Batch para execução automatizada dos 4 cenários da Aula 11).
   - Clique no botão verde **Play** (ou `Ctrl + R`).

4. **Painéis da Interface de Execução (conforme Slide 23):**
   - **PVG - evacuação em 3D:** Visão espacial dos pavilhões, agentes pedestres (amarelo: sóbrios, ciano: idosos, magenta: alcoolizados, vermelho: em fila), balizadores de staff com feixe de luz amarela/lanterna e portões abertos (verde) ou bloqueados (vermelho).
   - **Congestionamento:** Gráfico em tempo real de agentes impedidos nos gargalos.
   - **Indicadores:** Gráfico do percentual acumulado de pessoas evacuadas com os marcos **T90** e **T95**.
   - **Fluxo por saída:** Curvas de vazão instantânea (pessoas/segundo) para as saídas `S1`, `S2`, `S3`, `S4`, `S5` e `S6`.

---

## 🔬 Parâmetros Experimentais Configuráveis

Na aba lateral de parâmetros do GAMA, é possível ajustar:
- **Número de Visitantes:** 500 a 40.000 pessoas (padrão interativo: 3.000).
- **Proporção de Alcoolizados:** 10%, 25%, 40% (Matriz do Protocolo Experimental).
- **Número de Balizadores (Staff):** 0, 10, 25 indivíduos com lanternas.
- **Cenários da Aula 11:**
  - **C1 (Controle):** Iluminação de emergência ativada, todas as saídas abertas.
  - **C2 (Blackout Total):** Iluminação desligada, orientação degradada, todas as saídas abertas.
  - **C3 (Saída Bloqueada):** Iluminação ativada, saída crítica (ex: S2) bloqueada.
  - **C4 (Crítico):** Blackout total combinado com saída crítica bloqueada (stress test).

---

## 🛠 Ferramentas Auxiliares (Python)

Para reprocessar os dados ou gerar relatórios analíticos:

```bash
# Gerar uma nova população sintética com N agentes (ex: 5.000)
python tools/preparar_dados.py 5000

# Gerar os gráficos analíticos a partir dos dados gravados em results/
python tools/analisar_resultados.py
```
