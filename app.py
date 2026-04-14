import streamlit as st
import pandas as pd
import plotly.express as px
import re
import pytesseract
from pdf2image import convert_from_bytes

st.set_page_config(page_title="Auditoria de Folha - Jaborandi", layout="wide")
st.title("🏦 Sistema de Auditoria com OCR Integrado")
st.markdown("Faça o upload do **PDF original**. O sistema converterá as páginas em imagens e fará a leitura profunda (OCR). *Atenção: Por usar inteligência artificial de leitura de imagens, arquivos grandes podem levar alguns minutos.*")

RUBRICAS = {
    '006': {'nome': '006 - HE 50%', 'tipo': 'Hora Extra'},
    '011': {'nome': '011 - HE 100%', 'tipo': 'Hora Extra'},
    '018': {'nome': '018 - HE Mês Ant.', 'tipo': 'Hora Extra'},
    '031': {'nome': '031 - Gratific. Lei', 'tipo': 'Gratificação'},
    '089': {'nome': '089 - Comp. Carga', 'tipo': 'Hora Extra'},
    '812': {'nome': '812 - Gratificação SAMU', 'tipo': 'Gratificação'}
}

def limpar_valor(valor_str):
    digitos = re.sub(r'\D', '', str(valor_str))
    return float(digitos) / 100.0 if digitos else 0.0

@st.cache_data
def processar_arquivos_ocr(arquivos):
    registros = []
    log_extracao = []

    for arquivo in arquivos:
        pdf_bytes = arquivo.read()
        
        # Converte o PDF inteiro em uma lista de imagens
        imagens = convert_from_bytes(pdf_bytes, dpi=200)
        
        mes_arquivo = "Indefinido"
        
        # Barra de progresso para o usuário não achar que travou
        progress_bar = st.progress(0)
        status_text = st.empty()

        for num_pag, imagem in enumerate(imagens):
            status_text.text(f"Lendo página {num_pag + 1} de {len(imagens)} do arquivo {arquivo.name}...")
            
            # Aplica o OCR na imagem (forçando o idioma português)
            texto_ocr = pytesseract.image_to_string(imagem, lang='por')
            linhas = texto_ocr.split('\n')
            
            setor_atual = "Não Identificado"

            for i, linha in enumerate(linhas):
                linha_limpa = linha.strip()

                # 1. Trava do Mês/Ano: Só busca se ainda estiver Indefinido
                if mes_arquivo == "Indefinido" and "Mês/Ano" in linha_limpa:
                    match = re.search(r"(\d{2}/\d{4})", linha_limpa)
                    if match: 
                        mes_arquivo = match.group(1)
                    elif i + 1 < len(linhas):
                        match2 = re.search(r"(\d{2}/\d{4})", linhas[i+1])
                        if match2: mes_arquivo = match2.group(1)

                # 2. Captura do Setor pelo OCR
                if "Local de Trabalho:" in linha_limpa or "Trabalho:" in linha_limpa:
                    try:
                        parte = linha_limpa.split("Trabalho:")[1].strip()
                    except:
                        parte = ""
                        
                    if not parte and i + 1 < len(linhas):
                        parte = linhas[i+1].strip()

                    if parte:
                        parte = re.sub(r'["\',]', '', parte).strip()
                        if "-" in parte:
                            setor_atual = parte.split("-", 1)[1].strip().title()
                        else:
                            setor_atual = parte.title()

                # 3. Captura das Rubricas
                match_rubrica = re.search(r'^"?\s*(006|011|018|031|089|812)\b', linha_limpa)
                if match_rubrica:
                    codigo = match_rubrica.group(1)
                    numeros = re.findall(r'(?<!\d)\d{1,3}(?:[\.\,]\d{3})*[\.\,]\d{2}(?!\d)', linha_limpa)

                    if not numeros:
                        bloco = ""
                        for j in range(1, 4):
                            if i+j < len(linhas):
                                bloco += " " + linhas[i+j]
                        numeros = re.findall(r'(?<!\d)\d{1,3}(?:[\.\,]\d{3})*[\.\,]\d{2}(?!\d)', bloco)

                    if numeros:
                        valor = limpar_valor(numeros[-1])
                        if valor > 0:
                            registros.append({
                                'Arquivo': arquivo.name,
                                'Página': num_pag + 1,
                                'Mês/Ano': mes_arquivo, # Usa a variável travada
                                'Setor': setor_atual,
                                'Código': codigo,
                                'Rubrica': RUBRICAS[codigo]['nome'],
                                'Tipo': RUBRICAS[codigo]['tipo'],
                                'Valor (R$)': valor
                            })
                            log_extracao.append(f"✅ Pág {num_pag+1} | {mes_arquivo} | {setor_atual} | {RUBRICAS[codigo]['nome']}: R$ {valor:.2f}")

            # Atualiza a barra de progresso
            progress_bar.progress((num_pag + 1) / len(imagens))

        progress_bar.empty()
        status_text.empty()

    if not registros:
        return pd.DataFrame(), log_extracao

    df = pd.DataFrame(registros)
    
    # Preenche retroativamente os meses que falharam no início antes de achar a data
    mes_oficial = df[df['Mês/Ano'] != 'Indefinido']['Mês/Ano'].max()
    if pd.notna(mes_oficial):
        df['Mês/Ano'] = mes_oficial

    # Agrupa pelo máximo para evitar duplicações do OCR na mesma página
    df_db = df.groupby(['Arquivo', 'Mês/Ano', 'Setor', 'Código', 'Rubrica', 'Tipo'], as_index=False)['Valor (R$)'].max()
    return df_db, log_extracao


arquivos_upload = st.file_uploader("Upload dos Resumos (PDF Original)", type=["pdf"], accept_multiple_files=True)

if arquivos_upload:
    df_bruto, logs = processar_arquivos_ocr(arquivos_upload)

    if not df_bruto.empty:
        st.success("Leitura OCR concluída com sucesso!")
        
        st.subheader("1. 🛠️ Banco de Dados e Mapeamento de Setores")
        st.info("Aqui estão os lançamentos. Se o OCR não leu o nome de algum setor com clareza, você pode corrigir digitando na tabela abaixo.")
        
        df_editado = st.data_editor(
            df_bruto,
            column_config={
                "Setor": st.column_config.TextColumn("Local de Trabalho (Edite se necessário)"),
                "Valor (R$)": st.column_config.NumberColumn(format="R$ %.2f", disabled=True),
                "Código": st.column_config.TextColumn(disabled=True),
                "Rubrica": st.column_config.TextColumn(disabled=True),
                "Tipo": st.column_config.TextColumn(disabled=True),
                "Mês/Ano": st.column_config.TextColumn(disabled=True),
                "Arquivo": st.column_config.TextColumn(disabled=True)
            },
            hide_index=True,
            use_container_width=True
        )

        st.divider()

        st.subheader("2. 📋 Tabela Consolidada por Setor (Colunas Separadas)")
        df_pivot = df_editado.pivot_table(
            index=['Mês/Ano', 'Setor'], 
            columns='Rubrica', 
            values='Valor (R$)', 
            aggfunc='sum'
        ).fillna(0).reset_index()

        colunas_he = [c for c in df_pivot.columns if 'HE' in c or 'Carga' in c]
        colunas_grat = [c for c in df_pivot.columns if 'Gratific' in c or 'SAMU' in c]

        df_pivot['TOTAL HORAS EXTRAS'] = df_pivot[colunas_he].sum(axis=1) if colunas_he else 0
        df_pivot['TOTAL GRATIFICAÇÕES'] = df_pivot[colunas_grat].sum(axis=1) if colunas_grat else 0
        df_pivot['TOTAL GERAL'] = df_pivot['TOTAL HORAS EXTRAS'] + df_pivot['TOTAL GRATIFICAÇÕES']

        formato_moeda = {col: "R$ {:.2f}" for col in df_pivot.columns if col not in ['Mês/Ano', 'Setor']}
        st.dataframe(df_pivot.style.format(formato_moeda), use_container_width=True, hide_index=True)

        st.divider()

        st.subheader("3. 📊 Dashboards Evolutivos")
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("#### Evolução de Horas Extras")
            df_graf_he = df_pivot.groupby('Mês/Ano')['TOTAL HORAS EXTRAS'].sum().reset_index()
            fig_he = px.bar(df_graf_he, x='Mês/Ano', y='TOTAL HORAS EXTRAS', text_auto='.2s', color_discrete_sequence=['#1f77b4'])
            st.plotly_chart(fig_he, use_container_width=True)

        with col2:
            st.markdown("#### Evolução de Gratificações")
            df_graf_grat = df_pivot.groupby('Mês/Ano')['TOTAL GRATIFICAÇÕES'].sum().reset_index()
            fig_grat = px.bar(df_graf_grat, x='Mês/Ano', y='TOTAL GRATIFICAÇÕES', text_auto='.2s', color_discrete_sequence=['#ff7f0e'])
            st.plotly_chart(fig_grat, use_container_width=True)

        with st.expander("🕵️ Veja o Log do Leitor de OCR"):
            for log in logs:
                st.text(log)

    else:
        st.warning("O OCR não conseguiu localizar os códigos (006, 011, 018, 031, 089, 812) nestes PDFs.")
