FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py .
COPY web ./web
RUN useradd -r -u 10001 biko && mkdir /data && chown biko /data
USER biko
ENV DATA_DIR=/data TZ=Europe/Vienna PYTHONUNBUFFERED=1
EXPOSE 8092
CMD ["python", "server.py"]
