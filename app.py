import streamlit as st
import pandas as pd
import plotly.express as px
import pdfplumber
import re

st.set_page_config(page_title="Auditoria de Folha - Jaborandi", layout="wide")
st.title("🏦 Sistema Definitivo de Auditoria (Rubricas Exatas)")
st.markdown("Faça o upload do **PDF** do Resumo Contábil. Se o PDF estiver bloqueado (vetorizado), você pode subir diretamente o arquivo de texto (**TXT** ou **CSV**) extraído pelo seu OCR.")

# Dicionário exato com os códigos que você solicitou
RUBRICAS = {
    '006': {'nome': '006 - HE 50%', 'tipo': 'Hora Extra'},
    '011': {'nome': '011 - HE 100%', 'tipo': 'Hora Extra'},
    '018': {'nome': '018 - HE Mês Ant.', 'tipo': 'Hora Extra'},
    '031': {'nome': '031 - Gratific. Lei', 'tipo': 'Gratificação'},
    '089': {'nome': '089 - Comp. Carga', 'tipo': 'Hora Extra'},
    '812': {'nome': '812 - Gratificação SAMU', 'tipo': 'Gratificação'}
}

def limpar_valor(valor_str):
    # Limpa a formatação de dinheiro mantendo os centavos
    digitos = re.sub(r'\D', '', str(valor_str))
    return float(digitos) / 100.0 if digitos else 0.0

@st.cache_data
def processar_arquivos(arquivos):
    registros = []
    log_extracao = []

    for arquivo in arquivos:
        texto_completo = ""

        # 1. Tenta ler o arquivo (Suporta PDF ou TXT/CSV do seu OCR)
        if arquivo.name.lower().endswith('.pdf'):
            with pdfplumber.open(arquivo) as pdf:
                for pagina in pdf.pages:
                    # extract_text normal (sem layout) imita exatamente o OCR que você fez!
                    t = pagina.extract_text() 
                    if t: texto_completo += t + "\n"
        else:
            texto_completo = arquivo.getvalue().decode('utf-8', errors='ignore')

        linhas = texto_completo.split('\n')
        
        mes_atual = "Indefinido"
        setor_atual = "Não Identificado"

        # 2. O Leitor em Fluxo Contínuo (Imune à quebra de páginas)
        for i, linha in enumerate(linhas):
            linha_limpa = linha.strip()

            # Captura o Mês/Ano
            if "Mês/Ano" in linha_limpa:
                match = re.search(r"(\d{2}/\d{4})", linha_limpa)
                if match: 
                    mes_atual = match.group(1)
                elif i + 1 < len(linhas):
                    match2 = re.search(r"(\d{2}/\d{4})", linhas[i+1])
                    if match2: mes_atual = match2.group(1)

            # Captura o Setor (Lê o texto sujo e extrai só o nome)
            if "Local de Trabalho:" in linha_limpa:
                parte = linha_limpa.split("Local de Trabalho:")[1].strip()
                if not parte and i + 1 < len(linhas):
                    parte = linhas[i+1].strip()

                if parte:
                    # Remove aspas do OCR e limpa os códigos
                    parte = re.sub(r'["\',]', '', parte).strip()
                    if "-" in parte:
                        setor_atual = parte.split("-", 1)[1].strip().title()
                    else:
                        setor_atual = parte.title()

            # 3. A Caça às Rubricas Exatas
            # Procura linhas que comecem com "006", "011", etc (aceitando aspas do OCR)
            match_rubrica = re.search(r'^"?\s*(006|011|018|031|089|812)\b', linha_limpa)
            
            if match_rubrica:
                codigo = match_rubrica.group(1)

                # Busca qualquer número com formato financeiro na linha
                numeros = re.findall(r'(?<!\d)\d{1,3}(?:[\.\,]\d{3})*[\.\,]\d{2}(?!\d)', linha_limpa)

                # Se o OCR separou o valor na linha de baixo, ele procura no bloco
                if not numeros:
                    bloco = ""
                    for j in range(1, 4):
                        if i+j < len(linhas):
                            bloco += " " + linhas[i+j]
                    numeros = re.findall(r'(?<!\d)\d{1,3}(?:[\.\,]\d{3})*[\.\,]\d{2}(?!\d)', bloco)

                if numeros:
                    # Pega o último número financeiro (que é sempre o Valor Pago total do setor)
                    valor = limpar_valor(numeros[-1])
                    
                    if valor > 0:
                        registros.append({
                            'Arquivo': arquivo.name,
                            'Mês/Ano': mes_atual,
                            'Setor': setor_atual,
                            'Código': codigo,
                            'Rubrica': RUBRICAS[codigo]['nome'],
                            'Tipo': RUBRICAS[codigo]['tipo'],
                            'Valor (R$)': valor
                        })
                        log_extracao.append(f"✅ {mes_atual} | {setor_atual} | {RUBRICAS[codigo]['nome']}: R$ {valor:.2f}")

    if not registros:
        return pd.DataFrame(), log_extracao

    df = pd.DataFrame(registros)
    
    # Agrupa pegando o valor Máximo para garantir que é o resumo total do setor, não uma quebra dupla
    df_db = df.groupby(['Arquivo', 'Mês/Ano', 'Setor', 'Código', 'Rubrica', 'Tipo'], as_index=False)['Valor (R$)'].max()
    return df_db, log_extracao


# --- INTERFACE DO SISTEMA ---
arquivos_upload = st.file_uploader("Upload dos Resumos (PDF, TXT ou CSV do OCR)", type=["pdf", "txt", "csv"], accept_multiple_files=True)

if arquivos_upload:
    with st.spinner('Decodificando as rubricas detalhadas através do fluxo lógico...'):
        df_bruto, logs = processar_arquivos(arquivos_upload)

    if not df_bruto.empty:
        st.success("Rubricas financeiras extraídas com sucesso!")
        
        # 1. BANCO DE DADOS EDITÁVEL
        st.subheader("1. 🛠️ Banco de Dados e Mapeamento de Setores")
        st.info("Aqui estão os lançamentos brutos. Se algum setor vier do PDF como 'Não Identificado', dê dois cliques na célula e digite o nome correto para arrumar o banco de dados!")
        
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

        # 2. TABELA DE CONSOLIDAÇÃO PERFEITA (O que você pediu)
        st.subheader("2. 📋 Tabela Consolidada por Setor (Colunas Separadas)")
        
        # Faz o "Pivot": Transforma as rubricas em colunas (006, 011, etc ficam lado a lado)
        df_pivot = df_editado.pivot_table(
            index=['Mês/Ano', 'Setor'], 
            columns='Rubrica', 
            values='Valor (R$)', 
            aggfunc='sum'
        ).fillna(0).reset_index()

        # Encontra dinamicamente quais rubricas existem para somar os grandes grupos
        colunas_he = [c for c in df_pivot.columns if 'HE' in c or 'Carga' in c]
        colunas_grat = [c for c in df_pivot.columns if 'Gratific' in c or 'SAMU' in c]

        # Cria as colunas finais de soma
        df_pivot['TOTAL HORAS EXTRAS'] = df_pivot[colunas_he].sum(axis=1) if colunas_he else 0
        df_pivot['TOTAL GRATIFICAÇÕES'] = df_pivot[colunas_grat].sum(axis=1) if colunas_grat else 0
        df_pivot['TOTAL GERAL'] = df_pivot['TOTAL HORAS EXTRAS'] + df_pivot['TOTAL GRATIFICAÇÕES']

        # Exibe a tabela linda com formatação de moeda
        formato_moeda = {col: "R$ {:.2f}" for col in df_pivot.columns if col not in ['Mês/Ano', 'Setor']}
        st.dataframe(df_pivot.style.format(formato_moeda), use_container_width=True, hide_index=True)

        st.divider()

        # 3. DASHBOARDS
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
        st.warning("Não localizamos nenhum valor para as rubricas 006, 011, 018, 031, 089 ou 812 nestes arquivos.")
else:
    st.info("Aguardando o envio do PDF ou do arquivo de Texto gerado pelo seu OCR.")
