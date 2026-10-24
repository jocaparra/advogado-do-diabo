# Minha carteira x ranking

Cruza as ações que **você** tem com a classificação do modelo da semana: peso, setor, nota,
upside, concentração e o que a carteira da XP tem e a sua não. Tudo roda na sua máquina; nada é
enviado a servidor do projeto, e suas chaves e posições não são gravadas em arquivo versionado.

> Não é recomendação de investimento. A classificação é do modelo e ignora seu perfil, seus
> objetivos e seus impostos. Leia o [aviso legal](AVISO_LEGAL.md).

## Rodar (um comando)

Com Node.js e Python 3.9+ instalados, sem clonar nada:

```bash
npx advogado-do-diabo@latest --csv minhas_posicoes.csv
```

Ele baixa o ranking publicado da semana, cruza com as suas posições e imprime o relatório. Nesse
modo nada é gravado em disco (use `--salvar relatorio.md` se quiser guardar). Com o repositório
clonado, o equivalente é:

```bash
python src/minha_carteira.py
```

Sem argumentos usa a semana mais recente e as posições do MeuPluggy (se as variáveis `PLUGGY_*`
estiverem definidas) ou de `entrada/posicoes.csv`. Opções:

```bash
python src/minha_carteira.py --csv minhas_posicoes.csv
python src/minha_carteira.py --pluggy
python src/minha_carteira.py --pluggy-json resposta.json   # JSON de /investments já salvo, sem credenciais nem rede
python src/minha_carteira.py --semana semana_20261005
python src/minha_carteira.py --ranking https://.../ranking.json --salvar relatorio.md
```

O relatório é impresso no terminal e salvo em `semana_*/minha_carteira.md` (fora do git).
Só usa a biblioteca padrão do Python 3.9+.

**No Claude Code**, `/minha-carteira` roda o mesmo comando e comenta o resultado com base no
relatório da semana.

## Duas formas de informar suas posições

### 1. CSV (mais simples, sem conta em lugar nenhum)

Cole ou envie um arquivo com as colunas `ticker` e `quantidade` (opcionais: `preco_medio`,
`preco_atual`):

```
ticker;quantidade;preco_medio
PRIO3;100;42,10
ITUB4;200;30,50
```

### 2. MeuPluggy (leitura automática via Open Finance, grátis para uso pessoal)

Feito uma vez:

1. Em [meu.pluggy.ai](https://meu.pluggy.ai), crie a conta e conecte sua corretora ou banco.
2. Em [dashboard.pluggy.ai](https://dashboard.pluggy.ai), aba **Applications**, crie uma aplicação.
   Copie o **Client ID** e o **Client Secret**.
3. Na aplicação, abra a **Demo**, conecte pelo conector **MeuPluggy** e, no menu de três pontos,
   copie o **Item ID**.

Salve uma vez e depois é automático:

```bash
python src/minha_carteira.py --configurar     # ou: npx advogado-do-diabo@latest --configurar
python src/minha_carteira.py                  # nas próximas vezes, só isso
```

A configuração fica em `~/.config/advogado-do-diabo/config.json` (permissão 0600, fora de
qualquer repositório); `--esquecer` apaga. As variáveis `PLUGGY_CLIENT_ID`,
`PLUGGY_CLIENT_SECRET` e `PLUGGY_ITEM_IDS` têm prioridade sobre o arquivo.

A leitura é somente leitura: o programa não move dinheiro nem altera conexões. O plano gratuito
do MeuPluggy permite até 5 conexões ativas por titular e não tem SLA.

Cuidados: o Client Secret dá acesso de leitura aos seus dados; não o compartilhe nem o coloque
em arquivo versionado. O período de teste do dashboard pode limitar a criação de novas
conexões; confirme as condições atuais em [pluggy.ai/pricing](https://pluggy.ai/pricing).

## Seu plano

```bash
python src/minha_carteira.py --plano     # ou: npx advogado-do-diabo@latest --plano
```

Perguntas: horizonte (semanas, meses, anos), objetivo (crescimento, renda, preservação), queda
máxima tolerada, limite por ação e por setor. Fica em `~/.config/advogado-do-diabo/plano.json`
(permissão 0600). Com o plano salvo o relatório:

- **recalcula a nota** com os pesos do seu horizonte (`dados/horizontes.json`; premissa do
  projeto, não validada) e mostra a ordem entre as suas ações;
- compara a **volatilidade da carteira** (limite superior, média ponderada) com a queda que você
  tolera, escalada pelo prazo (vol x raiz do prazo, 1 desvio-padrão);
- usa **os seus limites** de concentração, no lugar dos padrões (25% por ação, 40% por setor);
- em `anos`, avisa que a evidência do modelo semanal é fraca e mostra as margens dos cenários de
  valuation (bear, base, bull), quando o ranking publicado as traz.

Não indica o que comprar, vender nem quanto aportar. O modelo não mede dividendos, então o
objetivo "renda" não altera a nota (o relatório avisa).

## De onde vem o ranking

- **Quem só usa:** o comando baixa `publico/ranking.json` do repositório, publicado por quem
  mantém o projeto. Só tem posição, setor, nota, classificação, certeza, cotação e upside ajustado.
- **Quem mantém:** roda a análise semanal (`/semana` no Claude Code) e publica o ranking com
  `python src/publicar_ranking.py semana_AAAAMMDD` (grava `publico/ranking.json`).
- Se houver uma pasta `semana_*` local, ela tem prioridade.

`entrada/`, `semana_*/`, `.env` e `posicoes*.csv` já estão no `.gitignore`.
