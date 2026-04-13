import streamlit as st
import pandas as pd
import plotly.express as px
import pdfplumber
import re

st.set_page_config(page_title="Dashboard Setorial", layout="wide")
st.title("Controle Setorial - Horas Extras e Gratificações")
st.markdown("Faça o upload dos **Resumos Contábeis em PDF** da Fiorilli.")

def limpar_valor(valor_str):
    # Pega apenas os números e transforma os últimos dois em centavos
    digitos = re.sub(r'\D', '', valor_str)
    if digitos:
        return float(digitos) / 100.0
    return 0.0

def extrair_linhas_visuais(pagina):
    """
    O Raio-X: Lê as coordenadas exatas das palavras no PDF e as costura 
    na mesma linha se estiverem na mesma altura, burlando as colunas invisíveis.
    """
    palavras = pagina.extract_words()
    linhas_dict = {}
    
    for p in palavras:
        y = round(p['top'])
        encaixou = False
        # Junta palavras que estejam na mesma linha (com tolerância de 4 pixels)
        for y_linha in linhas_dict.keys():
            if abs(y - y_linha) <= 4:
                linhas_dict[y_linha].append(p)
                encaixou = True
                break
        if not encaixou:
            linhas_dict[y] = [p]
            
    linhas_texto = []
    # Ordena de cima pra baixo, e depois da esquerda pra direita
    for y in sorted(linhas_dict.keys()):
        palavras_linha = sorted(linhas_dict[y], key=lambda x: x['x0'])
        texto_linha = " ".join([p['text'] for p in palavras_linha])
        linhas_texto.append(texto_linha)
        
    return linhas_texto

@st.cache_data
def processar_pdf(arquivos):
    dados_setores = {}
    log_extracao = []

    for arquivo in arquivos:
        with pdfplumber.open(arquivo) as pdf:
            mes_atual = "Indefinido"
            setor_atual = None

            for num_pagina, pagina in enumerate(pdf.pages):
                # Usa o Raio-X em vez da extração de texto padrão
                linhas_reais = extrair_linhas_visuais(pagina)
                
                for linha in linhas_reais:
                    linha_lower = linha.lower()
                    
                    # 1. Puxa Mês/Ano
                    if "mês/ano" in linha_lower:
                        match = re.search(r"(\d{2}/\d{4})", linha)
                        if match: mes_atual = match.group(1)
                        
                    # 2. Puxa o Setor isolado
                    if "local de trabalho:" in linha_lower:
                        partes = linha_lower.split("local de trabalho:")
                        setor_bruto = partes[1].strip()
                        # Limpa qualquer lixo que tenha caído na mesma linha
                        setor_bruto = re.split(r'mês/ano|folha|página|total', setor_bruto)[0].strip()
                        if "-" in setor_bruto:
                            setor_atual = setor_bruto.split("-", 1)[1].strip().title()
                        else:
                            setor_atual = setor_bruto.title()
                            
                        # Cria a gaveta para o setor
                        if setor_atual:
                            chave = f"{setor_atual}_{mes_atual}"
                            if chave not in dados_setores:
                                dados_setores[chave] = {
                                    'Mês/Ano': mes_atual,
                                    'Setor': setor_atual,
                                    'Horas Extras (R$)': 0.0,
                                    'Gratificações (R$)': 0.0
                                }

                    # Ignora a página se não souber o setor
                    if not setor_atual:
                        continue
                        
                    chave = f"{setor_atual}_{mes_atual}"
                    
                    # 3. Caça Dinheiro e Palavras-chave na Mesma Linha Visível
                    # Pega qualquer formato (1.234,56 ou 1234,56) isolado na frase
                    numeros_moeda = re.findall(r'(?<!\d)\d{1,3}(?:[\.\,]\d{3})*[\.\,]\d{2}(?!\d)', linha)
                    
                    if numeros_moeda:
                        ultimo_valor = limpar_valor(numeros_moeda[-1])
                        
                        # Testa Horas Extras e Complemento
                        if any(kw in linha_lower for kw in ['hora extra', 'horas extras', 'comp.carga horária', 'comp. carga horária']):
                            if ultimo_valor > dados_setores[chave]['Horas Extras (R$)']:
                                dados_setores[chave]['Horas Extras (R$)'] = ultimo_valor
                                log_extracao.append(f"✅ Pág {num_pagina+1} | {setor_atual}: HE -> R$ {ultimo_valor:.2f} (Linha: {linha[:80]})")
                                
                        # Testa Gratificações e SAMU
                        if any(kw in linha_lower for kw in ['gratific', 'gratifica', 'samu']):
                            if ultimo_valor > dados_setores[chave]['Gratificações (R$)']:
                                dados_setores[chave]['Gratificações (R$)'] = ultimo_valor
                                log_extracao.append(f"✅ Pág {num_pagina+1} | {setor_atual}: Gratificação -> R$ {ultimo_valor:.2f} (Linha: {linha[:80]})")

    if not dados_setores:
        return pd.DataFrame(), log_extracao

    df = pd.DataFrame(list(dados_setores.values()))
    df['Total Geral (R$)'] = df['Horas Extras (R$)'] + df['Gratificações (R$)']
    
    # Remove as linhas vazias do painel
    df = df[df['Total Geral (R$)'] > 0]
    return df.sort_values(by='Mês/Ano'), log_extracao

# --- INTERFACE DO APLICATIVO ---
arquivos_upload = st.file_uploader("Upload dos Resumos Contábeis (PDF)", type=["pdf"], accept_multiple_files=True)

if arquivos_upload:
    with st.spinner('Mapeando as coordenadas das palavras no PDF...'):
        df, logs = processar_pdf(arquivos_upload)
        
    with st.expander("🛠️ Log do Raio-X (Confira as linhas perfeitas que o sistema montou)"):
        if logs:
            for log in logs:
                st.text(log)
        else:
            st.text("Nenhuma palavra-chave financeira foi detectada nas linhas montadas.")
            
    if not df.empty:
        st.success("Dados lidos e decodificados com sucesso!")
        
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
