# Estratégia quantitativa (universo amplo, fatores e medição)

Trilha **paralela** ao ranking semanal da carteira da XP. Não altera nota, pesos nem relatório da semana:
produz uma carteira própria, calculada só em código (sem LLM), e a mede contra o Ibovespa e o CDI.
**Não é recomendação de investimento.** Leia o [aviso legal](AVISO_LEGAL.md).

## Por que existe

O ranking semanal ordena os ~14 papéis que a XP já escolheu, com uma nota em que três de cinco componentes
são julgamento e os pesos são convenção. Não havia como saber, no passado, se a nota previa alguma coisa.
Esta trilha calcula fatores com dados conhecidos em cada data e mede o resultado da própria carteira.

## Fluxo

| Etapa | Script | O que faz |
|---|---|---|
| Dados | `src/quant_dados.py` | Composição do IBrX 100 (B3), preços com proventos (Yahoo), CDI (BCB) e fundamentos da CVM por data de recebimento (point-in-time) |
| Fatores | `src/fatores_quant.py` | valor (E/P e B/P), qualidade (ROE), momentum 12-1, dividendos e baixa volatilidade, em postos 0 a 1 |
| Pesos | `dados/pesos_quant.json` | Proposta de pesos e mistura com a nota da XP (status `proposta`) |
| Carteira | `src/carteira_quant.py` | 12 melhores, pesos iguais, até 3 por setor. Salva o retrato em `aprendizado/quant/` |
| Medição | `src/medir_quant.py` | Retorno total em 3, 6 e 12 meses de cada retrato contra Ibovespa e CDI |

```bash
python src/carteira_quant.py --semana semana_AAAAMMDD   # carteira de hoje + nota reponderada dos papéis da XP
python src/medir_quant.py                         # mede os retratos vencidos
```

Rode `carteira_quant.py` uma vez por mês: cada retrato vira uma observação para a medição.

## Governança

Seguindo [APRENDIZADO.md](APRENDIZADO.md): `dados/pesos_quant.json` está como `proposta` e nada aqui muda o
ranking semanal sem aprovação explícita. O que se faz é rodar a carteira em paralelo e medir.
Um critério razoável de promoção: pelo menos 12 retratos mensais vencidos em 6 meses, com excesso médio
positivo contra o Ibovespa e acima do universo.

