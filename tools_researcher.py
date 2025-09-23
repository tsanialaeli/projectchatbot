print("===== SEDANG MENGIMPOR tools_researcher.py =====")
from db_utils import get_db_connection
from rapidfuzz import process
import re

TABLE_SITE = "site_name"
site_names_from_db = []


def load_all_site_names():
    global site_names_from_db
    print("📥 Memuat site_name dari tabel site_name...")

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT DISTINCT site_name 
                    FROM {TABLE_SITE}
                    WHERE site_name IS NOT NULL;
                """)
                site_names_from_db = [row[0] for row in cur.fetchall()]
                print(f"✅ {len(site_names_from_db)} site_name berhasil dimuat.")
    except Exception as e:
        print(f"❌ Error load site_name: {e}")


def query_site_from_db(full_query: str) -> str:
    print(f"🛠 Tool 'query_site_from_db' dipanggil dengan query: '{full_query}'")

    # LANGKAH 1: Ekstrak keyword
    words_to_ignore = {
        "daftar", "nama", "site", "di", "lokasi", "apa", "id", "dari", "yang",
        "ada", "berada", "untuk", "dan", "cari", "saja", "kode", "wilayah",
        "mengandung"
    }

    words = re.findall(r'\b\w+\b', full_query.lower())
    filtered_words = [word for word in words if word not in words_to_ignore]
    extracted_keyword = " ".join(filtered_words)

    if not extracted_keyword or len(extracted_keyword) < 3:
        return "❗ Pertanyaan terlalu pendek atau tidak spesifik. Coba sebutkan nama lokasi atau site yang lengkap."

    print(f"🔍 Keyword diekstrak: '{extracted_keyword}'")

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # LANGKAH 2: Coba cari berdasarkan site_id
                cur.execute(f"""
                    SELECT site_id, site_name
                    FROM {TABLE_SITE}
                    WHERE site_id ILIKE %s
                    ORDER BY site_id ASC
                """, (f"{extracted_keyword}%",))
                site_id_results = cur.fetchall()

                if site_id_results:
                    response = f"✅ Ditemukan {len(site_id_results)} site dengan site_id diawali '{extracted_keyword}':\n"
                    for site_id, site_name in site_id_results:
                        response += f"- Nama: {site_name}, ID: {site_id}\n"
                    return response.strip()

                # LANGKAH 3: Cari di site_name pakai fuzzy match
                corrected_name, score, _ = process.extractOne(extracted_keyword, site_names_from_db)

                if score > 75:
                    search_term = corrected_name
                    print(f"✅ Fuzzy match: '{extracted_keyword}' → '{search_term}' (Skor: {score})")
                else:
                    search_term = extracted_keyword
                    print(f"⚠ Tidak ada fuzzy match yang kuat. Menggunakan keyword asli: '{search_term}'")

                cur.execute(f"""
                    SELECT site_id, site_name
                    FROM {TABLE_SITE}
                    WHERE site_name ILIKE %s
                    ORDER BY site_name ASC
                """, (f"%{search_term}%",))
                site_name_results = cur.fetchall()

                if site_name_results:
                    response = f"✅ Ditemukan {len(site_name_results)} site dengan site_name mengandung '{search_term}':\n"
                    for site_id, site_name in site_name_results:
                        response += f"- Nama: {site_name}, ID: {site_id}\n"
                    return response.strip()

                # Jika tidak ada hasil dari semua cara
                return f"❌ Tidak ditemukan site dengan ID atau nama yang cocok untuk '{extracted_keyword}'."

    except Exception as e:
        print(f"❌ Terjadi error pada database: {e}")
        return f"❌ Terjadi kesalahan saat mengakses database: {str(e)}"


def is_existing_site(site: str) -> bool:
    site = site.strip().lower()
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT 1
                    FROM {TABLE_SITE}
                    WHERE LOWER(site_name) = %s OR LOWER(site_id) = %s
                    LIMIT 1
                """, (site, site))
                return cur.fetchone() is not None
    except Exception as e:
        print(f"❌ Error validasi site: {e}")
        return False