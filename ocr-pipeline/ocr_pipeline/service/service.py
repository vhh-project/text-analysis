from collections import namedtuple
from concurrent import futures
import threading
import time

from kombu import Connection, Exchange, Queue
from kombu.mixins import ConsumerProducerMixin
from loguru import logger
from prometheus_client import start_http_server, Histogram

from ocr_pipeline.processing.processor import Processor
from ocr_pipeline.service.config import Config
from ocr_pipeline.service.filestorage import FileStorage

REQUEST_TIME = Histogram('process_message_time',
                         'Time spent processing an incoming message')

Task = namedtuple('Task', 'message, future')


class OcrService(ConsumerProducerMixin, threading.Thread):

    def __init__(self, connection: Connection, config: Config):
        super().__init__()
        self.daemon = True
        self.should_stop = False
        self.ready = False
        self.connection = connection
        self.workerqueue = config.amqp.inqueue
        self.dlx = config.amqp.dlx
        self.invalidqueue = config.amqp.invalidqueue
        self.config = config
        self.executor = futures.ThreadPoolExecutor(max_workers=1)
        self.task = None
        self.fs = FileStorage.from_config(config)
        self.processor = Processor(config, self.fs)


    def _setup_dlx_exchange(self, channel):
        dlx_exchange = Exchange(self.dlx, type="fanout")
        self.dlx_exchange = dlx_exchange(channel)

    def _setup_invalid_queue(self, channel):
        queue = Queue(
            name=self.invalidqueue,
            exchange=self.dlx_exchange
        )
        self.invalid_queue = queue(channel)

    def _setup_worker_queue(self, channel):
        q_args = {
            'x-dead-letter-exchange': self.dlx,
            'x-dead-letter-routing-key': self.workerqueue,
            'x-max-priority': 127,
        }
        worker_queue = Queue(self.workerqueue, queue_arguments=q_args)
        self.worker_queue = worker_queue(channel)

    def _has_required_property(self, prop, message):
        prop_val = message.properties.get(prop, None)
        if not prop_val:
            return False
        return True

    def _handle_incoming_message(self, body, message):
        """Execute handling of task"""
        if self.task is not None:
            error = "Task was not None"
            logger.error(error)
            self.stop()
            raise ValueError(error)

        logger.debug("Verify incoming message properties")
        for prop in ['correlation_id', 'reply_to', 'content_type']:
            if not self._has_required_property(prop, message):
                logger.warning("Rejecting {} with body {} as {} was not set",
                               message, body, prop)
                message.reject(requeue=False)
                return

        logger.info("[{}] started", message.properties['correlation_id'])
        future = self.executor.submit(self._process_message_wrapper,
                                      body,
                                      message.properties)

        self._reply(message, {"progress": "processing"}, "success")
        self.task = Task(
            message,
            future
        )

    def _reply(self, message, result, status="success"):
        headers = {
            "service": self.__class__.__name__,
            "status": status
        }
        self.producer.publish(
            result,
            exchange='',
            routing_key=message.properties['reply_to'],
            correlation_id=message.properties['correlation_id'],
            headers=headers,
            serializer='json',
            retry=True
        )

    def _handle_task_finished(self):
        correlation_id = self.task.message.properties['correlation_id']
        try:
            status = "success"
            result = self.task.future.result()
        except Exception as e:
            logger.exception(
                f"[{correlation_id}]Exception occurred during handling"
            )
            status = "error"
            result = f"Request {self.task.message.decode()} failed\n{repr(e)}"
        self._reply(self.task.message, result, status)
        self.task.message.ack()
        logger.info(f"[{correlation_id}] done")

    def wait_ready(self):
        while not self.ready:
            time.sleep(0.1)

    def stop(self):
        self.executor.shutdown()
        self.should_stop = True

    def get_consumers(self, Consumer, channel):
        self._setup_dlx_exchange(channel)
        self._setup_invalid_queue(channel)
        self._setup_worker_queue(channel)

        return [Consumer(queues=self.worker_queue,
                         callbacks=[self._handle_incoming_message],
                         accept=['json'],
                         prefetch_count=1)]

    def on_iteration(self):
        if self.task is not None and self.task.future.done():
            logger.debug("task done")
            self._handle_task_finished()
            self.task = None

    def on_connection_error(self, exc, interval):
        super().on_connection_error(exc, interval)
        if self.task:
            logger.info("Dropping currently running task")
            # there is no way to kill the running thread, so we wait for it
            # future.exception() does not reraise compared to future.result()
            self.task.future.exception()
            self.task = None
            logger.info("Dropping currently running task...Done")

    def on_consume_ready(self, connection, channel, consumers):
        """Callback executed one we are ready to consume"""
        self.ready = True
        logger.info("{} is ready for consuming", self)

    def _process_message_wrapper(self, body: dict, properties: dict) -> dict:
        correlation_id = properties["correlation_id"]
        with logger.contextualize(correlation_id=correlation_id):
            return self.process_message(body)

    @REQUEST_TIME.time()
    def process_message(self, body):
        logger.debug("message from queue received: message.body={}", body)
        response = self.processor.run(body)
        logger.debug(response)
        return response


def run(config):
    logger.info("Starting")

    with Connection(config.amqp.url) as conn:
        logger.info("Connected to {}", conn)
        service = OcrService(conn, config)
        try:
            logger.info("start service")
            service.run()
            logger.info("service started")
        except KeyboardInterrupt:
            logger.info("Received KeyboardInterrupt, closing")


def main():
    run(Config())


if __name__ == "__main__":
    main()
