from django.urls import path
from .views import BuscarAfiliadoView, BuscarRetencionView, MesaDeEntradaView
from .views import guardar_expediente, archivo_expediente, cotizar_actual, descargar_adjunto, previsualizar_adjunto

app_name = 'afiliados'

urlpatterns = [
    path('atencion//', BuscarAfiliadoView.as_view(), name='buscar_afiliado'), # Sin DNI
    path('atencion/<str:dni>/', BuscarAfiliadoView.as_view(), name='buscar_afiliado'),

    path('retencion//', BuscarRetencionView.as_view(), name='buscar_retencion'), # Sin DNI
    path('retencion/<str:dni>/', BuscarRetencionView.as_view(), name='buscar_retencion'),
    path('api/cotizar/', cotizar_actual, name='cotizar_actual'),
    
    path('mesa//', MesaDeEntradaView.as_view(), name='mesa_entrada'), # Sin DNI
    path('mesa/<str:dni>/', MesaDeEntradaView.as_view(), name='mesa_entrada'),
    path('nuevo_expediente/guardar/', guardar_expediente, name='guardar_expediente'),
    path('nuevo_expediente/subir_archivo/', archivo_expediente, name='archivo_expediente'),
    path('expediente/descargar-adjunto/', descargar_adjunto, name='descargar_adjunto'),
    path('expediente/previsualizar-adjunto/', previsualizar_adjunto, name='previsualizar_adjunto')
]