FROM node:20-bullseye AS build

WORKDIR /app

COPY package.json yarn.lock ./
RUN yarn install --frozen-lockfile

COPY . .
RUN yarn build

# ---------- production stage ----------
FROM node:20-bullseye-slim

WORKDIR /app

RUN npm install -g serve@14

COPY --from=build /app/build ./build
COPY --from=build /app/serve.json ./build/serve.json

EXPOSE 3000

# serve -s enables SPA mode: all unknown routes -> index.html
CMD ["serve", "-s", "build", "-l", "3000"]
