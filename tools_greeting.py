def handle_greeting(query: str) -> str:
    """Menangani sapaan dan ucapan terima kasih dari pengguna."""
    query = query.lower() # Ubah ke huruf kecil agar tidak case-sensitive
    
    if "terima kasih" in query or "makasih" in query:
        return "Sama-sama! Senang bisa membantu."
    elif "halo" in query or "hai" in query or "hei" in query:
        return "Halo! Ada yang bisa aku bantu terkait informasi site?"
    else:
        # Jawaban default jika tidak cocok
        return "Ada yang bisa aku bantu terkait informasi site Central Java?"