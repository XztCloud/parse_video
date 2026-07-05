FROM node:20

WORKDIR /app

COPY package*.json ./
RUN npm install --registry=https://registry.npmmirror.com

COPY . .

RUN npm run build

CMD ["npm", "run", "start"]