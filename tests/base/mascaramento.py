"""Casos de mascaramento do conjunto congelado. Todos os dados são fictícios.

Pedido: `pedido(id, app, texto, intencao, pessoas, outros, liberar, manter, usuarios)`.
Tela: `tela(id, app, onde, trechos, pessoas, usuarios, outros, manter)`; `trechos` são os textos dos elementos, na
ordem da tela, como o Portal os entrega.

- `pessoas`: nomes de pessoas; nenhuma palavra de 3 letras ou mais deles pode sair.
- `usuarios`: nomes de usuário; o nome inteiro não pode sair.
- `outros`: e-mails, telefones, documentos; não podem sair.
- `liberar`: negócios, instituições e lugares que o pedido manda pesquisar; precisam sair reais.
- `manter`: o que precisa sair como está (rótulos, marcas, palavras comuns).
- `intencao`: respostas aceitas, separadas por "|".
- `nota`: por que o caso existe, quando não é óbvio (erros já vistos, armadilhas).
"""

# Cofre fictício: contatos e contas que estariam no aparelho.
CONTATOS = [
    "Lívia Bastos", "Caio Menezes", "Renata Oliveira", "Dr. Paulo Sales", "Tia Cida", "Vó Nena", "Bruno Kato",
    "Academia Fortis", "Pet Shop Bicho Bom", "Ana Júlia Ribeiro", "Igor Santana", "Thaís Carvalho", "Marcelo Antunes",
    "Pizzaria Bella Napoli", "Seu Raimundo Porteiro", "Débora RH", "Fábio Mecânico", "Jéssica Nails",
]
EMAILS = ["livia.bastos@gmail.com", "caio.menezes@outlook.com"]
TELEFONES = ["+55 61 99123-4567", "(11) 3222-1100", "61 98456-2210"]


def pedido(id, app, texto, intencao, pessoas=(), outros=(), liberar=(), manter=(), usuarios=(), nota=""):
    return {"id": id, "tipo": "pedido", "app": app, "onde": "pedido do usuário", "entrada": texto,
            "intencao": intencao.split("|"), "pessoas": list(pessoas), "usuarios": list(usuarios), "outros": list(outros),
            "liberar": list(liberar), "manter": list(manter), "nota": nota}


def tela(id, app, onde, trechos, pessoas=(), usuarios=(), outros=(), manter=(), nota=""):
    return {"id": id, "tipo": "tela", "app": app, "onde": onde, "trechos": list(trechos), "intencao": [],
            "pessoas": list(pessoas), "usuarios": list(usuarios), "outros": list(outros), "liberar": [],
            "manter": list(manter), "nota": nota}


PEDIDOS = [
    # --- ação com pessoa, em português ---
    pedido("ped-msg-livia", "whatsapp", "Manda mensagem pra Lívia dizendo que já tô saindo", "acao", ["Lívia"], manter=["saindo"]),
    pedido("ped-msg-minusc", "whatsapp", "manda pro caio que a reunião mudou pra 15h", "acao", ["caio"], manter=["reunião"],
           nota="nome do cofre em minúsculas: as regras fixas não pegam, só a IA"),
    pedido("ped-liga-renata", "telefone", "liga pra renata oliveira", "acao", ["renata", "oliveira"]),
    pedido("ped-dr-paulo", "whatsapp", "Avisa o Dr. Paulo que vou faltar na consulta de quinta", "acao", ["Paulo"], manter=["consulta"]),
    pedido("ped-fora-cofre", "whatsapp", "Manda um oi pro Henrique Albuquerque", "acao", ["Henrique", "Albuquerque"],
           nota="pessoa fora do cofre: só a IA acha"),
    pedido("ped-fora-cofre-minusc", "whatsapp", "pergunta pra gisele se ela vai no churrasco", "acao", ["gisele"], manter=["churrasco"]),
    pedido("ped-apelido", "whatsapp", "fala pro Juninho trazer o carregador", "acao", ["Juninho"], manter=["carregador"]),
    pedido("ped-tia", "telefone", "Liga pra Tia Cida no viva-voz", "acao", ["Cida"], manter=["Tia", "viva-voz"],
           nota="parentesco fica (STOPLIST), o nome sai trocado"),
    pedido("ped-vo", "whatsapp", "manda áudio pra vó nena perguntando se ela tomou o remédio", "acao", ["nena"], manter=["remédio"]),
    pedido("ped-grupo-pessoa", "whatsapp", "No grupo da faculdade, marca a Thaís e pergunta do trabalho", "acao", ["Thaís"], manter=["faculdade", "trabalho"]),
    pedido("ped-duas-pessoas", "whatsapp", "Encaminha a foto que o Bruno mandou pra Ana Júlia", "acao", ["Bruno", "Ana", "Júlia"], manter=["foto"]),
    pedido("ped-agenda-pessoa", "agenda", "Marca na agenda almoço com Marcelo Antunes sexta ao meio-dia", "acao", ["Marcelo", "Antunes"], manter=["almoço"]),
    pedido("ped-lembrete-pessoa", "relogio", "Me lembra amanhã de devolver o livro da Patrícia Lemos", "acao", ["Patrícia", "Lemos"], manter=["livro"]),
    pedido("ped-pix-pessoa", "outro", "Copia a chave pix do Igor que tá na conversa", "acao", ["Igor"], manter=["pix"]),
    pedido("ped-insta-bloq", "instagram", "Bloqueia a Fernanda Rocha no Instagram", "acao", ["Fernanda", "Rocha"], manter=["Instagram"]),
    pedido("ped-insta-story", "instagram", "Esconde meus stories da Débora", "acao|mista", ["Débora"], manter=["stories"]),
    pedido("ped-rota-casa", "maps", "Traça a rota até a casa da Renata", "acao|mista", ["Renata"], manter=["rota"]),
    pedido("ped-email-pessoa", "gmail", "Responde o e-mail do Caio Menezes dizendo que recebi o contrato", "acao", ["Caio", "Menezes"], manter=["contrato"]),
    pedido("ped-nome-comum", "whatsapp", "manda pra Rosa que a encomenda chegou", "acao", ["Rosa"], manter=["encomenda"],
           nota="nome que também é palavra comum"),
    pedido("ped-sobrenome-so", "telefone", "liga pro Kato", "acao", ["Kato"]),
    # --- ação com pessoa, em inglês (o run.sh manda pedidos em inglês) ---
    pedido("ped-en-msg", "whatsapp", "Send a message to Lívia saying I'm running late", "acao", ["Lívia"], manter=["running late"]),
    pedido("ped-en-call", "telefone", "Call Renata Oliveira", "acao", ["Renata", "Oliveira"]),
    pedido("ped-en-fora", "whatsapp", "Text Gustavo Pereira that dinner is at 8", "acao", ["Gustavo", "Pereira"], manter=["dinner"]),
    pedido("ped-en-minusc", "whatsapp", "tell igor i'll pick him up", "acao", ["igor"], manter=["pick him up"]),
    pedido("ped-en-follow", "instagram", "Unfollow Larissa Prado on Instagram", "acao", ["Larissa", "Prado"], manter=["Instagram"]),
    pedido("ped-en-email", "gmail", "Forward the last email from Thaís Carvalho to Bruno", "acao", ["Thaís", "Carvalho", "Bruno"], manter=["email"]),
    pedido("ped-en-calendar", "agenda", "Add a meeting with Marcelo tomorrow at 10", "acao", ["Marcelo"], manter=["meeting"]),
    pedido("ped-en-share", "chrome", "Share this page with Ana Júlia on WhatsApp", "acao", ["Ana", "Júlia"], manter=["WhatsApp"]),
    # --- negócios, instituições e lugares ---
    pedido("ped-neg-msg", "whatsapp", "Manda mensagem pra Academia Fortis perguntando o horário de sábado", "acao", ["Fortis"], manter=["Academia"],
           nota="negócio do cofre numa ação: o nome sai trocado"),
    pedido("ped-neg-pesquisa", "chrome", "Qual o horário da Academia Fortis no sábado?", "pesquisa", liberar=["Academia Fortis"],
           nota="o mesmo negócio numa pesquisa: precisa sair real"),
    pedido("ped-neg-endereco", "maps", "Qual o endereço da Pizzaria Bella Napoli?", "pesquisa", liberar=["Bella Napoli"]),
    pedido("ped-neg-cardapio", "chrome", "Vê o cardápio da Pizzaria Bella Napoli e manda pra Lívia", "mista", ["Lívia"], liberar=["Bella Napoli"]),
    pedido("ped-neg-fora", "chrome", "Que horas abre a Padaria Pão Dourado no Sudoeste?", "pesquisa", liberar=["Pão Dourado", "Sudoeste"]),
    pedido("ped-inst", "chrome", "Quando começa o período de matrícula da UnB?", "pesquisa", liberar=["UnB"], manter=["matrícula"]),
    pedido("ped-orgao", "chrome", "Como agendar atendimento no Na Hora de Taguatinga?", "pesquisa", liberar=["Taguatinga"]),
    pedido("ped-lugar", "maps", "Quanto tempo de carro até o Parque da Cidade?", "pesquisa|acao|mista", liberar=["Parque da Cidade"]),
    pedido("ped-loja-app", "outro", "Pede uma pizza grande na Bella Napoli pelo iFood", "acao", manter=["iFood", "pizza"],
           nota="pedir no app não é pesquisa: o nome pode sair trocado, mas iFood fica"),
    pedido("ped-pet", "whatsapp", "Agenda banho pro Thor no Pet Shop Bicho Bom", "acao", manter=["banho"],
           nota="Thor é o cachorro; cofre com 'Bom' testa excesso em outras palavras"),
    pedido("ped-en-neg", "chrome", "What time does Fortis Gym close today?", "pesquisa", liberar=["Fortis"]),
    pedido("ped-en-place", "maps", "Directions to Brasília airport", "pesquisa|acao|mista", liberar=["Brasília"]),
    pedido("ped-en-review", "chrome", "Look up reviews for Café Lamparina in Asa Norte", "pesquisa", liberar=["Lamparina", "Asa Norte"]),
    # --- pessoas famosas (mascaradas como qualquer pessoa desde 2026-10-18), marcas, apps ---
    pedido("ped-pub-noticia", "chrome", "Pesquise notícias sobre o Alexandre de Moraes", "pesquisa", ["Alexandre", "Moraes"],
           nota="famoso também é mascarado: o provedor planeja com o nome falso e o aparelho digita o real"),
    pedido("ped-pub-musica", "spotify", "Toca Marisa Monte no Spotify", "acao", ["Marisa", "Monte"], manter=["Spotify"]),
    pedido("ped-pub-video", "youtube", "Procura o último vídeo do Casimiro no YouTube", "acao|pesquisa|mista", ["Casimiro"],
           manter=["YouTube"]),
    pedido("ped-en-pub", "youtube", "Play the latest Anitta music video", "acao|pesquisa|mista", ["Anitta"]),
    pedido("ped-marca", "chrome", "Quanto custa o Galaxy S25 na Amazon?", "pesquisa", manter=["Galaxy S25", "Amazon"]),
    pedido("ped-pub-e-amigo", "whatsapp", "Manda pro Caio o link da entrevista do Neymar", "mista|acao", ["Caio", "Neymar"],
           nota="todo nome de gente é mascarado, mesmo o de um famoso: mascarar um famoso custa pouco, e um modelo "
                "pequeno que aprende a soltar alguns nomes deixa passar pessoas"),
    # --- sem nome próprio ---
    pedido("ped-cfg-escuro", "configuracoes", "Liga o modo escuro", "acao", manter=["modo escuro"]),
    pedido("ped-cfg-wifi", "configuracoes", "Desliga o Wi-Fi e liga o Bluetooth", "acao", manter=["Wi-Fi", "Bluetooth"]),
    pedido("ped-en-cfg", "configuracoes", "Turn on the eye comfort shield", "acao", manter=["eye comfort shield"]),
    pedido("ped-en-bat", "configuracoes", "Turn on power saving mode", "acao", manter=["power saving"]),
    pedido("ped-camera", "camera", "Abre a câmera frontal e liga o timer de 3 segundos", "acao", manter=["câmera", "timer"]),
    pedido("ped-calc", "calculadora", "Quanto é 15% de 230?", "pesquisa|acao", manter=["15%", "230"]),
    pedido("ped-dolar", "chrome", "Quanto tá o euro hoje?", "pesquisa", manter=["euro"]),
    pedido("ped-tempo", "chrome", "Vai chover amanhã em Brasília?", "pesquisa", liberar=["Brasília"]),
    pedido("ped-en-timer", "relogio", "Set a timer for 10 minutes", "acao", manter=["timer"]),
    pedido("ped-notion", "notion", "Cria uma página no Notion chamada Lista de compras", "acao", manter=["Notion", "Lista de compras"]),
    pedido("ped-en-notion", "notion", "Add milk to my shopping list in Notion", "acao", manter=["milk", "Notion"]),
    pedido("ped-yt", "youtube", "Pesquisa receita de pão de queijo no YouTube", "acao|pesquisa|mista", manter=["pão de queijo", "YouTube"]),
    # --- dados das regras fixas ---
    pedido("ped-email-cofre", "gmail", "Manda o relatório pro livia.bastos@gmail.com", "acao", outros=["livia.bastos@gmail.com"], manter=["relatório"]),
    pedido("ped-email-fora", "gmail", "Cadastra o e-mail ricardo.nunes@empresa.com.br na lista", "acao", ["ricardo", "nunes"], outros=["ricardo.nunes@empresa.com.br"]),
    pedido("ped-tel", "telefone", "Liga pro 61 98456-2210", "acao", outros=["98456-2210"]),
    pedido("ped-tel-fora", "whatsapp", "Salva o número (21) 99876-5432 como Leonardo", "acao", ["Leonardo"], outros=["99876-5432"]),
    pedido("ped-cpf", "outro", "Preenche o CPF 529.982.247-25 no formulário", "acao", outros=["529.982.247-25"], manter=["formulário"]),
    pedido("ped-handle", "instagram", "Segue o @gabi.martins_ no Instagram", "acao", usuarios=["gabi.martins_"], manter=["Instagram"]),
    pedido("ped-en-handle", "instagram", "Send a DM to @rafa_souza88 saying thanks", "acao", usuarios=["rafa_souza88"], manter=["thanks"]),
    pedido("ped-handle-sem-arroba", "instagram", "abre o perfil do joao.vitor.silva no insta", "acao", usuarios=["joao.vitor.silva"],
           nota="nome de usuário sem @: só a IA acha"),
    # --- apps mais usados que não tinham casos ---
    pedido("ped-nf-perfil", "netflix", "Coloca o próximo episódio no perfil da Lívia na Netflix", "acao", ["Lívia"],
           manter=["episódio", "Netflix"]),
    pedido("ped-olx-resp", "olx", "Responde a Daniela Prates na OLX dizendo que o sofá ainda está disponível", "acao",
           ["Daniela", "Prates"], manter=["OLX", "sofá"]),
    pedido("ped-ml-busca", "mercado-livre", "Procura no Mercado Livre uma bicicleta aro 29 até 1500 reais", "acao|pesquisa",
           manter=["Mercado Livre", "bicicleta aro 29"]),
    pedido("ped-en-x", "x", "Repost the latest post from Larissa Prado on X", "acao", ["Larissa", "Prado"], manter=["Repost"]),
    pedido("ped-en-ytm", "youtube-music", "Play Bruno's Pagode 90 playlist on YouTube Music", "acao", ["Bruno"],
           manter=["Pagode 90", "YouTube Music"]),
]

TELAS = [
    # --- WhatsApp ---
    tela("wa-lista", "whatsapp", "WhatsApp › Conversas", [
        "WhatsApp", "Ask Meta AI or Search", "All", "Unread", "Favourites", "Groups",
        "Lívia Bastos", "Ok, te espero lá", "10:42", "Família 💛", "Tia Cida: Photo", "09:15",
        "Henrique Albuquerque", "Valeu!", "Yesterday", "Chats", "Updates", "Communities", "Calls"],
        pessoas=["Lívia Bastos", "Cida", "Henrique Albuquerque"],
        manter=["Ask Meta AI or Search", "Unread", "Favourites", "Updates", "Communities"]),
    tela("wa-conversa", "whatsapp", "WhatsApp › conversa com contato", [
        "Navigate up", "Caio Menezes", "online", "Video call", "Voice call", "More options",
        "Bom dia! Conseguiu ver o orçamento?", "08:01", "Vi sim, amanhã te passo", "08:05", "Message", "Attach", "Camera", "Voice message"],
        pessoas=["Caio Menezes"], manter=["online", "Video call", "orçamento", "Attach", "Voice message"],
        nota="'Bom' está no cofre (Pet Shop Bicho Bom): testa excesso"),
    tela("wa-grupo-msgs", "whatsapp", "WhatsApp › grupo", [
        "Futebol de quarta ⚽", "Renata, Bruno, Igor, You", "~ Duda Teixeira", "quem leva a bola?", "Igor Santana", "eu levo",
        "~ Wesley", "tô dentro", "You", "beleza", "Message"],
        pessoas=["Renata", "Bruno", "Igor Santana", "Duda Teixeira", "Wesley"], manter=["Futebol de quarta", "quem leva a bola?"]),
    tela("wa-contato-info", "whatsapp", "WhatsApp › dados do contato", [
        "Contact info", "Gustavo Pereira", "+55 61 99812-3344", "Audio", "Video", "Pay", "Search",
        "Hey there! I am using WhatsApp.", "Media, links and docs", "Starred messages", "Block Gustavo Pereira", "Report Gustavo Pereira"],
        pessoas=["Gustavo Pereira"], outros=["99812-3344"], manter=["Contact info", "Media, links and docs", "Starred messages"]),
    tela("wa-atualizacoes", "whatsapp", "WhatsApp › Atualizações", [
        "Updates", "Status", "Add status", "Recent updates", "Marcelo Antunes", "12 minutes ago", "Patrícia Lemos", "Today, 08:30",
        "Channels", "Explore", "Jornal Metrópoles", "Follow"],
        pessoas=["Marcelo Antunes", "Patrícia Lemos"], manter=["Recent updates", "Channels", "Metrópoles"]),
    tela("wa-encaminhar", "whatsapp", "WhatsApp › encaminhar mensagem", [
        "Forward to…", "Search", "Frequently contacted", "Thaís Carvalho", "Bruno Kato", "Recent chats", "Raquel Duarte", "Trabalho - TI", "Send"],
        pessoas=["Thaís Carvalho", "Bruno Kato", "Raquel Duarte"], manter=["Frequently contacted", "Recent chats", "Trabalho"]),
    tela("wa-chamadas", "whatsapp", "WhatsApp › Ligações", [
        "Calls", "Favourites", "Add favourite", "Recent", "Vó Nena", "Incoming, yesterday 19:02", "Leonardo Teles", "Missed, 14 October"],
        pessoas=["Nena", "Leonardo Teles"], manter=["Add favourite", "Incoming", "Missed"]),
    tela("wa-mensagem-texto-pessoa", "whatsapp", "WhatsApp › conversa com nomes no texto", [
        "Ana Júlia Ribeiro", "Você viu que a Camila e o Rodrigo terminaram?", "Não acredito kkkk", "A Bianca que me contou"],
        pessoas=["Ana Júlia Ribeiro", "Camila", "Rodrigo", "Bianca"], manter=["Não acredito"]),
    tela("wa-pix", "whatsapp", "WhatsApp › conversa com chave pix", [
        "Fábio Mecânico", "Fica 350 o serviço", "Chave pix: fabio.oficina@gmail.com", "Ou CPF 390.533.447-05"],
        pessoas=["Fábio"], outros=["fabio.oficina@gmail.com", "390.533.447-05"], manter=["serviço", "Chave pix"]),
    tela("wa-en-chat", "whatsapp", "WhatsApp › conversa em inglês", [
        "Larissa Prado", "last seen today at 11:20", "Are we still on for Saturday?", "Yes! Bring Mateo too", "Message"],
        pessoas=["Larissa Prado", "Mateo"], manter=["last seen today", "Saturday"]),
    # --- Instagram ---
    tela("ig-perfil-outro", "instagram", "Instagram › perfil de outra pessoa", [
        "juliana.reis_", "Juliana Reis", "Designer | Brasília", "1,204", "followers", "387", "following", "Follow", "Message",
        "Followed by bruno.kato and 12 others"],
        pessoas=["Juliana Reis"], usuarios=["juliana.reis_", "bruno.kato"], manter=["Designer", "followers", "Follow", "Message"]),
    tela("ig-lista-seguindo", "instagram", "Instagram › perfil › Following", [
        "Following", "Search", "Sort by Default", "lari.prado", "Larissa Prado", "Following", "teo.andrade_", "Teo",
        "mp.fotografia", "Marina | Fotografia", "cafe.lamparina", "Café Lamparina", "dudateixeira99", "Duda T."],
        pessoas=["Larissa Prado", "Teo", "Marina", "Duda"], usuarios=["lari.prado", "teo.andrade_", "dudateixeira99", "mp.fotografia"],
        manter=["Sort by Default"],
        nota="imita o caso ig-seguindo da suíte: nomes de usuário fora do cofre que a Gemma já deixou passar"),
    tela("ig-seguidores", "instagram", "Instagram › perfil › Followers", [
        "Followers", "All followers", "rodrigo_alves.89", "Rodrigo Alves", "Remove", "biancaferraz", "Bianca Ferraz", "Remove",
        "pedrinho.games", "Pedrinho 🎮", "Remove"],
        pessoas=["Rodrigo Alves", "Bianca Ferraz", "Pedrinho"], usuarios=["rodrigo_alves.89", "biancaferraz", "pedrinho.games"],
        manter=["All followers", "Remove"]),
    tela("ig-feed", "instagram", "Instagram › Início", [
        "Instagram", "Your story", "gabi.martins_", "rafa_souza88", "camila.reis", "gabi.martins_", "Brasília, Distrito Federal",
        "Liked by caio.menezes and others", "gabi.martins_ Domingo de sol com a Lu e o Beto ☀️", "View all 23 comments", "2 hours ago"],
        pessoas=["Lu", "Beto"], usuarios=["gabi.martins_", "rafa_souza88", "camila.reis", "caio.menezes"],
        manter=["Your story", "View all 23 comments"],
        nota="'Lu' tem 2 letras e não é mascarado por regra; o caso aceita só 'Beto'"),
    tela("ig-comentarios", "instagram", "Instagram › comentários de um post", [
        "Comments", "carol_dias", "que lindaaa 😍", "Reply", "matheus.lb", "@carol_dias verdade", "Reply",
        "Pedro Henrique Sá", "saudades de vcs", "Add a comment for gabi.martins_"],
        pessoas=["Pedro Henrique Sá"], usuarios=["carol_dias", "matheus.lb", "gabi.martins_"], manter=["Comments", "Reply", "saudades"]),
    tela("ig-notificacoes", "instagram", "Instagram › Notificações", [
        "Notifications", "New", "teo.andrade_ started following you.", "1h", "Follow back",
        "This week", "lari.prado and rodrigo_alves.89 liked your photo.", "3d", "Suggested for you", "beatriz.coutinho", "Beatriz Coutinho"],
        pessoas=["Beatriz Coutinho"], usuarios=["teo.andrade_", "lari.prado", "rodrigo_alves.89", "beatriz.coutinho"],
        manter=["Follow back", "This week", "Suggested for you"]),
    tela("ig-dm-lista", "instagram", "Instagram › Mensagens", [
        "Messages", "Requests", "Search", "Notes", "Larissa Prado", "Sent 2h ago", "Grupo Viagem 🏖️", "Igor: bora fechar?",
        "matheus.lb", "Seen", "Active now"],
        pessoas=["Larissa Prado", "Igor"], usuarios=["matheus.lb"], manter=["Requests", "Notes", "Viagem", "Active now"]),
    tela("ig-privada", "instagram", "Instagram › Configurações › Privacidade da conta", [
        "Account privacy", "Private account", "When your account is public, your profile and posts can be seen by anyone.",
        "Switch to private account?", "Only your followers will be able to see your photos and videos.", "Switch to private", "Cancel"],
        manter=["Account privacy", "Private account", "Switch to private account?", "Switch to private", "Cancel"],
        nota="a Gemma já marcou 'Switch to private account?' como pessoa"),
    tela("ig-meu-perfil", "instagram", "Instagram › meu perfil", [
        "eu.mesmo_dev", "Edit profile", "Share profile", "Posts", "12", "Followers", "180", "Following", "203",
        "Pedro Lucas", "Dev | café | Brasília", "Story highlights"],
        pessoas=["Pedro Lucas"], usuarios=["eu.mesmo_dev"], manter=["Edit profile", "Share profile", "Story highlights"],
        nota="os próprios nomes de usuário não estão no cofre"),
    tela("ig-busca-recentes", "instagram", "Instagram › Busca", [
        "Search", "Recent", "See all", "mp.fotografia", "Marina | Fotografia • Following", "joao.vitor.silva", "João Vitor",
        "#brasilia", "Clear all"],
        pessoas=["Marina", "João Vitor"], usuarios=["mp.fotografia", "joao.vitor.silva"], manter=["Recent", "See all", "Clear all"]),
    tela("ig-amigos-proximos", "instagram", "Instagram › Configurações › Amigos próximos", [
        "Close Friends", "We don't send notifications when you edit your close friends list.", "Search",
        "thais.carvalho", "Thaís Carvalho", "igor.santana", "Igor Santana", "Done"],
        pessoas=["Thaís Carvalho", "Igor Santana"], usuarios=["thais.carvalho", "igor.santana"], manter=["Close Friends", "Done"]),
    # --- Gmail ---
    tela("gm-caixa", "gmail", "Gmail › Caixa de entrada", [
        "Search in mail", "Primary", "Marcelo Antunes", "Proposta revisada", "Segue em anexo a proposta com os ajustes…", "10:12",
        "Débora RH", "Holerite de setembro", "Oct 14", "Nubank", "Sua fatura fechou", "Oct 13", "Compose"],
        pessoas=["Marcelo Antunes", "Débora"], manter=["Primary", "Proposta revisada", "Holerite", "Nubank", "Compose"]),
    tela("gm-email", "gmail", "Gmail › um e-mail aberto", [
        "Proposta revisada", "Inbox", "Marcelo Antunes", "to me", "Oi Pedro, conforme falamos com a Sandra ontem, segue a proposta.",
        "marcelo.antunes@construtora-alfa.com.br", "Reply", "Forward"],
        pessoas=["Marcelo Antunes", "Pedro", "Sandra"], outros=["marcelo.antunes@construtora-alfa.com.br"], manter=["Inbox", "Reply", "Forward"]),
    tela("gm-novo-email", "gmail", "Gmail › novo e-mail", [
        "Compose", "From", "pedro.dev.teste@gmail.com", "To", "caio.menezes@outlook.com", "Subject", "Reunião de terça", "Compose email"],
        outros=["pedro.dev.teste@gmail.com", "caio.menezes@outlook.com"], manter=["Subject", "Reunião de terça"]),
    tela("gm-promo", "gmail", "Gmail › Promoções", [
        "Promotions", "Amazon.com.br", "Ofertas para você, Pedro", "iFood", "Cupom de R$ 15 no seu próximo pedido", "Spotify", "Premium por 3 meses"],
        pessoas=["Pedro"], manter=["Amazon.com.br", "iFood", "Spotify", "Premium"]),
    # --- Telefone e Contatos ---
    tela("tel-recentes", "telefone", "Telefone › Recentes", [
        "Recents", "Today", "Renata Oliveira", "Mobile, 2 min", "(61) 3344-9087", "Brasília", "Unknown", "Yesterday",
        "Seu Raimundo Porteiro", "Missed call", "Keypad", "Contacts"],
        pessoas=["Renata Oliveira", "Raimundo"], outros=["3344-9087"], manter=["Recents", "Missed call", "Keypad"]),
    tela("tel-chamada", "telefone", "Telefone › em chamada", [
        "Igor Santana", "Calling…", "+55 61 99234-1188", "Record", "Video call", "Bluetooth", "Speaker", "Mute", "Keypad", "End call"],
        pessoas=["Igor Santana"], outros=["99234-1188"], manter=["Calling", "Speaker", "Mute", "End call"]),
    tela("ct-lista", "contatos", "Contatos › lista", [
        "Contacts", "Search", "My profile", "Pedro Lucas", "Favourites", "Lívia Bastos", "Vó Nena", "A", "Academia Fortis",
        "Ana Júlia Ribeiro", "Alessandra Vieira", "B", "Bruno Kato"],
        pessoas=["Pedro Lucas", "Lívia Bastos", "Nena", "Ana Júlia Ribeiro", "Alessandra Vieira", "Bruno Kato"],
        manter=["My profile", "Favourites", "Academia"]),
    tela("ct-detalhe", "contatos", "Contatos › um contato", [
        "Alessandra Vieira", "Mobile", "+55 61 98877-6655", "Email", "ale.vieira@hotmail.com", "Birthday", "March 12",
        "Call", "Message", "Video call", "Edit", "Share"],
        pessoas=["Alessandra Vieira"], outros=["98877-6655", "ale.vieira@hotmail.com"], manter=["Birthday", "Edit", "Share"]),
    # --- Mensagens (SMS) ---
    tela("sms-lista", "mensagens", "Mensagens › conversas", [
        "Messages", "Conversations", "Contacts", "29872", "Seu código de verificação é 482913", "Now",
        "Renata Oliveira", "Chego em 10 min", "Claro", "Sua fatura de outubro está disponível"],
        pessoas=["Renata Oliveira"], manter=["Conversations", "código de verificação", "Claro", "fatura"]),
    tela("sms-banco", "mensagens", "Mensagens › SMS de banco", [
        "Bradesco", "Compra aprovada no cartão final 4421 R$ 89,90 MERCADO BOM PRECO", "Pix recebido de Marcos Vinícius Teixeira R$ 50,00"],
        pessoas=["Marcos Vinícius Teixeira"], manter=["Compra aprovada", "MERCADO", "Pix recebido"],
        nota="'BOM' em maiúsculas casa com o cofre (Bicho Bom)"),
    # --- Chrome ---
    tela("ch-busca", "chrome", "Chrome › resultados de busca", [
        "Search or type URL", "academia fortis horário sábado", "All", "Maps", "Images", "Academia Fortis - Asa Sul",
        "Aberto · Fecha às 22:00", "(61) 3201-4455", "Directions", "Call"],
        manter=["Search or type URL", "Directions", "Asa Sul"],
        nota="negócio liberado pelo pedido de pesquisa: o pedido ped-neg-pesquisa vem antes nesse fluxo; aqui sem pedido, o telefone do negócio pode sair trocado"),
    tela("ch-historico", "chrome", "Chrome › histórico", [
        "History", "Search your history", "Today", "Larissa Prado (@lari.prado) • Instagram photos and videos", "instagram.com",
        "como fazer bolo de cenoura - Pesquisa Google", "google.com", "Clear browsing data"],
        pessoas=["Larissa Prado"], usuarios=["lari.prado"], manter=["Search your history", "bolo de cenoura", "Clear browsing data"]),
    tela("ch-formulario", "chrome", "Chrome › página de formulário (site de teste)", [
        "127.0.0.1:8765/formulario.html", "Formulário de contato", "Nome", "Email", "Telefone", "Mensagem", "Enviar"],
        manter=["formulario", "Formulário de contato", "Nome", "Email", "Telefone", "Mensagem", "Enviar"],
        nota="a Gemma já marcou a URL como pessoa e 'email' e 'telefone' passaram a sair trocados"),
    tela("ch-abas-abertas", "chrome", "Chrome › abas abertas", [
        "Search your tabs", "3", "Tabs", "Incognito tabs", "Notícias de Brasília - Metrópoles", "Perfil de Rodrigo Alves | LinkedIn",
        "Receita de lasanha", "New tab"],
        pessoas=["Rodrigo Alves"], manter=["Incognito tabs", "Metrópoles", "LinkedIn", "Receita de lasanha", "New tab"]),
    tela("ch-noticia", "chrome", "Chrome › notícia", [
        "metropoles.com", "Lula sanciona lei do orçamento", "Por Mariana Costa", "Atualizado às 14:02",
        "O presidente Luiz Inácio Lula da Silva sancionou nesta quarta…", "Leia também"],
        pessoas=["Lula", "Luiz Inácio Lula da Silva", "Mariana Costa"], manter=["orçamento", "Leia também"],
        nota="famosos e a autora da notícia são mascarados como qualquer pessoa"),
    # --- YouTube ---
    tela("yt-inicio", "youtube", "YouTube › Início", [
        "YouTube", "Search", "Cast", "Notifications", "All", "Music", "Gaming", "Receita de pão de queijo mineiro",
        "Ana Maria Braga", "1.2M views • 2 years ago", "Shorts", "Subscriptions", "You"],
        manter=["Receita de pão de queijo", "Ana Maria Braga", "Subscriptions"]),
    tela("yt-comentarios", "youtube", "YouTube › comentários de um vídeo", [
        "Comments", "Sort comments", "@marcosoliveira3421", "fiz e ficou ótimo!", "@luana.fit", "minha vó fazia assim",
        "Reply", "Add a comment…"],
        usuarios=["@marcosoliveira3421", "@luana.fit"], manter=["Sort comments", "Reply", "Add a comment"]),
    tela("yt-voce", "youtube", "YouTube › Você", [
        "Pedro Lucas", "@pedrolucas-dev", "View channel", "History", "Playlists", "Watch later", "Liked videos", "Your videos", "Downloads"],
        pessoas=["Pedro Lucas"], usuarios=["@pedrolucas-dev"], manter=["View channel", "Watch later", "Liked videos"]),
    # --- Google Maps e Waze ---
    tela("mp-rota", "maps", "Maps › rota", [
        "Your location", "Casa da Renata", "Driving", "18 min", "7.4 km", "via Eixo Monumental", "Start", "Steps"],
        pessoas=["Renata"], manter=["Your location", "Driving", "Eixo Monumental", "Start"]),
    tela("mp-salvos", "maps", "Maps › Você › Salvos", [
        "Saved", "Your lists", "Favourites", "Want to go", "Labelled", "Home", "Work", "Casa da Vó Nena", "Academia Fortis"],
        pessoas=["Nena"], manter=["Your lists", "Want to go", "Labelled"]),
    tela("mp-lugar", "maps", "Maps › um lugar", [
        "Café Lamparina", "4.7", "(1,203)", "Coffee shop", "Open · Closes 8 PM", "Directions", "Call", "Reviews",
        "Tatiana Mello", "Ótimo café, atendimento do Wagner foi excelente"],
        pessoas=["Tatiana Mello", "Wagner"], manter=["Café Lamparina", "Coffee shop", "Directions", "Reviews"]),
    tela("wz-destinos", "waze", "Waze › início (em português)", [
        "HAMBURGER_BUTTON", "Casa", "Trabalho", "Novo", "Recentes", "Casa do Caio", "SQN 210 Bloco C",
        "Shopping Conjunto Nacional", "SCN Q 6, Asa Norte", "START_STATE_SEARCH_FIELD", "km/h"],
        pessoas=["Caio"], manter=["HAMBURGER_BUTTON", "Recentes", "Shopping Conjunto Nacional", "Trabalho"],
        nota="endereço em texto livre não é detectado (limite conhecido); aqui só o nome é conferido. Rótulos e etiquetas "
             "conferidos no aparelho em 2026-10-17"),
    # --- Configurações ---
    tela("cfg-inicio", "configuracoes", "Configurações › início", [
        "Settings", "Pedro Lucas", "Samsung account", "Connections", "Wi-Fi • Bluetooth • SIM manager", "Connected devices",
        "Modes and Routines", "Sounds and vibration", "Notifications", "Display", "Battery"],
        pessoas=["Pedro Lucas"], manter=["Samsung account", "Connections", "Modes and Routines", "Display", "Battery"]),
    tela("cfg-conta", "configuracoes", "Configurações › conta Samsung", [
        "Samsung account", "Pedro Lucas", "pedro.dev.teste@gmail.com", "Profile information", "Security and privacy", "Sign out"],
        pessoas=["Pedro Lucas"], outros=["pedro.dev.teste@gmail.com"], manter=["Profile information", "Security and privacy", "Sign out"]),
    tela("cfg-bluetooth", "configuracoes", "Configurações › Bluetooth", [
        "Bluetooth", "On", "Paired devices", "Galaxy Buds2 Pro", "JBL Flip 6", "Carro do Bruno", "Available devices", "Scan"],
        pessoas=["Bruno"], manter=["Paired devices", "Galaxy Buds2 Pro", "JBL Flip 6", "Available devices"]),
    tela("cfg-wifi", "configuracoes", "Configurações › Wi-Fi", [
        "Wi-Fi", "On", "Current network", "Casa_5G", "Connected", "Available networks", "Lívia 2.4G", "NET_2G8A1F", "Add network"],
        pessoas=["Lívia"], manter=["Current network", "Available networks", "Add network"]),
    tela("cfg-sobre-tela", "configuracoes", "Configurações › Sobre o telefone", [
        "About phone", "Pedro's S23+", "Edit", "Phone number", "+55 61 99123-4567", "Model name", "Galaxy S23+",
        "Serial number", "R5CW30ABC1D", "Software information", "Battery information"],
        pessoas=["Pedro"], outros=["99123-4567"], manter=["Model name", "Galaxy S23+", "Software information"]),
    tela("cfg-tela", "configuracoes", "Configurações › Tela", [
        "Display", "Light", "Dark", "Dark mode settings", "Brightness", "Adaptive brightness", "Eye comfort shield",
        "Screen mode", "Font size and style", "Screen zoom", "Edge panels"],
        manter=["Dark mode settings", "Adaptive brightness", "Eye comfort shield", "Edge panels"]),
    tela("cfg-notif", "configuracoes", "Configurações › Notificações", [
        "Notifications", "App notifications", "Recently sent", "WhatsApp", "Most recent", "Instagram", "Gmail",
        "Lock screen notifications", "Do not disturb"],
        manter=["App notifications", "WhatsApp", "Instagram", "Lock screen notifications", "Do not disturb"]),
    tela("cfg-contas", "configuracoes", "Configurações › Contas e backup › Gerenciar contas", [
        "Manage accounts", "Google", "pedro.dev.teste@gmail.com", "WhatsApp", "Telegram", "Samsung account", "Add account", "Auto sync data"],
        outros=["pedro.dev.teste@gmail.com"], manter=["Manage accounts", "Add account", "Auto sync data"]),
    # --- Câmera, Galeria, Calculadora, Relógio, Agenda ---
    tela("cam-principal", "camera", "Câmera › modo foto", [
        "Quick controls", "Flash", "Timer", "Ratio", "Motion photo", "Filters", "Photo", "Video", "Portrait", "More", "Gallery", "Switch camera"],
        manter=["Quick controls", "Motion photo", "Portrait", "Switch camera"]),
    tela("gal-album", "galeria", "Galeria › álbuns", [
        "Albums", "Camera", "Screenshots", "WhatsApp Images", "Aniversário da Lívia", "Viagem Chapada 2025", "Favourites", "Create album"],
        pessoas=["Lívia"], manter=["Screenshots", "WhatsApp Images", "Aniversário", "Viagem Chapada", "Create album"]),
    tela("gal-pessoas", "galeria", "Galeria › Pessoas e animais", [
        "People and pets", "Caio Menezes", "Ana Júlia", "Add name", "Thor", "Show hidden people"],
        pessoas=["Caio Menezes", "Ana Júlia"], manter=["People and pets", "Add name", "Show hidden people"]),
    tela("calc", "calculadora", "Calculadora", [
        "Calculator", "230×15%", "34.5", "History", "Unit converter", "Scientific", "Clear", "Equal"],
        manter=["Calculator", "Unit converter", "Scientific"]),
    tela("rel-alarmes", "relogio", "Relógio › Alarmes", [
        "Alarm", "06:30", "Mon, Tue, Wed, Thu, Fri", "Academia", "08:00", "Buscar a Lívia na escola", "Add alarm", "World clock", "Stopwatch", "Timer"],
        pessoas=["Lívia"], manter=["Mon, Tue", "Academia", "Buscar", "escola", "Add alarm", "Stopwatch"]),
    tela("ag-dia", "agenda", "Agenda › dia", [
        "October", "Thu 16", "Almoço com Marcelo Antunes", "12:00 - 13:00", "Reunião de projeto", "15:00 - 16:00",
        "Aniversário da Renata", "All day", "Add event"],
        pessoas=["Marcelo Antunes", "Renata"], manter=["Almoço", "Reunião de projeto", "Aniversário", "All day", "Add event"]),
    tela("ag-evento", "agenda", "Agenda › um evento", [
        "Reunião de projeto", "Thursday, 16 October 2026", "15:00 - 16:00", "Invitees", "thais.carvalho@empresa.com.br",
        "Rodrigo Alves", "Location", "Sala 3", "Edit", "Delete"],
        pessoas=["Rodrigo Alves"], outros=["thais.carvalho@empresa.com.br"], manter=["Invitees", "Location", "Sala 3"]),
    # --- Notion ---
    tela("no-inicio", "notion", "Notion › início", [
        "Pedro's Notion", "Search", "Inbox", "Home", "Recents", "Lista de compras", "Notas da reunião com Caio", "Planejamento 2026",
        "Private", "Shared", "Projeto TCC (Thaís, Igor)", "New page"],
        pessoas=["Caio", "Thaís", "Igor"], manter=["Inbox", "Recents", "Lista de compras", "Planejamento 2026", "Private", "Shared", "New page"]),
    tela("no-pagina", "notion", "Notion › página aberta", [
        "Notas da reunião", "Participantes: Marcelo, Sandra e Wesley", "Decidimos adiar a entrega para novembro.",
        "Responsável: Sandra Moura", "Add a comment", "Share"],
        pessoas=["Marcelo", "Sandra", "Wesley", "Moura"], manter=["Notas da reunião", "Participantes", "entrega", "Responsável", "Share"]),
    tela("no-compartilhar", "notion", "Notion › compartilhar página", [
        "Share", "Invite", "Email or group, separated by commas", "Pedro Lucas", "Full access", "Thaís Carvalho",
        "thais.carvalho@empresa.com.br", "Can edit", "Copy link"],
        pessoas=["Pedro Lucas", "Thaís Carvalho"], outros=["thais.carvalho@empresa.com.br"], manter=["Invite", "Full access", "Can edit", "Copy link"]),
    # --- Spotify, Play Store, iFood, Uber, Telegram, LinkedIn ---
    tela("sp-inicio", "spotify", "Spotify › início", [
        "Good evening", "Liked Songs", "Daily Mix 1", "Marisa Monte", "Discover Weekly", "Made for Pedro Lucas", "Jump back in", "Search", "Your Library"],
        pessoas=["Pedro Lucas", "Marisa Monte"], manter=["Liked Songs", "Discover Weekly", "Your Library"],
        nota="o artista também é mascarado, como o nome do usuário no título da seção"),
    tela("sp-playlist", "spotify", "Spotify › playlist compartilhada", [
        "Churrasco 🔥", "Bruno Kato, Larissa Prado and you", "3h 12min", "Shuffle", "Pagode do Thiaguinho", "Thiaguinho", "Added by bruno.kato"],
        pessoas=["Bruno Kato", "Larissa Prado", "Thiaguinho"], usuarios=["bruno.kato"], manter=["Shuffle"]),
    tela("ps-app", "playstore", "Play Store › página de app", [
        "Google Play", "WhatsApp Messenger", "WhatsApp LLC", "4.3", "Install", "Ratings and reviews", "Carla Mendes",
        "App bom mas trava às vezes", "Was this review helpful?"],
        pessoas=["Carla Mendes"], manter=["WhatsApp Messenger", "Ratings and reviews", "Was this review helpful?"]),
    tela("if-pedido", "ifood", "iFood › acompanhar pedido", [
        "Pedido #4821", "Pizzaria Bella Napoli", "Saiu para entrega", "Entregador: Josué", "Moto • ABC1D23", "Ajuda", "Chat com a loja"],
        pessoas=["Josué"], manter=["Saiu para entrega", "Entregador", "Ajuda", "Chat com a loja"]),
    tela("ub-corrida", "uber", "Uber › corrida", [
        "Your driver is arriving", "Wellington", "4.92", "Toyota Corolla • Gray", "QTP5E21", "Contact", "Safety", "Share trip status"],
        pessoas=["Wellington"], manter=["Your driver is arriving", "Toyota Corolla", "Safety", "Share trip status"]),
    tela("tg-lista", "telegram", "Telegram › conversas", [
        "Telegram", "Search", "Saved Messages", "Igor Santana", "Sticker", "Promoções Tech 🔥", "Galaxy Buds por R$ 499",
        "@caio_menezes", "online"],
        pessoas=["Igor Santana"], usuarios=["@caio_menezes"], manter=["Saved Messages", "Promoções Tech", "Galaxy Buds"]),
    tela("li-feed", "linkedin", "LinkedIn › feed", [
        "Search", "Home", "My Network", "Post", "Notifications", "Jobs", "Rodrigo Alves", "Senior Developer at Stone",
        "Feliz em anunciar que comecei na Stone!", "Like", "Comment", "Repost", "Send"],
        pessoas=["Rodrigo Alves"], manter=["My Network", "Jobs", "Senior Developer", "Stone", "Repost"]),
    # --- telas em português (app com idioma próprio) ---
    tela("pt-wa-conversa", "whatsapp", "WhatsApp em português › conversa", [
        "Voltar", "Ana Júlia Ribeiro", "visto por último hoje às 21:03", "Chamada de vídeo", "Ligar",
        "Vamos no aniversário da Bia sábado?", "Bora! Chamo o Henrique?", "Mensagem"],
        pessoas=["Ana Júlia Ribeiro", "Bia", "Henrique"], manter=["visto por último", "Chamada de vídeo", "aniversário", "Mensagem"]),
    tela("pt-if-loja", "ifood", "iFood › loja", [
        "Pizzaria Bella Napoli", "Pizza • 2,1 km • Mín. R$ 30", "Avaliações", "Mariana S.", "Chegou quentinha!", "Adicionar", "Ver sacola"],
        pessoas=["Mariana"], manter=["Avaliações", "Chegou quentinha", "Adicionar", "Ver sacola"]),
    tela("pt-banco-notif", "outro", "Notificação de banco (barra de notificações)", [
        "Nubank", "Transferência recebida", "Você recebeu R$ 120,00 de Fernanda Couto Alves", "agora", "Limpar"],
        pessoas=["Fernanda Couto Alves"], manter=["Nubank", "Transferência recebida", "Limpar"]),
    tela("pt-notif-varias", "outro", "Barra de notificações", [
        "Notificações", "WhatsApp • 3 mensagens de 2 conversas", "Lívia Bastos: chegou?", "Gustavo: 👍", "Gmail • Débora RH",
        "Holerite disponível", "Instagram • rafa_souza88 curtiu sua foto", "Limpar tudo"],
        pessoas=["Lívia Bastos", "Gustavo", "Débora"], usuarios=["rafa_souza88"], manter=["mensagens", "Holerite disponível", "curtiu sua foto", "Limpar tudo"]),
    # --- apps mais usados que não tinham casos; rótulos conferidos no aparelho em 2026-10-17, dados fictícios ---
    tela("ytm-inicio", "youtube-music", "YouTube Music › início", [
        "Activity feed", "Account", "Pagode 90", "Playlist • Bruno Kato", "Play all", "Marisa Monte", "Action menu",
        "Cast. Disconnected", "Play video", "Video player", "Home", "Samples", "Search", "Library"],
        pessoas=["Bruno Kato", "Marisa Monte"], manter=["Activity feed", "Pagode 90", "Cast. Disconnected", "Library"],
        nota="o artista também é mascarado, como o dono da playlist"),
    tela("nf-perfis", "netflix", "Netflix › escolha de perfil (em português)", [
        "Escolha o seu perfil", "Pedro", "Lívia", "Vó Nena", "Infantil", "Adicionar perfil", "Editar"],
        pessoas=["Pedro", "Lívia", "Nena"], manter=["Escolha o seu perfil", "Infantil", "Adicionar perfil", "Editar"]),
    tela("pv-perfis", "prime-video", "Prime Video › escolha de perfil", [
        "Who's watching?", "Pedro Lucas", "Renata", "KID", "New", "Edit profiles", "Learn more"],
        pessoas=["Pedro Lucas", "Renata"], manter=["Who's watching?", "Edit profiles", "Learn more"]),
    tela("olx-chat", "olx", "OLX › Chat (em português)", [
        "Chat", "Pesquisar chats", "Cadastrar horários para encontros", "Igor Santana", "Bicicleta aro 29",
        "Ainda está disponível?", "Hoje", "Mais", "Excluir", "Daniela Prates", "Sofá 3 lugares", "Fechado, passo amanhã às 18h",
        "Mais", "Excluir", "Início", "Explorar", "Anunciar", "Chat", "Menu"],
        pessoas=["Igor Santana", "Daniela Prates"],
        manter=["Pesquisar chats", "Cadastrar horários", "Bicicleta aro 29", "Sofá 3 lugares", "Excluir", "Anunciar"]),
    tela("ml-inicio", "mercado-livre", "Mercado Livre › início", [
        "Buscar en Mercado Libre", "Buscar con una imagen", "Enviar para Pedro Lucas", "SQN 210 Bloco C", "Veículos",
        "Bicicleta aro 29 Caloi", "MAIS VENDIDO", "R$ 1.299", "OFF", "Frete grátis", "Enviado pelo FULL", "Início",
        "Categorias", "Carrinho", "Mais"],
        pessoas=["Pedro Lucas"], manter=["Buscar en Mercado Libre", "Caloi", "MAIS VENDIDO", "Frete grátis", "Carrinho"],
        nota="a forma da linha de endereço ('Enviar para …') não foi conferida no aparelho"),
    tela("x-timeline", "x", "X › início", [
        "Show navigation drawer", "For you", "Following", "Larissa Prado", "@lari.prado", "2h",
        "bora no show da Marisa Monte sábado? @caio_menezes", "Reply", "Repost", "Like", "Bookmark", "Share",
        "Verified Business", "Home", "Explore", "Grok", "Notifications tab", "Messages"],
        pessoas=["Larissa Prado", "Marisa Monte"], usuarios=["@lari.prado", "@caio_menezes"],
        manter=["For you", "Repost", "Bookmark", "Grok", "Notifications tab"]),
    tela("nt-lista", "notes", "Samsung Notes › todas as notas", [
        "All notes", "12 notes", "Navigation drawer", "Import PDF", "Search", "More options", "This week",
        "Presente de aniversário da Renata", "Lista de compras", "Receita da tia Joana", "Sep", "Senha do wifi na casa do Bruno",
        "Create note"],
        pessoas=["Renata", "Joana", "Bruno"], manter=["All notes", "Import PDF", "This week", "Lista de compras", "Receita", "Create note"]),
    # --- só interface, para medir excesso ---
    tela("ui-instagram-cfg", "instagram", "Instagram › Configurações e atividade", [
        "Settings and activity", "Search", "Your account", "Accounts Center", "How you use Instagram", "Saved", "Archive",
        "Your activity", "Notifications", "Time management", "Who can see your content", "Account privacy", "Close Friends", "Blocked"],
        manter=["Settings and activity", "Accounts Center", "Time management", "Who can see your content", "Close Friends", "Blocked"]),
    tela("ui-chrome-menu", "chrome", "Chrome › menu", [
        "New tab", "New Incognito tab", "History", "Delete browsing data", "Downloads", "Bookmarks", "Recent tabs",
        "Share…", "Find in page", "Translate…", "Add to Home screen", "Desktop site", "Settings", "Help and feedback"],
        manter=["New Incognito tab", "Delete browsing data", "Find in page", "Add to Home screen", "Desktop site", "Help and feedback"]),
    tela("ui-waze-cfg", "waze", "Waze › Configurações (em português)", [
        "Configurações", "Geral", "Exibição de mapa", "Voz e som", "Preferências de direção", "Navegação",
        "Detalhes do veículo", "Alertas", "Postos de combustível", "Notificações"],
        manter=["Exibição de mapa", "Voz e som", "Preferências de direção", "Detalhes do veículo", "Postos de combustível"],
        nota="conferido no aparelho em 2026-10-17"),
    tela("ui-cfg-avancado", "configuracoes", "Configurações › Recursos avançados", [
        "Advanced features", "Galaxy AI", "Side button", "Motions and gestures", "One-handed mode", "Bixby Routines",
        "Smart suggestions", "Screenshots and screen recordings", "Show contacts when sharing content", "Dual Messenger"],
        manter=["Galaxy AI", "Side button", "Motions and gestures", "One-handed mode", "Dual Messenger"]),
    tela("ui-cfg-som", "configuracoes", "Configurações › Sons e vibração", [
        "Sounds and vibration", "Sound mode", "Sound", "Vibrate", "Mute", "Ringtone", "Over the Horizon", "Notification sound",
        "Spaceline", "System sound", "Volume"],
        manter=["Sound mode", "Ringtone", "Over the Horizon", "Spaceline", "System sound"],
        nota="nomes de toques parecem nomes próprios"),
    tela("ui-yt-cfg", "youtube", "YouTube › Configurações", [
        "Settings", "General", "Data saving", "Autoplay", "Video quality preferences", "Downloads", "Watch on TV",
        "Manage all history", "Your data in YouTube", "Privacy", "Try experimental new features", "Connected apps", "About"],
        manter=["Data saving", "Autoplay", "Watch on TV", "Manage all history", "Try experimental new features"]),
    tela("ui-notion-cfg", "notion", "Notion › Configurações", [
        "Settings", "Account", "Preferences", "Notifications", "Connections", "Language & region", "Appearance", "Use system setting",
        "Start week on Monday", "Open on start", "Last visited page", "Log out"],
        manter=["Preferences", "Language & region", "Appearance", "Start week on Monday", "Last visited page", "Log out"]),
    tela("ui-gmail-cfg", "gmail", "Gmail › Configurações gerais", [
        "General settings", "Theme", "Default notification action", "Archive", "Conversation view", "Swipe actions",
        "Default reply action", "Reply all", "Auto-fit messages", "Open web links in Gmail"],
        manter=["Default notification action", "Conversation view", "Swipe actions", "Reply all", "Auto-fit messages"]),
    tela("ui-cam-cfg", "camera", "Câmera › Configurações", [
        "Camera settings", "Scene optimiser", "Shot suggestions", "Scan QR codes", "Swipe Shutter button to", "Watermark",
        "Grid lines", "Location tags", "Shutter sound", "Reset settings", "Contact us"],
        manter=["Scene optimiser", "Shot suggestions", "Scan QR codes", "Watermark", "Grid lines", "Shutter sound"]),
    tela("ui-maps-menu", "maps", "Maps › menu da conta", [
        "Your profile", "Incognito mode", "Your timeline", "Location sharing", "Offline maps", "Your data in Maps",
        "Settings", "Help and feedback"],
        manter=["Incognito mode", "Your timeline", "Location sharing", "Offline maps"]),
]

CASOS = PEDIDOS + TELAS
