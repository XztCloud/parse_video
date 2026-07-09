FROM python:3.12-slim

WORKDIR /app




# 针对 Python 3.12 (Debian Bookworm) 的精确换源命令
RUN sed -i 's/URIs: http:\/\/deb.debian.org/URIs: http:\/\/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources && \
    apt-get update && \
    apt-get install -y ffmpeg && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/


COPY . .

RUN pip install --upgrade pip
RUN pip install -e .

CMD ["start-api"]