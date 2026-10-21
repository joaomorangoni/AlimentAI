"""Validacoes compartilhadas dos cadastros. Tudo que nao fizer sentido e recusado com mensagem clara (ValueError)."""
import math
import re
import unicodedata
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

ID_MAXIMO = 2_147_483_647
FUSO_BRASIL = timezone(timedelta(hours=-3))  # o Brasil nao tem horario de verao desde 2019
# Caixa aproximada do Brasil: coordenadas fora dela nao fazem sentido para esta rede.
LATITUDE_BRASIL = (-34.0, 6.0)
LONGITUDE_BRASIL = (-74.0, -34.0)
_NOME = re.compile(r"^[A-Za-zÀ-ÿ0-9][A-Za-zÀ-ÿ0-9 .,'&()/\-]+$")
_REGIAO = re.compile(r"^[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ .'/\-]+$")
_EMAIL = re.compile(r"^[a-z0-9][a-z0-9._%+\-]{0,63}@([a-z0-9]([a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$")
_TELEFONE = re.compile(r"^[0-9+() \-]+$")
_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def hoje():
    return datetime.now(FUSO_BRASIL).date()


def texto(valor, campo, minimo, maximo):
    """Texto limpo: sem caracteres de controle ou invisiveis, espacos normalizados e tamanho dentro do limite."""
    if not isinstance(valor, str):
        raise ValueError(f"{campo} deve ser um texto.")
    if any(unicodedata.category(c) in ("Cc", "Cf", "Cs", "Co", "Cn") for c in valor):
        raise ValueError(f"{campo} contém caracteres inválidos.")
    limpo = " ".join(valor.split())
    if not limpo:
        raise ValueError(f"{campo} é obrigatório.")
    if not minimo <= len(limpo) <= maximo:
        raise ValueError(f"{campo} deve ter de {minimo} a {maximo} caracteres.")
    return limpo


def _com_letras(limpo, campo):
    if sum(c.isalpha() for c in limpo) < 2:
        raise ValueError(f"{campo} deve conter letras.")


def nome(valor, campo="Nome"):
    limpo = texto(valor, campo, 2, 120)
    _com_letras(limpo, campo)
    if not _NOME.match(limpo):
        raise ValueError(f"{campo} contém caracteres não permitidos.")
    return limpo


def regiao(valor):
    limpo = texto(valor, "Região", 2, 80)
    if not _REGIAO.match(limpo):
        raise ValueError("Região deve conter apenas letras.")
    return limpo


def localizacao(dados):
    """Endereço estruturado; aceita região isolada para clientes antigos da API."""
    if "endereco" not in dados:
        return {"regiao": regiao(dados.get("regiao"))}
    valor = dados["endereco"]
    campos = {"cidade", "estado", "bairro", "rua", "numero", "complemento", "cep"}
    if not isinstance(valor, dict) or set(valor) - campos:
        raise ValueError("Endereço em formato inválido.")
    endereco = {}
    for campo, label, limite in (("cidade", "Cidade", 80), ("bairro", "Bairro", 100),
                                 ("rua", "Rua", 160), ("numero", "Número", 20)):
        endereco[campo] = texto(valor.get(campo), label, 2 if campo == "cidade" else 1, limite)
        if "<" in endereco[campo] or ">" in endereco[campo]:
            raise ValueError(f"{label} contém caracteres inválidos.")
    _com_letras(endereco["cidade"], "Cidade")
    estado = texto(valor.get("estado"), "Estado", 2, 2).upper()
    if estado not in "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split():
        raise ValueError("Estado inválido. Selecione uma UF brasileira.")
    endereco["estado"] = estado
    cep = texto(valor.get("cep"), "CEP", 8, 9)
    if not re.fullmatch(r"[0-9]{5}-?[0-9]{3}", cep):
        raise ValueError("CEP inválido. Use 00000-000.")
    digitos = cep.replace("-", "")
    endereco["cep"] = digitos[:5] + "-" + digitos[5:]
    complemento = valor.get("complemento")
    endereco["complemento"] = None if complemento is None or complemento == "" else texto(complemento, "Complemento", 1, 120)
    return {"regiao": endereco["cidade"], "endereco": endereco}


def email(valor):
    limpo = texto(valor, "E-mail", 6, 160).lower()
    if not _EMAIL.match(limpo) or ".." in limpo:
        raise ValueError("E-mail inválido.")
    return limpo


def telefone(valor):
    """Opcional. Telefone brasileiro: DDD + numero (fixo de 8 ou celular de 9 digitos), com ou sem +55."""
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None
    limpo = texto(valor, "Telefone", 8, 20)
    digitos = re.sub(r"\D", "", limpo)
    nacional = digitos[2:] if len(digitos) in (12, 13) and digitos.startswith("55") else digitos
    if (
        not _TELEFONE.match(limpo)
        or len(nacional) not in (10, 11)
        or int(nacional[:2]) < 11
        or len(set(digitos)) == 1
        or (len(nacional) == 11 and nacional[2] != "9")
    ):
        raise ValueError("Telefone inválido. Informe DDD e número, por exemplo (11) 91234-5678.")
    return limpo


def cnpj(valor):
    """Opcional. CNPJ com ou sem pontuacao; confere os dois digitos verificadores. Devolve so os 14 digitos."""
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None
    limpo = texto(valor, "CNPJ", 14, 18)
    digitos = re.sub(r"[.\-/]", "", limpo)

    if not re.fullmatch(r"\d{14}", digitos) or len(set(digitos)) == 1:
        raise ValueError("CNPJ inválido.")

    for tamanho in (12, 13):
        pesos = ([5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2] if tamanho == 12 else [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
        resto = sum(int(d) * p for d, p in zip(digitos[:tamanho], pesos)) % 11

        if int(digitos[tamanho]) != (0 if resto < 2 else 11 - resto):
            raise ValueError("CNPJ inválido.")

    return digitos


def inteiro_id(valor, campo):
    if isinstance(valor, bool) or not isinstance(valor, int) or not 1 <= valor <= ID_MAXIMO:
        raise ValueError(f"{campo} inválido.")
    return valor


def numero(valor, campo, minimo, maximo, casas=2, minimo_exclusivo=False):
    """Numero finito, com no maximo `casas` decimais e dentro do intervalo."""
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise ValueError(f"{campo} deve ser um número.")
    try:
        decimal = Decimal(str(valor))
    except InvalidOperation:
        raise ValueError(f"{campo} deve ser um número.") from None
    if not decimal.is_finite() or (isinstance(valor, float) and not math.isfinite(valor)):
        raise ValueError(f"{campo} deve ser um número.")
    if -decimal.as_tuple().exponent > casas:
        raise ValueError(f"{campo} deve ter no máximo {casas} casas decimais.")
    abaixo = valor <= minimo if minimo_exclusivo else valor < minimo
    if abaixo or valor > maximo:
        raise ValueError(f"{campo} deve estar entre {minimo:g} e {maximo:g}.")
    return float(decimal)


def coordenadas(latitude, longitude):
    """Opcional, mas sempre em par e dentro do Brasil."""
    if latitude is None and longitude is None:
        return None, None
    if latitude is None or longitude is None:
        raise ValueError("Informe latitude e longitude juntas.")
    lat = numero(latitude, "Latitude", LATITUDE_BRASIL[0], LATITUDE_BRASIL[1], casas=7)
    lon = numero(longitude, "Longitude", LONGITUDE_BRASIL[0], LONGITUDE_BRASIL[1], casas=7)
    return lat, lon


def data_iso(valor, campo):
    """Aceita apenas AAAA-MM-DD, existente no calendario."""
    if isinstance(valor, date) and not isinstance(valor, datetime):
        return valor
    if not isinstance(valor, str) or not _DATA.match(valor.strip()):
        raise ValueError(f"{campo} inválida. Use o formato AAAA-MM-DD.")
    try:
        return date.fromisoformat(valor.strip())
    except ValueError:
        raise ValueError(f"{campo} não existe no calendário.") from None


def escolha(valor, campo, validos):
    if not isinstance(valor, str) or valor not in validos:
        raise ValueError(f"{campo} inválido.")
    return valor
