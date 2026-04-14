import streamlit as st
import pandas as pd
import plotly.express as px
import pdfplumber
import re

st.set_page_config(page_title="Dashboard Setorial", layout="wide")
st.title("Controle Setorial - Horas Extras e Gratificações")
st.markdown("Faça o upload dos **Resumos Contábeis em PDF** da Fiorilli.")

def limpar_valor(valor_str):
    # Converte para número real (moeda)
    digitos = re.sub(r'\D', '', str(valor_str))
    if digitos:
        return float(digitos) / 100.0
    return 0.0

@st.cache_data
def processar_pdf(arquivos):
    dados_gerais = []
    log_extracao = []

    for arquivo in arquivos:
        with pdfplumber.open(arquivo) as pdf:
            mes_atual = "Indefinido"
            
            # A Memória do Setor (Não reseta a cada página)
            setor_memoria = "Não Identificado"

            for num_pagina, pagina in enumerate(pdf.pages):
                
                # --- PASSO 1: A CAÇA INFALÍVEL AO SETOR E MÊS (Leitura Palavra por Palavra) ---
                palavras = pagina.extract_words()
                
                for i, p in enumerate(palavras):
                    txt_lower = p['text'].lower()
                    
                    # Salva o Mês/Ano
                    if txt_lower == "mês/ano" and i + 1 < len(palavras):
                        prox_texto = palavras[i+1]['text']
                        if re.match(r"\d{2}/\d{4}", prox_texto):
                            mes_atual = prox_texto

                    # Salva o Setor (Acha as 3 palavras exatas e suga o que vem depois)
                    if txt_lower == "trabalho:" and i >= 2:
                        if palavras[i-1]['text'].lower() == "de" and palavras[i-2]['text'].lower() == "local":
                            setor_words = []
                            # Pega as palavras à frente até bater em uma palavra de cabeçalho
                            for j in range(i+1, min(i+20, len(palavras))):
                                word = palavras[j]['text']
                                if word.lower() in ["mês/ano", "folha", "página", "resumo", "total", "matrícula", "nome"]:
                                    break
                                setor_words.append(word)
                            
                            candidato = " ".join(setor_words).strip()
                            # Tira o código da frente
                            if "-" in candidato:
                                candidato = candidato.split("-", 1)[-1].strip()
                            
                            # Atualiza a memória apenas se achou um nome válido
                            if candidato and len(candidato) > 2:
                                setor_memoria = candidato.title()

                # --- PASSO 2: A CAÇA FINANCEIRA COM ISOLAMENTO DE COLUNAS ---
                texto_layout = pagina.extract_text(layout=True)
                if not texto_layout: continue
                
                # Deleta os códigos da Fiorilli (ex: 3.1.90.16) para o sistema não achar que é dinheiro
                texto_limpo = re.sub(r'\(\d{1,2}\.\d{1,2}\.\d{2,4}\.\d{2}\)', '', texto_layout)
                
                # O PULO DO GATO: Se houver 2 ou mais espaços, ele "quebra" a linha separando as colunas. 
                # Adeus mistura de FGTS com Hora Extra!
                blocos = re.split(r'\s{2,}|\n', texto_limpo)
                
                he_max = 0.0
                grat_max = 0.0

                for i, bloco in enumerate(blocos):
                    bloco_lower = bloco.lower()
                    
                    tem_he = any(kw in bloco_lower for kw in ['hora extra', 'horas extras', 'comp.carga', 'comp. carga'])
                    tem_grat = any(kw in bloco_lower for kw in ['gratific', 'samu'])
                    
                    if tem_he or tem_grat:
                        valor_encontrado = 0.0
                        
                        # 1º Tenta achar o dinheiro no próprio bloco
                        numeros_bloco = re.findall(r'(?<!\d)\d{1,3}(?:[\.\,]\d{3})*[\.\,]\d{2}(?!\d)', bloco)
                        
                        if numeros_bloco:
                            valor_encontrado = limpar_valor(numeros_bloco[-1])
                        else:
                            # 2º Se não tiver, o dinheiro está isolado no bloco da frente (coluna seguinte)
                            if i + 1 < len(blocos):
                                numeros_prox = re.findall(r'(?<!\d)\d{1,3}(?:[\.\,]\d{3})*[\.\,]\d{2}(?!\d)', blocos[i+1])
                                if numeros_prox:
                                    valor_encontrado = limpar_valor(numeros_prox[-1])
                                    
                        # Valida os maiores valores da página
                        if tem_he and valor_encontrado > he_max:
                            he_max = valor_encontrado
                            log_extracao.append(f"Pág {num_pagina+1} | {setor_memoria} | HE: R$ {he_max:.2f}")
                            
                        if tem_grat and valor_encontrado > grat_max:
                            grat_max = valor_encontrado
                            log_extracao.append(f"Pág {num_pagina+1} | {setor_memoria} | Gratificações: R$ {grat_max:.2f}")

                # Vincula os valores ao Setor que está na memória
                if he_max > 0 or grat_max > 0:
                    dados_gerais.append({
                        'Mês/Ano': mes_atual,
                        'Setor': setor_memoria,
                        'Horas Extras (R$)': he_max,
                        'Gratificações (R$)': grat_max
                    })

    if not dados_gerais:
        return pd.DataFrame(), log_extracao

    df = pd.DataFrame(dados_gerais)
    
    # Agrupa pelo Mês e Setor para não duplicar, pegando o Total máximo
    df_agrupado = df.groupby(['Mês/Ano', 'Setor'], as_index=False).max()
    df_agrupado['Total Geral (R$)'] = df_agrupado['Horas Extras (R$)'] + df_agrupado['Gratificações (R$)']
    
    return df_agrupado.sort_values(by='Mês/Ano'), log_extracao

# --- INTERFACE DO APLICATIVO ---
arquivos_upload = st.file_uploader("Upload dos Resumos Contábeis (PDF)", type=["pdf"], accept_multiple_files=True)

if arquivos_upload:
    with st.spinner('A extrair dados com fatiamento de colunas...'):
        df, logs = processar_pdf(arquivos_upload)
        
    with st.expander("🛠️ Log do Corte a Laser (Verifique se sumiu o FGTS e voltou o Setor)"):
        if logs:
            for log in logs:
                st.text(log)
        else:
            st.text("Nenhum valor localizado.")
            
    if not df.empty:
        st.success("Tabelas decodificadas com perfeição!")
        
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
    st.info("A aguardar o envio dos ficheiros PDF.")
