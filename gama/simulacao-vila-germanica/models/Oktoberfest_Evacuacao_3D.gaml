/**
 * Modelo: Oktoberfest_Evacuacao_3D
 * Descrição: Simulação Baseada em Agentes da Evacuação Emergencial sob Apagão Noturno no Parque Vila Germânica
 * Autores: Gabriel Cestari e Thomas Haskel
 * Disciplina: Optativa I (Simulação) - Prof. Dr. Marcos Mattedi (FURB)
 * Módulo III: Simulação Baseada em Regras - Aula 13 (Dados + GAMA)
 */

model Oktoberfest_Evacuacao_3D

global {
	// ==========================================
	// ARQUIVOS GEOGRÁFICOS E ENTRADAS (includes)
	// ==========================================
	file shape_file_geometrias <- shape_file(
	    "../includes/pvg_geometrias.shp",
	"EPSG:3857"
	);
	
	file shape_file_setores <- shape_file(
	    "../includes/setores.shp",
	"EPSG:3857"
	);
	
	file shape_file_saidas <- shape_file(
	    "../includes/saidas.shp",
	"EPSG:3857"
	);
	
	file shape_file_caminhos <- shape_file(
	    "../includes/caminhos.shp",
	"EPSG:3857"
	);
	
	geometry shape <- envelope(shape_file_geometrias);
	float step <- 1.0 #s; // Passo temporal discreto fixo de 1 segundo (conforme protocolo)

	// ==========================================
	// PARÂMETROS EXPERIMENTAIS (Matriz 3x3 e Cenários C1-C4)
	// ==========================================
	int numero_visitantes <- 3000 min: 100 max: 50000;
	float prop_alcoolizados <- 0.25 min: 0.0 max: 1.0; // Níveis: 0.10, 0.25, 0.40
	float prop_idosos <- 0.15 min: 0.0 max: 0.5;       // 15% idosos
	int n_staff <- 10 min: 0 max: 50;                 // Níveis: 0, 10, 25

	// Cenários da Aula 11 (C1, C2, C3, C4)
	bool blackout_ativo <- true;
	bool iluminacao_emergencia <- false;        // true no C1 e C3; false no C2 e C4
	string saida_bloqueada <- "Nenhuma" among: ["Nenhuma", "S1", "S2", "S3", "S4", "S5", "S6"];

	// Exportação de dados
	bool exportar_dados <- true;
	string arquivo_historico <- "../results/historico_evacuacao.csv";
	string arquivo_resumo <- "../results/resumo_cenarios.csv";

	// ==========================================
	// VARIÁVEIS DE ESTADO E INDICADORES
	// ==========================================
	int total_populacao <- 0;
	int total_evacuados <- 0;
	int restantes <- 0;
	float pct_evacuados <- 0.0;
	int agentes_impedidos <- 0;
	float densidade_maxima <- 0.0;
	
	// Tempos característicos
	float t90 <- -1.0;
	float t95 <- -1.0;
	float tte <- -1.0; // Tempo Total de Evacuação

	// Fluxo instantâneo por saída (pessoas por segundo no ciclo atual)
	int fluxo_S1 <- 0;
	int fluxo_S2 <- 0;
	int fluxo_S3 <- 0;
	int fluxo_S4 <- 0;
	int fluxo_S5 <- 0;
	int fluxo_S6 <- 0;

	// Acumuladores de vazão por saída
	map<string, int> evacuados_por_saida <- ["S1"::0, "S2"::0, "S3"::0, "S4"::0, "S5"::0, "S6"::0];
	map<string, int> fluxo_ciclo_saida   <- ["S1"::0, "S2"::0, "S3"::0, "S4"::0, "S5"::0, "S6"::0];

	// Rede de circulação
	graph rede_caminhos;

	// ==========================================
	// INICIALIZAÇÃO DO MODELO (init)
	// ==========================================
	init {
		write "=========================================================";
		write "Inicializando Simulação de Evacuação PVG - Oktoberfest";
		write "População: " + numero_visitantes + " | % Alcoolizados: " + (prop_alcoolizados * 100) + "% | Staff: " + n_staff;
		write "Condição: Blackout=" + blackout_ativo + " | Emergência=" + iluminacao_emergencia + " | Bloqueio=" + saida_bloqueada;
		write "=========================================================";

		// 1. Criar setores a partir do shapefile
		create setor from: shape_file_setores with: [
			id_setor::string(read("ID")),
			nome_setor::string(read("NOME")),
			area_m2::float(read("AREA_M2")),
			cor_hex::string(read("COR_HEX"))
		];

		// 2. Criar saídas a partir do shapefile
		create saida from: shape_file_saidas with: [
			id_saida::string(read("ID")),
			nome_saida::string(read("NOME")),
			setor_ref::string(read("SETOR")),
			largura_m::float(read("LARGURA_M")),
			capacidade_vazao::int(read("CAP_PESSOA")),
			status::string(read("STATUS"))
		];

		// Aplicar bloqueio de saída se definido no cenário
		if (saida_bloqueada != "Nenhuma") {
			ask saida where (each.id_saida = saida_bloqueada) {
				self.status <- "Bloqueada";
				write "ATENÇÃO: Portão de saída " + self.id_saida + " (" + self.nome_saida + ") foi BLOQUEADO!";
			}
		}

		// 3. Criar caminhos e montar grafo de circulação
		create caminho from: shape_file_caminhos with: [
			id_caminho::string(read("ID")),
			largura::float(read("LARGURA"))
		];
		rede_caminhos <- as_edge_graph(caminho);

		// 4. Carregar elementos arquiteturais como obstáculos de fundo
		create obstaculo from: shape_file_geometrias;

		// 5. Instanciar balizadores (staff) nos portões e gargalos estratégicos
		if (n_staff > 0) {
			list<saida> saidas_ativas <- saida where (each.status = "Aberta");
			int staff_alocados <- 0;
			
			// Alocar staff prioritariamente nos portões de saída
			loop s over: saidas_ativas {
				if (staff_alocados < n_staff) {
					create staff {
						location <- s.location;
						saida_alvo <- s;
						tem_lanterna <- true;
						alcance_iluminacao <- 30.0;
					}
					s.tem_balizador <- true;
					staff_alocados <- staff_alocados + 1;
				}
			}

			// Se ainda houver staff restante, alocar em interseções e corredores centrais
			int staff_restantes <- n_staff - staff_alocados;
			if (staff_restantes > 0) {
				create staff number: staff_restantes {
					setor sec_aleat <- one_of(setor);
					location <- any_location_in(sec_aleat);
					tem_lanterna <- true;
					alcance_iluminacao <- 25.0;
				}
			}
		}

		// 6. Instanciar visitantes
		// Se o arquivo CSV contiver o número necessário, podemos ler direto,
		// ou gerar proporcionalmente aos setores conforme o protocolo.
		total_populacao <- numero_visitantes;
		restantes <- total_populacao;

		create visitante number: numero_visitantes {
			// Sorteio de perfil comportamental
			float sorteio <- rnd(1.0);
			if (sorteio < prop_alcoolizados) {
				perfil <- "alcoolizado";
				velocidade_base <- rnd(0.8, 1.2); // v0 média ~ 1.1 m/s
				tempo_reacao <- rnd(8.0, 25.0);    // tempo de reação lento sob álcool
				capacidade_orientacao <- 0.35;
				cor_agente <- #magenta;
			} else if (sorteio < (prop_alcoolizados + prop_idosos)) {
				perfil <- "idoso";
				velocidade_base <- rnd(0.7, 1.0); // v0 média ~ 0.9 m/s
				tempo_reacao <- rnd(5.0, 15.0);
				capacidade_orientacao <- 0.60;
				cor_agente <- #cyan;
			} else {
				perfil <- "sobrio";
				velocidade_base <- rnd(1.2, 1.6); // v0 média ~ 1.4 m/s
				tempo_reacao <- rnd(2.0, 8.0);
				capacidade_orientacao <- 0.90;
				cor_agente <- #yellow;
			}

			// Alocação espacial no pavilhão
			setor setor_inicial <- one_of(setor);
			location <- any_location_in(setor_inicial);
			speed <- velocidade_base;
			alvo_saida <- nil;
		}

		// Inicializar cabeçalho do arquivo CSV de histórico se exportação estiver ativa
		if (exportar_dados) {
			save ["tempo_s", "restantes", "evacuados", "pct_evacuados", "impedidos", "densidade_max", "fluxo_S1", "fluxo_S2", "fluxo_S3", "fluxo_S4", "fluxo_S5", "fluxo_S6"] 
				to: arquivo_historico format: "csv" rewrite: true;
		}
	}

	// ==========================================
	// DINÂMICA GLOBAL A CADA CICLO (tick = 1s)
	// ==========================================
	reflex monitorar_indicadores {
		// Zerar contadores instantâneos de fluxo do ciclo
		fluxo_S1 <- fluxo_ciclo_saida["S1"];
		fluxo_S2 <- fluxo_ciclo_saida["S2"];
		fluxo_S3 <- fluxo_ciclo_saida["S3"];
		fluxo_S4 <- fluxo_ciclo_saida["S4"];
		fluxo_S5 <- fluxo_ciclo_saida["S5"];
		fluxo_S6 <- fluxo_ciclo_saida["S6"];

		// Resetar medidores instantâneos
		fluxo_ciclo_saida["S1"] <- 0;
		fluxo_ciclo_saida["S2"] <- 0;
		fluxo_ciclo_saida["S3"] <- 0;
		fluxo_ciclo_saida["S4"] <- 0;
		fluxo_ciclo_saida["S5"] <- 0;
		fluxo_ciclo_saida["S6"] <- 0;

		total_evacuados <- total_populacao - length(visitante);
		restantes <- length(visitante);
		pct_evacuados <- (total_evacuados / total_populacao) * 100.0;

		// Contar agentes temporariamente impedidos nos portões
		agentes_impedidos <- visitante count (each.esperando_no_portao);

		// Registro de T90, T95 e TTE
		if (t90 < 0.0 and pct_evacuados >= 90.0) {
			t90 <- time;
			write ">>> Marco atingido: T90 = " + t90 + "s (" + total_evacuados + " evacuados)";
		}
		if (t95 < 0.0 and pct_evacuados >= 95.0) {
			t95 <- time;
			write ">>> Marco atingido: T95 = " + t95 + "s (" + total_evacuados + " evacuados)";
		}

		// Estimativa da densidade máxima nos gargalos (portões)
		float maior_dens <- 0.0;
		ask saida where (each.status = "Aberta") {
			int vizinhos <- length(visitante at_distance 15.0);
			float dens_local <- vizinhos / (3.14159 * 15.0 * 15.0 / 2.0); // pessoas/m² aproximada
			if (dens_local > maior_dens) {
				maior_dens <- dens_local;
			}
		}
		if (maior_dens > densidade_maxima) {
			densidade_maxima <- maior_dens;
		}

		// Exportação para CSV periódica (a cada 5 segundos)
		if (exportar_dados and (cycle mod 5 = 0 or restantes = 0)) {
			save [int(time), restantes, total_evacuados, pct_evacuados, agentes_impedidos, densidade_maxima, fluxo_S1, fluxo_S2, fluxo_S3, fluxo_S4, fluxo_S5, fluxo_S6]
				to: arquivo_historico format: "csv" rewrite: false;
		}

		// Critério de Parada: Esvaziamento total ou horizonte de 3600s
		if (restantes <= 0 or cycle >= 3600) {
			tte <- time;
			write "=========================================================";
			write "SIMULAÇÃO CONCLUÍDA!";
			write "Tempo Total de Evacuação (TTE): " + tte + "s (" + (tte / 60.0) + " min)";
			write "Percentual Evacuado: " + pct_evacuados + "% (" + total_evacuados + "/" + total_populacao + ")";
			write "T90: " + t90 + "s | T95: " + t95 + "s";
			write "Densidade Máxima Registrada: " + densidade_maxima + " ped/m²";
			write "Evacuados por Saída: " + evacuados_por_saida;
			write "=========================================================";

			if (exportar_dados) {
				save [saida_bloqueada, blackout_ativo, iluminacao_emergencia, prop_alcoolizados, n_staff, total_populacao, total_evacuados, pct_evacuados, t90, t95, tte, densidade_maxima]
					to: arquivo_resumo format: "csv" rewrite: false;
			}
			do pause;
		}
	}
}

// ==========================================
// ESPÉCIES DO MODELO (Agents & Environment)
// ==========================================

// 1. Pavilhões / Setores
species setor {
	string id_setor;
	string nome_setor;
	float area_m2;
	string cor_hex;

	aspect padrao {
		draw shape color: rgb(cor_hex) border: #black;
		draw nome_setor at: location + {0, 0, 5} color: #black font: font("SansSerif", 18, #bold);
	}

	aspect visao_3d {
		draw shape color: rgb(cor_hex) border: #white depth: 4.0;
		draw nome_setor at: location + {0, 0, 10} color: #white font: font("SansSerif", 16, #bold);
	}
}

// 2. Elementos arquiteturais (paredes e divisórias da planta do PVG)
species obstaculo {
	aspect padrao {
		draw shape color: rgb(160, 160, 160);
	}
}

// 3. Caminhos e Corredores de Fuga
species caminho {
	string id_caminho;
	float largura;

	aspect padrao {
		draw shape color: rgb(200, 200, 200) width: 2.0;
	}
}

// 4. Portões de Saída da Vila Germânica
species saida {
	string id_saida;
	string nome_saida;
	string setor_ref;
	float largura_m;
	int capacidade_vazao; // capacidade máxima de pessoas que passam simultaneamente por segundo
	string status;        // "Aberta" ou "Bloqueada"
	bool tem_balizador <- false;
	int ocupacao_atual <- 0;

	reflex gerenciar_fluxo {
		ocupacao_atual <- 0; // zerado a cada ciclo para permitir nova leva de pedestres
	}

	aspect padrao {
		if (status = "Bloqueada") {
			draw cross(20.0, 4.0) color: #red;
			draw "BLOQUEADA (" + id_saida + ")" at: location + {0, -15, 0} color: #red font: font("SansSerif", 12, #bold);
		} else {
			draw rectangle(22.0, 12.0) depth: 6.0 color: (tem_balizador ? #cyan : #green) border: #black;
			draw id_saida at: location + {0, -12, 0} color: #lime font: font("SansSerif", 12, #bold);
		}
	}
}

// 5. Equipe de Segurança e Balizadores (Staff)
species staff skills: [moving] {
	saida saida_alvo <- nil;
	bool tem_lanterna <- true;
	float alcance_iluminacao <- 25.0;

	aspect padrao {
		// Halos de lanterna / iluminação residual
		draw circle(alcance_iluminacao) color: rgb(255, 255, 100, 40) border: #yellow;
		draw circle(4.0) color: #blue border: #white;
		draw "STAFF" at: location + {0, 6, 0} color: #yellow font: font("SansSerif", 10, #bold);
	}
}

// 6. Pedestres / Visitantes da Oktoberfest
species visitante skills: [moving] {
	string perfil;               // "sobrio", "idoso", "alcoolizado"
	float velocidade_base;
	float tempo_reacao;
	float capacidade_orientacao; // probabilidade de escolher o melhor portão diretamente
	rgb cor_agente;
	
	saida alvo_saida <- nil;
	bool esperando_no_portao <- false;
	int ciclos_impedidos <- 0;

	// Percepção e Decisão
	reflex decidir_saida when: alvo_saida = nil or (alvo_saida != nil and alvo_saida.status = "Bloqueada") {
		// Se o tempo decorrido for menor que o tempo de reação pessoal pós-blackout, aguarda
		if (time < tempo_reacao and blackout_ativo and not iluminacao_emergencia) {
			return;
		}

		list<saida> saidas_disponiveis <- saida where (each.status = "Aberta");
		if (empty(saidas_disponiveis)) {
			return;
		}

		// Se houver staff balizador próximo com lanterna, o pedestre é orientado para o portão do staff
		staff guia_proximo <- staff closest_to self;
		if (guia_proximo != nil and (self distance_to guia_proximo) <= guia_proximo.alcance_iluminacao and guia_proximo.saida_alvo != nil) {
			alvo_saida <- guia_proximo.saida_alvo;
			return;
		}

		// Sob blackout sem iluminação de emergência e sem staff:
		// Visitantes alcoolizados e com baixa orientação tendem a imitar o fluxo de multidão
		if (blackout_ativo and not iluminacao_emergencia and rnd(1.0) > capacidade_orientacao) {
			visitante vizinho <- one_of(visitante at_distance 20.0);
			if (vizinho != nil and vizinho.alvo_saida != nil and vizinho.alvo_saida.status = "Aberta") {
				alvo_saida <- vizinho.alvo_saida;
				return;
			}
		}

		// Caso padrão: escolher a saída aberta mais próxima geograficamente
		alvo_saida <- saidas_disponiveis with_min_of (self distance_to each);
	}

	// Movimento e Resolução de Gargalos
	reflex mover when: alvo_saida != nil and alvo_saida.status = "Aberta" {
		// Checar se já reagiu
		if (time < tempo_reacao and blackout_ativo and not iluminacao_emergencia) {
			return;
		}

		float dist <- self distance_to alvo_saida;

		// Chegada ao portão de saída
		if (dist <= 12.0) {
			// Resolução de gargalo / capacidade de vazão do portão
			if (alvo_saida.ocupacao_atual < alvo_saida.capacidade_vazao) {
				// Efetiva a passagem pelo portão
				alvo_saida.ocupacao_atual <- alvo_saida.ocupacao_atual + 1;
				
				// Atualizar registros
				if (fluxo_ciclo_saida contains_key alvo_saida.id_saida) {
					fluxo_ciclo_saida[alvo_saida.id_saida] <- fluxo_ciclo_saida[alvo_saida.id_saida] + 1;
					evacuados_por_saida[alvo_saida.id_saida] <- evacuados_por_saida[alvo_saida.id_saida] + 1;
				}
				
				// Agente com sucesso evacuado do parque
				do die;
				return;
			} else {
				// Portão saturado no ciclo (formação de fila / clogging)
				esperando_no_portao <- true;
				ciclos_impedidos <- ciclos_impedidos + 1;
				return;
			}
		}

		// Agente em trânsito
		esperando_no_portao <- false;

		// Ajuste de velocidade pela densidade local (relação de Weidmann)
		int vizinhos_aglomerados <- length(visitante at_distance 8.0);
		float fator_densidade <- 1.0;
		if (vizinhos_aglomerados > 4) {
			fator_densidade <- max(0.25, 1.0 - (vizinhos_aglomerados * 0.08));
		}

		// Efeito da visibilidade (blackout reduz a velocidade em até 40% se não houver iluminação de emergência)
		float fator_iluminacao <- 1.0;
		if (blackout_ativo and not iluminacao_emergencia) {
			fator_iluminacao <- 0.65;
		}

		speed <- velocidade_base * fator_densidade * fator_iluminacao;

		// Deslocamento direcionado à saída
		do goto target: alvo_saida.location speed: speed;
	}

	aspect padrao {
		if (esperando_no_portao) {
			draw circle(2.8) color: #red border: #white;
		} else {
			draw circle(2.0) color: cor_agente;
		}
	}
}

// ==========================================
// EXPERIMENTOS E INTERFACE GRÁFICA
// ==========================================

experiment Evacuacao_Oktoberfest type: gui {
	// Parâmetros editáveis na barra lateral do GAMA
	parameter "Número de Visitantes:" var: numero_visitantes category: "População" min: 500 max: 40000 step: 500;
	parameter "Proporção de Alcoolizados:" var: prop_alcoolizados category: "População" min: 0.0 max: 0.8 step: 0.05;
	parameter "Proporção de Idosos:" var: prop_idosos category: "População" min: 0.0 max: 0.4 step: 0.05;
	parameter "Número de Balizadores (Staff):" var: n_staff category: "Segurança e Balizadores" min: 0 max: 30 step: 5;
	parameter "Blackout Ativo:" var: blackout_ativo category: "Cenário Ambiental";
	parameter "Iluminação de Emergência:" var: iluminacao_emergencia category: "Cenário Ambiental";
	parameter "Saída Bloqueada:" var: saida_bloqueada category: "Cenário Ambiental";

	output {
		// 1. Janela Principal 3D / Espacial
		display "PVG - evacuação em 3D" type: opengl background: #black {
		
		    // Visitantes desenhados antes dos setores transparentes
		    species visitante aspect: padrao;
		
		    // Pavilhões com transparência de 75%
		    species setor aspect: visao_3d transparency: 0.75;
		
		    species obstaculo aspect: padrao refresh: false;
		    species caminho aspect: padrao refresh: false;
		    species saida aspect: padrao;
		    species staff aspect: padrao;
		}

		// 2. Gráfico de Congestionamento (Fila / Agentes impedidos)
		display "Congestionamento" refresh: every(1 #cycle) {
			chart "Agentes impedidos ou aguardando saída" type: series background: #white {
				data "Fila proxy (pessoas)" value: agentes_impedidos color: #orange marker: false style: line;
			}
		}

		// 3. Gráfico de Indicadores (Percentual de Evacuação Acumulado)
		display "Indicadores" refresh: every(1 #cycle) {
			chart "Evacuacao acumulada" type: series background: #white y_range: [0, 100] {
				data "Evacuados (%)" value: pct_evacuados color: #green marker: false style: line;
			}
		}

		// 4. Gráfico de Fluxo por Saída (Pessoas por segundo nas saídas S1 a S6)
		display "Fluxo por saída" refresh: every(1 #cycle) {
			chart "Pessoas por segundo" type: series background: #white {
				data "S1" value: fluxo_S1 color: #red marker: false style: line;
				data "S2" value: fluxo_S2 color: #blue marker: false style: line;
				data "S3" value: fluxo_S3 color: #green marker: false style: line;
				data "S4" value: fluxo_S4 color: #purple marker: false style: line;
				data "S5" value: fluxo_S5 color: #orange marker: false style: line;
				data "S6" value: fluxo_S6 color: #cyan marker: false style: line;
			}
		}

		// Monitores de barra superior / lateral (idênticos à interface dos slides)
		monitor "T95 (s: -1 se nao atingido)" value: t95;
		monitor "Evacuados (%)" value: pct_evacuados;
		monitor "Densidade maxima acumulada" value: densidade_maxima;
		monitor "T90 (s: -1 se nao atingido)" value: t90;
		monitor "Restantes" value: restantes;
		monitor "Agentes impedidos / esperando no portao" value: agentes_impedidos;
		monitor "Tempo desde o alarme (s)" value: time;
	}
}

// Experimento Batch para replicar os 4 Cenários da Aula 11
experiment Cenarios_Aula11 type: batch repeat: 5 until: (restantes <= 0 or cycle >= 3600) {
	parameter "Cenário de Saída Bloqueada" var: saida_bloqueada among: ["Nenhuma", "S2"];
	parameter "Iluminação de Emergência" var: iluminacao_emergencia among: [true, false];
}
