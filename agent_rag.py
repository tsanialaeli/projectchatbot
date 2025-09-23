import os
from langchain.chat_models import ChatOpenAI
from langchain.agents import AgentExecutor, Tool, create_react_agent
from langchain.prompts import PromptTemplate
from tools.tools_rag import jawab_pertanyaan_pgvector

def create_rag_agent() -> AgentExecutor:
    print("🔍 Membuat RAG Agent...")

    llm = ChatOpenAI(
        model="mistralai/mistral-small-3.2-24b-instruct",
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPENROUTER_API_KEY_MISTRAL"),
        temperature=0.3,
    )

    tools = [
    Tool(
        name="JawabRAG",
        func=jawab_pertanyaan_pgvector,
        description=(
            "Gunakan **jika** input adalah pertanyaan (mengandung tanda tanya) atau permintaan informasi "
            "yang membutuhkan referensi dokumen seperti gangguan, status site, atau masalah yang terjadi. "
            "Juga gunakan jika kalimat mengandung kata perintah seperti 'sebutkan', 'berikan', 'daftar', "
            "'tunjukkan', atau bentuk permintaan informasi umum lainnya."
        ),
        return_direct=False
    )
]

    prompt = PromptTemplate(
        input_variables=["input", "agent_scratchpad", "tools", "tool_names"],
        template="""
Anda adalah asisten teknis yang menjawab pertanyaan berdasarkan dokumen notulensi.

Gunakan tools ini bila perlu:
{tools}

Pertanyaan: pertanyaan yang harus dijawab  
Thought: Aku harus memutuskan apakah akan menggunakan tool atau tidak untuk menjawab pertanyaan ini. Jika membutuhkan pencarian nama atau ID site, maka aku harus menggunakan tool.  
Action: nama tool yang akan digunakan, harus salah satu dari [{tool_names}]  
Action Input: Anda WAJIB menggunakan teks ASLI dan LENGKAP dari 'Pertanyaan' di atas. JANGAN MENERJEMAHKAN ATAU MENGUBAHNYA.

(Setelah tool berjalan, Anda akan melihat 'Observation')

Thought: Aku sekarang sudah mendapatkan informasi yang dibutuhkan dari tool dan tahu jawaban akhirnya.  
Final Answer: jawaban akhir untuk pengguna, berdasarkan informasi dari Observation.

FORMAT WAJIB:
Pertanyaan: {input}
Thought: Saya mempertimbangkan apakah butuh referensi dokumen.
Action: (nama tool)
Action Input: (pertanyaan lengkap)

Observation: (hasil tool)
Thought: Saya sudah tahu jawabannya.
Final Answer: (jawaban akhir untuk user)


🧠 Aturan Penggunaan Tool JawabRAG:

Gunakan **JawabRAG** jika pengguna menanyakan atau meminta informasi seperti:
- Gangguan atau masalah di site tertentu
- Apakah suatu site sudah diperbaiki
- Site mana yang mengalami masalah
- Apa saja kendala di lokasi tertentu
- Sebutkan kendala site
- Menggunakan kata perintah seperti "sebutkan", "berikan", "tunjukkan", "daftar" yang merujuk pada informasi dokumen

📌 Panduan Keputusan:
1. Jika input berisi pertanyaan (ADA tanda tanya "?") → gunakan tool JawabRAG.
2. Jika input mengandung kata perintah seperti "sebutkan", "berikan", "tunjukkan", "daftar" → gunakan tool JawabRAG.
3. Jika input adalah kalimat pernyataan tanpa tanda tanya dan tidak mengandung kata perintah → anggap itu catatan notulensi, JANGAN gunakan tool.
4. Gunakan JawabRAG hanya sesuai nama site yang disebutkan, jangan ambil isi catatan site lain.
5. Jika terdapat lebih dari satu masalah pada site tersebut, tampilkan semuanya dalam format daftar:
   - Baterai soak
   - Tegangan PLN rendah
   - Interferensi

⛔ Larangan:
- JANGAN pakai tool JawabRAG jika tidak mengandung tanda tanya atau kata perintah di atas.
- JANGAN pakai tool JawabRAG jika input adalah catatan seperti "antena rusak", "sinyal hilang", "sinyal rusak", dll.

{agent_scratchpad}
"""
    )

    agent = create_react_agent(llm=llm, tools=tools, prompt=prompt)

    return AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=True,
        handle_parsing_errors="auto",
        return_intermediate_steps=False,
        max_iterations=5,
        early_stopping_method="force"
    )
