"""Tarefas da coleta noturna (ver coleta.py): dados de treino para a etapa 1 do plano de modelos pequenos.

Rodam sem ninguém olhando, então só navegam, buscam e leem. Nenhuma envia, publica, curte, segue, compra, reserva,
pede, apaga, liga para alguém ou muda um ajuste: um toque errado do Laya deve, no pior caso, abrir a tela errada.
Ficam de fora apps de banco e pagamento, governo, autenticadores, VPN e acesso remoto. Pedidos em inglês (o Laya só
é bom em inglês). Cada app é encerrado antes da tarefa, para ela começar na tela inicial dele.
"""

TASKS = {
    "com.android.settings": [
        "Open the Wi-Fi settings",
        "Open the Bluetooth settings",
        "Show me the battery usage",
        "Open the display settings",
        "Open the sound and vibration settings",
        "Open the notification settings",
        "Show the list of installed apps",
        "Open the storage settings",
        "Open the lock screen settings",
        "Open the accessibility settings",
        "Open the language settings",
        "Show the date and time settings",
        "What is the model number of this phone?",
        "Open the software update screen",
        "Open the developer options",
        "Show the font size and style settings",
        "Open the security and privacy settings",
        "Open the connected devices settings",
        "Show the data usage of the mobile network",
        "Open the screen timeout setting",
        "Open the navigation bar settings",
        "Open the keyboard settings",
        "Open the digital wellbeing screen",
        "Open the advanced features settings",
        "Show the home screen settings",
    ],
    "com.sec.android.app.clockpackage": [
        "Open the alarms in the Clock app",
        "Open the world clock",
        "Open the stopwatch",
        "Open the timer in the Clock app",
        "Open the settings of the Clock app",
    ],
    "com.sec.android.app.popupcalculator": [
        "Calculate 125 plus 349 in the Calculator and tell me the result",
        "Calculate 12 times 12 in the Calculator and tell me the result",
        "Open the unit converter in the Calculator",
        "Open the calculation history in the Calculator",
        "Calculate 1000 divided by 8 in the Calculator and tell me the result",
    ],
    "com.sec.android.gallery3d": [
        "Open the Gallery and show my albums",
        "Open the Gallery and show the stories",
        "Open the settings of the Gallery",
        "Open the recycle bin of the Gallery",
        "Open the screenshots album in the Gallery",
    ],
    "com.samsung.android.app.contacts": [
        "Open the contacts and show the groups",
        "Open the settings of the Contacts app",
        "Open my own profile card in the contacts",
    ],
    "com.samsung.android.messaging": [
        "Open the Messages app and show the conversations",
        "Open the settings of the Messages app",
        "Open the blocked numbers in the Messages app",
    ],
    "com.samsung.android.dialer": [
        "Open the Phone app and show the recent calls",
        "Open the keypad in the Phone app",
        "Open the settings of the Phone app",
    ],
    "com.samsung.android.app.notes": [
        "Open Samsung Notes and show the folders",
        "Search Samsung Notes for shopping",
        "Open the settings of Samsung Notes",
    ],
    "com.sec.android.app.voicenote": [
        "Open the Voice Recorder and show the list of recordings",
        "Open the settings of the Voice Recorder",
    ],
    "com.sec.android.app.shealth": [
        "Open Samsung Health and show today's steps",
        "Open the sleep data in Samsung Health",
        "Open the settings of Samsung Health",
    ],
    "com.google.android.calendar": [
        "Open Google Calendar and show this week",
        "Open the settings of Google Calendar",
        "Search Google Calendar for meeting",
    ],
    "com.google.android.apps.photos": [
        "Open Google Photos and show the collections",
        "Search Google Photos for beach",
        "Open the settings of Google Photos",
    ],
    "com.google.android.apps.translate": [
        "Translate good morning to Spanish in Google Translate",
        "Open the saved translations in Google Translate",
        "Open the settings of Google Translate",
    ],
    "com.google.android.apps.docs": [
        "Open Google Drive and show the shared files",
        "Search Google Drive for budget",
        "Open the starred files in Google Drive",
    ],
    "com.google.android.apps.docs.editors.sheets": [
        "Open Google Sheets and show the recent spreadsheets",
    ],
    "com.google.android.apps.podcasts": [
        "Search Google Podcasts for history",
    ],
    "com.google.android.youtube": [
        "Search YouTube for cooking recipes",
        "Open the Shorts tab in YouTube",
        "Open the subscriptions in YouTube",
        "Open the watch history in YouTube",
        "Open the settings of YouTube",
        "Open the downloads in YouTube",
    ],
    "com.google.android.apps.youtube.music": [
        "Open YouTube Music and show my library",
        "Search YouTube Music for jazz",
        "Open the Explore tab in YouTube Music",
        "Open the settings of YouTube Music",
    ],
    "com.spotify.music": [
        "Open Spotify and show my library",
        "Search Spotify for samba",
        "Open the settings of Spotify",
        "Open the liked songs in Spotify",
    ],
    "com.aspiro.tidal": [
        "Open Tidal and show my collection",
        "Search Tidal for bossa nova",
    ],
    "com.audible.application": [
        "Open Audible and show my library",
    ],
    "com.amazon.kindle": [
        "Open Kindle and show my library",
        "Open the settings of the Kindle app",
    ],
    "com.netflix.mediaclient": [
        "Search Netflix for documentaries",
        "Open My Netflix",
        "Open the new and hot tab in Netflix",
    ],
    "com.amazon.avod.thirdpartyclient": [
        "Search Prime Video for comedy",
        "Open the settings of Prime Video",
    ],
    "com.disney.disneyplus": [
        "Search Disney+ for Pixar",
        "Open the downloads in Disney+",
    ],
    "com.wbd.stream": [
        "Search Max for series",
    ],
    "com.instagram.android": [
        "Open the Instagram search tab",
        "Open the Reels tab in Instagram",
        "Open my saved posts on Instagram",
        "Open the Instagram settings",
        "Open the notifications on Instagram",
        "Open the archive on Instagram",
    ],
    "com.instagram.barcelona": [
        "Open the search in Threads",
        "Open my profile in Threads",
    ],
    "com.twitter.android": [
        "Open the search tab in X",
        "Open the notifications in X",
        "Open the settings of X",
        "Open my bookmarks in X",
    ],
    "com.zhiliaoapp.musically": [
        "Open the discover search in TikTok",
        "Open my profile in TikTok",
    ],
    "com.pinterest": [
        "Search Pinterest for living room ideas",
        "Open my saved pins in Pinterest",
    ],
    "com.linkedin.android": [
        "Open the jobs tab in LinkedIn",
        "Open the notifications in LinkedIn",
        "Open my network in LinkedIn",
    ],
    "com.facebook.katana": [
        "Open the menu in Facebook",
        "Open the notifications in Facebook",
    ],
    "com.whatsapp": [
        "Open WhatsApp and show the chats",
        "Open the updates tab in WhatsApp",
        "Open the settings of WhatsApp",
        "Open the starred messages in WhatsApp",
    ],
    "com.discord": [
        "Open the direct messages in Discord",
        "Open the settings of Discord",
    ],
    "com.microsoft.office.outlook": [
        "Open Outlook and show the inbox",
        "Open the calendar in Outlook",
        "Open the settings of Outlook",
    ],
    "com.android.chrome": [
        "Open wikipedia.org in Chrome",
        "Open the bookmarks in Chrome",
        "Open the history in Chrome",
        "Open the downloads in Chrome",
        "Open the settings of Chrome",
        "Search Google in Chrome for the weather in Brasilia",
    ],
    "org.mozilla.firefox": [
        "Open the settings of Firefox",
        "Open the bookmarks in Firefox",
    ],
    "com.sec.android.app.sbrowser": [
        "Open the bookmarks in Samsung Internet",
    ],
    "com.google.android.googlequicksearchbox": [
        "Search Google for the population of Brazil",
        "Open the settings of the Google app",
    ],
    "com.waze": [
        "Search for Parque da Cidade in Waze and open the place details, without starting navigation",
        "Open the settings of the Waze app",
        "Open the saved places in Waze",
    ],
    "com.mercadolibre": [
        "Search Mercado Livre for headphones",
        "Open my purchases in Mercado Livre",
        "Open the favorites in Mercado Livre",
    ],
    "com.amazon.mShop.android.shopping": [
        "Search Amazon for running shoes",
        "Open my orders in Amazon",
    ],
    "com.shopee.br": [
        "Search Shopee for phone case",
    ],
    "com.alibaba.aliexpresshd": [
        "Search AliExpress for usb cable",
    ],
    "com.schibsted.bomnegocio.androidApp": [
        "Search OLX for bicycle",
        "Open my ads in OLX",
    ],
    "com.luizalabs.mlapp": [
        "Search Magalu for air fryer",
    ],
    "com.zzkko": [
        "Search Shein for jacket",
    ],
    "br.com.brainweb.ifood": [
        "Search iFood for pizza",
        "Open my orders in iFood",
    ],
    "com.ubercab": [
        "Open the activity tab in Uber",
        "Open the account tab in Uber",
    ],
    "com.taxis99": [
        "Open the trips history in 99",
    ],
    "com.airbnb.android": [
        "Search Airbnb for stays in Salvador",
        "Open the wishlists in Airbnb",
    ],
    "com.strava": [
        "Open my activities in Strava",
        "Open the settings of Strava",
    ],
    "com.gympass": [
        "Search Wellhub for gyms nearby",
    ],
    "com.sofascore.results": [
        "Open the football matches of today in Sofascore",
        "Search Sofascore for Flamengo",
    ],
    "com.trello": [
        "Open Trello and show my boards",
        "Open the settings of Trello",
    ],
    "notion.id": [
        "Search Notion for meeting notes",
        "Open the inbox in Notion",
    ],
    "com.canva.editor": [
        "Open Canva and show my designs",
        "Search Canva for birthday card templates",
    ],
    "com.microsoft.office.officehubrow": [
        "Open Microsoft 365 and show the recent files",
    ],
    "com.openai.chatgpt": [
        "Open the chat history in ChatGPT",
    ],
    "com.android.vending": [
        "Search the Play Store for a note taking app",
        "Open the Play Store and show the apps that have updates",
        "Open the settings of the Play Store",
    ],
    "com.vsco.cam": [
        "Open the studio in VSCO",
    ],
    "com.chess": [
        "Open the puzzles in Chess.com",
    ],
    "com.sirma.mobile.bible.android": [
        "Search the Bible app for Psalm 23",
    ],
    "com.memrise.android.memrisecompanion": [
        "Open the settings of Memrise",
    ],
    "com.ingresso.cinemas": [
        "Open the movies showing now in Ingresso.com",
    ],
    "com.tranzmate": [
        "Search Moovit for a route to the bus station",
    ],
    "org.zwanoo.android.speedtest": [
        "Open the results history in Speedtest",
    ],
}
