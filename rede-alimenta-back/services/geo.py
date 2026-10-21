"""Geografia simples para a recomendacao de ONGs: distancia em linha reta (haversine) e posicao aproximada de cidades.

A distancia usada pelo modelo vem, nesta ordem, de: (1) latitude/longitude informadas no cadastro, (2) o centro da
cidade citada na regiao (tabela abaixo, precisao de alguns km) e (3) uma estimativa fixa, quando nada disso existe.
Linha reta nao e rota urbana: o numero e uma aproximacao e a interface informa de onde ele veio."""
import math
import re
import unicodedata

RAIO_TERRA_KM = 6371.0088
ORIGEM_COORDENADAS = "coordenadas"
ORIGEM_CIDADE = "cidade"
ORIGEM_ESTIMATIVA = "estimativa"

# Capitais e cidades grandes (centro aproximado). Texto da regiao que cita uma delas ganha uma posicao.
_CIDADES = """
Rio Branco|-9.97|-67.81
Maceió|-9.67|-35.74
Macapá|0.03|-51.07
Manaus|-3.12|-60.02
Salvador|-12.97|-38.50
Fortaleza|-3.73|-38.52
Brasília|-15.79|-47.88
Vitória|-20.32|-40.34
Goiânia|-16.69|-49.26
São Luís|-2.53|-44.30
Cuiabá|-15.60|-56.10
Campo Grande|-20.47|-54.62
Belo Horizonte|-19.92|-43.94
Belém|-1.46|-48.50
João Pessoa|-7.12|-34.86
Curitiba|-25.43|-49.27
Recife|-8.05|-34.88
Teresina|-5.09|-42.80
Rio de Janeiro|-22.91|-43.17
Natal|-5.79|-35.21
Porto Alegre|-30.03|-51.23
Porto Velho|-8.76|-63.90
Boa Vista|2.82|-60.67
Florianópolis|-27.59|-48.55
São Paulo|-23.55|-46.63
Aracaju|-10.91|-37.07
Palmas|-10.18|-48.33
Campinas|-22.91|-47.06
Santos|-23.96|-46.33
Guarulhos|-23.46|-46.53
São Bernardo do Campo|-23.69|-46.56
Santo André|-23.66|-46.53
São Caetano do Sul|-23.62|-46.56
Osasco|-23.53|-46.79
Sorocaba|-23.50|-47.46
Ribeirão Preto|-21.18|-47.81
São José dos Campos|-23.22|-45.90
Jundiaí|-23.19|-46.88
Piracicaba|-22.73|-47.65
Bauru|-22.31|-49.06
São José do Rio Preto|-20.82|-49.38
Mogi das Cruzes|-23.52|-46.19
Diadema|-23.69|-46.62
Barueri|-23.51|-46.88
Carapicuíba|-23.52|-46.84
Taboão da Serra|-23.62|-46.79
Franca|-20.54|-47.40
Limeira|-22.56|-47.40
Marília|-22.21|-49.95
Presidente Prudente|-22.12|-51.39
Taubaté|-23.03|-45.56
Americana|-22.74|-47.33
Praia Grande|-24.01|-46.41
Guarujá|-23.99|-46.26
São Vicente|-23.96|-46.39
Suzano|-23.54|-46.31
Itaquaquecetuba|-23.49|-46.35
Niterói|-22.88|-43.10
Duque de Caxias|-22.79|-43.31
São Gonçalo|-22.83|-43.05
Nova Iguaçu|-22.76|-43.45
Petrópolis|-22.51|-43.18
Volta Redonda|-22.52|-44.10
Campos dos Goytacazes|-21.75|-41.32
Contagem|-19.93|-44.05
Betim|-19.97|-44.20
Uberlândia|-18.92|-48.28
Uberaba|-19.75|-47.93
Juiz de Fora|-21.76|-43.35
Montes Claros|-16.73|-43.86
Governador Valadares|-18.85|-41.95
Ipatinga|-19.47|-42.54
Serra|-20.13|-40.31
Vila Velha|-20.33|-40.29
Londrina|-23.31|-51.16
Maringá|-23.42|-51.94
Ponta Grossa|-25.09|-50.16
Cascavel|-24.96|-53.46
Foz do Iguaçu|-25.55|-54.59
Joinville|-26.30|-48.85
Blumenau|-26.92|-49.07
Itajaí|-26.91|-48.66
Chapecó|-27.10|-52.62
Criciúma|-28.68|-49.37
Caxias do Sul|-29.17|-51.18
Canoas|-29.92|-51.18
Pelotas|-31.77|-52.34
Santa Maria|-29.69|-53.81
Feira de Santana|-12.27|-38.97
Vitória da Conquista|-14.87|-40.84
Olinda|-8.01|-34.86
Jaboatão dos Guararapes|-8.11|-35.01
Caruaru|-8.28|-35.97
Petrolina|-9.39|-40.50
Campina Grande|-7.23|-35.88
Arapiraca|-9.75|-36.66
Mossoró|-5.19|-37.34
Juazeiro do Norte|-7.21|-39.32
Caucaia|-3.74|-38.65
Imperatriz|-5.52|-47.48
Ananindeua|-1.37|-48.37
Santarém|-2.44|-54.71
Anápolis|-16.33|-48.95
Aparecida de Goiânia|-16.82|-49.25
Dourados|-22.22|-54.81
Rondonópolis|-16.47|-54.64
Várzea Grande|-15.65|-56.13
"""


def _normalizar(texto):
    texto = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", texto).strip()


CIDADES = {}
for _linha in _CIDADES.strip().splitlines():
    _nome, _lat, _lon = _linha.split("|")
    CIDADES[_normalizar(_nome)] = (float(_lat), float(_lon))
# Mais longos primeiro: "sao jose dos campos" ganha de qualquer nome mais curto contido nele.
_CHAVES = sorted(CIDADES, key=len, reverse=True)


def coordenadas_da_regiao(regiao):
    """Centro aproximado da cidade citada no texto da regiao, ou None. 'Zona Sul, São Paulo' -> centro de São Paulo."""
    texto = " " + _normalizar(regiao) + " "
    for chave in _CHAVES:
        if " " + chave + " " in texto:
            return CIDADES[chave]
    return None


def _valida(lat, lon):
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    if math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180:
        return (lat, lon)
    return None


def resolver_posicao(latitude, longitude, regiao):
    """(posicao, origem): coordenadas do cadastro, senao o centro da cidade da regiao, senao (None, None)."""
    if latitude is not None and longitude is not None:
        posicao = _valida(latitude, longitude)
        if posicao:
            return posicao, ORIGEM_COORDENADAS
    posicao = coordenadas_da_regiao(regiao)
    if posicao:
        return posicao, ORIGEM_CIDADE
    return None, None


def distancia_km(a, b):
    """Distancia em linha reta (haversine) entre dois pontos (lat, lon), em km."""
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * RAIO_TERRA_KM * math.asin(min(1.0, math.sqrt(h)))
