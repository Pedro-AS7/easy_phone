"""Escolhas de controle do conjunto congelado: o que o `/pick` do Laya responde quando o rótulo pedido pelo plano não
está escrito igual na tela.

`escolha(id, app, onde, pedidos, tela, certo, nota)`:
- `pedidos`: os nomes que o plano dá ao controle (o executor manda todos de uma vez).
- `tela`: os rótulos da tela, na ordem em que aparecem.
- `certo`: o rótulo a tocar, ou None quando o controle não está nesta tela (o certo é responder "nenhum"). Uma tupla
  quando o mesmo controle aparece como mais de um elemento (a etiqueta da linha e o texto dela): qualquer um vale.

Nenhum pedido é igual a um rótulo da tela (sem contar maiúsculas): esses o executor resolve por código, sem o Laya.
"""


def escolha(id, app, onde, pedidos, tela, certo, nota=""):
    return {"id": id, "app": app, "onde": onde, "pedidos": list(pedidos), "tela": list(tela), "certo": certo, "nota": nota,
            "conferido": any(tela is real for real in CONFERIDAS)}


# Rótulos de telas reais, em inglês (a interface do aparelho é em inglês).
# Configurações em três telas, como aparecem ao rolar (conferido no aparelho em 2026-10-16).
CFG_TOPO = ["Check it out", "Dismiss suggestion", "Settings", "Samsung account", "Connections", "Connected devices", "Galaxy AI",
            "Modes and Routines", "Sounds and vibration", "Notifications", "Display", "Search", "Voice search"]
CFG_MEIO = ["Display", "Battery", "Wallpaper and style", "Themes", "Home screen", "Lock screen and AOD", "Security and privacy",
            "Location", "Safety and emergency", "Accounts and backup", "Google services", "Advanced features",
            "Digital Wellbeing and parental controls", "Settings", "Search", "Voice search"]
CFG_FIM = ["Google services", "Advanced features", "Digital Wellbeing and parental controls", "Device care", "Apps",
           "General management", "Accessibility", "Software update", "User guide", "Remote management", "About phone",
           "Developer options", "Settings", "Search", "Voice search"]
CFG_CONEXOES = ["Wi-Fi", "Bluetooth", "NFC and contactless payments", "Ultra-wideband (UWB)", "Flight mode", "SIM manager",
                "Mobile networks", "Data usage", "Mobile Hotspot and Tethering", "More connection settings"]
CFG_TELA = ["Light", "Dark", "Dark mode settings", "Brightness", "Adaptive brightness", "Extra brightness", "Motion smoothness",
            "Eye comfort shield", "Screen mode", "Font size and style", "Screen zoom", "Full screen apps", "Camera cutout",
            "Screen timeout", "Edge panels", "Navigation bar", "Touch sensitivity", "Show charging information", "Screen saver"]
CFG_BATERIA = ["Battery", "Power saving", "Background usage limits", "More battery settings", "Charging settings", "Battery protection"]
CFG_SOM = ["Sound mode", "Sound", "Vibrate", "Mute", "Ringtone", "Notification sound", "System sound", "Volume",
           "Call vibration pattern", "Vibration intensity", "Sound quality and effects", "Separate app sound"]
CFG_SOBRE = ["Edit", "Phone number", "Model name", "Model number", "Serial number", "IMEI", "Status information",
             "Legal information", "Software information", "Battery information"]
CFG_SOFTWARE = ["Service provider software version", "One UI version", "Android version", "Google Play system update",
                "Baseband version", "Kernel version", "Build number", "Knox version"]
CFG_SEGURANCA = ["Security and privacy", "Lock screen", "Accounts", "Lost device protection", "App security", "Updates",
                 "Privacy", "Biometrics", "More security settings", "More privacy settings"]
CFG_AVANCADO = ["Galaxy AI", "Side button", "Motions and gestures", "One-handed mode", "Bixby Routines", "Smart suggestions",
                "Screenshots and screen recordings", "Show contacts when sharing content", "Video call effects", "Dual Messenger"]
IG_PERFIL = ["Create", "eu.mesmo_dev", "Options", "Edit profile", "Share profile", "Discover people", "Posts", "Followers",
             "Following", "Story highlights", "Home", "Reels", "Search and explore", "Profile"]
IG_CFG = ["Settings and activity", "Search", "Accounts Center", "Saved", "Archive", "Your activity", "Notifications",
          "Time management", "Account privacy", "Close Friends", "Crossposting", "Blocked", "Hide story and live",
          "Messages and story replies", "Tags and mentions", "Comments", "Sharing and reuse", "Restricted accounts",
          "Hidden words", "Muted accounts", "Content preferences", "Like and share counts", "Language and translations",
          "Help", "Log out"]
# Instagram › Início (conferido em 2026-10-17): o ícone de criar e o coração de notificações não têm rótulo na árvore;
# os stories (nomes de usuário) ficam de fora.
IG_INICIO = ["Instagram Home feed", "Reels tray container", "Home", "Reels", "Message", "Search and explore", "Profile"]
IG_POST = ["More options", "Like", "Comment", "Send post", "Save", "Add a comment…", "View all 23 comments"]
WA_LISTA = ["WhatsApp", "Camera", "More options", "Ask Meta AI or Search", "All filter, , selected", "Favorites filter, , unselected",
            "Add new list", "Archived", "New chat", "Updates", "Communities", "Calls"]
WA_MENU = ["New group", "New community", "Broadcast lists", "Linked devices", "Starred", "Payments", "Read all", "Settings"]
WA_CFG = ["Account", "Privacy", "Avatar", "Lists", "Chats", "Notifications", "Storage and data", "App language", "Help",
          "Invite a friend", "App updates"]
WA_CONVERSA = ["Navigate up", "Video call", "Voice call", "More options", "Emoji", "Message", "Attach", "Camera", "Voice message"]
# Chrome › aba nova (conferido em 2026-10-17): o botão de abas diz quantas há; os atalhos de sites e a conta ficam de fora.
CH_INICIO = ["Open the home page", "See 7 tabs", "Customize and control Google Chrome", "Search Google or type URL",
             "Search with your camera using Google Lens", "Ask AI Mode", "AI Mode", "New Incognito tab", "Incognito"]
CH_MENU = ["Forward", "Bookmark this page", "Download this page", "Page info", "Refresh", "New tab", "New Incognito tab",
           "History", "Delete browsing data", "Downloads", "Bookmarks", "Recent tabs", "Share…", "Find in page", "Translate…",
           "Add to Home screen", "Desktop site", "Settings", "Help and feedback"]
CH_CFG = ["Search engine", "Password Manager", "Payment methods", "Addresses and more", "Privacy and security", "Safety check",
          "Notifications", "Theme", "Homepage", "Toolbar shortcut", "Accessibility", "Site settings", "Languages", "Downloads", "About Chrome"]
YT_INICIO = ["YouTube Premium", "Messages inbox", "Search", "Explore Menu", "All", "Gaming", "Action menu", "More actions",
             "Home", "Shorts", "Create", "Subscriptions", "You"]
YT_VIDEO = ["Minimise", "Cast", "Captions", "Settings", "Play video", "Like", "Dislike", "Share", "Remix", "Download", "Save",
            "Subscribe", "Comments"]
YT_VOCE = ["View channel", "Switch account", "History", "Playlists", "Watch later", "Liked videos", "Your videos", "Downloads",
           "Your movies", "Get YouTube Premium", "Time watched", "Help and feedback", "Settings"]
# Câmera no modo foto, como a árvore a expõe (conferido no aparelho em 2026-10-16): proporção e foto em movimento
# aparecem pelo nome interno, e as configurações ficam dentro de "Quick controls".
CAM = ["Floating shutter", "Flash", "BACK_CAMERA_PICTURE_SIZE_NORMAL", "MOTION_PHOTO_OFF", "Filters", "Quick controls",
       "Ultra wide lens", "Wide-angle lens", "Wide-angle lens two times zoom", "Telephoto lens", "View pictures and videos",
       "Take picture", "Switch to front camera", "Photo, Mode"]
CAM_CFG = ["Scene optimiser", "Shot suggestions", "Scan QR codes", "Swipe Shutter button to", "Watermark", "Advanced picture options",
           "Auto HDR", "Video stabilisation", "Grid lines", "Location tags", "Shooting methods", "Settings to keep", "Shutter sound",
           "Vibration feedback", "Reset settings", "Privacy notice", "Contact us", "About Camera"]
GAL = ["Pictures", "Albums", "Menu", "Search", "Camera", "Screenshots", "Favorites", "Create", "More options", "View all"]
GAL_FOTO = ["Navigate up", "Details", "Favourite", "Edit", "Share", "Delete", "More options", "Bixby Vision"]
NO_INICIO = ["Search", "Inbox", "Home", "Recents", "Lista de compras", "Notas da reunião", "Planejamento 2026", "Private",
             "Shared", "Add a page", "Settings", "Notion AI"]
NO_PAGINA = ["Back", "Share", "Add comment", "More", "Add icon", "Add cover", "Untitled", "Type '/' for commands", "Done"]
MP_INICIO = ["Search here", "Voice search", "Your profile", "Restaurants", "Petrol", "Groceries", "Coffee", "Explore",
             "You", "Contribute", "Choose start location", "Recentre"]
MP_ROTA = ["Your location", "Choose destination", "Swap start and destination", "Driving", "Transit", "Walking", "Cycling",
           "Start", "Steps", "Add stop", "Route options"]
# Waze (conferido em 2026-10-17): em português no aparelho; a tela é em Compose, e os controles sem texto aparecem pelas
# etiquetas internas (HAMBURGER_BUTTON...). O destino recente é fictício. No menu ficam de fora o texto de "planejar"
# e o de "marketplace", e nas configurações três itens, que não foram identificados.
WZ = ["HAMBURGER_BUTTON", "WAZE_BOTTOM_SHEET_HANDLE", "START_STATE_SCROLLABLE_CONTENT", "START_STATE_FAVORITES_CAROUSEL",
      "START_STATE_FAVORITES_CAROUSEL_HOME_CELL", "Casa", "START_STATE_FAVORITES_CAROUSEL_WORK_CELL", "Trabalho",
      "START_STATE_FAVORITES_CAROUSEL_NEW_CELL", "Novo", "START_STATE_RECENT_SECTION_HEADER", "Recentes",
      "START_STATE_RECENT_SECTION_CELL0", "Shopping Conjunto Nacional", "START_STATE_SEARCH_FIELD", "km/h"]
WZ_MENU = WZ + ["MAIN_MENU_ACTIONS_PLAN_A_DRIVE", "ACTION_CELL_ICON", "MAIN_MENU_ACTIONS_INBOX", "Caixa de entrada",
                "MAIN_MENU_ACTIONS_SETTINGS", "Configurações", "MAIN_MENU_ACTIONS_MARKETPLACE",
                "MAIN_MENU_ACTIONS_HELP_AND_FEEDBACK", "Ajuda e comentários", "MAIN_MENU_ACTIONS_SHUTDOWN", "Desligar"]
WZ_CFG = ["Configurações", "Geral", "Exibição de mapa", "Voz e som", "Preferências de direção", "Navegação",
          "Detalhes do veículo", "Alertas", "Postos de combustível", "Notificações"]
GM = ["Open navigation drawer", "Ask Gmail", "Primary", "Promotions", "Social", "Compose", "Meet"]
GM_EMAIL = ["Navigate up", "Archive", "Delete", "Mark as unread", "More options", "Reply", "Reply all", "Forward", "Add emoji reaction"]
# Calculadora (conferido no aparelho): as teclas não aparecem na árvore de acessibilidade.
CALC = ["History", "Unit converter", "Scientific mode", "Calculator input field 0", "Result preview", "Backspace"]
REL = ["Alarm", "World clock", "Stopwatch", "Timer", "Add alarm", "More options", "Start", "Hours", "Minutes", "Seconds"]
TEL = ["Keypad", "Recents", "Contacts", "Search", "More options", "Call", "Video call", "Voicemail"]
CT = ["Dismiss suggestion", "Create contact", "Search", "More options", "My profile", "Groups", "Contacts"]
SP = ["Home", "Search", "Your Library", "Premium", "Create", "Liked Songs", "Settings and privacy", "What's new", "Recents"]
SP_TOCANDO = ["Minimise", "More options", "Like", "Shuffle", "Previous", "Pause", "Next", "Repeat", "Connect to a device",
              "Share", "Queue", "Lyrics"]
# Apps mais usados que não tinham casos (conferidos em 2026-10-17). Ficam de fora os textos de conteúdo (títulos,
# capas, nomes), que mudam a cada abertura.
YTM_INICIO = ["Activity feed", "Account", "Play all", "Action menu", "Cast. Disconnected", "Play video", "Video player",
              "Home", "Samples", "Search", "Library"]
NF_INICIO = ["Início", "Séries", "Filmes", "Jogos", "Halloween", "Novidades", "Minha lista", "Clipes", "Buscar",
             "Minha Netflix"]  # em português no aparelho
PV_INICIO = ["unmute", "Prime Video", "Included with Prime", "Continue watching", "35 min left", "21 min left", "Home",
             "Prime", "My Stuff", "Downloads", "Search", "Subscriptions", "Movies", "TV shows", "Sports", "Live TV"]
OLX_INICIO = ["Veículos", "Imóveis", "Produtos", "Favoritos", "Serviços", "Categorias", "Localização", "Início",
              "Explorar", "Anunciar", "Chat", "Menu"]
# Mercado Livre: a busca aparece em espanhol e o resto em português, como no aparelho.
ML_INICIO = ["Buscar en Mercado Libre", "Buscar con una imagen", "Veículos", "MAIS VENDIDO", "OFF", "grátis", "amanhã",
             "Enviado pelo FULL", "Início", "Categorias", "Carrinho", "Mais"]
X_INICIO = ["Show navigation drawer", "Find people to follow", "For you", "Following", "Add", "NFL",
            "Explain this post with Grok", "Post options", "Video", "Unmute", "Reply", "Repost", "Like", "Impressions",
            "Bookmark", "Share", "Verified Business", "Scroll to top", "Post", "Home", "Explore", "Grok",
            "Notifications tab", "Messages"]
GG_INICIO = ["Google", "AI mode history", "AI Mode", "Search Live", "Generate Image", "Search", "Voice search",
             "Camera search", "Today", "More options", "Home", "Notifications", "Activity"]
NT_INICIO = ["All notes", "Navigation drawer", "Import PDF", "Search", "More options", "This week", "Sep", "Create note"]


# Telas cujos rótulos foram conferidos no aparelho (tests/captura.py em 2026-10-16; em 2026-10-17, o arquivo/tela.py,
# que mostra só os textos embutidos no app e os ids). As outras são de memória e podem não bater com a tela real.
CONFERIDAS = [CFG_TOPO, CFG_MEIO, CFG_FIM, CAM, CALC, WA_LISTA, YT_INICIO, GAL, GM, CT, IG_INICIO, CH_INICIO, WZ, WZ_MENU,
              WZ_CFG, YTM_INICIO, NF_INICIO, PV_INICIO, OLX_INICIO, ML_INICIO, X_INICIO, GG_INICIO, NT_INICIO]

ESCOLHAS = [
    # --- Configurações: o controle está na tela com outro nome ---
    escolha("cfg-escuro-tela", "configuracoes", "Configurações › início", ["Dark mode", "Screen"], CFG_TOPO, "Display"),
    escolha("cfg-wifi-conexoes", "configuracoes", "Configurações › início", ["Wi-Fi settings", "Network"], CFG_TOPO, "Connections"),
    escolha("cfg-som", "configuracoes", "Configurações › início", ["Sound"], CFG_TOPO, "Sounds and vibration"),
    escolha("cfg-sobre", "configuracoes", "Configurações › rolada até o fim", ["About device", "Phone information"], CFG_FIM, "About phone"),
    escolha("cfg-atualizar", "configuracoes", "Configurações › rolada até o fim", ["System update"], CFG_FIM, "Software update"),
    escolha("cfg-papel", "configuracoes", "Configurações › rolada até o meio", ["Wallpaper"], CFG_MEIO, "Wallpaper and style"),
    escolha("cfg-apps", "configuracoes", "Configurações › rolada até o fim", ["Applications", "App settings"], CFG_FIM, "Apps"),
    escolha("cfg-bloqueio", "configuracoes", "Configurações › rolada até o meio", ["Lock screen", "Always On Display"], CFG_MEIO, "Lock screen and AOD"),
    escolha("cfg-gps", "configuracoes", "Configurações › rolada até o meio", ["GPS"], CFG_MEIO, "Location"),
    escolha("cfg-backup", "configuracoes", "Configurações › rolada até o meio", ["Backup"], CFG_MEIO, "Accounts and backup"),
    escolha("cfg-tempo-tela", "configuracoes", "Configurações › rolada até o meio", ["Screen time"], CFG_MEIO, "Digital Wellbeing and parental controls"),
    escolha("cfg-idioma", "configuracoes", "Configurações › rolada até o fim", ["Language", "Language and input"], CFG_FIM, "General management"),
    escolha("cfg-avancado", "configuracoes", "Configurações › rolada até o meio", ["Gestures"], CFG_MEIO, "Advanced features"),
    escolha("cfg-otimizar", "configuracoes", "Configurações › rolada até o fim", ["Optimize", "Phone maintenance"], CFG_FIM, "Device care"),
    escolha("cfg-ia", "configuracoes", "Configurações › início", ["AI features"], CFG_TOPO, "Galaxy AI"),
    escolha("cfg-dev", "configuracoes", "Configurações › rolada até o fim", ["Developer mode"], CFG_FIM, "Developer options"),
    escolha("cfg-manual", "configuracoes", "Configurações › rolada até o fim", ["Help", "Tips"], CFG_FIM, "User guide"),
    escolha("cfg-google", "configuracoes", "Configurações › rolada até o meio", ["Google"], CFG_MEIO, "Google services"),
    escolha("cfg-x-sobre-topo", "configuracoes", "Configurações › início", ["About device", "Phone information"], CFG_TOPO, None,
            nota="'About phone' fica no fim da lista: o certo é 'nenhum', para o executor rolar"),
    escolha("cfg-x-bateria-fim", "configuracoes", "Configurações › rolada até o fim", ["Battery saver"], CFG_FIM, None),
    escolha("cfg-aviao", "configuracoes", "Configurações › Conexões", ["Airplane mode"], CFG_CONEXOES, "Flight mode"),
    escolha("cfg-roteador", "configuracoes", "Configurações › Conexões", ["Hotspot", "Tethering"], CFG_CONEXOES, "Mobile Hotspot and Tethering"),
    escolha("cfg-dados", "configuracoes", "Configurações › Conexões", ["Mobile data"], CFG_CONEXOES, "Data usage",
            nota="ambíguo entre 'Mobile networks' e 'Data usage'; o uso de dados é o que a suíte usa"),
    escolha("cfg-nfc", "configuracoes", "Configurações › Conexões", ["NFC"], CFG_CONEXOES, "NFC and contactless payments"),
    escolha("cfg-chip", "configuracoes", "Configurações › Conexões", ["SIM card settings"], CFG_CONEXOES, "SIM manager"),
    escolha("cfg-escuro-chave", "configuracoes", "Configurações › Tela", ["Dark mode"], CFG_TELA, "Dark"),
    escolha("cfg-luz-azul", "configuracoes", "Configurações › Tela", ["Blue light filter"], CFG_TELA, "Eye comfort shield"),
    escolha("cfg-120hz", "configuracoes", "Configurações › Tela", ["Refresh rate", "120 Hz"], CFG_TELA, "Motion smoothness"),
    escolha("cfg-fonte", "configuracoes", "Configurações › Tela", ["Text size"], CFG_TELA, "Font size and style"),
    escolha("cfg-borda", "configuracoes", "Configurações › Tela", ["Edge panel", "Side panel"], CFG_TELA, "Edge panels",
            nota="imita cfg-borda da suíte"),
    escolha("cfg-desligar-tela", "configuracoes", "Configurações › Tela", ["Screen off time", "Sleep"], CFG_TELA, "Screen timeout"),
    escolha("cfg-brilho-auto", "configuracoes", "Configurações › Tela", ["Auto brightness"], CFG_TELA, "Adaptive brightness"),
    escolha("cfg-economia", "configuracoes", "Configurações › Bateria", ["Battery saver", "Power saving mode"], CFG_BATERIA, "Power saving"),
    escolha("cfg-carga", "configuracoes", "Configurações › Bateria", ["Protect battery", "Limit charging to 80%"], CFG_BATERIA, "Battery protection"),
    escolha("cfg-silencio", "configuracoes", "Configurações › Sons", ["Silent mode"], CFG_SOM, "Mute"),
    escolha("cfg-vibrar", "configuracoes", "Configurações › Sons", ["Vibration mode"], CFG_SOM, "Vibrate"),
    escolha("cfg-toque", "configuracoes", "Configurações › Sons", ["Ringtone settings", "Call sound"], CFG_SOM, "Ringtone"),
    escolha("cfg-versao", "configuracoes", "Configurações › Sobre o telefone", ["Software version", "Android version"], CFG_SOBRE, "Software information"),
    escolha("cfg-versao-2", "configuracoes", "Configurações › Sobre › Informações de software", ["Android release"], CFG_SOFTWARE, "Android version"),
    escolha("cfg-compilacao", "configuracoes", "Configurações › Sobre › Informações de software", ["Build"], CFG_SOFTWARE, "Build number"),
    escolha("cfg-digital", "configuracoes", "Configurações › Segurança e privacidade", ["Fingerprint", "Face recognition"], CFG_SEGURANCA, "Biometrics"),
    escolha("cfg-encontrar", "configuracoes", "Configurações › Segurança e privacidade", ["Find My Mobile"], CFG_SEGURANCA, "Lost device protection"),
    escolha("cfg-print", "configuracoes", "Configurações › Recursos avançados", ["Screenshot settings"], CFG_AVANCADO, "Screenshots and screen recordings"),
    escolha("cfg-botao", "configuracoes", "Configurações › Recursos avançados", ["Power key", "Side key settings"], CFG_AVANCADO, "Side button"),
    # --- Configurações: o controle não está nesta tela ---
    escolha("cfg-x-flash", "configuracoes", "Configurações › início", ["Flash"], CFG_TOPO, None),
    escolha("cfg-x-escuro-som", "configuracoes", "Configurações › Sons", ["Dark mode"], CFG_SOM, None),
    escolha("cfg-x-wifi-tela", "configuracoes", "Configurações › Tela", ["Wi-Fi"], CFG_TELA, None),
    escolha("cfg-x-mensagem", "configuracoes", "Configurações › rolada até o fim", ["Send message"], CFG_FIM, None),
    escolha("cfg-x-borda-bateria", "configuracoes", "Configurações › Bateria", ["Edge panels"], CFG_BATERIA, None),
    escolha("cfg-x-imei", "configuracoes", "Configurações › Conexões", ["IMEI"], CFG_CONEXOES, None),
    escolha("cfg-x-papel-sobre", "configuracoes", "Configurações › Sobre o telefone", ["Wallpaper"], CFG_SOBRE, None),
    # --- Instagram ---
    escolha("ig-menu", "instagram", "Instagram › perfil", ["Menu", "Settings and activity"], IG_PERFIL, "Options",
            nota="o menu do perfil é um ícone com descrição 'Options'"),
    escolha("ig-editar", "instagram", "Instagram › perfil", ["Edit bio"], IG_PERFIL, "Edit profile"),
    escolha("ig-seguindo", "instagram", "Instagram › perfil", ["Following list", "People I follow"], IG_PERFIL, "Following"),
    escolha("ig-busca", "instagram", "Instagram › perfil", ["Explore", "Search"], IG_PERFIL, "Search and explore"),
    escolha("ig-novo-post", "instagram", "Instagram › perfil", ["New post", "Add post"], IG_PERFIL, "Create"),
    escolha("ig-privacidade", "instagram", "Instagram › Configurações", ["Privacy", "Private account"], IG_CFG, "Account privacy"),
    escolha("ig-bloqueados", "instagram", "Instagram › Configurações", ["Blocked accounts"], IG_CFG, "Blocked"),
    escolha("ig-salvos", "instagram", "Instagram › Configurações", ["Saved posts"], IG_CFG, "Saved"),
    escolha("ig-tempo", "instagram", "Instagram › Configurações", ["Daily limit", "Screen time"], IG_CFG, "Time management"),
    escolha("ig-stories", "instagram", "Instagram › Configurações", ["Hide story from"], IG_CFG, "Hide story and live"),
    escolha("ig-sair", "instagram", "Instagram › Configurações", ["Sign out", "Logout"], IG_CFG, "Log out"),
    escolha("ig-curtidas", "instagram", "Instagram › Configurações", ["Hide like counts"], IG_CFG, "Like and share counts"),
    escolha("ig-dm", "instagram", "Instagram › Início", ["Direct messages", "Inbox"], IG_INICIO, "Message",
            nota="as mensagens estão na barra de baixo, como 'Message'"),
    escolha("ig-faixa-stories", "instagram", "Instagram › Início", ["Stories", "Story tray"], IG_INICIO, "Reels tray container",
            nota="a faixa de stories se chama 'Reels tray container' na árvore"),
    escolha("ig-x-notificacoes-inicio", "instagram", "Instagram › Início", ["Notifications", "Activity"], IG_INICIO, None,
            nota="o coração de notificações não tem rótulo na árvore: o certo é 'nenhum' e pedir ajuda com o índice"),
    escolha("ig-reels", "instagram", "Instagram › Início", ["Videos", "Reels tab"], IG_INICIO, "Reels"),
    escolha("ig-salvar-post", "instagram", "Instagram › post", ["Bookmark"], IG_POST, "Save"),
    escolha("ig-compartilhar-post", "instagram", "Instagram › post", ["Share", "Send"], IG_POST, "Send post"),
    escolha("ig-x-privada-perfil", "instagram", "Instagram › perfil", ["Private account"], IG_PERFIL, None),
    escolha("ig-x-escuro", "instagram", "Instagram › Configurações", ["Dark mode"], IG_CFG, None),
    escolha("ig-x-codigo", "instagram", "Instagram › perfil", ["Verification code"], IG_PERFIL, None),
    escolha("ig-x-arquivo-inicio", "instagram", "Instagram › Início", ["Archive"], IG_INICIO, None),
    # --- WhatsApp ---
    escolha("wa-menu", "whatsapp", "WhatsApp › conversas", ["Menu", "Settings"], WA_LISTA, "More options"),
    escolha("wa-busca", "whatsapp", "WhatsApp › conversas", ["Search"], WA_LISTA, "Ask Meta AI or Search"),
    escolha("wa-nova", "whatsapp", "WhatsApp › conversas", ["New message", "Start chat"], WA_LISTA, "New chat"),
    escolha("wa-status", "whatsapp", "WhatsApp › conversas", ["Status"], WA_LISTA, "Updates"),
    escolha("wa-ligacoes", "whatsapp", "WhatsApp › conversas", ["Call history"], WA_LISTA, "Calls"),
    escolha("wa-favoritos", "whatsapp", "WhatsApp › conversas", ["Favourite chats"], WA_LISTA, "Favorites filter, , unselected"),
    escolha("wa-arquivadas", "whatsapp", "WhatsApp › conversas", ["Archived chats"], WA_LISTA, "Archived"),
    escolha("wa-x-nao-lidas", "whatsapp", "WhatsApp › conversas", ["Unread chats"], WA_LISTA, None, nota="não há filtro de não lidas nesta conta"),
    escolha("wa-web", "whatsapp", "WhatsApp › menu", ["WhatsApp Web", "Connect computer"], WA_MENU, "Linked devices"),
    escolha("wa-grupo", "whatsapp", "WhatsApp › menu", ["Create group"], WA_MENU, "New group"),
    escolha("wa-favoritas", "whatsapp", "WhatsApp › menu", ["Starred messages"], WA_MENU, "Starred"),
    escolha("wa-armazenamento", "whatsapp", "WhatsApp › Configurações", ["Storage", "Auto-download"], WA_CFG, "Storage and data"),
    escolha("wa-idioma", "whatsapp", "WhatsApp › Configurações", ["Language"], WA_CFG, "App language"),
    escolha("wa-visto", "whatsapp", "WhatsApp › Configurações", ["Last seen", "Read receipts"], WA_CFG, "Privacy"),
    escolha("wa-anexo", "whatsapp", "WhatsApp › conversa", ["Attachment", "Paperclip", "Send file"], WA_CONVERSA, "Attach"),
    escolha("wa-audio", "whatsapp", "WhatsApp › conversa", ["Record audio", "Microphone"], WA_CONVERSA, "Voice message"),
    escolha("wa-campo", "whatsapp", "WhatsApp › conversa", ["Type a message", "Message box"], WA_CONVERSA, "Message"),
    escolha("wa-x-arquivar", "whatsapp", "WhatsApp › conversa", ["Archive chat"], WA_CONVERSA, None),
    escolha("wa-x-backup-lista", "whatsapp", "WhatsApp › conversas", ["Chat backup"], WA_LISTA, None),
    # --- Chrome ---
    escolha("ch-endereco", "chrome", "Chrome › início", ["Address bar", "URL bar"], CH_INICIO, "Search Google or type URL"),
    escolha("ch-abas", "chrome", "Chrome › início", ["Tabs", "Tab switcher"], CH_INICIO, "See 7 tabs",
            nota="o rótulo do botão de abas traz o número de abas abertas"),
    escolha("ch-lens", "chrome", "Chrome › início", ["Google Lens", "Visual search"], CH_INICIO,
            "Search with your camera using Google Lens"),
    escolha("ch-casa", "chrome", "Chrome › início", ["Home", "Home button"], CH_INICIO, "Open the home page"),
    escolha("ch-anonima-inicio", "chrome", "Chrome › início", ["Incognito tab", "Private tab"], CH_INICIO,
            ("New Incognito tab", "Incognito")),
    escolha("ch-ia", "chrome", "Chrome › início", ["AI search", "Ask Google AI"], CH_INICIO, ("Ask AI Mode", "AI Mode")),
    escolha("ch-menu", "chrome", "Chrome › início", ["Menu", "Three dots"], CH_INICIO, "Customize and control Google Chrome"),
    escolha("ch-anonima", "chrome", "Chrome › menu", ["Incognito tab", "Private tab"], CH_MENU, "New Incognito tab"),
    escolha("ch-limpar", "chrome", "Chrome › menu", ["Clear browsing data", "Clear history"], CH_MENU, "Delete browsing data"),
    escolha("ch-desktop", "chrome", "Chrome › menu", ["Request desktop site", "Desktop version"], CH_MENU, "Desktop site"),
    escolha("ch-traduzir", "chrome", "Chrome › menu", ["Translate page"], CH_MENU, "Translate…"),
    escolha("ch-favorito", "chrome", "Chrome › menu", ["Add bookmark", "Star"], CH_MENU, "Bookmark this page"),
    escolha("ch-atalho", "chrome", "Chrome › menu", ["Create shortcut", "Install app"], CH_MENU, "Add to Home screen"),
    escolha("ch-recarregar", "chrome", "Chrome › menu", ["Reload"], CH_MENU, "Refresh"),
    escolha("ch-buscador", "chrome", "Chrome › Configurações", ["Default search engine"], CH_CFG, "Search engine"),
    escolha("ch-senhas", "chrome", "Chrome › Configurações", ["Saved passwords", "Passwords"], CH_CFG, "Password Manager"),
    escolha("ch-tema", "chrome", "Chrome › Configurações", ["Dark theme", "Dark mode"], CH_CFG, "Theme"),
    escolha("ch-x-grade", "chrome", "Chrome › início", ["Grid lines", "Composition guide"], CH_INICIO, None),
    escolha("ch-x-flash", "chrome", "Chrome › menu", ["Flash"], CH_MENU, None),
    escolha("ch-x-senha-inicio", "chrome", "Chrome › início", ["Password Manager"], CH_INICIO, None),
    # --- YouTube ---
    escolha("yt-busca", "youtube", "YouTube › Início", ["Search YouTube", "Search button"], YT_INICIO, "Search"),
    escolha("yt-inscricoes", "youtube", "YouTube › Início", ["Subscribed channels"], YT_INICIO, "Subscriptions"),
    escolha("yt-conta", "youtube", "YouTube › Início", ["Library", "Account"], YT_INICIO, "You"),
    escolha("yt-x-tv", "youtube", "YouTube › Início", ["Watch on TV", "Chromecast"], YT_INICIO, None,
            nota="o botão de transmitir só aparece com uma TV na rede"),
    escolha("yt-premium", "youtube", "YouTube › Início", ["YouTube logo", "Go to home"], YT_INICIO, "YouTube Premium",
            nota="o logo aparece como 'YouTube Premium'; 'Home' também serve, mas o certo pelo nome é o logo"),
    escolha("yt-legendas", "youtube", "YouTube › vídeo", ["Subtitles", "CC"], YT_VIDEO, "Captions"),
    escolha("yt-qualidade", "youtube", "YouTube › vídeo", ["Quality", "Video settings"], YT_VIDEO, "Settings"),
    escolha("yt-baixar", "youtube", "YouTube › vídeo", ["Download video", "Save offline"], YT_VIDEO, "Download"),
    escolha("yt-depois", "youtube", "YouTube › Você", ["Watch Later playlist", "Saved for later"], YT_VOCE, "Watch later"),
    escolha("yt-historico", "youtube", "YouTube › Você", ["Watch history"], YT_VOCE, "History"),
    escolha("yt-x-cache", "youtube", "YouTube › Início", ["Clear cache"], YT_INICIO, None),
    escolha("yt-x-apagar-conta", "youtube", "YouTube › Você", ["Delete account"], YT_VOCE, None),
    # --- Câmera e Galeria ---
    escolha("cam-ajustes", "camera", "Câmera › modo foto", ["Camera settings", "Gear icon"], CAM, "Quick controls",
            nota="as configurações ficam dentro de 'Quick controls'"),
    escolha("cam-frontal", "camera", "Câmera › modo foto", ["Front camera", "Flip camera", "Selfie"], CAM, "Switch to front camera"),
    escolha("cam-foto", "camera", "Câmera › modo foto", ["Shutter button", "Capture photo"], CAM, "Take picture"),
    escolha("cam-proporcao", "camera", "Câmera › modo foto", ["Aspect ratio", "Picture size"], CAM, "BACK_CAMERA_PICTURE_SIZE_NORMAL",
            nota="o botão aparece pelo nome interno"),
    escolha("cam-zoom", "camera", "Câmera › modo foto", ["2x zoom", "Zoom in"], CAM, "Wide-angle lens two times zoom"),
    escolha("cam-ultra", "camera", "Câmera › modo foto", ["0.6x", "Ultra wide"], CAM, "Ultra wide lens"),
    escolha("cam-galeria", "camera", "Câmera › modo foto", ["Gallery", "Last photo thumbnail"], CAM, "View pictures and videos"),
    escolha("cam-movimento", "camera", "Câmera › modo foto", ["Motion photo"], CAM, "MOTION_PHOTO_OFF", nota="nome interno"),
    escolha("cam-x-temporizador", "camera", "Câmera › modo foto", ["Self-timer", "Countdown"], CAM, None,
            nota="o temporizador fica dentro de 'Quick controls'; não há rótulo dele nesta tela"),
    escolha("cam-x-retrato", "camera", "Câmera › modo foto", ["Portrait mode", "Live focus"], CAM, None,
            nota="os modos não aparecem como rótulos na árvore, só 'Photo, Mode'"),
    escolha("cam-grade", "camera", "Câmera › Configurações", ["Grid", "Composition guide"], CAM_CFG, "Grid lines",
            nota="imita cam-grade da suíte, em que o Laya foi por 'Quick controls' na tela anterior"),
    escolha("cam-marca", "camera", "Câmera › Configurações", ["Add watermark"], CAM_CFG, "Watermark"),
    escolha("cam-qr", "camera", "Câmera › Configurações", ["QR code scanner"], CAM_CFG, "Scan QR codes"),
    escolha("cam-som", "camera", "Câmera › Configurações", ["Camera sound", "Shutter noise"], CAM_CFG, "Shutter sound"),
    escolha("cam-gps", "camera", "Câmera › Configurações", ["Save location", "GPS tag"], CAM_CFG, "Location tags"),
    escolha("cam-x-grade-principal", "camera", "Câmera › modo foto", ["Grid lines"], CAM, None,
            nota="a grade fica nas configurações; 'Quick controls' é a armadilha"),
    escolha("cam-x-anonima", "camera", "Câmera › modo foto", ["Incognito tab"], CAM, None),
    escolha("gal-apagar", "galeria", "Galeria › foto", ["Trash", "Remove"], GAL_FOTO, "Delete"),
    escolha("gal-info", "galeria", "Galeria › foto", ["Info", "Photo details"], GAL_FOTO, "Details"),
    escolha("gal-albuns", "galeria", "Galeria › início", ["Album list"], GAL, "Albums"),
    escolha("gal-x-filtro", "galeria", "Galeria › início", ["Portrait"], GAL, None),
    # --- Notion ---
    escolha("no-nova", "notion", "Notion › início", ["New page", "Create page"], NO_INICIO, "Add a page",
            nota="imita notion-pagina: o Laya já abriu uma página existente no lugar de criar"),
    escolha("no-busca", "notion", "Notion › início", ["Find", "Search pages"], NO_INICIO, "Search"),
    escolha("no-titulo", "notion", "Notion › página nova", ["Title", "Page title"], NO_PAGINA, "Untitled"),
    escolha("no-corpo", "notion", "Notion › página nova", ["Body", "Page content"], NO_PAGINA, "Type '/' for commands"),
    escolha("no-capa", "notion", "Notion › página nova", ["Cover image"], NO_PAGINA, "Add cover"),
    escolha("no-x-config-pagina", "notion", "Notion › página nova", ["Settings"], NO_PAGINA, None),
    escolha("no-x-compartilhar-inicio", "notion", "Notion › início", ["Share page"], NO_INICIO, None),
    # --- Maps e Waze ---
    escolha("mp-busca", "maps", "Maps › início", ["Search box", "Search"], MP_INICIO, "Search here"),
    escolha("mp-gasolina", "maps", "Maps › início", ["Gas stations"], MP_INICIO, "Petrol"),
    escolha("mp-centralizar", "maps", "Maps › início", ["My location", "Center map"], MP_INICIO, "Recentre"),
    escolha("mp-pe", "maps", "Maps › rota", ["On foot", "Walk"], MP_ROTA, "Walking"),
    escolha("mp-onibus", "maps", "Maps › rota", ["Public transport", "Bus"], MP_ROTA, "Transit"),
    escolha("mp-iniciar", "maps", "Maps › rota", ["Go", "Navigate"], MP_ROTA, "Start"),
    escolha("mp-parada", "maps", "Maps › rota", ["Add waypoint"], MP_ROTA, "Add stop"),
    escolha("mp-x-anonimo-rota", "maps", "Maps › rota", ["Incognito mode"], MP_ROTA, None),
    # Waze em português: o plano pede em inglês e a tela responde em português ou pela etiqueta interna.
    escolha("wz-busca", "waze", "Waze › início", ["Search", "Where to?"], WZ, "START_STATE_SEARCH_FIELD"),
    escolha("wz-menu", "waze", "Waze › início", ["Menu", "Main menu"], WZ, "HAMBURGER_BUTTON"),
    escolha("wz-casa", "waze", "Waze › início", ["Go home", "Home address"], WZ,
            ("Casa", "START_STATE_FAVORITES_CAROUSEL_HOME_CELL")),
    escolha("wz-trabalho", "waze", "Waze › início", ["Work", "Office"], WZ, ("Trabalho", "START_STATE_FAVORITES_CAROUSEL_WORK_CELL")),
    escolha("wz-x-modo-escuro-inicio", "waze", "Waze › início", ["Dark mode"], WZ, None),
    escolha("wz-ajustes", "waze", "Waze › menu", ["Settings", "Preferences"], WZ_MENU, ("Configurações", "MAIN_MENU_ACTIONS_SETTINGS")),
    escolha("wz-caixa", "waze", "Waze › menu", ["Inbox", "Messages"], WZ_MENU, ("Caixa de entrada", "MAIN_MENU_ACTIONS_INBOX")),
    escolha("wz-ajuda", "waze", "Waze › menu", ["Help", "Support"], WZ_MENU, ("Ajuda e comentários", "MAIN_MENU_ACTIONS_HELP_AND_FEEDBACK")),
    escolha("wz-sair", "waze", "Waze › menu", ["Quit", "Exit Waze"], WZ_MENU, ("Desligar", "MAIN_MENU_ACTIONS_SHUTDOWN")),
    escolha("wz-planejar", "waze", "Waze › menu", ["Planned drives", "Plan a drive"], WZ_MENU, "MAIN_MENU_ACTIONS_PLAN_A_DRIVE"),
    escolha("wz-voz", "waze", "Waze › Configurações", ["Voice & sound", "Navigation voice"], WZ_CFG, "Voz e som"),
    escolha("wz-carro", "waze", "Waze › Configurações", ["Vehicle details", "Car type"], WZ_CFG, "Detalhes do veículo"),
    escolha("wz-mapa", "waze", "Waze › Configurações", ["Map display", "Map settings"], WZ_CFG, "Exibição de mapa"),
    escolha("wz-gasolina", "waze", "Waze › Configurações", ["Gas stations", "Fuel"], WZ_CFG, "Postos de combustível"),
    escolha("wz-geral", "waze", "Waze › Configurações", ["General settings"], WZ_CFG, "Geral"),
    escolha("wz-x-conta-cfg", "waze", "Waze › Configurações", ["Log out"], WZ_CFG, None),
    # --- Gmail, Calculadora, Relógio, Telefone, Contatos, Spotify ---
    escolha("gm-escrever", "gmail", "Gmail › caixa de entrada", ["New email", "Write"], GM, "Compose"),
    escolha("gm-menu", "gmail", "Gmail › caixa de entrada", ["Menu", "Folders"], GM, "Open navigation drawer"),
    escolha("gm-busca", "gmail", "Gmail › caixa de entrada", ["Search in mail", "Search"], GM, "Ask Gmail",
            nota="a busca do Gmail virou 'Ask Gmail'"),
    escolha("gm-lixo", "gmail", "Gmail › e-mail", ["Trash", "Remove email"], GM_EMAIL, "Delete"),
    escolha("gm-encaminhar", "gmail", "Gmail › e-mail", ["Send to someone else"], GM_EMAIL, "Forward"),
    escolha("gm-nao-lido", "gmail", "Gmail › e-mail", ["Mark unread"], GM_EMAIL, "Mark as unread"),
    escolha("gm-x-escrever-email", "gmail", "Gmail › e-mail", ["Compose"], GM_EMAIL, None),
    escolha("calc-conversor", "calculadora", "Calculadora", ["Unit conversion", "Convert units"], CALC, "Unit converter"),
    escolha("calc-cientifica", "calculadora", "Calculadora", ["Scientific calculator", "Advanced functions"], CALC, "Scientific mode"),
    escolha("calc-apagar", "calculadora", "Calculadora", ["Delete", "Erase"], CALC, "Backspace"),
    escolha("calc-conta", "calculadora", "Calculadora", ["Display", "Expression field"], CALC, "Calculator input field 0"),
    escolha("calc-x-porcento", "calculadora", "Calculadora", ["%", "Percent"], CALC, None,
            nota="as teclas não aparecem na árvore de acessibilidade"),
    escolha("calc-x-raiz", "calculadora", "Calculadora", ["Square root"], CALC, None),
    escolha("rel-cronometro", "relogio", "Relógio", ["Chronometer"], REL, "Stopwatch"),
    escolha("rel-novo-alarme", "relogio", "Relógio › Alarmes", ["New alarm", "Create alarm"], REL, "Add alarm"),
    escolha("rel-fuso", "relogio", "Relógio", ["Time zones"], REL, "World clock"),
    escolha("tel-teclado", "telefone", "Telefone", ["Dialpad", "Dial"], TEL, "Keypad"),
    escolha("tel-historico", "telefone", "Telefone", ["Call log", "Call history"], TEL, "Recents"),
    escolha("tel-caixa", "telefone", "Telefone", ["Voice mail"], TEL, "Voicemail"),
    escolha("ct-novo", "contatos", "Contatos", ["New contact", "Add contact"], CT, "Create contact"),
    escolha("ct-perfil", "contatos", "Contatos", ["My card", "Own profile"], CT, "My profile"),
    escolha("ct-x-bloquear", "contatos", "Contatos", ["Block number"], CT, None),
    escolha("sp-biblioteca", "spotify", "Spotify › início", ["Library", "My playlists"], SP, "Your Library"),
    escolha("sp-curtidas", "spotify", "Spotify › início", ["Favourite songs", "Liked"], SP, "Liked Songs"),
    escolha("sp-config", "spotify", "Spotify › início", ["Settings"], SP, "Settings and privacy"),
    escolha("sp-aleatorio", "spotify", "Spotify › tocando", ["Shuffle play", "Random"], SP_TOCANDO, "Shuffle"),
    escolha("sp-pular", "spotify", "Spotify › tocando", ["Skip", "Next track"], SP_TOCANDO, "Next"),
    escolha("sp-letra", "spotify", "Spotify › tocando", ["Song lyrics"], SP_TOCANDO, "Lyrics"),
    escolha("sp-fila", "spotify", "Spotify › tocando", ["Up next", "Play queue"], SP_TOCANDO, "Queue"),
    escolha("sp-x-podcast", "spotify", "Spotify › tocando", ["Podcasts"], SP_TOCANDO, None),
    # --- YouTube Music ---
    escolha("ytm-biblioteca", "youtube-music", "YouTube Music › início", ["Your library", "Saved music"], YTM_INICIO, "Library"),
    escolha("ytm-busca", "youtube-music", "YouTube Music › início", ["Search music", "Find a song"], YTM_INICIO, "Search"),
    escolha("ytm-notificacoes", "youtube-music", "YouTube Music › início", ["Notifications", "Bell icon"], YTM_INICIO, "Activity feed"),
    escolha("ytm-conta", "youtube-music", "YouTube Music › início", ["Profile picture", "My account"], YTM_INICIO, "Account"),
    escolha("ytm-transmitir", "youtube-music", "YouTube Music › início", ["Cast to TV", "Chromecast"], YTM_INICIO, "Cast. Disconnected"),
    escolha("ytm-amostras", "youtube-music", "YouTube Music › início", ["Short clips", "Shorts"], YTM_INICIO, "Samples"),
    escolha("ytm-x-letra", "youtube-music", "YouTube Music › início", ["Lyrics"], YTM_INICIO, None),
    escolha("ytm-x-equalizador", "youtube-music", "YouTube Music › início", ["Equalizer"], YTM_INICIO, None),
    # --- Netflix (em português) ---
    escolha("nf-busca", "netflix", "Netflix › início", ["Search"], NF_INICIO, "Buscar"),
    escolha("nf-series", "netflix", "Netflix › início", ["TV shows"], NF_INICIO, "Séries"),
    escolha("nf-filmes", "netflix", "Netflix › início", ["Movies"], NF_INICIO, "Filmes"),
    escolha("nf-perfil", "netflix", "Netflix › início", ["My profile", "Account"], NF_INICIO, "Minha Netflix"),
    escolha("nf-lista", "netflix", "Netflix › início", ["Watchlist", "Saved titles"], NF_INICIO, "Minha lista"),
    escolha("nf-novidades", "netflix", "Netflix › início", ["New & Hot", "Coming soon"], NF_INICIO, "Novidades"),
    escolha("nf-clipes", "netflix", "Netflix › início", ["Fast Laughs", "Short videos"], NF_INICIO, "Clipes"),
    escolha("nf-x-baixados", "netflix", "Netflix › início", ["Downloads"], NF_INICIO, None,
            nota="os downloads ficam dentro de 'Minha Netflix'"),
    escolha("nf-x-legendas", "netflix", "Netflix › início", ["Subtitles"], NF_INICIO, None),
    # --- Prime Video ---
    escolha("pv-lista", "prime-video", "Prime Video › início", ["Watchlist", "My list"], PV_INICIO, "My Stuff"),
    escolha("pv-baixados", "prime-video", "Prime Video › início", ["Offline videos", "Saved downloads"], PV_INICIO, "Downloads"),
    escolha("pv-canais", "prime-video", "Prime Video › início", ["Channels", "Add-on subscriptions"], PV_INICIO, "Subscriptions"),
    escolha("pv-ao-vivo", "prime-video", "Prime Video › início", ["Live channels", "Live"], PV_INICIO, "Live TV"),
    escolha("pv-series", "prime-video", "Prime Video › início", ["Series", "Shows"], PV_INICIO, "TV shows"),
    escolha("pv-som", "prime-video", "Prime Video › início", ["Turn sound on", "Sound"], PV_INICIO, "unmute"),
    escolha("pv-x-legendas", "prime-video", "Prime Video › início", ["Subtitles"], PV_INICIO, None),
    # --- OLX (em português) ---
    escolha("olx-vender", "olx", "OLX › início", ["Sell", "Post an ad"], OLX_INICIO, "Anunciar"),
    escolha("olx-mensagens", "olx", "OLX › início", ["Messages", "Inbox"], OLX_INICIO, "Chat"),
    escolha("olx-salvos", "olx", "OLX › início", ["Saved ads", "Favourites"], OLX_INICIO, "Favoritos"),
    escolha("olx-carros", "olx", "OLX › início", ["Cars", "Vehicles"], OLX_INICIO, "Veículos"),
    escolha("olx-imoveis", "olx", "OLX › início", ["Real estate", "Houses"], OLX_INICIO, "Imóveis"),
    escolha("olx-local", "olx", "OLX › início", ["Location", "Change city"], OLX_INICIO, "Localização"),
    escolha("olx-x-carrinho", "olx", "OLX › início", ["Shopping cart"], OLX_INICIO, None),
    # --- Mercado Livre ---
    escolha("ml-busca", "mercado-livre", "Mercado Livre › início", ["Search", "Search products"], ML_INICIO, "Buscar en Mercado Libre"),
    escolha("ml-foto", "mercado-livre", "Mercado Livre › início", ["Image search", "Search by photo"], ML_INICIO, "Buscar con una imagen"),
    escolha("ml-carrinho", "mercado-livre", "Mercado Livre › início", ["Cart", "Shopping cart"], ML_INICIO, "Carrinho"),
    escolha("ml-categorias", "mercado-livre", "Mercado Livre › início", ["Departments", "All categories"], ML_INICIO, "Categorias"),
    escolha("ml-menu", "mercado-livre", "Mercado Livre › início", ["More", "Menu"], ML_INICIO, "Mais"),
    escolha("ml-x-escuro", "mercado-livre", "Mercado Livre › início", ["Dark mode"], ML_INICIO, None),
    # --- X ---
    escolha("x-menu", "x", "X › início", ["Menu", "Side menu"], X_INICIO, "Show navigation drawer"),
    escolha("x-novo", "x", "X › início", ["Compose", "New tweet"], X_INICIO, "Post"),
    escolha("x-retweet", "x", "X › início", ["Retweet"], X_INICIO, "Repost"),
    escolha("x-salvar", "x", "X › início", ["Save post", "Save"], X_INICIO, "Bookmark"),
    escolha("x-busca", "x", "X › início", ["Search"], X_INICIO, "Explore"),
    escolha("x-dm", "x", "X › início", ["Direct messages", "Inbox"], X_INICIO, "Messages"),
    escolha("x-notificacoes", "x", "X › início", ["Notifications", "Alerts"], X_INICIO, "Notifications tab"),
    escolha("x-curtir", "x", "X › início", ["Heart", "Favorite"], X_INICIO, "Like"),
    escolha("x-topo", "x", "X › início", ["Back to top", "Go up"], X_INICIO, "Scroll to top"),
    escolha("x-x-config", "x", "X › início", ["Settings"], X_INICIO, None),
    escolha("x-x-rascunhos", "x", "X › início", ["Drafts"], X_INICIO, None),
    # --- app do Google ---
    escolha("gg-lens", "google", "Google › início", ["Google Lens", "Search with camera"], GG_INICIO, "Camera search"),
    escolha("gg-voz", "google", "Google › início", ["Microphone", "Speak a search"], GG_INICIO, "Voice search"),
    escolha("gg-ia", "google", "Google › início", ["Ask AI", "AI search"], GG_INICIO, "AI Mode"),
    escolha("gg-imagem", "google", "Google › início", ["Create image", "Image generator"], GG_INICIO, "Generate Image"),
    escolha("gg-ao-vivo", "google", "Google › início", ["Live search", "Talk to Google"], GG_INICIO, "Search Live"),
    escolha("gg-historico-ia", "google", "Google › início", ["AI history", "Past AI chats"], GG_INICIO, "AI mode history"),
    escolha("gg-x-config", "google", "Google › início", ["Settings"], GG_INICIO, None),
    # --- Samsung Notes ---
    escolha("nt-nova", "notes", "Samsung Notes › todas as notas", ["New note", "Add note"], NT_INICIO, "Create note"),
    escolha("nt-pastas", "notes", "Samsung Notes › todas as notas", ["Folders", "Menu"], NT_INICIO, "Navigation drawer"),
    escolha("nt-pdf", "notes", "Samsung Notes › todas as notas", ["Open PDF", "Add PDF file"], NT_INICIO, "Import PDF"),
    escolha("nt-busca", "notes", "Samsung Notes › todas as notas", ["Find note", "Search notes"], NT_INICIO, "Search"),
    escolha("nt-x-lixeira", "notes", "Samsung Notes › todas as notas", ["Trash", "Recycle bin"], NT_INICIO, None),
]
