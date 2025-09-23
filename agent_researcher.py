# ===== SEDANG MENGIMPOR agent_researcher.py =====

import os
from langchain.chat_models import ChatOpenAI
from langchain.agents import create_react_agent, AgentExecutor, Tool
from langchain.prompts import PromptTemplate
from tools.tools_researcher import query_site_from_db



def create_researcher_agent() -> AgentExecutor:
    print("🔍 Membuat Researcher Agent (Versi Spesialis)...")

    llm = ChatOpenAI(
        model="mistralai/mistral-small-3.2-24b-instruct",
        openai_api_key=os.getenv("OPENROUTER_API_KEY_MISTRAL"),
        openai_api_base="https://openrouter.ai/api/v1",
        temperature=0.2,
        max_retries=5 
    )

    tools = [
        Tool(
            name="SiteDatabaseQuery",
            func=query_site_from_db,
            description=(
                "Gunakan tool ini jika TUJUAN AKHIR pengguna adalah untuk mendapatkan "
                "DAFTAR NAMA SITE atau ID SITE berdasarkan nama site. Ini adalah tool utama untuk "
                "PENCARIAN site, bahkan jika pertanyaan menyertakan filter lokasi seperti 'di Kedungmundu' atau 'di Semarang'. "
                "Contoh pertanyaan yang cocok: "
                "'daftar nama site di purbalingga', "
                "'site id dari site purbalingga_mt', "
                "'apa id untuk site banjaran_purbalingga_tb', "
                "'nama site yang ada di banyumas' ,"
                "'site id 14PBG000'. "
            ),
             return_direct=True
        )
    ]

    researcher_prompt = PromptTemplate(
        input_variables=["input", "agent_scratchpad", "tools", "tool_names"],
        template="""
Anda adalah agen spesialis dalam pencarian informasi site. Tugas Anda adalah menjawab pertanyaan pengguna menggunakan tool yang tersedia berikut ini:

{tools}

📌 Tool ini digunakan untuk pencarian **daftar site**, **site ID berdasarkan nama**, atau **nama site berdasarkan ID**.

Contoh pertanyaan yang cocok:
- "daftar nama site di Purbalingga"
- "apa site ID dari purbalingga_mt"
- "site apa saja di Semarang"
- "site id 15YOG01?"
- "site 15SMN01?"
- "site bawang?"

GUNAKAN FORMAT DI BAWAH INI DENGAN SANGAT TELITI:

Pertanyaan: pertanyaan yang harus dijawab  
Thought: Aku harus memutuskan apakah akan menggunakan tool atau tidak untuk menjawab pertanyaan ini. Jika membutuhkan pencarian nama atau ID site, maka aku harus menggunakan tool.  
Action: nama tool yang akan digunakan, harus salah satu dari [{tool_names}]  
Action Input: Anda WAJIB menggunakan teks ASLI dan LENGKAP dari 'Pertanyaan' di atas. JANGAN MENERJEMAHKAN ATAU MENGUBAHNYA.

(Setelah tool berjalan, Anda akan melihat 'Observation')

Thought: Aku sekarang sudah mendapatkan informasi yang dibutuhkan dari tool dan tahu jawaban akhirnya.  
Final Answer: jawaban akhir untuk pengguna, berdasarkan informasi dari Observation.

⛔⛔⛔ PERINGATAN PENTING:
Setelah menulis `Action` dan `Action Input`, ANDA HARUS BERHENTI.  
❗JANGAN lanjut ke Thought atau Final Answer  
❗JANGAN tulis teks seperti "hasil akan ditampilkan setelah observation..."

✅ TULIS `Action` dan `Action Input` lalu BERHENTI.

Pertanyaan: {input}  
{agent_scratchpad}
"""
    )

   
    agent = create_react_agent(llm, tools, researcher_prompt)
    return AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=True,
        max_iterations=10,
        handle_parsing_errors=True
    )
