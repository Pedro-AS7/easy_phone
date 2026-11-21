"""Casos de avaliação da IA local. Todos os dados são fictícios.

Cada caso diz o que NÃO pode aparecer no texto enviado ao provedor (`mascarar`) e o
que precisa continuar lá (`manter`). Em pedidos, `intencao` lista as respostas aceitas.
"""

# Cofre fictício: o que estaria nos contatos e contas do aparelho.
CONTATOS = [
    "Lucas Andrade", "Gabriel Ferreira", "Mariana Lopes", "Dra. Helena Prado", "Barbearia Arctos",
    "UCB Secretaria", "Pizzaria Donatello", "Tio Jorge", "Rafaela Nutri", "Oficina do Beto",
]
EMAILS = ["lucas.andrade@gmail.com"]
TELEFONES = ["+55 61 98888-7777", "(61) 3344-5566"]


def pedido(grupo, texto, intencao, mascarar=(), manter=()):
    return {"tipo": "pedido", "grupo": grupo, "entrada": texto, "intencao": intencao.split("|"),
            "mascarar": list(mascarar), "manter": list(manter)}


def tela(grupo, texto, mascarar=(), manter=()):
    return {"tipo": "tela", "grupo": grupo, "entrada": texto, "intencao": [],
            "mascarar": list(mascarar), "manter": list(manter)}


CASOS = [
    # --- ação com pessoas ---
    pedido("Ação com pessoa", "Manda uma mensagem pro Gabriel avisando que vou atrasar 10 minutos", "acao", ["Gabriel"], ["atrasar"]),
    pedido("Ação com pessoa", "liga pra mariana lopes", "acao", ["mariana", "lopes"]),
    pedido("Ação com pessoa", "Avisa a Dra. Helena que vou me atrasar pra consulta", "acao", ["Helena"], ["consulta"]),
    pedido("Ação com pessoa", "Marca um almoço com o Thiago Nogueira na sexta e coloca na agenda", "acao", ["Thiago", "Nogueira"], ["almoço"]),
    pedido("Ação com pessoa", "manda pro beto da oficina que o carro tá fazendo barulho", "acao", ["beto"], ["carro"]),
    pedido("Ação com pessoa", "Me lembra de comprar o presente da Helena no sábado", "acao", ["Helena"], ["presente"]),
    pedido("Ação com pessoa", "Responde a Mariana no WhatsApp: tô chegando, me espera na portaria", "acao", ["Mariana"], ["WhatsApp", "portaria"]),
    pedido("Ação com pessoa", "Tira um print da conversa com o Gabriel e manda pra Mariana", "acao", ["Gabriel", "Mariana"]),
    pedido("Ação com pessoa", "manda mensagem pra helena prado dizendo que amei o presente", "acao", ["helena", "prado"], ["presente"]),
    pedido("Ação com pessoa", "Oculta meus stories pra Rafaela no Instagram", "acao|mista", ["Rafaela"], ["Instagram"]),
    pedido("Ação com pessoa", "Qual o melhor caminho pra casa da Mariana agora?", "acao|mista|pesquisa", ["Mariana"]),
    pedido("Ação com pessoa", "Pesquisa no Google quem é Gabriel Ferreira", "pesquisa|mista", ["Gabriel", "Ferreira"], ["Google"]),
    # --- negócios e instituições ---
    pedido("Negócio ou instituição", "Envie uma mensagem para a Barbearia Arctos perguntando se tem horário amanhã", "acao", ["Arctos"], ["Barbearia"]),
    pedido("Negócio ou instituição", "Qual o endereço da Barbearia Arctos?", "pesquisa", [], ["Barbearia Arctos"]),
    pedido("Negócio ou instituição", "Que horas fecha a secretaria da UCB hoje?", "pesquisa", [], ["UCB"]),
    pedido("Negócio ou instituição", "Quanto custa um corte na Barbearia Arctos? Vê no Instagram deles", "pesquisa|mista", [], ["Arctos", "Instagram"]),
    pedido("Negócio ou instituição", "Qual o telefone da Clínica Sorriso Perfeito em Taguatinga?", "pesquisa", [], ["Sorriso Perfeito", "Taguatinga"]),
    pedido("Negócio ou instituição", "Qual o horário de funcionamento do Detran de Brasília?", "pesquisa", [], ["Detran", "Brasília"]),
    pedido("Negócio ou instituição", "Abre o Nubank e me mostra o saldo", "acao", [], ["Nubank", "saldo"]),
    # --- mistos ---
    pedido("Pedido misto", "Pesquise o endereço da Pizzaria Donatello e mande para o Gabriel", "mista", ["Gabriel"], ["Donatello"]),
    pedido("Pedido misto", "Veja no site da UCB quando começam as matrículas e avise a Mariana", "mista", ["Mariana"], ["UCB", "matrículas"]),
    pedido("Pedido misto", "Compra ingresso pro show do Caetano Veloso em Brasília", "mista|acao|pesquisa", ["Caetano Veloso"]),
    # --- pesquisa pura ---
    pedido("Pesquisa pura", "Quem é o atual técnico da seleção brasileira?", "pesquisa", [], ["seleção brasileira"]),
    pedido("Pesquisa pura", "Pesquise as últimas notícias sobre o Lula", "pesquisa", ["Lula"]),
    pedido("Pesquisa pura", "Como ocultar meus stories para uma pessoa no Instagram?", "pesquisa|mista", [], ["Instagram", "stories"]),
    pedido("Pesquisa pura", "Quanto tá o dólar hoje?", "pesquisa", [], ["dólar"]),
    pedido("Pesquisa pura", "Qual a previsão do tempo para amanhã em Brasília?", "pesquisa", [], ["Brasília"]),
    # --- dados por regra fixa ---
    pedido("Dados por regra fixa", "Meu e-mail é lucas.andrade@gmail.com, cadastra ele na newsletter do Nexo Jornal", "mista|acao", ["lucas.andrade@gmail.com"], ["Nexo"]),
    pedido("Dados por regra fixa", "Manda meu CPF 123.456.789-09 pro Tio Jorge", "acao", ["123.456.789-09", "Jorge"]),
    pedido("Dados por regra fixa", "Liga pro número (61) 98888-7777", "acao", ["98888-7777"]),
    pedido("Dados por regra fixa", "Bloqueia o @joao.pedro_22 no Instagram", "acao", ["joao.pedro_22"], ["Instagram"]),
    pedido("Dados por regra fixa", "Aumenta o brilho da tela e liga o modo escuro", "acao", [], ["brilho", "modo escuro"]),
    # --- texto de tela ---
    tela("Tela do Instagram", "Legenda: Aniversário da Bia Monteiro ontem, foi demais! • Comentários • carol_dias: lindas • Pedro Henrique Sá: saudades de vcs",
         ["Bia", "Monteiro", "carol_dias", "Pedro Henrique"], ["Aniversário", "Comentários"]),
    tela("Tela do Instagram", "juliana.reis_ • Juliana Reis • 1.204 seguidores • Seguir • Mensagem",
         ["juliana.reis_", "Juliana", "Reis"], ["seguidores", "Seguir", "Mensagem"]),
    tela("Outras telas", "Grupo Futebol de quinta • Renato Vilela: quem vai hoje? • ~Duda: eu vou • Você: tô dentro",
         ["Renato", "Vilela", "Duda"], ["Futebol"]),
    tela("Outras telas", "Conexões • Wi-Fi • Bluetooth • Modo avião • Uso de dados • Mais configurações de conexão",
         [], ["Conexões", "Wi-Fi", "Bluetooth", "Modo avião", "Uso de dados"]),
    tela("Outras telas", "Receita de pão caseiro fácil • 2,3 mi de visualizações • Comentário de marcos_tulio88: fiz e deu certo",
         ["marcos_tulio88"], ["Receita", "visualizações"]),
    tela("Outras telas", "Nubank: Você recebeu uma transferência de R$ 250,00 de Fernanda Couto Alves",
         ["Fernanda", "Couto", "Alves"], ["Nubank", "250,00"]),
    tela("Outras telas", "Pesquisas recentes • sintomas de dengue • vagas desenvolvedor python brasília • aniversário camila torres presente",
         ["camila", "torres"], ["dengue", "python"]),
    tela("Outras telas", "De: Otávio Brandão <otavio.brandao@empresa.com.br> • Assunto: Proposta comercial revisada",
         ["Otávio", "Brandão", "otavio.brandao@empresa.com.br"], ["Proposta comercial"]),
]
