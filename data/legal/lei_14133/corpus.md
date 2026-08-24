# Lei Federal nº 14.133/2021 — corpus LicitAll (trechos operacionais)

Fonte: texto oficial da Lei 14.133/2021. Chunks curados para RAG de triagem pré-certame.
Não substitui consulta ao Diário Oficial / Planalto.

## Art. 5º — Princípios

Art. 5º Na aplicação desta Lei, serão observados os princípios da legalidade, da impessoalidade,
da moralidade, da publicidade, da eficiência, do interesse público, da probidade administrativa,
da igualdade, do planejamento, da transparência, da eficácia, da segregação de funções,
da motivação, da vinculação ao edital, do julgamento objetivo, da segurança jurídica,
da razoabilidade, da competitividade, da proporcionalidade, da celeridade,
da economicidade e do desenvolvimento nacional sustentável.

## Art. 11 — Objetivos do processo licitatório

Art. 11. O processo licitatório tem por objetivos:
I - assegurar a seleção da proposta apta a gerar o resultado de contratação mais vantajoso
para a Administração Pública, inclusive no que se refere ao ciclo de vida do objeto;
II - assegurar tratamento isonômico entre os licitantes, bem como a justa competição;
III - evitar contratações com sobrepreço ou com preços manifestamente inexequíveis
e superfaturamento na execução dos contratos;
IV - incentivar a inovação e o desenvolvimento nacional sustentável.

## Art. 40 — Especificações técnicas

Art. 40. O termo de referência deverá conter, no mínimo, os seguintes elementos, quando aplicável:
...
As especificações técnicas devem ser claras, precisas e suficientes, vedadas especificações
que, por excessivas, irrelevantes ou desnecessárias, limitem a competição.

## Art. 41 — Marca e similaridade

Art. 41. No caso de licitação que envolva o fornecimento de bens, a Administração poderá:
I - indicar marca ou modelo, nas hipóteses previstas em regulamento, desde que formalmente justificado;
II - exigir amostra ou prova de conceito do bem, quando necessário.
A indicação de marca sem justificativa técnica adequada pode caracterizar restrição indevida
à competitividade, em desacordo com os princípios do Art. 5º e com a jurisprudência do TCU.

## Art. 63 — Vistoria e esclarecimentos preliminares

Art. 63. Os licitantes poderão ser convocados a apresentar documentos complementares
ou a realizar diligências, desde que necessários à análise da proposta ou da habilitação
e não alterem a substância da proposta.
Exigência de vistoria técnica obrigatória deve observar proporcionalidade e não pode
ser utilizada para restringir artificialmente o universo de competidores; prazos e condições
devem ser razoáveis e compatíveis com o objeto (Arts. 5º e 67).

## Art. 66 — Habilitação jurídica

Art. 66. A habilitação jurídica destinará-se a demonstrar a capacidade do licitante
para exercer direitos e assumir obrigações, e a documentação exigida limitar-se-á à comprovação
de existência jurídica da pessoa e, quando cabível, de representação.

## Art. 67 — Qualificação técnica

Art. 67. A documentação relativa à qualificação técnico-profissional e técnico-operacional
será restrita a:
I - apresentação de profissional, devidamente registrado no conselho profissional competente,
quando o exercício da atividade assim o exigir;
II - certidões ou atestados de capacidade técnica;
III - prova de atendimento de requisitos previstos em lei especial, quando houver;
entre outros requisitos legais pertinentes ao objeto.
É vedada a exigência de comprovação de atividade ou de aptidão com limitações de tempo
ou de locais específicos que inibam a participação, salvo quando indispensável à execução.

## Art. 68 — Regularidade fiscal, social e trabalhista

Art. 68. As habilitações fiscal, social e trabalhista serão aferidas mediante a verificação
dos seguintes requisitos, conforme o caso:
I - a inscrição no Cadastro de Pessoas Físicas (CPF) ou no Cadastro Nacional da Pessoa Jurídica (CNPJ);
II - a inscrição no cadastro de contribuintes estadual e/ou municipal, se houver;
III - a regularidade perante a Fazenda federal, estadual e/ou municipal;
IV - a regularidade relativa à Seguridade Social e ao FGTS;
V - a regularidade perante a Justiça do Trabalho;
entre outras exigências legais aplicáveis.

## Art. 69 — Qualificação econômico-financeira

Art. 69. A habilitação econômico-financeira será aferida de forma objetiva, por índices
e documentos usualmente adotados para a avaliação da situação financeira necessária
e suficiente à execução do objeto, vedada a exigência de valores mínimos de faturamento
anteriores e de índices de rentabilidade ou lucratividade.
A exigência de capital social ou patrimônio líquido mínimo deve ser justificada
e compatível com o risco da contratação; percentuais excessivos (parâmetro frequente
de análise no TCU em torno de 10% do valor estimado) podem ser considerados restritivos.

## Art. 82 a 84 — Pregão (referência)

O pregão, na forma eletrônica, observa rito próprio desta Lei, com disputa por lances
e fase de habilitação conforme o edital, preservados os princípios do Art. 5º
e a competitividade.

## Art. 164 — Impugnação e pedidos de esclarecimento

Art. 164. Qualquer pessoa é parte legítima para impugnar edital de licitação por
irregularidade ou para solicitar esclarecimento sobre os seus termos, devendo
protocolar o pedido até 3 (três) dias úteis antes da data de abertura do certame.
A resposta será divulgada em sítio eletrônico oficial no prazo de 3 (três) dias úteis,
limitado ao último dia útil anterior à abertura.
No LicitAll, ausente data explícita no edital, o limite é calculado em dias úteis
nacionais retroativos a partir da data de abertura (ver `src/compliance/lei_14133.py`).

## Art. 4º — ME/EPP e LC 123/2006

Art. 4º Aplicam-se às licitações e contratos de que trata esta Lei as disposições
permanentes da Lei Complementar nº 123/2006 (ME/EPP).
Em especial, o Art. 48 da LC 123 prevê, entre outros, a possibilidade de:
- certames ou itens exclusivos para ME/EPP até R$ 80.000,00;
- cota reservada de até 25% do objeto para ME/EPP, quando couber.
Benefícios só devem ser afirmados pelo sistema se constarem do edital analisado.
