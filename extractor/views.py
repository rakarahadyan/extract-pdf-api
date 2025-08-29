# extractor/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
import os
from django.conf import settings
from .utils import extract_pib, extract_sppb

class ExtractDocumentsView(APIView):
    def post(self, request):
        try:
            # ambil data text
            tps_code = request.data.get("kode_tps")
            jumlah_sppb = int(request.data.get("jumlah_sppb", 0))

            # ambil file PIB
            pib_file = request.FILES.get("file_pib")

            # ambil semua file sppb sesuai jumlah_sppb
            sppb_files = []
            for i in range(1, jumlah_sppb + 1):
                f = request.FILES.get(f"file_sppb_{i}")
                if f:
                    sppb_files.append(f)

            # validasi sederhana
            if not (tps_code and pib_file and sppb_files):
                return Response({
                    "status": False,
                    "message": "kode_tps, file_pib, dan file_sppb wajib dikirim",
                    "pib": None,
                    "sppb": None
                }, status=status.HTTP_400_BAD_REQUEST)

            # folder simpan
            base_dir = os.path.join(settings.MEDIA_ROOT, "documents", tps_code)
            os.makedirs(base_dir, exist_ok=True)

            # simpan PIB
            pib_path = os.path.join(base_dir, pib_file.name)
            with open(pib_path, "wb+") as f:
                for chunk in pib_file.chunks():
                    f.write(chunk)

            # ekstraksi PIB
            pib_result = extract_pib(pib_path)

            # simpan & ekstrak semua SPPB
            sppb_results = []
            for sppb_file in sppb_files:
                sppb_path = os.path.join(base_dir, sppb_file.name)
                with open(sppb_path, "wb+") as f:
                    for chunk in sppb_file.chunks():
                        f.write(chunk)

                # ekstraksi tiap file
                sppb_results.append(extract_sppb(sppb_path))

            return Response({
                "status": True,
                "message": "Ekstraksi berhasil",
                "pib": pib_result,
                "sppb": sppb_results
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                "status": False,
                "message": f"Terjadi kesalahan: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
