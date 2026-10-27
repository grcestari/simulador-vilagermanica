"""
Script: preparar_dados.py
Descrição: Processamento, validação de shapefiles e geração de populações sintéticas para o GAMA.
Projeto: Simulação de Evacuação no Parque Vila Germânica (Oktoberfest de Blumenau)
Autores: Gabriel Cestari e Thomas Haskel
Disciplina: Optativa I (Simulação) - Prof. Dr. Marcos Mattedi (FURB)
"""

import os
import sys
import random
import csv
import shapefile

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INCLUDES_DIR = os.path.join(BASE_DIR, "includes")

def gerar_populacao_csv(n_total=3000, prop_alc=0.25, prop_ido=0.15, seed=42):
    """Gera o arquivo CSV de visitantes com distribuição realista por setor e perfil."""
    random.seed(seed)
    output_path = os.path.join(INCLUDES_DIR, "visitantes.csv")
    
    # Distribuição espacial nos pavilhões
    # Setor 1: 25%, Setor 2: 35%, Setor 3: 25%, Setor 4 (Biergarten): 15%
    setores_info = [
        ("Setor 1", 0.25, (1120.0, 2220.0), (1880.0, 2510.0)),
        ("Setor 2", 0.35, (1120.0, 2220.0), (1080.0, 1790.0)),
        ("Setor 3", 0.25, (1120.0, 2220.0), (490.0, 990.0)),
        ("Setor 4", 0.15, (1130.0, 2420.0), (2590.0, 3120.0))
    ]
    
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "setor", "perfil", "velocidade_ms", "tempo_reacao_s", "coord_x", "coord_y"])
        
        pid = 1
        for sname, spct, (xmin, xmax), (ymin, ymax) in setores_info:
            count = int(n_total * spct)
            for _ in range(count):
                r = random.random()
                if r < prop_alc:
                    perfil = "alcoolizado"
                    v0 = round(random.gauss(1.1, 0.20), 2)
                    t_reacao = round(random.uniform(8.0, 25.0), 1)
                elif r < (prop_alc + prop_ido):
                    perfil = "idoso"
                    v0 = round(random.gauss(0.9, 0.10), 2)
                    t_reacao = round(random.uniform(5.0, 15.0), 1)
                else:
                    perfil = "sobrio"
                    v0 = round(random.gauss(1.4, 0.15), 2)
                    t_reacao = round(random.uniform(2.0, 8.0), 1)
                
                x = round(random.uniform(xmin, xmax), 2)
                y = round(random.uniform(ymin, ymax), 2)
                writer.writerow([pid, sname, perfil, max(0.4, v0), t_reacao, x, y])
                pid += 1

    print(f"[OK] Gerado arquivo de populacao sintetica: {output_path} ({pid-1} agentes)")

def gerar_camadas_gis():
    """Gera shapefiles auxiliares (saidas, setores, caminhos) na pasta includes."""
    prj_path = os.path.join(INCLUDES_DIR, "pvg_geometrias.prj")
    prj_content = ""
    if os.path.exists(prj_path):
        with open(prj_path, "r", encoding="utf-8", errors="ignore") as f:
            prj_content = f.read()

    # 1. Saídas
    saidas_base = os.path.join(INCLUDES_DIR, "saidas")
    try:
        w = shapefile.Writer(saidas_base, shapeType=shapefile.POINT)
        w.field("ID", "C", 10)
        w.field("NOME", "C", 40)
        w.field("SETOR", "C", 20)
        w.field("LARGURA_M", "F", 6, 2)
        w.field("CAP_PESSOA", "N", 6)
        w.field("STATUS", "C", 15)

        saidas_data = [
            ("S1", "Saida Setor 1 Norte (Stein)", "Setor 1", 6.0, 15, "Aberta", 1622.43, 2540.28),
            ("S2", "Saida Setor 2 Oeste (Campos)", "Setor 2", 8.0, 20, "Aberta", 1116.36, 1692.57),
            ("S3", "Saida Setor 2 Leste (Patio)", "Setor 2", 8.0, 20, "Aberta", 2233.32, 1434.93),
            ("S4", "Saida Setor 3 Oeste (Acesso)", "Setor 3", 6.0, 15, "Aberta", 1112.04, 677.73),
            ("S5", "Saida Setor 3 Sul (Galegao)", "Setor 3", 6.0, 15, "Aberta", 1751.31, 462.36),
            ("S6", "Saida Biergarten Norte", "Setor 4", 8.0, 20, "Aberta", 1639.95, 3000.12),
            ("E1", "Emergencia Setor 1 Sul", "Setor 1", 4.0, 10, "Aberta", 1945.23, 1831.32),
            ("E2", "Emergencia Rota Fuga Central", "Setor 2", 5.0, 12, "Aberta", 1501.47, 1028.16),
            ("E3", "Emergencia Setor 3 Leste", "Setor 3", 4.0, 10, "Aberta", 2231.76, 721.53),
            ("E4", "Emergencia Biergarten Oeste", "Setor 4", 4.0, 10, "Aberta", 1102.68, 2722.17)
        ]
        for sid, nome, setor, larg, cap, status, x, y in saidas_data:
            w.point(x, y)
            w.record(sid, nome, setor, larg, cap, status)
        w.close()
        if prj_content:
            with open(os.path.join(INCLUDES_DIR, "saidas.prj"), "w") as f:
                f.write(prj_content)
        print(f"[OK] Camada de saidas gerada: {saidas_base}.shp")
    except Exception as e:
        print(f"[AVISO] Camada de saidas ja existente ou em uso pelo GAMA ({e})")

    # 2. Setores
    setores_base = os.path.join(INCLUDES_DIR, "setores")
    try:
        w = shapefile.Writer(setores_base, shapeType=shapefile.POLYGON)
        w.field("ID", "C", 10)
        w.field("NOME", "C", 40)
        w.field("AREA_M2", "F", 10, 2)
        w.field("CAP_MAX", "N", 8)
        w.field("COR_HEX", "C", 10)

        setores_poly = [
            ("Setor 1", "Setor 1 - Eisenbahn", 5477.0, 10000, "#4169E1", [
                [1090.0, 1850.0], [2250.0, 1850.0], [2250.0, 2540.0], [1090.0, 2540.0], [1090.0, 1850.0]
            ]),
            ("Setor 2", "Setor 2 - Pavilhao Central", 7266.0, 14000, "#32CD32", [
                [1090.0, 1050.0], [2250.0, 1050.0], [2250.0, 1820.0], [1090.0, 1820.0], [1090.0, 1050.0]
            ]),
            ("Setor 3", "Setor 3 - Pavilhao Sul", 5900.0, 11000, "#FF8C00", [
                [1090.0, 460.0], [2250.0, 460.0], [2250.0, 1020.0], [1090.0, 1020.0], [1090.0, 460.0]
            ]),
            ("Setor 4", "Setor 4 - Biergarten", 3500.0, 5000, "#9370DB", [
                [1100.0, 2560.0], [2450.0, 2560.0], [2450.0, 3150.0], [1100.0, 3150.0], [1100.0, 2560.0]
            ])
        ]
        for sid, nome, area, cap, cor, pts in setores_poly:
            w.poly([pts])
            w.record(sid, nome, area, cap, cor)
        w.close()
        if prj_content:
            with open(os.path.join(INCLUDES_DIR, "setores.prj"), "w") as f:
                f.write(prj_content)
        print(f"[OK] Camada de setores gerada: {setores_base}.shp")
    except Exception as e:
        print(f"[AVISO] Camada de setores ja existente ou em uso pelo GAMA ({e})")

    # 3. Caminhos
    caminhos_base = os.path.join(INCLUDES_DIR, "caminhos")
    try:
        w = shapefile.Writer(caminhos_base, shapeType=shapefile.POLYLINE)
        w.field("ID", "C", 10)
        w.field("NOME", "C", 40)
        w.field("LARGURA", "F", 6, 2)

        caminhos_lines = [
            ("C1", "Eixo Norte-Sul Oeste", 8.0, [[1116.0, 460.0], [1116.0, 1050.0], [1116.0, 1850.0], [1116.0, 2540.0], [1116.0, 3050.0]]),
            ("C2", "Eixo Norte-Sul Leste", 8.0, [[2230.0, 460.0], [2230.0, 1050.0], [2230.0, 1850.0], [2230.0, 2540.0], [2230.0, 3050.0]]),
            ("C3", "Corredor Central Rota Fuga", 12.0, [[1116.0, 1030.0], [1670.0, 1030.0], [2230.0, 1030.0]]),
            ("C4", "Conexao Setor 1 - Setor 2", 10.0, [[1116.0, 1835.0], [1670.0, 1835.0], [2230.0, 1835.0]]),
            ("C5", "Conexao Setor 1 - Biergarten", 10.0, [[1116.0, 2550.0], [1670.0, 2550.0], [2230.0, 2550.0]]),
            ("C6", "Acesso Sul Galegao", 8.0, [[1116.0, 462.0], [1751.0, 462.0], [2230.0, 462.0]]),
            ("C7", "Acesso Portaria Principal", 10.0, [[2230.0, 1435.0], [2525.0, 1523.0]])
        ]
        for cid, cnome, clarg, cpts in caminhos_lines:
            w.line([cpts])
            w.record(cid, cnome, clarg)
        w.close()
        if prj_content:
            with open(os.path.join(INCLUDES_DIR, "caminhos.prj"), "w") as f:
                f.write(prj_content)
        print(f"[OK] Camada de caminhos gerada: {caminhos_base}.shp")
    except Exception as e:
        print(f"[AVISO] Camada de caminhos ja existente ou em uso pelo GAMA ({e})")

if __name__ == "__main__":
    n = 3000
    if len(sys.argv) > 1:
        n = int(sys.argv[1])
    print(f"Executando preparacao de dados para GAMA (N={n})...")
    gerar_camadas_gis()
    gerar_populacao_csv(n_total=n)
    print("Processamento concluido com sucesso!")
