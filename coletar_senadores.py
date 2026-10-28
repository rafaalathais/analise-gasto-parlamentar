import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import requests


ANOS = range(2008, 2026)
PASTA_CACHE = Path('dados_cache')
PASTA_SENADORES = Path('dados_senadores')
URL_BASE = 'https://legis.senado.leg.br/dadosabertos/senador'
ENDPOINTS = {'detalhe': '', 'mandatos': '/mandatos', 'filiacoes': '/filiacoes'}
INTERVALO = 0.5
TENTATIVAS = 4
TRABALHADORES = 4
controle_requisicoes = threading.Lock()
proxima_requisicao = 0.0
sessao_local = threading.local()


def codigos_ceaps():
    arquivos = [PASTA_CACHE / f'ceaps_{ano}.csv' for ano in ANOS]
    ausentes = [str(arquivo) for arquivo in arquivos if not arquivo.is_file()]
    if ausentes:
        raise FileNotFoundError(f'CSVs da CEAPS ausentes: {ausentes}')
    codigos = set()
    for arquivo in arquivos:
        coluna = pd.read_csv(arquivo, sep=';', dtype='string', encoding='utf-8-sig', usecols=['COD_SENADOR'])
        if coluna.empty:
            raise ValueError(f'CSV da CEAPS sem registros: {arquivo}')
        codigos.update(coluna.COD_SENADOR.dropna().str.strip())
    if not codigos or any(not codigo.isdigit() for codigo in codigos):
        raise ValueError('COD_SENADOR ausente ou fora do formato numérico esperado')
    return sorted(codigos, key=lambda codigo: int(codigo))


def validar_resposta(dados, tipo, codigo):
    if not isinstance(dados, dict):
        return False
    try:
        if tipo == 'detalhe':
            identificacao = dados['DetalheParlamentar']['Parlamentar']['IdentificacaoParlamentar']
            return str(identificacao['CodigoParlamentar']) == codigo and bool(identificacao.get('NomeParlamentar'))
        raiz = 'MandatoParlamentar' if tipo == 'mandatos' else 'FiliacaoParlamentar'
        lista = 'Mandatos' if tipo == 'mandatos' else 'Filiacoes'
        item = 'Mandato' if tipo == 'mandatos' else 'Filiacao'
        parlamentar = dados[raiz]['Parlamentar']
        itens = parlamentar[lista][item]
        return str(parlamentar['Codigo']) == codigo and isinstance(itens, (dict, list)) and bool(itens)
    except (KeyError, TypeError):
        return False


def aguardar_intervalo():
    global proxima_requisicao
    with controle_requisicoes:
        agora = time.monotonic()
        espera = max(0, proxima_requisicao - agora)
        if espera:
            time.sleep(espera)
        proxima_requisicao = time.monotonic() + INTERVALO


def obter_sessao():
    if not hasattr(sessao_local, 'sessao'):
        sessao_local.sessao = requests.Session()
        sessao_local.sessao.headers.update({'Accept': 'application/json'})
    return sessao_local.sessao


def coletar_endpoint(codigo, tipo, sufixo):
    arquivo = PASTA_SENADORES / f'{tipo}_{codigo}.json'
    if arquivo.is_file():
        try:
            if validar_resposta(json.loads(arquivo.read_text(encoding='utf-8-sig')), tipo, codigo):
                return {'codigo': codigo, 'endpoint': tipo, 'situacao': 'reutilizado', 'requisicoes': 0, 'erro': ''}
        except (OSError, UnicodeError, json.JSONDecodeError):
            pass
    url = f'{URL_BASE}/{codigo}{sufixo}.json'
    ultimo_erro = ''
    requisicoes = 0
    for tentativa in range(TENTATIVAS):
        try:
            aguardar_intervalo()
            requisicoes += 1
            resposta = obter_sessao().get(url, timeout=(15, 45))
            if resposta.status_code != 200:
                ultimo_erro = f'HTTP {resposta.status_code}'
                if resposta.status_code not in (429, 500, 502, 503, 504):
                    break
                intervalo_servidor = resposta.headers.get('Retry-After', '')
                espera = float(intervalo_servidor) if intervalo_servidor.replace('.', '', 1).isdigit() else 0
            else:
                if 'json' not in resposta.headers.get('Content-Type', '').lower():
                    raise ValueError('resposta não é JSON')
                dados = resposta.json()
                if not validar_resposta(dados, tipo, codigo):
                    raise ValueError('JSON sem os dados esperados ou com código divergente')
                temporario = arquivo.with_suffix('.json.tmp')
                temporario.write_bytes(resposta.content)
                temporario.replace(arquivo)
                return {'codigo': codigo, 'endpoint': tipo, 'situacao': 'baixado', 'requisicoes': requisicoes, 'erro': ''}
        except (requests.RequestException, ValueError, OSError) as erro:
            ultimo_erro = str(erro)
            espera = 0
        if tentativa < TENTATIVAS - 1:
            time.sleep(max(2 ** (tentativa + 1), min(30, espera)))
    return {'codigo': codigo, 'endpoint': tipo, 'situacao': 'falha', 'requisicoes': requisicoes, 'erro': ultimo_erro}


def coletar_codigo(codigo):
    return [coletar_endpoint(codigo, tipo, sufixo) for tipo, sufixo in ENDPOINTS.items()]


def main():
    codigos = codigos_ceaps()
    PASTA_SENADORES.mkdir(exist_ok=True)
    resultados = []
    with ThreadPoolExecutor(max_workers=TRABALHADORES) as executor:
        tarefas = [executor.submit(coletar_codigo, codigo) for codigo in codigos]
        for numero, tarefa in enumerate(as_completed(tarefas), 1):
            resultados.extend(tarefa.result())
            if numero % 25 == 0 or numero == len(codigos):
                print(f'Códigos processados: {numero}/{len(codigos)}', flush=True)
    falhas = [resultado for resultado in resultados if resultado['situacao'] == 'falha']
    resumo = {
        'codigos_ceaps': len(codigos),
        'consultas_realizadas': sum(resultado['requisicoes'] for resultado in resultados),
        'respostas_validas_por_endpoint': {
            tipo: sum(resultado['endpoint'] == tipo and resultado['situacao'] != 'falha' for resultado in resultados)
            for tipo in ENDPOINTS
        },
        'arquivos_reutilizados': sum(resultado['situacao'] == 'reutilizado' for resultado in resultados),
        'arquivos_baixados': sum(resultado['situacao'] == 'baixado' for resultado in resultados),
        'falhas': sorted(falhas, key=lambda item: (int(item['codigo']), item['endpoint']))
    }
    (PASTA_SENADORES / 'resumo_coleta.json').write_text(json.dumps(resumo, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({chave: valor for chave, valor in resumo.items() if chave != 'falhas'}, ensure_ascii=False, indent=2))
    print(f'Falhas: {len(falhas)}. Detalhes em dados_senadores/resumo_coleta.json.')
    if falhas:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
