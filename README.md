# advogado-do-diabo

**Uma análise independente e aprofundada, ação por ação, da carteira "Top Ações" da XP, para quem
quer outra opinião antes de decidir.** Todo mês a XP publica uma carteira recomendada para o
longo prazo. Este projeto parte dela, mas não a toma como verdade: refaz a análise toda semana
com dados primários, tenta se desmentir e entrega um relatório que diz o que sabe, o que não
sabe e onde discorda.

> **Não somos filiados à XP.** Projeto independente e de código aberto, sem vínculo,
> patrocínio ou endosso da XP Investimentos. "XP" é marca de seu titular e aparece apenas para
> identificar o relatório analisado.
>
> **Não é recomendação de investimento.** As saídas são de um modelo, podem conter erros e não
> consideram o seu perfil. Leia o [aviso legal](docs/AVISO_LEGAL.md) antes de usar.

## Sobre os rótulos "comprar", "aguardar" e "evitar"

São a **classificação do modelo** para o horizonte de semanas, resultado de uma nota calculada
com regras públicas e pesos documentados. **Não são uma ordem, uma oferta nem uma recomendação
de investimento pessoal.** Eles ignoram seu perfil de risco, seu patrimônio, seus objetivos e seus
impostos, e podem estar errados. "Comprar" significa apenas "o modelo vê relação favorável entre
nota e upside nesta semana"; "evitar", o contrário. Use como mais uma opinião, confira os dados
nas fontes e, se for investir, converse com um profissional habilitado.

## O que sai para cada ação

- **Dossiê com dados da CVM:** receita, lucro e EBITDA de 12 meses, margens, ROE, dívida líquida,
  múltiplos e histórico de 4 anos, calculados dos dados abertos (DFP e ITR), com método e fonte.
- **Valuation em cenários** (bear, base e bull) e grade de sensibilidade, mais o que o preço
  embute: retorno esperado (ke implícito), crescimento implícito e ROE exigido.
- **Checklist do setor** (banco, saneamento, petróleo, mineração, software etc.), cada item com
  fonte e data, ou "pendente".
- **Nota, ação sugerida e certeza**, com prós, contras, riscos, gatilho de revisão e as objeções de
  um agente advogado, reconferidas por um auditor independente.
- **Comparação com a XP, as casas de análise e o Ibovespa**, e a medição do próprio desempenho
  das recomendações passadas (com aviso quando a amostra é pequena).

## Cruze com a sua carteira (5 minutos)

Quer saber o que o modelo acha **das ações que você já tem**? Um comando mostra, para cada uma,
a nota, a classificação do modelo e o quanto sua carteira está concentrada. Roda na sua máquina:
nada seu é enviado ao projeto.

Você precisa do [Node.js](https://nodejs.org) e do [Python 3.9+](https://www.python.org/downloads/)
instalados. Escolha um caminho.

### Caminho A: digitar suas ações (mais rápido, sem conta em lugar nenhum)

1. Crie um arquivo `minhas_acoes.csv` com uma linha por ação (quantidade que você tem):

   ```
   ticker;quantidade
   PRIO3;10
   ITUB4;5
   ```

   Dica: se tiver FIIs ou ativos que o modelo não cobre, acrescente a coluna `preco_atual`
   (`BTLG11;3;102,40`) para eles entrarem no valor total.

2. No terminal, na pasta onde salvou o arquivo:

   ```bash
   npx advogado-do-diabo@latest --csv minhas_acoes.csv
   ```

### Caminho B: puxar da corretora (Open Finance, grátis)

Feito **uma vez**; depois é um comando só. Usa o MeuPluggy, em que você mesmo autoriza a leitura:

1. **Conecte sua corretora.** Em [meu.pluggy.ai](https://meu.pluggy.ai), crie a conta e conecte a
   corretora ou o banco pelo Open Finance.
2. **Crie suas chaves.** Em [dashboard.pluggy.ai](https://dashboard.pluggy.ai), aba *Applications*,
   crie uma aplicação e copie o **Client ID** e o **Client Secret** (são seus; não compartilhe).
3. **Pegue o ID da conexão.** Na aplicação, abra a *Demo*, conecte pelo conector **MeuPluggy** e,
   no menu de três pontos, copie o **Item ID**.
4. **Salve uma vez.** No terminal:

   ```bash
   npx advogado-do-diabo@latest --configurar
   ```

   Ele pergunta Client ID, Client Secret (não aparece enquanto você digita) e Item ID, testa a
   conexão e só então salva em `~/.config/advogado-do-diabo/config.json`, com permissão só do seu
   usuário e fora de qualquer repositório.
5. **Daqui em diante é automático.** Na semana seguinte (e em todas), basta:

   ```bash
   npx advogado-do-diabo@latest
   ```

   Para apagar o que foi salvo: `npx advogado-do-diabo@latest --esquecer`. (Quem preferir não
   guardar nada em arquivo pode definir `PLUGGY_CLIENT_ID`, `PLUGGY_CLIENT_SECRET` e
   `PLUGGY_ITEM_IDS` no terminal; elas têm prioridade sobre o arquivo.)

A leitura é somente leitura: não move dinheiro nem altera nada. Limites: até 5 conexões por
pessoa, sem garantia de funcionamento (plano gratuito); o consentimento do Open Finance expira e
pode precisar ser renovado no MeuPluggy. Confira as condições em
[pluggy.ai/pricing](https://pluggy.ai/pricing).

### Seu plano (opcional)

Informe uma vez por quanto tempo pretende manter as ações (semanas, meses ou anos), seu objetivo,
quanto de queda tolera e seus limites de concentração:

```bash
npx advogado-do-diabo@latest --plano
```

Cinco perguntas curtas, salvas só na sua máquina. Daí em diante o relatório ganha a seção
**"Seu plano"**: a nota recalculada para o seu horizonte, o risco da carteira contra a queda que
você tolera e a concentração contra os seus limites. `--sem-plano` ignora o plano numa execução;
`--esquecer` apaga tudo o que foi salvo.

A nota do ranking é de **semanas**. Para meses e anos, o projeto reajusta os pesos dos mesmos
componentes (mais valuation, menos notícias e momentum); essa conversão é uma premissa do projeto,
**não validada**, e fica em [dados/horizontes.json](dados/horizontes.json). Em prazos de anos a
evidência é fraca: use os cenários de valuation do relatório e os dossiês.



Valor total, quanto cada ação pesa, nota e classificação do modelo (comprar, aguardar, evitar),
pontos de concentração por ação e por setor, e o que a carteira da XP tem e a sua não. Nada é
gravado na sua pasta; use `--salvar relatorio.md` se quiser guardar.

> É a classificação de um modelo, **não** recomendação de investimento: ignora seu perfil,
> seus objetivos e seus impostos. Leia o [aviso legal](docs/AVISO_LEGAL.md). Mais detalhes em
> [docs/MINHA_CARTEIRA.md](docs/MINHA_CARTEIRA.md).

## O que você precisa

| Quero | Preciso de |
|---|---|
| Ver o dossiê numérico (CVM, valuation, ke implícito) de uma lista de ações | Python 3.10+ e internet. **Sem Claude Code.** `python src/modo_minimo.py semana_AAAAMMDD WEGE3 ITUB4` |
| Rodar a análise completa com ranking, notícias, casas, auditoria e PDF | [Claude Code](https://claude.com/claude-code) e o PDF mensal da XP. No Claude Code: `/semana` |

Passo a passo e problemas comuns em [docs/COMO_RODAR.md](docs/COMO_RODAR.md).

## Como funciona

Cada etapa de coleta e julgamento é um agente em [.claude/agents/](.claude/agents/) (Claude Code).
Eles trocam apenas arquivos JSON dentro de uma pasta `semana_AAAAMMDD/`
(contrato em [docs/regras_comuns.md](docs/regras_comuns.md)). O que é conta é feito por scripts
em [src/](src/), não por modelo de linguagem.

| Etapa | Quem | Saída |
|---|---|---|
| Leitura do PDF (mensal) | `leitor` | `xp_mensal/AAAAMM/xp.json` |
| Coleta (semanal) | `precos`, `casas`, `noticias`, `fundamentos`, `fluxo`, `macro` | `*.json` |
| Fundamentos e dossiê | `src/coletar_cvm.py`, `src/gerar_dossie.py` | `fundamentos_cvm.json`, `dossie.json` |
| Síntese | `analista`, `risco`, `src/calcular_derivados.py` | `sintese.json`, `risco.json` |
| Crítica | `advogado`, `auditor`, `src/conferir.py` | `contra.json`, `auditoria.json`, `conferencia.json` |
| Entrega | `grafico`, `relator`, `src/montar_relatorio.py` | `graficos/`, `relatorio.pdf` |
| Diário | `monitor` | `alertas.json` |

Princípios: nenhum dado inventado (o que falta vira "não verificado"), toda informação com fonte
e data, só fontes de lista fechada, número calculável é calculado em código, e a opinião da XP
não é tratada como verdade.

## Cadência: PDF mensal, fontes semanais

- **Uma vez por mês**, quando a XP publica o PDF novo, o agente `leitor` grava
  `xp_mensal/AAAAMM/xp.json`.
- **Toda semana**, os agentes de coleta (`precos`, `casas`, `noticias`, `fundamentos`, `fluxo`,
  `macro`) buscam fontes novas dos últimos 7 dias e gravam em `semana_AAAAMMDD/`. Cada semana
  usa o `xp.json` mensal mais recente publicado até a data dela.
- `src/atualizar_historico.py` registra o ranking em `historico_carteira.json`, e a Figura 9
  compara com a semana anterior.

```
xp_mensal/202610/xp.json          # mensal
semana_20261005/*.json            # semanal: dados, análise, textos.json
semana_20261005/graficos/         # figuras e dados de cada uma
semana_20261005/relatorio.pdf
historico_carteira.json
```

## Qualidade dos dados

Número que pode ser calculado de fonte estruturada é calculado em código, não "lido" por modelo:

| Script | O que faz |
|---|---|
| `src/coletar_cvm.py` | Baixa DFP, ITR e FCA dos dados abertos da CVM e calcula receita, lucro e EBITDA de 12 meses, dívida líquida, P/L, P/VP, EV/EBITDA, ROE, payout e histórico anual de cada ticker (`fundamentos_cvm.json`). |
| `src/gerar_dossie.py` e `src/valuation.py` | Dossiê por ação: valuation de lucros descontados em cenários (premissas em `dados/premissas_valuation.json`, perfis em `dados/perfis_setoriais.json`), retorno esperado e crescimento implícitos no preço, checklist setorial preenchido pelos agentes com fonte e data. É modelo de referência, não previsão. |
| `src/regras.py` e `src/calcular_derivados.py` | Regra única de contagem de casas, mediana de preço alvo, upsides, upside ajustado e nota. O script grava os campos derivados em `casas.json` e `sintese.json` e lista o que mudou. |
| `src/atualizar_historico.py` e `src/avaliar.py` | Registram cada recomendação (nota, ação, certeza, preço, Ibovespa, versão das regras e pesos) e, quando o horizonte vence, medem o retorno contra o Ibovespa em 4 e 12 semanas por ação sugerida, certeza e posição, com correlação de postos entre nota e resultado. Sem amostra mínima (30 observações em 8 semanas) o resultado é marcado como insuficiente. |
| `src/conferir.py` | Valida cada JSON contra [schemas/](schemas/) e recalcula nota, upsides, medianas, retorno de 5 dias, beta e volatilidade de 90 pregões. Erros bloqueiam a geração do PDF. |

Limites conhecidos do cálculo da CVM (sempre sinalizados em `avisos`): EBITDA aproximado por
EBIT + depreciação da DVA; dívida sem arrendamentos; valor de mercado com preço único para ON e PN;
BDRs (como ROXO34) não têm demonstrações na CVM. Correções manuais de ticker em
[dados/mapa_tickers_manual.json](dados/mapa_tickers_manual.json).

## Código orientado a dados

Os scripts não contêm texto de análise nem tickers: leem os JSON da semana e o
`textos.json` (camada editorial escrita pelos agentes `analista`, `grafico` e `relator`).
Datas, contagens, limites de eixo, corte de compra, calendário e comparação com a semana
anterior são calculados dos dados.

## Dados e relatórios

Este repositório **não distribui** os dados nem o PDF de nenhuma semana: cada pessoa gera os
seus, a partir das fontes públicas. Há modelos dos arquivos editoriais em
[docs/modelos/](docs/modelos/) e os formatos de cada JSON estão em [schemas/](schemas/).

## Uso

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

1. **Mensal:** coloque o PDF da XP na raiz; o comando `/semana` roda o agente `leitor` e grava
   `xp_mensal/AAAAMM/xp.json`.
2. **Semanal:** no Claude Code, rode `/semana` (ou `/semana AAAAMMDD`). Ele executa os agentes de
   coleta e análise, que gravam os JSON em `semana_AAAAMMDD/` (contrato em
   [docs/regras_comuns.md](docs/regras_comuns.md)).
3. **Parte determinística**, em ordem (coleta da CVM, derivados, dossiê, conferência, avaliação,
   figuras, PDF e histórico):

```bash
python src/executar.py semana_AAAAMMDD
```

Ou passo a passo:

```bash
python src/coletar_cvm.py semana_AAAAMMDD         # fundamentos da CVM
python src/calcular_derivados.py semana_AAAAMMDD  # medianas, upsides e nota
python src/gerar_dossie.py semana_AAAAMMDD        # valuation e checklist
python src/conferir.py semana_AAAAMMDD            # conferência numérica
python src/avaliar.py semana_AAAAMMDD             # recomendações vencidas x Ibovespa
python src/gerar_graficos.py semana_AAAAMMDD      # figuras
python src/montar_relatorio.py semana_AAAAMMDD    # PDF
python src/atualizar_historico.py semana_AAAAMMDD # registra o ranking da semana
python -m unittest discover tests                 # testes offline
```

As pastas `semana_*/`, `xp_mensal/` e o `historico_carteira.json` ficam locais e são ignorados
pelo git.

## Limitações conhecidas

- A qualidade do relatório depende dos agentes: o código só renderiza o que está nos JSON.
  Se um campo faltar, a figura ou a seção mostra "não verificado" ou é omitida.
- Cotações vêm de agregadores (Yahoo Finance, brapi), não da B3 diretamente
  (ver [docs/diagnostico_acesso.md](docs/diagnostico_acesso.md)).
- O estilo visual do relatório é inspirado no PDF da XP; veja [docs/estilo_visual.md](docs/estilo_visual.md). Não somos afiliados à XP.
- O valuation é simplificado e conservador para empresas com ROE em expansão; o `ke` implícito é mais informativo que o valor justo isolado.
- Para contribuir, veja [CONTRIBUTING.md](CONTRIBUTING.md); para segurança, [SECURITY.md](SECURITY.md).

## Licença

[MIT](LICENSE) para o código. Nenhum relatório, texto editorial ou dado de terceiros é
distribuído aqui. Veja o [aviso legal](docs/AVISO_LEGAL.md).
