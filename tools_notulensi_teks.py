# notulensi.py
import os
import re
import unicodedata
from datetime import datetime, timedelta
from fpdf import FPDF
from dateutil.parser import parse as parse_date
import dateparser
import calendar
from collections import defaultdict
from rapidfuzz import fuzz

from db_utils import get_db_connection
from tools.tools_researcher import query_site_from_db

TXT_FOLDER = os.path.join(os.getcwd(), "catatan_txt")
PDF_FOLDER = os.path.join(os.getcwd(), "generated_pdfs")
TABLE_NAME = "catatan_site"
TABLE_SITE = "site_name"

os.makedirs(TXT_FOLDER, exist_ok=True)
os.makedirs(PDF_FOLDER, exist_ok=True)

user_sessions = {}
db_write_lock = None  # pastikan ini didefinisikan sesuai implementasi lock DB


# ----------------------------
# Helper Functions
# ----------------------------
def sanitize_text_for_pdf(text: str) -> str:
    return unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('utf-8')


def similar(a: str, b: str) -> float:
    return fuzz.token_set_ratio(a.lower(), b.lower()) / 100.0


def _prepare_timestamp():
    now = datetime.now()
    tanggal = now.strftime("%A, %d %B %Y")
    jam = now.strftime("%H:%M:%S")
    return tanggal, jam


def extract_site_name(text: str) -> str | None:
    match = re.search(r"\bsite\s+([a-zA-Z0-9_\-]+)", text.lower())
    return match.group(1).lower() if match else None


def parse_tanggal_to_db_format(tanggal_input: str) -> str:
    tanggal = dateparser.parse(tanggal_input, languages=["id", "en"])
    if tanggal:
        return tanggal.strftime("%A, %d %B %Y")
    return tanggal_input


def format_notulensi_to_markdown(raw_text: str) -> str:
    raw_text = re.sub(r"📅\s*(.?)\s-\s*⏰\s*(.*?)\n", r"\n### 📅 \1 - ⏰ \2\n", raw_text)
    raw_text = raw_text.replace("📝", "\n📝").replace("\\n", "\n")
    return re.sub(r"\n{2,}", "\n\n", raw_text.strip())


# ----------------------------
# Status Update
# ----------------------------
def update_status_catatan(query: str) -> str | None:
    query_lower = query.lower()
    match = re.search(r"site\s+([\w\-]+)", query_lower)
    if not match:
        return "❌ Tidak ditemukan nama site dalam kalimat."

    site = match.group(1).strip().lower()
    selesai_triggers = ["sudah", "telah", "teratasi", "selesai", "diperbaiki", "diselesaikan", "beres", "clear", "aman"]
    if not any(trigger in query_lower for trigger in selesai_triggers):
        return "⚠ Tidak ditemukan indikasi bahwa masalah telah selesai."

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT id, COALESCE(isi_catatan, '') 
                    FROM {TABLE_NAME}
                    WHERE LOWER(site_name) = %s AND status IS DISTINCT FROM 'selesai'
                """, (site,))
                rows = cur.fetchall()

                updated = 0
                now = datetime.now().strftime("%A, %d %B %Y")

                for row_id, isi_db in rows:
                    if not isi_db or not isinstance(isi_db, str):
                        continue

                    score = similar(query_lower, isi_db.lower())
                    user_words = set(re.findall(r'\w+', query_lower))
                    isi_words = set(re.findall(r'\w+', isi_db.lower()))
                    overlap = user_words & isi_words

                    if score >= 0.75 and len(overlap) >= 2:
                        cur.execute(f"""
                            UPDATE {TABLE_NAME}
                            SET status = 'selesai', tanggal_selesai = %s
                            WHERE id = %s
                        """, (now, row_id))
                        updated += 1

                conn.commit()
                if updated == 0:
                    return f"ℹ Tidak ada catatan cocok yang diperbarui untuk site {site.upper()}."
                return f"✅ {updated} catatan di site {site.upper()} ditandai selesai."

    except Exception as e:
        return f"❌ Gagal memperbarui status: {e}"
def query_site_from_db(site_input):
    """
    Cek apakah site ada di tabel site_data
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT site_name FROM {TABLE_SITE} WHERE LOWER(site_name) = %s", (site_input.lower(),))
                result = cur.fetchone()
                return result is not None
    except Exception as e:
        print(f"[ERROR] query_site_from_db: {e}")
        return False

# ----------------------------
# Catat Notulensi
# ----------------------------
def catat_notulensi(query: str, user_id: str = "default") -> str:
    isi_lower = query.lower().strip()
    session = user_sessions.setdefault(user_id, {})

    abaikan = [
        'sedang diaudit', 'dalam proses audit', 'masih dicek', 'dalam pengecekan',
        'site ini sedang audit', 'audit site', 'belum diketik'
    ]

    # Update status jika ada kata kunci selesai
    if "sudah" in isi_lower and any(k in isi_lower for k in ["selesai", "teratasi", "ditangani"]):
        msg = update_status_catatan(query)
        return msg if msg else "⚠ Tidak ditemukan catatan yang relevan untuk diperbarui."

    # Hanya catat site
    match_site_only = re.match(r"^catat\s+site\s+([\w\-]+)\s*$", query, re.IGNORECASE)
    if match_site_only:
        site_only = match_site_only.group(1).lower()
        if not query_site_from_db(site_only):
            return f"⚠ Site {site_only} tidak ditemukan dalam database."
        session["site"] = site_only
        return f"📌 Site {site_only.upper()} tercatat — kirim catatan dengan format: 'site {site_only} isi catatan'."

    # Ekstrak site
    site = extract_site_name(query)
    if not site:
        return "⚠ Harap sertakan nama site di catatan. Contoh: 'site MAOS_EP genset turun'."
    if not query_site_from_db(site):
        return f"⚠ Site {site} tidak ditemukan dalam database."
    session["site"] = site

    # Ekspor jika diminta
    if "txt" in isi_lower:
        return export_notulensi("txt", user_id)
    if "pdf" in isi_lower:
        return export_notulensi("pdf", user_id)

    tanggal, jam = _prepare_timestamp()
    valid_notes = []

    # Proses setiap baris catatan
    for line in re.split(r"(?<=[\.,\n])\s+", query):
        clean = line.strip("* .,\n").strip()
        if not clean:
            continue
        if re.fullmatch(r"site\s+[a-zA-Z0-9_\-]+[:\s]*", clean.lower()):
            continue
        clean = re.sub(r"^\s*site\s+[a-zA-Z0-9_\-]+[:\s]*", "", clean, flags=re.IGNORECASE)
        clean = re.sub(r"\bsite\s+[a-zA-Z0-9_\-]+[:\s]*$", "", clean, flags=re.IGNORECASE)
        if len(clean) > 5 and ' ' in clean and not any(x in clean.lower() for x in abaikan):
            status = "selesai" if any(k in clean.lower() for k in ["selesai", "sudah", "teratasi"]) else "aktif"
            tanggal_selesai = tanggal if status == "selesai" else None
            valid_notes.append({
                "tanggal": tanggal,
                "jam": jam,
                "isi": clean,
                "status": status,
                "tanggal_selesai": tanggal_selesai,
                "file_path": None,
                "original_filename": None,
                "custom_name": None,
                "file_type": None
            })

    if not valid_notes:
        return "⚠ Catatan terlalu pendek atau tidak valid. Sertakan deskripsi yang jelas minimal 6 karakter."

    # Simpan ke session
    session.setdefault("catatan", []).extend(valid_notes)

    # ----------------------------
    # Simpan ke database
    # ----------------------------
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                for note in valid_notes:
                    cur.execute(f"""
                        INSERT INTO {TABLE_NAME} 
                        (site_name, isi_catatan, status, tanggal, jam, file_path, original_filename, custom_name, file_type, tanggal_selesai)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        site,
                        note["isi"],
                        note["status"],
                        note["tanggal"],
                        note["jam"],
                        note.get("file_path"),
                        note.get("original_filename"),
                        note.get("custom_name"),
                        note.get("file_type"),
                        note.get("tanggal_selesai")
                    ))
            conn.commit()
    except Exception as e:
        return f"❌ Catatan dicatat di session, tapi gagal simpan ke database: {e}"

    return f"📝 {len(valid_notes)} catatan untuk site **{site.upper()}** dicatat dan tersimpan ke database."

# ----------------------------
# Export Notulensi (TXT/PDF)
# ----------------------------
def export_notulensi(tipe: str, user_id: str) -> str | None:
    session = user_sessions.get(user_id, {})
    catatan = session.get("catatan")
    site = session.get("site") or session.get("last_site")

    if not catatan or not site:
        return f"⚠ Tidak bisa ekspor {tipe.upper()}. Belum ada catatan atau site."

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    if tipe.lower() == "txt":
        os.makedirs(TXT_FOLDER, exist_ok=True)
        path = os.path.join(TXT_FOLDER, f"{site.upper()}_{timestamp}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"📝 Notulensi Site {site.upper()}\n\n")
            for item in catatan:
                simbol = "✅" if item.get("status") == "selesai" else "⏳"
                f.write(f"📅 {item['tanggal']} ⏰ {item['jam']}\n{simbol} {item['isi']}\n\n")
        session["last_txt_path"] = path
        return path

    elif tipe.lower() == "pdf":
        os.makedirs(PDF_FOLDER, exist_ok=True)
        path = os.path.join(PDF_FOLDER, f"{site.upper()}_{timestamp}.pdf")
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", "B", 14)
        pdf.cell(0, 10, f"Notulensi Site {site.upper()}", ln=True, align="C")
        pdf.ln(5)
        pdf.set_font("Arial", size=12)
        for item in catatan:
            simbol = "Selesai" if item.get("status") == "selesai" else "Aktif"
            teks = f"Tanggal: {item['tanggal']} - Jam: {item['jam']}\nIsi: {sanitize_text_for_pdf(item['isi'])}\nStatus: {simbol}\n"
            pdf.multi_cell(0, 10, teks)
            pdf.ln(2)
        pdf.output(path)
        session["last_pdf_path"] = path
        return path

    return f"⚠ Tipe ekspor '{tipe}' tidak dikenali."

def parse_tanggal_to_db_format(tanggal_input: str) -> str:
    tanggal = dateparser.parse(tanggal_input, languages=["id", "en"])
    if tanggal:
        return tanggal.strftime("%A, %d %B %Y")  # ex: 'Monday, 04 August 2025'
    return tanggal_input

def tampilkan_notulensi(query: str, user_id: str = "default") -> str:
    query_lower = query.lower().strip()
    session = user_sessions.get(user_id, {})

    site_tanggal_match = re.search(r"site\s+([a-z0-9_\-]+).*tanggal\s+([\w\s,\-/]+)", query_lower)
    tanggal_match = re.search(r"tanggal\s+([\w\s,\-/]+)", query_lower)
    site_match = re.search(r"(?:catatan|notulensi)\s+site\s+([a-z0-9_\-]+)", query_lower)
    tampilkan_catatan_terakhir = "tampilkan catatannya" in query_lower or "tampilkan catatan" in query_lower

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                hasil = []
                catatan_terstruktur = []

                # ===========================
                # MODE 1: SESSION ADA
                # ===========================
                if tampilkan_catatan_terakhir and session.get("site"):
                    site = session.get("site") or session.get("last_site")

                    # Ambil catatan session
                    catatan_session = session.get("catatan", [])

                    # Ambil catatan DB
                    cur.execute(f"""
                        SELECT tanggal, jam, isi_catatan, status, tanggal_selesai
                        FROM {TABLE_NAME}
                        WHERE LOWER(site_name) = %s
                          AND isi_catatan IS NOT NULL
                        ORDER BY id DESC
                    """, (site.lower(),))
                    rows_db = cur.fetchall()

                    hasil.append(f"📑 **Catatan Site {site.upper()} (Session + Database):\n")

                    semua_catatan = []

                    # Masukkan DB
                    for tgl, jam, isi, status, tgl_selesai in rows_db:
                        poin = [p.strip() for p in isi.strip().splitlines() if p.strip()]
                        semua_catatan.extend([{
                            "tanggal": tgl,
                            "jam": jam or "-",
                            "isi": p,
                            "status": status,
                            "tanggal_selesai": tgl_selesai
                        } for p in poin])

                    # Masukkan session
                    semua_catatan.extend(catatan_session)

                    # Format output
                    for item in semua_catatan:
                        simbol = "✅" if item.get("status") == "selesai" else "⏳"
                        selesai_info = f" (✅ selesai: {item.get('tanggal_selesai')})" if item.get("status") == "selesai" and item.get("tanggal_selesai") else ""
                        hasil.append(f"📅 {item['tanggal']} - ⏰ {item['jam']}{selesai_info}\n{simbol} {item['isi']}\n")
                        catatan_terstruktur.append(item)

                    # Update session
                    user_sessions[user_id]["catatan"] = catatan_terstruktur
                    user_sessions[user_id]["last_site"] = site.upper()
                    return format_notulensi_to_markdown("\n".join(hasil))

                # ===========================
                # MODE 2: SESSION KOSONG / LANGSUNG DB
                # ===========================
                site_to_query = None
                tanggal_to_query = None

                if site_tanggal_match:
                    site_to_query = site_tanggal_match.group(1).strip().lower()
                    tanggal_input = site_tanggal_match.group(2).strip()
                    tanggal_to_query = parse_tanggal_to_db_format(tanggal_input)
                elif site_match:
                    site_to_query = site_match.group(1).strip().lower()
                elif tanggal_match:
                    tanggal_input = tanggal_match.group(1).strip()
                    tanggal_to_query = parse_tanggal_to_db_format(tanggal_input)

                if not site_to_query and not tanggal_to_query:
                    return ("⚠ Format tidak dikenali. Gunakan:\n"
                            "- tampilkan catatan site [nama_site]\n"
                            "- tampilkan catatan tanggal [tanggal]\n"
                            "- tampilkan catatan site [nama_site] tanggal [tanggal]\n"
                            "- tampilkan catatannya / tampilkan catatan (session + DB)")

                # Query DB sesuai filter
                sql = f"SELECT site_name, tanggal, jam, isi_catatan, status, tanggal_selesai FROM {TABLE_NAME} WHERE isi_catatan IS NOT NULL"
                params = []

                if site_to_query:
                    sql += " AND LOWER(site_name) = %s"
                    params.append(site_to_query)
                if tanggal_to_query:
                    sql += " AND tanggal = %s"
                    params.append(tanggal_to_query)
                sql += " ORDER BY tanggal, jam"

                cur.execute(sql, tuple(params))
                rows = cur.fetchall()

                if not rows:
                    if site_to_query and tanggal_to_query:
                        return f"📭 Tidak ada catatan untuk site {site_to_query.upper()} tanggal {tanggal_input}."
                    elif site_to_query:
                        return f"📭 Tidak ada catatan untuk site {site_to_query.upper()}."
                    elif tanggal_to_query:
                        return f"📭 Tidak ada catatan untuk tanggal {tanggal_input}."

                # Format hasil DB
                header = "📑 **Catatan Site {}**:\n".format(site_to_query.upper()) if site_to_query else f"🗓 **Catatan Tanggal {tanggal_input}**:\n"
                hasil.append(header)

                for row in rows:
                    site_name, tgl, jam, isi, status, tgl_selesai = row
                    poin = [p.strip() for p in isi.strip().splitlines() if p.strip()]
                    simbol = "✅" if status == "selesai" else "⏳"
                    selesai_info = f" (✅ selesai: {tgl_selesai})" if status == "selesai" and tgl_selesai else ""
                    bullet = "\n".join([f"{simbol} {p}" for p in poin])
                    lokasi = f"📍 {site_name.upper()} " if site_to_query is None else ""
                    hasil.append(f"📅 {tgl} - {lokasi}⏰ {jam or '-'}{selesai_info}\n{bullet}\n")

                return format_notulensi_to_markdown("\n".join(hasil))

    except Exception as e:
        return f"⚠ Gagal mengambil data: {e}"
    
def rekap_catatan(query: str, user_id: str = "default") -> str:
    query = query.lower().strip()
    minggu_ini = "minggu ini" in query
    minggu_kemarin = "minggu kemarin" in query or "last week" in query
    bulan_ini = "bulan ini" in query
    bulan_kemarin = "bulan kemarin" in query or "last month" in query
    rentang_match = re.search(r"dari\s+([\d\w\s\-\/]+)\s+sampai\s+([\d\w\s\-\/]+)", query)
    bulan_range_match = re.search(r"bulan\s+(\w+)\s*(\d{4})?\s*tanggal\s+(\d{1,2})\s+sampai\s+(\d{1,2})", query)
    bulan_match = re.search(r"bulan\s+(\w+)\s*(\d{4})?", query)

    try:
        today = datetime.now().date()

        if minggu_ini:
            tanggal_awal = today - timedelta(days=today.weekday())
            tanggal_akhir = today

        elif minggu_kemarin:
            tanggal_awal = today - timedelta(days=today.weekday() + 7)
            tanggal_akhir = tanggal_awal + timedelta(days=6)

        elif bulan_ini:
            tanggal_awal = today.replace(day=1)
            tanggal_akhir = today

        elif bulan_kemarin:
            first_day_this_month = today.replace(day=1)
            last_month_last_day = first_day_this_month - timedelta(days=1)
            tanggal_awal = last_month_last_day.replace(day=1)
            tanggal_akhir = last_month_last_day

        elif bulan_range_match:
            nama_bulan = bulan_range_match.group(1)
            tahun = int(bulan_range_match.group(2) or today.year)
            tanggal1 = int(bulan_range_match.group(3))
            tanggal2 = int(bulan_range_match.group(4))
            bulan_num = dateparser.parse(f"1 {nama_bulan} {tahun}", languages=["id"]).month
            tanggal_awal = datetime(tahun, bulan_num, tanggal1).date()
            tanggal_akhir = datetime(tahun, bulan_num, tanggal2).date()

        elif bulan_match:
            nama_bulan = bulan_match.group(1)
            tahun = int(bulan_match.group(2) or today.year)
            bulan_num = dateparser.parse(f"1 {nama_bulan} {tahun}", languages=["id"]).month
            tanggal_awal = datetime(tahun, bulan_num, 1).date()
            last_day = calendar.monthrange(tahun, bulan_num)[1]
            tanggal_akhir = datetime(tahun, bulan_num, last_day).date()

        elif rentang_match:
            tanggal_awal = parse_date(rentang_match.group(1), dayfirst=True).date()
            tanggal_akhir = parse_date(rentang_match.group(2), dayfirst=True).date()

        else:
            return "⚠️ Format tidak dikenali. Gunakan:\n- rekap minggu ini\n- rekap minggu kemarin\n- rekap bulan ini\n- rekap bulan kemarin\n- rekap bulan [nama_bulan] [tahun opsional]\n- rekap bulan [nama_bulan] [tahun opsional] tanggal [tgl1] sampai [tgl2]\n- rekap dari [tgl] sampai [tgl]"

    except Exception as e:
        return f"❌ Gagal memproses tanggal: {e}"

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT site_name, tanggal, jam, isi_catatan, status, tanggal_selesai
                    FROM {TABLE_NAME}
                    WHERE isi_catatan IS NOT NULL
                    ORDER BY site_name, tanggal, jam
                """)
                rows = cur.fetchall()

        if not rows:
            return "📭 Tidak ada catatan ditemukan di database."

        hasil = []
        site_summary = defaultdict(lambda: {"total": 0, "selesai": 0, "aktif": 0, "catatan": []})
        catatan_terstruktur = []

        for site, tgl, jam, isi, status, tgl_selesai in rows:
            try:
                tgl_date = parse_date(tgl, dayfirst=True).date()
            except:
                continue
            if not (tanggal_awal <= tgl_date <= tanggal_akhir):
                continue
            simbol = "✅" if status == "selesai" else "⏳"
            selesai_info = f"\n📌 selesai: {tgl_selesai}" if status == "selesai" and tgl_selesai else ""
            poin = [p.strip() for p in isi.strip().splitlines() if p.strip()]

            site_data = site_summary[site]
            site_data["total"] += 1
            site_data["selesai"] += 1 if status == "selesai" else 0
            site_data["aktif"] += 1 if status != "selesai" else 0
            for p in poin:
                site_data["catatan"].append(f"📅 {tgl} - ⏰ {jam or '-'}\n{simbol} {p}{selesai_info}")
                catatan_terstruktur.append({
                    "tanggal": tgl,
                    "jam": jam or "-",
                    "isi": p,
                    "status": status,
                    "tanggal_selesai": tgl_selesai
                })

        hasil.append(f"📊 **Rekap Catatan ({tanggal_awal.strftime('%d %B')} – {tanggal_akhir.strftime('%d %B %Y')}):**\n")
        for site, data in site_summary.items():
            hasil.append(f"### 📍 {site.upper()}\nTotal: {data['total']} | ✅ Selesai: {data['selesai']} | ⏳ Aktif: {data['aktif']}\n")
            hasil.extend(data["catatan"])
            hasil.append("")

        user_sessions[user_id] = {
            "site": "REKAP_CATATAN",
            "catatan": catatan_terstruktur,
            "last_site": "REKAP_CATATAN"
        }

        return format_notulensi_to_markdown("\n".join(hasil))

    except Exception as e:
        return f"❌ Gagal mengambil data dari database: {e}"