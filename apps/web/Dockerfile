FROM node:22.21.1-bookworm-slim AS build

WORKDIR /app

ARG API_BASE_URL=http://api:8000
ARG AUTH_DATABASE_URL=postgresql://careeract:careeract@postgres:5432/careeract
ARG BETTER_AUTH_SECRET=build-only-secret-build-only-secret
ARG BETTER_AUTH_URL=http://localhost
ENV API_BASE_URL=$API_BASE_URL
ENV AUTH_DATABASE_URL=$AUTH_DATABASE_URL
ENV BETTER_AUTH_SECRET=$BETTER_AUTH_SECRET
ENV BETTER_AUTH_URL=$BETTER_AUTH_URL

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM node:22.21.1-bookworm-slim

WORKDIR /app
ENV NODE_ENV=production

COPY --from=build --chown=node:node /app/public ./public
COPY --from=build --chown=node:node /app/.next/standalone ./
COPY --from=build --chown=node:node /app/.next/static ./.next/static

EXPOSE 3000

USER node

CMD ["node", "server.js"]
