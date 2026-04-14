import streamlit as st
import pdfplumber
import pandas as pd
import re
import os
import plotly.express as px
from streamlit_gsheets import GSheetsConnection
import extra_streamlit_components as stx
import datetime
import time
import json
import pytesseract
from pdf2image import convert_from_bytes

# ==========================================
# 1. CONFIGURAÇÕES INICIAIS E MEMÓRIA
# ==========================================
st.set_page_config(page_title="Auditoria Folha - Jaborandi", layout="wide", initial_sidebar_state="expanded")

cookie_manager = stx.CookieManager(key="folha_mgr_vfinal")

if "primeira_vez" not in st.session_state:
    st.session_state.primeira_vez = False
    time.sleep(0.5)
    st.rerun()

if "uploader_key" not in st.session_state:
    st.session_state.uploader_key = 0
if "autenticado" not in st.session_state:
    st.session_state.autenticado = False
if "usuario_logado" not in st.session_state:
    st.session_state.usuario_logado = ""
if "nivel_acesso" not in st.session_state:
    st.session_state.nivel_acesso = ""
if "ignorar_cookie" not in st.session_state:
    st.session_state.ignorar_cookie = False
if "relatorio_recem_enviado" not in st.session_state:
    st.session_state.relatorio_recem_enviado = False

try:
    if st.session_state.ignorar_cookie:
        st.session_state.ignorar_cookie = False
    else:
        pacote_sessao = cookie_manager.get(cookie="sessao_folha")
        if pacote_sessao and not st.session_state.autenticado:
            dados = pacote_sessao if isinstance(pacote_sessao, dict) else json.loads(pacote_sessao)
            st.session_state.autenticado = True
            st.session_state.usuario_logado = dados["user"]
            st.session_state.nivel_acesso = dados["nivel"]
except Exception as e:
    pass

# ==========================================
# 2. CUSTOMIZAÇÃO VISUAL (TEMA JABORANDI)
# ==========================================
st.markdown("""
<style>
    .block-container { padding-top: 2rem; padding-bottom: 2rem; }
    h1, h2, h3 { color: #0C3C7A; font-family: 'Segoe UI', sans-serif; font-weight: 700; }
    .stButton>button {
        background-color: #0C3C7A; color: white; border-radius: 8px; 
        border: none; padding: 0.5rem 1rem; transition: all 0.3s ease; font-weight: 600;
        width: 100%;
    }
    .stButton>button:hover { background-color: #082954; color: white; transform: translateY(-2px); box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
    div[data-testid="stMetricValue"] { color: #0C3C7A; font-weight: 800; }
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] { height: 50px; background-color: transparent; border-radius: 6px 6px 0px 0px; padding: 10px 20px; border: 1px solid transparent; }
    .stTabs [aria-selected="true"] { background-color: #E8F0FE; border-bottom: 4px solid #0C3C7A !important; color: #0C3C7A !important; font-weight: 800; }
    [data-testid="stSidebar"] { background-color: #F8F9FA; border-right: 1px solid #DEE2E6; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 3. FUNÇÕES BASE E EXTRAÇÃO (OCR FOLHA)
# ==========================================
MESES_PT = {
    "01": "Janeiro", "02": "Fevereiro", "03": "Março", "04": "Abril",
    "05": "Maio", "06": "Junho", "07": "Julho", "08": "Agosto",
    "09": "Setembro", "10": "Outubro", "11": "Novembro", "12": "Dezembro", "00": "Desconhecido"
}

RUBRICAS = {
    '006': {'nome': '006 - HE 50%', 'tipo': 'Hora Extra'},
    '011': {'nome': '011 - HE 100%', 'tipo': 'Hora Extra'},
    '018': {'nome': '018 - HE Mês Ant.', 'tipo': 'Hora Extra'},
    '031': {'nome': '031 - Gratific. Lei', 'tipo': 'Gratificação'},
    '089': {'nome': '089 - Comp. Carga', 'tipo': 'Hora Extra'},
    '812': {'nome': '812 - Gratificação SAMU', 'tipo': 'Gratificação'}
}

def formata_moeda(valor):
    return f"R$ {valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

def converter_para_numero(valor):
    if pd.isna(valor): return 0.0
    if isinstance(valor, (int, float)): return float(valor)
    v_str = str(valor).strip()
    v_str = re.sub(r'[^\d\.,\-]', '', v_str)
    if v_str == '': return 0.0
    if '.' in v_str and ',' in v_str:
        v_str = v_str.replace('.', '')
    v_str = v_str.replace(',', '.')
    try: return float(v_str)
    except ValueError: return 0.0

@st.cache_data(show_spinner=False)
def extrair_dados_ocr(arquivos):
    registros = []
    meses_identificados = set()

    for arquivo in arquivos:
        pdf_bytes = arquivo.read()
        imagens = convert_from_bytes(pdf_bytes, dpi=200)
        
        mes_arquivo = "Indefinido"
        
        # MEMÓRIA DO SETOR: Fica fora do ciclo das páginas para não sofrer amnésia
        setor_memoria = "Não Identificado"
        
        progress_bar = st.progress(0)
        status_text = st.empty()

        for num_pag, imagem in enumerate(imagens):
            status_text.text(f"A processar página {num_pag + 1} de {len(imagens)} do ficheiro {arquivo.name}...")
            texto_ocr = pytesseract.image_to_string(imagem, lang='por')
            linhas = texto_ocr.split('\n')

            for i, linha in enumerate(linhas):
                linha_limpa = linha.strip()

                # 1. Trava do Mês/Ano
                if mes_arquivo == "Indefinido" and "Mês/Ano" in linha_limpa:
                    match = re.search(r"(\d{2}/\d{4})", linha_limpa)
                    if match: mes_arquivo = match.group(1)
                    elif i + 1 < len(linhas):
                        match2 = re.search(r"(\d{2}/\d{4})", linhas[i+1])
                        if match2: mes_arquivo = match2.group(1)

                # 2. Leitura Flexível do Setor (Ignora falhas do OCR)
                match_setor = re.search(r'(?:Local\s+de\s+)?Trabalho\s*[:;]\s*(.+)', linha_limpa, re.IGNORECASE)
                if match_setor:
                    parte = match_setor.group(1).strip()
                    parte = re.sub(r'["\'|\[\]]', '', parte).strip()
                    if parte:
                        if "-" in parte:
                            setor_memoria = parte.split("-", 1)[-1].strip().title()
                        else:
                            setor_memoria = parte.title()

                # 3. Busca de Rubricas
                match_rubrica = re.search(r'^"?\s*(006|011|018|031|089|812)\b', linha_limpa)
                if match_rubrica:
                    codigo = match_rubrica.group(1)
                    numeros = re.findall(r'(?<!\d)\d{1,3}(?:[\.\,]\d{3})*[\.\,]\d{2}(?!\d)', linha_limpa)
                    
                    if not numeros:
                        bloco = " ".join([linhas[i+j] for j in range(1, 4) if i+j < len(linhas)])
                        numeros = re.findall(r'(?<!\d)\d{1,3}(?:[\.\,]\d{3})*[\.\,]\d{2}(?!\d)', bloco)

                    if numeros:
                        valor = converter_para_numero(numeros[-1])
                        if valor > 0:
                            nome_exibicao = setor_memoria if setor_memoria != "Não Identificado" else f"Página {num_pag+1} (Editar)"
                            
                            registros.append({
                                'Arquivo': arquivo.name,
                                'Mês/Ano Numérico': mes_arquivo,
                                'Setor': nome_exibicao,
                                'Código': codigo,
                                'Rubrica': RUBRICAS[codigo]['nome'],
                                'Tipo': RUBRICAS[codigo]['tipo'],
                                'Valor (R$)': valor
                            })
                            
            progress_bar.progress((num_pag + 1) / len(imagens))

        progress_bar.empty()
        status_text.empty()
        meses_identificados.add(mes_arquivo)

    if not registros:
        return pd.DataFrame(), []

    df = pd.DataFrame(registros)
    mes_oficial = df[df['Mês/Ano Numérico'] != 'Indefinido']['Mês/Ano Numérico'].max()
    if pd.notna(mes_oficial):
        df['Mês/Ano Numérico'] = mes_oficial

    if mes_oficial and mes_oficial != "Indefinido":
        mes_split, ano_split = mes_oficial.split("/")
        df['Mês'] = mes_split
        df['Ano'] = ano_split
    else:
        df['Mês'] = "00"
        df['Ano'] = "0000"

    df_db = df.groupby(['Arquivo', 'Mês/Ano Numérico', 'Mês', 'Ano', 'Setor', 'Código', 'Rubrica', 'Tipo'], as_index=False)['Valor (R$)'].max()
    return df_db, list(meses_identificados)

# ==========================================
# 4. BARRA LATERAL FIXA
# ==========================================
url_brasao = "logo.png"
col_img1, col_img2, col_img3 = st.sidebar.columns([1, 2, 1])
with col_img2:
    try: st.image(url_brasao, use_container_width=True)
    except: pass 
        
st.sidebar.markdown(
    """
    <div style='text-align: center; color: #0C3C7A; font-weight: 700; font-size: 16px; margin-bottom: 25px;'>
        Prefeitura Municipal<br>de Jaborandi/SP
    </div>
    """, unsafe_allow_html=True
)
st.sidebar.markdown("---")

# ==========================================
# 5. TELA DE LOGIN CENTRALIZADA
# ==========================================
if not st.session_state.autenticado:
    st.title("🏛️ Sistema de Auditoria de Folha")
    st.write("---")
    col_espaco1, col_login, col_espaco3 = st.columns([1, 2, 1])
    
    with col_login:
        st.markdown("<h3 style='text-align: center; color: #0C3C7A;'>🔒 Acesso ao Painel</h3>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center;'>Por favor, insira as suas credenciais institucionais.</p>", unsafe_allow_html=True)
        st.write("") 
        
        usuario_digitado = st.text_input("Usuário").strip()
        senha_digitada = st.text_input("Palavra-passe", type="password")
        lembrar_me = st.checkbox("Manter-me ligado neste computador")
        
        if st.button("Entrar no Sistema", use_container_width=True):
            try:
                login_sucesso = False
                if "admin" in st.secrets and usuario_digitado in st.secrets["admin"]:
                    if st.secrets["admin"][usuario_digitado] == senha_digitada:
                        st.session_state.autenticado = True
                        st.session_state.usuario_logado = usuario_digitado
                        st.session_state.nivel_acesso = "admin"
                        login_sucesso = True
                elif "viewer" in st.secrets and usuario_digitado in st.secrets["viewer"]:
                    if st.secrets["viewer"][usuario_digitado] == senha_digitada:
                        st.session_state.autenticado = True
                        st.session_state.usuario_logado = usuario_digitado
                        st.session_state.nivel_acesso = "viewer"
                        login_sucesso = True
                        
                if login_sucesso:
                    if lembrar_me:
                        pacote = json.dumps({"user": usuario_digitado, "nivel": st.session_state.nivel_acesso})
                        expira_em = datetime.datetime.now() + datetime.timedelta(days=30)
                        cookie_manager.set("sessao_folha", pacote, expires_at=expira_em)
                        time.sleep(0.5) 
                    st.rerun()
                else:
                    st.error("Usuário ou palavra-passe incorretos! Tente novamente.")
            except Exception as e:
                st.error("🚨 ERRO NO PROCESSO DE LOGIN.")
                st.exception(e)
                st.stop()
    st.stop()

# ==========================================
# 6. LER BASE DE DADOS (PÓS-LOGIN)
# ==========================================
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    colunas_bd = ["Arquivo", "Mês/Ano Numérico", "Mês", "Ano", "Setor", "Código", "Rubrica", "Tipo", "Valor (R$)"]
    df_db = conn.read(worksheet="Dados", ttl=0)
    
    if df_db.empty or "Rubrica" not in df_db.columns:
        df_db = pd.DataFrame(columns=colunas_bd)
    else:
        df_db["Valor (R$)"] = df_db["Valor (R$)"].apply(converter_para_numero)
        df_db["Mês"] = df_db["Mês"].astype(str).str.replace(".0", "", regex=False).str.zfill(2)
        df_db["Ano"] = df_db["Ano"].astype(str).str.replace(".0", "", regex=False)
        df_db = df_db.sort_values(by=["Ano", "Mês"])
        df_db["Nome do Mês"] = df_db["Mês"].map(MESES_PT).fillna("Desconhecido")
        df_db["Mês/Ano Exibição"] = df_db["Nome do Mês"] + " " + df_db["Ano"]
        ordem_cronologica = df_db["Mês/Ano Exibição"].unique().tolist()
        
except Exception as e:
    st.error("🚨 Erro ao ligar ao Google Sheets. Verifique se a folha se chama 'Dados' e as colunas estão corretas.")
    df_db = pd.DataFrame(columns=["Ano"]) 
    ordem_cronologica = []

# ==========================================
# 7. BARRA LATERAL E LOGOUT PROTEGIDO
# ==========================================
st.sidebar.title("Filtros de Gestão")

if not df_db.empty and len(df_db) > 0 and "Ano" in df_db.columns:
    anos_disponiveis = df_db["Ano"].dropna().unique().tolist()
    anos_disponiveis.sort(reverse=True)
    if anos_disponiveis:
        ano_escolhido = st.sidebar.selectbox("Filtre as análises por Ano:", anos_disponiveis)
        df_ano = df_db[df_db["Ano"] == ano_escolhido]
        
        total_he = df_ano[df_ano["Tipo"] == "Hora Extra"]["Valor (R$)"].sum()
        total_grat = df_ano[df_ano["Tipo"] == "Gratificação"]["Valor (R$)"].sum()
        
        st.sidebar.write("---")
        st.sidebar.info(f"**Resumo Global ({ano_escolhido}):**\n\n"
                        f"🕒 Total HE: **{formata_moeda(total_he)}**\n\n"
                        f"💰 Total Gratificações: **{formata_moeda(total_grat)}**")
    else:
        ano_escolhido = None
        df_ano = pd.DataFrame()
else:
    ano_escolhido = None
    df_ano = pd.DataFrame()

st.sidebar.markdown("---")
st.sidebar.success(f"✅ Sessão iniciada como: **{st.session_state.usuario_logado.capitalize()}**")
st.sidebar.caption(f"Nível: {'Administrador' if st.session_state.nivel_acesso == 'admin' else 'Visualizador'}")

if st.sidebar.button("Sair do Sistema", use_container_width=True):
    st.session_state.autenticado = False
    st.session_state.usuario_logado = ""
    st.session_state.nivel_acesso = ""
    st.session_state.ignorar_cookie = True 
    st.components.v1.html(
        """<script>document.cookie = "sessao_folha=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;"; window.parent.location.reload();</script>""",
        height=0
    )

# ==========================================
# 8. ÁREA PRINCIPAL E GATILHO DO WHATSAPP
# ==========================================
st.title("🏛️ Painel Auditoria de Folha")

if st.session_state.relatorio_recem_enviado:
    st.success("✅ A base de dados na nuvem foi atualizada com sucesso!")
    numero_prefeito = "556296962071" 
    mensagem = "Olá Prefeito, os dados de Horas Extras e Gratificações da Folha acabam de ser atualizados. O sistema está pronto para análise no link: https://valdirgc.github.io/folha-jaborandi/."
    link_wpp = f"https://api.whatsapp.com/send?phone={numero_prefeito}&text={mensagem.replace(' ', '%20')}"
    
    st.markdown(f"""
    <a href="{link_wpp}" target="_blank" style="text-decoration: none;">
        <div style="background-color: #25D366; color: white; padding: 12px; border-radius: 8px; text-align: center; font-weight: bold; margin-bottom: 10px; cursor: pointer;">
            📱 Notificar Prefeito via WhatsApp
        </div>
    </a>
    """, unsafe_allow_html=True)
    
    if st.button("❌ Dispensar Aviso"):
        st.session_state.relatorio_recem_enviado = False
        st.rerun()
    st.write("---")

if st.session_state.nivel_acesso == "admin" and not st.session_state.relatorio_recem_enviado:
    with st.expander("📥 Importar e Homologar Resumos Contábeis (PDF)"):
        st.write("*O sistema usará IA (OCR) para leitura. Aguarde a conversão das imagens.*")
        arquivos_pdf = st.file_uploader(
            "Selecione os PDFs", type=["pdf"], accept_multiple_files=True, key=f"uploader_{st.session_state.uploader_key}"
        )

        if arquivos_pdf:
            with st.spinner("A processar Inteligência Artificial..."):
                df_extraido, meses_identificados = extrair_dados_ocr(arquivos_pdf)
            
            if not df_extraido.empty:
                st.success(f"Foram extraídas {len(df_extraido)} rubricas!")
                st.markdown("### ✍️ Tabela de Homologação")
                st.warning("Verifique a coluna 'Setor'. Se o robô não conseguiu ler o nome do setor e aparecer '(Editar)', dê dois cliques na célula abaixo, corrija o nome e depois guarde.")
                
                # O utilizador edita os setores antes de guardar
                df_editado = st.data_editor(
                    df_extraido,
                    column_config={
                        "Setor": st.column_config.TextColumn("Local de Trabalho (HOMOLOGAR)", required=True),
                        "Valor (R$)": st.column_config.NumberColumn(format="R$ %.2f", disabled=True),
                    },
                    use_container_width=True, hide_index=True
                )
                
                if st.button("💾 Validar e Integrar no Servidor"):
                    meses_ja_salvos = df_db["Mês/Ano Numérico"].dropna().unique().tolist()
                    df_novos = df_editado[~df_editado["Mês/Ano Numérico"].isin(meses_ja_salvos)]
                    meses_ignorados = df_editado[df_editado["Mês/Ano Numérico"].isin(meses_ja_salvos)]["Mês/Ano Numérico"].unique().tolist()
                    
                    if not df_novos.empty:
                        df_completo = pd.concat([df_db, df_novos], ignore_index=True)
                        conn.update(worksheet="Dados", data=df_completo)
                        st.session_state.relatorio_recem_enviado = True 
                    
                    if meses_ignorados:
                        st.error(f"Os meses {', '.join(meses_ignorados)} já existiam e foram ignorados.")
                    
                    st.session_state.uploader_key += 1
                    st.rerun()

# ==========================================
# 9. DASHBOARD GERENCIAL
# ==========================================
st.write("---")

if not df_ano.empty and "Mês/Ano Exibição" in df_ano.columns:
    aba1, aba2, aba3, aba4 = st.tabs([
        "📈 Evolução Global", "🏢 Análise por Setor", "🔍 Análise por Rubrica", "📅 Comparativo Anual"
    ])
    
    id_sufixo = f"_{ano_escolhido}"
    
    # Pivot Table consolidado para toda a aplicação usar
    df_pivot_ano = df_ano.pivot_table(
        index=['Mês/Ano Exibição', 'Setor'], 
        columns='Rubrica', values='Valor (R$)', aggfunc='sum'
    ).fillna(0).reset_index()
    
    colunas_he = [c for c in df_pivot_ano.columns if 'HE' in c or 'Carga' in c]
    colunas_grat = [c for c in df_pivot_ano.columns if 'Gratific' in c or 'SAMU' in c]
    df_pivot_ano['TOTAL HE'] = df_pivot_ano[colunas_he].sum(axis=1) if colunas_he else 0
    df_pivot_ano['TOTAL GRAT'] = df_pivot_ano[colunas_grat].sum(axis=1) if colunas_grat else 0
    df_pivot_ano['TOTAL GERAL'] = df_pivot_ano['TOTAL HE'] + df_pivot_ano['TOTAL GRAT']

    # --- ABA 1: GERAL ---
    with aba1:
        st.subheader(f"Gastos Totais ({ano_escolhido})")
        resumo_mes = df_pivot_ano.groupby("Mês/Ano Exibição", sort=False)[["TOTAL HE", "TOTAL GRAT"]].sum().reset_index()
        
        col1, col2 = st.columns(2)
        with col1:
            fig1 = px.bar(resumo_mes, x="Mês/Ano Exibição", y="TOTAL HE", title="Horas Extras (R$)", color_discrete_sequence=["#0C3C7A"], category_orders={"Mês/Ano Exibição": ordem_cronologica})
            st.plotly_chart(fig1, use_container_width=True, key=f"g_he{id_sufixo}")
        with col2:
            fig2 = px.bar(resumo_mes, x="Mês/Ano Exibição", y="TOTAL GRAT", title="Gratificações (R$)", color_discrete_sequence=["#FF7F0E"], category_orders={"Mês/Ano Exibição": ordem_cronologica})
            st.plotly_chart(fig2, use_container_width=True, key=f"g_grat{id_sufixo}")
            
        st.write("**Consolidação Mensal (Valores Totais)**")
        st.dataframe(resumo_mes.style.format({"TOTAL HE": "R$ {:.2f}", "TOTAL GRAT": "R$ {:.2f}"}), use_container_width=True, hide_index=True)
        
    # --- ABA 2: SETOR ---
    with aba2:
        st.subheader(f"Investigação por Setor ({ano_escolhido})")
        setor_escolhido = st.selectbox("Selecione o Setor:", df_pivot_ano["Setor"].unique().tolist())
        df_setor = df_pivot_ano[df_pivot_ano["Setor"] == setor_escolhido]
        
        fig_s1 = px.line(df_setor, x="Mês/Ano Exibição", y=["TOTAL HE", "TOTAL GRAT"], markers=True, title=f"Evolução - {setor_escolhido}", category_orders={"Mês/Ano Exibição": ordem_cronologica})
        st.plotly_chart(fig_s1, use_container_width=True, key=f"g_setor{id_sufixo}")
        
        st.write(f"**Detalhamento Fino - {setor_escolhido}**")
        formato_moeda = {col: "R$ {:.2f}" for col in df_setor.columns if col not in ['Mês/Ano Exibição', 'Setor']}
        st.dataframe(df_setor.style.format(formato_moeda), use_container_width=True, hide_index=True)
            
    # --- ABA 3: RUBRICA ---
    with aba3:
        st.subheader(f"Custo por Código Específico ({ano_escolhido})")
        rubricas_disp = df_ano["Rubrica"].unique().tolist()
        rubrica_escolhida = st.selectbox("Selecione a Rubrica:", rubricas_disp)
        
        df_rubrica = df_ano[df_ano["Rubrica"] == rubrica_escolhida]
        resumo_rub_mes = df_rubrica.groupby("Mês/Ano Exibição", sort=False)["Valor (R$)"].sum().reset_index()
        
        fig_r1 = px.bar(resumo_rub_mes, x="Mês/Ano Exibição", y="Valor (R$)", text_auto=".2s", color_discrete_sequence=["#4CAF50"], title=f"Total Pago: {rubrica_escolhida}", category_orders={"Mês/Ano Exibição": ordem_cronologica})
        st.plotly_chart(fig_r1, use_container_width=True, key=f"g_rub{id_sufixo}")

    # --- ABA 4: COMPARATIVO ANUAL ---
    with aba4:
        st.subheader("Variação do Mesmo Mês entre Anos (Detalhamento)")
        meses_salvos = df_db["Nome do Mês"].unique().tolist()
        
        if meses_salvos:
            mes_escolhido = st.selectbox("Selecione o Mês para comparar:", meses_salvos)
            
            # Agrupa agora pelo Ano E pelo Tipo (Hora Extra / Gratificação)
            df_comparativo = df_db[df_db["Nome do Mês"] == mes_escolhido].groupby(["Ano", "Tipo"])[["Valor (R$)"]].sum().reset_index()
            df_comparativo["Ano"] = df_comparativo["Ano"].astype(str)
            
            if not df_comparativo.empty:
                # Cria o gráfico com barras agrupadas (lado a lado)
                fig_a1 = px.bar(
                    df_comparativo, 
                    x="Ano", 
                    y="Valor (R$)", 
                    color="Tipo", 
                    barmode="group", # Coloca as barras lado a lado
                    text_auto=".2s", 
                    title=f"Variação Financeira por Categoria - {mes_escolhido}",
                    color_discrete_map={"Hora Extra": "#0C3C7A", "Gratificação": "#FF7F0E"} # Cores padronizadas
                )
                
                # Joga o texto do valor para cima da barra para não amontoar
                fig_a1.update_traces(textposition='outside')
                
                st.plotly_chart(fig_a1, use_container_width=True, key=f"g_ano{id_sufixo}")
                
                # Adiciona também uma tabelinha resumo abaixo do gráfico para facilitar a cópia
                st.write("**Tabela de Variação (Valores Totais)**")
                df_comp_pivot = df_comparativo.pivot(index="Ano", columns="Tipo", values="Valor (R$)").fillna(0).reset_index()
                
                # Formata a tabela para moeda
                formato_moeda_comp = {col: "R$ {:.2f}" for col in df_comp_pivot.columns if col != 'Ano'}
                st.dataframe(df_comp_pivot.style.format(formato_moeda_comp), use_container_width=True, hide_index=True)
            else:
                st.info(f"Não há lançamentos de rubricas no mês de {mes_escolhido} nos anos selecionados.")
