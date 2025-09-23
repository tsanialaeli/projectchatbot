print("===== SEDANG MENGIMPOR agent_supervisor.py =====")
import os
from langchain.chat_models import ChatOpenAI
from langchain.agents import AgentExecutor, Tool, create_react_agent
from langchain.prompts import PromptTemplate
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.chat_history import BaseChatMessageHistory
from pydantic import BaseModel, Field
from typing import List
from langchain_core.messages import BaseMessage
from langchain_core.runnables import RunnableLambda


# ==== DEFINE IN-MEMORY HISTORY ====
class InMemoryHistory(BaseChatMessageHistory, BaseModel):
    messages: List[BaseMessage] = Field(default_factory=list)
    def add_messages(self, messages: List[BaseMessage]) -> None:
        self.messages.extend(messages)
    def clear(self) -> None:
        self.messages = []

# ==== GLOBAL STORE UNTUK SETIAP SESSION ====
store = {}

def get_session_history(config) -> BaseChatMessageHistory:
    if isinstance(config, dict):
        session_id = config.get("configurable", {}).get("session_id", "default")
    elif isinstance(config, str):
        # fallback kalau config dikirim sebagai string
        session_id = config
    else:
        session_id = "default"

    if session_id not in store:
        print(f"🧠 Membuat session baru: {session_id}")
        store[session_id] = InMemoryHistory()
    else:
        print(f"🧠 Memuat session yang sudah ada: {session_id}")

    print(f"🧾 Isi memory untuk {session_id}:")
    for msg in store[session_id].messages:
        print(f"  - {msg.type.upper()}: {msg.content}")

    return store[session_id]


print("📥 Mengimpor semua agent...")
from agents.agent_researcher import create_researcher_agent
from tools.tools_greeting import handle_greeting
from agents.agent_notulensi_teks import create_notulensi_teks_agent
from agents.agent_dokumen import create_dokumen_agent
from agents.agent_rag import create_rag_agent
from tools.tools_notulensi_teks import catat_notulensi



def create_supervisor_agent(
    researcher_agent: AgentExecutor,
    notulensi_teks_agent: AgentExecutor,
    dokumen_agent: AgentExecutor,
    rag_agent: AgentExecutor
) -> AgentExecutor:
    print("👔 Membuat Supervisor Agent...")

    print("📡 Menyiapkan LLM untuk supervisor...")
    llm = ChatOpenAI(
        model="mistralai/mistral-small-3.2-24b-instruct",
        openai_api_base="https://openrouter.ai/api/v1",
        openai_api_key=os.getenv("OPENROUTER_API_KEY_MISTRAL"),
        temperature=0.2,
        max_retries=5
    )


    tools =[
        Tool(
            name="SiteResearcher",
            func=lambda action_input: researcher_agent.invoke({"input": str(action_input)}),
            description=(
                "Gunakan tool ini jika TUJUAN AKHIR pengguna adalah untuk mendapatkan "
                "DAFTAR NAMA SITE atau ID SITE berdasarkan nama site. Ini adalah tool utama untuk "
                "PENCARIAN site, bahkan jika pertanyaan menyertakan filter lokasi seperti 'di Kedungmundu' atau 'di Semarang'. "
                "Contoh pertanyaan yang cocok: "
                "'daftar nama site di purbalingga', "
                "'site id dari site purbalingga_mt', "
                "'apa id untuk site banjaran_purbalingga_tb', "
                "'nama site yang ada di banyumas'."
            ),
             return_direct=True

        ),
        Tool(
            name="GreetingAndChat",
            func=lambda action_input, config=None: handle_greeting(
            action_input,
            session_id=config.get("configurable", {}).get("session_id", "default")
            ),
            description="Gunakan tool ini jika pengguna hanya menyapa (seperti 'halo', 'hai') atau mengucapkan terima kasih."
        ),
        # ✅ Tool baru untuk agent info site
        Tool(
            name="SiteNameOnlyResponder",
            func=lambda action_input: f"Apa yang ingin kamu ketahui tentang site {action_input.strip()}?",
            description=
            ("Gunakan ini HANYA jika pengguna hanya menyebutkan nama site saja tanpa tanda tanya, TANPA menyebut kata seperti 'traffic', 'grafik', 'power', 'user', atau permintaan lainnya."
        " Contoh input valid: '14BAG0123', 'site kedungmundu_mt'."
        " Jangan gunakan tool ini jika pengguna menyebut metrik atau rentang tanggal."
        " Jangan gunakan tool ini jika pengguna menyebut site 14PBG000?, site 15YOG01?"
            ),
            return_direct=True
        ),
        Tool(
            name="CatatNotulensi",
            func=lambda action_input: notulensi_teks_agent.invoke({"input": str(action_input)}),
            description=("Gunakan untuk mencatat isi notulensi berbasis teks. "
            "Contoh: 'tolong catat',"
            " 'notulensi site cilacap_pl',"
            " Gunakan ini untuk mencatat keluhan teknis seperti sinyal jelek, baterai rusak, rru rusak, dll."
            ),
            return_direct=True 

        ),
        Tool(
            name="UpdateStatusCatatan",
            func=lambda action_input: notulensi_teks_agent.invoke({"input": str(action_input)}),            
            description=(
        "Gunakan tool ini jika pengguna mengatakan bahwa sebuah gangguan atau masalah sudah selesai, teratasi, atau selesai diperbaiki.\n"
        "Contoh:\n"
        "- gangguan sinyal lemah di site CILACAP_PL sudah teratasi\n"
        "- gangguan interferensi site XYZ sudah selesai\n"
        "- masalah baterai site X sudah diperbaiki"
        ),
        return_direct=True

        ),
        Tool(
             name="TampilkanNotulensi",
            func=lambda action_input: notulensi_teks_agent.invoke({"input": str(action_input)}),
            description="Gunakan untuk menampilkan kembali notulensi yang pernah disimpan. Contoh: 'tampilkan notulensi site cilacap_pl', 'lihat catatan 10 juli'.",
            return_direct=True

        ),
        Tool(
            name="RekapCatatan",
            func=lambda action_input: notulensi_teks_agent.invoke({"input": str(action_input)}),
            description="Gunakan untuk menampilkan rekap catatan audit site mingguan, bulanan, atau rentang tanggal.",
            return_direct=True

        ),

        Tool(
            name="SimpanFile",
            func=lambda action_input: dokumen_agent.invoke({"input": str(action_input)}),
            description=("Gunakan untuk menyimpan file dari pengguna. Contoh: 'simpan file notulensi ini', 'tolong simpan dokumen audit'."
            ),
            return_direct=True

        ),
        Tool(
            name="UnggahDokumen",
            func=lambda action_input: dokumen_agent.invoke({"input": str(action_input)}),
            description=( "Gunakan tool ini hanya jika pengguna secara eksplisit mengatakan ingin MENGUNGGAH, "
                          "UPLOAD, atau MENYIMPAN dokumen baru untuk site tertentu. "
                          "Jangan gunakan ini untuk permintaan menampilkan dokumen yang sudah ada."
            ),
            return_direct=True 

        ),
        Tool(
            name="JawabRAG",
            func=lambda action_input: rag_agent.invoke({"input": str(action_input)}),
            description=(
        "Gunakan tool ini jika pengguna bertanya atau meminta informasi tentang gangguan, status site, "
        "masalah yang terjadi, atau ingin dijawab berdasarkan isi dokumen dan catatan yang telah disimpan. "
        "Aktifkan jika kalimat mengandung tanda tanya atau menggunakan kata perintah seperti 'sebutkan', "
        "'berikan', 'daftar', 'tunjukkan', atau bentuk permintaan informasi umum lainnya. "
        "Contoh: 'apa gangguan di site cilacap?', 'gangguan power terjadi di mana saja?', "
        "'site mana yang belum normal?', 'masalah baterai di site X sudah selesai?', "
        "'sebutkan semua site yang sedang gangguan', 'berikan daftar site yang sudah normal'."
    ),
    return_direct=True
)

    ]

    supervisor_prompt = PromptTemplate(
    input_variables=["input", "agent_scratchpad", "tools", "tool_names", "chat_history"],
    template="""
    📜 Riwayat percakapan sebelumnya (chat_history):
{chat_history}

---
Jawab pertanyaan pengguna berikut dengan sebaik mungkin. Anda memiliki akses ke tool di bawah ini:

{tools}

📌 Jika pengguna TIDAK menyebut nama site secara eksplisit, periksa chat_history di bawah ini. Jika percakapan sebelumnya menyebutkan site (misalnya "KEDUNGMUNDU_EP"), asumsikan bahwa pertanyaan saat ini merujuk pada site tersebut. Misalnya:

- Pertanyaan: "berapa throughput-nya?"
- Site terakhir dalam chat_history: "KEDUNGMUNDU_EP"
- Maka tool dan input yang digunakan adalah: DataSiteQuery → "berapa throughput site KEDUNGMUNDU_EP"

📌 Jika pengguna MENYEBUTKAN SITE SECARA EKSPLISIT (misal site id 14XXX atau nama site), anggap itu sebagai site konteks AKTIF untuk semua pertanyaan lanjutan, tanpa perlu melihat memory.”

Gunakan format berikut dengan sangat teliti:

Pertanyaan: Pertanyaan yang harus Anda jawab
Thought: Anda harus selalu berpikir tentang apa yang harus dilakukan.
Action: Nama tool yang akan digunakan, harus salah satu dari [{tool_names}]
Action Input: Input untuk tool tersebut
Observation: Hasil dari eksekusi tool
... (Urutan ini bisa berulang)

Thought: Saya sekarang sudah tahu jawaban akhirnya.
Final Answer: Jawaban akhir untuk pertanyaan asli dari pengguna

📌 Panduan memilih tool:
- Gunakan TampilkanRiwayat jika pengguna ingin melihat isi percakapan sebelumnya.
  Contoh: "apa yang pernah aku tanya", "tampilkan riwayat", "apa pernah aku bahas tentang cilacap?"
- Gunakan SiteResearcher jika pertanyaan berkaitan dengan pencarian daftar site, **site ID, atau mencocokkan **nama site ↔ ID site. Contoh: "daftar site di Purbalingga", "apa site ID dari purbalingga_mt", "site apa saja di Kabupaten X", "site apa saja di Semarang", "site di bawang?", "nama site wonotunggal?", "site wonotunggal?", "site gemuh?", "site id 15SMN01?", "site 15SMN01?", "site purbalingga?".
- Gunakan SiteLocation jika pertanyaan menanyakan detail lokasi, *koordinat, **micro cluster, **konfigurasi ran* atau region/sales area dari site yang sudah diketahui namanya atau ID-nya. Contoh: "di mana lokasi site purbalingga_mt", "koordinat site 14PBG0060", "region site ini di mana?", "konfigurasi ran CILACAP1_PL", JUMLAH SITE per kabupaten (contoh: "berapa site di Klaten?", "di semarang ada berapa site?", "total jumlah site di klaten?").
- Gunakan SiteInfoQuery jika pertanyaan menyangkut data teknis site dasar seperti azimuth antenna, antenna height, transport, dan hub type. Contoh: "berapa azimuth site RNGASPENDAWA_MT", "apa hub type site ini?", JUMLAH SITE per tipe hub (contoh: "berapa jumlah site yang bertipe hub small hub site?", "berapa jumlah site yang bertipe hub end site?", "total jumlah site tipe small hub site ?").
- Gunakan DataSiteQuery jika pertanyaan menyangkut data numerik site VLR, traffic, throughput, enodeb_id, resource atau revenue. Contoh: "berapa traffic im3 site KLUMIH", "enodeb_id dari site BAWANG", "resource site KARANGDADAP_PEKALONGAN_TB"
- Gunakan SiteNameOnlyResponder jika pengguna hanya menyebutkan nama site saja, tanpa menyampaikan pertanyaan. Contoh: "KEDUNGMUNDU_EP", "PSBAWANG_TB", "14CLP0071". JANGAN GUNAKAN TOOL INI JIKA ADA PERTANYAAN SEPERTI "site id 15YOG01?", "site gemuh?", "site batang?" (ini tugas agent researcher)
-JIKA PENGGUNA BERTANYA "SITE GEMUH"?, "site 15YOG01?","site 15SMN01?" GUNAKAN AGENT RESEARCHER JANGAN MENGARAHKAN KE TOOL SiteNameOnlyResponder, TOOL ini jika pengguna hanya menyebutkan nama site seperti, "PURBALINGGA_PL", "14PBG0063"!!!
- JIKA PERTANYAAN MENGANDUNG "site 15YOG01?","site 15SMN01? JANGAN ARAHKAN KE TOOL SiteNameOnlyResponder, TOOL ini jika pengguna hanya menyebutkan nama site yang tidak terdapat tanda tanya seperti, "PURBALINGGA_PL", "14PBG0063"!!!
🚨 PRIORITAS:

Jika input MENGANDUNG kata seperti "tampilkan", "lihat", atau "baca"
DAN juga MENGANDUNG kata seperti "catatan", "notulensi", atau "laporan",
MAKA gunakan tool TampilkanNotulensi.

Jika input HANYA BERISI satu kata atau frasa yang merupakan nama site, tanpa kata kerja atau instruksi lainnya,
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

- Gunakan CatatNotulensi :
   - jika perintah untuk mencatat isi notulensi berbasis teks. Contoh: 'tolong catat', 'catat site','notulensi site cilacap_pl', 'simpan catatan audit', 'Antena site rusak'."
   - Jika pengguna sebelumnya menyebutkan sedang audit site tertentu (misalnya "tolong saya sedang audit site CILACAP_PL"),
dan selanjutnya dia memberikan kalimat yang tampak seperti isi laporan atau notulensi (contoh: "Antena site rusak"),
maka gunakan tool CatatNotulensi untuk menambahkan catatan, bukan mengulang deteksi site baru.
    - Jika isi catatan seperti 'trafik turun di jam 9 pagi' GUNAKAN tool CatatNotulensi BUKAN tool DatasiteQuery
    - JANGAN GUNAKAN TampilkanNotulensi jika pertanyaan untuk MENAMPILKAN KEMBALI NOTULENSI YANG PERNAH DISIMPAN. Contoh: 'tampilkan notulensi site cilacap_pl', 'lihat catatan 10 juli'."
📌 Khusus untuk CatatNotulensi:
- Jika pengguna hanya mengirim kalimat biasa (contoh: 'tegangan pln tinggi', 'baterai bocor', 'antena rusak'), hasil dari tool adalah:
  "📝 Catatan diterima. Ada lagi yang ingin dicatat? Ketik cukup jika selesai."

- Gunakan TampilkanNotulensi jika pertanyaan untuk MENAMPILKAN KEMBALI NOTULENSI YANG PERNAH DISIMPAN. Contoh: 'tampilkan notulensi site cilacap_pl', 'lihat catatan 10 juli'."
- Jika pengguna mengajukan pertanyaan seperti "tampilkan catatan site purbalingga_pl", maka gunakan tool TampilkanNotulensi

  ❗JANGAN buat Final Answer dulu. Tunggu sampai pengguna mengetik cukup.

- Hanya jika pengguna mengetik cukup, gunakan tool SimpanCatatanNotulensi, dan barulah buat Final Answer dari hasilnya.
-Gunakan SimpanFile jika pengguna sudah mengunggah file dan ingin menyimpannya ke sistem.
- Gunakan TampilkanDokumen jika pengguna menyebut "tampilkan", "lihat", "buka", atau "akses" dokumen atau file tertentu, bahkan jika tidak menyebut kata 'file' secara eksplisit.
- Gunakan UnggahDokumen *hanya jika pengguna menyatakan ingin mengirim dokumen, seperti "unggah", "upload", "kirim file", atau menyebut "saya mau upload" — *hindari asumsi default berdasarkan input pendek seperti 'dokumen site xxx'.
- Gunakan **JAWABRAG** jika pertanyaan menyangkut:
  - site mana saja yang mengalami masalah tertentu.
  - apakah masalah tertentu sudah diperbaiki atau belum.
  - JANGAN GUNAKAN **JAWABRAG** untuk menangani pernyataan seperti "tower kurang tinggi, sinyal hilang", "baterai lemah", INI MERUPAKAN TUGAS *CatatNotulensi*!!
  - Jika input mengandung kata perintah seperti "sebutkan", "berikan", "tunjukkan", "daftar" → gunakan tool **JawabRAG**.


📌 Berikut beberapa aturan penting:
- Jika pengguna ingin melihat, menampilkan, membaca catatan notulensi, gunakan tool TampilkanNotulensi.
- Jika pengguna ingin mencatat, menambahkan, menyimpan catatan baru, gunakan tool CatatNotulensi.
- Jangan gunakan CatatNotulensi jika permintaan pengguna hanya menyebut nama site, karena itu bisa berarti ingin melihat catatan yang sudah ada.
- Gunakan UpdateStatusCatatan jika pengguna mengatakan bahwa masalah, gangguan, atau kendala sudah selesai, diperbaiki, atau teratasi. 
  Contoh: 
  - "gangguan trafik site cilacap_pl sudah selesai" 
  - "baterai site ini sudah diganti" 
  - "gangguan sinyal sudah diperbaiki"



Pertanyaan: {input}
{agent_scratchpad}
"""
)


    agent = create_react_agent(
        llm=llm,
        tools=tools,
        prompt=supervisor_prompt,
    )

    base_executor = AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=True,
        handle_parsing_errors=True,
        max_iterations=4,
    )

    agent_with_memory = RunnableWithMessageHistory(
        RunnableLambda(lambda x: base_executor.invoke(x)),
        get_session_history,
        input_messages_key="input",
        history_messages_key="chat_history",
)

    return agent_with_memory