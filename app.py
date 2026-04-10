import streamlit as st
import pandas as pd
import plotly.express as px
import pdfplumber
import re

# 1. Configuração da Página
st.set_page_config(page_title="Dashboard Setorial", layout="wide")
st.title("Controle Setorial - Horas Extras e Gratificações")
st.markdown("Faça o upload de **um ou vários** relatórios de *Resumo Contábil* para gerar o comparativo.")

# 2. Processamento do PDF (Busca Flexível)
@st.cache_data
def processar_relatorios(arquivos):
    todos_dados = {}

    for arquivo in arquivos:
        with pdfplumber.open(arquivo) as pdf:
            for pagina in pdf.pages:
                texto = pagina.extract_text()
                if not texto: continue
                
                # Acha o Mês/Ano da página
                mes_ano = "Indefinido"
                match_mes = re.search(r"Mês/Ano\s*(\d{2}/\d{4})", texto, re.IGNORECASE)
                if match_mes:
                    mes_ano = match_mes.group(1)
                    
                # Acha o Setor da página
                setor_atual = "Não Identificado"
                match_setor = re.search(r"Local de Trabalho:\s*(?:[\d]+\s*-\s*)?([^\n]+)", texto, re.IGNORECASE)
                if match_setor:
                    setor_atual = match_setor.group(1).strip()
                    
                if setor_atual == "Não Identificado":
                    continue
                    
                # Cria a "gaveta" do setor para aquele mês se não existir
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
                
                # Mapeamento exato do que procurar
                padroes = {
                    'Horas Extras 50%': r"horas extras 50%",
                    'Horas Extras 100%': r"horas extras 100%",
                    'Comp. Carga Horária': r"comp[\.\s]*carga hor[aá]ria",
                    'Gratificações': r"(?:gratific lei|gratifica[cç][aã]o samu)"
                }
                
                # Caça os valores ignorando a bagunça do PDF
                for rubrica, padrao in padroes.items():
                    for match in re.finditer(padrao, texto, re.IGNORECASE):
                        # Pega o bloco de texto logo à frente da palavra encontrada (100 caracteres)
                        trecho = texto[match.end():match.end()+100]
                        
                        # Acha todos os números com formato financeiro (X,XX ou X.XXX,XX ou X.XXX.XX)
                        matches_monetarios = re.findall(r'\d+(?:[\.\,]\d{3})*[\.\,]\d{2}', trecho)
                        
                        if len(matches_monetarios) >= 2:
                            # O segundo número financeiro na tabela é sempre o Valor (o primeiro é a Referência)
                            valor_str = matches_monetarios[1] 
                            apenas_digitos = re.sub(r'\D', '', valor_str)
                            todos_dados[chave][rubrica] += float(apenas_digitos) / 100.0
                        elif len(matches_monetarios) == 1:
                            # Prevenção caso o PDF cole a quantidade no valor de referência
                            valor_str = matches_monetarios[0]
                            apenas_digitos = re.sub(r'\D', '', valor_str)
                            todos_dados[chave][rubrica] += float(apenas_digitos) / 100.0

    if not todos_dados:
        return pd.DataFrame()
        
    # Transforma o dicionário em Tabela (DataFrame)
    df = pd.DataFrame(list(todos_dados.values()))
    
    # Cria a coluna de Total e filtra os setores que estão zerados
    df['Total Geral (R$)'] = df['Horas Extras 50%'] + df['Horas Extras 100%'] + df['Comp. Carga Horária'] + df['Gratificações']
    df = df[df['Total Geral (R$)'] > 0]
    
    return df.sort_values(by='Mês/Ano')

# 3. Interface do Sistema
arquivos_upload = st.file_uploader("Upload dos Resumos Contábeis (PDF)", type=["pdf"], accept_multiple_files=True)

if arquivos_upload:
    with st.spinner('Lendo os relatórios e cruzando os dados...'):
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
            # Agrupa os totais do município por mês
            df_grafico = df.groupby('Mês/Ano')[['Horas Extras 50%', 'Horas Extras 100%', 'Comp. Carga Horária', 'Gratificações']].sum().reset_index()
            
            fig = px.bar(
                df_grafico, 
                x='Mês/Ano', 
                y=['Horas Extras 50%', 'Horas Extras 100%', 'Comp. Carga Horária', 'Gratificações'],
                barmode='group',
                labels={'value': 'Valor (R$)', 'variable': 'Tipo de Pagamento'}
            )
            st.plotly_chart(fig, use_container_width=True)
            
            st.subheader("📋 Consolidado Setorial")
            df_tabela = df
            
        else:
            st.subheader(f"📊 Evolução Mensal - {setor_selecionado}")
            df_setor = df[df['Setor'] == setor_selecionado]
            
            # Gráfico de linhas para ver a evolução de cada rubrica no setor escolhido
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

        # Exibe a tabela bonitinha formatada em Reais
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
