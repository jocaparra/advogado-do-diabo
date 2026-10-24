# Interface local

Interface web do Advogado do Diabo, para ler a semana, o dossiê, as objeções, a sua carteira, o
desempenho e a rotina. Roda só no seu computador. Não é recomendação de investimento.

```
python3 src/servidor.py            # abre em http://127.0.0.1:8765/
python3 src/servidor.py --porta 9000 --raiz CAMINHO   # outra porta ou outra pasta de semanas
```

- Front-end em `app/`: HTML, CSS e JS puros, sem build. `app/catalogo.html` mostra todos os componentes.
- Servidor em `src/servidor.py`: só biblioteca padrão, por padrão só em `127.0.0.1`. Lê a pasta `semana_*` mais
  recente (`sintese.json`, `contra.json`, `dossie.json`, `auditoria.json`...), `avaliacao.json` e
  `historico_carteira.json`.
- Visual: `app/tokens.css` é a fonte das cores, raios e fontes. Valor solto no CSS é erro.
  A fonte é a do sistema (SF Pro no Mac); não é hospedada.
- Tema: o claro é o padrão. O botão Escuro/Claro guarda a escolha neste navegador.

## Celular, tablet e web

O mesmo app se adapta à largura da janela, sem mudar de endereço e sem build:

| Largura | Layout |
|---|---|
| até 519 px (celular) | coluna única, barra de abas embaixo |
| 520 a 959 px (tablet) | mesma coluna, um pouco mais larga |
| 960 px ou mais (web) | menu lateral, aviso legal no topo, títulos em Display (34/38) e as telas de leitura em duas colunas |
| 1180 px ou mais | no Chat, painel de cartões de bot ao lado da conversa |

- O **aviso legal** fica sempre no topo (no web, na faixa acima do conteúdo), e o alternador de tema no rodapé do menu.
- O **dossiê** e as objeções continuam sem item de menu: o item ativo é a Semana, de onde se chega a eles.
- O **cartão de bot** vem da aba "Meus bots" do kit de design: avatar, nome, papel, status, tarefa, "apps" e tempo no ar.
  Aqui os "apps" são os **arquivos que o bot lê** (`casas.json`) e o "tempo no ar" é a **data dos dados**. O status mostra
  Pronto (arquivo da semana existe), Sem arquivo (âmbar: não verificado) ou Respondendo (verde pulsando). O bot ativo tem o avatar
  invertido, como no kit. Em telas menores que 1180 px, a barra de bots em fichas faz o mesmo papel.
- Decisão de tipografia: o kit usa a fonte Geist (Google Fonts); o nosso DS manda a fonte do sistema (SF Pro no Mac) e proíbe
  embutir ou hospedar fonte, então a Geist **não** foi adotada. Cores, raios e o resto seguem `tokens.css`.
- **Publicar na internet não está feito.** O servidor abre só para você (`127.0.0.1`) ou, com `--celular`, para o seu Wi-Fi com token.
  Colocá-lo numa URL pública expõe a sua carteira e o seu uso do Claude, e exigiria login, HTTPS e um limite de uso.

## Chat com os bots

A aba Chat tem um bot por agente do projeto. Cada bot responde só com o arquivo que o seu agente grava na pasta
da semana, em `src/bots.py`:

| Bot | Arquivo | Para quê |
|---|---|---|
| Analista | `sintese.json`, `dossie.json`, `xp.json`, `contra.json` | tese, nota, ação, certeza, onde discorda da XP |
| Advogado | `contra.json` | objeções, lacunas e veredito |
| Auditor | `auditoria.json`, `conferencia.json` | o que foi conferido, reprovado e corrigido |
| Fundamentos | `fundamentos.json`, `dossie.json` | indicadores e valuation |
| Casas | `casas.json` | recomendações, alvos, mediana, divergência da XP |
| Notícias | `noticias.json` | fatos recentes e eventos futuros |
| Fluxo | `fluxo.json` | momentum, volume, médias, volatilidade |
| Macro | `macro.json` | juros, câmbio, cenário político, efeito por setor |
| Risco | `risco.json` | volatilidade, beta, concentração, estresse |
| Monitor | `alertas.json` | alertas da semana |

Cada bot tem a sua conversa, e a barra no topo troca de bot. Perguntas fora do escopo recebem a indicação do bot certo.

Como responde: o servidor monta o contexto e chama `claude -p` **sem ferramentas**, fora da pasta do projeto e sem
sessão salva. Cada pergunta consome uso do seu Claude Code, uma por vez.

- O modelo só vê o contexto e cita fontes por identificador. O servidor troca o identificador pela fonte e data
  do arquivo e descarta o que não existe: uma fonte inventada não chega à tela.
- O que falta nos arquivos vira "não verificado" (tag tracejada), nunca um número. Sem o arquivo, o bot diz isso.
- Tickers citados na resposta viram link para o dossiê. O dossiê não tem aba: abre pela lista da Semana ou pelo chat,
  e o Voltar leva à aba de origem.
- A carteira só vai ao Claude se você marcar "Usar minha carteira", e só como peso, nota e ação do modelo
  (sem quantidades nem valores em reais). Vale para qualquer bot. Desligada por padrão.
- O texto dos arquivos tem conteúdo copiado da web: entra no contexto marcado como dado, não como instrução.
- Modelo padrão: `sonnet` (troque com a variável `ADV_CHAT_MODELO`). Sem o comando `claude` no PATH, o chat aparece Offline.

### Componentes de chat no sistema de design

Ficam em `app/chat.css` e aparecem em `app/catalogo.html`: barra de bots (`.bots` `.bot`), mensagem do usuário
(`.msg.u`, invertida) e do bot (`.msg.a`, superfície com borda e monograma `.av.t`), fontes da resposta (`.fontes` com
`.tag` e `.tag.nv`), indicador de escrita (`.digitando`), sugestões (`.sugestoes` com `.chip`) e campo de mensagem
(`.compor` com `.enviar`). Seguem as regras do DESIGN.md:

- Só tokens; nenhum valor de cor ou raio solto (há teste para isso).
- Os bots se distinguem por monograma, não por cor: verde, âmbar e vermelho continuam reservados.
- Link no texto é azul. Erro aparece como o aviso em âmbar (`.obj`), não como balão vermelho.
- Alvos de toque de 44 px (bot, sugestão, enviar) e movimento desligado com `prefers-reduced-motion`.
- Toda resposta mostra fonte e data, ou a tag tracejada de "sem fontes citadas" / "não verificado".

### Barra de bots e perguntas: rolagem

As duas faixas rolam na horizontal (`app/js/rolagem.js`), e cada entrada tem o seu gesto:

- **Dedo:** rolagem nativa do navegador, com alinhamento suave nos itens e sem arrastar a página.
- **Mouse:** arrastar a faixa (o cursor vira mão), roda do mouse na vertical e trackpad. Arrastar não aperta o botão
  sob o cursor; um clique parado aperta. Quando a faixa chega ao fim, a roda volta a rolar a página.
- **Teclado:** setas esquerda e direita, Home e End movem o foco entre os botões e a faixa acompanha.
- **Bordas:** esmaecem enquanto houver mais itens naquele lado.

## Mensagens agendadas

No chat, escreva um pedido com dia e hora, por exemplo **"me manda o resumo do Risco segunda às 16"**. O chat mostra
o que entendeu (dia, hora, bot e pergunta) e só agenda depois do botão **Confirmar**. No horário, o servidor roda a
pergunta no bot e avisa pela **notificação do macOS**; a resposta, com as fontes, também aparece no chat do bot
(que se abre sozinho). A lista fica na tela Rotina, onde dá para cancelar.

- O pedido é entendido em código (`src/agenda.py`), não pelo Claude: é instantâneo, não gasta uso e dá sempre a mesma data.
  Só a execução no horário usa o Claude, como qualquer pergunta.
- Entende: dias da semana (inclusive "a próxima quinta"), hoje, amanhã, depois de amanhã, "dia 25", "25/10", "23/10/2026",
  "daqui a 2 horas", "em 30 minutos", "em 3 dias às 9h"; horas como "16", "16h30", "16:30", "4 da tarde", "meio-dia".
- Recusa com explicação, em vez de adivinhar: horário que já passou, data que não existe, mais de 60 dias, "em 2 meses",
  "semana que vem", pedidos recorrentes ("toda segunda") e pedido sem horário. Frase sem pedido de envio ("quais eventos vêm
  segunda às 16?") segue como pergunta normal.
- Uma vez só, no máximo 10 ativas. A agenda fica em `~/.config/advogado-do-diabo/agenda.json` (só o seu usuário lê; sem carteira).
- **O Mac e o servidor precisam estar ligados.** Se o horário passar com o servidor desligado, a mensagem roda ao ligar,
  marcada como atrasada, até 12 horas depois; depois disso fica como perdida e não é enviada.
- O texto da notificação segue como argumento do `osascript`, nunca dentro do script: resposta com aspas ou comandos não executa nada.
- `ADV_SEM_NOTIFICAR=1` silencia a notificação (a resposta continua no chat).

## Testar no celular

```
python3 src/servidor.py --celular
```

Abre o servidor para o Wi-Fi e imprime uma URL com um token aleatório (novo a cada execução), por exemplo
`http://192.168.x.x:8765/?k=...`. Abra essa URL no celular, ligado no mesmo Wi-Fi. O token vira um cookie e some
da barra de endereço. Sem o token, o servidor responde 401 e não entrega dado nenhum.

- A rede local usa HTTP sem criptografia: use só em rede de confiança (nada de Wi-Fi público).
- O token dá acesso à sua carteira e ao botão de rodar a semana. Não compartilhe a URL.
- Sem `--celular`, o servidor só atende o próprio computador.
- Se o celular não abrir, confira o firewall do Mac e se o Wi-Fi não isola aparelhos (rede de visitantes).

## Regras que a interface segue

- Dado ausente aparece como "não verificado" ou "pendente", tracejado e âmbar. Nada é preenchido.
- Toda informação traz fonte e data. O que vem de agente, sem CVM, diz isso na tag.
- Comprar, Aguardar e Evitar são rótulos do modelo. O aviso fica na tela da semana, e o aviso legal no topo.
- Texto dos arquivos nunca vira HTML: tudo passa por escape.

## Privacidade

- O CSV da carteira é lido pelo servidor e fica só em memória. Não é gravado em disco por aqui.
  O botão "Esquecer" apaga da memória.
- O plano usa o mesmo arquivo privado de `src/plano.py` (`~/.config/advogado-do-diabo/plano.json`).
- Se existir `minha_carteira.json` na pasta da semana (gerado por `src/minha_carteira.py`, não versionado),
  a tela mostra esse arquivo enquanto nada for importado.
- A API só responde ao próprio `127.0.0.1`/`localhost`. Escritas exigem o cabeçalho `X-Adv` e mesma origem.

## Rotina semanal

O botão "Rodar semana" só dispara depois de uma confirmação na tela e roda `claude -p "/semana AAAAMMDD"`
(uma por vez, log em `.cache/rotina.log`). Isso aciona os agentes de verdade: leva tempo, usa a web e
consome o seu uso do Claude Code. O progresso vem dos arquivos que aparecem na pasta da semana.

## Escolhas de interface (não vêm do modelo)

- Nota: verde a partir de 7, âmbar a partir de 4, vermelho abaixo. É só leitura visual, não é regra do modelo.
- "Discorda" compara a ação sugerida com o rating da XP (Compra = comprar, Neutro = aguardar, Venda = evitar).
- Gráfico de desempenho: média das recomendações Comprar por semana de recomendação, contra o Ibovespa.
  O CDI só entra quando houver série; hoje aparece "não verificado".
- Concentração por setor usa fg, azul, cinza e linha, para não gastar verde, âmbar e vermelho como decoração.

## Testes

`python3 -m unittest tests.test_servidor tests.test_interface_js` (dados sintéticos, sem rede). O segundo roda
`tests/js/interface.test.mjs` em Node (tema, escape de HTML, componentes, CSS sem cor solta) e pula se não houver
Node 22.7 ou mais novo. A suíte completa: `python3 -m unittest discover tests`.
