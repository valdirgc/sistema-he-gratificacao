import streamlit as st
import pandas as pd
import plotly.express as px
import pdfplumber
import re

st.set_page_config(page_title="Dashboard Setorial", layout="wide")
st.title("Controle Setorial - Horas Extras e Gratificações")
st.markdown("Faça o upload dos **Resumos Contábeis em PDF** da Fiorilli.")

def limpar_valor(valor_str):
    # Remove qualquer coisa que não seja número e transforma em Reais
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
                # O SEGREDO: layout=True força o Python a respeitar a distância visual da tela
                texto = pagina.extract_text(layout=True)
                if not texto: continue
                
                linhas = texto.split('\n')
                
                for linha in linhas:
                    linha_lower = linha.lower()
                    
                    # 1. Puxa Mês/Ano
                    if "mês/ano" in linha_lower:
                        match = re.search(r"(\d{2}/\d{4})", linha)
                        if match: mes_atual = match.group(1)
                        
                    # 2. Puxa Setor de forma limpa
                    if "local de trabalho:" in linha_lower:
                        partes = linha_lower.split("local de trabalho:")
                        if len(partes) > 1:
                            setor_bruto = partes[1].strip()
                            # Tira qualquer texto que possa ter vazado na mesma linha
                            setor_bruto = re.split(r'mês/ano|folha|página', setor_bruto)[0].strip()
                            if "-" in setor_bruto:
                                setor_atual = setor_bruto.split("-", 1)[1].strip().title()
                            elif setor_bruto:
                                setor_atual = setor_bruto.title()
                                
                    if not setor_atual: continue
                    
                    chave = f"{setor_atual}_{mes_atual}"
                    if chave not in dados_setores:
                        dados_setores[chave] = {
                            'Mês/Ano': mes_atual,
                            'Setor': setor_atual,
                            'Horas Extras (R$)': 0.0,
                            'Gratificações (R$)': 0.0
                        }
                        
                    # 3. Busca Ultra Permissiva de Valores na Linha Perfeita
                    tem_he = any(kw in linha_lower for kw in ['hora extra', 'horas extras', 'comp.carga'])
                    tem_grat = any(kw in linha_lower for kw in ['gratific', 'samu'])
                    
                    if tem_he or tem_grat:
                        # Pega qualquer formato financeiro: 1.234,56 | 1234.56 | 1,234.56 | 0,00
                        numeros = re.findall(r'(?<!\d)\d{1,3}(?:[.,]\d{3})*[.,]\d{2}(?!\d)', linha)
                        
                        if numeros:
                            # O valor contábil é sempre o último número isolado na linha
                            valor_final = limpar_valor(numeros[-1])
                            
                            # Salva o maior valor encontrado para garantir que pegamos o Total do Resumo do Setor
                            if tem_he and valor_final > dados_setores[chave]['Horas Extras (R$)']:
                                dados_setores[chave]['Horas Extras (R$)'] = valor_final
                                log_extracao.append(f"✅ {setor_atual} | HE: R$ {valor_final:.2f} | Linha: {linha.strip()}")
                                
                            if tem_grat and valor_final > dados_setores[chave]['Gratificações (R$)']:
                                dados_setores[chave]['Gratificações (R$)'] = valor_final
                                log_extracao.append(f"✅ {setor_atual} | Gratificações: R$ {valor_final:.2f} | Linha: {linha.strip()}")

    if not dados_setores:
        return pd.DataFrame(), log_extracao

    df = pd.DataFrame(list(dados_setores.values()))
    df['Total Geral (R$)'] = df['Horas Extras (R$)'] + df['Gratificações (R$)']
    
    # Exclui quem estiver zerado
    df = df[df['Total Geral (R$)'] > 0]
    
    return df.sort_values(by='Mês/Ano'), log_extracao

# --- INTERFACE DO APLICATIVO ---
arquivos_upload = st.file_uploader("Upload dos Resumos Contábeis (PDF)", type=["pdf"], accept_multiple_files=True)

if arquivos_upload:
    with st.spinner('Lendo e recriando o layout do PDF...'):
        df, logs = processar_pdf(arquivos_upload)
        
    with st.expander("🛠️ Log da Extração com Layout (Clique para ver as linhas originais)"):
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
