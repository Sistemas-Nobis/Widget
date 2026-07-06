"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.contrib import admin
from django.urls import path, include
from django.http import HttpResponse

def test_view(request):
    return HttpResponse("¡Funciona!")

urlpatterns = [
    path('admin/', admin.site.urls),
    path('test/', test_view),
]

# cuentas (auth MSAL + gestión de permisos) va ANTES de home/afiliados
# para que ningún pattern greedy de esos includes lo sombree.
urlpatterns += [
    path('', include('cuentas.urls')),
]

urlpatterns += [
    path('', include('home.urls')),
    path('', include('afiliados.urls')),
]

# En dev NO hay proxy Apache que quite el prefijo /widget/, pero el frontend hace
# fetch a /widget/... Montamos las mismas URLs bajo /widget/ solo con DEBUG para
# que las llamadas funcionen local. En prod Apache strippea /widget/ y esto no aplica.
if settings.DEBUG:
    urlpatterns += [
        path('widget/', include(('cuentas.urls', 'cuentas'), namespace='cuentas_widget')),
        path('widget/', include(('home.urls', 'home'), namespace='home_widget')),
        path('widget/', include(('afiliados.urls', 'afiliados'), namespace='afiliados_widget')),
    ]
