import asyncio
import datetime
import itertools
import json
import os
import zipfile
import tempfile
from io import BytesIO
from pathlib import Path
from urllib import response
from urllib.parse import quote
from django.http.response import HttpResponseForbidden
from asgiref.sync import async_to_sync, sync_to_async
from django.http import HttpResponse, HttpResponseBadRequest
from django.http import JsonResponse

from channels.db import database_sync_to_async
from django.template import loader
from django.views.decorators.cache import cache_page, never_cache
from django.views.decorators.csrf import csrf_exempt
from loguru import logger
from PIL import Image
import requests

from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.rl_config import defaultPageSize
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import pandas as pd
import io

from generic_ner_ui.models import Run, Status, RunResult
from generic_ner_ui.settings import LOGOUT_URL
from generic_ner_ui.static import config
from generic_ner_ui.utils import redirect
from main.processing import download_minio_file, start_processing, \
    get_files_to_download_any, download_file_to_stream, update_pdf, \
    download_minio_file_data, compress, get_folder_size, convert_size, has_tiff_file

pdfmetrics.registerFont(TTFont('FreeSans', 'static/FreeSans.ttf', 'UTF-8'))

def base_page(request):
    runs = Run.objects.filter(user_id=request.user.username)
    runs = list(reversed(runs))

    grouped_runs = {}
    for r in runs:
        g = str(r.bucket)
        if g == "":
            g = "Unspecified"
        if g not in grouped_runs:
            grouped_runs[g]=[]

        run_data = {
            k: getattr(r, k)
            for k in [
                "user_id",
                "task_id",
                "file_name",
                "bucket",
                "minio_path",
                "upload_date",
                "error",
                "lang",
                "page_count",
                "status",
                "review_complete",
                "latest_review_date",
                "marked_complete",
                "has_tiff",
            ]
        }
        run_data["folder_size"] = convert_size(r.folder_size)
        run_data["folder_size_bytes"] = r.folder_size
        grouped_runs[g].append(run_data)

    open_tasks_all_users = Run.objects.filter(status=Status.QUEUED).count()
    busy = open_tasks_all_users >= 20
        
    context = {
        "busy": busy,
        "grouped_runs":grouped_runs,
        "is_new": len(runs) == 0,
        "logout_url": LOGOUT_URL,
    }

    template = loader.get_template('base.html')
    return HttpResponse(template.render(context, request))


def human_correction_type_evaluation(df):
    if "method" not in df.columns:
        return 0, 0, 0, 0

    c_correction_manual = 0
    c_correction_accept_suggestion = 0
    c_ocr_is_ok = 0
    c_correction_removed = 0

    for i, row in df[(df.correction != "") & (df.method.notnull())].iterrows():
        text = row.text.lower()
        human_correction = row.human_correction.lower()
        correction = eval(row.correction.lower())

        if hasattr(row, 'method'):  # text removed
            if row.method.lower() == "remove":
                c_correction_removed += 1
                continue

        if text == human_correction:  # ocr is correct
            c_ocr_is_ok += 1
            continue

        accept_suggestion = ""
        for c in correction:
            if c == human_correction:  # suggestion accept
                c_correction_accept_suggestion += 1
                accept_suggestion = c
                break
        if accept_suggestion:
            continue
        c_correction_manual += 1  # manual correction
    return c_correction_manual, c_correction_accept_suggestion, c_ocr_is_ok, c_correction_removed


def get_correction_stats(data):
    df = pd.DataFrame(data['ner']['entries'])
    d = {'operation_add': None,
         'operation_remove': None,
         'operation_update': None,
         'total_operations': None,
         'text_len': None,
         'corrections': None,
         'corrections_reviewed': None,
         'corrections_left': None,
         'c_correction_manual': None,
         'c_correction_accept_suggestion': None,
         'c_correction_is_ok': None,
         'c_correction_removed': None
    }
    if 'method' not in df.columns:
        return d

    # ADD: if row contains human_add & method has been updated -> avoid double count
    if 'human_add' in df.columns:
        d['operation_add'] = df['human_add'].count()
        cnt_updated_adds = len(df[(df.human_add == True) & (df.method == "update")].index)
    else:
        d['operation_add'] = 0
        cnt_updated_adds = 0

    # REMOVE:
    operation_counts = df['method'].value_counts()
    if 'remove' in operation_counts:
        d['operation_remove'] = operation_counts['remove']
    else:
        d['operation_remove'] = 0

    # UPDATE:
    if 'update' in operation_counts:
        d['operation_update'] = operation_counts['update'] - cnt_updated_adds
    else:
        d['operation_update'] = 0

    d['total_operations'] = len(df[df.method.notnull()].index)
    d['text_len'] = df.shape[0]

    # correction suggestion reviews
    c_corrections = len(df[df.correction != ''].index)
    c_corrections_reviewed = len(df[(df.correction != '') & (df.method.notnull())].index)
    d['corrections'] = c_corrections
    d['corrections_reviewed'] = c_corrections_reviewed
    d['corrections_left'] = d['corrections'] - d['corrections_reviewed']

    # suggestion accuracy metrics
    c_manual, c_accept, c_is_ok, c_removed = human_correction_type_evaluation(df)
    d['c_correction_manual']  = "{0:,.2f}".format(c_manual/d['corrections_reviewed'] * 100)
    d['c_correction_accept_suggestion'] = "{0:,.2f}".format(c_accept/d['corrections_reviewed'] * 100)
    d['c_correction_is_ok'] = "{0:,.2f}".format(c_is_ok/d['corrections_reviewed'] * 100)
    d['c_correction_removed'] = "{0:,.2f}".format(c_removed/d['corrections_reviewed'] * 100)
    return d


def admin_page(request):
    #if request.user.username != "sebastian":
    #    return HttpResponseForbidden()

    runs = Run.objects.filter()
    runs = list(reversed(runs))

    grouped_runs = {}
    user_stats = {}
    error_runs = []
    correction_stats = {}
        
    for r in runs:
        #try:
        #    for page in range(0, len(r.result_data.data["pages"])):
        #        correction_stats[f"{page}_{r.file_name}"] = get_correction_stats(r.result_data.data["pages"][page])
        #except Exception as e:
        #    logger.info(e)

        usr = str(r.user_id)
        if usr not in grouped_runs:
            grouped_runs[usr] = []
            user_stats[usr] = [0, 0, 0, 0, 0, 0] # 0 errors, 1 files, 2 pages, 3 queued, 4 processing, 5 storageused

        # user storage usage        
        if r.status == Status.FINISHED:
            minio_bucket, object_id = r.result_prep["output"].split('/', 1)
            folder_size = get_folder_size(minio_bucket, object_id)
            user_stats[usr][5] += folder_size

        if r.status == Status.ERROR:
            user_stats[usr][0] += 1
            error_runs.append({
            k: getattr(r, k)
            for k in [
                "user_id",
                "task_id",
                "file_name",
                "bucket",
                "minio_path",
                "upload_date",
                "error",
                "lang",
                "page_count",
                "status"
            ]
        })

        if r.status == Status.QUEUED:
            user_stats[usr][3] += 1

        if r.status == Status.PROCESSING:
            user_stats[usr][4] += 1

        user_stats[usr][1] += 1
        if r.page_count is not None:
            user_stats[usr][2] += int(r.page_count)

        grouped_runs[usr].append({
            k: getattr(r, k)
            for k in [
                "user_id",
                "task_id",
                "file_name",
                "bucket",
                "minio_path",
                "upload_date",
                "error",
                "lang",
                "page_count",
                "status"
            ]
        })

    # append metric to users storage usage
    total_errors = 0
    total_files = 0
    total_pages  = 0
    total_queued = 0
    total_processing = 0
    total_storageused = 0
    for user in user_stats:
        total_errors += user_stats[user][0]
        total_files += user_stats[user][1]
        total_pages += user_stats[user][2]
        total_queued += user_stats[user][3]
        total_processing += user_stats[user][4]
        total_storageused += user_stats[user][5]
        user_stats[user][5] = convert_size(user_stats[user][5])
    user_stats["total"] = [total_errors, total_files, total_pages, total_queued, total_processing, convert_size(total_storageused)]

    correction_stats_mean = dict(pd.DataFrame(correction_stats).T.astype(float).mean(axis=0).map('{:,.2f}'.format))
    correction_stats_sum = dict(pd.DataFrame(correction_stats).T.astype(float).sum().map('{:.0f}'.format))

    context = {
        "user_stats": user_stats,
        "grouped_runs": grouped_runs,
        "error_runs": error_runs,
        "logout_url": LOGOUT_URL,
        "correction_stats": correction_stats,
        "correction_stats_mean": correction_stats_mean,
        "correction_stats_sum": correction_stats_sum,
    }

    template = loader.get_template('admin.html')
    return HttpResponse(template.render(context, request))


def upload_view(request):

    runs = Run.objects.filter(user_id=request.user.username).only("bucket")

    groups = set()
    for r in runs:
        g = str(r.bucket)
        if g != "":
            groups.add(g)

    context = {
        "groups": sorted(groups, key=str.casefold),
        "logout_url": LOGOUT_URL,
        "onedrive_id": "d2f55b23-57aa-4ed6-a515-0f4d0a98555d",  # TODO: config
    }
    template = loader.get_template('upload.html')
    return HttpResponse(template.render(context, request))


@csrf_exempt
def upload(request):
    logger.debug(f"request 'upload' {request.method}")
    if request.method == 'POST':
        if request.FILES is None and "url" not in request.POST:
            return HttpResponseBadRequest('No files attached.')
        language = request.POST["language"]
        bucket = request.POST["bucket"]

        if request.FILES is not None:
            files = request.FILES.getlist('file')
            logger.info(f"File upload with {len(files)} files.")
            logger.debug(f"{request.FILES}")
            for f in files:
                start_processing(request.user.username, f, f.name, language, bucket)
        if "url" in request.POST:
            urls = request.POST.getlist("url")
            names = request.POST.getlist("name")
            logger.info(f"File upload with {len(urls)} urls.")
            for url, name in zip(urls, names):
                logger.info(f"Downloading {name} from onedrive via {url}")
                r = requests.get(url)
                r.raise_for_status()
                logger.info(f"Downloaded File: {r.status_code} , {len(r.content)}")
                f = BytesIO(initial_bytes=r.content)
                f.seek(0)
                start_processing(request.user.username, f, name, language, bucket)

    return HttpResponse(status=200)


def get_run(request, id, expect_result=True):
    run = Run.objects.get(task_id=id)
    assert run.user_id == request.user.username
    assert not expect_result or run.status == Status.FINISHED
    return run

def get_run_forcedata(request, id, expect_result=True):
    run = Run.objects.get(task_id=id)
    test = run.result_data
    assert run.user_id == request.user.username
    assert not expect_result or run.status == Status.FINISHED
    return run

@csrf_exempt
def delete_files(request):
    ids = request.POST.getlist("paths")

    for task_id in ids:
        try:
            run = get_run(request, task_id, expect_result=False)
            run.delete()
        except Exception:
            logger.exception(f"Failed to delete {task_id}")
    return redirect('/main')

@csrf_exempt
def rename_group(request):
    prev_group_name = request.POST.getlist("prev_group_name")[0]
    new_group_name = request.POST.getlist("new_group_name")[0]    
    runs = Run.objects.filter(user_id=request.user.username)
    runs = list(reversed(runs))
    for r in runs:
        g = str(r.bucket)
        if g == prev_group_name:
            r.bucket = new_group_name
            r.save()
    return redirect('/main')


@csrf_exempt
def delete_tiffs(request):
    ids = request.POST.getlist("paths")

    for task_id in ids:
        run = get_run(request, task_id, expect_result=False)
        minio_bucket, object_id = run.result_prep["output"].split('/', 1)
        original_file = run.file_name
        _ = has_tiff_file(minio_bucket, object_id, original_file, delete=True)

        run.has_tiff = False
        run.folder_size = get_folder_size(minio_bucket, object_id)
        run.save()
    return redirect(request.META.get('HTTP_REFERER', '/'))

async def get_files(run):
    request, paths = get_files_to_download_any(run.result_data.data)
    request_json = json.dumps(request, ensure_ascii=False)
    file_root = Path(run.file_name).stem
    data = run.result_data.data
    filename_base = Path(data["pages"][0]["preprocessing"]["orig"]).stem

    # DATES
    date = str(run.upload_date.strftime('%Y-%m-%d_%H-%M-%S'))
    date_upload = date
    if run.latest_review_date:
        date = str(run.latest_review_date.strftime('%Y-%m-%d_%H-%M-%S'))

    # JSON
    filename_json = f"{filename_base}_AC-OCR-BOW_{date}.json"
    request_json_path = f"{file_root}/{filename_json}"

    # TXT
    txt_path_unrev = f"{file_root}/{filename_base}_AC-OCR-BOW-Unrev_{date_upload}.txt"
    content_unrev = []
    for page in range(0, len(data["pages"])):
        content_unrev.append(data['pages'][page]['ner']['text'])
    txt_unrev = str.encode("\n\n".join(content_unrev))

    # add JSON + TXT
    results = [(request_json_path, request_json),
               (txt_path_unrev, txt_unrev)]
    paths, minio_paths = zip(*paths)

    # TIFF, PNG, JPG, PDF
    paths_renamed = []
    for p in paths:
        ext = Path(p).suffix
        if (ext == '.png'):
            if (p[-7:] == '_og.png'):
                ext = f"_AC-BOW_{date_upload}.png"
            else:
                ext = f"_AC-BOW-GS_{date_upload}.png"
        elif (ext == '.jpg'):
            ext = f"-BOW_{date_upload}.jpg"
        elif (ext == '.tiff'):
            ext = f"-BOW_{date_upload}.tiff"
        elif (ext == '.pdf'):
            ext = f"_AC-OCR-BOW-Unrev_{date_upload}.pdf"
        else:
            ext = "_UNKNOWN.txt"
        export_path = f"{file_root}/{filename_base}{ext}"
        paths_renamed.append(export_path)
    paths_renamed = tuple(paths_renamed)

    # gather streams
    streams = await asyncio.gather(*[
        download_file_to_stream(path)
        for path in minio_paths
    ])

    # remove candidates for each file-stream not found False
    remove_indices = [i for i, x in enumerate(streams) if x is False]
    streams = [i for j, i in enumerate(streams) if j not in remove_indices]
    paths_renamed = [i for j, i in enumerate(paths_renamed) if j not in remove_indices]
    streams = [s.read() for s in streams]
    results.extend(zip(paths_renamed, streams))
    return results


@sync_to_async
def get_runs_by_ids(request, ids, force_result=True):
    return [get_run(request, task_id, expect_result=force_result)
            for task_id in ids]

@sync_to_async
def get_runs_by_ids_data(request, ids, force_result=True):
    return [get_run_forcedata(request, task_id, expect_result=force_result)
            for task_id in ids]

@csrf_exempt
@async_to_sync
async def check_status_updates(request):
    ids = request.POST.getlist("paths")
    states = request.POST.getlist("states")
    runs = await get_runs_by_ids(request, ids, force_result=False)
    changed = [{"task_id":str(r.task_id),
                "status":int(r.status),
                "error":str(r.error),
                "has_tiff":str(r.has_tiff),
                "folder_size":convert_size(r.folder_size),
                "folder_size_bytes":r.folder_size,
                "marked_complete":str(r.marked_complete),
                "page_count":str(r.page_count)} for r,s in zip(runs, states) if r.status != int(s)]
    return JsonResponse(changed,safe=False)

    ##change = any(r.status != int(s) for r, s in zip(runs, states))
    #if change:
    #    logger.info(f"{[(r.status, s, type(r.status), type(s)) for r, s in zip(runs, states)]}")
    #    return redirect('/main')
    #else:
    #    return HttpResponse('')


@csrf_exempt
def update_marked_complete(request):
    ids = request.POST.getlist("paths")
    for task_id in ids:
        try:
            run = get_run(request, task_id, expect_result=False)
            run.marked_complete = not run.marked_complete
            run.save()
        except Exception:
            logger.exception(f"Failed to update marked_complete on {task_id}")
    return redirect('/main')


@csrf_exempt
@async_to_sync
async def download_all(request):
    ids = request.GET.getlist("paths")
    runs = await get_runs_by_ids_data(request, ids)
    response = HttpResponse(content_type='application/zip')

    # rename "duplicate" runs[i].file_name foldernames
    run_filenames = []
    for r in runs: run_filenames.append(r.file_name)
    valid_filenames = []
    for i, _ in enumerate(run_filenames):
        if run_filenames[i] not in valid_filenames:
            valid_filenames.append(run_filenames[i])
        else:
            c = 1
            while (True):
                if f"{run_filenames[i]}_{c}" not in valid_filenames:
                    duplicate_rename = f"{Path(runs[i].file_name).stem}_{c}{Path(runs[i].file_name).suffix}"
                    runs[i].file_name = duplicate_rename
                    valid_filenames.append(duplicate_rename)
                    break
                c += 1

    with zipfile.ZipFile(response, "w", zipfile.ZIP_STORED, False) as zip_file:
        paths = await asyncio.gather(*[get_files(run) for run in runs])
        for path, stream in itertools.chain.from_iterable(paths):
            zip_file.writestr(path, stream)

    # filename is the first file assuming the download of single zip request
    pdf_path = f"{Path(runs[0].file_name).stem}.zip"
    try:
        pdf_path.encode('ascii')
        file_expr = 'filename="{}"'.format(pdf_path)
    except UnicodeEncodeError:
        file_expr = "filename*=utf-8''{}".format(quote(pdf_path))

    response['Content-Disposition'] = 'attachment; {}'.format(file_expr)
    return response


@csrf_exempt
@cache_page(24 * 3600 * 7)
@async_to_sync
async def image(request, id, page):
    run = await database_sync_to_async(get_run)(request, id)
    minio_path = run.result_prep["pages"][page]["preprocessing"]["minio"]
    image_stream = await download_file_to_stream(minio_path)
    img = Image.open(image_stream).convert('RGB')

    img.thumbnail((config.image.width, config.image.height))

    response = HttpResponse(content_type="image/jpeg")
    img.save(response, format="jpeg", quality=100, optimize=True, progressive=True)

    return response


@csrf_exempt
@never_cache
def download_txt(request, id):
    run = get_run(request, id)

    # filename_ext.txt
    ext = f"_AC-OCR-BOW-Unrev_{str(run.upload_date.strftime('%Y-%m-%d_%H-%M-%S'))}.txt"
    if run.latest_review_date:
        ext = f"_AC-OCR-BOW-Rev_{str(run.latest_review_date.strftime('%Y-%m-%d_%H-%M-%S'))}.txt"
    txt_path = f"{Path(run.file_name).stem}{ext}"
 
    data = run.result_data.data
    content = []
    for page in range(0, len(data["pages"])):
        if 'text_reviewed' in data["pages"][page]['ner'].keys():
            content.append(data["pages"][page]['ner']['text_reviewed'])
        else:
            content.append(data["pages"][page]['ner']['text'])

    response = HttpResponse("\n\n".join(content), content_type='text/plain')
    response['Content-Disposition'] = f'attachment; filename="{txt_path}"'
    return response


@csrf_exempt
@never_cache
def download_json(request, id):
    run = get_run(request, id)

    ext = f"_AC-OCR-BOW_{str(run.upload_date.strftime('%Y-%m-%d_%H-%M-%S'))}.json"
    json_path = f"{Path(run.file_name).stem}{ext}"

    data = run.result_data.data
    request_json = json.dumps(data, ensure_ascii=False)

    response = HttpResponse(request_json, content_type='application/json')
    response['Content-Disposition'] = f'attachment; filename="{json_path}"'
    return response


@csrf_exempt
@never_cache
def download_pdf(request, id):
    run = get_run(request, id)

    # PDF un-reviewed
    if not run.latest_review_date:
        ext = f"_AC-OCR-BOW-Unrev_{str(run.upload_date.strftime('%Y-%m-%d_%H-%M-%S'))}.pdf"
        pdf_path = f"{Path(run.file_name).stem}{ext}"

        minio_path = run.result_prep["output"]
        response = download_minio_file(minio_path, content_type="application/pdf")
        response['Content-Disposition'] = f'attachment; filename="{pdf_path}"'
        return response

    # PDF reviewed
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

    # # prepare DB update
    # minio_bucket, object_id = run.result_prep["output"].split('/', 1)
    # file = io.BytesIO(response.content)
    # size = file.getbuffer().nbytes
    # # update pdf in database + pdf state
    # update_pdf(minio_bucket, object_id, file, size)
    # run.pdf_uptodate = True
    # run.save()


def create_single_pdf(data, outfile):
    font_name = 'FreeSans'
    padding = 20
    pdf = canvas.Canvas(outfile)
    pdf.setTitle("BOW - Batch OCR Webservice")
    pdf.setAuthor("BOW - Batch OCR Webservice")
    pdf.setSubject("Created by BOW - Batch OCR Webservice")

    for i, row in enumerate(data):
        # logger.info(f"Creating pdf page {i} width: {row['preprocessing']['width']}, height: {row['preprocessing']['height']}")

        # insert document background
        minio_path_img = data[i]["preprocessing"]["minio"]
        image_stream = download_minio_file_data(minio_path_img)
        temporary_image = ImageReader(image_stream)
        pdf.setPageSize((row['preprocessing']['width'], row['preprocessing']['height']))
        pdf.drawImage(temporary_image, 0, 0, width=row['preprocessing']['width'], height=row['preprocessing']['height'])

        entries = pd.DataFrame.from_dict(pd.DataFrame(row['ner']['entries']))
        if 'method' in entries.columns:
            entries = entries[entries.method != 'remove']
        else:
            entries['human_correction'] = pd.to_numeric("")

        # font settings
        try:
            meadian_fontsize = entries.height.median()
        except Exception as e:
            logger.info(f"using default fontsize due to: {e}")
            meadian_fontsize = 10

        # insert text data
        for j, entry_row in entries.iterrows():
            if entry_row.height > meadian_fontsize + padding or entry_row.height < meadian_fontsize - padding:
                font_size = meadian_fontsize + padding
            else:
                font_size = entry_row.height

            # filter human corrections
            if not pd.isna(entry_row.human_correction):
                box_text = entry_row.human_correction
            else:
                box_text = entry_row.text

            font_width = pdf.stringWidth(box_text, font_name, font_size)
            text = pdf.beginText()
            text.setTextRenderMode(3)
            text.setFont(font_name, font_size)
            text.setTextOrigin(entry_row.left, row['preprocessing']['height'] - entry_row.top - entry_row.height)
            box_width = (entry_row.width)
            try:
                text.setHorizScale(100.0 * box_width / font_width)
            except Exception as e:
                logger.info(e)
            text.textLine(box_text)
            pdf.drawText(text)
        pdf.showPage()
    pdf.save()
    return pdf


@csrf_exempt
@cache_page(24 * 3600 * 7)
def download_original(request, id):
    run = get_run(request, id, expect_result=False)
    minio_path = run.minio_path
    return download_minio_file(minio_path)


def transform_page(page, ner_types):
    entities = page["ner"]["entities"]
    entries = page["ner"]["entries"]
    text = page["ocr"]["text"]
    page_width = page["preprocessing"]["width"]
    page_height = page["preprocessing"]["height"]

    for entity in entities:
        entity["entries"] = []

    position = 0
    complete_text = ""
    for entry in entries:
        end_position = position + len(entry["text"])
        entry["left_norm"] = round(entry["left"] / page_width * 100,2)
        entry["width_norm"] = round(entry["width"] / page_width * 100,2)
        entry["top_norm"] = round(entry["top"] / page_height * 100,2)
        entry["height_norm"] = round(entry["height"] / page_height * 100,2)
        if entry["correction"] == "":
            entry["correction"] = []
        else:
            s = entry["correction"].replace("[","").replace("]","").replace("'","")
            #if "[" in s:
            #    eo = s.split("[")
            #    es = []
            #    for e in eo:
            #        es.extend(e.replace("]","").split(","))
            #else:
            es = s.split(",")
            entry["correction"] = es

        for entity in entities:
            if position <= entity["end"] and end_position >= entity["start"]:
                entity["entries"].append(entry)
        position = end_position + 1
        complete_text += entry["text"] + " "

    if complete_text:
        complete_text = complete_text[:-1]
    try:
        # TODO: 
        assert complete_text == text
    except Exception as e:
        logger.info(f"transform_page err: {e}")

    entity_groups = [{
        "name": group.name,
        "entity_types": group.entities,
        "entities": []
    } for group in config.entitygroups.groups]

    entity_groups.append({
        "name": "Without group",
        "entity_types": [],
        "entities": []
    })

    for entity in entities:
        entity["color_id"] = ner_types.index(entity["type"]) % 9
        found = False

        for entity_group in entity_groups:
            if entity["type"] in entity_group["entity_types"]:
                entity_group["entities"].append(entity)
                found = True

        if not found:
            entity_groups[-1]["entities"].append(entity)

    if len(entity_groups) == 1:
        entity_groups[0]["name"] = None

    page["ner"]["entity_groups"] = entity_groups

    return page


def gather_entity_types(pages):
    ner_types = []

    for group in config.entitygroups.groups:
        for entity_type in group.entities:
            if entity_type not in ner_types:
                ner_types.append(entity_type)

    for page in pages:
        for entity in page["ner"]["entities"]:
            if entity["type"] not in ner_types:
                ner_types.append(entity["type"])
    return ner_types


def gather_entity_stats(pages):
    data = dict()

    for i, page in enumerate(pages):
        for entity in page["ner"]["entities"]:
            _type = entity["type"]
            text = entity["value"]
            if (_type, text) not in data:
                data[(_type, text)] = {
                    "text": text,
                    "type": _type,
                    "count": 0,
                    "pages": []
                }
            data[(_type, text)]["count"] += 1
            if i not in data[(_type, text)]["pages"]:
                data[(_type, text)]["pages"].append(i)
    return list(data.values())


def delete(request, id):
    run = get_run(request, id, expect_result=False)
    run.delete()
    return redirect('/main')


@csrf_exempt
def update_human_corrections(request):
    run = get_run(request, request.POST['task_id'])
    data = run.result_data.data
    human_corrections = json.loads(request.POST['save-review'])

    for i in human_corrections:
        if i['method'] == "update":
            data["pages"][i['page']]['ner']['entries'][(i['row'])]['human_correction'] = i['value']
            data["pages"][i['page']]['ner']['entries'][(i['row'])]['method'] = i['method']

        elif i['method'] == "remove":
            data["pages"][i['page']]['ner']['entries'][(i['row'])]['human_correction'] = ""
            data["pages"][i['page']]['ner']['entries'][(i['row'])]['method'] = i['method']

        elif i['method'] == "add":
            page_width = data["pages"][i['page']]['preprocessing']['width']
            page_height = data["pages"][i['page']]['preprocessing']['height']

            # receive percentages % -> map to px values
            v_left = (i['value']['left'] * page_width / 100)
            v_width = (i['value']['width'] * page_width / 100)
            v_top = (i['value']['top'] * page_height / 100)
            v_height = (i['value']['height'] * page_height / 100)
            add_row = {
                'top': v_top,
                'left': v_left,
                'width': v_width,
                'height': v_height,
                'conf': int(100),
                'text': i['value']['text'],
                'time': None,
                'correction': '',
                'human_correction': i['value']['text'],
                'method': i['method'],
                'human_add': True  # human added row
            }
            data["pages"][i['page']]['ner']['entries'].append(add_row)

        elif i['method'] == "update_add":
            page_width = data["pages"][i['page']]['preprocessing']['width']
            page_height = data["pages"][i['page']]['preprocessing']['height']
            v_left = (i['value']['left'] * page_width / 100)
            v_width = (i['value']['width'] * page_width / 100)
            v_top = (i['value']['top'] * page_height / 100)
            v_height = (i['value']['height'] * page_height / 100)
            data["pages"][i['page']]['ner']['entries'][(i['row'])]['top'] = v_top
            data["pages"][i['page']]['ner']['entries'][(i['row'])]['left'] = v_left
            data["pages"][i['page']]['ner']['entries'][(i['row'])]['width'] = v_width
            data["pages"][i['page']]['ner']['entries'][(i['row'])]['height'] = v_height

        # update JSON reviewed text
        text_reviewed_list = []
        for entry in data["pages"][i['page']]['ner']['entries']:
            if 'human_correction' in entry.keys():
                text_reviewed_list.append(entry['human_correction'])
            else:
                text_reviewed_list.append(entry['text'])
        data["pages"][i['page']]['ner']['text_reviewed'] = ' '.join(text_reviewed_list)

    # update human review state run variable
    run.review_complete = check_human_review_state(data)

    # after any update the pdf is not up to date
    if len(human_corrections) > 0:
        run.pdf_uptodate = False
        run.latest_review_date = datetime.datetime.now()

    results = data
    run.result_data = RunResult(data=results)
    run.result_data.save()
    run.save()
    return JsonResponse({"success": 1}, safe=False)


def check_human_review_state(data):
    for page in data['pages']:
        for entry in page['ner']['entries']:
            # first correction that has no review - returns false
            if (entry['correction'] != '') and ('method' not in entry.keys()):
                return False
    return True


def details(request, id, view="text"):
    run = get_run(request, id)
    pages = run.result_data.data["pages"][:50]
    ner_types = gather_entity_types(pages)
    entity_stats = gather_entity_stats(pages)

    context = {
        "cut_off": len(run.result_data.data["pages"]) > 50,
        "task_id": id,
        "file_name": Path(run.file_name).stem,
        "latest_review_date": run.latest_review_date,
        "file_name_original": run.file_name,
        "pages": [
            transform_page(page, ner_types=ner_types)
            for page in pages
        ],
        "view": view,
        "entitystats": entity_stats,
        "logout_url": LOGOUT_URL,
        "page_lengths": [
            len(page['ner']['entries'])
            for i, page in enumerate(pages)
        ],
        "has_tiff": run.has_tiff,
    }

    template = loader.get_template('display.html')
    return HttpResponse(template.render(context, request))
