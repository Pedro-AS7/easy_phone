"""Casos fictícios para comparar variantes do Laya (pesos, quantização, runtime). Usados por tests/eval_laya.py.

PICKS: (rótulos que o plano pede, rótulos da tela, rótulo certo ou None quando o controle não está na tela).
FRAGMENTS: (trecho de tela, True se cita pessoa ou nome de usuário).
"""

PROFILE = ["Edit profile", "Share profile", "Posts", "Followers", "Following", "Options", "Create", "Reels", "Home",
           "Search and explore"]
IG_SETTINGS = ["Accounts Center", "Saved", "Archive", "Your activity", "Notifications", "Time management",
               "Account privacy", "Close Friends", "Blocked", "Hide story and live"]
SETTINGS = ["Connections", "Sounds and vibration", "Notifications", "Display", "Battery", "Wallpaper and style",
            "Home screen", "Lock screen", "Security and privacy", "Location", "Accounts and backup",
            "Advanced features", "General management", "Accessibility", "Software update", "About phone"]
CHROME = ["Home", "Search or type URL", "Switch or close tabs", "Customize and control Google Chrome", "Discover"]
CAMERA = ["Quick controls", "Switch camera", "Photo", "Video", "Portrait", "More", "Gallery", "Zoom"]
YOUTUBE = ["Home", "Shorts", "Create", "Subscriptions", "You", "Search", "Notifications", "Cast"]
NOTION = ["Home", "Search", "Inbox", "New page", "Shopping list", "Meeting notes", "Settings"]

PICKS = [
    (["Menu", "Settings and activity"], PROFILE, "Options"),
    (["Privacy", "Private account"], IG_SETTINGS, "Account privacy"),
    (["Dark mode", "Screen"], SETTINGS, "Display"),
    (["Address bar", "URL bar"], CHROME, "Search or type URL"),
    (["Tabs"], CHROME, "Switch or close tabs"),
    (["Settings", "Camera settings"], CAMERA, "Quick controls"),
    (["Search", "Search YouTube"], YOUTUBE, "Search"),
    (["Add page", "Create page"], NOTION, "New page"),
    (["About device", "Phone information"], SETTINGS, "About phone"),
    (["Sound"], SETTINGS, "Sounds and vibration"),
    (["Front camera", "Flip camera"], CAMERA, "Switch camera"),
    (["System update"], SETTINGS, "Software update"),
    (["Private account"], PROFILE, None),
    (["Dark mode"], IG_SETTINGS, None),
    (["Flash"], SETTINGS, None),
    (["Incognito tab"], CAMERA, None),
    (["Clear cache"], YOUTUBE, None),
    (["Edge panels"], NOTION, None),
    (["Send message"], SETTINGS, None),
    (["Grid lines", "Composition guide"], CHROME, None),
    (["Verification code"], PROFILE, None),
    (["Delete account"], YOUTUBE, None),
]

FRAGMENTS = [(text, True) for text in [
    "Marina Azevedo", "Rafael Tavares", "Helena Prado: chego as 8", "joao.cardoso_", "Liked by bia_monteiro and others",
    "Message from Otavio Lacerda", "@luan.ferraz mentioned you", "Call Dr. Renata Sobral", "caio_vasques started following you",
    "Larissa P. replied to your story", "Shared with Tomas Guedes", "duda.nogueira99", "Birthday: Ines Falcao",
    "Sent by Murilo Bastos", "Hi Vitoria, your order shipped", "Tagged: pedro_h.lima, anaclara.rz",
    "Reply to Estela", "Voice message from Gustavo Paes",
]] + [(text, False) for text in [
    "Settings", "Connections", "Switch to private account?", "Account privacy", "Turn on", "Dark mode", "About phone",
    "Search or type URL", "Customize and control Google Chrome", "New page", "Quick controls", "Composition guide",
    "Software update", "Notifications", "Battery", "Share profile", "Followers", "Following", "Edit profile",
    "Your activity", "Time management", "Close Friends", "Blocked", "Subscriptions", "Shorts", "Wi-Fi", "Bluetooth",
    "Eye comfort shield", "Sounds and vibration", "Lock screen", "Only people you approve can see your posts",
    "Android version", "Clear browsing data", "Add to Home screen", "Meeting notes", "Shopping list",
    "Switch camera", "Portrait", "Cancel", "Save", "Done", "Back", "More options", "Help and feedback",
    "Accounts and backup", "General management", "Privacy Policy", "Terms of Service", "Storage", "Language",
]]

# Em português: mede o risco de fixar o peso em inglês quando a tela não está em inglês.
FRAGMENTS_PT = [(text, True) for text in [
    "Marina Azevedo", "Helena Prado: chego às 8", "Mensagem de Otávio Lacerda", "Curtido por bia_monteiro e outras pessoas",
    "caio_vasques começou a seguir você", "Ligar para Dra. Renata Sobral", "Enviado por Murilo Bastos",
    "Oi Vitória, seu pedido saiu para entrega", "Aniversário de Inês Falcão", "Responder a Estela",
    "Mensagem de voz de Gustavo Paes", "@luan.ferraz mencionou você", "Compartilhado com Tomás Guedes",
    "Larissa P. respondeu ao seu story", "duda.nogueira99", "Marcados: pedro_h.lima, anaclara.rz",
]] + [(text, False) for text in [
    "Configurações", "Conexões", "Mudar para conta privada?", "Privacidade da conta", "Ativar", "Modo escuro",
    "Sobre o telefone", "Pesquisar ou digitar URL", "Nova página", "Atualização de software", "Notificações", "Bateria",
    "Compartilhar perfil", "Seguidores", "Seguindo", "Editar perfil", "Sua atividade", "Amigos próximos", "Bloqueados",
    "Inscrições", "Tela de bloqueio", "Sons e vibração", "Somente pessoas aprovadas podem ver suas publicações",
    "Limpar dados de navegação", "Cancelar", "Salvar", "Concluído", "Voltar", "Mais opções", "Ajuda e feedback",
    "Contas e backup", "Armazenamento", "Idioma", "Trocar de câmera", "Lista de compras", "Notas da reunião",
]]
