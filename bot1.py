import os
import time
import json
import pandas as pd
import pdfplumber
import schedule
from datetime import datetime
from unidecode import unidecode

# --- IMPORTS DO SELENIUM (Nativo, sem gerenciador externo) ---
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
# Nota: Removemos o 'webdriver_manager' e o 'Service' para evitar conflito de cache

class DOEProcessor:
    def __init__(self):
        self.base_url = "https://diariooficial.cepe.com.br/diariooficialweb/#/home?diario=MQ%3D%3D"
        self.download_dir = os.path.join(os.getcwd(), "downloads")
        self.reports_dir = os.path.join(os.getcwd(), "relatorios")
        
        os.makedirs(self.download_dir, exist_ok=True)
        os.makedirs(self.reports_dir, exist_ok=True)

        # SEU DICIONÁRIO (Com Alison Hideo)
        self.keywords = {
            "MONITORAMENTO_PESSOAL": {
                "termos": ["SEU NOME"],
                "impacto": "ALTO"
            },
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
                "impacto": "BAIXO"
            }
        }

    def setup_driver(self):
        """Configura o navegador Chrome usando o modo NATIVO do Selenium 4.10+"""
        chrome_options = Options()
        
        # --- ATENÇÃO: COMENTE/DESCOMENTE PARA VER O NAVEGADOR ---
        # chrome_options.add_argument("--headless=new") # Roda em background (invisível)
        
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")
        
        prefs = {
            "download.default_directory": self.download_dir,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "plugins.always_open_pdf_externally": True
        }
        chrome_options.add_experimental_option("prefs", prefs)
        
        # SOLUÇÃO FINAL PARA O ERRO DE VERSÃO:
        # Não passamos 'service'. O Selenium detecta o Chrome 143 instalado e baixa 
        # o driver correto automaticamente em tempo de execução.
        return webdriver.Chrome(options=chrome_options)

    def fetch_pdf_by_date(self, data_str):
        print(f"[{datetime.now()}] Tentando buscar edição de: {data_str}...")
        driver = self.setup_driver()
        
        try:
            driver.get(self.base_url)
            wait = WebDriverWait(driver, 20)
            
            # --- LÓGICA DE BUSCA POR DATA ---
            print("Procurando campo de data...")
            try:
                # Tenta achar o input de data
                # OBS: Em alguns frameworks, o input pode ser do type='text' com máscara.
                # Vamos tentar ser abrangentes no XPATH.
                date_input = wait.until(EC.element_to_be_clickable((By.XPATH, "//input[contains(@placeholder, 'Data') or @type='date' or contains(@class, 'datepicker')]")))
                
                # Limpa e digita a data
                date_input.click()
                # Truque para limpar campo com máscara:
                date_input.send_keys(Keys.CONTROL + "a")
                date_input.send_keys(Keys.DELETE)
                
                # Digita a data
                date_input.send_keys(data_str)
                time.sleep(1) # Pequena pausa visual
                date_input.send_keys(Keys.ENTER)
                
                print(f"Data {data_str} inserida. Aguardando atualização...")
                time.sleep(5) 
                
            except Exception as e:
                print(f"⚠️ Aviso: Não consegui filtrar a data automaticamente. Baixando edição padrão. Erro: {str(e)[:50]}...")

            # Busca botão de download
            print("Tentando clicar no download...")
            download_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button.btn-download-pdf, a[href$='.pdf'], .fa-download")))
            download_btn.click()
            
            print("Download iniciado...")
            time.sleep(15) 
            
            # Renomeia o arquivo baixado
            files = [os.path.join(self.download_dir, f) for f in os.listdir(self.download_dir) if f.endswith('.pdf')]
            if not files: return None
            
            latest_file = max(files, key=os.path.getctime)
            new_name = os.path.join(self.download_dir, f"DOE_{data_str.replace('/','-')}.pdf")
            
            if os.path.exists(new_name):
                os.remove(new_name)
            os.rename(latest_file, new_name)
            
            return new_name

        except Exception as e:
            print(f"Erro ao processar data {data_str}: {e}")
            return None
        finally:
            driver.quit()

    def clean_text(self, text):
        if not text: return ""
        return " ".join(text.split())

    def analyze_pdf(self, pdf_path):
        print(f"Analisando: {os.path.basename(pdf_path)}")
        extracted_data = []
        concursos_data = []
        
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                text = page.extract_text()
                if not text: continue
                
                lines = text.split('\n')
                topico_estimado = "GERAL"
                for line in lines[:5]:
                    if line.isupper() and len(line) > 5:
                        topico_estimado = line
                        break
                
                text_clean = self.clean_text(text)
                text_lower = text_clean.lower()
                
                for categoria, info in self.keywords.items():
                    for termo in info['termos']:
                        if termo in text_lower:
                            start_idx = text_lower.find(termo)
                            start_ctx = max(0, start_idx - 100)
                            end_ctx = min(len(text_clean), start_idx + 200)
                            snippet = text_clean[start_ctx:end_ctx]
                            
                            entry = {
                                "arquivo": os.path.basename(pdf_path),
                                "pagina": i + 1,
                                "topico_detectado": topico_estimado,
                                "categoria": categoria,
                                "termo_encontrado": termo,
                                "impacto": info['impacto'],
                                "resumo_snippet": snippet.strip() + "...",
                                "data_processamento": datetime.now().strftime("%Y-%m-%d")
                            }
                            
                            extracted_data.append(entry)
                            if info['impacto'] == "ALTO":
                                concursos_data.append(entry)
                            break 
        return extracted_data, concursos_data

    def generate_reports(self, data, concursos):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        if data:
            json_path = os.path.join(self.reports_dir, f"relatorio_multiplo_{timestamp}.json")
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            print(f"✅ Relatório salvo em: {json_path}")

    def process_dates(self, lista_datas):
        all_findings = []
        all_concursos = []
        
        for data in lista_datas:
            print(f"\n=== Processando dia {data} ===")
            pdf_path = self.fetch_pdf_by_date(data)
            
            if pdf_path and os.path.exists(pdf_path):
                findings, concursos = self.analyze_pdf(pdf_path)
                all_findings.extend(findings)
                all_concursos.extend(concursos)
            else:
                print(f"❌ Não foi possível obter o PDF de {data}")
        
        if all_findings:
            self.generate_reports(all_findings, all_concursos)
        else:
            print("Nenhum termo encontrado nas datas analisadas.")

if __name__ == "__main__":
    bot = DOEProcessor()
    
    # DATAS PARA TESTAR (Janeiro de 2026, conforme sua configuração)
    # Certifique-se que estas datas existem no site
    datas = ["02/01/2025", "03/02/2025", "03/03/2025", "03/04/2025", "03/05/2025"] 
    
    bot.process_dates(datas)
