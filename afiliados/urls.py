from django.urls import path
from .views import BuscarAfiliadoView, BuscarRetencionView

app_name = 'afiliados'

urlpatterns = [
    path('atencion/<str:dni>/', BuscarAfiliadoView.as_view(), name='buscar_afiliado'),
    path('retencion/<str:dni>/', BuscarRetencionView.as_view(), name='buscar_retencion'),
]