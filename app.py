import streamlit as st
import pandas as pd
import plotly.express as px
import pdfplumber
import re

st.set_page_config(page_title="Dashboard Setorial", layout="wide")
st.title("Controle Setorial - Horas Extras e Gratificações")
st.markdown("Faça o upload dos **Resumos Contábeis em PDF** da Fiorilli.")

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
            mes_atual = "Indefinido"
            setor_atual = None

            for num_pagina, pagina in enumerate(pdf.pages):
                texto = pagina.extract_text()
                if not texto: continue

                # A MÁGICA: Remove todas as quebras de linha e junta tudo numa frase só (Tudo minúsculo para facilitar)
                texto_limpo = re.sub(r'\s+', ' ', texto).lower()

                # 1. Busca o Mês
                match_mes = re.search(r"mês/ano\s*(\d{2}/\d{4})", texto_limpo)
                if match_mes:
                    mes_atual = match_mes.group(1)

                # 2. Busca o Setor (Lê o que está entre 'Local de Trabalho:' e a próxima palavra chave do relatório)
                match_setor = re.search(r"local de trabalho:\s*(?:\d+\s*-\s*)?([a-zà-ÿ0-9\s\.\-\"\']+?)\s+(?:mês/ano|folha|resumo|total)", texto_limpo)
                if match_setor:
                    setor_atual = match_setor.group(1).strip().title()

                if not setor_atual:
                    continue

                chave = f"{setor_atual}_{mes_atual}"
                if chave not in dados_setores:
                    dados_setores[chave] = {
                        'Mês/Ano': mes_atual,
                        'Setor': setor_atual,
                        'Horas Extras (R$)': 0.0,
                        'Gratificações (R$)': 0.0
                    }

                # 3. Foca apenas no quadro de Resumo de Proventos para evitar linhas duplicadas de funcionários
                match_resumo = re.search(r'resumo de proventos(.*?)(?:descontos|resumo de descontos|base de i\.r\.r\.f|$)', texto_limpo)
                bloco_alvo = match_resumo.group(1) if match_resumo else texto_limpo

                # 4. Função Caçadora Absoluta
                def cacar_valor(palavras, bloco):
                    maior = 0.0
                    for kw in palavras:
                        for match in re.finditer(re.escape(kw), bloco):
                            # Pega os próximos 80 caracteres após a palavra encontrada
                            trecho = bloco[match.end() : match.end() + 80]
                            
                            # Para de ler assim que encontrar a primeira letra da PRÓXIMA rubrica (ex: 'Insalubridade')
                            match_letra = re.search(r'[a-zà-ÿ]', trecho)
                            if match_letra:
                                trecho = trecho[:match_letra.start()]
                                
                            # Puxa o último valor financeiro que ficou isolado no trecho
                            numeros = re.findall(r'(?<!\d)\d{1,3}(?:[\.\,]\d{3})*[\.\,]\d{2}(?!\d)', trecho)
                            if numeros:
                                val = limpar_valor(numeros[-1])
                                if val > maior: maior = val
                    return maior

                # Caça os valores usando todas as variações de palavras da prefeitura
                he = cacar_valor(['hora extra', 'horas extras', 'comp.carga horária', 'comp. carga horária'], bloco_alvo)
                grat = cacar_valor(['gratific', 'gratifica', 'samu'], bloco_alvo)

                # Salva se encontrou algo
                if he > dados_setores[chave]['Horas Extras (R$)']:
                    dados_setores[chave]['Horas Extras (R$)'] = he
                    log_extracao.append(f"✅ Pág {num_pagina+1} | {setor_atual}: Achou HE -> R$ {he}")

                if grat > dados_setores[chave]['Gratificações (R$)']:
                    dados_setores[chave]['Gratificações (R$)'] = grat
                    log_extracao.append(f"✅ Pág {num_pagina+1} | {setor_atual}: Achou Gratificação -> R$ {grat}")

    if not dados_setores:
        return pd.DataFrame(), log_extracao

    df = pd.DataFrame(list(dados_setores.values()))
    df['Total Geral (R$)'] = df['Horas Extras (R$)'] + df['Gratificações (R$)']
    
    # Limpa da tela os setores que não tiveram nem Hora Extra nem Gratificação
    df = df[df['Total Geral (R$)'] > 0]
    
    return df.sort_values(by='Mês/Ano'), log_extracao

# --- INTERFACE DO APLICATIVO ---
arquivos_upload = st.file_uploader("Upload dos Resumos Contábeis (PDF)", type=["pdf"], accept_multiple_files=True)

if arquivos_upload:
    with st.spinner('Esmagando a formatação do PDF e extraindo valores...'):
        df, logs = processar_pdf(arquivos_upload)
        
    with st.expander("🛠️ Log de Extração (Clique para ver as capturas da IA)"):
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
