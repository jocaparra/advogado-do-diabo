# Objetivo da carteira (leia primeiro)

Este arquivo fixa **para que o projeto existe**. Antes de mudar código, regra ou análise, confira se
a mudança serve a este objetivo. Em caso de dúvida, vale o que está aqui.

## Objetivo

Ter uma **segunda opinião independente e honesta** sobre a carteira "Top Ações" da XP e sobre as
ações que eu realmente tenho, para decidir melhor no **longo prazo**, sem tomar a XP (nem o próprio
modelo) como verdade.

Isso se desdobra em três frentes:

1. **Ranking semanal (advogado do diabo):** refazer a análise ação por ação com dados primários
   (CVM, preços, casas, notícias), tentar se desmentir e dizer o que se sabe, o que não se sabe e onde
   se discorda da XP.
2. **Minha carteira:** cruzar as posições que eu tenho (CSV ou MeuPluggy) com o ranking: nota,
   concentração, setor, o que a XP tem e eu não. Tudo local.
3. **Trilha quantitativa (DEVIL):** uma carteira de regras fixas (5 fatores), calculada só em código,
   medida contra o Ibovespa e o CDI, para saber **se o ranking prevê alguma coisa**. É paralela e não
   altera o ranking.

## Princípios (não negociáveis)

- **Melhorar com validação, nunca ajustar ao passado.** Regras congeladas antes de testar; contar as
  tentativas; resultado só vale se aguentar as duas metades da amostra e fora da amostra.
- **Honestidade sobre incerteza.** Amostra pequena, dado faltando ou fonte fraca aparecem no texto,
  não são escondidos. Sem número inventado: sem dado, "pendente".
- **Não é recomendação de investimento.** "Comprar/aguardar/evitar" é classificação do modelo, não
  ordem. O [aviso legal](AVISO_LEGAL.md) vale sempre.
- **Independência:** sem vínculo com a XP; "XP" só identifica o relatório analisado.
- **Privacidade:** posições, chaves da Pluggy, backtests e comparações **nunca** vão para o
  GitHub. Ficam em `entrada/`, `aprendizado/`, `semana_*/` e nos arquivos locais já ignorados.
- **Commits são manuais:** quem commita sou eu, no VS Code. Nada de commit automático.

## O que NÃO é objetivo

- Prever o mercado no curto prazo ou fazer trading.
- Substituir um profissional habilitado ou considerar meu perfil, patrimônio e impostos.
- Otimizar o backtest até ele parecer bom.

## Onde está cada coisa

| Assunto | Arquivo |
|---|---|
| Visão geral e uso | [README.md](../README.md) |
| Como rodar a semana | [COMO_RODAR.md](COMO_RODAR.md) |
| Cruzar minha carteira | [MINHA_CARTEIRA.md](MINHA_CARTEIRA.md) |
| Trilha quantitativa | [QUANT.md](QUANT.md) |
| Regras comuns dos agentes | [regras_comuns.md](regras_comuns.md) |
| Aviso legal | [AVISO_LEGAL.md](AVISO_LEGAL.md) |

## Estado e próximos passos

- Ranking semanal e cruzamento com a minha carteira: funcionando.
- Avaliação e aprendizado: retorno total contra o Ibovespa, exclusões e versão do código registradas, propostas
  revalidadas, versões com hash e frequência observada por nível de certeza. Calibrar a certeza como probabilidade
  e testar pesos continuam dependendo de amostra.
- Trilha quantitativa: em validação. Próximo: três testes pré-registrados (teto de 25% por setor,
  peso por capitalização, bandas de rebalanceamento) e **não mexer antes de 6 retratos mensais
  reais** (rodar `carteira_quant.py` todo mês e medir com `medir_quant.py`).

_Se o objetivo mudar, altere este arquivo primeiro e depois o código._
