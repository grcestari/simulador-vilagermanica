/**
 * Modelo: evacuacao
 * Descrição: Simulação de Evacuação no Parque Vila Germânica (Oktoberfest de Blumenau)
 * Autores: Gabriel Cestari e Thomas Haskel
 * Disciplina: Optativa I (Simulação) - Prof. Dr. Marcos Mattedi (FURB)
 * Módulo III: Simulação Baseada em Regras - Aula 13 (Dados + GAMA)
 */

model evacuacao

import "Oktoberfest_Evacuacao_3D.gaml"

// Este arquivo estende e disponibiliza o experimento padrão de evacuação
experiment Simulacao_Evacuacao parent: Evacuacao_Oktoberfest {
}
