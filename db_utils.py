# db_utils.py
import psycopg2
from datetime import datetime
import json

# Simpan session aktif di memory untuk caching cepat (opsional)
user_sessions = {}

DB_CONFIG = dict(
    host="localhost",
    port=.......,
    database=".....",
    user="......",
    password=".....",
)

def get_db_connection():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except Exception as e:
        print(f"❌ Gagal koneksi ke DB: {e}")
        raise

# ======================== SESSION FUNCTIONS ========================

def init_sessions_table():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    user_id TEXT PRIMARY KEY,
                    site TEXT,
                    catatan TEXT,
                    last_txt_path TEXT,
                    last_pdf_path TEXT,
                    last_site TEXT,  -- ✅ tambahkan ini
                    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.commit()

def save_user_session(user_id, site=None, catatan=None, last_site=None, last_txt_path=None, last_pdf_path=None):
    try:
        last_activity = datetime.now().isoformat()

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO sessions (user_id, site, catatan, last_site, last_txt_path, last_pdf_path, last_activity)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (user_id) DO UPDATE SET
                        site = EXCLUDED.site,
                        catatan = EXCLUDED.catatan,
                        last_site = EXCLUDED.last_site,
                        last_txt_path = EXCLUDED.last_txt_path,
                        last_pdf_path = EXCLUDED.last_pdf_path,
                        last_activity = EXCLUDED.last_activity;
                """, (
                    user_id,
                    site,
                    json.dumps(catatan or []),  # pastikan list/dict jadi string
                    last_site,
                    last_txt_path,
                    last_pdf_path,
                    last_activity
                ))
            conn.commit()

        # Simpan juga di cache memory
        user_sessions[user_id] = {
            "site": site,
            "catatan": catatan or [],
            "last_txt_path": last_txt_path,
            "last_site": last_site,
            "last_pdf_path": last_pdf_path,
            "last_activity": last_activity
        }

        print(f"✅ Session untuk user_id={user_id} berhasil disimpan.")

    except Exception as e:
        print(f"❌ Gagal simpan session: {e}")
        
def load_user_session(user_id: str):
    """
    Ambil data session user dari tabel sessions.
    """
    # Cek di cache memory dulu
    if user_id in user_sessions:
        return user_sessions[user_id]

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT site, catatan, last_txt_path, last_site, last_activity
            FROM sessions
            WHERE user_id = %s
        """, (user_id,))
        row = cur.fetchone()
        if row:
            session_data = {
                "site": row[0],
                "catatan": row[1],
                "last_txt_path": row[2],
                "last_site": row[3],
                "last_activity": row[4]
            }
            user_sessions[user_id] = session_data
            return session_data
        return None
    except Exception as e:
        print(f"❌ Gagal ambil session: {e}")
        return None
    finally:
        cur.close()
        conn.close()

def delete_user_session(user_id: str):
    """
    Hapus data session user (misal saat reset chat).
    """
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM sessions WHERE user_id = %s", (user_id,))
        conn.commit()
        user_sessions.pop(user_id, None)
        print(f"✅ Session untuk user_id={user_id} berhasil dihapus.")
    except Exception as e:
        print(f"❌ Gagal hapus session: {e}")
    finally:
        cur.close()
        conn.close()

# ======================== CATATAN SITE FUNCTIONS ========================

def simpan_catatan_site(site_name: str, isi_catatan: str):
    """
    Simpan catatan site ke tabel catatan_site.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO catatan_site (site_name, isi_catatan) VALUES (%s, %s)",
            (site_name, isi_catatan)
        )
        conn.commit()
        print("✅ Catatan berhasil disimpan ke DB.")
    except Exception as e:
        print(f"❌ Gagal simpan catatan: {e}")
    finally:
        cur.close()
        conn.close()


