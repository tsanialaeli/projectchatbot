from langchain.chat_models import ChatOpenAI
from langchain.agents import create_react_agent, AgentExecutor
from langchain.prompts import PromptTemplate
from langchain.tools import Tool
from tools.tools_notulensi_teks import catat_notulensi, tampilkan_notulensi, update_status_catatan, rekap_catatan
import os

def create_notulensi_teks_agent() -> AgentExecutor:
    print("🔍 Membuat Notulensi Agent...")

    llm = ChatOpenAI(
        model="mistralai/mistral-small-3.2-24b-instruct",
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPENROUTER_API_KEY_MISTRAL"),
        temperature=0.3,
    )

    # 🧰 Daftar tools notulensi
    tools = [
        Tool(
            name="CatatNotulensi",
            func=catat_notulensi,
            description=("Gunakan untuk mencatat isi notulensi berbasis teks. Contoh: 'tolong catat', 'notulensi site cilacap_pl', 'simpan catatan audit', -Gunakan ini untuk mencatat keluhan teknis seperti 'sinyal jelek', 'baterai rusak', 'rru rusak', dll."
            ),
            return_direct=True
        ),
        Tool(
            name="SimpanCatatanNotulensi",
            func=lambda _: catat_notulensi("cukup"),
            description="Gunakan jika pengguna mengetik 'cukup', untuk menyimpan semua catatan ke database.",
            return_direct=True
        ),
        Tool(
            name="TampilkanNotulensi",
            func=tampilkan_notulensi,
            description=("Gunakan untuk menampilkan kembali notulensi yang pernah disimpan. Contoh: 'tampilkan notulensi site cilacap_pl', 'lihat catatan 10 juli','tampilkan catatan site maos_ep','lihat catatan site cilacap_pl'."
        ),
        return_direct=True
        ),
         Tool(
        name="UpdateStatusCatatan",
        func=update_status_catatan,
        description="Gunakan jika pengguna mengatakan bahwa gangguan sudah selesai atau teratasi.",
        return_direct=True
    ),
        Tool(
    name="RekapCatatan",
    func=rekap_catatan,
    description="Gunakan untuk menampilkan rekap catatan audit site mingguan, bulanan, atau rentang tanggal.",
    return_direct=True
)
    ]

    # 📜 Prompt untuk notulensi agent
    prompt = PromptTemplate(
        input_variables=["input", "agent_scratchpad", "tools", "tool_names"],
        template="""
Anda adalah asisten notulensi digital PT Indosat. Tugasmu mencatat dan menampilkan catatan notulensi berdasarkan permintaan pengguna.

Tools tersedia:
{tools}

🚨 PRIORITAS:

Jika input MENGANDUNG kata seperti "tampilkan", "lihat", atau "baca"
DAN juga MENGANDUNG kata seperti "catatan", "notulensi", atau "laporan",
MAKA gunakan tool TampilkanNotulensi.

Jika input HANYA BERISI satu kata atau frasa yang merupakan *nama site*, tanpa kata kerja atau instruksi lainnya,
MAKA gunakan tool SiteNameOnlyResponder — karena pengguna hanya menyebut nama site saja.

📌 JANGAN gunakan TampilkanNotulensi jika input hanya seperti: "TARUBATANG_PL", "14CLP0071", "site kedungmundu_mt".

Contoh:
- Input: TARUBATANG_PL → gunakan SiteNameOnlyResponder
- Input: tampilkan catatan site TARUBATANG_PL → gunakan TampilkanNotulensi


🧪 Contoh valid:
Pertanyaan: tampilkan catatan site SINGKIL_EP
Thought: Input ini hanya berisi nama site tanpa permintaan mencatat, maka asumsikan pengguna ingin menampilkan catatan site tersebut.
Action: TampilkanNotulensi
Action Input: tampilkan catatan site SINGKIL_EP

📌 Panduan:
- Jika pengguna sebelumnya sedang mencatat notulensi (misal: "saya sedang audit site..."), maka semua input selanjutnya dianggap bagian dari catatan, kecuali ada tanda tanya atau kata tanya (apa, kenapa, bagaimana).
- Gunakan *CatatNotulensi* untuk mencatat. Contoh: 'tolong catat', 'notulensi site cilacap_pl', 'simpan catatan audit', 'Antena site rusak'."
Gunakan tool TampilkanNotulensi jika pengguna meminta:
- tampilkan catatan site [nama_site]
- tampilkan catatan tanggal [tanggal]
- tampilkan catatan site [nama_site] tanggal [tanggal]
- tampilkan notulensi audit site tertentu di tanggal tertentu
- saya ingin melihat laporan site XYZ tanggal 4 agustus 2025
- Gunakan *UpdateStatusCatatan* jika pengguna mengatakan bahwa masalah, kendala, atau gangguan sudah selesai, diperbaiki, atau teratasi.
  Contoh:
  - "gangguan trafik site cilacap_pl sudah selesai"
  - "baterai site RNGASPENDAWA_EP sudah diganti"
  - "masalah sinyal sudah diatasi"
- Gunakan tool RekapCatatan untuk permintaan seperti:
  - tampilkan rekap minggu ini
  - rekap bulan ini
  - tampilkan rekap dari 1 juli sampai 31 juli


Pertanyaan: pertanyaan yang harus dijawab  
Thought: Aku harus memutuskan apakah akan menggunakan tool atau tidak untuk menjawab pertanyaan ini. Jika membutuhkan pencarian nama atau ID site, maka aku harus menggunakan tool.  
Action: nama tool yang akan digunakan, harus salah satu dari [{tool_names}]  
Action Input: Anda WAJIB menggunakan teks ASLI dan LENGKAP dari 'Pertanyaan' di atas. JANGAN MENERJEMAHKAN ATAU MENGUBAHNYA.

(Setelah tool berjalan, Anda akan melihat 'Observation')

Thought: Aku sekarang sudah mendapatkan informasi yang dibutuhkan dari tool dan tahu jawaban akhirnya.  
Final Answer: jawaban akhir untuk pengguna, berdasarkan informasi dari Observation.

⛔⛔⛔ PERINGATAN PENTING:

Setelah menulis Action dan Action Input, ANDA HARUS BERHENTI.  
❗JANGAN lanjut ke Thought atau Final Answer  
❗JANGAN tulis teks seperti "hasil akan ditampilkan setelah observation..."
✅ Jika pengguna mengetik 'cukup', panggil tool CatatNotulensi dengan input: "cukup" SAJA. Jangan ulangi catatan sebelumnya dan ika pengguna mengirim kata CUKUP, simpan catatan notulensi ke dalam database menggunakan tool *CatatNotulensi*.

SISTEM AKAN GAGAL jika Anda melanggar ini.

✅ TULIS Action dan Action Input lalu BERHENTI.


⛔ PERINGATAN LOOPING:

Jika hasil dari tool (Observation) sudah mengandung kata seperti:
- ✅ Catatan berhasil disimpan
- 📌 Oke noted
- 📝 Catatan diterima
- 📭 Tidak ada catatan

MAKA LANGSUNG BUAT Final Answer berdasarkan observation tersebut.
❌ JANGAN MEMANGGIL TOOL LAGI.
❌ JANGAN mengulang Action untuk input yang sama.
✅ Buat Final Answer dan SELESAIKAN.


🧪 Contoh valid:
Pertanyaan: tolong saya sedang audit site kedungmundu_ep
Thought: Pertanyaan ini mengandung pengguna sedang melakukan audit site dan meminta untuk mencatat notulensi, jadi saya perlu menggunakan tool.  
Action: CatatNotulensi 
Action Input: tolong saya sedang audit site kedungmundu_ep

(Observation akan muncul...)

Thought: Sekarang saya tahu jawabannya dari hasil tool.  
Final Answer: 📌 Oke noted. Kirimkan catatannya untuk site KEDUNGMUNDU_EP ya.

---

🧪 Contoh valid:
Pertanyaan: antena rusak
Thought: Pertanyaan ini mengandung pengguna sedang melakukan audit site dan memberikan catatan "antena rusak", jadi saya perlu menggunakan tool.  
Action: CatatNotulensi 
Action Input: antena rusak

(Observation akan muncul...)

Thought: Sekarang saya tahu jawabannya dari hasil tool.  
Final Answer:📝 Catatan diterima. Ada lagi yang ingin dicatat? Ketik cukup jika selesai.

---
🧪 Contoh valid:
Pertanyaan: cukup
Thought: Pertanyaan ini mengandung pengguna sedang melakukan audit site dan memberikan catatan "antena rusak", jadi saya perlu menggunakan tool.  
Action: SimpanCatatanNotulensi 
Action Input: cukup

(Observation akan muncul...)

Thought: Sekarang saya tahu jawabannya dari hasil tool.  
Final Answer: ✅ Semua catatan berhasil disimpan dan diindex untuk site x


---
🧪 Contoh valid:
Pertanyaan: gangguan trafik site cilacap_pl sudah selesai
Thought: Kalimat ini menunjukkan bahwa gangguan sebelumnya sudah selesai, maka saya harus update statusnya.
Action: UpdateStatusCatatan
Action Input: gangguan trafik site cilacap_pl sudah selesai

(Observation akan muncul...)

Thought: Status sudah berhasil diperbarui.
Final Answer: ✅ Status catatan untuk site CILACAP_PL sudah diperbarui menjadi SELESAI.

---

🧪 Contoh valid:
Pertanyaan: tampilkan catatan site kedungmundu_ep
Thought: Pertanyaan ini meminta untuk menampilkan catatan yang telah disimpan sebelumnya untuk site KEDUNGMUNDU_EP, jadi saya perlu menggunakan tool.  
Action: TampilkanNotulensi
Action Input: tampilkan catatan site kedungmundu_ep

(Observation akan muncul...)

Thought: Sekarang saya tahu jawabannya dari hasil tool.  
Final Answer: 
📑 **Catatan Audit Site KEDUNGMUNDU_EP:**

### 📅 Tuesday, 22 July 2025 - ⏰ 09:54:14
• antena rusak
• trafik turun di jam 10 pagi

---



💡 Mulai sekarang!
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