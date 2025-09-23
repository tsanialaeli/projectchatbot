from langchain.chat_models import ChatOpenAI
from langchain.agents import create_react_agent, AgentExecutor
from langchain.tools import Tool
from langchain.prompts import PromptTemplate
import os
from tools.tools_dokumen import unggah_dokumen, simpan_file

def create_dokumen_agent() -> AgentExecutor:
    print("📁 Membuat Dokumen Agent...")

    llm = ChatOpenAI(
        model="mistralai/mistral-small-3.2-24b-instruct",
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPENROUTER_API_KEY_MISTRAL"),
        temperature=0.3,
    )

    tools = [
        Tool(
            name="SimpanFile",
            func=lambda x: "✅ Dokumen berhasil disimpan.",
            description="Gunakan untuk menyimpan file dari pengguna. Contoh: 'simpan file notulensi ini', 'tolong simpan dokumen audit'.",
            return_direct=True 
        ),
        Tool(
            name="UnggahDokumen",
            func=unggah_dokumen,
            description="Gunakan jika pengguna ingin mengunggah file. Contoh: 'saya mau upload dokumen', 'unggah dokumen audit site'.",
            return_direct=True 
        ),
    ]

    prompt = PromptTemplate(
        input_variables=["input", "agent_scratchpad", "tools", "tool_names"],
        template="""
Anda adalah asisten digital untuk manajemen dokumen di PT Indosat. Tugas Anda adalah membantu menyimpan dan menampilkan file dokumen seperti notulensi, laporan, atau hasil audit dari pengguna.

Tools yang tersedia:
{tools}

📌 Panduan Penggunaan Tool:
- **SimpanFile** → Jika pengguna telah mengunggah file dan ingin menyimpannya.
- **UnggahDokumen** → Jika pengguna ingin upload file baru.

FORMAT WAJIB:
Pertanyaan: (isi pertanyaan asli dari pengguna)
Thought: Apakah perlu menggunakan tool? Jika ya, tentukan tool yang tepat.
Action: (pilih salah satu dari [{tool_names}])
Action Input: (gunakan teks asli dari pengguna tanpa diterjemahkan atau diubah)

(Setelah tool dijalankan → akan muncul Observation)

Thought: Tool sudah memberikan hasil. Sekarang saya bisa menjawab pengguna.
Final Answer: Jawaban akhir kepada pengguna berdasarkan hasil dari Observation.

⛔ Jangan langsung beri Final Answer sebelum ada hasil dari tool.
⛔ Jangan tulis Action dan Final Answer sekaligus.
✅ Pastikan Action Input = teks asli pertanyaan.

💡 Contoh valid:
Pertanyaan: tolong simpan dokumen audit minggu ini
Thought: Pengguna ingin menyimpan file, maka saya gunakan tool SimpanFile
Action: SimpanFile
Action Input: tolong simpan dokumen audit minggu ini

---

💡 Contoh valid:
Pertanyaan: saya mau upload dokumen audit
Thought: Pengguna ingin mengunggah file.
Action: UnggahDokumen
Action Input: saya mau upload dokumen audit

---

Pertanyaan: {input}
{agent_scratchpad}
"""
    )

    agent = create_react_agent(llm=llm, tools=tools, prompt=prompt)

    return AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=True,
        return_intermediate_steps=False,
        handle_parsing_errors=True,
        max_iterations=5,
        early_stopping_method="force"
    )
