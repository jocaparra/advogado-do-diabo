---
description: Cruza a sua carteira (MeuPluggy/Open Finance ou CSV) com o ranking da semana e comenta o resultado
argument-hint: "[--csv arquivo | --pluggy] [--semana pasta]"
---
Rode `python src/minha_carteira.py $ARGUMENTS` (sem argumentos ele usa a semana mais recente e as
posições de `PLUGGY_*` ou de `entrada/posicoes.csv`). Se faltar a pasta da semana ou as posições,
diga o que falta e pare; não invente dado.

Depois de ler a saída (e `minha_carteira.json`, se precisar do detalhe), responda em até 12 linhas:

1. Foto da carteira: valor, número de posições, cobertura do ranking e nota média ponderada.
2. Onde ela mais se afasta do ranking da semana (posições em "aguardar"/"evitar" com peso alto,
   alvos "comprar" ausentes) e os pontos de concentração sinalizados.
3. O que o relatório da semana (`sintese.json`: divergências, riscos, lacunas) diz sobre as
   posições de maior peso, citando apenas o que está lá.
4. Itens fora do ranking ou sem preço: liste, sem opinar sobre eles.

Regras: isto é uma leitura da classificação do modelo, **não recomendação de investimento
personalizada**; não diga "compre", "venda" nem "reduza", descreva o que o modelo indica e as
incertezas. Termine lembrando que ignora perfil, objetivos e impostos. Não imprima chaves nem
IDs da Pluggy, não comite, não publique e não envie nada para fora.
