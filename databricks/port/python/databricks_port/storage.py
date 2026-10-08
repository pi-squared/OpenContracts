"""Durable pilot source/media storage through Django's native Storage API."""

from urllib.parse import quote

from databricks_port.lakebase import connect
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import Storage


class LakebaseStorage(Storage):
    def _open(self, name, mode="rb"):
        with connect() as database, database.cursor() as cursor:
            cursor.execute("SELECT content FROM port_blob WHERE name=%s", (name,))
            row = cursor.fetchone()
        if row is None:
            raise FileNotFoundError(name)
        return ContentFile(bytes(row[0]), name=name)

    def _save(self, name, content):
        data = b"".join(content.chunks())
        while True:
            with connect() as database, database.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO port_blob VALUES (%s,%s) ON CONFLICT (name) DO NOTHING RETURNING name",
                    (name, data),
                )
                if cursor.fetchone() is not None:
                    return name
            name = self.get_available_name(name)

    def exists(self, name):
        with connect() as database, database.cursor() as cursor:
            cursor.execute("SELECT 1 FROM port_blob WHERE name=%s", (name,))
            return cursor.fetchone() is not None

    def size(self, name):
        with connect() as database, database.cursor() as cursor:
            cursor.execute(
                "SELECT octet_length(content) FROM port_blob WHERE name=%s", (name,)
            )
            row = cursor.fetchone()
        if row is None:
            raise FileNotFoundError(name)
        return row[0]

    def delete(self, name):
        with connect() as database, database.cursor() as cursor:
            cursor.execute("DELETE FROM port_blob WHERE name=%s", (name,))

    def listdir(self, path):
        prefix = path.rstrip("/") + "/" if path else ""
        pattern = (
            prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        )
        directories, files = set(), []
        with connect() as database, database.cursor() as cursor:
            cursor.execute("SELECT name FROM port_blob WHERE name LIKE %s", (pattern,))
            for (name,) in cursor.fetchall():
                remainder = name[len(prefix) :]
                directory, separator, _ = remainder.partition("/")
                if separator:
                    directories.add(directory)
                else:
                    files.append(remainder)
        return sorted(directories), sorted(files)

    def url(self, name):
        return settings.APP_ORIGIN + "/port/media/" + quote(name, safe="/")
