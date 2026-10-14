FROM python:3.13.16-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv/app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Fixed uid: ops/stack-start.sh gives the app's secret files to this user.
RUN groupadd --gid 10001 app \
 && useradd --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app
USER 10001:10001

EXPOSE 8000
# --no-control-socket: gunicorn's control socket would go in $HOME, which does
# not exist on the read-only file system, and nothing here uses gunicornc.
CMD ["sh", "-c", "python manage.py migrate --noinput && exec gunicorn dixie.wsgi --no-control-socket --bind 0.0.0.0:8000 --workers 3 --access-logfile -"]
