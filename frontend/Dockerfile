FROM node:20

WORKDIR /app

COPY package*.json ./
RUN npm install --registry=https://registry.npmmirror.com

COPY . .

# 接收 compose 传过来的参数
ARG API_PROXY_TARGET
# 将其转为构建时的环境变量，让 next build 能读到
ENV API_PROXY_TARGET=$API_PROXY_TARGET

RUN npm run build

CMD ["npm", "run", "start"]