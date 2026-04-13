import streamlit as st
import pandas as pd
import plotly.express as px
import pdfplumber
import re

st.set_page_config(page_title="Dashboard Setorial", layout="wide")
st.title("Controle Setorial - Horas Extras e Gratificações")
st.markdown("Faça o upload dos **Resumos Contábeis em PDF** da Fiorilli.")

# Remove qualquer letra ou pontuação inútil e força os 2 últimos dígitos como centavos
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
                
                linhas = texto.split('\n')
                
                mes_ano = "Indefinido"
                setor_atual = "Não Identificado"
                
                # PASSO 1: Descobrir o Setor e o Mês da Página
                for i, linha in enumerate(linhas):
                    linha_lower = linha.lower()
                    
                    if "mês/ano" in linha_lower:
                        match_mes = re.search(r"(\d{2}/\d{4})", linha)
                        if match_mes: 
                            mes_ano = match_mes.group(1)
                        elif i + 1 < len(linhas):
                            match_mes_prox = re.search(r"(\d{2}/\d{4})", linhas[i+1])
                            if match_mes_prox: mes_ano = match_mes_prox.group(1)
                            
                    if "local de trabalho:" in linha_lower:
                        setor_bruto = re.split(r'local de trabalho:', linha, flags=re.IGNORECASE)[1].strip()
                        # Se estiver vazio na frente, pega a linha de baixo
                        if not setor_bruto and i + 1 < len(linhas):
                            setor_bruto = linhas[i+1].strip()
                        
                        # Limpa qualquer sujeira que a Fiorilli jogue na mesma linha
                        setor_bruto = re.split(r'\s+mês/ano|\s+folha mensal|\s+total|\s+resumo', setor_bruto, flags=re.IGNORECASE)[0].strip()
                        if "-" in setor_bruto:
                            setor_atual = setor_bruto.split("-", 1)[1].strip()
                        else:
                            setor_atual = setor_bruto

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

                # PASSO 2: Caçar os valores à prova de erros de espaçamento
                for linha in linhas:
                    linha_lower = linha.lower()
                    
                    # Regex absoluto: Acha valores como 1.234,56 mesmo se estiverem grudados em letras
                    valores_moeda = re.findall(r'(?<!\d)\d{1,3}(?:[\.\,]\d{3})*[\.\,]\d{2}(?!\d)', linha)
                    
                    if valores_moeda:
                        valor_linha = limpar_valor(valores_moeda[-1]) # Pega o último número financeiro da linha
                        
                        # Captura Horas Extras e Complemento de Carga Horária
                        if any(kw in linha_lower for kw in ["hora extra", "horas extras", "comp.carga", "comp. carga"]):
                            # Sempre sobrepõe pelo MAIOR valor (o que garante que ele vai pegar o Total do Resumo e não de um só funcionário)
                            if valor_linha > dados_setores[chave]['Horas Extras (R$)']:
                                dados_setores[chave]['Horas Extras (R$)'] = valor_linha
                                linha_log = linha.strip()[:80] # Pega só um pedaço para o log não ficar gigante
                                log_extracao.append(f"Pág {num_pagina+1} | {setor_atual} -> Achou HE: R$ {valor_linha:.2f} (Lido de: {linha_log})")
                                
                        # Captura Gratificações (SAMU, Lei 2291, etc)
                        if any(kw in linha_lower for kw in ["gratific", "gratifica"]):
                            if valor_linha > dados_setores[chave]['Gratificações (R$)']:
                                dados_setores[chave]['Gratificações (R$)'] = valor_linha
                                linha_log = linha.strip()[:80]
                                log_extracao.append(f"Pág {num_pagina+1} | {setor_atual} -> Achou Gratificações: R$ {valor_linha:.2f} (Lido de: {linha_log})")

    if not dados_setores:
        return pd.DataFrame(), log_extracao

    df = pd.DataFrame(list(dados_setores.values()))
    df['Total Geral (R$)'] = df['Horas Extras (R$)'] + df['Gratificações (R$)']
    
    # Exclui setores onde o valor final foi R$ 0,00
    df = df[df['Total Geral (R$)'] > 0]
    
    return df.sort_values(by='Mês/Ano'), log_extracao


# --- INTERFACE DO APLICATIVO ---
arquivos_upload = st.file_uploader("Upload dos Resumos Contábeis (PDF)", type=["pdf"], accept_multiple_files=True)

if arquivos_upload:
    with st.spinner('Extraindo informações linha por linha...'):
        df, logs = processar_pdf(arquivos_upload)
        
    # --- MODO DIAGNÓSTICO ---
    with st.expander("🛠️ Log de Extração (Clique para ver as linhas exatas que o sistema capturou)"):
        if logs:
            for log in logs:
                st.text(log)
        else:
            st.text("Nenhum valor financeiro atrelado às palavras-chave foi encontrado.")
            
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
