import pdfplumber
import re
import sys

def extract_bl_awb(all_text):
    """
    Cari House-BL/AWB dan Master-BL/AWB di text dokumen.
    """
    result = {
        "house_bl_awb": None,
        "master_bl_awb": None,
    }

    # Pola langsung (angka/huruf campuran panjang, bisa ada slash)
    m = re.search(r"House[-\s]?BL/AWB\s*:?\s*([A-Z0-9/.-]+)", all_text, flags=re.I)
    if m:
        house_bl_awb = m.group(1).strip()
        result["house_bl_awb"] = house_bl_awb[3:]

    m = re.search(r"Master[-\s]?BL/AWB\s*:?\s*([A-Z0-9/.-]+)", all_text, flags=re.I)
    if m:
        master_bl_awb = m.group(1).strip()
        result["master_bl_awb"] = master_bl_awb[3:]

    return result

def extract_sarana_pengangkutan_main(all_text):
    # 1) Kumpulkan baris antara "10. Nama Sarana Pengangkutan..." s/d poin berikutnya (mis. "11.")
    
    lines = all_text.splitlines()
    start_idx = None
    for i, line in enumerate(lines):
        if line.strip().startswith("10. Nama Sarana Pengangkutan"):
            start_idx = i
            break

    result = {
        "kode_bendera": None,   # e.g. US, ID, PA
        "negara": None,         # e.g. GERMANY, JAPAN, TAIWAN
        "nama": None,           # e.g. FEDERAL EXPRESS CORPORATION, MY INDO AIRLINES, EVER BOOMY
        "voyage_flight": None,  # e.g. FX5194, 2Y6011, 1147-082A
        "bendera": None,        # e.g. UNITED STATES, INDONESIA, PANAMA
    }

    if start_idx is None:
        return result

    # Ambil tail di baris label (mungkin berisi kode bendera, mis. "… Bendera PA")
    label_line = lines[start_idx]
    tail = re.sub(r"^10\.\s*Nama Sarana Pengangkutan\s*&\s*No\.\s*Voy/Flight\s*dan\s*Bendera\s*:?", "", label_line, flags=re.I).strip()

    block = []
    if tail:
        block.append(tail)

    # Himpun baris berikutnya sampai ketemu next point (mis. "11.", "12.", dst)
    for j in range(start_idx + 1, len(lines)):
        s = lines[j].strip()
        if re.match(r"^\d{1,2}\.\s", s):  # berhenti saat heading poin berikutnya
            break
        block.append(s)

    # Bersihkan: buang kosong & noise (contoh "PENJUAL SG/TW/DE")
    cleaned = []
    for s in block:
        s2 = s.strip()
        if not s2:
            continue
        if s2.upper().startswith("PENJUAL"):
            continue
        cleaned.append(s2)

    if not cleaned:
        return result

    # ---- Heuristik 0: kode_bendera dari tail/first token yang hanya 2-3 huruf kapital ----
    # contoh: "PA", "US", "ID" di tail atau baris pertama
    def take_country_code_from(text):
        m = re.match(r"^([A-Z]{2,3})$", text.strip())
        return m.group(1) if m else None

    # Jika tail berupa "PA/US/ID", tandai sebagai kode_bendera & drop dari list
    if result["kode_bendera"] is None and cleaned:
        code = take_country_code_from(cleaned[0])
        if code:
            result["kode_bendera"] = code
            cleaned = cleaned[1:]  # buang baris tersebut

    # Cadangan: jika tail di label memuat kode bendera nyelip (mis. “… Bendera US”)
    if result["kode_bendera"] is None and tail:
        m = re.search(r"\b([A-Z]{2,3})\b$", tail)
        if m:
            result["kode_bendera"] = m.group(1)

    # ---- Heuristik 1: deteksi line flight + bendera (format paling stabil) ----
    # Cocok: "FX5194 UNITED STATES", "2Y6011 INDONESIA", "1147-082A PANAMA"
    flight_idx = None
    for idx, s in enumerate(cleaned):
        m = re.match(r"^([A-Z0-9]{1,4}\d{2,6}(?:-[A-Z0-9]+)?)\s+([A-Z][A-Z\s,]+)$", s)
        if m:
            result["voyage_flight"] = m.group(1)
            result["bendera"] = m.group(2).strip()
            flight_idx = idx
            break

    # ---- Heuristik 2: mapping negara & nama ----
    # Pola umum multi-line:
    #   [NEGARA]
    #   [NAMA]
    #   [FLIGHT + BENDERA]
    #
    # Jadi jika kita temukan flight line pada index k, maka nama ≈ cleaned[k-1], negara ≈ cleaned[k-2] (jika ada).
    if flight_idx is not None:
        if flight_idx - 1 >= 0 and not result["nama"]:
            result["nama"] = cleaned[flight_idx - 1]
        if flight_idx - 2 >= 0 and not result["negara"]:
            # Ambil yang uppercase dan tanpa digit agar cenderung negara
            cand = cleaned[flight_idx - 2]
            if re.match(r"^[A-Z][A-Z\s,\.()-]+$", cand) and not re.search(r"\d", cand):
                result["negara"] = cand

    # ---- Heuristik 3: jika flight belum ketemu, coba INLINE flatten (Format 1) ----
    if result["voyage_flight"] is None:
        flat = " ".join(cleaned)
        # Contoh inline: "US GERMANY FEDERAL EXPRESS CORPORATION FX5194 UNITED STATES"
        m = re.search(
            r"\b([A-Z]{2,3})\s+([A-Z][A-Z\s,]+?)\s+([A-Z0-9\s\.\-&]+?)\s+([A-Z0-9]{1,4}\d{2,6}(?:-[A-Z0-9]+)?)\s+([A-Z][A-Z\s,]+)\b",
            flat
        )
        if m:
            # Jangan menimpa kode_bendera kalau sudah ada dari tail, kecuali kosong
            if result["kode_bendera"] is None:
                result["kode_bendera"] = m.group(1).strip()
            if result["negara"] is None:
                result["negara"] = m.group(2).strip()
            if result["nama"] is None:
                result["nama"] = m.group(3).strip()
            result["voyage_flight"] = m.group(4).strip()
            result["bendera"] = m.group(5).strip()

    # ---- Heuristik 4: jika negara/nama masih kosong, isi konservatif dari urutan awal ----
    # Setelah buang flight line, urutan paling sering: [NEGARA][NAMA]
    if result["negara"] is None or result["nama"] is None:
        # Buang baris flight dari list kerja
        work = cleaned[:]
        if flight_idx is not None:
            work.pop(flight_idx)
        # Ambil negara kandidat pertama yang uppercase-only (tanpa digit)
        if result["negara"] is None:
            for s in work:
                if re.match(r"^[A-Z][A-Z\s,\.()-]+$", s) and not re.search(r"\d", s):
                    result["negara"] = s
                    break
        # Nama: baris uppercase yang bukan negara dan bukan kode 2-3 huruf
        if result["nama"] is None:
            for s in work:
                if not re.search(r"\d", s) and not re.match(r"^[A-Z]{2,3}$", s):
                    # Hindari memilih negara jika sudah terisi dan s == negara
                    if result["negara"] and s == result["negara"]:
                        continue
                    result["nama"] = s
                    break

    return result

def extract_sarana_pengangkutan_subs(all_text):
    # 1) Kumpulkan baris antara "10. Nama Sarana Pengangkutan..." s/d poin berikutnya (mis. "11.")
    lines = all_text.splitlines()
    start_idx = None
    for i, line in enumerate(lines):
        if line.strip().startswith("10. Nama Sarana Pengangkutan"):
            start_idx = i
            break

    result = {
        "kode_bendera": None,   # e.g. US, ID, PA
        "negara": None,         # e.g. GERMANY, JAPAN, TAIWAN
        "nama": None,           # e.g. FEDERAL EXPRESS CORPORATION, MY INDO AIRLINES, EVER BOOMY
        "voyage_flight": None,  # e.g. FX5194, 2Y6011, 1147-082A, 3
        "bendera": None,        # e.g. UNITED STATES, INDONESIA, PANAMA
    }

    if start_idx is None:
        return result

    # Ambil tail di baris label (mungkin berisi kode bendera, mis. "… Bendera PA")
    label_line = lines[start_idx]
    tail = re.sub(r"^10\.\s*Nama Sarana Pengangkutan\s*&\s*No\.\s*Voy/Flight\s*dan\s*Bendera\s*:?", "", label_line, flags=re.I).strip()

    block = []
    if tail:
        block.append(tail)

    # Himpun baris berikutnya sampai ketemu next point (mis. "11.", "12.", dst)
    for j in range(start_idx + 1, len(lines)):
        s = lines[j].strip()
        if re.match(r"^\d{1,2}\.\s", s):  # berhenti saat heading poin berikutnya
            break
        block.append(s)

    # Bersihkan: buang kosong & noise (contoh "PENJUAL SG/TW/DE")
    cleaned = []
    for s in block:
        s2 = s.strip()
        if not s2:
            continue
        if s2.upper().startswith("PENJUAL"):
            continue
        cleaned.append(s2)

    if not cleaned:
        return result

    def take_country_code_from(text):
        m = re.match(r"^([A-Z]{2,3})$", text.strip())
        return m.group(1) if m else None

    # Jika baris pertama cuma kode 2-3 huruf, ambil sebagai kode_bendera
    if result["kode_bendera"] is None and cleaned:
        code = take_country_code_from(cleaned[0])
        if code:
            result["kode_bendera"] = code
            cleaned = cleaned[1:]

    # Cadangan: jika tail di label memuat kode bendera nyelip (mis. “… Bendera US”)
    if result["kode_bendera"] is None and tail:
        m_tail = re.search(r"\b([A-Z]{2,3})\b$", tail)
        if m_tail:
            result["kode_bendera"] = m_tail.group(1)

    # ---- Heuristik tambahan: cek pola 'angka saja' atau 'angka + negara' ----
    flight_idx = None
    for idx, s in enumerate(cleaned):
        # pola: "3 PANAMA" atau "12 INDONESIA"
        m_num_country = re.match(r"^(\d{1,4})\s+([A-Z][A-Z\s,]+)$", s)
        if m_num_country:
            result["voyage_flight"] = m_num_country.group(1).strip()
            result["bendera"] = m_num_country.group(2).strip()
            flight_idx = idx
            break

        # pola: baris hanya angka (contoh "3") — kemungkinan next line adalah negara/bendera
        m_only_num = re.match(r"^(\d{1,4})\s*$", s)
        if m_only_num:
            result["voyage_flight"] = m_only_num.group(1).strip()
            # jika ada baris berikutnya, ambil sebagai bendera bila cocok
            if idx + 1 < len(cleaned):
                cand = cleaned[idx + 1]
                if re.match(r"^[A-Z][A-Z\s,]+$", cand):
                    result["bendera"] = cand.strip()
                    flight_idx = idx
                    break
            # jika tidak ada bendera di next line, kita tetap terima voyage
            flight_idx = idx
            break

    # ---- Heuristik standar: flight + bendera (airline+angka, angka-dash, dll) ----
    if result["voyage_flight"] is None:
        for idx, s in enumerate(cleaned):
            # pola 1: Airline code + angka (FX5194, 2Y6011)
            m = re.match(r"^([A-Z]{1,3}\d{2,6})\s+([A-Z][A-Z\s,]+)$", s)
            if not m:
                # pola 2: numeric + dash/alfanumerik (1147-082A)
                m = re.match(r"^(\d{1,6}(?:-[A-Z0-9]+)?)\s+([A-Z][A-Z\s,]+)$", s)
            if not m:
                # pola 3: kombinasi lain (ambil jika ada huruf+angka)
                m = re.match(r"^([A-Z0-9]{2,8})\s+([A-Z][A-Z\s,]+)$", s)

            if m:
                # cegah menangkap baris yang jelas bukan flight (mis: '1 PACKAGE' atau '1 BULK' -> cek kata kedua bukan 'PACKAGE'/'BULK'/'FCL')
                second_token = m.group(2).split()[0] if m.group(2) else ""
                if second_token.upper() in ("PACKAGE", "BULK", "FCL", "KG", "PKG"):
                    continue
                result["voyage_flight"] = m.group(1).strip()
                result["bendera"] = m.group(2).strip()
                flight_idx = idx
                break

    # ---- Heuristik mapping negara & nama (berdasarkan posisi flight_idx) ----
    if flight_idx is not None:
        # nama biasanya baris sebelum flight
        if flight_idx - 1 >= 0 and not result["nama"]:
            candidate_name = cleaned[flight_idx - 1]
            # Hindari memilih sesuatu yang terlihat seperti kode (2-3 huruf) atau angka
            if not re.match(r"^[A-Z]{2,3}$", candidate_name) and not re.search(r"\d", candidate_name):
                result["nama"] = candidate_name
        # negara biasanya baris sebelum nama
        if flight_idx - 2 >= 0 and not result["negara"]:
            cand = cleaned[flight_idx - 2]
            if re.match(r"^[A-Z][A-Z\s,\.()-]+$", cand) and not re.search(r"\d", cand):
                result["negara"] = cand

    # ---- Heuristik inline (satu baris flatten) jika masih kosong ----
    if result["voyage_flight"] is None:
        flat = " ".join(cleaned)
        m = re.search(
            r"\b([A-Z]{2,3})\s+([A-Z][A-Z\s,]+?)\s+([A-Z0-9\s\.\-&]+?)\s+([A-Z0-9]{1,4}\d{1,6}(?:-[A-Z0-9]+)?)\s+([A-Z][A-Z\s,]+)\b",
            flat
        )
        if m:
            if result["kode_bendera"] is None:
                result["kode_bendera"] = m.group(1).strip()
            if result["negara"] is None:
                result["negara"] = m.group(2).strip()
            if result["nama"] is None:
                result["nama"] = m.group(3).strip()
            result["voyage_flight"] = m.group(4).strip()
            result["bendera"] = m.group(5).strip()

    # ---- Fallback: jika negara/nama masih kosong, isi konservatif dari urutan awal ----
    if result["negara"] is None or result["nama"] is None:
        work = cleaned[:]
        if flight_idx is not None and 0 <= flight_idx < len(work):
            # jika flight line terdeteksi, hapus untuk deduksi nama/negara
            try:
                work.pop(flight_idx)
            except Exception:
                pass
        # negara kandidat pertama yang uppercase-only (tanpa digit)
        if result["negara"] is None:
            for s in work:
                if re.match(r"^[A-Z][A-Z\s,\.()-]+$", s) and not re.search(r"\d", s):
                    result["negara"] = s
                    break
        # nama: baris uppercase yang bukan negara dan bukan kode 2-3 huruf
        if result["nama"] is None:
            for s in work:
                if not re.search(r"\d", s) and not re.match(r"^[A-Z]{2,3}$", s):
                    if result["negara"] and s == result["negara"]:
                        continue
                    result["nama"] = s
                    break

    return result

def ambil_pelabuhan(match):
    if not match:
        return None
    teks = match.group(1).strip()
    parts = teks.split()
    return parts[-1] if parts else ""

def extract_pib(pdf_path):
    all_text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                all_text += "\n" + text

    data_extracted = {}

    # === Data Umum ===
    m = re.search(r"Nomor Pengajuan\s*:([0-9]+)\s*Tanggal Pengajuan\s*:([0-9-]+)", all_text)
    if m:
        data_extracted["nomor_pengajuan"] = m.group(1).strip()
        data_extracted["tanggal_pengajuan"] = m.group(2).strip()

    m = re.search(r"Kantor Pabean\s*:([A-Z0-9\s\-\.\(\)]+)", all_text)
    if m:
        data_extracted["kantor_pabean"] = m.group(1).strip()

    # Importir
    identitas = re.search(r"2\. Identitas\s*:\s*([0-9 /]+)", all_text)
    nama_alamat = re.search(r"3\. Nama, Alamat\s*:(.*?)\n", all_text, re.S)
    nib = re.search(r"5\. NIB\s*:\s*([0-9]+)", all_text)

    data_extracted["importir"] = {
        "identitas": identitas.group(1).strip() if identitas else None,
        "nama": None,
        "alamat": None,
        "nib": nib.group(1).strip() if nib else None
    }
    if nama_alamat:
        parts = nama_alamat.group(1).strip().split("\n", 1)
        if len(parts) == 2:
            data_extracted["importir"]["nama"] = parts[0].strip()
            data_extracted["importir"]["alamat"] = parts[1].strip()
        else:
            data_extracted["importir"]["nama"] = parts[0].strip()

    # Invoice
    m = re.search(r"15\. Invoice\s*: No\. ([0-9]+)\s*Tgl\.([0-9-]+)", all_text)
    if m:
        data_extracted["invoice_no"] = m.group(1).strip()
        data_extracted["invoice_date"] = m.group(2).strip()

    # Perkiraan Tanggal Tiba
    m = re.search(r"11\. Perkiraan Tanggal Tiba\s*:([0-9-]+)", all_text)
    if m:
        data_extracted["perkiraan_tiba"] = m.group(1).strip()

    # Pelabuhan muat / transit / tujuan
    muat = re.search(r"12\. Pelabuhan Muat\s*:(.*?)\n", all_text)
    transit = re.search(r"13\. Pelabuhan Transit\s*:(.*?)\n", all_text)
    tujuan = re.search(r"14\. Pelabuhan Tujuan\s*:(.*?)\n", all_text)

    data_extracted["pelabuhan"] = {
        "muat": ambil_pelabuhan(muat),
        "transit": ambil_pelabuhan(transit),
        "tujuan": ambil_pelabuhan(tujuan),
    }

    sarana_main = extract_sarana_pengangkutan_main(all_text)

    if sarana_main.get("voyage_flight") is None:
        sarana_main = extract_sarana_pengangkutan_subs(all_text)

    data_extracted["sarana_pengangkutan"] = sarana_main

    m = re.search(r"Nomor\s*:\s*([0-9]+)\s*Tanggal\s*:\s*([0-9-]+)", all_text)
    if m:
        data_extracted["pendaftaran"] = {
            "nomor": m.group(1).strip(),
            "tanggal": m.group(2).strip()
        }
    else:
        # fallback kalau format tanpa "Nomor :" 
        m = re.search(r"Nomor dan Tanggal Pendaftaran\s*([0-9]+)\s*([0-9-]+)", all_text)
        if m:
            data_extracted["pendaftaran"] = {
                "nomor": m.group(1).strip(),
                "tanggal": m.group(2).strip()
            }

    data_extracted["bl_awb"] = extract_bl_awb(all_text)
    
    # === Data Barang ===
    barang_list = []

    # --- Format Lama ---
    pattern_lama = r"(\d{4,8})\s+Kode Brg.*?BYR\s+([\d\.,-]+)\s*-\s*([\d\.,-]+).*?Uraian\s*:(.*?)Kondisi Brg\s*:\s*([A-Z]+).*?Negara\s*:\s*([A-Z\s\(\)]+)"
    matches = re.finditer(pattern_lama, all_text, re.S)

    for match in matches:
        hs_code = match.group(1).strip()
        jumlah_satuan = match.group(2).strip().replace(",", "").replace(".", ",").replace("-", "")
        nilai_pabean = match.group(3).replace(",", "").replace("-", "")
        uraian = re.sub(r"\s+", " ", match.group(4).strip())
        kondisi = match.group(5).strip()
        negara = match.group(6).strip()

        # Ambil qty (dari Berat Bersih jika ada)
        qty_match = re.search(r"Berat Bersih\s*\(Kg\)\s*([\d\.,]+)", all_text)
        if qty_match:
            qty = qty_match.group(1).replace(",", "")
        else:
            qty = jumlah_satuan  # fallback

        # Cari kode satuan
        start, end = match.span()
        context = all_text[end:end+200]

        if re.search(r"\bMETRIC\s+TON\b", uraian, re.I) or re.search(r"\bMETRIC\s+TON\b", context, re.I):
            kode_satuan = "TNE"
        else:
            satuan_match = re.search(r"\(([A-Z0-9\-]+)\)", uraian)
            if not satuan_match:
                satuan_match = re.search(r"\(([A-Z0-9\-]+)\)", context)
            kode_satuan = satuan_match.group(1).strip() if satuan_match else None

        barang_list.append({
            "uraian": uraian,
            "kondisi": kondisi,
            "negara": negara,
            "hs_code": hs_code,
            "jumlah_satuan": jumlah_satuan, 
            "qty": qty,                     
            "kode_satuan": kode_satuan,
            "nilai_pabean": nilai_pabean
        })

    # --- Fallback Format Baru ---
    if not barang_list:
        pattern_baru = r"Pos Tarif\s*:\s*(\d{4,8}).*?BYR\s+([\d\.,-]+)\s*-\s*([\d\.,-]+)(.*?)Kondisi Brg\s*:\s*([A-Z]+).*?Negara\s*:\s*([A-Z\s\(\)]+)"
        matches = re.finditer(pattern_baru, all_text, re.S)
        for match in matches:
            hs_code = match.group(1).strip()
            jumlah_satuan = match.group(2).strip().replace(",", "").replace(".", ",").replace("-", "")
            nilai_pabean = match.group(3).replace(",", "").replace("-", "")
            uraian = re.sub(r"\s+", " ", match.group(4).strip())
            kondisi = match.group(5).strip()
            negara = match.group(6).strip()

            # Ambil qty (dari Berat Bersih jika ada)
            qty_match = re.search(r"Berat Bersih\s*\(Kg\)\s*([\d\.,]+)", all_text)
            if qty_match:
                qty = qty_match.group(1).replace(",", "")
            else:
                qty = jumlah_satuan  # fallback

            # Cari kode satuan
            start, end = match.span()
            context = all_text[end:end+200]

            # 1️⃣ Prioritas: cek METRIC TON
            if re.search(r"\bMETRIC\s+TON\b", uraian, re.I) or re.search(r"\bMETRIC\s+TON\b", context, re.I):
                kode_satuan = "TNE"
            else:
                # 2️⃣ Kalau tidak ada, cek (XXX)
                satuan_match = re.search(r"\(([A-Z0-9\-]+)\)", uraian)
                if not satuan_match:
                    satuan_match = re.search(r"\(([A-Z0-9\-]+)\)", context)
                kode_satuan = satuan_match.group(1).strip() if satuan_match else None


            barang_list.append({
                "uraian": uraian,
                "kondisi": kondisi,
                "negara": negara,
                "hs_code": hs_code,
                "jumlah_satuan": jumlah_satuan, 
                "qty": qty,
                "kode_satuan": kode_satuan,
                "nilai_pabean": nilai_pabean
            })

    data_extracted["barang"] = barang_list
    
    # Kalau barang tetap kosong → stop program
    if not barang_list:
        print("Ada kesalahan, Cek kembali isi dokumen.")
        sys.exit(1)

    return data_extracted

def _clean(val):
    if val is None:
        return None
    v = val.strip()
    if v == "" or v == "-":
        return None
    return v

def extract_sppb(pdf_path):
    # Gabungkan teks semua halaman
    all_text = ""
    lines = []
    with pdfplumber.open(pdf_path) as pdf:
        for p in pdf.pages:
            t = p.extract_text() or ""
            all_text += "\n" + t
            lines += [ln.rstrip() for ln in t.splitlines()]

    data = {}

    # --- SPPB header: Nomor & Tanggal ---
    m = re.search(r"SURAT PERSETUJUAN PENGELUARAN BARANG.*?\n\s*Nomor\s*:\s*([^\n]+?)\s*Tanggal\s*:\s*([0-9\-]+)", all_text, re.S)
    if m:
        data["sppb"] = {"nomor": _clean(m.group(1)), "tanggal": _clean(m.group(2))}

    # --- Pendaftaran PIB: Nomor & Tanggal ---
    m = re.search(r"Nomor Pendaftaran PIB\s*:\s*([0-9]+)\s*Tanggal\s*:\s*([0-9\-]+)", all_text)
    if m:
        data["pendaftaran_pib"] = {"nomor": _clean(m.group(1)), "tanggal": _clean(m.group(2))}

    # --- Nomor Aju ---
    m = re.search(r"Nomor aju\s*:\s*([0-9]+)", all_text, re.I)
    if m:
        data["nomor_aju"] = _clean(m.group(1))

    # ========= Importir block =========
    # Ambil blok dari kata 'Importir' sampai sebelum 'Lokasi Barang' (atau habis dokumen)
    imp_block = None
    bm = re.search(r"Kepada\s*:\s*.*?Importir(.*?)(?=\n\s*Lokasi Barang\s*:|\Z)", all_text, re.S | re.I)
    if bm:
        imp_block = bm.group(1)

    imp_npwp = imp_nitku = imp_nama = imp_alamat = None
    if imp_block:
        # Ambil NPWP pertama di blok ini = NPWP importir
        m = re.search(r"\bNPWP\s*:\s*([0-9\-]+)", imp_block)
        if m: imp_npwp = _clean(m.group(1))

        m = re.search(r"\bNITKU\s*:\s*([0-9]+)", imp_block)
        if m: imp_nitku = _clean(m.group(1))

        m = re.search(r"\bNama\s*:\s*(.*)", imp_block)
        if m: imp_nama = _clean(m.group(1))

        m = re.search(r"\bAlamat\s*:\s*(.*)", imp_block)
        if m: imp_alamat = _clean(m.group(1))

    data["importir"] = {
        "npwp": imp_npwp,
        "nitku": imp_nitku,
        "nama": imp_nama,
        "alamat": imp_alamat
    }

    # ========= PPJK block =========
    # Strategi: cari kemunculan kedua "NPWP :" setelah blok Importir.
    ppjk_npwp = ppjk_nama = ppjk_alamat = ppjk_np_ppjk = None
    npwp_iter = list(re.finditer(r"\bNPWP\s*:\s*(.*)", all_text))
    if len(npwp_iter) >= 2:
        start = npwp_iter[1].end()
        tail = all_text[start:]
        ppjk_npwp = _clean(npwp_iter[1].group(1))

        m = re.search(r"\bNama\s*:\s*(.*)", tail)
        if m: ppjk_nama = _clean(m.group(1))

        m = re.search(r"\bAlamat\s*:\s*(.*)", tail)
        if m: ppjk_alamat = _clean(m.group(1))

        m = re.search(r"\bNP\s*PPJK\s*:\s*(.*)", tail)
        if m: ppjk_np_ppjk = _clean(m.group(1))

    data["ppjk"] = {
        "npwp": ppjk_npwp,
        "nama": ppjk_nama,
        "alamat": ppjk_alamat,
        "np_ppjk": ppjk_np_ppjk
    }

    # --- Lokasi Barang ---
    m = re.search(r"Lokasi Barang\s*:\s*(.*)", all_text)
    if m:
        data["lokasi_barang"] = _clean(m.group(1))

    # --- AWB / BL + tanggal ---
    m = re.search(r"No\.?\s*B/?L atau AWB\s*\(Host\)\s*:\s*([^\s]+)\s*Tanggal\s*:\s*([0-9\-]+)", all_text, re.I)
    if m:
        data["awb"] = {"nomor": _clean(m.group(1)), "tanggal": _clean(m.group(2))}

    # --- Sarana Pengangkut + Flight ---
    m = re.search(r"Nama Sarana Pengangkut\s*:\s*(.*)", all_text)
    sarana = _clean(m.group(1)) if m else None

    m = re.search(r"No\.?\s*Voy\.?/Flight\s*:\s*([A-Z0-9]+)", all_text, re.I)
    flight = _clean(m.group(1)) if m else None

    data["sarana_pengangkut"] = {"nama": sarana, "voy_flight": flight}

    # --- BC 1.1 + Tgl + Pos ---
    m = re.search(r"No\.?\s*BC\s*1\.1\s*:\s*([0-9]+)\s*Tanggal\s*:\s*([0-9\-]+)", all_text, re.I)
    if m:
        nomor_bc11 = m.group(1).strip()
        tanggal_bc11 = m.group(2).strip()
        # cari nomor pos (12 digit) di sekitar baris ini
        before = all_text[max(0, m.start()-100):m.start()]
        after = all_text[m.end():m.end()+100]
        pos_match = re.search(r"\b\d{10,15}\b", before + "\n" + after)
        pos_val = pos_match.group(0) if pos_match else None

        data["bc11"] = {
            "nomor": nomor_bc11,
            "tanggal": tanggal_bc11,
            "pos": pos_val
        }

    # --- Kemasan, Berat, Peti Kemas ---
    # Jumlah/Jenis Kemasan bisa berada di satu baris yang sama dengan label "Berat :"
    m = re.search(r"Jumlah/jenis kemasan\s*:\s*([^\n]+)", all_text, re.I)
    jumlah_jenis_kemasan = None
    if m:
        raw = m.group(1)
        # potong jika ada "Berat :" di ujung baris
        raw = re.split(r"\s+Berat\s*:\s*", raw)[0]
        jumlah_jenis_kemasan = _clean(raw)

    m = re.search(r"Merk kemasan\s*:\s*(.*)", all_text, re.I)
    merk_kemasan = _clean(m.group(1)) if m else None

    m = re.search(r"Jumlah peti kemas\s*:\s*([0-9]+)", all_text, re.I)
    jumlah_pk = _clean(m.group(1)) if m else None

    m = re.search(r"Nomor Peti Kemas/Ukuran\s*:\s*(.*)", all_text, re.I)
    nomor_pk = _clean(m.group(1)) if m else None

    # Berat: jika "Berat :" tidak diikuti angka, cari angka 4 desimal di sekitar baris kemasan
    berat = None
    m = re.search(r"\bBerat\s*:\s*([0-9][0-9\.,]*)", all_text, re.I)
    if m:
        berat = _clean(m.group(1))
    else:
        # cari index baris 'Jumlah/jenis kemasan'
        idx = None
        for i, ln in enumerate(lines):
            if re.search(r"Jumlah/jenis kemasan", ln, re.I):
                idx = i
                break
        # cari angka d.dddd di 2 baris sebelum hingga 3 baris sesudah
        if idx is not None:
            rng_lo = max(0, idx - 2)
            rng_hi = min(len(lines), idx + 4)
            for j in range(rng_lo, rng_hi):
                mm = re.search(r"\b\d+\.\d{4}\b", lines[j])
                if mm:
                    berat = mm.group(0)
                    break

    data["kemasan"] = {
        "jumlah_jenis": jumlah_jenis_kemasan,
        "merk": merk_kemasan,
        "jumlah_peti_kemas": jumlah_pk,
        "nomor_peti_kemas_ukuran": nomor_pk,
        "berat": _clean(berat),
    }

    return data

