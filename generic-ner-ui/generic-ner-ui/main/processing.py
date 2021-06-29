import asyncio
import datetime
import io
import itertools
import pytz

from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpResponse
from loguru import logger
from minio import Minio

from generic_ner_ui.models import Run, RunResult, Status
from generic_ner_ui.static import config
from main.amqp import AmqpClient, myuuid, PipelineError
from main.asyncio_loop import start_loop

minio_client = None
amqp_client = None
async_loop = None


def create_minio_client():
    global minio_client
    if minio_client is None:
        minio_url = config.minio.host
        if config.minio.port:
            minio_url = f"{minio_url}:{config.minio.port}"

        minio_client = Minio(minio_url,
                             access_key=config.minio.key,
                             secret_key=config.minio.secret,
                             secure=False)
        if not minio_client.bucket_exists(config.minio.upload_bucket):
            minio_client.make_bucket(config.minio.upload_bucket)
    return minio_client


def get_files_to_download_path(response):
    new_path = response.split("/", 1)[1]
    return new_path, [(new_path, response)]


def get_files_to_download_any(response):
    if isinstance(response, dict):
        return get_files_to_download_dir(response)
    elif isinstance(response, list):
        return get_files_to_download_list(response)
    elif isinstance(response, str) and response.startswith(config.minio.upload_bucket):
        return get_files_to_download_path(response)
    else:
        return response, []


def get_files_to_download_list(response):
    if not response:
        return [], []
    response, files = zip(*[
        get_files_to_download_any(ele)
        for ele in response
    ])

    files = list(itertools.chain.from_iterable(files))
    return response, files


def get_files_to_download_dir(response):
    data = {
        key: get_files_to_download_any(value)
        for key, value in response.items()
    }
    new_response = {
        key: value[0]
        for key, value in data.items()
    }
    files = list(itertools.chain.from_iterable([
        value[1] for _, value in data.items()
    ]))
    return new_response, files


async def download_file_to_stream(minio_path):
    logger.info(f"downloading {minio_path} from minio")
    bucket, path = minio_path.split("/", 1)
    client = create_minio_client()
    data = client.get_object(bucket, path)
    response = io.BytesIO()
    for d in data.stream(32 * 1024):
        response.write(d)
    response.seek(0)
    return response


def download_minio_file(minio_path, content_type="image/png"):
    logger.info(f"downloading {minio_path} from minio")
    bucket, path = minio_path.split("/", 1)
    client = create_minio_client()
    data = client.get_object(bucket, path)
    response = HttpResponse(content_type=content_type)
    for d in data.stream(32 * 1024):
        response.write(d)
    return response


def download_minio_file_data(minio_path):
    logger.info(f"downloading {minio_path} from minio")
    bucket, path = minio_path.split("/", 1)
    client = create_minio_client()
    data = client.get_object(bucket, path)
    response = io.BytesIO()
    for d in data.stream(32 * 1024):
        response.write(d)
    response.seek(0)
    return response


def create_async_loop():
    global async_loop
    if async_loop is None:
        async_loop = start_loop()
    return async_loop


async def create_amqp_client():
    global amqp_client
    if amqp_client is None:
        amqp_client = await AmqpClient(config).connect()
    return amqp_client


async def get_result_prep(result):
    d = {
        k: v
        for k, v in result.items()
        if k != "pages"
    }
    d["pages"] = [
        {
            "preprocessing": page["preprocessing"]
        }
        for page in result["pages"]
    ]
    return d


@async_to_sync
async def queue_count():
    client = await AmqpClient(config).connect()
    return await client.get_queue_count()


async def process(run: Run):
    client = await create_amqp_client()
    logger.info(f"start processing for document {run.file_name}")
    try:
        result = await client.process_case({"minio": run.minio_path,
                                            "lang": run.lang}, run)
        run.result_data = RunResult(data=result)  # TODO: 
        logger.info(run.result_data)
        await database_sync_to_async(run.result_data.save)() # TODO: 
        run.result_prep = await get_result_prep(result)
        run.status = Status.FINISHED
        logger.info("After -> Pipeline Run")
        logger.info(run.status)
        logger.info(f"successfully processed document {run.file_name}")
    except PipelineError as e:
        if e.page_num is None:
            logger.error(f"processing of {run.file_name} {run.task_id} failed "
                         f"on {e.task_name} correlation_id {e.correlation_id} "
                         f"with errormessage: '{e}'")
        else:
            logger.error(f"processing of {run.file_name} {run.task_id} failed "
                         f"on {e.task_name}-{e.page_num} correlation_id "
                         f"{e.correlation_id} with errormessage: '{e}'")
        run.error = f"{e.task_name}: {e}"
        run.status = Status.ERROR
    except Exception as e:
        run.status = Status.ERROR
        logger.exception(e)
    except ObjectDoesNotExist:
        logger.info(f"results for run {run.task_id} are discarded, as the run was deleted.")
        run = None
    finally:
        try:
            if run is not None:
                await database_sync_to_async(run.save)()
        except Exception as e:
            logger.exception(e)


def start_processing(user, file, name, language, bucket):
    if bucket is None:
        bucket = ""
    logger.info(f"uploading {name} to minio")
    task_id = myuuid()
    object_id = f"{task_id}/{name}"
    minio_bucket = config.minio.upload_bucket
    object_path = f"{minio_bucket}/{object_id}"
    run = Run(
        user_id=user,
        task_id=task_id,
        file_name=name,
        minio_path=object_path,
        upload_date=datetime.datetime.now(tz=pytz.timezone('Europe/Vienna')),
        lang=language,
        bucket=bucket,
        page_count=1 if name[-4:] != ".pdf" else None,
        review_complete=False,
        pdf_uptodate=True
    )
    run.save()
    try:
        size = -1
        if hasattr(file, 'size'):
            size = file.size
        else:
            size = file.getbuffer().nbytes
        client = create_minio_client()
        _async_loop = create_async_loop()
        client.put_object(minio_bucket, object_id, file, size)

        logger.info(f"{minio_bucket}, {object_id}, {file}, {size}")
        logger.info(f"{type(minio_bucket)}, {type(object_id)}, {type(file)}, {type(size)}")

        _async_loop.call_soon_threadsafe(asyncio.create_task, process(run))
    except Exception as e:
        logger.exception(f"Error uploading file {file}")
        run.error = str(e)
        run.save()

def update_pdf(minio_bucket, object_id, file, size):
    client = create_minio_client()
    client.put_object(minio_bucket, object_id, file, size)


