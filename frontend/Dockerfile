FROM node:22-alpine

WORKDIR /app

# Сборка по замку, а не по диапазонам из package.json: `npm ci` ставит
# ровно те версии, что в package-lock.json, и падает, если замок разошёлся
# с манифестом. Иначе фронт на сервере собирался бы не тем, чем у нас
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 5173
CMD ["npm", "run", "dev"]
