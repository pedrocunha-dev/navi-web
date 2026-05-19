from django.urls import path
from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("status/", views.scraping_status, name="scraping_status"),
    path("unificar/", views.unificar_arquivos, name="unificar_arquivos"),
    path("download/<str:filename>/", views.download_tmp, name="download_tmp"),
    path("unificar/planilhas/", views.unificar_planilhas, name="unificar_planilhas"),
    path("unificar/relatorios/", views.unificar_relatorios, name="unificar_relatorios"),
    path("cancelar/", views.cancelar_raspagem, name="cancelar_raspagem"),
    path("limpar-tmp/", views.limpar_tmp, name="limpar_tmp"),
    path("configuracoes/", views.configuracoes, name="configuracoes"),
]