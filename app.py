import streamlit as st
import pandas as pd
import plotly.express as px
import pdfplumber
import re

# 1. Configuração da Página
st.set_page_config(page_title="Dashboard Setorial", layout="wide")
st.title("Controle Setorial - Horas Extras e Gratificações")
st.markdown("Faça o upload de **um ou vários** relatórios de *Resumo Contábil* para gerar o comparativo.")

# 2. Processamento à Prova de Quebras de Linha
@st.cache_data
def processar_relatorios(arquivos):
    todos_dados = {}
    log_extracao = [] # Guarda o histórico para você auditar depois

    for arquivo in arquivos:
        with pdfplumber.open(arquivo) as pdf:
            for num_pagina, pagina in enumerate(pdf.pages):
                texto = pagina.extract_text()
                if not texto: continue
                
                linhas = texto.split('\n')
                # O Pulo do Gato: Transforma toda a página numa linha só, removendo quebras chatas
                texto_limpo = re.sub(r'\s+', ' ', texto) 
                
                # Extrai Mês/Ano
                mes_ano = "Indefinido"
                for i, linha in enumerate(linhas):
                    if "Mês/Ano" in linha:
                        match = re.search(r"(\d{2}/\d{4})", linha)
                        if match: mes_ano = match.group(1)
                        elif i+1 < len(linhas):
                            match = re.search(r"(\d{2}/\d{4})", linhas[i+1])
                            if match: mes_ano = match.group(1)
                        break
                        
                # Extrai Setor
                setor_atual = "Não Identificado"
                for i, linha in enumerate(linhas):
                    if "Local de Trabalho:" in linha:
                        parte = linha.split("Local de Trabalho:")[1].strip()
                        if not parte and i+1 < len(linhas):
                            parte = linhas[i+1].strip()
                            
                        # Limpa os códigos numéricos iniciais
                        if "-" in parte:
                            setor_atual = parte.split("-", 1)[1].strip()
                        else:
                            setor_atual = parte
                        break
                        
                if setor_atual == "Não Identificado" or setor_atual == "":
                    continue
                    
                # Cria a "gaveta" do setor
                chave = f"{setor_atual}_{mes_ano}"
                if chave not in todos_dados:
                    todos_dados[chave] = {
                        'Mês/Ano': mes_ano,
                        'Setor': setor_atual,
                        'Horas Extras 50%': 0.0,
                        'Horas Extras 100%': 0.0,
                        'Comp. Carga Horária': 0.0,
                        'Gratificações': 0.0
                    }
                
                # Dicionário de busca (Adicionei variações de espaçamento por segurança)
                padroes = {
                    'Horas Extras 50%': r"horas extras 50%",
                    'Horas Extras 100%': r"horas extras 100%",
                    'Comp. Carga Horária': r"comp[\.\s]*carga hor[aá]ria",
                    'Gratificações': r"(?:gratific\s*lei|gratifica[cç][aã]o\s*samu)"
                }
                
                # Caça os valores no texto unificado
                for rubrica, padrao in padroes.items():
                    for match in re.finditer(padrao, texto_limpo, re.IGNORECASE):
                        # Pega uma janela de texto logo após o nome da rubrica
                        inicio = match.end()
                        trecho = texto_limpo[inicio:inicio+80]
                        
                        # Acha todos os números formatados como moeda (X,XX ou X.XXX,XX)
                        matches_moeda = re.findall(r'\d+(?:[\.\,]\d{3})*[\.\,]\d{2}', trecho)
                        if matches_moeda:
                            # O valor pago é sempre o último da sequência de Referência/Quantidade
                            valor_str = matches_moeda[:2][-1] 
                            
                            # Limpa os pontos e vírgulas para converter em Float
                            digitos = re.sub(r'\D', '', valor_str)
                            if digitos:
                                valor_final = float(digitos) / 100.0
                                todos_dados[chave][rubrica] += valor_final
                                log_extracao.append(f"✅ {setor_atual} | Achou {rubrica}: R$ {valor_final:.2f}")

    df_bruto = pd.DataFrame(list(todos_dados.values()))
    return df_bruto, log_extracao

# 3. Interface Visual
arquivos_upload = st.file_uploader("Upload dos Resumos Contábeis (PDF)", type=["pdf"], accept_multiple_files=True)

if arquivos_upload:
    with st.spinner('Analisando as matrizes contábeis...'):
        df, logs = processar_relatorios(arquivos_upload)
        
    if not df.empty:
        # Coluna de Soma Total do Setor
        df['Total Geral (R$)'] = df['Horas Extras 50%'] + df['Horas Extras 100%'] + df['Comp. Carga Horária'] + df['Gratificações']
        
        # --- MODO DIAGNÓSTICO PARA AUDITORIA ---
        with st.expander("🛠️ Modo Diagnóstico (Clique para verificar o que o sistema conseguiu ler do PDF)"):
            st.write("Se um setor não aparecer nos gráficos, verifique aqui se ele foi encontrado pelo sistema:")
            st.dataframe(df)
            st.write("Registro de Leitura (Últimos valores processados):")
            for log in logs[-20:]: # Mostra os 20 últimos logs de captura
                st.text(log)

        # Remove os setores que ficaram com R$ 0,00 em tudo
        df = df[df['Total Geral (R$)'] > 0]
        
        if df.empty:
            st.warning("O sistema leu o arquivo, mas todos os valores para as rubricas especificadas vieram zerados.")
        else:
            df = df.sort_values(by='Mês/Ano')
            
            # --- DASHBOARD ---
            st.sidebar.header("Filtros Setoriais")
            lista_setores = df['Setor'].unique().tolist()
            lista_setores.sort()
            lista_setores.insert(0, "Visão Geral (Todos os Setores)")
            
            setor_selecionado = st.sidebar.selectbox("Escolha o Local de Trabalho", lista_setores)
            
            st.divider()
            
            if setor_selecionado == "Visão Geral (Todos os Setores)":
                st.subheader("📊 Comparativo Mensal - Visão Geral do Município")
                df_grafico = df.groupby('Mês/Ano')[['Horas Extras 50%', 'Horas Extras 100%', 'Comp. Carga Horária', 'Gratificações']].sum().reset_index()
                
                fig = px.bar(
                    df_grafico, 
                    x='Mês/Ano', 
                    y=['Horas Extras 50%', 'Horas Extras 100%', 'Comp. Carga Horária', 'Gratificações'],
                    barmode='group',
                    labels={'value': 'Valor (R$)', 'variable': 'Tipo de Pagamento'}
                )
                st.plotly_chart(fig, use_container_width=True)
                
                st.subheader("📋 Consolidado Geral da Prefeitura")
                df_tabela = df
                
            else:
                st.subheader(f"📊 Evolução Mensal - {setor_selecionado}")
                df_setor = df[df['Setor'] == setor_selecionado]
                
                fig = px.line(
                    df_setor, 
                    x='Mês/Ano', 
                    y=['Horas Extras 50%', 'Horas Extras 100%', 'Comp. Carga Horária', 'Gratificações', 'Total Geral (R$)'],
                    markers=True,
                    labels={'value': 'Valor (R$)', 'variable': 'Rubrica'}
                )
                st.plotly_chart(fig, use_container_width=True)
                
                st.subheader(f"📋 Lançamentos - {setor_selecionado}")
                df_tabela = df_setor

            # Formatação Financeira para a Tabela
            st.dataframe(
                df_tabela,
                column_config={
                    "Horas Extras 50%": st.column_config.NumberColumn(format="R$ %.2f"),
                    "Horas Extras 100%": st.column_config.NumberColumn(format="R$ %.2f"),
                    "Comp. Carga Horária": st.column_config.NumberColumn(format="R$ %.2f"),
                    "Gratificações": st.column_config.NumberColumn(format="R$ %.2f"),
                    "Total Geral (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
                },
                hide_index=True,
                use_container_width=True
            )

    else:
        st.warning("O documento foi processado, mas não possui o formato esperado de 'Resumo Contábil'.")
else:
    st.info("Aguardando o envio dos arquivos PDF.")
