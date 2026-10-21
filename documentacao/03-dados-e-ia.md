# Dados e inteligência artificial

## Situação atual

O sistema tem dataset simulado, treino reproduzível, modelo persistido, inferência na API e métricas (pasta `ml/`). A API expõe a classificação de risco e a recomendação de ONGs (veja [Arquitetura e API](02-arquitetura-e-api.md)). As métricas são de dados simulados e não comprovam eficácia em cenário real.

## Dataset proposto

Começar com dados simulados identificados como tal. Dados públicos devem ter fonte, licença, data de coleta e limitações registradas antes do uso. Evitar nome, telefone, e-mail e coordenadas residenciais no dataset de treinamento.

| Campo proposto | Tipo/unidade | Uso |
|---|---|---|
| lote_id | identificador sintético | Rastreabilidade; não usar como atributo preditivo |
| alimento_descricao | texto | Classificação semântica do alimento |
| categoria | classe | Caracterização do lote |
| quantidade_kg | número positivo | Volume disponível |
| dias_ate_validade | número de dias no instante da previsão | Urgência |
| distancia_km | número não negativo | Viabilidade geográfica |
| capacidade_disponivel_kg | número não negativo | Compatibilidade com ONG |
| risco_descarte | rótulo definido pela equipe | Alvo de classificação |
| origem_dados | público/simulado | Transparência |

Definir o horizonte de `risco_descarte` e como o rótulo será obtido. Dados simulados por regras permitem demonstrar o fluxo, mas a reprodução dessas regras pelo modelo não comprova eficácia em cenário real.

## Curadoria e avaliação propostas

1. Registrar origem, licença, método de simulação e versão do dataset.
2. Verificar duplicatas, valores ausentes, unidades, validade e distribuição de classes.
3. Separar treino, validação e teste antes dos ajustes; agrupar registros do mesmo lote para evitar vazamento. Usar divisão temporal quando adequada ao cenário.
4. Comparar um baseline simples com um classificador scikit-learn. Avaliar Transformers apenas se o componente textual e os dados justificarem.
5. Ajustar pré-processamento apenas no treino e documentar seed, versões e parâmetros.
6. Medir acurácia, precisão, recall, F1 e matriz de confusão; destacar recall dos lotes de alto risco e desempenho por região/categoria.
7. Medir latência de inferência e registrar resultados no conjunto de teste, sem inventar valores.

## Recomendação geográfica proposta

Filtrar ONGs por capacidade disponível e elegibilidade do lote. Com coordenadas válidas, calcular distância geográfica e ordenar candidatas considerando distância e urgência. Distância em linha reta não equivale a rota urbana; a otimização de coleta exige dados ou serviço de roteamento e validação específica.

Documentar fórmula/pesos do score, restrições e motivo da recomendação. Avaliar situações em que uma região ou ONG recebe menos oportunidades. Manter confirmação humana para recebimento e condições do alimento.

## Artefatos esperados do checkpoint 1

- Dataset versionado, dicionário e ficha de origem.
- Script/notebook de treinamento reproduzível e dependências.
- Modelo persistido, versão e procedimento de inferência local.
- Relatório de métricas, baseline, limitações e casos de erro.
- Matriz STRIDE revisada para incluir o processamento de IA.

## Implementação (pasta `ml/`)

```bash
pip install -r ml/requirements-ml.txt
python ml/generate_dataset.py   # ml/data/lotes_simulados.csv (3000 lotes simulados, seed 42)
python ml/train.py              # ml/models/risco_descarte.joblib, ml/reports/metricas.json e rede-alimenta-back/ia/*.json
python ml/predict.py '{"alimento_descricao":"pao frances","categoria":"padaria","quantidade_kg":20,"dias_ate_validade":1,"distancia_km":4,"capacidade_disponivel_kg":50}'
python -m unittest discover -s ml/tests   # JSON da API == pipeline scikit-learn
```

**Protocolo:** divisão estratificada 70/15/15 (treino/validação/teste), sem vazamento (cada linha é um lote único). Candidatos: baseline (classe majoritária), regressão logística, regressão logística com `class_weight="balanced"` e Random Forest. Entre as regressões logísticas (únicas exportáveis para JSON), a escolha usa o F1 macro na validação. O teste é usado uma vez, ao final.

**Resultados no teste (450 lotes simulados; `ml/reports/metricas.json`):**

| Métrica | Valor |
|---|---|
| Modelo escolhido | logistic_regression_balanced |
| Acurácia | 0,840 (baseline majoritária: 0,700) |
| F1 macro | 0,762 |
| Recall / precisão de alto risco | 0,892 / 0,949 |
| Recall da classe médio | 0,622 (precisão 0,535) |
| Latência de inferência | ~0,013 ms por lote |

Limitações: o rótulo é gerado por uma regra simulada com ruído, então o modelo apenas reproduz essa regra; as classes são desbalanceadas (~70% alto risco); o Random Forest teve F1 macro menor na validação (0,728); a classe médio é a mais difícil (30 de 74 lotes classificados como alto). Hugging Face Transformers não foi usado. Para uso real, é preciso coletar dados reais de doações e descartes e reavaliar por região e categoria.

Recomendação de ONGs: filtra por capacidade, calcula o risco para cada ONG e ordena por `score_ia` (empate: a ONG mais perto); a prioridade sugerida vem do risco previsto para a melhor ONG. Exige confirmação humana.

**Distância.** É a linha reta (haversine, `services/geo.py`) entre o doador e a ONG, na ordem: (1) latitude e longitude do cadastro; (2) o centro da cidade citada na região ("Zona Sul, São Paulo" vira o centro de São Paulo; tabela com as 27 capitais e cerca de 80 cidades grandes, precisão de alguns km); (3) a estimativa fixa de antes (5 km na mesma região, 15 km em outra). A tela mostra a origem de cada número ("entre cidades", "estimada"). Linha reta não é rota de coleta.

**Faixa do treino.** O dataset simulado tem quantidade de 1 a 120 kg, validade de 0 a 847 dias, distância de 0,5 a 25 km e capacidade de 5 a ~200 kg (`faixa_treino` em `ia/modelo_risco.json`, gravada por `ml/train.py`). Uma regressão logística extrapola sem limite fora disso: antes do ajuste, uma ONG com 2.000 kg de capacidade ganhava score de ~100% só por estar fora da faixa. Agora `ia/inferencia.py` leva cada valor ao limite da faixa e a resposta lista as `entradas_ajustadas`; a tela marca com * a distância acima de 25 km. Não houve novo treino: os coeficientes e as métricas são os mesmos.

**Fora do escopo atual:** rotas e tempo de deslocamento, avaliação de equidade entre regiões e treino com dados reais de doação e descarte.

## Curadoria e fontes de dados

O dataset de treino é **simulado** (regras com ruído em `ml/generate_dataset.py`; origem, seed e versão registrados). Não há conjunto público de doações por lote, com validade, quantidade e destino, na granularidade que o modelo precisa; por isso nenhum dado aberto entra no treino, e as métricas só demonstram o fluxo, não eficácia em cenário real.

Dados abertos e fontes públicas foram usados apenas para **dimensionar o problema** no pitch. Os valores abaixo são os divulgados por essas instituições; as páginas oficiais do IBGE e da ONU bloquearam a consulta automática ao preparar este documento, então os números vêm de reproduções (links) e devem ser conferidos nas fontes oficiais antes de serem citados na defesa:

| Dado | Valor divulgado | Fonte |
|---|---|---|
| Insegurança alimentar no Brasil (IBGE, PNAD Contínua, 4º tri de 2023) | 27,6% dos domicílios (21,6 milhões) com algum grau de insegurança alimentar; 4,1% (cerca de 3,2 milhões) com insegurança grave | Divulgação do IBGE, reproduzida pelo [CFN](https://cfn.org.br/ibge-divulga-dados-sobre-seguranca-alimentar-no-pais/) |
| Desperdício global de alimentos (ONU Meio Ambiente, Food Waste Index 2024) | 1,05 bilhão de toneladas em 2022, cerca de 132 kg por pessoa | [UNEP](https://www.unep.org/news-and-stories/press-release/world-squanders-over-1-billion-meals-day-un-report) |
| Desperdício doméstico no Brasil (mesmo relatório, segundo a Embrapa) | cerca de 94 kg por pessoa por ano, a partir de um estudo-piloto em cinco regiões da cidade do Rio de Janeiro (2023), sem extrapolação nacional | [Embrapa](https://embrapa.br/busca-de-noticias/-/noticia/87972089/world-squanders-over-1-billion-meals-a-day-according-to-un) |

Para melhorar a nota de curadoria no futuro: parametrizar o gerador com prazos de validade de uma fonte aberta (por exemplo, tabelas públicas de vida útil de alimentos) e registrar licença, data de coleta e limitações de cada fonte.
