import streamlit as st
import pandas as pd
import json
import os
import glob
import plotly.express as px
from datetime import datetime

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Monitor DOE-PE",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- FUNÇÃO DE CARREGAMENTO DE DADOS ---
@st.cache_data
def load_data(report_dir):
    all_files = glob.glob(os.path.join(report_dir, "*.json"))
    
    if not all_files:
        return pd.DataFrame()
    
    data_frames = []
    for filename in all_files:
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if data:
                    df = pd.DataFrame(data)
                    # Adiciona coluna com a data do arquivo (extraída do nome ou timestamp interno)
                    df['arquivo_origem'] = os.path.basename(filename)
                    data_frames.append(df)
        except Exception as e:
            st.error(f"Erro ao ler {filename}: {e}")
            
    if not data_frames:
        return pd.DataFrame()
        
    final_df = pd.concat(data_frames, ignore_index=True)
    
    # Converter data se existir
    if 'data_processamento' in final_df.columns:
        final_df['data_processamento'] = pd.to_datetime(final_df['data_processamento'])
        
    return final_df

# --- INTERFACE PRINCIPAL ---

st.title("📊 Monitor Inteligente: Diário Oficial de PE")
st.markdown("Dashboard de inteligência para monitoramento de Concursos, Pesquisa e Regulação.")

# Carregar dados
REPORTS_DIR = os.path.join(os.getcwd(), "relatorios")
df = load_data(REPORTS_DIR)

if df.empty:
    st.warning(f"⚠️ Nenhum relatório JSON encontrado na pasta: {REPORTS_DIR}")
    st.info("Execute o script 'diario_bot.py' primeiro para gerar dados.")
    st.stop()

# --- SIDEBAR (FILTROS) ---
st.sidebar.header("🔍 Filtros")

# Filtro de Impacto
impacto_options = df['impacto'].unique().tolist()
selected_impacto = st.sidebar.multiselect("Nível de Impacto", impacto_options, default=impacto_options)

# Filtro de Categoria
categoria_options = df['categoria'].unique().tolist()
selected_categoria = st.sidebar.multiselect("Categorias", categoria_options, default=categoria_options)

# Aplicar filtros
df_filtered = df[
    (df['impacto'].isin(selected_impacto)) &
    (df['categoria'].isin(selected_categoria))
]

# --- KPI CARDS ---
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Total de Menções", len(df_filtered))
with col2:
    concursos = len(df_filtered[df_filtered['categoria'] == 'CONCURSOS_SELECOES'])
    st.metric("Concursos/Seleções", concursos, delta_color="normal")
with col3:
    # Contagem de PDFs únicos processados
    arquivos = df_filtered['arquivo_origem'].nunique()
    st.metric("Diários Analisados", arquivos)
with col4:
    high_impact = len(df_filtered[df_filtered['impacto'] == 'ALTO'])
    st.metric("Alertas de Alto Impacto", high_impact, delta_color="inverse")

st.markdown("---")

# --- ABAS DE VISUALIZAÇÃO ---
tab1, tab2, tab3 = st.tabs(["📈 Visão Geral", "🎯 Oportunidades (Concursos)", "📝 Dados Detalhados"])

with tab1:
    col_chart1, col_chart2 = st.columns(2)
    
    with col_chart1:
        st.subheader("Ocorrências por Categoria")
        fig_cat = px.bar(df_filtered, x='categoria', color='impacto', 
                         color_discrete_map={'ALTO': '#FF4B4B', 'MEDIO': '#FFA15A', 'BAIXO': '#00CC96'},
                         title="Volume de Menções por Tema")
        st.plotly_chart(fig_cat, use_container_width=True)
        
    with col_chart2:
        st.subheader("Distribuição por Secretaria/Tópico")
        if 'topico_detectado' in df_filtered.columns:
            # Pegar top 10 tópicos para não poluir o gráfico
            top_topics = df_filtered['topico_detectado'].value_counts().nlargest(10).index
            df_topics = df_filtered[df_filtered['topico_detectado'].isin(top_topics)]
            
            fig_topic = px.pie(df_topics, names='topico_detectado', hole=0.4, 
                               title="Top 10 Secretarias/Órgãos Citados")
            st.plotly_chart(fig_topic, use_container_width=True)

with tab2:
    st.subheader("🚨 Alertas de Concursos e Processos Seletivos")
    
    # Filtrar apenas concursos
    df_concursos = df_filtered[df_filtered['categoria'] == 'CONCURSOS_SELECOES']
    
    if df_concursos.empty:
        st.success("Nenhuma menção a concursos nos filtros atuais.")
    else:
        for index, row in df_concursos.iterrows():
            with st.expander(f"{row['termo_encontrado'].upper()} - Pág. {row['pagina']} ({row['arquivo_origem']})"):
                st.markdown(f"**Tópico:** {row['topico_detectado']}")
                st.markdown(f"**Contexto:**")
                # Highlight da palavra chave no texto
                snippet = row['resumo_snippet']
                termo = row['termo_encontrado']
                snippet_highlight = snippet.replace(termo, f":red[**{termo}**]")
                st.markdown(f"> ...{snippet_highlight}...")

with tab3:
    st.subheader("Tabela de Dados Brutos")
    
    # Pesquisa textual na tabela
    search_term = st.text_input("Buscar termo específico dentro dos resultados:")
    
    if search_term:
        df_display = df_filtered[df_filtered['resumo_snippet'].str.contains(search_term, case=False, na=False)]
    else:
        df_display = df_filtered
        
    st.dataframe(
        df_display[['data_processamento', 'categoria', 'topico_detectado', 'termo_encontrado', 'pagina', 'resumo_snippet']],
        use_container_width=True,
        column_config={
            "resumo_snippet": st.column_config.TextColumn("Trecho do Texto", width="large"),
            "pagina": st.column_config.NumberColumn("Pág.", format="%d")
        }
    )
    
    # Botão de download
    csv = df_display.to_csv(index=False).encode('utf-8')
    st.download_button(
        "📥 Baixar Tabela Filtrada (CSV)",
        data=csv,
        file_name="dados_filtrados_doe.csv",
        mime="text/csv",
    )