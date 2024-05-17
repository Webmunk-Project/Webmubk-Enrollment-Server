from django.contrib import admin
from django.urls import path

import sys

if sys.version_info[0] > 2:
    from django.urls import re_path as url, include # pylint: disable=no-name-in-module
else:
    from django.conf.urls import url, include

urlpatterns = [
    path('admin/', admin.site.urls),
    url(r'^quicksilver/', include('quicksilver.urls')),
    url(r'^export/', include('simple_data_export.urls')),
    url(r'^enroll/', include('enrollment.urls')),
]
