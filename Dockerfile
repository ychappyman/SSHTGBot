FROM python:3.9-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 复制 requirements.txt 并安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 设置环境变量，使用 10000 作为默认端口
ENV PORT=10000

# 暴露端口
EXPOSE $PORT

# 使用 Hypercorn 运行应用
CMD hypercorn app:app --bind 0.0.0.0:$PORT --workers 1
