import streamlit as st
import pandas as pd
import plotly.express as px
import pdfplumber
import re

# 1. Configuração da Página
st.set_page_config(page_title="Dashboard Setorial", layout="wide")
st.title("Controle Setorial - Horas Extras e Gratificações")
st.markdown("Faça o upload de **um ou vários** relatórios de *Resumo Contábil* para gerar o comparativo.")

# 2. Função Inteligente para ler valores financeiros
def extrair_valor_financeiro(texto):
    """
    Encontra o último bloco de números em uma linha de texto.
    Resolve o problema do PDF gerar valores como '18.955.68' em vez de '18.955,68'
    """
    matches = re.findall(r'[\d\.,]+', texto)
    if not matches:
        return 0.0
    
    ultimo_num = matches[-1]
    digitos = re.sub(r'\D', '', ultimo_num)
    
    if not digitos:
        return 0.0
    return float(digitos) / 100.0

# 3. Processamento do PDF Setorial
@st.cache_data
def processar_relatorios(arquivos):
    todos_dados = []

    for arquivo in arquivos:
        mes_ano = "Indefinido"
        dados_setores = {}
        setor_atual = "Não Identificado"
        
        with pdfplumber.open(arquivo) as pdf:
            for pagina in pdf.pages:
                texto = pagina.extract_text()
                if not texto: continue
                
                linhas = texto.split('\n')
                
                for i, linha in enumerate(linhas):
                    linha_lower = linha.lower()
                    
                    # Captura Mês/Ano
                    if "mês/ano" in linha_lower:
                        match_data = re.search(r"(\d{2}/\d{4})", linha)
                        if match_data:
                            mes_ano = match_data.group(1)
                        elif i + 1 < len(linhas):
                            match_data_prox = re.search(r"(\d{2}/\d{4})", linhas[i+1])
                            if match_data_prox:
                                mes_ano = match_data_prox.group(1)
                                
                    # Captura o Setor
                    if "local de trabalho:" in linha_lower:
                        partes = linha.split("Local de Trabalho:")
                        if len(partes) > 1:
                            setor_bruto = partes[1].strip()
                            # Tira o código da frente (ex: "001001 - Hospital" -> "Hospital")
                            if "-" in setor_bruto:
                                setor_atual = setor_bruto.split("-", 1)[1].strip()
                            else:
                                setor_atual = setor_bruto
                        
                        # Cria o "balde" para guardar os valores desse setor neste mês
                        chave = f"{setor_atual}_{mes_ano}"
                        if chave not in dados_setores:
                            dados_setores[chave] = {
                                'Mês/Ano': mes_ano,
                                'Setor': setor_atual,
                                'Horas Extras 50%': 0.0,
                                'Horas Extras 100%': 0.0,
                                'Comp. Carga Horária': 0.0,
                                'Gratificações': 0.0
                            }
                            
                    # Pula as linhas até achar o primeiro setor
                    if setor_atual == "Não Identificado":
                        continue
                        
                    chave = f"{setor_atual}_{mes_ano}"
                    
                    # Varre as rubricas específicas que você pediu
                    if "horas extras 50%" in linha_lower:
                        dados_setores[chave]['Horas Extras 50%'] += extrair_valor_financeiro(linha)
                    elif "horas extras 100%" in linha_lower:
                        dados_setores[chave]['Horas Extras 100%'] += extrair_valor_financeiro(linha)
                    elif "comp.carga horária" in linha_lower or "comp. carga horária" in linha_lower:
                        dados_setores[chave]['Comp. Carga Horária'] += extrair_valor_financeiro(linha)
                    elif "gratific lei" in linha_lower or "gratificação samu" in linha_lower:
                        dados_setores[chave]['Gratificações'] += extrair_valor_financeiro(linha)
                        
        # Junta os dados do PDF atual na lista geral
        todos_dados.extend(list(dados_setores.values()))
        
    if not todos_dados:
        return pd.DataFrame()
        
    df = pd.DataFrame(todos_dados)
    
    # Remove setores que não tiveram NENHUM lançamento nessas 4 rubricas para limpar a tela
    df['Soma_Verificacao'] = df['Horas Extras 50%'] + df['Horas Extras 100%'] + df['Comp. Carga Horária'] + df['Gratificações']
    df = df[df['Soma_Verificacao'] > 0].drop(columns=['Soma_Verificacao'])
    
    # Cria a coluna de Total Geral do Setor
    df['Total Geral (R$)'] = df['Horas Extras 50%'] + df['Horas Extras 100%'] + df['Comp. Carga Horária'] + df['Gratificações']
    
    # Ordena pelo mês/ano para os gráficos ficarem na sequência certa
    df = df.sort_values(by='Mês/Ano')
    
    return df

# 4. Interface do Usuário
# O accept_multiple_files=True permite selecionar vários PDFs ao mesmo tempo
arquivos_upload = st.file_uploader("Upload dos Resumos Contábeis (PDF)", type=["pdf"], accept_multiple_files=True)

if arquivos_upload:
    with st.spinner('Processando os relatórios...'):
        df = processar_relatorios(arquivos_upload)
        
    if not df.empty:
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
            
            st.subheader("📋 Tabela Consolidada (Todos os Setores)")
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

        # Configura a exibição financeira na tabela
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
        st.warning("Nenhum lançamento de Hora Extra ou Gratificação foi encontrado nos documentos enviados.")
else:
    st.info("Aguardando o envio dos arquivos PDF.")
