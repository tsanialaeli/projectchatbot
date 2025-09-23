# file: main.py
print("===== SEDANG MENJALANKAN main.py =====")
from dotenv import load_dotenv
from gradio_app import build_gradio_app

# Load env duluan
load_dotenv()

# =================== Import Semua Agent ===================
from agents.agent_supervisor import create_supervisor_agent
from agents.agent_researcher import create_researcher_agent
from agents.agent_notulensi_teks import create_notulensi_teks_agent
from agents.agent_dokumen import create_dokumen_agent
from agents.agent_rag import create_rag_agent


# =================== Import Pendukung ===================
from tools.tools_researcher import load_all_site_names

# =================== Inisialisasi Semua Agent ===================
print("🚀 Menginisialisasi semua agent...")
researcher = create_researcher_agent()
notulensi_teks = create_notulensi_teks_agent()
dokumen = create_dokumen_agent()
rag = create_rag_agent()


supervisor_agent = create_supervisor_agent(
    researcher_agent=researcher,
    notulensi_teks_agent=notulensi_teks,
    dokumen_agent=dokumen,
    rag_agent=rag
)
print("✅ Semua agent siap digunakan.")

# =================== Load Data Referensi ===================
load_all_site_names()


# =================== Jalankan Gradio App ===================

if __name__ == "__main__":
    app = build_gradio_app(supervisor_agent)
    app.queue().launch(server_name="127.0.0.1", server_port=7861)