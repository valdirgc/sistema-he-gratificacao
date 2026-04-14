import streamlit as st
import pdfplumber
import pandas as pd
import re
import os
import plotly.express as px
from streamlit_gsheets import GSheetsConnection
import extra_streamlit_components as stx
import datetime
import json
import time
import pytesseract
from pdf2image import convert_from_bytes

# ==========================================
# 1. CONFIGURAÇÕES INICIAIS E SEGURANÇA
# ==========================================
st.set_page_config(page_title="Auditoria Folha - Jaborandi", layout="wide", initial_sidebar_state="expanded")

# Gestão de Cookies para Login Persistente
cookie_manager = stx.CookieManager(key="folha_auditoria_vfinal")

# Inicialização de Estados
if "autenticado" not in st.session_state:
    st.session_state.autenticado = False
if "usuario_logado" not in st.session_state:
    st.session_state.usuario_logado = ""
if "nivel_acesso" not in st.session_state:
    st.session_state.nivel_acesso = ""
if "uploader_key" not in st.session_state:
    st.session_state.uploader_key = 0
if "relatorio_recem_enviado" not in st.session_state:
    st.session_state.relatorio_recem_enviado = False

# Lógica de Auto-Login via Cookie
try:
    pacote_sessao = cookie_manager.get(cookie="sessao_folha")
    if pacote_sessao and not st.session_state.autenticado:
        dados = pacote_sessao if isinstance(pacote_sessao, dict) else json.loads(pacote_sessao)
        st.session_state.autenticado = True
        st.session_state.usuario_logado = dados["user"]
        st.session_state.nivel_acesso = dados["nivel"]
except:
    pass

# ==========================================
# 2. TEMA VISUAL (PADRÃO JABORANDI)
# ==========================================
st.markdown("""
<style>
    .block-container { padding-top: 2rem; }
    h1, h2, h3 { color: #0C3C7A; font-family: 'Segoe UI', sans-serif; font-weight: 700; }
    .stButton>button {
        background-color: #0C3C7A; color: white; border-radius: 8px; font-weight: 600; width: 100%;
    }
    .stButton>button:hover { background-color: #082954; transform: translateY(-1px); }
    [data-testid="stSidebar"] { background-color: #F8F9FA; border-right: 1px solid #DEE2E6; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 3. DICIONÁRIOS E AUXILIARES
# ==========================================
MESES_PT = {
    "01": "Janeiro", "02": "Fevereiro", "03": "Março", "04": "Abril",
    "05": "Maio", "06": "Junho", "07": "Julho", "08": "Agosto",
    "09": "Setembro", "10": "Outubro", "11": "Novembro", "12": "Dezembro"
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
    v_str = re.sub(r'[^\d\.,\-]', '', str(valor).strip())
    if not v_str: return 0.0
    if '.' in v_str and ',' in v_str: v_str = v_str.replace('.', '')
    v_str = v_str.replace(',', '.')
    try: return float(v_str)
    except: return 0.0

# ==========================================
# 4. MOTOR DE INTELIGÊNCIA ARTIFICIAL (OCR)
# ==========================================
@st.cache_data(show_spinner=False)
def extrair_dados_ocr(arquivos):
    registros = []
    for arquivo in arquivos:
        imagens = convert_from_bytes(arquivo.read(), dpi=200)
        mes_ano_arquivo = "Indefinido"
        setor_memoria = "Não Identificado"
        
        progresso = st.progress(0)
        status = st.empty()

        for idx, img in enumerate(imagens):
            status.text(f"Lendo página {idx+1} de {len(imagens)}...")
            texto = pytesseract.image_to_string(img, lang='por')
            linhas = texto.split('\n')

            for i, linha in enumerate(linhas):
                # Captura Mês/Ano (Fica travado para o arquivo)
                if mes_ano_arquivo == "Indefinido":
                    m_data = re.search(r"(\d{2}/\d{4})", linha)
                    if m_data: mes_ano_arquivo = m_data.group(1)

                # Captura Setor (Com memória para as páginas seguintes)
                m_setor = re.search(r'(?:Trabalho)\s*[:;]\s*(.+)', linha, re.IGNORECASE)
                if m_setor:
                    s_bruto = re.sub(r'["\'|\[\]]', '', m_setor.group(1)).strip()
                    setor_memoria = s_bruto.split("-")[-1].strip().title() if s_bruto else setor_memoria

                # Captura Rubricas
                m_rub = re.search(r'^"?\s*(006|011|018|031|089|812)\b', linha.strip())
                if m_rub:
                    cod = m_rub.group(1)
                    nums = re.findall(r'\d{1,3}(?:[\.\,]\d{3})*[\.\,]\d{2}', linha)
                    if not nums: # Busca na linha de baixo se o OCR quebrou
                        nums = re.findall(r'\d{1,3}(?:[\.\,]\d{3})*[\.\,]\d{2}', " ".join(linhas[i+1:i+3]))
                    
                    if nums:
                        valor = converter_para_numero(nums[-1])
                        registros.append({
                            'Arquivo': arquivo.name, 'Mês/Ano Numérico': mes_ano_arquivo,
                            'Setor': setor_memoria, 'Código': cod,
                            'Rubrica': RUBRICAS[cod]['nome'], 'Tipo': RUBRICAS[cod]['tipo'],
                            'Valor (R$)': valor
                        })
            progresso.progress((idx + 1) / len(imagens))
        progresso.empty()
        status.empty()

    df = pd.DataFrame(registros)
    if not df.empty:
        # Ajuste de Datas
        data_final = df[df['Mês/Ano Numérico'] != 'Indefinido']['Mês/Ano Numérico'].max()
        df['Mês/Ano Numérico'] = data_final
        df['Mês'] = data_final.split("/")[0]
        df['Ano'] = data_final.split("/")[1]
    return df

# ==========================================
# 5. LÓGICA DE LOGIN
# ==========================================
if not st.session_state.autenticado:
    st.title("🏛️ Sistema de Auditoria de Folha")
    st.write("---")
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.subheader("🔒 Acesso Restrito")
        user = st.text_input("Usuário").strip()
        pw = st.text_input("Senha", type="password")
        lembrar = st.checkbox("Manter-me conectado")
        if st.button("Entrar"):
            if user in st.secrets["admin"] and st.secrets["admin"][user] == pw:
                st.session_state.autenticado, st.session_state.nivel_acesso = True, "admin"
                st.session_state.usuario_logado = user
            elif user in st.secrets["viewer"] and st.secrets["viewer"][user] == pw:
                st.session_state.autenticado, st.session_state.nivel_acesso = True, "viewer"
                st.session_state.usuario_logado = user
            
            if st.session_state.autenticado:
                if lembrar:
                    cookie_manager.set("sessao_folha", {"user": user, "nivel": st.session_state.nivel_acesso}, expires_at=datetime.datetime.now() + datetime.timedelta(days=30))
                st.rerun()
            else: st.error("Credenciais inválidas")
    st.stop()

# ==========================================
# 6. CONEXÃO DATABASE (GOOGLE SHEETS)
# ==========================================
conn = st.connection("gsheets", type=GSheetsConnection)
df_db = conn.read(worksheet="Dados", ttl=0)

if not df_db.empty and "Valor (R$)" in df_db.columns:
    df_db["Valor (R$)"] = df_db["Valor (R$)"].apply(converter_para_numero)
    df_db["Mês"] = df_db["Mês"].astype(str).str.replace(".0", "", regex=False).str.zfill(2)
    df_db["Ano"] = df_db["Ano"].astype(str).str.replace(".0", "", regex=False)
    df_db["Nome do Mês"] = df_db["Mês"].map(MESES_PT)
    df_db["Mês/Ano Exibição"] = df_db["Nome do Mês"] + " " + df_db["Ano"]
    ordem_meses = df_db.sort_values(["Ano", "Mês"])["Mês/Ano Exibição"].unique().tolist()

# ==========================================
# 7. SIDEBAR (FILTROS E LOGOUT)
# ==========================================
st.sidebar.image("logo.png", use_container_width=True)
st.sidebar.markdown("<h3 style='text-align:center;'>Jaborandi/SP</h3>", unsafe_allow_html=True)
st.sidebar.write("---")

ano_sel = st.sidebar.selectbox("Ano de Referência", sorted(df_db["Ano"].unique(), reverse=True)) if not df_db.empty else None
df_ano = df_db[df_db["Ano"] == ano_sel] if ano_sel else pd.DataFrame()

if not df_ano.empty:
    st.sidebar.metric("Total HE", formata_moeda(df_ano[df_ano["Tipo"]=="Hora Extra"]["Valor (R$)"].sum()))
    st.sidebar.metric("Total Gratificações", formata_moeda(df_ano[df_ano["Tipo"]=="Gratificação"]["Valor (R$)"].sum()))

if st.sidebar.button("Sair do Sistema"):
    cookie_manager.delete("sessao_folha")
    st.session_state.autenticado = False
    st.rerun()

# ==========================================
# 8. ÁREA ADMINISTRATIVA (UPLOAD E OCR)
# ==========================================
if st.session_state.nivel_acesso == "admin":
    st.title("🏛️ Painel de Gestão e Auditoria")
    
    if st.session_state.relatorio_recem_enviado:
        st.success("✅ Banco de Dados Atualizado!")
        wpp_msg = f"https://api.whatsapp.com/send?phone=556296962071&text=Olá%20Prefeito,%20os%20dados%20da%20folha%20foram%20atualizados."
        st.markdown(f'<a href="{wpp_msg}" target="_blank"><button style="background-color:#25D366; color:white; border:none; padding:10px; border-radius:5px; width:100%; cursor:pointer; font-weight:bold;">📱 Notificar Prefeito</button></a>', unsafe_allow_html=True)
        if st.button("Limpar Aviso"): 
            st.session_state.relatorio_recem_enviado = False
            st.rerun()

    with st.expander("📥 Importar Novos Relatórios (PDF)"):
        files = st.file_uploader("Selecione os arquivos", type="pdf", accept_multiple_files=True, key=f"up_{st.session_state.uploader_key}")
        if files:
            with st.spinner("IA processando imagens..."):
                df_novos = extrair_dados_ocr(files)
            if not df_novos.empty:
                st.write("### ✍️ Homologação de Dados")
                st.info("Ajuste os nomes dos setores se necessário antes de salvar.")
                df_homolog = st.data_editor(df_novos, use_container_width=True, hide_index=True)
                
                if st.button("💾 Confirmar e Salvar no Banco"):
                    meses_existentes = df_db["Mês/Ano Numérico"].unique().tolist()
                    final_to_save = df_homolog[~df_homolog["Mês/Ano Numérico"].isin(meses_existentes)]
                    if not final_to_save.empty:
                        conn.update(worksheet="Dados", data=pd.concat([df_db, final_to_save], ignore_index=True))
                        st.session_state.relatorio_recem_enviado = True
                        st.session_state.uploader_key += 1
                        st.rerun()
                    else: st.error("Este mês já existe no banco de dados.")

# ==========================================
# 9. DASHBOARD (VISUALIZAÇÃO)
# ==========================================
if not df_ano.empty:
    st.write("---")
    t1, t2, t3, t4 = st.tabs(["📈 Geral", "🏢 Por Setor", "🔍 Por Rubrica", "📅 Comparativo Anual"])

    # Consolidação para os gráficos
    df_piv = df_ano.pivot_table(index=['Mês/Ano Exibição', 'Setor'], columns='Tipo', values='Valor (R$)', aggfunc='sum').fillna(0).reset_index()

    with t1:
        c1, c2 = st.columns(2)
        res_geral = df_piv.groupby("Mês/Ano Exibição", sort=False).sum().reset_index()
        c1.plotly_chart(px.bar(res_geral, x="Mês/Ano Exibição", y="Hora Extra", title="Total Horas Extras", color_discrete_sequence=["#0C3C7A"], category_orders={"Mês/Ano Exibição": ordem_meses}), use_container_width=True)
        c2.plotly_chart(px.bar(res_geral, x="Mês/Ano Exibição", y="Gratificação", title="Total Gratificações", color_discrete_sequence=["#FF7F0E"], category_orders={"Mês/Ano Exibição": ordem_cronologica}), use_container_width=True)
        st.dataframe(res_geral.style.format({"Hora Extra": "R$ {:.2f}", "Gratificação": "R$ {:.2f}"}), use_container_width=True, hide_index=True)

    with t2:
        setor = st.selectbox("Filtrar Setor", df_piv["Setor"].unique())
        df_s = df_piv[df_piv["Setor"] == setor]
        st.plotly_chart(px.line(df_s, x="Mês/Ano Exibição", y=["Hora Extra", "Gratificação"], markers=True, title=f"Evolução - {setor}", category_orders={"Mês/Ano Exibição": ordem_meses}), use_container_width=True)

    with t3:
        rub = st.selectbox("Filtrar Rubrica", df_ano["Rubrica"].unique())
        res_r = df_ano[df_ano["Rubrica"] == rub].groupby("Mês/Ano Exibição", sort=False)["Valor (R$)"].sum().reset_index()
        st.plotly_chart(px.bar(res_r, x="Mês/Ano Exibição", y="Valor (R$)", title=f"Custo: {rub}", color_discrete_sequence=["#4CAF50"], category_orders={"Mês/Ano Exibição": ordem_meses}), use_container_width=True)

    with t4:
        st.subheader("Variação do Mesmo Mês entre Anos")
        mes_ref = st.selectbox("Mês de Comparação", df_db["Nome do Mês"].unique())
        df_comp = df_db[df_db["Nome do Mês"] == mes_ref].groupby(["Ano", "Tipo"])["Valor (R$)"].sum().reset_index()
        
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("##### 🕒 Horas Extras")
            fig_he = px.bar(df_comp[df_comp["Tipo"]=="Hora Extra"], x="Ano", y="Valor (R$)", text_auto=".2s", color_discrete_sequence=["#0C3C7A"])
            st.plotly_chart(fig_he, use_container_width=True)
        with c2:
            st.markdown("##### 💰 Gratificações")
            fig_gr = px.bar(df_comp[df_comp["Tipo"]=="Gratificação"], x="Ano", y="Valor (R$)", text_auto=".2s", color_discrete_sequence=["#FF7F0E"])
            st.plotly_chart(fig_gr, use_container_width=True)
        
        st.write("**Tabela Consolidada**")
        st.dataframe(df_comp.pivot(index="Ano", columns="Tipo", values="Valor (R$)").style.format("R$ {:.2f}"), use_container_width=True)

else: st.info("Aguardando upload de dados para exibir o Dashboard.")
