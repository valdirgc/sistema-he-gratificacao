import streamlit as st
import pandas as pd
import plotly.express as px
import pdfplumber
import re

# 1. Configuração Inicial da Página
st.set_page_config(page_title="Controle de HE e Gratificação", layout="wide")
st.title("Controle de Horas Extras e Gratificações")

# 2. Função Robusta de Extração de Dados do PDF
@st.cache_data # Faz o sistema não precisar re-ler o PDF se você só mudar um filtro
def extrair_dados_folha(arquivo_pdf):
    dados = []
    
    # Regex para valores financeiros (busca o padrão 1.234,56 ou 1234,56 em qualquer lugar do texto)
    re_hora_extra = re.compile(r"Horas Extras\s*\(3\.1\.90\.16\).*?([\d\.]*,\d+)", re.IGNORECASE | re.DOTALL)
    re_gratificacao = re.compile(r"Gratific\s+Lei\s+2291/2021.*?([\d\.]*,\d+)", re.IGNORECASE | re.DOTALL)
    re_samu = re.compile(r"Gratificação\s+SAMU.*?([\d\.]*,\d+)", re.IGNORECASE | re.DOTALL)
    
    mes_atual = "Indefinido"
    
    with pdfplumber.open(arquivo_pdf) as pdf:
        for pagina in pdf.pages:
            texto = pagina.extract_text()
            if not texto:
                continue
            
            linhas = texto.split('\n')
            setor_atual = "Não Identificado"
            nome_atual = "Não Identificado"
            
            # Varredura linha por linha para fugir dos problemas de quebra de texto
            for i, linha in enumerate(linhas):
                # Captura o Mês/Ano
                if "Mês/Ano" in linha and i + 1 < len(linhas):
                    # Tenta pegar na mesma linha ou na próxima
                    match_mes = re.search(r"(\d{2}/\d{4})", linha + " " + linhas[i+1])
                    if match_mes:
                        mes_atual = match_mes.group(1)

                # Captura o Setor (Local de Trabalho)
                if "Local de Trabalho:" in linha:
                    parte_setor = linha.replace("Local de Trabalho:", "").strip()
                    if parte_setor:
                        setor_atual = parte_setor
                    elif i + 1 < len(linhas): # Se estiver vazio na linha, pega a próxima
                        setor_atual = linhas[i+1].strip()
                        
                    # Limpa os códigos numéricos da frente (ex: "001002 - Saúde" vira "Saúde")
                    if "-" in setor_atual:
                        setor_atual = setor_atual.split("-", 1)[-1].strip()

                # Captura o Nome do Funcionário (geralmente fica 2 linhas abaixo de "Desligamento")
                if "Desligamento" in linha:
                    if i + 2 < len(linhas):
                        possivel_nome = linhas[i+2].strip()
                        # Verifica se não é um número (como a matrícula)
                        if not possivel_nome.replace('.','').replace('-','').isdigit():
                            nome_atual = possivel_nome
                        elif i + 3 < len(linhas): # Se for a matrícula, o nome tá na próxima
                            nome_atual = linhas[i+3].strip()

            # Captura de Valores Financeiros usando o texto completo da página
            match_he = re_hora_extra.search(texto)
            valor_he = match_he.group(1).replace('.', '').replace(',', '.') if match_he else "0.00"
            
            match_grat = re_gratificacao.search(texto)
            valor_grat = match_grat.group(1).replace('.', '').replace(',', '.') if match_grat else "0.00"
            
            match_samu = re_samu.search(texto)
            valor_samu = match_samu.group(1).replace('.', '').replace(',', '.') if match_samu else "0.00"
            
            total_gratificacao = float(valor_grat) + float(valor_samu)
            
            # Só adiciona na base se a página pertencer a um funcionário com HE ou Gratificação
            if float(valor_he) > 0 or total_gratificacao > 0:
                dados.append({
                    'Mês/Ano': mes_atual,
                    'Setor': setor_atual,
                    'Funcionário': nome_atual,
                    'Hora Extra (R$)': float(valor_he),
                    'Gratificação (R$)': total_gratificacao
                })

    # Cria o DataFrame. Se não achar nada, cria as colunas vazias para não dar erro
    if not dados:
        return pd.DataFrame(columns=['Mês/Ano', 'Setor', 'Funcionário', 'Hora Extra (R$)', 'Gratificação (R$)'])
        
    return pd.DataFrame(dados)

# 3. Interface do Usuário (Upload e Dashboard)
arquivo_upload = st.file_uploader("Faça o upload do Resumo Contábil (PDF)", type=["pdf"])

if arquivo_upload is not None:
    with st.spinner('Analisando o documento e montando a base de dados...'):
        df = extrair_dados_folha(arquivo_upload)
    
    # MODO DEPURAÇÃO: Mostra a tabela de extração para conferência
    with st.expander("🔍 Ver Tabela de Dados Extraída (Clique para abrir)"):
        st.write("Verifique se as colunas 'Setor' e 'Funcionário' estão preenchidas corretamente:")
        st.dataframe(df)

    # Verifica se o DataFrame tem dados reais antes de montar os filtros
    if not df.empty and 'Setor' in df.columns:
        st.success("Dados carregados com sucesso!")
        
        # Filtros na Barra Lateral
        st.sidebar.header("Filtros de Pesquisa")
        
        lista_setores = df['Setor'].unique().tolist()
        setor_selecionado = st.sidebar.selectbox("Selecione o Setor", lista_setores)
        
        # Filtra os funcionários apenas do setor selecionado
        funcionarios_do_setor = df[df['Setor'] == setor_selecionado]['Funcionário'].unique().tolist()
        funcionarios_do_setor.insert(0, "Todos os Funcionários")
        funcionario_selecionado = st.sidebar.selectbox("Selecione o Funcionário", funcionarios_do_setor)
        
        st.divider()
        
        # Gráfico Comparativo Setorial
        st.subheader(f"📊 Comparativo Mensal - Setor: {setor_selecionado}")
        df_setor = df[df['Setor'] == setor_selecionado]
        
        # Agrupa os valores para o gráfico
        df_agrupado_mes = df_setor.groupby('Mês/Ano')[['Hora Extra (R$)', 'Gratificação (R$)']].sum().reset_index()
        
        fig = px.bar(
            df_agrupado_mes, 
            x='Mês/Ano', 
            y=['Hora Extra (R$)', 'Gratificação (R$)'],
            barmode='group',
            labels={'value': 'Valor (R$)', 'variable': 'Tipo de Pagamento'},
            color_discrete_map={'Hora Extra (R$)': '#1f77b4', 'Gratificação (R$)': '#2ca02c'}
        )
        fig.update_layout(yaxis_tickformat="R$ .2f")
        st.plotly_chart(fig, use_container_width=True)

        st.divider()
        
        # Tabela de Detalhamento
        if funcionario_selecionado == "Todos os Funcionários":
            st.subheader(f"📋 Lançamentos - {setor_selecionado} (Geral)")
            df_tabela = df_setor
        else:
            st.subheader(f"👤 Lançamentos de: {funcionario_selecionado}")
            df_tabela = df_setor[df_setor['Funcionário'] == funcionario_selecionado]

        # Exibe a tabela final formatada
        st.dataframe(
            df_tabela,
            column_config={
                "Hora Extra (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
                "Gratificação (R$)": st.column_config.NumberColumn(format="R$ %.2f")
            },
            hide_index=True,
            use_container_width=True
        )
            
    else:
        st.error("O sistema não conseguiu encontrar informações válidas de Horas Extras ou Gratificações neste formato de PDF.")
else:
    st.info("Aguardando o envio do arquivo PDF para gerar o dashboard.")
