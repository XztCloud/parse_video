FROM python:3.12-slim

WORKDIR /app

# 1. 精确换源并安装系统依赖 (ffmpeg)
RUN sed -i 's/URIs: http:\/\/deb.debian.org/URIs: http:\/\/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources && \
    apt-get update && \
    apt-get install -y ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# 2. 升级 pip
RUN pip install --no-cache-dir --upgrade pip -i https://mirrors.aliyun.com/pypi/simple/

# 3. 利用缓存：只复制 pyproject.toml 来安装巨型依赖包
COPY pyproject.toml .

# 创建一个空的 app 目录，防止 setuptools 找不到 packages=["app"] 而报错
RUN mkdir app && \
    pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ . || true

# 4. 复制其余所有源码（此时修改业务代码，上方步骤 1-3 全部走缓存，秒级构建）
COPY . .

# 5. 正式安装整个项目（不加 -e，直接打包进 site-packages）
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ .

# 6. 使用你配置的 project.scripts 启动命令
CMD ["start-api"]