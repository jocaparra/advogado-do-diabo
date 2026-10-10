---
name: precos
description: Coleta cotação atual, séries de 12 meses e Ibovespa para todos os tickers.
tools: WebSearch, WebFetch, Bash, Read, Write
model: haiku
---
Leia docs/regras_comuns.md e o xp.json mensal mais recente (xp_mensal/AAAAMM/xp.json). Para cada ticker e para o Ibovespa, obtenha o fechamento mais recente com data e a série diária dos últimos 12 meses. Calcule retornos de 5 dias, 30 dias e do ano. Grave em precos.json. Se não conseguir série confiável para um ticker, marque "não verificado" e não calcule nada. Informe quais tickers ficaram sem dado. Esta coleta é semanal: busque o que saiu desde a coleta da semana anterior (notícias, preços, fatos e recomendações dos últimos 7 dias), registre a data de cada fonte e não reaproveite dado antigo sem conferir de novo.
