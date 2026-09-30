FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# LibreOffice без графики — PDF отчётов родителям из того же docx, что уходит
# в Word: один источник, одинаковая вёрстка. Шрифты шаблонов школы:
# DejaVu Sans, Liberation Serif (метрики Times New Roman) и цветные эмодзи.
# gettext — переводы сервера: makemessages и compilemessages (locale/*.po → .mo).
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential libpq5 curl gettext \
    libreoffice-writer-nogui fonts-dejavu-core fonts-liberation fonts-noto-color-emoji \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-dev.txt ./
ARG INSTALL_DEV=false
RUN pip install --upgrade pip \
 && if [ "$INSTALL_DEV" = "true" ]; then pip install -r requirements-dev.txt; else pip install -r requirements.txt; fi

COPY . .

EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
