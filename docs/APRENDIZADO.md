# Aprendizado contínuo

O projeto mede as próprias recomendações contra o que aconteceu e guarda o que aprendeu. **Isto não é
treinamento de um modelo de Machine Learning**: com poucas semanas de dados, um modelo só decoraria ruído.
O que existe é registro, avaliação, memória com grau de validação e uma calibração conservadora que fica
fechada até haver amostra.

Nada aqui altera nota, peso ou regra sozinho. Toda mudança passa por proposta, validação fora da amostra e
a sua aprovação explícita, e vira uma nova versão que pode ser revertida.

## Ciclo

1. **Registrar** (`atualizar_historico.py`): ranking, componentes da nota, previsões (comprar = acima do
   Ibovespa, evitar = abaixo, aguardar = neutra), conclusões e versão das regras.
2. **Avaliar** (`avaliar.py`): retorno contra o Ibovespa em 1, 4 e 12 semanas. Cada previsão vira `acerto`,
   `erro`, `neutro_confirmado`, `oportunidade_perdida` ou `queda_evitada`. A faixa de "neutro" (3, 6 e 10 pp)
   é convenção, não calibrada.
3. **Feedback** (`feedback.py`): suas correções e comentários, só acrescentados, sempre `nao_validado`.
4. **Memória** (`memoria.py`): fato, preferência, experiência, hipótese e conclusão validada. Uma conclusão só
   nasce de `promover`, com ≥ 30 observações, ≥ 3 semanas independentes e `--aprovado-por usuario`.
5. **Aprender** (`aprender.py`): portão de amostra, erros recorrentes, proposta de pesos, versões, verificação
   de regressão e rollback.
6. **Retrospectivas** (`aprendizado/retrospectivas/`): leitura de uma semana contra fechamentos posteriores,
   schema em `schemas/retrospectiva.schema.json`.

## Comandos

```bash
python src/aprender.py fase <pasta_da_semana>        # em que fase os dados permitem estar e o que falta
python src/aprender.py relatorio <pasta_da_semana>   # portão, vereditos e erros recorrentes
python src/aprender.py propor <pasta_da_semana>      # só gera proposta se o portão abrir e houver ganho
python src/aprender.py aplicar <pasta> --proposta ID --aprovado-por usuario
python src/aprender.py verificar <pasta_da_semana>   # compara com a versão anterior, sugere rollback
python src/aprender.py reverter --para 1
python src/feedback.py add --semana 2026-10-05 --tipo correcao --ticker TOTS3 --texto "..."
python src/memoria.py buscar --tag regime_eleicao
```

## Fases

| Fase | Quando | O que faz |
|---|---|---|
| 1 | sempre | coleta, memória contextual, retrospectivas |
| 2 | ≥ 30 observações vencidas com componentes, em ≥ 8 semanas | calibração dos 5 pesos, ±5 pp por peso, validada fora da amostra |
| 3 | ≥ 200 observações em ≥ 52 semanas (convenção) | modelo mais flexível, só com validação walk-forward e comparação com a versão anterior |

O aprendizado mede o resultado em 1 semana por padrão (`--horizonte 1_semana`), o que devolve o primeiro
retorno em 7 dias e abre a Fase 2 com ~9 semanas de histórico. Em 4 semanas são ~12, em 12 semanas ~20. Prazo
mais curto chega antes, mas cada observação carrega mais ruído; use `--horizonte 4_semanas` para um
veredito mais estável.

## Limites

- Os 14 papéis de uma semana compartilham fatores (juros, câmbio, eleição): 14 observações valem bem menos
  que 14 amostras independentes.
- O retorno é total (preço mais dividendos e JCP por data ex, sem reinvestimento), comparável ao Ibovespa de
  retorno total. Observação sem proventos conhecidos até o fim da janela fica só com preço e marca a avaliação
  como incompleta (`aviso_proventos`). Parte dos proventos vem de fonte única (Yahoo), sem conferência.
- Só os pesos da nota são aprendidos. O desconto do rali e o corte de compra ainda não.
- A memória e as propostas ficam em `aprendizado/` (local, fora do git). Os parâmetros versionados ficam em
  `dados/parametros_aprendidos.json`, criado só na primeira aplicação aprovada.
