# Gastos parlamentares dos senadores - CEAPS

Projeto da disciplina IMD1151 - Ciência de Dados (UFRN) para investigar padrões nos gastos da Cota para o Exercício da Atividade Parlamentar dos Senadores (CEAPS).

**Grupo:** 
- Gabriel Ferreira Cavalcante
- Jordson Albino Galvão Tavares 
- Rafaela Thais de Abreu Lúcio Maia.

## Dados e execução

A fonte principal é o [Portal de Dados Abertos do Senado Federal](https://adm.senado.gov.br/adm-dadosabertos/swagger-ui/index.html). O notebook coleta os CSVs anuais da CEAPS de **2008 a 2025**; 2026 não integra este recorte. Os arquivos baixados ficam em `dados_cache/` para reutilização.

Na pasta do projeto, instale as dependências com `python -m pip install -r requirements.txt`. Execute primeiro as células de coleta da CEAPS no notebook para criar os CSVs em `dados_cache/`. Depois, execute `python coletar_senadores.py` para consultar os códigos desses CSVs. O script salva os JSONs em `dados_senadores/`, reutiliza arquivos válidos e registra falhas em `dados_senadores/resumo_coleta.json`. Se a coleta for interrompida, execute o mesmo comando novamente. Por fim, reinicie o kernel e execute todas as células do notebook em ordem.

## Dados preparados

- `df_ceaps_bruto`: registros consolidados, com os campos originais e o ano do arquivo de origem.
- `df_ceaps_limpo`: cópia sem remoção de linhas, com tipos verificados, textos tratados e colunas derivadas para comparação e exibição. `ID` e `COD_SENADOR` permanecem textuais.
- `resumo_dicionario_bruto`, `diagnostico`, `tipos_e_ausencias` e `comparacao`: tabelas de estrutura, ausências, problemas de qualidade e conferência antes/depois.

O notebook lê os JSONs locais e produz `df_parlamentares`, `df_mandatos`, `df_exercicios` e `df_filiacoes`. A cobertura da coleta e os problemas de integração devem ser conferidos antes de relacionar essas tabelas às despesas. Não há atribuição automática de UF ou partido às despesas históricas.
