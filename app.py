import streamlit as st
import pandas as pd
import plotly.express as px
import pdfplumber
import re

st.set_page_config(page_title="Dashboard Setorial", layout="wide")
st.title("Controle Setorial - Horas Extras e Gratificações")
st.markdown("Faça o upload dos **Resumos Contábeis em PDF** da Fiorilli.")

# Remove qualquer pontuação e força os 2 últimos dígitos como centavos
def limpar_valor(valor_str):
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
                
                # Transforma a página inteira numa tripa só, com espaços simples
                texto_limpo = re.sub(r'\s+', ' ', texto)

                # 1. Puxa Mês/Ano
                mes_ano = "Indefinido"
                match_mes = re.search(r"Mês/Ano\s*(\d{2}/\d{4})", texto_limpo, re.IGNORECASE)
                if match_mes:
                    mes_ano = match_mes.group(1)

                # 2. Puxa o Setor isolando o nome de forma cirúrgica
                setor_atual = "Não Identificado"
                padrao_setor = r"Local de Trabalho:\s*(?:\d+\s*-\s*)?(.*?)(?:\s+Mês/Ano|\s+Folha Mensal|\s+Total de Vencimentos|\s+Resumo de)"
                match_setor = re.search(padrao_setor, texto_limpo, re.IGNORECASE)
                
                if match_setor:
                    setor_atual = match_setor.group(1).strip()
                else:
                    # Tenta um plano B caso o cabeçalho esteja bagunçado
                    match_fallback = re.search(r"Local de Trabalho:\s*(?:\d+\s*-\s*)?([A-Za-zÀ-ÖØ-öø-ÿ].*?)(?:\s{2,}|$)", texto_limpo, re.IGNORECASE)
                    if match_fallback: setor_atual = match_fallback.group(1).strip()

                if setor_atual == "Não Identificado" or not setor_atual:
                    continue

                chave = f"{setor_atual}_{mes_ano}"
                if chave not in dados_setores:
                    dados_setores[chave] = {
                        'Mês/Ano': mes_ano,
                        'Setor': setor_atual,
                        'Horas Extras (R$)': 0.0,
                        'Gratificações (R$)': 0.0
                    }

                # 3. O Caçador de Números (A prova de falhas da Fiorilli)
                def cacar_maximo(palavras_chave):
                    maior = 0.0
                    for palavra in palavras_chave:
                        # Protege parênteses na palavra
                        padrao = palavra.replace("(", r"\(").replace(")", r"\)")
                        
                        for match in re.finditer(padrao, texto_limpo, re.IGNORECASE):
                            # Pega os caracteres logo após a palavra
                            trecho = texto_limpo[match.end():match.end()+60]
                            
                            # Para de ler assim que encontrar a próxima palavra (letra)
                            match_letra = re.search(r'[A-Za-zÀ-ÖØ-öø-ÿ]', trecho)
                            if match_letra:
                                trecho = trecho[:match_letra.start()]
                                
                            # Acha todos os formatos financeiros (Aceita 1.234,56 ou 1.234.56 ou 1234,56)
                            numeros = re.findall(r'\b\d{1,3}(?:[\.\,]\d{3})*[\.\,]\d{2}\b', trecho)
                            if numeros:
                                val = limpar_valor(numeros[-1])
                                if val > maior: maior = val
                    return maior

                # Captura o maior valor que encontrar para o setor (Nativa problemas de múltiplas páginas)
                val_he = cacar_maximo(["Horas Extras (3.1.90.16)", "Hora Extra", "Comp.Carga Horária", "Horas Extras 50%"])
                val_grat = cacar_maximo(["Gratificações", "Gratific Lei", "Gratificação SAMU", "Gratificacao SAMU"])

                if val_he > dados_setores[chave]['Horas Extras (R$)']:
                    dados_setores[chave]['Horas Extras (R$)'] = val_he
                    log_extracao.append(f"Pág {num_pagina+1} | {setor_atual} -> Achou HE: R$ {val_he:.2f}")

                if val_grat > dados_setores[chave]['Gratificações (R$)']:
                    dados_setores[chave]['Gratificações (R$)'] = val_grat
                    log_extracao.append(f"Pág {num_pagina+1} | {setor_atual} -> Achou Gratificações: R$ {val_grat:.2f}")

    if not dados_setores:
        return pd.DataFrame(), log_extracao

    df = pd.DataFrame(list(dados_setores.values()))
    df['Total Geral (R$)'] = df['Horas Extras (R$)'] + df['Gratificações (R$)']
    
    # Exclui setores onde o valor foi R$ 0,00 para os dois
    df = df[df['Total Geral (R$)'] > 0]
    
    return df.sort_values(by='Mês/Ano'), log_extracao

# --- INTERFACE DO APLICATIVO ---
arquivos_upload = st.file_uploader("Upload dos Resumos Contábeis (PDF)", type=["pdf"], accept_multiple_files=True)

if arquivos_upload:
    with st.spinner('Decodificando os dados financeiros...'):
        df, logs = processar_pdf(arquivos_upload)
        
    # --- MODO DIAGNÓSTICO ---
    with st.expander("🛠️ Log de Extração (Clique para ver os valores encontrados por página)"):
        if logs:
            for log in logs:
                st.text(log)
        else:
            st.text("Nenhum valor numérico vinculado a essas rubricas foi encontrado.")
            
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
