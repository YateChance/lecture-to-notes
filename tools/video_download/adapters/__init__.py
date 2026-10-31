"""Explicit transport registry: add backends without changing discovery workflows."""
from .direct_http import fetch as direct_http
from .local_file import fetch as local_file

ADAPTERS = {'direct_http': direct_http, 'local_file': local_file}
