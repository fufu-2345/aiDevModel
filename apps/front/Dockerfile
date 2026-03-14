FROM node:18-alpine

WORKDIR /app

RUN npm install -g pnpm

COPY package.json pnpm-lock.yaml* ./

RUN pnpm install 

COPY . . 

RUN pnpm build

EXPOSE 3000
ENV NODE_ENV=production

CMD ["next", "start",]