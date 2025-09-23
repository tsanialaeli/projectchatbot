import gradio as gr
from typing import Any, AsyncGenerator
from PIL import Image
import os
import io
import csv
import time
import uuid
import asyncio
import ast
import json
from datetime import datetime
from tools.tools_notulensi_teks import export_notulensi
from tools.tools_dokumen import simpan_file

# Tambahan: fungsi simpan jawaban RAG ke TXT/PDF
from tools.tools_rag import simpan_jawaban_ke_txt, simpan_jawaban_ke_pdf

# === Variabel Global ===
TEMP_MAP_PATH = "temp_site_map.png"
TEMP_CHART_PATH = "temp_site_chart.png"
CHAT_LOG_PATH = "chatbot_logbook.csv"

TXT_FOLDER = "generated_txts"
PDF_FOLDER = "generated_pdfs"
os.makedirs(TXT_FOLDER, exist_ok=True)
os.makedirs(PDF_FOLDER, exist_ok=True)

# === Antrian Agent ===
user_queue = []
agent_busy = False
queue_lock = asyncio.Lock()

# === Logging Chat ke CSV ===
def log_to_csv(user_message: str, agent_name: str, bot_response: str, response_time: float):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    file_exists = os.path.exists(CHAT_LOG_PATH)
    with open(CHAT_LOG_PATH, mode="a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        if not file_exists:
            writer.writerow(["Timestamp", "Pertanyaan", "Agent yang menangani", "Jawaban", "Waktu Respons (detik)"])
        writer.writerow([timestamp, user_message, agent_name, bot_response, f"{response_time:.2f}"])

# === Fungsi Utama Agent (Async + Antrian) ===
async def run_agent_interface(
    message: str,
    history: list,
    agent_to_run: Any,
    authenticated: bool,
    session_id: str
) -> AsyncGenerator[tuple[str | None, Any | None, bool, str], None]:

    global user_queue, agent_busy

    print(f"[🟢 SESSION] User dengan session_id = {session_id} mengirim: {message}")

    # --- Logika Otentikasi ---
    password = "indosat2025"
    if not authenticated:
        if message.strip() == password:
            yield "✅ Password benar! Sekarang kamu bisa tanya tentang site Central Java.", None, True, session_id
            return
        else:
            yield "🔐 Silakan masukkan password terlebih dahulu.", None, False, session_id
            return

    # === Daftarkan di antrian ===
    async with queue_lock:
        if session_id not in user_queue:
            user_queue.append(session_id)
            print(f"[QUEUE] session_id {session_id} ditambahkan ke antrian.")

    timeout_seconds = 120
    wait_start = time.time()
    last_status_message = ""

    # --- Feedback Awal ---
    yield "Koneksi ke antrian berhasil. Mengecek status...", None, True, session_id

    while True:
        if time.time() - wait_start > timeout_seconds:
            async with queue_lock:
                if session_id in user_queue:
                    user_queue.remove(session_id)
            print(f"[TIMEOUT] session_id {session_id} dihapus dari antrian karena timeout.")
            yield "❌ Waktu tunggu Anda di antrian melebihi batas (2 menit). Silakan coba lagi.", None, True, session_id
            return

        async with queue_lock:
            if user_queue and user_queue[0] == session_id and not agent_busy:
                agent_busy = True
                print(f"[PROCESS] session_id {session_id} mendapat giliran dan memulai proses.")
                break
            try:
                position = user_queue.index(session_id) + 1
                total = len(user_queue)
                status_message = (
                    f"⏳ Anda berada di antrian ke-{position} dari {total} pengguna.\n"
                    "Mohon tunggu sebentar, agen akan segera melayani Anda."
                )
            except ValueError:
                print(f"[WARNING] session_id {session_id} tidak ditemukan lagi di antrian.")
                yield "Terjadi masalah pada antrian. Silakan kirim ulang pesan Anda.", None, True, session_id
                return

        if status_message != last_status_message:
            last_status_message = status_message
            yield status_message, None, True, session_id

        await asyncio.sleep(2)

    # === Bersihkan gambar lama sebelum proses baru ===
    for path in [TEMP_CHART_PATH, TEMP_MAP_PATH]:
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception as e:
                print(f"[WARNING] Gagal menghapus {path}: {e}")

    # === Mulai proses agent ===
    start_time = time.time()
    final_output_str = ""
    image = None

    try:
        yield "🤖 Giliran Anda tiba! Agen sedang memproses permintaan Anda...", None, True, session_id

        result = await agent_to_run.ainvoke(
            {"input": message},
            config={"configurable": {"session_id": session_id}}
        )

        # Ambil field output dengan robust parsing:
        if isinstance(result, dict):
            output_val = result.get("output", "❌ Output tidak ditemukan.")
        else:
            output_val = result

        # Jika output_val adalah dict (langsung), ambil nested output jika ada
        if isinstance(output_val, dict):
            output_val = output_val.get("output", output_val)

        # Jika output_val adalah string yang merepresentasikan dict/JSON, coba parse
        if isinstance(output_val, str):
            out_str = output_val.strip()
            if out_str.startswith("{") and out_str.endswith("}"):
                try:
                    parsed = json.loads(out_str)
                    if isinstance(parsed, dict) and "output" in parsed:
                        output_val = parsed["output"]
                except json.JSONDecodeError:
                    try:
                        parsed = ast.literal_eval(out_str)
                        if isinstance(parsed, dict) and "output" in parsed:
                            output_val = parsed["output"]
                    except Exception:
                        pass

        final_output_str = str(output_val).strip()

        # === Ambil gambar jika ada hasil baru ===
        if os.path.exists(TEMP_CHART_PATH):
            try:
                image = Image.open(TEMP_CHART_PATH)
            except Exception as e:
                print(f"[WARNING] Gagal membuka chart: {e}")
        elif os.path.exists(TEMP_MAP_PATH):
            try:
                image = Image.open(TEMP_MAP_PATH)
            except Exception as e:
                print(f"[WARNING] Gagal membuka map: {e}")

        final_output_str = final_output_str.replace("[[NO_HISTORY]]", "").strip()

    except Exception as e:
        print(f"[ERROR] Terjadi kesalahan saat menjalankan agent: {e}")
        final_output_str = "❌ Maaf, terjadi kesalahan internal saat memproses permintaan Anda."

    finally:
        async with queue_lock:
            if session_id in user_queue:
                user_queue.remove(session_id)
            agent_busy = False
            print(f"[FINISH] session_id {session_id} selesai. Lock dilepaskan.")

    response_time = time.time() - start_time
    if hasattr(agent_to_run, "runnable"):
        agent_name = type(agent_to_run.runnable).__name__
    else:
        agent_name = type(agent_to_run).__name__

    log_to_csv(message, agent_name, final_output_str, response_time)

    yield final_output_str, image, True, session_id

# Simpan jawaban RAG ke TXT dan PDF (gunakan fungsi dari tools/rag.py)
def save_rag_txt(jawaban: str):
    filename = os.path.join(TXT_FOLDER, "jawaban_rag.txt")
    simpan_jawaban_ke_txt(jawaban, filename)
    return filename if os.path.exists(filename) else None

def save_rag_pdf(jawaban: str):
    filename = os.path.join(PDF_FOLDER, "jawaban_rag.pdf")
    simpan_jawaban_ke_pdf(jawaban, filename)
    return filename if os.path.exists(filename) else None

# === Build Gradio App ===
def build_gradio_app(agent_to_run: Any):
    def generate_session_id():
        return str(uuid.uuid4())

    # Variabel simpan jawaban terakhir
    last_answer = {"text": ""}

    with gr.Blocks(theme=gr.themes.Soft()) as demo:
        gr.Markdown("# 🤖 Site Audit Chatbot")

        state_authenticated = gr.State(value=False)
        state_session_id = gr.State(generate_session_id)
        image_output_state = gr.State(value=None)
        answer_state = gr.State(value="")  # simpan jawaban terakhir

        with gr.Tabs():
            # Chat Tab
            with gr.TabItem("💬 Chat"):
                chatbot_history = gr.Chatbot(
                    label="Obrolan", bubble_full_width=False, height=500,
                    avatar_images=(None, "logo_indosat.jpg")
                )
                with gr.Row():
                    txt_input = gr.Textbox(scale=4, show_label=False, placeholder="Masukkan password atau pertanyaan...")
                    btn_submit = gr.Button("▶️ Kirim")


            # Visualisasi Tab
            with gr.TabItem("📊 Visualisasi"):
                gr.Markdown("### 📸 Visual Output dari Agent")
                image_display = gr.Image(label="🖼 Gambar Hasil", interactive=False)

            # Dokumen Tab
            with gr.TabItem("📂 Dokumen"):
                gr.Markdown("### 📅 Unggah Dokumen Audit")
                nama_input = gr.Text(label="📝 Nama File", placeholder="Contoh: laporan_audit")
                file_input = gr.File(label="📌 Pilih File", file_types=[".pdf", ".txt", ".docx", ".csv", ".jpg", ".jpeg", ".png"])
                btn_upload = gr.Button("📤 Upload Sekarang")
                upload_output = gr.Textbox(label="🧾 Status Upload", interactive=False)

                def handle_upload(file, nama, authenticated):
                    user_id = "default"
                    if not authenticated:
                        return "🔒 Login dulu."
                    if not file:
                        return "⚠ Harap pilih file."
                    result = simpan_file(file, user_id=user_id, custom_name=nama)
                    return result if isinstance(result, str) else "✅ File berhasil disimpan."

                btn_upload.click(fn=handle_upload, inputs=[file_input, nama_input, state_authenticated], outputs=upload_output)

            # Notulensi Tab
            with gr.TabItem("📝 Notulensi"):
                gr.Markdown("### 📄 Ekspor Notulensi")

                with gr.Row():
                    btn_n_txt = gr.Button("📄 Jadikan Notulensi TXT dan Unduh")
                    download_n_txt = gr.File(label="📁 File TXT", interactive=False)

                    btn_n_pdf = gr.Button("🧾 Jadikan Notulensi PDF dan Unduh")
                    download_n_pdf = gr.File(label="📁 File PDF", interactive=False)
                    
                with gr.Row():
                    btn_txt = gr.Button("📄 Jadikan Jawaban RAG TXT dan Unduh")
                    download_txt = gr.File(label="File TXT", interactive=False)

                    btn_pdf = gr.Button("🧾 Jadikan Jawaban RAG PDF dan Unduh")
                    download_pdf = gr.File(label="File PDF", interactive=False)

                def handle_export_notulensi_txt(authenticated):
                    if not authenticated:
                        return None
                    result = export_notulensi("txt","default")
                    return result if isinstance(result, str) and os.path.exists(result) else None

                def handle_export_notulensi_pdf(authenticated):
                    if not authenticated:
                        return None
                    result = export_notulensi("pdf","default")
                    if isinstance(result, dict) and result.get("url"):
                        path = os.path.join("generated_pdfs", result["name"])
                        return path if os.path.exists(path) else None
                    elif isinstance(result, str) and os.path.exists(result):
                        return result
                    return None
                # Fungsi untuk simpan jawaban RAG ke TXT dan PDF
                def export_txt_wrapper(jawaban):
                    if not jawaban:
                        return None
                    return save_rag_txt(jawaban)

                def export_pdf_wrapper(jawaban):
                    if not jawaban:
                        return None
                    return save_rag_pdf(jawaban)

                btn_n_txt.click(fn=handle_export_notulensi_txt, inputs=state_authenticated, outputs=download_n_txt)
                btn_n_pdf.click(fn=handle_export_notulensi_pdf, inputs=state_authenticated, outputs=download_n_pdf)

        # Handler Chat
        async def handle_chat_submission(message, history, auth_status, session_id):
            history.append([message, "⏳ Menghubungi agen..."])
            yield {chatbot_history: history, txt_input: "", answer_state: ""}
            final_image = None
            final_auth = auth_status

            jawaban_terakhir = ""

            async for text, image, new_auth, new_sess_id in run_agent_interface(
                message, history, agent_to_run, auth_status, session_id
            ):
                history[-1][1] = text
                if image:
                    final_image = image
                final_auth = new_auth
                jawaban_terakhir = text
                yield {chatbot_history: history, answer_state: jawaban_terakhir}

            yield {image_output_state: final_image, state_authenticated: final_auth, answer_state: jawaban_terakhir}

        # Bind event
        txt_input.submit(
            fn=handle_chat_submission,
            inputs=[txt_input, chatbot_history, state_authenticated, state_session_id],
            outputs=[chatbot_history, txt_input, answer_state, image_output_state, state_authenticated]
        )
        btn_submit.click(
            fn=handle_chat_submission,
            inputs=[txt_input, chatbot_history, state_authenticated, state_session_id],
            outputs=[chatbot_history, txt_input, answer_state, image_output_state, state_authenticated]
        )
        image_output_state.change(fn=lambda img: img, inputs=image_output_state, outputs=image_display)

        btn_txt.click(fn=export_txt_wrapper, inputs=answer_state, outputs=download_txt)
        btn_pdf.click(fn=export_pdf_wrapper, inputs=answer_state, outputs=download_pdf)

    return demo