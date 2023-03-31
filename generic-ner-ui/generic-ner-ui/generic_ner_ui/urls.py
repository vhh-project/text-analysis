"""generic_ner_ui URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/2.1/topics/http/urls/
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
import tempfile
from decorator_include import decorator_include
from django.conf.urls import url
from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LogoutView
from django.http import JsonResponse
from django.urls import include, path, re_path

from generic_ner_ui import settings
from generic_ner_ui.utils import redirect

import datetime
import itertools
import json
from pathlib import Path
from generic_ner_ui.models import Run
from django.db.models import Q
from django.http import HttpResponse
from main.views import create_single_pdf, download_pdf
from generic_ner_ui.settings import SECRET, ALLOWED_IPS
from loguru import logger
from main.processing import compress
from main.processing import download_minio_file

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[-1].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def validate_access(request):
    try:
        #if get_client_ip(request) not in ALLOWED_IPS:
        #    return False
        request_secret = request.GET.getlist("secret")[0]
        if request_secret != SECRET:
            return False
        return True
    except Exception as e:
        logger.info(f"{get_client_ip(request)}, {e}")
        return False


def search_files(request):
    try:
        if not validate_access(request):
            return JsonResponse([{"access": "denied"}], safe=False)
        request_date = request.GET.getlist("lastApproved")[0]
        date = datetime.datetime.strptime(request_date, "%Y%m%dT%H%M%S%z").strftime("%Y-%m-%d %H:%M:%S.%f%z")
    except Exception as e:
        return JsonResponse([{"exception": str(e)}], safe=False)

    runs = Run.objects.filter( (Q(latest_review_date__gt=date) | Q(finish_date__gt=date)) & Q(marked_complete=True) )
    runs = list(reversed(runs))

    context = []
    for r in runs:
        if r.latest_review_date:
            date = r.latest_review_date.strftime("%Y%m%dT%H%M%S%z")
        elif r.finish_date:
            date = r.finish_date.strftime("%Y%m%dT%H%M%S%z")
        else:
            date = ""
        context.append({
            "id": r.task_id,
            "lastApproved": date,
            "title": f"{Path(r.file_name).stem}.pdf",
            "resultPdfUrl": request.build_absolute_uri(f"/bow/{r.task_id}/result.pdf?secret={SECRET}").replace("http://", "https://"),
            "jsonUrl": request.build_absolute_uri(f"/bow/{r.task_id}/result.json?secret={SECRET}").replace("http://", "https://")
        })
    return JsonResponse(context, safe=False, json_dumps_params={'ensure_ascii': False})


def download_json(request, id):
    if not validate_access(request):
        return JsonResponse([{"access": "denied"}], safe=False)

    run = Run.objects.get(task_id=id)
    data = run.result_data.data

    file_root = Path(run.file_name).stem
    filename_base = Path(data['output']).stem

    date = run.upload_date.strftime('%Y-%m-%d_%H-%M-%S')
    if run.latest_review_date:
        date = run.latest_review_date.strftime('%Y-%m-%d_%H-%M-%S')
    elif run.finish_date:
        date = run.finish_date.strftime('%Y-%m-%d_%H-%M-%S')
    filename_json = f"{filename_base}_AC-OCR-BOW_{date}.json"
    request_json_path = f"{file_root}/{filename_json}"

    response = HttpResponse(json.dumps(data, ensure_ascii=False), content_type='application/json')
    response['Content-Disposition'] = f'attachment; filename="{request_json_path}"'
    return response


def download_pdf(request, id):
    if not validate_access(request):
        return JsonResponse([{"access": "denied"}], safe=False)

    run = Run.objects.get(task_id=id)

    # PDF un-reviewed
    if not run.latest_review_date:
        ext = f"_AC-OCR-BOW-Unrev_{str(run.upload_date.strftime('%Y-%m-%d_%H-%M-%S'))}.pdf"
        pdf_path = f"{Path(run.file_name).stem}{ext}"

        minio_path = run.result_prep["output"]
        response = download_minio_file(minio_path, content_type="application/pdf")
        response['Content-Disposition'] = f'attachment; filename="{pdf_path}"'
        return response

    ext = f"_AC-OCR-BOW-Unrev_{str(run.upload_date.strftime('%Y-%m-%d_%H-%M-%S'))}.pdf"
    if run.finish_date != None:
        ext = f"_AC-OCR-BOW-Unrev_{str(run.finish_date.strftime('%Y-%m-%d_%H-%M-%S'))}.pdf"
    if run.latest_review_date != None:
        ext = f"_AC-OCR-BOW-Rev_{str(run.latest_review_date.strftime('%Y-%m-%d_%H-%M-%S'))}.pdf"

    pdf_path = f"{Path(run.file_name).stem}{ext}"

    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=True) as temp_1:
        _ = create_single_pdf(run.result_data.data['pages'], temp_1.name)

        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=True) as temp_2:
            success = compress(temp_1.name, temp_2.name, power=1)
            export_file = temp_1.name
            if success:
                export_file = temp_2.name

            with open(export_file, 'rb') as file:
                response = HttpResponse(file.read(), content_type='application/pdf')
                response['Content-Disposition'] = f'attachment; filename="{pdf_path}"'
                return response

    #response = HttpResponse(content_type='application/pdf')
    #response['Content-Disposition'] = f'attachment; filename="{pdf_path}"'
    #response = create_single_pdf(run.result_data.data['pages'], response)
    #return response


def health_check(request):
    return JsonResponse({"status": "up"})


urlpatterns = [
    re_path(r'^$', lambda _: redirect('/main')),
    path('', include('social_django.urls', namespace='social')),
    path('admin/', admin.site.urls),
    path('main/', decorator_include(login_required, ('main.urls', "main"),
                                    namespace="main")),
    path('health', health_check),
    path('search', search_files),
    path('<str:id>/result.pdf', download_pdf),
    path("<str:id>/result.json", download_json),
    url(r'^logout/$', LogoutView.as_view(), {'next_page': settings.LOGOUT_REDIRECT_URL}, name='logout'),
]
