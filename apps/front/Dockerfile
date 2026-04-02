FROM node:18-alpine AS builder

RUN apk add --no-cache libc6-compat
WORKDIR /app

RUN npm install -g pnpm

COPY package.json pnpm-workspace.yaml pnpm-lock.yaml turbo.json ./
RUN npm pkg delete scripts.postinstall

COPY packages ./packages
COPY apps/front ./apps/front

RUN pnpm install 
RUN pnpm build

FROM node:18-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production

RUN apk add --no-cache libc6-compat && \
    npm install -g pnpm

COPY --from=builder /app /app

WORKDIR /app/apps/front

EXPOSE 3000

CMD ["pnpm", "start"]