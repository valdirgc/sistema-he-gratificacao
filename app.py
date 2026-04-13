import streamlit as st
import pandas as pd
import plotly.express as px
import pdfplumber
import re

st.set_page_config(page_title="Dashboard Setorial", layout="wide")
st.title("Controle Setorial - Horas Extras e Gratificações")
st.markdown("Faça o upload dos **Resumos Contábeis em PDF** da Fiorilli.")

def limpar_valor(valor_str):
    # Converte texto para moeda R$
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
            setor_atual = "Não Identificado"

            for num_pagina, pagina in enumerate(pdf.pages):
                # Usa o layout visual para garantir que os números não se misturem
                texto = pagina.extract_text(layout=True)
                if not texto: continue
                linhas = texto.split('\n')

                # 1. Tenta achar o Mês/Ano
                match_mes = re.search(r"Mês/Ano\s*(\d{2}/\d{4})", texto, re.IGNORECASE)
                if match_mes: mes_atual = match_mes.group(1)

                # 2. Tenta achar o Setor
                for i, linha in enumerate(linhas):
                    if "Local de Trabalho:" in linha:
                        parte = linha.split("Local de Trabalho:")[1].strip()
                        if parte:
                            setor_atual = parte
                        elif i + 1 < len(linhas) and linhas[i+1].strip():
                            setor_atual = linhas[i+1].strip()
                        break

                # Limpa o nome do setor
                setor_limpo = setor_atual
                if "-" in setor_atual:
                    setor_limpo = setor_atual.split("-", 1)[-1].strip()
                setor_limpo = re.sub(r'\s+', ' ', setor_limpo).title()
                
                # A CORREÇÃO DE OURO: Se o setor vier em branco, jamais descarte os dados!
                if not setor_limpo or setor_limpo == "Não Identificado" or setor_limpo == "Matrícula Nome Desligamento":
                    setor_limpo = f"Setor não identificado (Página {num_pagina+1})"

                # 3. Caça aos Valores (Mantém o maior da página)
                he_max_pag = 0.0
                grat_max_pag = 0.0

                for linha in linhas:
                    linha_lower = linha.lower()
                    
                    tem_he = any(kw in linha_lower for kw in ['hora extra', 'horas extras', 'comp.carga', 'comp. carga'])
                    tem_grat = any(kw in linha_lower for kw in ['gratific', 'samu'])

                    if tem_he or tem_grat:
                        # Pega o último número financeiro da linha
                        numeros = re.findall(r'(?<!\d)\d{1,3}(?:[\.\,]\d{3})*[\.\,]\d{2}(?!\d)', linha)
                        if numeros:
                            valor = limpar_valor(numeros[-1])
                            
                            if tem_he and valor > he_max_pag:
                                he_max_pag = valor
                                log_extracao.append(f"Pág {num_pagina+1} | {setor_limpo} | HE: R$ {valor:.2f}")
                                
                            if tem_grat and valor > grat_max_pag:
                                grat_max_pag = valor
                                log_extracao.append(f"Pág {num_pagina+1} | {setor_limpo} | Gratificações: R$ {valor:.2f}")

                # Só salva se tiver encontrado algum valor financeiro
                if he_max_pag > 0 or grat_max_pag > 0:
                    dados_gerais.append({
                        'Mês/Ano': mes_atual,
                        'Setor': setor_limpo,
                        'Horas Extras (R$)': he_max_pag,
                        'Gratificações (R$)': grat_max_pag
                    })

    if not dados_gerais:
        return pd.DataFrame(), log_extracao

    df = pd.DataFrame(dados_gerais)
    
    # Agrupa por Mês e Setor pegando o valor máximo encontrado (o Resumo do Setor)
    df_agrupado = df.groupby(['Mês/Ano', 'Setor'], as_index=False).max()
    df_agrupado['Total Geral (R$)'] = df_agrupado['Horas Extras (R$)'] + df_agrupado['Gratificações (R$)']
    
    return df_agrupado.sort_values(by='Mês/Ano'), log_extracao

# --- INTERFACE DO APLICATIVO ---
arquivos_upload = st.file_uploader("Upload dos Resumos Contábeis (PDF)", type=["pdf"], accept_multiple_files=True)

if arquivos_upload:
    with st.spinner('Extraindo dados sem bloqueios...'):
        df, logs = processar_pdf(arquivos_upload)
        
    with st.expander("🛠️ Log do Extrator Salva-Vidas"):
        if logs:
            for log in logs:
                st.text(log)
        else:
            st.text("Nenhum valor localizado.")
            
    if not df.empty:
        st.success("Dados resgatados com sucesso!")
        
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
