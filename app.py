import streamlit as st
import pandas as pd
import plotly.express as px
import pdfplumber
import re

st.set_page_config(page_title="Dashboard Setorial", layout="wide")
st.title("Controle Setorial - Horas Extras e Gratificações")
st.markdown("Faça o upload dos **Resumos Contábeis em PDF** da Fiorilli.")

def limpar_valor(valor_str):
    # Limpa a formatação (ex: 1.234,56 ou 1234.56) e transforma em número real
    digitos = re.sub(r'\D', '', valor_str)
    if digitos:
        return float(digitos) / 100.0
    return 0.0

@st.cache_data
def processar_pdf(arquivos):
    dados_setores = {}
    log_extracao = []

    for arquivo in arquivos:
        with pdfplumber.open(arquivo) as pdf:
            mes_atual = "Indefinido"
            setor_atual = None

            for num_pagina, pagina in enumerate(pdf.pages):
                texto = pagina.extract_text()
                if not texto: continue
                
                # 1. Captura Mês/Ano pelo texto do topo
                match_mes = re.search(r"Mês/Ano\s*(\d{2}/\d{4})", texto, re.IGNORECASE)
                if match_mes: mes_atual = match_mes.group(1)
                    
                # 2. Captura o Setor de forma limpa
                match_setor = re.search(r"Local de Trabalho:\s*(?:\d+\s*-\s*)?([^\n]+)", texto, re.IGNORECASE)
                if match_setor:
                    setor_bruto = match_setor.group(1).strip()
                    # Tira vazamentos de outras colunas na mesma linha
                    setor_bruto = re.split(r'Mês/Ano|Folha|Página|Resumo', setor_bruto, flags=re.IGNORECASE)[0].strip()
                    if "-" in setor_bruto:
                        setor_atual = setor_bruto.split("-", 1)[1].strip().title()
                    else:
                        setor_atual = setor_bruto.title()
                else:
                    # Plano B caso o regex falhe
                    for linha in texto.split('\n'):
                        if "Local de Trabalho:" in linha:
                            partes = linha.split("Local de Trabalho:")
                            if len(partes) > 1:
                                s = partes[1].strip()
                                if "-" in s:
                                    setor_atual = s.split("-", 1)[1].strip().title()
                                else:
                                    setor_atual = s.title()
                            break
                            
                if not setor_atual: continue
                
                chave = f"{setor_atual}_{mes_atual}"
                if chave not in dados_setores:
                    dados_setores[chave] = {
                        'Mês/Ano': mes_atual,
                        'Setor': setor_atual,
                        'Horas Extras (R$)': 0.0,
                        'Gratificações (R$)': 0.0
                    }
                    
                # 3. A MÁGICA DAS TABELAS OCULTAS QUE VOCÊ DESCOBRIU!
                tabelas = pagina.extract_tables()
                for tabela in tabelas:
                    for linha in tabela:
                        # Reconstrói as linhas perfeitamente caso a Fiorilli tenha quebrado em sub-linhas
                        max_linhas = max([len(str(c).split('\n')) for c in linha if c] + [0])
                        
                        for i in range(max_linhas):
                            linha_visual = []
                            for c in linha:
                                if c:
                                    partes = str(c).split('\n')
                                    if i < len(partes):
                                        linha_visual.append(partes[i].strip())
                                        
                            texto_linha = " ".join(linha_visual).lower()
                            
                            # Ignora o cabeçalho gigantesco que mistura todos os impostos
                            if any(x in texto_linha for x in ['fgts a recolher', 'total a empenhar', 'patronal', 'vantagens']):
                                continue
                                
                            # Apaga os códigos como (3.1.90.16) para o sistema não achar que é dinheiro
                            texto_linha = re.sub(r'\(\d\.\d\.\d{2}\.\d{2}\)', '', texto_linha)
                            
                            # Procura os alvos na linha da tabela
                            tem_he = any(kw in texto_linha for kw in ['hora extra', 'horas extras', 'comp.carga'])
                            tem_grat = any(kw in texto_linha for kw in ['gratific', 'samu'])
                            
                            if tem_he or tem_grat:
                                # Acha todos os formatos financeiros (Ex: 109,60 | 2.631,08 | 0,00)
                                numeros = re.findall(r'(?<!\d)\d{1,3}(?:[\.\,]\d{3})*[\.\,]\d{2}(?!\d)', texto_linha)
                                
                                if numeros:
                                    # O valor real é SEMPRE o último número financeiro da tabela
                                    valor_final = limpar_valor(numeros[-1])
                                    
                                    # Usamos o sinal de MAIOR (>) para pegar sempre o Total do Resumo Setorial
                                    if tem_he and valor_final > dados_setores[chave]['Horas Extras (R$)']:
                                        dados_setores[chave]['Horas Extras (R$)'] = valor_final
                                        log_extracao.append(f"✅ {setor_atual} | HE: R$ {valor_final:.2f} | Tabela: {texto_linha}")
                                        
                                    if tem_grat and valor_final > dados_setores[chave]['Gratificações (R$)']:
                                        dados_setores[chave]['Gratificações (R$)'] = valor_final
                                        log_extracao.append(f"✅ {setor_atual} | Gratificações: R$ {valor_final:.2f} | Tabela: {texto_linha}")

    if not dados_setores:
        return pd.DataFrame(), log_extracao

    df = pd.DataFrame(list(dados_setores.values()))
    df['Total Geral (R$)'] = df['Horas Extras (R$)'] + df['Gratificações (R$)']
    
    # Exclui os setores sem nenhum lançamento nessas rubricas
    df = df[df['Total Geral (R$)'] > 0]
    
    return df.sort_values(by='Mês/Ano'), log_extracao

# --- INTERFACE DO APLICATIVO ---
arquivos_upload = st.file_uploader("Upload dos Resumos Contábeis (PDF)", type=["pdf"], accept_multiple_files=True)

if arquivos_upload:
    with st.spinner('Lendo as tabelas ocultas do PDF...'):
        df, logs = processar_pdf(arquivos_upload)
        
    with st.expander("🛠️ Log das Tabelas Ocultas (Veja as linhas lidas com sucesso)"):
        if logs:
            for log in logs:
                st.text(log)
        else:
            st.text("Nenhum valor financeiro atrelado às palavras-chave foi encontrado.")
            
    if not df.empty:
        st.success("Dados lidos e decodificados com sucesso!")
        
        st.sidebar.header("Filtros Setoriais")
        lista_setores = df['Setor'].unique().tolist()
        lista_setores.sort()
        lista_setores.insert(0, "Visão Geral (Todos os Setores)")
        setor_selecionado = st.sidebar.selectbox("Escolha o Local de Trabalho", lista_setores)
        
        st.divider()
        
        if setor_selecionado == "Visão Geral (Todos os Setores)":
            st.subheader("📊 Comparativo Mensal - Prefeitura (Totalizado)")
            df_grafico = df.groupby('Mês/Ano')[['Horas Extras (R$)', 'Gratificações (R$)']].sum().reset_index()
            
            fig = px.bar(
                df_grafico, 
                x='Mês/Ano', 
                y=['Horas Extras (R$)', 'Gratificações (R$)'],
                barmode='group'
            )
            st.plotly_chart(fig, use_container_width=True)
            df_tabela = df
        else:
            st.subheader(f"📊 Evolução Mensal - {setor_selecionado}")
            df_setor = df[df['Setor'] == setor_selecionado]
            
            fig = px.line(
                df_setor, 
                x='Mês/Ano', 
                y=['Horas Extras (R$)', 'Gratificações (R$)', 'Total Geral (R$)'],
                markers=True
            )
            st.plotly_chart(fig, use_container_width=True)
            df_tabela = df_setor

        st.subheader("📋 Consolidado Geral")
        st.dataframe(
            df_tabela,
            column_config={
                "Horas Extras (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
                "Gratificações (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
                "Total Geral (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
            },
            hide_index=True,
            use_container_width=True
        )
    else:
        st.warning("Não localizamos nenhum valor de Hora Extra ou Gratificação nos PDFs enviados.")
else:
    st.info("Aguardando o envio dos arquivos PDF.")
