# SLA da T.I

O SLA mede se a T.I atende e resolve os chamados dentro do prazo combinado. Vale só para chamados
**enviados para a T.I** e abertos depois da ativação. Os chamados antigos e os de outros setores
ficam "sem SLA".

## Como a prioridade é definida (impacto × urgência, ITIL)

Quem abre o chamado **não escolhe a prioridade**. Responde duas perguntas e o sistema calcula:

1. **Quem está sendo afetado?** (impacto)
2. **Quanto isso atrapalha o trabalho?** (urgência)

| Impacto \ Urgência | Não atrapalha, pode esperar | Atrapalha, mas dá para continuar | O trabalho parou |
|---|---|---|---|
| **Só eu** | Baixa | Baixa | Média |
| **Meu setor ou várias pessoas** | Baixa | Média | Alta |
| **A empresa toda ou vários setores** | Média | Alta | Alta |

A T.I pode **ajustar a prioridade** no chamado depois de analisar. Por exemplo, a pessoa diz que
"o trabalho parou", mas tem um mouse reserva na gaveta. A mudança fica no histórico e os prazos são
recalculados.

A matriz fica em `MATRIZ_PRIORIDADE`, em `app/modelos.py`. Os exemplos que aparecem no formulário
ficam em `EXEMPLOS_PRIORIDADE`, em `app/rotas/chamados.py`.

## Catálogo de exemplos

Use esta tabela como referência para a equipe e para orientar os usuários.

| Prioridade | Incidente (algo parou ou falhou) | Solicitação (pedido ou dúvida) |
|---|---|---|
| **Alta** | Sem internet ou rede na empresa · sistema (ERP) fora do ar para um setor inteiro · servidor de arquivos fora · e-mail parado para todos · impressora do faturamento ou da expedição parada · vírus ou ataque | Acesso urgente para um setor inteiro trabalhar (ex.: sistema novo que entra em produção hoje) |
| **Média** | Meu computador não liga · sem acesso ao sistema só para mim · impressora do setor com falha (dá para usar outra) · lentidão que atrapalha o setor · telefone do setor mudo | Acesso ou conta para um funcionário que começa em breve · instalar um programa necessário para o trabalho da semana |
| **Baixa** | Mouse ou teclado com defeito · monitor com mancha · um programa que trava às vezes · lentidão leve só para mim | Instalar um programa · criar uma pasta ou dar acesso · dúvida no Excel ou no e-mail · troca de equipamento planejada · papel de parede, assinatura de e-mail |

## Os dois prazos

| Prazo | Começa | Para quando |
|---|---|---|
| **Primeiro atendimento** | Chamado aberto (ou encaminhado para a T.I) | Alguém da T.I assume, muda o status ou comenta |
| **Solução** | Chamado aberto (ou encaminhado para a T.I) | Status vai para **Fechado** |

- Os prazos contam **só o expediente**: segunda a sexta, das 7h às 18h. Um dia útil tem 11 h.
- **Pausa em "Aguardando usuário".** O relógio da solução para enquanto o chamado espera a pessoa.
- **Reabrir** retoma o relógio de onde parou. O tempo em que ficou fechado não conta.
- **Encaminhar para fora da T.I** tira o SLA. Se o chamado voltar para a T.I, os prazos recomeçam a
  partir do encaminhamento.

## Metas padrão

O administrador edita as metas em **Painel → SLA da T.I → Metas de SLA**, ou em `/sla`.

| | Primeiro atendimento | Solução |
|---|---|---|
| Incidente – Alta | 30 min | 4 h |
| Incidente – Média | 2 h | 1 dia útil |
| Incidente – Baixa | 4 h | 3 dias úteis |
| Solicitação – Alta | 1 h | 1 dia útil |
| Solicitação – Média | 4 h | 3 dias úteis |
| Solicitação – Baixa | 1 dia útil | 5 dias úteis |
| Problema | sem SLA | sem SLA |

Cada chamado guarda a meta que valia quando foi aberto. Se a tabela mudar depois, o passado não muda.
A meta só é recalculada quando a T.I muda a categoria ou a prioridade do chamado.

## Onde aparece

O SLA aparece só para quem atende, para supervisores e para o administrador.

- **Lista de chamados:** selo com o tempo que falta. Fica cinza no prazo, amarelo a partir de 75% do
  prazo e vermelho quando estoura. Tem filtros "SLA em risco ou estourado" e "SLA estourado".
- **Chamado:** os dois prazos com barra de progresso, a data e hora limite e o tempo pausado.
- **Painel e PDF do relatório:** % no prazo dos encerrados no período (atendimento e solução), com
  comparação ao período anterior e separação por prioridade, categoria e responsável. Mostra também
  quantos estão em risco ou estourados agora.
- **Excel do relatório:** quem é afetado, quanto atrapalha, as metas e a situação de cada prazo.

## Alertas por e-mail

| Quando | Quem recebe |
|---|---|
| 75% do prazo usado | Responsável |
| Prazo estourado | Responsável e CPD (`avisos_cpd`) |

Cada prazo avisa no máximo uma vez por nível. O comando `python manage.py verificar-sla` roda a cada
15 minutos durante o expediente. A linha do cron está em [deploy/OPERACAO.md](../deploy/OPERACAO.md).
