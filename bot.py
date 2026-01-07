import os
import time
import json
import re
import pandas as pd
import pdfplumber
import schedule
from datetime import datetime
from unidecode import unidecode

# Automação Web
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

class DOEProcessor:
    def __init__(self):
        self.base_url = "https://diariooficial.cepe.com.br/diariooficialweb/#/home?diario=MQ%3D%3D"
        self.download_dir = os.path.join(os.getcwd(), "downloads")
        self.reports_dir = os.path.join(os.getcwd(), "relatorios")
        
        # Cria diretórios se não existirem
        os.makedirs(self.download_dir, exist_ok=True)
        os.makedirs(self.reports_dir, exist_ok=True)

        # DICIONÁRIO DE PALAVRAS-CHAVE E PESOS
        # Estrutura: 'Categoria': {'termos': [], 'impacto': 'Alto/Médio/Baixo'}
        self.keywords = {
            "CONCURSOS_SELECOES": {
                "termos": ["concurso público", "processo seletivo", "nomeação", "homologação", "edital de abertura", "convocação"],
                "impacto": "ALTO"
            },
            "SAUDE_BIOTEC": {
                "termos": ["secretaria de saúde", "biotecnologia", "medicamentos", "insumos", "laboratório", "vacinação", "epidemiológica"],
                "impacto": "MEDIO"
            },
            "EDUCACAO_PESQUISA": {
                "termos": ["fapesq", "bolsa de pesquisa", "mestrado", "doutorado", "universidade de pernambuco", "educação básica"],
                "impacto": "MEDIO"
            },
            "REGULACAO_LEIS": {
                "termos": ["decreto nº", "lei nº", "portaria nº", "resolução"],
                "impacto": "BAIXO" # Baixo volume de alerta, mas importante
            }
        }

    def setup_driver(self):
        """Configura o navegador Chrome em modo Headless (sem interface visual)"""
        chrome_options = Options()
        chrome_options.add_argument("--headless")  # Executa em background
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        
        # Configura download automático
        prefs = {
            "download.default_directory": self.download_dir,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "plugins.always_open_pdf_externally": True
        }
        chrome_options.add_experimental_option("prefs", prefs)
        
        service = Service(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=chrome_options)

    def fetch_latest_pdf(self):
        """Acessa o site e baixa o último PDF disponível"""
        print(f"[{datetime.now()}] Iniciando acesso ao DOE-PE...")
        driver = self.setup_driver()
        
        try:
            driver.get(self.base_url)
            
            # Aguarda o carregamento da lista de diários (ajuste o seletor conforme necessidade do site SPA)
            # Nota: Sites SPA podem mudar classes dinamicamente. Buscamos por texto ou estrutura.
            wait = WebDriverWait(driver, 20)
            
            # Tentativa de localizar o botão de download/visualização do primeiro item da lista
            # Como não tenho acesso DOM em tempo real, simulo a busca pelo botão de PDF da edição mais recente
            print("Buscando edição mais recente...")
            
            # Exemplo genérico de seletor para o primeiro item de download
            # Ajuste fino pode ser necessário inspecionando o site real
            download_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button.btn-download-pdf, a[href$='.pdf']")))
            download_btn.click()
            
            print("Download iniciado. Aguardando conclusão...")
            time.sleep(15) # Espera simples para download concluir
            
            # Retorna o arquivo mais recente na pasta
            files = [os.path.join(self.download_dir, f) for f in os.listdir(self.download_dir) if f.endswith('.pdf')]
            if not files:
                return None
            latest_file = max(files, key=os.path.getctime)
            return latest_file

        except Exception as e:
            print(f"Erro ao baixar PDF (verifique seletores): {e}")
            # Fallback para teste: se tiver um PDF na pasta, usa ele
            files = [os.path.join(self.download_dir, f) for f in os.listdir(self.download_dir) if f.endswith('.pdf')]
            if files:
                print("Usando arquivo local existente para continuidade.")
                return max(files, key=os.path.getctime)
            return None
        finally:
            driver.quit()

    def clean_text(self, text):
        """Limpeza básica de texto para análise"""
        if not text: return ""
        return " ".join(text.split())

    def analyze_pdf(self, pdf_path):
        """Lê o PDF e extrai informações baseadas no dicionário"""
        print(f"Processando arquivo: {os.path.basename(pdf_path)}")
        
        extracted_data = []
        concursos_data = []
        
        with pdfplumber.open(pdf_path) as pdf:
            total_pages = len(pdf.pages)
            print(f"Total de páginas: {total_pages}")

            for i, page in enumerate(pdf.pages):
                text = page.extract_text()
                if not text: continue
                
                # Tenta identificar o Tópico/Secretaria pelo cabeçalho (Texto em Uppercase no topo)
                lines = text.split('\n')
                topico_estimado = "GERAL"
                for line in lines[:5]: # Olha as 5 primeiras linhas
                    if line.isupper() and len(line) > 5:
                        topico_estimado = line
                        break
                
                # Busca por palavras-chave
                text_clean = self.clean_text(text)
                text_lower = text_clean.lower()
                
                found_categories = []
                impact_level = "BAIXO"
                
                for categoria, info in self.keywords.items():
                    for termo in info['termos']:
                        if termo in text_lower:
                            found_categories.append(categoria)
                            
                            # Define contexto (snippet) - 100 caracteres antes e depois
                            start_idx = text_lower.find(termo)
                            start_ctx = max(0, start_idx - 100)
                            end_ctx = min(len(text_clean), start_idx + 200)
                            snippet = text_clean[start_ctx:end_ctx]
                            
                            entry = {
                                "pagina": i + 1,
                                "topico_detectado": topico_estimado,
                                "categoria": categoria,
                                "termo_encontrado": termo,
                                "impacto": info['impacto'],
                                "resumo_snippet": snippet.strip() + "...",
                                "data_processamento": datetime.now().strftime("%Y-%m-%d")
                            }
                            
                            extracted_data.append(entry)
                            
                            # Lógica de Impacto
                            if info['impacto'] == "ALTO":
                                impact_level = "ALTO"
                                concursos_data.append(entry)
                            elif info['impacto'] == "MEDIO" and impact_level != "ALTO":
                                impact_level = "MEDIO"
                            
                            # Break para não repetir o mesmo termo mil vezes na mesma página
                            break 

        return extracted_data, concursos_data

    def generate_reports(self, data, concursos, filename_base):
        """Gera JSON e CSV dos resultados"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        
        # 1. Relatório Geral (JSON Estruturado)
        json_path = os.path.join(self.reports_dir, f"relatorio_geral_{timestamp}.json")
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
            
        # 2. Relatório Específico de Concursos (CSV para Excel)
        if concursos:
            df_concursos = pd.DataFrame(concursos)
            csv_path = os.path.join(self.reports_dir, f"ALERTA_CONCURSOS_{timestamp}.csv")
            df_concursos.to_csv(csv_path, index=False, sep=';', encoding='utf-8-sig')
            print(f"🔥 ALERTA: {len(concursos)} menções a concursos/seleções encontradas!")
        
        # 3. Resumo por Tópicos (Agrupamento)
        df = pd.DataFrame(data)
        if not df.empty:
            summary = df.groupby(['topico_detectado', 'categoria'])['pagina'].count().reset_index()
            txt_path = os.path.join(self.reports_dir, f"resumo_topicos_{timestamp}.txt")
            with open(txt_path, 'w', encoding='utf-8') as f:
                f.write("=== RESUMO DO DIÁRIO OFICIAL ===\n\n")
                for index, row in summary.iterrows():
                    f.write(f"[{row['categoria']}] {row['topico_detectado']}: {row['pagina']} ocorrências\n")

        print(f"✅ Relatórios gerados na pasta: {self.reports_dir}")

    def run_pipeline(self):
        """Orquestrador principal"""
        print("\n=== INICIANDO PIPELINE DE ANÁLISE DO DOE ===")
        
        # 1. Baixar
        pdf_path = self.fetch_latest_pdf()
        
        if pdf_path and os.path.exists(pdf_path):
            # 2. Analisar
            all_data, concursos_only = self.analyze_pdf(pdf_path)
            
            # 3. Gerar Relatórios
            if all_data:
                self.generate_reports(all_data, concursos_only, os.path.basename(pdf_path))
            else:
                print("Nenhuma palavra-chave relevante encontrada hoje.")
                
            # Limpeza (Opcional: remover PDF após análise)
            # os.remove(pdf_path)
        else:
            print("Falha ao obter o arquivo PDF.")
        
        print("=== FIM DO PROCESSO ===\n")

# --- AGENDAMENTO ---
def job():
    bot = DOEProcessor()
    bot.run_pipeline()

if __name__ == "__main__":
    # Modo Imediato (para teste agora)
    job()

    # Modo Agendado (Descomente abaixo para rodar todo dia às 06:00)
    # print("Agendamento ativado: Execução diária às 06:00")
    # schedule.every().day.at("06:00").do(job)
    # while True:
    #     schedule.run_pending()
    #     time.sleep(60)