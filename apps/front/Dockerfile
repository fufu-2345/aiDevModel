FROM node:18-alpine

RUN apk add --no-cache libc6-compat
WORKDIR /app

RUN npm install -g pnpm

COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./

COPY packages ./packages

COPY apps/front ./apps/front

RUN pnpm install 

RUN pnpm build

EXPOSE 3000
ENV NODE_ENV=production

CMD ["pnpm", "start",]