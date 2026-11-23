import os
import signal
from threading import Event, Thread

from celery import bootsteps
from celery.utils.log import get_logger
from celery.worker.components import Beat

from wine_cellar.conf.celery import celery_app

logger = get_logger(__name__)


class BeatWatchdog(bootsteps.StartStopStep):
    requires = (Beat,)

    def __init__(self, worker, **kwargs):
        self.stopping = Event()
        self.thread = None
        super().__init__(worker, **kwargs)

    def start(self, worker):
        if worker.beat is None:
            raise RuntimeError("Embedded Celery Beat is required")
        self.thread = Thread(target=self.watch, args=(worker.beat,), daemon=True)
        self.thread.start()

    def watch(self, beat):
        while not self.stopping.wait(2):
            if not beat.is_alive():
                logger.error("Embedded Celery Beat exited; restarting the worker")
                os.kill(os.getpid(), signal.SIGTERM)
                return

    def close(self, worker):
        self.stopping.set()

    def stop(self, worker):
        self.stopping.set()
        if self.thread is not None:
            self.thread.join()

    terminate = stop


celery_app.steps["worker"].add(BeatWatchdog)
