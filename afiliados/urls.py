from django.urls import path
from .views import BuscarAfiliadoView, BuscarRetencionView, cotizar_actual

app_name = 'afiliados'

urlpatterns = [
    path('atencion//', BuscarAfiliadoView.as_view(), name='buscar_afiliado'), # Sin DNI
    path('atencion/<str:dni>/', BuscarAfiliadoView.as_view(), name='buscar_afiliado'),
    path('retencion//', BuscarRetencionView.as_view(), name='buscar_retencion'), # Sin DNI
    path('retencion/<str:dni>/', BuscarRetencionView.as_view(), name='buscar_retencion'),
    path('api/cotizar/', cotizar_actual, name='cotizar_actual'),
]