"""
WSGI config for vitrine_virtual project.
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'vitrine_virtual.settings')

application = get_wsgi_application()
