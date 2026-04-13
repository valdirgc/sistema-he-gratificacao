import streamlit as st
import pandas as pd
import plotly.express as px
import pdfplumber
import re

st.set_page_config(page_title="Dashboard Setorial", layout="wide")
st.title("Controle Setorial - Horas Extras e Gratificações")
st.markdown("Faça o upload dos **Resumos Contábeis em PDF** da Fiorilli.")

@st.cache_data
def processar_pdf(arquivos):
    dados_setores = {}

    for arquivo in arquivos:
        with pdfplumber.open(arquivo) as pdf:
            mes_ano = "Indefinido"
            setor_atual = "Não Identificado"

            for pagina in pdf.pages:
                texto = pagina.extract_text()
                if not texto: continue
                
                linhas = texto.split('\n')

                for linha in linhas:
                    linha_lower = linha.lower()

                    # 1. Captura o Mês/Ano (Data da folha)
                    if "mês/ano" in linha_lower:
                        match = re.search(r"(\d{2}/\d{4})", linha)
                        if match: mes_ano = match.group(1)

                    # 2. Captura o Setor e cria a gaveta de dados dele
                    if "local de trabalho:" in linha_lower:
                        partes = linha.split("Local de Trabalho:")
                        if len(partes) > 1:
                            setor_bruto = partes[1].strip()
                            # Tira o código da frente (ex: "001001 - Hospital" -> "Hospital")
                            if "-" in setor_bruto:
                                setor_atual = setor_bruto.split("-", 1)[1].strip()
                            else:
                                setor_atual = setor_bruto
                            
                            chave = f"{setor_atual}_{mes_ano}"
                            if chave not in dados_setores:
                                dados_setores[chave] = {
                                    'Mês/Ano': mes_ano,
                                    'Setor': setor_atual,
                                    'Horas Extras (R$)': 0.0,
                                    'Gratificações (R$)': 0.0
                                }

                    if setor_atual == "Não Identificado":
                        continue

                    chave = f"{setor_atual}_{mes_ano}"
                    
                    # 3. Mapeamento Exato do Vocabulário da Fiorilli
                    # O regex abaixo acha qualquer número no formato de moeda (ex: 1.234,56 ou 123,45)
                    padrao_moeda = r'\d{1,3}(?:\.\d{3})*,\d{2}'

                    # Caça Horas Extras e Complemento
                    if any(x in linha_lower for x in ["comp.carga horária", "horas extras 50%", "horas extras 100%"]):
                        valores = re.findall(padrao_moeda, linha)
                        if valores:
                            str_valor = valores[-1].replace('.', '').replace(',', '.')
                            dados_setores[chave]['Horas Extras (R$)'] += float(str_valor)

                    # Caça Gratificações (Lei 2291, SAMU, etc)
                    if any(x in linha_lower for x in ["gratific lei", "gratificação samu", "gratificacao samu"]):
                        valores = re.findall(padrao_moeda, linha)
                        if valores:
                            str_valor = valores[-1].replace('.', '').replace(',', '.')
                            dados_setores[chave]['Gratificações (R$)'] += float(str_valor)

    if not dados_setores:
        return pd.DataFrame()

    df = pd.DataFrame(list(dados_setores.values()))
    df['Total Geral (R$)'] = df['Horas Extras (R$)'] + df['Gratificações (R$)']
    
    # Remove setores que tiveram zero nessas rubricas
    df = df[df['Total Geral (R$)'] > 0]
    return df.sort_values(by='Mês/Ano')


# --- INTERFACE DO APLICATIVO ---
arquivos_upload = st.file_uploader("Upload dos Resumos Contábeis (PDF)", type=["pdf"], accept_multiple_files=True)

if arquivos_upload:
    with st.spinner('Puxando os dados dos relatórios...'):
        df = processar_pdf(arquivos_upload)
        
    if not df.empty:
        st.success("Dados lidos com sucesso!")
        
        # Filtros
        st.sidebar.header("Filtros Setoriais")
        lista_setores = df['Setor'].unique().tolist()
        lista_setores.sort()
        lista_setores.insert(0, "Visão Geral (Todos os Setores)")
        setor_selecionado = st.sidebar.selectbox("Escolha o Local de Trabalho", lista_setores)
        
        st.divider()
        
        # Gráficos
        if setor_selecionado == "Visão Geral (Todos os Setores)":
            st.subheader("📊 Comparativo Mensal - Prefeitura")
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

        # Tabela
        st.subheader("📋 Consolidado")
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
