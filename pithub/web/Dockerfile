# pithub 웹 (Fly.io) — Next.js standalone
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# NEXT_PUBLIC_* 는 빌드 시점에 번들에 박힌다. Fly의 build secret/arg 로 전달한다.
ARG NEXT_PUBLIC_SUPABASE_URL
ARG NEXT_PUBLIC_SUPABASE_ANON_KEY
ARG NEXT_PUBLIC_PITHUB_MCP_URL
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production PORT=3000 HOSTNAME=0.0.0.0
RUN addgroup -S pithub && adduser -S pithub -G pithub
COPY --from=build --chown=pithub:pithub /app/.next/standalone ./
COPY --from=build --chown=pithub:pithub /app/.next/static ./.next/static
COPY --from=build --chown=pithub:pithub /app/public ./public
USER pithub
EXPOSE 3000
CMD ["node", "server.js"]
