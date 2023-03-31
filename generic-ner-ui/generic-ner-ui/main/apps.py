import random
from django.apps import AppConfig
from loguru import logger


class MainConfig(AppConfig):
    name = 'generic_ner_ui'
    
    #
    # Re-queue the task to populate rabbitmq, if the service restarts and we have runnings tasks open or waiting
    #
    def ready(self):
        import sys
        
        if sys.argv[1] != "collectstatic" and sys.argv[1] != "migrate" and sys.argv[1] != "makemigrations":
            import time
            logger.info(f"checking open tasks, waiting for db to start")
            time.sleep(10+random.random()*5)

            from generic_ner_ui.models import Run, Status, RunResult
            import asyncio
            from main.processing import process,create_async_loop
            #from multiprocessing import Event
#
            #ev = Event()
#
            #if not ev.is_set():
            #    ev.set()

            import sys, socket

            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.bind(("127.0.0.1", 47212))
                time.sleep(10)
            except socket.error:
                logger.info("restart already started, DO NOTHING")
            else:
                logger.info( "restart started")

                open_tasks_all_users = list(Run.objects.filter(status=Status.QUEUED))
                running_tasks_all_users = list(Run.objects.filter(status=Status.PROCESSING))

                if len(open_tasks_all_users) > 0:
                    logger.info(f"[STARTUP] open tasks = {len(open_tasks_all_users)}")
                if len(running_tasks_all_users) > 0:
                    logger.info(f"[STARTUP] running tasks = {len(running_tasks_all_users)}")

                _async_loop = create_async_loop()

                for task in running_tasks_all_users:
                    _async_loop.call_soon_threadsafe(asyncio.create_task, process(task))
                for task in open_tasks_all_users:
                    _async_loop.call_soon_threadsafe(asyncio.create_task, process(task))

                # hacky restart code for a specific user

                #tasks_single_user = list(Run.objects.filter(user_id="vhh_lit-db"))
                #for task in tasks_single_user:
                #    logger.info(f"[STARTUP] reloading tasks = {task.file_name}")
                #    task.status = Status.QUEUED
                #    task.save()
                #    _async_loop.call_soon_threadsafe(asyncio.create_task, process(task))
                #    #break
