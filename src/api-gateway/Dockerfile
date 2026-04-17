# syntax=docker/dockerfile:1.7

# --- Builder stage ---
FROM node:20-alpine AS builder
WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install --no-audit --no-fund

COPY tsconfig*.json nest-cli.json ./
COPY src ./src

RUN npm run build && npm prune --omit=dev

# --- Runtime stage ---
FROM node:20-alpine AS runtime
WORKDIR /app

ENV NODE_ENV=production \
    PORT=3000

RUN apk add --no-cache curl \
    && addgroup -S nodejs && adduser -S nestjs -G nodejs

COPY --from=builder --chown=nestjs:nodejs /app/node_modules ./node_modules
COPY --from=builder --chown=nestjs:nodejs /app/dist ./dist
COPY --from=builder --chown=nestjs:nodejs /app/package.json ./package.json

USER nestjs

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:3000/health || exit 1

CMD ["node", "dist/main.js"]
