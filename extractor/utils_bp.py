import pdfplumber
import re
import sys

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
        "muat": muat.group(1).strip() if muat else None,
        "transit": transit.group(1).strip() if transit else None,
        "tujuan": tujuan.group(1).strip() if tujuan else None
    }

    # barang_list = []

    # # Barang jamak (lebih dari 1 item, biasanya di halaman 2 dst)
    # pattern_multi = r"(\d{4,8})\s+Kode Brg.*?BYR\s+([\d\.,-]+)\s*-\s*([\d\.,-]+).*?Uraian\s*:(.*?)Kondisi Brg\s*:\s*([A-Z]+).*?Negara\s*:\s*([A-Z\s\(\),]+)"
    # matches = re.finditer(pattern_multi, all_text, re.S)

    # for match in matches:
    #     hs_code = match.group(1).strip()
    #     qty = match.group(2).replace(",", "").strip()
    #     nilai_pabean = match.group(3).replace(",", "").strip()
    #     uraian = re.sub(r"\s+", " ", match.group(4).strip())
    #     kondisi = match.group(5).strip()
    #     negara = match.group(6).strip()
    #     barang_list.append({
    #         "hs_code": hs_code,
    #         "qty": qty,
    #         "nilai_pabean": nilai_pabean,
    #         "uraian": uraian,
    #         "kondisi": kondisi,
    #         "negara": negara
    #     })

    # # Jika belum ketemu (artinya barang tunggal di halaman 1)
    # if not barang_list:
    #     pattern_single = r"Pos Tarif\s*:\s*(\d{8}).*?BYR\s+([\d\.,-]+)\s*-\s*([\d\.,-]+).*?Uraian\s*:(.*?)Kondisi Brg\s*:\s*([A-Z]+).*?Negara\s*:\s*([A-Z\s\(\),]+)"
    #     matches = re.finditer(pattern_single, all_text, re.S)

    #     for match in matches:
    #         hs_code = match.group(1).strip()
    #         qty = match.group(2).replace(",", "").strip()
    #         nilai_pabean = match.group(3).replace(",", "").strip()
    #         uraian = re.sub(r"\s+", " ", match.group(4).strip())
    #         kondisi = match.group(5).strip()
    #         negara = match.group(6).strip()
    #         barang_list.append({
    #             "hs_code": hs_code,
    #             "qty": qty,
    #             "nilai_pabean": nilai_pabean,
    #             "uraian": uraian,
    #             "kondisi": kondisi,
    #             "negara": negara
    #         })

    # data_extracted["barang"] = barang_list
    
    # === Data Barang ===
    barang_list = []

    # --- Format Lama ---
    pattern_lama = r"(\d{4,8})\s+Kode Brg.*?BYR\s+([\d\.,-]+)\s*-\s*([\d\.,-]+).*?Uraian\s*:(.*?)Kondisi Brg\s*:\s*([A-Z]+).*?Negara\s*:\s*([A-Z\s\(\)]+)"
    matches = re.finditer(pattern_lama, all_text, re.S)

    for match in matches:
        hs_code = match.group(1).strip()
        qty = float(match.group(2).replace(",", "").replace("-", ""))
        nilai_pabean = float(match.group(3).replace(",", "").replace("-", ""))
        uraian = re.sub(r"\s+", " ", match.group(4).strip())
        kondisi = match.group(5).strip()
        negara = match.group(6).strip()

        # Cari kode satuan
        start, end = match.span()
        context = all_text[end:end+200]
        satuan_match = re.search(r"([A-Z ]+)\s*\(([A-Z0-9\- ]+)\)", uraian + " " + context)
        kode_satuan = satuan_match.group(1).strip() if satuan_match else None

        barang_list.append({
            "uraian": uraian,
            "kondisi": kondisi,
            "negara": negara,
            "hs_code": hs_code,
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
            qty = float(match.group(2).replace(",", "").replace("-", ""))
            nilai_pabean = float(match.group(3).replace(",", "").replace("-", ""))
            uraian = re.sub(r"\s+", " ", match.group(4).strip())
            kondisi = match.group(5).strip()
            negara = match.group(6).strip()

            # Cari kode satuan
            start, end = match.span()
            context = all_text[end:end+200]
            satuan_match = re.search(r"([A-Z ]+)\s*\(([A-Z0-9\- ]+)\)", uraian + " " + context)
            kode_satuan = satuan_match.group(1).strip() if satuan_match else None

            barang_list.append({
                "uraian": uraian,
                "kondisi": kondisi,
                "negara": negara,
                "hs_code": hs_code,
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
    m = re.search(r"No\.?\s*BC\s*1\.1\s*:\s*([0-9]+)\s*Tanggal\s*:\s*([0-9\-]+)\s*Pos\s*:\s*([^\n]*)", all_text, re.I)
    if m:
        data["bc11"] = {
            "nomor": _clean(m.group(1)),
            "tanggal": _clean(m.group(2)),
            "pos": _clean(m.group(3))
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

