# ESTILO VISUAL: IRMÃO DO PDF DA XP

O estilo é inspirado no relatório da XP para facilitar a comparação lado a lado. O projeto não é afiliado, patrocinado nem endossado pela XP Investimentos; "XP" é marca de seu titular e aparece apenas para identificar o relatório analisado.


Formato da página
• Paisagem, proporção 16 por 9, uma ideia principal por página.
• Cabeçalho em faixa preta no topo, título em amarelo ouro, subtítulo em branco, data no canto direito.
• Rodapé em toda página com fonte dos dados, data de corte e número da página.

Paleta
• Amarelo ouro #FFB800: cabeçalhos de tabela, destaques e série do agente.
• Preto #000000: cabeçalho de página e títulos.
• Cinza médio #7F7F7F: série do Ibovespa e dados de referência.
• Cinza claro #F0F0F0: caixas de resumo e linhas alternadas.
• Verde #2E7D32, amarelo de alerta #F9A825, vermelho #C62828: usados só para sinalizar recomendação, alerta e variação positiva ou negativa.

Tabelas: cabeçalho amarelo com texto preto em negrito, corpo branco, números à direita, negativos em vermelho e positivos em verde.

Gráficos: fundo branco, grade horizontal cinza clara, sem bordas pesadas, título em cima no formato "Figura N: descrição", legenda sempre visível, valores escritos nas barras e no ponto final das linhas, eixos com unidade. Cada gráfico tem uma frase de leitura logo abaixo, dizendo o que mostra e por que importa para a decisão.

Tipografia: sem serifa, mínimo de 9 pontos, nada cortado nem sobreposto.

FIGURAS OBRIGATÓRIAS (agente de origem entre parênteses)

Figura 1 (precos e xp): Carteira XP contra Ibovespa em base 100, últimos 12 meses, linha amarela e linha cinza. Ao lado, tabela de retornos: semana, mês, 2026, 12 meses, desde o início.
Figura 2 (analista): ranking em barras horizontais da melhor para a pior, nota de 0 a 10, cor pela ação sugerida (verde comprar, amarelo aguardar, vermelho evitar), certeza ao lado. Rodapé: a nota serve para ordenar e não é probabilidade.
Figura 3 (precos e casas): upside em barras agrupadas por ticker: até o preço alvo da XP, até a mediana das outras casas e o ajustado pelo agente. Tabela ao lado com preço atual, preço alvo e data da cotação.
Figura 4 (casas): barras empilhadas de compra, neutro e venda por ticker, com marcador para o rating da XP. Só com pelo menos 3 casas verificadas. Senão, "dado insuficiente".
Figura 5 (fluxo e precos): retorno em 5 dias, 30 dias e 2026 de cada ticker contra a linha do Ibovespa.
Figura 6 (risco): dispersão de upside ajustado contra risco (volatilidade de 90 dias ou beta), tamanho do ponto pela certeza, rótulo com o ticker.
Figura 7 (xp e analista): exposição setorial em barras agrupadas: peso do setor no Ibovespa, peso na carteira da XP e peso do conjunto de ações que o agente classificou como comprar.
Figura 8 (macro): pequenos gráficos dos últimos 3 meses para juros, dólar, Brent, Ibovespa e fluxo estrangeiro, com uma linha por indicador sobre o efeito na carteira.
Figura 9 (analista e histórico): mudança de posição no ranking contra a semana anterior. Primeira execução: "primeira execução, sem comparação".
Figura 10 (macro e noticias): calendário de catalisadores das próximas 4 semanas, marcando a ação afetada.
Tabela de alertas: nível (bolinha colorida), ticker, fato, fonte, data, impacto esperado, ação recomendada.
Tabela de resumo por ação: ticker, setor, preço atual, preço alvo XP, upside, rating XP, consenso das casas, nota do agente, ação sugerida, certeza.

REGRAS DE DADOS DOS GRÁFICOS
1. Todo ponto vem de fonte verificável e com data.
2. Se não houver série confiável, não gere o gráfico. Escreva no lugar: "Gráfico não gerado: dado não verificado", com o motivo.
3. Todo gráfico tem rodapé com fonte e data de corte no mesmo formato do PDF da XP.
4. Upside sempre mostra preço atual e data da cotação.
5. Guarde os dados de cada gráfico em graficos/ para auditoria.
6. Figuras que dependem de agente inativo na ETAPA escolhida saem como "não gerado nesta etapa".

ESTRUTURA DO PDF
Página 1: resumo executivo em caixa cinza clara (máximo 10 linhas): visão do mercado, mudanças contra o relatório anterior, 3 principais conclusões. Ao lado, Figura 1.
Página 2: painel macro (Figura 8) e leitura do cenário.
Página 3: ranking completo (Figura 2) com tabela de ação sugerida, nota, upside, principal motivo.
Página 4: upside e consenso (Figuras 3 e 4).
Página 5: desempenho e risco (Figuras 5 e 6).
Página 6: exposição setorial (Figura 7) e riscos da carteira como um todo.
Página 7: mudanças no ranking (Figura 9) e calendário (Figura 10).
Páginas seguintes: análise de cada ação na ordem do ranking, uma por página, com tabela de resumo, tese, pros, contras, catalisadores, riscos, gatilho de revisão, fontes com data.
Página de divergências com a XP: onde o agente discorda e por quê, lado a lado.
Página de objeções do advogado e resultado da auditoria.
Página de alertas.
Última página: lacunas (incluindo o diagnóstico de acesso) e lista de fontes.
