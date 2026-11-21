"""Nomes de gente frequentes no Brasil, sem acento e em minúsculas (a forma de `masking.plain`), para as regras
fixas de nome (`Masker.learn`): um prenome daqui é nome de pessoa em qualquer caixa, mesmo fora do cofre e sem a IA
local, e o que vem depois dele continua o nome. `AMBIGUOUS` são os que também são palavra comum ("rosa", "costa",
"lima"): esses só valem capitalizados. As listas vieram do maskai (`nomes_comuns.py` e `dados/nomes_palavras.txt`).
"""

FIRST_NAMES = frozenset("""
aarao aaron abel abigail abilio abner abraao adalberto adam adao adelaide adelia adelina ademar ademir adilson
adolfo adrian adriana adriano adriel afonso agatha agenor agnaldo agnes agostinho alan alana alberto albino
alceu alcides alcione aldo alef alessandra alessandro alex alexandre alexia alexsander alexsandro alfredo alice
alicia aline alisson allan allana allyson almir aloisio altair alvaro alyssa amalia amanda amaro amauri amelia
ana anabela anastacia anderson andre andrea andrei andreia andressa andrey angela angelica angelina angelo anita
anselmo anthony antonela antonella antonieta antonio antony aparecida aparecido apollo apolo ari ariane ariel
aristides arlete armando arnaldo arthur artur asafe augusta augusto aurelio aurora ayla aylla ayrton aysha
baltazar barbara bartolomeu beatriz bella benedita benedito benicio benjamim benjamin bento berenice bernardo
betina bianca brayan brenda breno bruna bruno bryan bryen caetano caio caleb calebe camila camille camilo carla
carlos carmem carmen carolina caroline cassiano cassio catarina caua cauan caue cecilia cecilio celeste celia
celina celso cesar charles charlotte christian christopher cibele cicero cintia clara clarice clarissa claudia
claudio cleber cleide cleiton clovis conceicao cristian cristiane cristiano cristina cristofer cristovao
custodio dafne daiane dalila damiao dandara daniel daniela danielle danilo dante darci dario davi david davy
debora deborah denis denise diana diego dimas diogo dirce divina domingos dominic donizete dora douglas dulce
edgar edilson edison edite edmilson edna edson eduarda eduardo elaine eliana eliane elias elisa elisabete eliseu
eloa eloah eloisa elton elza emanoel emanuel emanuela emanuele emanuelly emerson emilia emilly emily enrico enzo
erica erick erico ernesto esdras ester estevao esther euclides eugenio eunice eurico eva evandro evelin evellyn
evelyn everton expedito ezequiel fabiana fabiano fabio fabiola fabricio fatima felipe felix fernanda fernando
filipe filomena flavia flavio flora francine francisca francisco frederico gabriel gabriela gabrielle gabrielly
gael geni geovana geraldo gerson gertrudes gilberto gilmar gilson giovana giovani giovanna giovanni gisele
giulia giullia glaucia glauco gloria gonzalo graciano graziela guilherme guilhermina gustavo hadassa hanna
hannah heitor helena helio hellena heloisa henrique henry heraldo hercules hilda hugo humberto iago ian iara
iasmin icaro igor inacio ingrid iolanda irani irene isaac isabel isabela isabella isabelly isadora isaias isaque
isis ismael israel italo ivan ivete ivo ivone jade jader jailson jair jairo jamile jandira jaqueline jasmin
jefferson jennifer jeremias jessica joana joao joaquim joel jonas jonathan jordana jorge josafa jose joselia
josiane josue joyce juan judite julia juliana juliano julio junior jurema jussara kaique kamilly karina kaua
kauan kauany kayky kelly kemilly kenzo kevin laercio laila lais lara larissa laura lauro lavinia layla leandra
leandro leo leonardo leonel leonor leticia levi lia liam liana lidia lilian lincoln lis livia liz lorena lorenzo
lorrane lourdes lourenco luan luana luara luca lucas lucca lucia luciana luciano lucimar lucio luigi luis luisa
luiz luiza luna lunna luzia madalena maite malu manoel manuel manuela manuella marcela marcelo marcia marcio
marco marcos margarida maria mariah mariana mariane marilene marina mario marisa marlene marli marta mateus
matheus mathias matteo mauricio mauro max maximiliano maya mayara maysa melina melinda melissa messias michel
michele miguel milena milton mirella miriam moacir moises monica murilo nadia nair nalu natalia natan nathalia
nathan nelson neuza nicolas nicole nilson nina noah noemi norberto octavio odair odete olavo olga oliver olivia
orlando osmar osvaldo oswaldo otavio otto pablo paloma pamela patricia patrick paula paulo pedro pietra pietro
priscila quiteria rael rafael rafaela raimunda raimundo raissa ramon raquel raul ravi rayane rayssa rebeca
regina reinaldo renan renata renato ricardo rinaldo rita roberta roberto robson rodolfo rodrigo rogerio romeu
ronaldo rosalia rosana rosangela rose rosemary ruan rubens rui ruth ryan sabrina salvador samanta samara samira
samuel sandra sandro sara sarah sebastiana sebastiao sergio severino silvana silvia silvio simao simone sofia
solange sonia sophia sophie stefany stella stephany suelen suzana tadeu taina tais tales tamara tania tatiana
tereza terezinha thais thales thalita thayla thayna theo thiago thomas tiago tobias tomas tulio ulisses ursula
valdete valdir valentim valentina valeria valter vanessa vania vera veronica vicente victor vilma vinicius vitor
vitoria viviane wagner waldir wallace walter washington wellington wesley willian wilson yago yan yara yasmin
yuri zeca zelia zilda zion zoe zuleide
""".split())

SURNAMES = frozenset("""
abdala abrantes abreu acioli adorno affonso aguiar albuquerque alcantara alencar almeida alvarenga alves alvim
amaral amaro amorim andrade anjos antunes aquino aragao arantes araujo arrais arruda assis avelar avila azevedo
bacelar bandeira baptista barbosa barcelos barra barreto barros barroso bastos batista becker benevides
bernardes bezerra bianchi bicalho bispo bittencourt boaventura bonfim borges botelho braga branco brandao brandt
brito brum bueno cabral caetano calado caldeira calixto camara camargo campelo campos canuto cardoso cardozo
carmo carneiro carrara carvalhal carvalho cassiano castilho castro cavalcante cavalcanti cerqueira cezar chagas
chaves cintra coelho cordeiro correa correia cortes costa coutinho couto crespo cruz cunha damasceno dantas dias
diniz domingues dorneles dourado drummond duarte esteves evangelista fagundes falcao faria farias feitosa
fernandes ferraz ferreira figueiredo filgueiras flor fogaca fonseca fontes fontoura fraga fragoso franca franco
freire freitas frota furtado gadelha galvao garcia gaspar godinho godoy goes gois gomes goncalves gondim goulart
gouveia guedes guerra guerreiro guimaraes hoffmann holanda honorato jesus jordao lacerda lamego laranjeira leal
leao leite leme lemos lessa liberato lima linhares lins lobo lopes loureiro lourenco lustosa luz macedo machado
magalhaes maia malta mamede marinho mariz marques martins mascarenhas mata matos mattos medeiros meira meireles
mello melo mendes mendonca menezes mesquita milani miranda monteiro montenegro moraes morais moreira mota motta
moura muniz nascimento neves nogueira nolasco noronha novaes novais nunes oliveira ornelas pacheco paes paiva
passos pastor paz pedrosa peixoto pereira pestana pimenta pimentel pinheiro pinho pinto pires pontes portela
porto prado prates prestes quadros queiroz quintela rabelo ramos rangel reboucas rego reis rezende ribeiro ricci
rios rocha rodrigues rosa rosario salazar sales salgado sampaio santana santos sarmento seixas serpa serrano
silva silveira simoes siqueira soares sodre sousa souza tavares tavora teixeira teles telles timoteo toledo
torres trindade uchoa valadares valenca valente vargas vasconcelos vasques vaz veloso ventura viana vidal vieira
vilar vilela viveiros xavier zanetti
""".split())

AMBIGUOUS = frozenset("""
abadia abramo acacia adi adir adonis adorno agata aide air albina albino alexandrina alexandrino ali alicio
aliene alise alma alta altiva altivo amada amado amador amando amara amaria amarilis amaro america americano
amir amos amparo angel angelica angra ani anjos anunciacao any aparecida aparecido apolo aquilino aranha arcanjo
argentina argentino ari ariana ariete armando armenio arsenio assuncao atonia atos aura aurea aureo aurora
babara baiano bala bandeira barao barata barra barreira barreiros basso bastiao beck bela belo benigna benigno
benta bento bispo boas braganca brain branca branco bras brasil brasileiro bretas brisa brown caiado cairo
calado caldas caldeira calos camara camelo caminha campos candida candido canto carioca carneiro carol cassia
castanheira castanho castelo catarina cavalheiro celeste chagas chales chaves chiara chico cirio clara claro
clemencia clever cloves coelho colombo conceicao conde constancia constantino cordeiro corona cortes cosmo costa
crespo cristal cruz custodia daisy dalia dante dara daria dean delgado deli delicia desire deus deusa diamantina
dias dileta diva divina divino domingo domingos dora dores dos dourado dulce duque eclair eider elan elder elide
elite elmo elves ema emir encarnacao eremita ermita esmeralda esmeraldina esperanca espirito eugenia eva
evangelista expedita falcao faria faro fausto felicidade ferro figueira filha filho firmo flor flora florentina
florentino flores flori florindo fontes fortes fraga franca frances franco frank frota furtado galhardo gama
gardenia gaucho gema generosa genesis gentil georgia germano germina glades gloria gorge graca gracas grace
guerra guerreiro guia harry hector heron holanda homem homero hora horta iam ida ide ilha imaculada indiana
inocencia ira ires iria iris irlanda irma iron isla israel ivy jacinto jack jade jardim jasmine jeronimo jesuita
jimmy joanete joaninha job john jordano julho junho junior justo juvenil lacy lady lago lair lane laranjeira
lays lazaro lea leal leao lee leia leitao leite leme lemes leo leones leonina levy lia libera libia liege lima
lincoln linda lira lirio lisa lisboa lobao lobo longo lordes lourdes lua luna luz machado macia macio madeira
magna magno magnolia maia maior malta mangabeira manso mar maranhao marcial marciana marciano marco margarida
mariano marina marine marines marinho mark martin martini massa mata max maximo may meira mel mere mesquita
messias midia mike miler miller minas mineiro mira miro modesto monte montes moreno moro mota mourao nadir nao
narciso nascimento nata natal natalicia natalicio natalina natalino naves nazareno negrao negreiros neto neves
newton nice nina nobre noel nora norma normando nova oliva orlando orlei pais paixao palma palmeira paloma
paraiba parente parreira passos pastor pastora patricio patrocinio paulista pavao paz pedra pedreira pedrinho
pena penteado pequeno perola perpetua pessoa pestana peter piedade pilar pimenta pinheiro pinho pinto pio
placido ponte pontes porto prado prata prazeres prestes preto primo pureza quadros quaresma raiara raposo ravel
ray real rebelo reges regia rego reinado reis remi rena riam rick rio rios rocha rock roger rolando romana
romano romaria roque rosa rosado rosario rosas rose ruas rubi rui russo sa sacramento safira said sales salgado
salgueiro salmo salvador salvadora sander sandy santa santinha santo santos sao sardinha savana scarlet senhora
senna serena serio serpa serra serrano severo sibila silvan silvestre silvo sirene siria sirio smith sobrinho
socorro sol solene sonha tailor tais tecla terra tiara tina toledo tomas tome tony torres tosta tostes tourinho
trindade urbano vale valente velho veneranda ventura vera veras vila villas viola violeta vital vitoria
vitoriano viveiros vivia viviam waldo walker wander washington welder wellington wilder will xisto zenite
""".split())
