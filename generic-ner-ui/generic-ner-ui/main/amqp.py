import asyncio
import itertools
import json
from typing import Dict, Optional
import uuid

from aio_pika import Channel, connect, IncomingMessage, Message
from aio_pika import Queue as PikaQueue
from channels.db import database_sync_to_async
from loguru import logger

from generic_ner_ui.config import Config
from generic_ner_ui.models import PipelineRun, Run, Status


def myuuid():
    return str(uuid.uuid4())


class PipelineError(Exception):
    def __init__(self, message, task_name, correlation_id, page_num, *args):
        self.task_name = task_name
        self.correlation_id = correlation_id
        self.page_num = page_num
        super(PipelineError, self).__init__(message, *args)


async def select_page(pages, page_id):
    return pages[page_id]


class AmqpClient:

    def __init__(self, config: Config):
        self.connection = None
        self.channel: Optional[Channel] = None
        self.callback_queue: Optional[PikaQueue] = None
        self.queues: Dict[str, asyncio.Queue[IncomingMessage]] = {}

        self.config = config

    async def connect(self):
        logger.info("Connecting...")
        self.connection = await connect(self.config.amqp.url)
        self.channel = await self.connection.channel()
        self.callback_queue = await self.channel.declare_queue(
            exclusive=True,
            arguments={"x-max-priority": 127}
        )
        await self.callback_queue.consume(self.on_response)
        logger.info("Connecting...done")
        return self

    async def on_response(self, message: IncomingMessage):
        logger.debug("Getting message for {}", message.correlation_id)
        if message.correlation_id in self.queues:
            queue = self.queues[message.correlation_id]
            await queue.put(message)

    @database_sync_to_async
    def save_pipeline_run(self, correlation_id, run, page_num=None):
        PipelineRun(
            correlation_id=correlation_id,
            run=run,
            page_num=page_num
        ).save()

    @database_sync_to_async
    def add_pipeline_error(self, correlation_id, error):
        pipeline_run = PipelineRun.objects.get(correlation_id=correlation_id)
        pipeline_run.error = error
        pipeline_run.save()

    @database_sync_to_async
    def add_pipeline_result(self, correlation_id, result):
        pipeline_run = PipelineRun.objects.get(correlation_id=correlation_id)
        pipeline_run.result = result
        pipeline_run.save()

    @database_sync_to_async
    def set_progress(self, run):
        run.status = Status.PROCESSING
        run.save()

    @database_sync_to_async
    def get_priority(self, user_id):
        run_count = Run.objects.filter(user_id=user_id).count()
        total_count = Run.objects.count()

        percentage = run_count / total_count

        return int(120 * (1 - percentage)) + 7

    async def _request(self, queue_name, body, run: Run, page_num=None):
        correlation_id = myuuid()
        queue: asyncio.Queue[IncomingMessage] = asyncio.Queue()
        await self.save_pipeline_run(correlation_id, run, page_num)
        self.queues[correlation_id] = queue
        assert self.channel is not None
        assert self.channel.default_exchange is not None
        assert self.callback_queue is not None
        await self.channel.default_exchange.publish(
            Message(
                body.encode(),
                content_type='application/json',
                correlation_id=correlation_id,
                reply_to=self.callback_queue.name,
                priority=await self.get_priority(run.user_id)
            ),
            routing_key=queue_name,
        )
        return correlation_id

    async def get_queue_count(self):
        return len(self.queues)

    async def receive(self, correlation_id, name, run: Run, page_num=None):
        """Yields a single message that is tagged to a correlation_id"""
        queue = self.queues[correlation_id]

        progress_msg = await queue.get()
        progress_text = json.loads(progress_msg.body.decode("utf-8"))
        if progress_msg.headers["status"] != "success" or progress_text != {"progress": "processing"}:
            logger.error(f"Progressmsg for for {progress_msg.correlation_id} failed")
            await self.add_pipeline_error(correlation_id, progress_text)
            raise PipelineError(progress_text,
                                name,
                                progress_msg.correlation_id,
                                page_num)
        await self.set_progress(run)

        msg = await queue.get()
        await msg.ack()
        msg_text = msg.body.decode("utf-8")
        del self.queues[correlation_id]

        if msg.headers["status"] != "success":
            logger.error(f"Message for {msg.correlation_id} failed")
            await self.add_pipeline_error(correlation_id, msg_text)
            raise PipelineError(msg_text,
                                name,
                                msg.correlation_id,
                                page_num)

        msg_json = json.loads(msg_text)
        await self.add_pipeline_result(correlation_id, msg_json)
        if page_num is None:
            logger.info(f"finished pipeline '{name}' on '{run.file_name}'")
        else:
            logger.info(f"finished pipeline '{name}-{page_num}' on "
                        f"'{run.file_name}'")
        return msg_json

    async def request_data(self, pipeline, request, run: Run, page_num=None):
        if page_num is None:
            logger.info(f"running pipeline '{pipeline.name}' on "
                        f"'{run.file_name}'")
        else:
            logger.info(f"running pipeline '{pipeline.name}-{page_num}'"
                        f"on {run.file_name}")
        body = json.dumps(request)
        corr_id = await self._request(pipeline.queue_name, body, run, page_num)
        return await self.receive(corr_id, pipeline.name, run, page_num)

    async def request_tasks(self,
                            pipeline,
                            tasks: Dict[str, asyncio.Task],
                            run: Run,
                            page_num=None):
        request = {
            dependency: await tasks[dependency]
            for dependency in pipeline.depends_on
        }
        if len(pipeline.depends_on) == 1:
            request = request[pipeline.depends_on[0]]

        return await self.request_data(pipeline, request, run, page_num)

    async def process_case(self, initial_request, run):
        pipelines = self.config.pipelines.pipelines
        first_pipeline = pipelines[0]
        request = await self.request_data(first_pipeline, initial_request, run)

        pages = request["pages"]
        pages_count = len(pages)
        page_tasks = []
        run.page_count = pages_count
        for i in range(pages_count):
            tasks: Dict[str, asyncio.tasks] = {
                first_pipeline.name: asyncio.create_task(select_page(pages, i))
            }
            for pipeline in pipelines[1:]:
                tasks[pipeline.name] = asyncio.create_task(
                    self.request_tasks(pipeline, tasks, run, page_num=i))
            page_tasks.append(tasks)

        flat_tasks = itertools.chain.from_iterable(tasks.values()
                                                   for tasks in page_tasks)
        flat_results = list(await asyncio.gather(*flat_tasks))

        pages = [{
            pipe.name: flat_results[i * len(pipelines) + j]
            for j, pipe in enumerate(pipelines)
        } for i in range(pages_count)]
        if self.config.pipelines.return_last:
            pages = [
                page[pipelines[-1].name]
                for page in pages
            ]

        request["pages"] = pages
        return request

    async def close(self):
        await self.connection.close()
