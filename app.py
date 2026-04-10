import streamlit as st
import pandas as pd

st.set_page_config(page_title="Leitor de Excel - Fiorilli", layout="wide")
st.title("Análise da Estrutura da Planilha")
st.markdown("Suba o arquivo exportado em **Excel** para vermos como as colunas estão organizadas.")

arquivo_upload = st.file_uploader("Upload do Relatório (Excel/XML)", type=["xlsx", "xls", "xml"])

if arquivo_upload:
    try:
        # Tenta ler a planilha
        df = pd.read_excel(arquivo_upload)
        
        st.success("Planilha lida com sucesso!")
        
        st.write("### 👀 Visão Bruta dos Dados")
        st.write(f"Total de linhas: {len(df)}")
        st.dataframe(df)
        
        st.info("Por favor, tire um print dessa tabela ou me diga quais são os nomes exatos das colunas onde estão os Setores, as Horas Extras e as Gratificações!")
        
    except Exception as e:
        st.error(f"Erro ao tentar ler o arquivo: {e}")
        st.write("Se der erro, tente exportar na opção 'Excel table (XML)' ou 'Open Document Spreadsheet' e tente novamente.")
