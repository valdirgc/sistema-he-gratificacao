import pdfplumber
import re
import pandas as pd
import streamlit as st

def extrair_dados_folha(arquivo_pdf):
    dados = []
    
    # Regex para capturar os campos chave do documento
    re_mes_ano = re.compile(r"Mês/Ano\s*(\d{2}/\d{4})")
    re_setor = re.compile(r"Local de Trabalho:\s*\d+\s*-\s*(.+)")
    re_nome = re.compile(r"Nome\s+Desligamento\s+[\d-]+\s+(.+)") # Ajuste dependendo da quebra de linha
    
    # Regex para valores financeiros (busca o padrão de número brasileiro: 1.234,56)
    re_hora_extra = re.compile(r"Horas Extras \(3\.1\.90\.16\).*?([\d\.]*,\d+)")
    re_gratificacao = re.compile(r"Gratific Lei 2291/2021.*?([\d\.]*,\d+)")
    re_samu = re.compile(r"Gratificação SAMU.*?([\d\.]*,\d+)")

    mes_atual = "Indefinido"
    
    with pdfplumber.open(arquivo_pdf) as pdf:
        for pagina in pdf.pages:
            texto = pagina.extract_text()
            if not texto:
                continue
                
            # Extrai Mês/Ano (geralmente no cabeçalho)
            match_mes = re_mes_ano.search(texto)
            if match_mes:
                mes_atual = match_mes.group(1)
                
            # Extrai Setor
            match_setor = re_setor.search(texto)
            setor_atual = match_setor.group(1).strip() if match_setor else "Não Identificado"
            
            # Extrai Nome do Funcionário
            match_nome = re_nome.search(texto)
            if match_nome:
                nome_atual = match_nome.group(1).strip()
                
                # Busca Horas Extras
                match_he = re_hora_extra.search(texto)
                valor_he = match_he.group(1).replace('.', '').replace(',', '.') if match_he else "0.00"
                
                # Busca Gratificações (Soma Lei 2291 + SAMU, se houver)
                match_grat = re_gratificacao.search(texto)
                valor_grat = match_grat.group(1).replace('.', '').replace(',', '.') if match_grat else "0.00"
                
                match_samu = re_samu.search(texto)
                valor_samu = match_samu.group(1).replace('.', '').replace(',', '.') if match_samu else "0.00"
                
                total_gratificacao = float(valor_grat) + float(valor_samu)
                
                # Se o funcionário teve HE ou Gratificação, adicionamos à base
                if float(valor_he) > 0 or total_gratificacao > 0:
                    dados.append({
                        'Mês/Ano': mes_atual,
                        'Setor': setor_atual,
                        'Funcionário': nome_atual,
                        'Hora Extra (R$)': float(valor_he),
                        'Gratificação (R$)': total_gratificacao
                    })

    return pd.DataFrame(dados)
