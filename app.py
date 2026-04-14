import streamlit as st
import pandas as pd
import plotly.express as px
import pdfplumber
import re

st.set_page_config(page_title="Dashboard Setorial", layout="wide")
st.title("Controle de Horas Extras e Gratificações")
st.markdown("O sistema extrai as rubricas detalhadas. Como o PDF bloqueia a leitura dos setores, **digite o nome do Local de Trabalho diretamente na tabela abaixo** para gerar os gráficos.")

def limpar_valor(valor_str):
    digitos = re.sub(r'\D', '', str(valor_str))
    if digitos:
        return float(digitos) / 100.0
    return 0.0

@st.cache_data
def processar_pdf(arquivos):
    dados_paginas = []
    log_extracao = []

    # Os caçadores cirúrgicos: Procuram o Código + Palavra Chave na mesma linha
    padroes_he = [
        r'\b006\b.*horas?\s*extras?', 
        r'\b011\b.*hora\s*extra', 
        r'\b018\b.*horas?\s*extras?', 
        r'\b089\b.*comp\.?\s*carga'
    ]
    padroes_grat = [
        r'\b031\b.*gratific', 
        r'\b812\b.*gratifica[cç][aã]o'
    ]

    for arquivo in arquivos:
        with pdfplumber.open(arquivo) as pdf:
            for num_pagina, pagina in enumerate(pdf.pages):
                texto = pagina.extract_text(layout=True)
                if not texto: continue
                
                # Busca o Mês/Ano da folha
                mes_atual = "Indefinido"
                match_mes = re.search(r"mês/ano\s*(\d{2}/\d{4})", texto, re.IGNORECASE)
                if match_mes: mes_atual = match_mes.group(1)

                linhas = texto.split('\n')
                he_pag = 0.0
                grat_pag = 0.0

                for linha in linhas:
                    linha_clean = linha.lower()
                    
                    tem_he = any(re.search(p, linha_clean) for p in padroes_he)
                    tem_grat = any(re.search(p, linha_clean) for p in padroes_grat)

                    if tem_he or tem_grat:
                        # Extrai qualquer número financeiro
                        numeros = re.findall(r'(?<!\d)\d{1,3}(?:[\.\,]\d{3})*[\.\,]\d{2}(?!\d)', linha)
                        
                        if numeros:
                            # Na lista detalhada, o valor é sempre o último número formatado antes da classificação contábil
                            valor = limpar_valor(numeros[-1])
                            
                            if tem_he:
                                he_pag += valor  # Soma todos os funcionários da página
                                log_extracao.append(f"Pág {num_pagina+1} | Rubrica HE Encontrada | + R$ {valor:.2f}")
                                
                            if tem_grat:
                                grat_pag += valor # Soma todos os funcionários da página
                                log_extracao.append(f"Pág {num_pagina+1} | Rubrica GRAT Encontrada | + R$ {valor:.2f}")

                # Se achou dinheiro daquelas rubricas na página, cria uma linha na tabela
                if he_pag > 0 or grat_pag > 0:
                    dados_paginas.append({
                        'Arquivo': arquivo.name,
                        'Mês/Ano': mes_atual,
                        'Página': f"Pág {num_pagina+1}",
                        'Setor': "Pendente (Clique para digitar)", # O usuário vai editar isso na tela
                        'Horas Extras (R$)': he_pag,
                        'Gratificações (R$)': grat_pag
                    })

    if not dados_paginas:
        return pd.DataFrame(), log_extracao

    return pd.DataFrame(dados_paginas), log_extracao

# --- INTERFACE DO APLICATIVO ---
arquivos_upload = st.file_uploader("Upload dos Resumos Contábeis (PDF)", type=["pdf"], accept_multiple_files=True)

if arquivos_upload:
    with st.spinner('A caçar rubricas detalhadas (006, 011, 018, 031, 089, 812)...'):
        df_bruto, logs = processar_pdf(arquivos_upload)
        
    with st.expander("🛠️ Log de Extração (Verifique a soma das rubricas por página)"):
        if logs:
            for log in logs:
                st.text(log)
        else:
            st.text("Nenhuma das rubricas específicas foi encontrada.")
            
    if not df_bruto.empty:
        st.success("Rubricas financeiras extraídas com sucesso!")
        
        st.subheader("1. ✍️ Identificação dos Setores (Tabela Editável)")
        st.info("💡 **DICA:** Clique na coluna 'Setor' abaixo e digite o nome do departamento correspondente àquela página. Os gráficos abaixo serão atualizados automaticamente!")
        
        # Cria a tabela interativa onde o Valdir pode digitar os nomes
        df_editado = st.data_editor(
            df_bruto,
            column_config={
                "Setor": st.column_config.TextColumn("Local de Trabalho (Edite aqui)", required=True),
                "Horas Extras (R$)": st.column_config.NumberColumn(format="R$ %.2f", disabled=True),
                "Gratificações (R$)": st.column_config.NumberColumn(format="R$ %.2f", disabled=True),
                "Arquivo": st.column_config.TextColumn(disabled=True),
                "Mês/Ano": st.column_config.TextColumn(disabled=True),
                "Página": st.column_config.TextColumn(disabled=True)
            },
            hide_index=True,
            use_container_width=True
        )

        # Agrupa os valores pelo nome que o usuário digitou
        df_agrupado = df_editado.groupby(['Mês/Ano', 'Setor'], as_index=False)[['Horas Extras (R$)', 'Gratificações (R$)']].sum()
        df_agrupado['Total Geral (R$)'] = df_agrupado['Horas Extras (R$)'] + df_agrupado['Gratificações (R$)']
        
        st.divider()
        st.subheader("2. 📊 Gráficos e Dashboards")
        
        st.sidebar.header("Filtros Setoriais")
        lista_setores = df_agrupado['Setor'].unique().tolist()
        lista_setores.sort()
        # Se houver setores pendentes, coloca no topo para chamar atenção
        if "Pendente (Clique para digitar)" in lista_setores:
            lista_setores.remove("Pendente (Clique para digitar)")
            lista_setores.insert(0, "Pendente (Clique para digitar)")
            
        lista_setores.insert(0, "Visão Geral (Todos os Setores)")
        setor_selecionado = st.sidebar.selectbox("Escolha o Local de Trabalho", lista_setores)
        
        if setor_selecionado == "Visão Geral (Todos os Setores)":
            df_grafico = df_agrupado.groupby('Mês/Ano')[['Horas Extras (R$)', 'Gratificações (R$)']].sum().reset_index()
            fig = px.bar(
                df_grafico, 
                x='Mês/Ano', 
                y=['Horas Extras (R$)', 'Gratificações (R$)'],
                barmode='group'
            )
            st.plotly_chart(fig, use_container_width=True)
            df_tabela = df_agrupado
        else:
            df_setor = df_agrupado[df_agrupado['Setor'] == setor_selecionado]
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
        st.warning("Não localizamos nenhum valor para as rubricas 006, 011, 018, 031, 089 ou 812 nos PDFs enviados.")
else:
    st.info("A aguardar o envio dos ficheiros PDF.")
