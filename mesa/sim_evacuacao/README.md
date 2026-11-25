# Simulador de Evacuação — Parque Vila Germânica (`Mesa` + `Mesa-LLM`)

## 1. Setup (Instalação de Dependências)

> **Requisito:** Python **3.11**, **3.12** ou **3.13**.

1. Acesse a pasta do projeto:
   ```bash
   cd mesa/sim_evacuacao
   ```

2. Crie e ative o ambiente virtual (`.venv`):

   **Windows (PowerShell):**
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

   **Linux / macOS:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```

---

## 2. Como Rodar

### Opção 1: Dashboard Visual no Navegador (Recomendado)

Com o ambiente virtual ativo, execute:

```bash
python dashboard.py
```

* O servidor local iniciará em `http://127.0.0.1:8765` e abrirá o navegador automaticamente.
* Opções adicionais:
  ```bash
  python dashboard.py --porta 8765 --sem-abrir
  ```

---

### Opção 2: Execução via Terminal (`run.py`)

Executa a simulação em lote e exporta os gráficos (`.png`), tabelas (`.csv`) e métricas (`.json`) para a pasta `resultados/`:

```bash
# Execução padrão (300 ocupantes, modo regras)
python run.py

# Alterando o número de ocupantes e a seed
python run.py --n 500 --seed 7
```

---

### Opção 3: Testando com IA (`Mesa-LLM` / Gemini)

* **Pelo Dashboard:** informe sua chave no campo **`🔑 Gemini Key`** no topo da página, defina o número de agentes em **`LLM`** e clique em **`Aplicar`** (ou use o botão **`🧠 Comparar C1–C4 (Com vs. Sem LLM)`**).
* **Pelo Terminal:**
  ```bash
  # Passando a chave diretamente via argumento
  python run.py --gemini-key "SUA_CHAVE_AQUI" --llm 3

  # Comparando os 4 cenários (C1–C4) Com e Sem LLM
  python run.py --comparar-2x2 --gemini-key "SUA_CHAVE_AQUI" --llm 3
  ```
  *(Alternativamente, copie `.env.example` para `.env`, preencha `GEMINI_API_KEY=` e execute `python run.py --llm 3`).*
