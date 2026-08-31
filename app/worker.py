from redis import Redis
from rq import SimpleWorker
from rq.serializers import JSONSerializer

from .config import settings
from .queue import get_redis_connection


def main() -> None:
    connection: Redis = get_redis_connection()
    worker = SimpleWorker([settings.ai_queue_name], connection=connection, serializer=JSONSerializer)
    worker.work(with_scheduler=True)


if __name__ == "__main__":
    main()
