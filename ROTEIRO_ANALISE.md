# Roteiro: uma análise que você consegue explicar

Material preparado com assistência de IA. Não é um diário retroativo nem comprovação de trabalho manual. Os campos de interpretação do Excel ficam vazios para você trabalhar, não para simular autoria.

## 1. Qual é a pergunta?

**Como os rótulos históricos se distribuem na base e em um recorte?**

Não vamos construir um detector de fraude. O rótulo já existe na base; os gráficos descrevem associações. A versão publicada trabalha com **10.000 linhas**, das quais **453** têm rótulo de fraude. A ampliação para 17.880 linhas foi preparada separadamente, mas não publicada: não use seus números para explicar esta planilha.

## 2. O que é dado, transformação e apresentação?

| Etapa | Onde conferir | Limite |
| --- | --- | --- |
| Campos de entrada preservados no SQLite | `employment_type`, `required_experience`, `industry`, `fraudulent` | Já pertencem à base histórica tratada; não são raw original comprovado. |
| Campos derivados | Notebook, seção Entrada → regra → saída | Ausentes viram Não Informado em categorias; flags viram 0/1 ou rótulos legíveis. Não se recupera texto perdido antes do histórico. |
| Base tratada | Jobs_Data.xlsx | 31 colunas, sem fórmulas ou gráficos. Não confundir com dados brutos. |
| Contas e interpretação | Jobs_Database.xlsx → Passo_a_passo | Fórmulas e valores salvos são gerados; interpretação e execução manual precisam ser suas. |
| Comparação visual | Dashboard no Excel e painel web | Filtros e população precisam ser iguais para comparar resultados. |

## 3. Faça a primeira conta no Excel

Abra **Jobs_Database.xlsx** no Microsoft Excel com cálculo automático e selecione **Passo_a_passo**.

| Célula | Conta | Resultado desta versão |
| --- | --- | --- |
| C7 | CONT.VALORES dos IDs | 10.000 |
| C8 | SOMA da flag de fraude | 453 |
| C9 | C8 / C7 | 4,53% |

Selecione as células para inspecionar as fórmulas. Para praticar de verdade, duplique a aba, apague C7:C15 e redigite as fórmulas, sem colar valores. Nomes no arquivo são internacionais: COUNTA, SUM, COUNTIFS, SUMIFS, IFERROR. O Excel pode mostrá-los como CONT.VALORES, SOMA, CONT.SES, SOMASES e SEERRO; o separador depende da configuração local.

A unidade é a **linha/anúncio da base**, não a pessoa e não necessariamente um anúncio único. Se não houver observações, a fórmula didática mostra 0 por IFERROR; escreva “sem observações”, não “risco zero”.

## 4. Compare sem trocar o denominador

O exemplo é **Logo = Não E Remoto = Sim**, mantendo os demais filtros em Todos:

- C12: CONT.SES para as duas condições → **120** linhas.
- C13: SOMASES da flag com as mesmas condições → **26** rótulos.
- C14: 26 / 120 → **21,67%**.
- C15: (26 / 120 − 453 / 10.000) × 100 → **17,14 pontos percentuais** acima da base.

A diferença não demonstra que ausência de logo ou trabalho remoto causam fraude. O grupo é pequeno, pode misturar países e setores e não foi selecionado aleatoriamente. Não filtre Status = Fraudulenta para comparar risco: uma taxa de 100% seria consequência da seleção do próprio rótulo.

Na aba Dashboard, configure Logo em **F9 = Não** e Remoto em **J9 = Sim**, com **B6/F6/J6/B9 = Todos**. Os três indicadores devem coincidir com C12:C14. As contas em Passo_a_passo são fixas sobre a base completa e independentes dos filtros. Os filtros da tabela Base_Interativa_Vagas também são independentes do Dashboard.

## 5. Escreva, não apenas copie

Preencha os três espaços amarelos de Passo_a_passo:

1. Qual foi sua pergunta e qual o numerador/denominador da resposta?
2. Qual explicação alternativa existe e o que não pode ser concluído?
3. Qual outro recorte você testou? Registre todos os filtros e a evidência.

Não há conclusão pessoal pronta. Uma frase defensável precisa indicar a base histórica, os filtros, a quantidade de observações e a limitação. Revise o conteúdo e siga as regras de atribuição da instituição.

## 6. Confira com Python

Execute o notebook em ordem na raiz do projeto. Ele mostra exemplos reais de campos de entrada e derivados, valida as regras em todas as linhas e compara as duas contas com a base usada no Excel. Esse antes/depois é **da derivação de campos**, não uma alegação de recuperação da limpeza raw original.

Para reconstruir o Excel: `pip install -r requirements-dev.txt` e `python scripts/build_workbook.py`.

## 7. O que foi testado e o que ainda é manual?

Os testes recalculam fórmulas em motor Python e verificam resultados, recortes e arquivos. Isso não substitui abrir a planilha no Microsoft Excel e testar a interface nativa. O notebook identifica a assistência de IA. Os workflows antigos do GitHub Actions continuam uma pendência separada; teste local aprovado não significa CI remoto aprovado.
