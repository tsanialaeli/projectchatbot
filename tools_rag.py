# tools/rag.py

import os
import re
from PIL import Image
import pytesseract
import unicodedata
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
from langchain.chat_models import ChatOpenAI

from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import PGVector
from langchain_community.document_loaders import (
    PDFMinerLoader,
    UnstructuredWordDocumentLoader,
    CSVLoader,
    UnstructuredFileLoader,
)

from langchain.docstore.document import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from fpdf import FPDF
from db_utils import get_db_connection

# === Konfigurasi Vectorstore ===
COLLECTION_NAME = "notulensi_vector"
CONNECTION_STRING = "postgresql+psycopg2://postgres:Magangindosat1@localhost:5434/chatbot"
embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
splitter = RecursiveCharacterTextSplitter(chunk_size=300, chunk_overlap=100)

# === Fungsi koneksi PGVector ===
def get_pgvector_store():
    return PGVector(
        collection_name=COLLECTION_NAME,
        connection_string=CONNECTION_STRING,
        embedding_function=embeddings,
    )

# === Fungsi untuk mengindeks dokumen/file ===
def index_file(file_path: str = None, documents: list = None, site_name: str = None):
    docs = []

    if documents:
        docs = splitter.split_documents(documents)

    elif file_path:
        ext = os.path.splitext(file_path)[1].lower()
        basename = os.path.basename(file_path)

        if ext in [".jpg", ".jpeg", ".png"]:
            try:
                image = Image.open(file_path)
                extracted_text = pytesseract.image_to_string(image)

                if not extracted_text.strip():
                    print("⚠️ Tidak ada teks di gambar.")
                    return

                raw_docs = [Document(
                    page_content=extracted_text,
                    metadata={"source": basename, "site_name": site_name}
                )]
            except Exception as e:
                print(f"❌ Gagal OCR: {e}")
                return

        else:
            try:
                if ext == ".txt":
                    loader = UnstructuredFileLoader(file_path, mode="elements")
                elif ext == ".pdf":
                    loader = PDFMinerLoader(file_path)
                elif ext in [".docx", ".doc"]:
                    loader = UnstructuredWordDocumentLoader(file_path)
                elif ext == ".csv":
                    loader = CSVLoader(file_path)
                else:
                    print(f"⛔ Format file tidak dikenali: {file_path}")
                    return

                raw_docs = loader.load()
                for doc in raw_docs:
                    doc.metadata["source"] = basename
                    if site_name:
                        doc.metadata["site_name"] = site_name

            except Exception as e:
                print(f"❌ Gagal load dokumen: {e}")
                return

        docs = splitter.split_documents(raw_docs)

    else:
        print("❌ Harus beri file_path atau documents.")
        return

    if not docs:
        print("⚠️ Tidak ada dokumen untuk diindeks.")
        return

    try:
        PGVector.from_documents(
            documents=docs,
            embedding=embeddings,
            collection_name=COLLECTION_NAME,
            connection_string=CONNECTION_STRING,
        )
        print("✅ Dokumen berhasil diindeks.")
    except Exception as e:
        print(f"❌ Gagal menyimpan ke PGVector: {e}")

# === Ambil konteks dari database ===
def get_catatan_site_context(site_name: str | None) -> str:
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                if not site_name:
                    return ""
                cur.execute("""
                    SELECT tanggal, jam, isi_catatan, status, tanggal_selesai 
                    FROM catatan_site 
                    WHERE LOWER(site_name) = %s 
                    ORDER BY tanggal, jam
                """, (site_name.lower(),))
                rows = cur.fetchall()

        if not rows:
            return f"Tidak ada catatan ditemukan untuk site {site_name.upper()}."

        lines = [f"📍 Ringkasan catatan site {site_name.upper()}:"]
        for tanggal, jam, isi, status, tanggal_selesai in rows:
            simbol = "✅" if status == "selesai" else "⏳"
            selesai_info = f" (selesai: {tanggal_selesai})" if status == "selesai" and tanggal_selesai else ""
            lines.append(f" 📅 {tanggal} ⏰ {jam} {simbol}{selesai_info} {(isi or '').strip()}")
        return "\n".join(lines)

    except Exception as e:
        return f"⚠️ Gagal mengambil data catatan dari database (Error: {e})"

# === Jawaban berbasis RAG ===
def jawab_pertanyaan_pgvector(pertanyaan: str, user_id: str = "default") -> str:
    match = re.search(r"site\s+([\w\-]+)", pertanyaan, re.IGNORECASE)
    site_name = match.group(1) if match else None

    db_context = get_catatan_site_context(site_name)

    vectorstore = PGVector(
        collection_name=COLLECTION_NAME,
        connection_string=CONNECTION_STRING,
        embedding_function=embeddings,
    )
    retriever = vectorstore.as_retriever(search_type="similarity", k=8)
    docs = retriever.get_relevant_documents(pertanyaan)
    vector_context = "\n".join([doc.page_content for doc in docs])

    full_context = f"{db_context}\n\n{vector_context}".strip()

    llm = ChatOpenAI(
        temperature=0.2,
        model="mistralai/mistral-small-3.2-24b-instruct",
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPENROUTER_API_KEY_MISTRAL"),
    )

    prompt = PromptTemplate(
        input_variables=["context", "question"],
        template="""\
Anda adalah asisten teknis yang bertugas menganalisis dokumen gangguan teknis pada site. Berdasarkan informasi berikut:

{context}

Jawablah pertanyaan berikut secara lengkap:

{question}

❗Jika terdapat tanda tanya ("?") dalam pertanyaan, maka 90% besar kemungkinan membutuhkan referensi dari dokumen. Maka dari itu, gunakan tool JawabRAG.
⚠️ Jika Anda menemukan lebih dari satu informasi dalam dokumen, tampilkan semuanya dalam format daftar:

Contoh:
- Baterai soak
- Interferensi
- Tegangan PLN tinggi

Jangan hilangkan gangguan kecil sekalipun seperti sinyal down, kabel rusak, atau baterai soak.
"""
    )

    chain = LLMChain(llm=llm, prompt=prompt)
    result = chain.invoke({
        "context": full_context,
        "question": pertanyaan
    })

    return f"[Hasil dari JawabRAG]:\n{result['text'].strip()}"

# === Simpan jawaban ke file TXT ===
def simpan_jawaban_ke_txt(jawaban: str, filename: str = "jawaban_rag.txt"):
    with open(filename, "w", encoding="utf-8") as f:
        f.write(jawaban)
    print(f"✅ Jawaban berhasil disimpan ke {filename}")

def sanitize_text_for_pdf(text: str) -> str:
    # Normalisasi ke NFKD dan hilangkan karakter non-ASCII
    normalized = unicodedata.normalize('NFKD', text)
    ascii_text = normalized.encode('ascii', 'ignore').decode('ascii')
    return ascii_text

def simpan_jawaban_ke_pdf(jawaban: str, filename: str):
    # Sanitasi supaya aman untuk FPDF
    safe_text = sanitize_text_for_pdf(jawaban)
    
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.multi_cell(0, 10, safe_text)
    pdf.output(filename)
    print(f"✅ Jawaban berhasil disimpan ke {filename}")

# === Contoh penggunaan ===
if __name__ == "__main__":
    pertanyaan = "Apa gangguan yang terjadi di site dermasari_pl?"
    hasil_jawaban = jawab_pertanyaan_pgvector(pertanyaan)
    print(hasil_jawaban)

    # Simpan ke TXT
    simpan_jawaban_ke_txt(hasil_jawaban, "hasil_jawaban.txt")

    # Simpan ke PDF
    simpan_jawaban_ke_pdf(hasil_jawaban, "hasil_jawaban.pdf")
