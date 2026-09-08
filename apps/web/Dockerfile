FROM node:22.21.1-bookworm-slim AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM node:22.21.1-bookworm-slim

WORKDIR /app
ENV NODE_ENV=production

COPY --from=build /app ./

EXPOSE 3000

CMD ["npm", "run", "start"]
