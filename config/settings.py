from pathlib import Path
from urllib.parse import urlparse
import os

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Carga variables de entorno desde .env (ver .env.example)
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / '.env')
except ImportError:
    pass
 
# SECURITY WARNING: keep the secret key used in production secret!
# Se lee de .env en producción; el valor hardcodeado queda solo como fallback de dev.
SECRET_KEY = os.environ.get(
    'DJANGO_SECRET_KEY',
    'django-insecure-8xv_ta*-1dryi#afggy2!h)(^q&)7t_v%uw56ls=o+w0iihv=_',
)

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get('DJANGO_DEBUG', 'True') == 'True'

ALLOWED_HOSTS = ['172.210.161.18', 'localhost', 'widget.nobis.com.ar', '192.168.0.156', '172.16.1.186','10.4.0.176']
CSRF_TRUSTED_ORIGINS = ['https://widget.nobis.com.ar']

# ---------------------------------------------------------------------------
# Autenticación Azure AD (MSAL) + sesión cross-site (iframe de 3ª parte)
# ---------------------------------------------------------------------------
# Flag maestro del gate. Con False los decoradores pasan de largo (deploy dormido / rollback).
WIDGET_AUTH_ENABLED = os.environ.get('WIDGET_AUTH_ENABLED', 'False') == 'True'

# El widget corre embebido como iframe bajo un top-level de OTRO dominio (cross-site).
# Se controla por env, NO acoplado a DEBUG (prender DEBUG no debe romper la auth).
WIDGET_CROSS_SITE = os.environ.get('WIDGET_CROSS_SITE', 'False') == 'True'

# Cookie de sesión: persistente en el navegador, compartida entre pestañas/iframes del mismo origen.
SESSION_COOKIE_NAME = 'widget_sessionid'          # host-only (sin SESSION_COOKIE_DOMAIN)
SESSION_COOKIE_SAMESITE = 'None' if WIDGET_CROSS_SITE else 'Lax'
SESSION_COOKIE_SECURE = WIDGET_CROSS_SITE         # 'None' exige Secure; en http local rompería
SESSION_COOKIE_HTTPONLY = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
SESSION_COOKIE_AGE = 60 * 60 * 9                  # 9 h absolutas (jornada)
SESSION_SAVE_EVERY_REQUEST = False                # no reescribir sesión por request (evita lock de sqlite con el polling)

# CSRF: el frontend lee 'csrftoken' de document.cookie -> NO renombrar ni HttpOnly.
CSRF_COOKIE_NAME = 'csrftoken'
CSRF_COOKIE_SAMESITE = 'None' if WIDGET_CROSS_SITE else 'Lax'
CSRF_COOKIE_SECURE = WIDGET_CROSS_SITE

# Detrás del proxy Apache (TLS terminado ahí). Verificar que Apache envíe X-Forwarded-Proto.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# El atributo Partitioned (CHIPS) lo agrega Apache al Set-Cookie (Django 5.0.6 no lo emite nativo).
# Ver deploy/apache-widget.conf.example.

# --- MSAL / App Registration (valores reales en .env) ---
MSAL_CLIENT_ID = os.environ.get('MSAL_CLIENT_ID', '')
MSAL_TENANT_ID = os.environ.get('MSAL_TENANT_ID', '')
MSAL_CLIENT_SECRET = os.environ.get('MSAL_CLIENT_SECRET', '')
MSAL_AUTHORITY = os.environ.get(
    'MSAL_AUTHORITY',
    f'https://login.microsoftonline.com/{MSAL_TENANT_ID}' if MSAL_TENANT_ID else '',
)
# redirect_uri PÚBLICO (con prefijo /widget/). NUNCA usar request.build_absolute_uri().
MSAL_REDIRECT_URI = os.environ.get('MSAL_REDIRECT_URI', 'http://localhost:8000/auth/callback')
MSAL_SCOPES = []  # MSAL agrega openid/profile/offline_access. Sin Graph salvo overage de grupos.

# Prefijo público que agrega el proxy Apache (Django no lo ve). Vacío en dev.
# Se deriva del path del redirect_uri para no configurarlo dos veces.
WIDGET_URL_PREFIX = '/widget' if urlparse(MSAL_REDIRECT_URI).path.startswith('/widget/') else ''

# --- RBAC / superadmin ---
# Break-glass: lista de UPNs superadmin (bootstrap anti-lockout, no depende de la tabla).
WIDGET_SUPERADMINS = [
    u.strip().lower() for u in os.environ.get('WIDGET_SUPERADMINS', '').split(',') if u.strip()
]
# Grupo Entra dedicado de superadmins (opcional, se resuelve del claim 'groups').
WIDGET_SUPERADMIN_GROUP_ID = os.environ.get('WIDGET_SUPERADMIN_GROUP_ID', '').strip()
 
# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'home',
    'afiliados',
    'cuentas',
]
 
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]
 
ROOT_URLCONF = 'config.urls'
 
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'cuentas.context_processors.widget_auth',
            ],
        },
    },
]
 
WSGI_APPLICATION = 'config.wsgi.application'
 
 
# Database
# https://docs.djangoproject.com/en/5.0/ref/settings/#databases
 
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}
 
 
# Password validation
# https://docs.djangoproject.com/en/5.0/ref/settings/#auth-password-validators
 
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]
 
 
# Internationalization
# https://docs.djangoproject.com/en/5.0/topics/i18n/
 
LANGUAGE_CODE = 'es'
 
TIME_ZONE = 'America/Argentina/Cordoba'
 
USE_I18N = True
 
USE_TZ = True
 
 
# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.0/howto/static-files/
 
# URL para los archivos estáticos
STATIC_URL = '/static/'

# Directorio donde Django buscará archivos estáticos adicionales
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'static'),
    os.path.join(BASE_DIR, 'home', 'static'),
    os.path.join(BASE_DIR, 'afiliados', 'static'),
]

# Solo en producción: carpeta donde Django recolectará archivos estáticos
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
 
# Default primary key field type
# https://docs.djangoproject.com/en/5.0/ref/settings/#default-auto-field
 
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
 
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'unique-snowflake',
    }
}