"""Gera o relatório do Tema 1 (até 3 páginas) em PDF.

Uso: python gerar_relatorio.py relatorio-tema1.pdf   (precisa do pacote reportlab)
"""
import sys

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (KeepTogether, ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

TINTA = colors.HexColor("#10233A")
ACENTO = colors.HexColor("#0E7C7B")
CINZA = colors.HexColor("#5B6875")

ss = getSampleStyleSheet()
corpo = ParagraphStyle("corpo", parent=ss["Normal"], fontName="Helvetica", fontSize=11, leading=15.4,
                       alignment=TA_JUSTIFY, spaceAfter=6)
titulo = ParagraphStyle("titulo", parent=corpo, fontName="Helvetica-Bold", fontSize=15.5, leading=19,
                        textColor=TINTA, alignment=0, spaceAfter=3)
meta = ParagraphStyle("meta", parent=corpo, fontSize=9.4, leading=12.4, textColor=CINZA, alignment=0, spaceAfter=0)
h1 = ParagraphStyle("h1", parent=corpo, fontName="Helvetica-Bold", fontSize=12.6, leading=16, textColor=ACENTO,
                    alignment=0, spaceBefore=13, spaceAfter=4)
h2 = ParagraphStyle("h2", parent=corpo, fontName="Helvetica-Bold", fontSize=11, leading=14.4, textColor=TINTA,
                    alignment=0, spaceBefore=7, spaceAfter=3)
cel = ParagraphStyle("cel", parent=corpo, fontSize=10, leading=13, alignment=0, spaceAfter=0)
celb = ParagraphStyle("celb", parent=cel, fontName="Helvetica-Bold", textColor=colors.white)
code = lambda t: f"<font face='Courier'>{t}</font>"


def lista(itens):
    return ListFlowable([ListItem(Paragraph(t, corpo), leftIndent=11) for t in itens],
                        bulletType="bullet", start="•", leftIndent=12, bulletFontSize=8)


def tabela(linhas, larguras):
    dados = [[Paragraph(c, celb) for c in linhas[0]]] + [[Paragraph(c, cel) for c in l] for l in linhas[1:]]
    t = Table(dados, colWidths=larguras, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), TINTA),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#EEF3F0")]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#C8D3CE")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


SETCFG = code("set_config('app.usuario', ..., true)")
P = lambda t: Paragraph(t, corpo)
H1 = lambda t: Paragraph(t, h1)
H2 = lambda t: Paragraph(t, h2)

story = [
    Paragraph("Tema 1 — Cadastro de Pacientes, Equipe Médica e Agendamentos", titulo),
    Paragraph("Sistema de Gestão Hospitalar e Telemedicina · Banco relacional (PostgreSQL 16) · "
              "Laboratório de Banco de Dados · Prof. Eduardo Freitas · 27/11/2026", meta),
    Paragraph("<b>Integrantes:</b> Yuri e Antônio", meta),
    Spacer(1, 4),

    H1("1. Objetivo"),
    P("O Tema 1 é o núcleo relacional do sistema hospitalar: cadastra pacientes, médicos, especialidades, convênios "
      "e planos, agenda consultas e cirurgias e fatura os atendimentos. O enunciado pede ênfase em integridade "
      "referencial, controle de concorrência contra agendamentos duplicados, triggers e stored procedures para "
      "auditoria e transações que amarram o faturamento ao plano de saúde. A decisão que guiou o projeto foi colocar "
      "<b>todas essas regras no próprio banco</b>, e não no código da aplicação: assim elas valem para qualquer "
      "cliente, seja a API, o psql ou o DBeaver."),

    H1("2. Arquitetura e tecnologias"),
    P("Tudo roda em Docker Compose, na mesma estrutura do Tema 3 para facilitar a integração: o "
      f"{code('postgres:16-alpine')} guarda dados e regras; três réplicas idênticas de uma API em Python "
      "(FastAPI + asyncpg) atendem os pedidos; um Nginx na porta 8081 distribui o tráfego entre elas. A API usa "
      "apenas SQL escrito à mão, sem ORM, e se limita a traduzir os códigos de erro do Postgres (SQLSTATE) em "
      "respostas HTTP: violação de unicidade ou de conflito vira 409, chave estrangeira, CHECK ou regra da "
      "procedure vira 422. Os scripts do banco ficam em quatro arquivos executados na primeira subida: "
      f"{code('01_schema.sql')}, {code('02_auditoria.sql')}, {code('03_faturamento.sql')} e {code('04_seed.sql')}. "
      "Uma página simples (localhost:8081) mostra agenda, faturas e auditoria em tempo real durante a demonstração."),

    H1("3. Aplicação do banco relacional"),
    H2("3.1 Modelo e integridade referencial"),
    P("São oito tabelas: especialidade, convênio, plano, paciente, médico, agendamento, fatura e auditoria. As regras "
      "estão declaradas no schema:"),
    lista([
        "chaves estrangeiras entre todas as entidades, com <i>ON DELETE RESTRICT</i> (não se apaga um médico que tem "
        "agendamentos);",
        f"{code('UNIQUE')} em CPF, CRM, CNPJ e no par convênio/nome do plano, e uma fatura por atendimento;",
        f"{code('CHECK')} de formato (CPF com 11 dígitos, CNPJ com 14), de faixa (cobertura entre 0 e 100%, valores "
        "positivos) e de coerência: o paciente tem plano, carteirinha e validade, ou nenhum dos três (particular); "
        "só cirurgia tem valor próprio; na fatura, parte do convênio + parte do paciente = total.",
    ]),

    H2("3.2 Controle de concorrência: nenhum horário duplicado"),
    P(f"O período do agendamento é um {code('tstzrange')} no formato [início, fim), e a tabela tem duas "
      f"<i>exclusion constraints</i> com índice GiST: {code('EXCLUDE USING gist (medico_id WITH =, periodo WITH &amp;&amp;)')} "
      "e a equivalente para o paciente, ambas ignorando agendamentos cancelados. O operador &amp;&amp; testa sobreposição de "
      f"intervalos e a extensão {code('btree_gist')} permite combiná-lo com a igualdade do médico. Com isso o banco "
      "recusa dois horários sobrepostos mesmo quando os pedidos chegam ao mesmo tempo por réplicas diferentes da API, "
      "e horários encostados (09:00–09:30 e 09:30–10:00) continuam válidos. No teste de carga, 500 pedidos "
      "simultâneos para o mesmo médico e horário resultam em <b>1 agendamento gravado e 499 recusados</b>, em cerca de "
      "8 segundos."),

    H2("3.3 Auditoria com trigger e função PL/pgSQL"),
    P(f"A função {code('fn_auditoria()')} é disparada após INSERT, UPDATE e DELETE em paciente, médico e plano e grava "
      f"na tabela auditoria a operação, o registro, o estado anterior e o novo (com {code('to_jsonb')}), o momento e "
      f"o usuário. Esse usuário vem de {SETCFG}, que a API executa no início "
      "de cada transação de escrita com o valor do cabeçalho X-Usuario; por ser local à transação, ele não vaza entre "
      "pedidos que reaproveitam a mesma conexão do pool. Atualizações que não mudam nada não geram registro, e outro "
      "trigger torna a trilha imutável: UPDATE, DELETE e TRUNCATE na auditoria são recusados."),

    H2("3.4 Faturamento transacional ligado ao plano"),
    P(f"A stored procedure {code('realizar_atendimento(id)')} trava o agendamento com {code('SELECT ... FOR UPDATE')}, "
      "confere se ele ainda está agendado e se o plano do paciente é válido na data do atendimento, calcula a parte do "
      "convênio pela cobertura (a do paciente é o total menos essa parte, para a soma sempre fechar), emite a fatura e "
      "marca o atendimento como realizado, tudo em uma única transação. Se o plano estiver vencido, um "
      f"{code('RAISE EXCEPTION')} desfaz tudo: o atendimento continua agendado e nenhuma fatura é criada. A trava "
      "impede que duas chamadas simultâneas gerem duas faturas, e o trigger "
      f"{code('trg_transicao_status')} só permite agendado → realizado ou cancelado, de modo que nem pelo psql é "
      "possível cancelar um atendimento já faturado."),

    H1("4. Testes e validação"),
    P("Há 66 testes automatizados (pytest) que rodam num container contra o PostgreSQL real, porque o que se quer "
      "provar são as regras do banco: violações de cada constraint, horários sobrepostos, encostados e cancelados, "
      "corrida de transações, auditoria, imutabilidade da trilha, cálculo e rollback do faturamento e todas as rotas "
      "da API. Além deles, um teste de carga separado faz a corrida de 500 agendamentos, e o roteiro da apresentação "
      "foi executado do zero com o banco recriado, conferindo a saída de cada passo."),

    H1("5. Contribuições"),
    tabela([
        ["Integrante", "Responsabilidades"],
        ["Yuri", "Tabelas de cadastro (pacientes, médicos, especialidades, convênios e planos), integridade "
                 "referencial e auditoria por trigger."],
        ["Antônio", "Agendamento de consultas e cirurgias, controle de concorrência e procedure de faturamento."],
        ["Ambos", "Containerização com Docker, API, testes, integração com os demais temas, relatório e apresentação."],
    ], [3.0 * cm, 14.0 * cm]),

    H1("6. Aprendizados"),
    lista([
        "<b>Correto não é o mesmo que utilizável.</b> A primeira versão, só com a exclusion constraint, sempre deixava "
        "um único vencedor, mas com 500 inserções simultâneas o Postgres resolvia parte das disputas por deadlock "
        "(110 numa corrida, cerca de 1 s para detectar cada um): a corrida passava de 60 s e o Nginx devolvia 502. "
        f"Um trigger que trava a linha do médico antes da inserção ({code('FOR NO KEY UPDATE')}, que não bloqueia as "
        "checagens de chave estrangeira) colocou as tentativas em fila: zero deadlocks e cerca de 8 s. A constraint "
        "continua sendo a garantia; o trigger só organiza a disputa.",
        "<b>Checar antes de inserir não resolve concorrência.</b> Um SELECT na aplicação seguido de INSERT deixa uma "
        "janela em que dois pedidos passam; só uma regra dentro do banco fecha essa janela.",
        "<b>Regra no banco vale para todos os clientes.</b> Auditoria e trava de status feitas por trigger continuam "
        "valendo quando alguém altera os dados direto pelo DBeaver, o que um log na aplicação não garantiria.",
        "<b>Um teste só prova algo se falhou antes.</b> Um teste de concorrência com threads em Python passava mesmo "
        "sem a correção, porque não reproduzia a intercalação que causava o deadlock; o teste que valeu foi o feito "
        "pela API, que falhava antes e passou depois.",
        "<b>Detalhes que quebram a demonstração.</b> Fuso horário (a API passou a devolver -03:00, que o navegador "
        "entende), IDs previsíveis nos dados de exemplo e datas relativas ao dia em que o banco é recriado.",
    ]),

    H1("7. Integração com os demais temas"),
    P("Pacientes e médicos do Tema 1 são a base dos outros módulos: o grafo de interações, o prontuário e a triagem "
      "precisam referenciar os mesmos identificadores. A API do Tema 1 expõe esses dados, e a proposta para o sistema "
      "completo é um Nginx único na frente de todos os temas, encaminhando cada prefixo de rota para o módulo "
      "correspondente."),
]

doc = SimpleDocTemplate(sys.argv[1] if len(sys.argv) > 1 else "relatorio-tema1.pdf", pagesize=A4,
                        leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.8 * cm, bottomMargin=1.8 * cm,
                        title="Relatório — Tema 1: Cadastro, Agendamentos e Faturamento",
                        author="Yuri e Antônio")


def rodape(canvas, doc_):
    canvas.saveState()
    canvas.setFont("Helvetica", 8.5)
    canvas.setFillColor(CINZA)
    canvas.drawString(2 * cm, 1.1 * cm, "Tema 1 · Cadastro, Agendamentos e Faturamento")
    canvas.drawRightString(A4[0] - 2 * cm, 1.1 * cm, f"{doc_.page}")
    canvas.restoreState()


doc.build(story, onFirstPage=rodape, onLaterPages=rodape)
