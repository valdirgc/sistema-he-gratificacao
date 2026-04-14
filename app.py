import streamlit as st
import pandas as pd
import plotly.express as px
import pdfplumber
import re

st.set_page_config(page_title="Dashboard Setorial", layout="wide")
st.title("Controle Setorial - Horas Extras e Gratificações")
st.markdown("Faça o upload dos **Resumos Contábeis em PDF** da Fiorilli.")

def limpar_valor(valor_str):
    digitos = re.sub(r'\D', '', str(valor_str))
    if digitos:
        return float(digitos) / 100.0
    return 0.0

@st.cache_data
def processar_pdf(arquivos):
    dados_gerais = []
    log_extracao = []

    for arquivo in arquivos:
        with pdfplumber.open(arquivo) as pdf:
            mes_atual = "Indefinido"
            
            # O SEGREDO: O setor fica FORA do ciclo das páginas para não sofrer amnésia
            setor_memoria = "Não Identificado"

            for num_pagina, pagina in enumerate(pdf.pages):
                
                # --- LEITURA 1: MODO LÓGICO (Atualiza a memória do Setor) ---
                texto_logico = pagina.extract_text()
                if not texto_logico: continue
                
                linhas_logicas = texto_logico.split('\n')
                
                for i, linha in enumerate(linhas_logicas):
                    if "Mês/Ano" in linha:
                        match = re.search(r"(\d{2}/\d{4})", linha)
                        if match: mes_atual = match.group(1)
                        
                    if "Local de Trabalho:" in linha:
                        parte = linha.split("Local de Trabalho:")[1].strip()
                        
                        # Se estiver vazio, tenta a linha de baixo
                        if not parte and i + 1 < len(linhas_logicas):
                            parte = linhas_logicas[i+1].strip()
                            
                        # Limpa palavras que costumam aparecer ao lado
                        parte = re.split(r'Mês/Ano|Folha|Página|Matrícula', parte, flags=re.IGNORECASE)[0].strip()
                        
                        # SÓ atualiza a memória se houver um nome válido. 
                        # Se estiver em branco na página de resumo, mantém o da página anterior!
                        if parte and parte.lower() not in ["matrícula", "nome", "desligamento", ""]:
                            if "-" in parte:
                                setor_memoria = parte.split("-", 1)[-1].strip().title()
                            else:
                                setor_memoria = parte.title()
                        break

                # --- LEITURA 2: MODO VISUAL (Busca o Dinheiro) ---
                texto_visual = pagina.extract_text(layout=True)
                linhas_visuais = texto_visual.split('\n')

                he_max = 0.0
                grat_max = 0.0

                for linha in linhas_visuais:
                    linha_lower = linha.lower()
                    tem_he = any(kw in linha_lower for kw in ['hora extra', 'horas extras', 'comp.carga', 'comp. carga'])
                    tem_grat = any(kw in linha_lower for kw in ['gratific', 'samu'])

                    if tem_he or tem_grat:
                        numeros = re.findall(r'(?<!\d)\d{1,3}(?:[\.\,]\d{3})*[\.\,]\d{2}(?!\d)', linha)
                        if numeros:
                            valor = limpar_valor(numeros[-1])
                            
                            if tem_he and valor > he_max:
                                he_max = valor
                                log_extracao.append(f"Pág {num_pagina+1} | {setor_memoria} | HE: R$ {valor:.2f}")
                                
                            if tem_grat and valor > grat_max:
                                grat_max = valor
                                log_extracao.append(f"Pág {num_pagina+1} | {setor_memoria} | Gratificações: R$ {valor:.2f}")

                # Associa os valores encontrados à memória do setor atual
                if he_max > 0 or grat_max > 0:
                    dados_gerais.append({
                        'Mês/Ano': mes_atual,
                        'Setor': setor_memoria,
                        'Horas Extras (R$)': he_max,
                        'Gratificações (R$)': grat_max
                    })

    if not dados_gerais:
        return pd.DataFrame(), log_extracao

    df = pd.DataFrame(dados_gerais)
    
    # Agrupa por Mês e Setor (o valor máximo de cada página para evitar duplicados)
    df_agrupado = df.groupby(['Mês/Ano', 'Setor'], as_index=False).max()
    df_agrupado['Total Geral (R$)'] = df_agrupado['Horas Extras (R$)'] + df_agrupado['Gratificações (R$)']
    
    return df_agrupado.sort_values(by='Mês/Ano'), log_extracao


# --- INTERFACE DO APLICATIVO ---
arquivos_upload = st.file_uploader("Upload dos Resumos Contábeis (PDF)", type=["pdf"], accept_multiple_files=True)

if arquivos_upload:
    with st.spinner('A carregar ficheiros e consolidar setores...'):
        df, logs = processar_pdf(arquivos_upload)
        
    with st.expander("🛠️ Registo de Extração (Verifique a Memória dos Setores)"):
        if logs:
            for log in logs:
                st.text(log)
        else:
            st.text("Nenhum valor localizado.")
            
    if not df.empty:
        st.success("Dados lidos com sucesso!")
        
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
    st.info("A aguardar o envio dos ficheiros PDF.")
