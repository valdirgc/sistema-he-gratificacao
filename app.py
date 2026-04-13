import streamlit as st
import pandas as pd
import plotly.express as px
import pdfplumber
import re

st.set_page_config(page_title="Dashboard Setorial", layout="wide")
st.title("Controle Setorial - Horas Extras e Gratificações")
st.markdown("Faça o upload dos **Resumos Contábeis em PDF** da Fiorilli.")

def limpar_valor(valor_str):
    # Transforma em número real com segurança
    digitos = re.sub(r'\D', '', str(valor_str))
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
            setor_atual = "Não Identificado"

            for num_pagina, pagina in enumerate(pdf.pages):
                texto = pagina.extract_text()
                if not texto: continue
                
                # 1. Busca Segura do Setor (Sem usar Regex que dá erro)
                for linha in texto.split('\n'):
                    if "Local de Trabalho:" in linha:
                        partes = linha.split("Local de Trabalho:")
                        if len(partes) > 1:
                            s = partes[1].strip()
                            # Limpa vazamentos de outras colunas na mesma linha
                            s = s.split('Mês/Ano')[0].split('Folha')[0].split('Página')[0].strip()
                            if "-" in s:
                                setor_atual = s.split("-", 1)[-1].strip().title()
                            elif s:
                                setor_atual = s.title()
                        break
                
                # 2. Busca Segura do Mês/Ano
                for i, linha in enumerate(texto.split('\n')):
                    if "Mês/Ano" in linha:
                        match_mes = re.search(r"(\d{2}/\d{4})", linha)
                        if match_mes:
                            mes_atual = match_mes.group(1)
                        elif i + 1 < len(texto.split('\n')):
                            match_mes_prox = re.search(r"(\d{2}/\d{4})", texto.split('\n')[i+1])
                            if match_mes_prox:
                                mes_atual = match_mes_prox.group(1)
                        break
                        
                if setor_atual == "Não Identificado":
                    continue
                    
                chave = f"{setor_atual}_{mes_atual}"
                if chave not in dados_setores:
                    dados_setores[chave] = {
                        'Mês/Ano': mes_atual,
                        'Setor': setor_atual,
                        'Horas Extras (R$)': 0.0,
                        'Gratificações (R$)': 0.0
                    }
                    
                # 3. Extração Direta das Tabelas Ocultas (A Tática que Funcionou!)
                tabelas = pagina.extract_tables()
                for tabela in tabelas:
                    for linha_tabela in tabela:
                        if not linha_tabela: continue
                        
                        # Limpa quebras de linha dentro das células e transforma em string
                        celulas = [str(c).replace('\n', ' ').strip() for c in linha_tabela if c]
                        texto_linha = " ".join(celulas).lower()
                        
                        # Pula o cabeçalho de totais gerais da prefeitura para não sujar o gráfico do setor
                        if any(x in texto_linha for x in ['fgts a recolher', 'total a empenhar', 'patronal', 'vantagens']):
                            continue
                        
                        tem_he = any(kw in texto_linha for kw in ['hora extra', 'horas extras', 'comp.carga'])
                        tem_grat = any(kw in texto_linha for kw in ['gratific', 'samu'])
                        
                        if tem_he or tem_grat:
                            # Acha qualquer número financeiro
                            numeros = re.findall(r'(?<!\d)\d{1,3}(?:[\.\,]\d{3})*[\.\,]\d{2}(?!\d)', texto_linha)
                            
                            if numeros:
                                valor_final = limpar_valor(numeros[-1])
                                
                                # Pega sempre o maior valor encontrado (que representa o Total do Resumo Setorial)
                                if tem_he and valor_final > dados_setores[chave]['Horas Extras (R$)']:
                                    dados_setores[chave]['Horas Extras (R$)'] = valor_final
                                    log_extracao.append(f"✅ Pág {num_pagina+1} | {setor_atual} | HE: R$ {valor_final:.2f} | Tabela: {texto_linha}")
                                    
                                if tem_grat and valor_final > dados_setores[chave]['Gratificações (R$)']:
                                    dados_setores[chave]['Gratificações (R$)'] = valor_final
                                    log_extracao.append(f"✅ Pág {num_pagina+1} | {setor_atual} | Gratificações: R$ {valor_final:.2f} | Tabela: {texto_linha}")

    if not dados_setores:
        return pd.DataFrame(), log_extracao

    df = pd.DataFrame(list(dados_setores.values()))
    df['Total Geral (R$)'] = df['Horas Extras (R$)'] + df['Gratificações (R$)']
    
    # Exclui os setores sem lançamentos nas rubricas
    df = df[df['Total Geral (R$)'] > 0]
    
    return df.sort_values(by='Mês/Ano'), log_extracao

# --- INTERFACE DO APLICATIVO ---
arquivos_upload = st.file_uploader("Upload dos Resumos Contábeis (PDF)", type=["pdf"], accept_multiple_files=True)

if arquivos_upload:
    with st.spinner('Consolidando os dados de forma segura...'):
        df, logs = processar_pdf(arquivos_upload)
        
    with st.expander("🛠️ Log das Tabelas Ocultas (Valores validados)"):
        if logs:
            for log in logs:
                st.text(log)
        else:
            st.text("Nenhum valor financeiro encontrado nas tabelas ocultas.")
            
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
