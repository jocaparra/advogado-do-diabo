# Aviso legal

**Leia antes de usar.**

1. **Não somos filiados à XP.** Este projeto é independente. Não tem vínculo, patrocínio ou
   endosso da XP Investimentos nem de qualquer casa de análise citada. "XP" e os nomes das demais
   instituições são marcas de seus titulares e aparecem apenas para identificar os documentos
   analisados e as fontes.
2. **Não é recomendação de investimento.** Os rótulos "comprar", "aguardar" e "evitar" são a
   classificação do modelo, não uma ordem nem uma oferta. Os resultados (notas, rótulos,
   preços justos, cenários) são saídas de um modelo e de agentes de linguagem, com premissas
   explícitas. Não consideram seu perfil, patrimônio, objetivos ou tributos e não substituem um
   profissional habilitado. A classificação do modelo não é uma ordem nem uma oferta.
3. **Pode conter erros.** Dados vêm de fontes públicas e de agregadores, e parte do texto é gerado
   por modelo de linguagem. Há uma conferência numérica em código, mas ela não cobre tudo. Todo dado
   relevante deve ser conferido na fonte antes de qualquer decisão.
4. **Desempenho passado e modelos não garantem resultado.** O projeto mede o próprio desempenho
   contra o Ibovespa (`avaliacao.json`); com amostra pequena o resultado não é evidência.
5. **Sem garantia.** O código é distribuído sob licença MIT, "como está". Nenhum autor responde por
   perdas decorrentes do uso.
6. **Direitos de terceiros.** O repositório não distribui relatórios, textos editoriais nem dados
   de terceiros. Quem usar o projeto obtém os dados das fontes e responde pelo uso conforme os
   termos de cada uma. Se você é titular de algum conteúdo e quer que algo seja removido, abra uma issue.
7. **Regulação.** Quem publicar relatórios derivados deste projeto para terceiros deve verificar a
   regulamentação aplicável à divulgação de análises de valores mobiliários no seu país (no Brasil,
   a da CVM). Este repositório não presta esse serviço.

## Plano do usuário

A leitura "no seu horizonte" usa pesos definidos pelo projeto (`dados/horizontes.json`), sem
validação estatística. Ela reordena a nota semanal do modelo; não é recomendação personalizada,
não considera seu patrimônio total, impostos, liquidez ou objetivos além dos informados, e pode
estar errada. Prazos de anos estão fora do que o modelo semanal foi desenhado para medir.
