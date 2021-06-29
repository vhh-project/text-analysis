from django.shortcuts import redirect as _redirect

from generic_ner_ui.settings import FORCE_SCRIPT_NAME




def redirect(url):
    if url.startswith("/") and FORCE_SCRIPT_NAME:
        url = f"{FORCE_SCRIPT_NAME}{url}"
    return _redirect(url)


