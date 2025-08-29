from django.urls import path
from .views import ExtractDocumentsView

urlpatterns = [
    path("extract/", ExtractDocumentsView.as_view(), name="extract-documents"),
]
