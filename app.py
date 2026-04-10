import streamlit as st
import pandas as pd

st.set_page_config(page_title="Leitor de Relatórios", layout="wide")
st.title("Análise da Estrutura da Planilha")
st.markdown("Suba o arquivo exportado da Fiorilli. O sistema tentará quebrar a proteção de formato falso.")

# Aceita vários tipos de formatos para teste
arquivo_upload = st.file_uploader("Upload do Relatório", type=["xlsx", "xls", "xml", "html", "txt", "csv"])

if arquivo_upload:
    df = None
    
    try:
        # Tentativa 1: Leitura de Excel Padrão (Caso você tenha feito o 'Salvar Como')
        df = pd.read_excel(arquivo_upload)
        st.success("✅ Arquivo lido perfeitamente como Excel Padrão!")
        
    except Exception as e1:
        try:
            # Tentativa 2: Leitura de HTML disfarçado (A tática principal da Fiorilli)
            arquivo_upload.seek(0) # Volta o leitor pro começo do arquivo
            tabelas = pd.read_html(arquivo_upload)
            df = tabelas[0] # Pega a primeira tabela encontrada
            st.success("✅ Arquivo lido! O sistema identificou que era um HTML disfarçado de Excel.")
            
        except Exception as e2:
            try:
                # Tentativa 3: Leitura como Texto/CSV (Caso exporte na opção 'Text')
                arquivo_upload.seek(0)
                df = pd.read_csv(arquivo_upload, sep='\t')
                st.success("✅ Arquivo lido! O sistema identificou que era um arquivo de Texto tabulado.")
                
            except Exception as e3:
                st.error("❌ Não foi possível ler o formato deste arquivo automaticamente.")
                st.write(f"Erro principal: {e1}")

    if df is not None:
        st.write("### 👀 Visão Bruta dos Dados")
        st.write(f"Total de linhas lidas: {len(df)}")
        st.dataframe(df)
        
        st.info("Deu certo! Tire um print dessa tabela ou escreva aqui os nomes das colunas que indicam o **Setor**, a **Rubrica/Descrição** e o **Valor** para montarmos o dashboard final.")
