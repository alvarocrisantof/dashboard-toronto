# Rótulo da DRE → campo do FINAL

Gerado do JS do index.html (`row('Rótulo',...,'campos')`).
Subtotais (`dre-sub`) são **calculados**: nunca corrija o subtotal, corrija as linhas-folha (`dre-sub2`) que o compõem.
Rótulos repetidos (Showroom, Atacado, Laudo Cautelar, Garantia) dependem do grupo pai: veja a coluna Grupo.

| Grupo | Rótulo no print | Campo(s) |
|---|---|---|
| Vendas de Veículos | **Vendas de Veículos** (subtotal) | `merch_bruta_sw`, `merch_bruta_at` |
| Vendas de Veículos | Showroom | `merch_bruta_sw` |
| Vendas de Veículos | Atacado | `merch_bruta_at` |
| Receita de Serviços | **Receita de Serviços** (subtotal) | `intermediacao_fin`, `laudo_venda`, `transf_venda`, `fotos`, `prep_veiculo`, `gasolina`, `rec_doc_sai`, `rec_svc`, `venda_svc`, `venda_comiss`, `aluguel`, `garantia_venda` |
| Receita de Serviços | Rec. Documentos | `rec_doc_sai` |
| Receita de Serviços | Rec. Serv. Agregados | `rec_svc` |
| Receita de Serviços | Venda de Serviços | `venda_svc` |
| Receita de Serviços | Laudo Cautelar | `laudo_venda` |
| Receita de Serviços | Transferência | `transf_venda` |
| Receita de Serviços | Intermediação Financ. | `intermediacao_fin` |
| Receita de Serviços | Venda Comissionada | `venda_comiss` |
| Receita de Serviços | Fotos Veiculares | `fotos` |
| Receita de Serviços | Preparação Veicular | `prep_veiculo` |
| Receita de Serviços | Gasolina Agenciados | `gasolina` |
| Receita de Serviços | Aluguéis | `aluguel` |
| Receita de Serviços | Garantia (Venda) | `garantia_venda` |
| Receitas Diversas | **Receitas Diversas** (subtotal) | `rec_diversas` |
| Descontos | **Descontos** (subtotal) | `desc_sw`, `desc_at` |
| Descontos | Showroom | `desc_sw` |
| Descontos | Atacado | `desc_at` |
| Impostos | **Impostos** (subtotal) | `esocial`, `fgts`, `csll_irpj`, `pis_cofins`, `icms`, `iss`, `alvara`, `fisc_func`, `iptu`, `retencoes`, `custas`, `das` |
| Impostos | ICMS | `icms` |
| Impostos | ISS | `iss` |
| Impostos | DAS (Simples) | `das` |
| Impostos | DARF PIS/COFINS | `pis_cofins` |
| Impostos | DARF E-Social | `esocial` |
| Impostos | FGTS | `fgts` |
| Impostos | CSLL/IRPJ | `csll_irpj` |
| Impostos | IPTU | `iptu` |
| Impostos | Alvará/Taxas | `alvara`, `fisc_func` |
| Impostos | Retenções/Custas | `retencoes`, `custas` |
| Devoluções | **Devoluções** (subtotal) | `devolucao`, `dev_fin` |
| Devoluções | Devolução | `devolucao` |
| Devoluções | Dev. Intermediação | `dev_fin` |
| Custo de Compra | **Custo de Compra** (subtotal) | `custo_compra_sw`, `custo_compra_at` |
| Custo de Compra | Showroom | `custo_compra_sw` |
| Custo de Compra | Atacado | `custo_compra_at` |
| Custo de Preparação | **Custo de Preparação** (subtotal) | `custo_prep_entrega`, `frete`, `multa_veiculo`, `custos_prep_lv` |
| Custo de Preparação | Prep./Entrega | `custo_prep_entrega` |
| Custo de Preparação | Frete/Outros | `frete`, `custos_prep_lv` |
| Custo de Preparação | Multa Veicular | `multa_veiculo` |
| Custo de Documentos | **Custo de Documentos** (subtotal) | `despachante_ent`, `ipva`, `taxas_transf_ent`, `baixa_gravame`, `comunicado_venda`, `despesas_postais`, `multas_nao_abat` |
| Custo de Documentos | IPVA | `ipva` |
| Custo de Documentos | Despachante Entrada | `despachante_ent` |
| Custo de Documentos | Taxas Transferência Ent. | `taxas_transf_ent` |
| Custo de Documentos | Baixa de Gravame | `baixa_gravame` |
| Custo de Documentos | Comunicado de Venda | `comunicado_venda` |
| Custo de Documentos | Despesas Postais | `despesas_postais` |
| Custo de Documentos | Multas não abatidas | `multas_nao_abat` |
| Custo de Serviços | **Custo de Serviços** (subtotal) | `garantia_custo`, `laudo_custo` |
| Custo de Serviços | Garantia | `garantia_custo` |
| Custo de Serviços | Laudo Cautelar | `laudo_custo` |
| Despesas com Vendas | **Despesas com Vendas** (subtotal) | `comissao_venda`, `comissao_c`, `pos_vendas`, `taxas_transf_sai`, `despachante_sai` |
| Despesas com Vendas | Comissão S/ Venda | `comissao_venda` |
| Despesas com Vendas | Comissão c/ Venda | `comissao_c` |
| Despesas com Vendas | Pós-Vendas | `pos_vendas` |
| Despesas com Vendas | Taxas Transf. Saída | `taxas_transf_sai` |
| Despesas com Vendas | Despachante Saída | `despachante_sai` |
| Despesas com Pessoal | **Despesas com Pessoal** (subtotal) | `salarios`, `desp_adm_dem`, `desp_pessoal_var`, `ferias`, `rescisao`, `fgts_rescis`, `plano_saude`, `datas_com`, `refeitorio`, `transporte`, `uniforme`, `medicina`, `cursos`, `churrasco`, `almoco_meta` |
| Despesas com Pessoal | Salários | `salarios` |
| Despesas com Pessoal | Desp. Adm./Demissão | `desp_adm_dem` |
| Despesas com Pessoal | Desp. c/ Pessoal | `desp_pessoal_var` |
| Despesas com Pessoal | Férias | `ferias` |
| Despesas com Pessoal | Rescisão | `rescisao` |
| Despesas com Pessoal | FGTS Rescisório | `fgts_rescis` |
| Despesas com Pessoal | Plano de Saúde | `plano_saude` |
| Despesas com Pessoal | Datas Comemorativas | `datas_com` |
| Despesas com Pessoal | Refeições/Lanches | `refeitorio` |
| Despesas com Pessoal | Transporte | `transporte` |
| Despesas com Pessoal | Uniforme | `uniforme` |
| Despesas com Pessoal | Medicina do Trabalho - ASO | `medicina` |
| Despesas com Pessoal | Churrasco por Meta | `churrasco` |
| Despesas com Pessoal | Almoço Meta Diamante | `almoco_meta` |
| Despesas com Pessoal | Cursos e Treinamentos | `cursos` |
| Despesas Administrativas | **Despesas Administrativas** (subtotal) | `aluguel_cond2`, `copa`, `cartorio`, `mat_aux`, `mat_escrit`, `seguros`, `contabil`, `informatica`, `associacoes`, `consultoria`, `juridico`, `viagens`, `estacionamento`, `pub_adm` |
| Despesas Administrativas | Copa e Bar | `copa` |
| Despesas Administrativas | Cartório | `cartorio` |
| Despesas Administrativas | Materiais | `mat_aux`, `mat_escrit` |
| Despesas Administrativas | Seguros e Proteções | `seguros` |
| Despesas Administrativas | Serviços Contábeis | `contabil` |
| Despesas Administrativas | Informática | `informatica` |
| Despesas Administrativas | Serviços Consultoria | `consultoria` |
| Despesas Administrativas | Viagens e Representações | `viagens` |
| Despesas Administrativas | Serviços Advocatícios | `juridico` |
| Despesas Administrativas | Associações e Sindicatos | `associacoes` |
| Despesas Administrativas | Estacionamento | `estacionamento` |
| Despesas Administrativas | Aluguéis e Condomínios | `aluguel_cond2` |
| Despesas Administrativas | Propaganda e Publicidade (Adm.) | `pub_adm` |
| Despesas Estabelecimento | **Despesas Estabelecimento** (subtotal) | `aluguel_cond`, `agua`, `energia`, `telefonia`, `limpeza`, `manutencao_loja` |
| Despesas Estabelecimento | Aluguéis/Condomínios | `aluguel_cond` |
| Despesas Estabelecimento | Água e Esgoto | `agua` |
| Despesas Estabelecimento | Energia Elétrica | `energia` |
| Despesas Estabelecimento | Telefonia/Internet | `telefonia` |
| Despesas Estabelecimento | Limpeza | `limpeza` |
| Despesas Estabelecimento | Manutenção da Loja | `manutencao_loja` |
| Despesas Marketing | **Despesas Marketing** (subtotal) | `publicidade`, `portais`, `feirao`, `brindes` |
| Despesas Marketing | Propaganda/Publicidade | `publicidade` |
| Despesas Marketing | Portais de Anúncio | `portais` |
| Despesas Marketing | Feirão/Eventos | `feirao` |
| Despesas Marketing | Brindes e Presentes | `brindes` |
| Despesas Sócios | **Despesas Sócios** (subtotal) | `pro_labore`, `dividendos` |
| Despesas Sócios | Pró-Labore | `pro_labore` |
| Despesas Sócios | Distribuição Dividendos | `dividendos` |
| Empréstimos/Financiamentos | **Empréstimos/Financiamentos** (subtotal) | `emprestimos` |
| Despesas Variáveis | **Despesas Variáveis** (subtotal) | `aj_saida` |
| Despesas Variáveis | Ajuste de Saldo – Saída | `aj_saida` |
| Máquinas e Equipamentos | **Máquinas e Equipamentos** (subtotal) | `maq_equip` |
| Receitas Financeiras | **Receitas Financeiras** (subtotal) | `retorno_fin`, `retorno_acordos`, `rendimento`, `seguro_rec`, `remuner_bank`, `retorno_comiss`, `juros_rec`, `pecld_rec`, `desc_pagar` |
| Receitas Financeiras | Retorno/Comissões/Acordos | `retorno_comiss` |
| Receitas Financeiras | Retorno de Financiamento | `retorno_fin` |
| Receitas Financeiras | Retorno (Acordos e Plus) | `retorno_acordos` |
| Receitas Financeiras | Comissão de Seguro | `seguro_rec` |
| Receitas Financeiras | Rendimento de Aplicação | `rendimento` |
| Receitas Financeiras | Remuneração Bancária – TIME | `remuner_bank` |
| Receitas Financeiras | Descontos a Pagar | `desc_pagar` |
| Receitas Financeiras | Juros a Receber | `juros_rec` |
| Receitas Financeiras | Recuperação PECLD | `pecld_rec` |
| Despesas Financeiras | **Despesas Financeiras** (subtotal) | `tarifa_bancaria`, `juros_pagar`, `juros_pagar2`, `iof`, `desc_receber` |
| Despesas Financeiras | Tarifa Bancária | `tarifa_bancaria` |
| Despesas Financeiras | IOF | `iof` |
| Despesas Financeiras | Descontos a Receber | `desc_receber` |
| Despesas Financeiras | Juros a Pagar | `juros_pagar`, `juros_pagar2` |

Campos de quantidade (não monetários): `q`, `q_sw`, `q_at`, `q_proprio`, `q_consig`.

Nome da conta no AutoConf → campo: ver `_DRE_EXT` em `update_dashboard.py` (ex.: 'Ajuste de saldo - Entrada' → `rec_diversas`).
