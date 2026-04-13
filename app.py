import streamlit as st
import pandas as pd
import plotly.express as px
import pdfplumber
import re

st.set_page_config(page_title="Dashboard Setorial", layout="wide")
st.title("Controle Setorial - Horas Extras e Gratificações")
st.markdown("Faça o upload dos **Resumos Contábeis em PDF** da Fiorilli.")

# Função blindada contra a bagunça de pontos e vírgulas da Fiorilli
def limpar_valor(valor_str):
    # Pega algo como '18.955.68' ou '1.763,20', tira os pontos/virgulas e força os últimos 2 dígitos como centavos
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
            for num_pagina, pagina in enumerate(pdf.pages):
                texto = pagina.extract_text()
                if not texto: continue
                
                # Transforma a página inteira numa tripa de texto contínua para evitar quebras de linha falsas
                texto_limpo = re.sub(r'\s+', ' ', texto)
                linhas = texto.split('\n')
                
                mes_ano = "Indefinido"
                setor_atual = "Não Identificado"

                # 1. Puxa o Mês/Ano e o Nome do Setor do cabeçalho da página
                for i, linha in enumerate(linhas):
                    linha_lower = linha.lower()
                    if "mês/ano" in linha_lower:
                        match = re.search(r"(\d{2}/\d{4})", linha)
                        if match: mes_ano = match.group(1)
                        elif i + 1 < len(linhas):
                            match = re.search(r"(\d{2}/\d{4})", linhas[i+1])
                            if match: mes_ano = match.group(1)
                            
                    if "local de trabalho:" in linha_lower:
                        partes = linha.split("Local de Trabalho:")
                        if len(partes) > 1:
                            setor_bruto = partes[1].strip()
                            if "-" in setor_bruto:
                                setor_atual = setor_bruto.split("-", 1)[1].strip()
                            else:
                                setor_atual = setor_bruto
                        break # Achou o setor, pode parar de procurar nessa página

                if setor_atual == "Não Identificado" or not setor_atual:
                    continue
                    
                # Cria a "gaveta" do setor
                chave = f"{setor_atual}_{mes_ano}"
                if chave not in dados_setores:
                    dados_setores[chave] = {
                        'Mês/Ano': mes_ano,
                        'Setor': setor_atual,
                        'Horas Extras (R$)': 0.0,
                        'Gratificações (R$)': 0.0
                    }

                # 2. Tiro de precisão: Vai direto no quadro de Resumo de Proventos buscar a soma consolidada
                # Busca 'Hora Extra' seguida de dois blocos de números (Referência e Valor)
                match_he = re.search(r"Horas?\s*Extras?\s+[\d\.,]+\s+([\d\.,]+)", texto_limpo, re.IGNORECASE)
                if match_he:
                    val_he = limpar_valor(match_he.group(1))
                    if val_he > 0:
                        dados_setores[chave]['Horas Extras (R$)'] = val_he
                        log_extracao.append(f"Pág {num_pagina+1} | {setor_atual} -> Hora Extra: R$ {val_he:.2f}")

                # Busca 'Gratificações' seguida de dois blocos de números
                match_grat = re.search(r"Gratifica\w*\s+[\d\.,]+\s+([\d\.,]+)", texto_limpo, re.IGNORECASE)
                if match_grat:
                    val_grat = limpar_valor(match_grat.group(1))
                    if val_grat > 0:
                        dados_setores[chave]['Gratificações (R$)'] = val_grat
                        log_extracao.append(f"Pág {num_pagina+1} | {setor_atual} -> Gratificações: R$ {val_grat:.2f}")

    if not dados_setores:
        return pd.DataFrame(), log_extracao

    df = pd.DataFrame(list(dados_setores.values()))
    df['Total Geral (R$)'] = df['Horas Extras (R$)'] + df['Gratificações (R$)']
    
    # Remove apenas quem tem a soma zerada nessas rubricas especificas
    df = df[df['Total Geral (R$)'] > 0]
    
    return df.sort_values(by='Mês/Ano'), log_extracao


# --- INTERFACE DO APLICATIVO ---
arquivos_upload = st.file_uploader("Upload dos Resumos Contábeis (PDF)", type=["pdf"], accept_multiple_files=True)

if arquivos_upload:
    with st.spinner('Lendo relatórios e consolidando valores...'):
        df, logs = processar_pdf(arquivos_upload)
        
    # --- MODO DIAGNÓSTICO ---
    with st.expander("🛠️ Log de Extração (Clique para ver os valores lidos das páginas)"):
        if logs:
            for log in logs:
                st.text(log)
        else:
            st.text("Nenhum valor encontrado nos relatórios.")
            
    if not df.empty:
        st.success("Dados lidos com sucesso!")
        
        st.sidebar.header("Filtros Setoriais")
        lista_setores = df['Setor'].unique().tolist()
        lista_setores.sort()
        lista_setores.insert(0, "Visão Geral (Todos os Setores)")
        setor_selecionado = st.sidebar.selectbox("Escolha o Local de Trabalho", lista_setores)
        
        st.divider()
        
        # Gráficos
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
