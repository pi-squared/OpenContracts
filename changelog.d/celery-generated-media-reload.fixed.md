Exclude generated local media from the development worker's file watcher so uploads and parsing do not restart Celery and strand document processing before its final unlock task.
