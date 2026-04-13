import streamlit as st
import pandas as pd
import pdfplumber

st.set_page_config(page_title="Raio-X do PDF", layout="wide")
st.title("🕵️‍♂️ Raio-X do Resumo Contábil (Fiorilli)")
st.markdown("Chega de tentar adivinhar. Vamos ver exatamente como o Python enxerga esse arquivo.")

arquivo_upload = st.file_uploader("Suba o Resumo Contábil (PDF)", type=["pdf"])

if arquivo_upload:
    with pdfplumber.open(arquivo_upload) as pdf:
        total_paginas = len(pdf.pages)
        st.success(f"PDF carregado! O arquivo tem {total_paginas} páginas.")
        
        st.write("---")
        # Deixei a página 6 como padrão porque sei que lá no Hospital Municipal tem Hora Extra
        pagina_alvo = st.number_input("Qual página você quer investigar?", min_value=1, max_value=total_paginas, value=6)
        
        # Pega a página escolhida (o índice começa no zero, por isso o -1)
        page = pdf.pages[pagina_alvo - 1]
        
        # Cria abas para vermos as diferentes formas de leitura
        tab1, tab2, tab3, tab4 = st.tabs(["1. Texto Bruto", "2. Texto com Layout", "3. Tabelas Ocultas", "4. Palavra por Palavra"])
        
        with tab1:
            st.subheader("Leitura Padrão")
            st.write("Assim é como o extrator normal puxa os dados (ignorando colunas).")
            texto_bruto = page.extract_text()
            st.text_area("Resultado:", texto_bruto, height=500)
            
        with tab2:
            st.subheader("Leitura Visual")
            st.write("Assim é como ele tenta recriar os espaços em branco da tela.")
            texto_layout = page.extract_text(layout=True)
            st.text_area("Resultado:", texto_layout, height=500)
            
        with tab3:
            st.subheader("Leitura de Tabelas (O Segredo?)")
            st.write("Às vezes, os sistemas desenham tabelas invisíveis. Vamos ver se o Python acha alguma grade de dados aqui:")
            tabelas = page.extract_tables()
            if tabelas:
                for i, tabela in enumerate(tabelas):
                    st.write(f"Tabela Encontrada {i+1}:")
                    df = pd.DataFrame(tabela)
                    st.dataframe(df, use_container_width=True)
            else:
                st.warning("O Python não encontrou nenhuma tabela estruturada (com linhas e colunas) nesta página.")
                
        with tab4:
            st.subheader("Leitura Palavra por Palavra")
            st.write("Aqui vemos exatamente como ele recorta cada pedaço de texto. Observe se o nome e o valor estão colados!")
            palavras = page.extract_words()
            if palavras:
                # Cria uma tabela mostrando o texto e a posição dele na tela
                df_palavras = pd.DataFrame(palavras)[['text', 'x0', 'top']]
                df_palavras.columns = ['Texto Lido', 'Posição Horizontal (X)', 'Posição Vertical (Y)']
                st.dataframe(df_palavras, use_container_width=True, height=500)
            else:
                st.warning("Nenhuma palavra extraída.")
