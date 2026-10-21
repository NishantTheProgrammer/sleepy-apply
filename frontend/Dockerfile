FROM node:22-bookworm-slim

WORKDIR /app

COPY package*.json ./
RUN rm -f package-lock.json && npm install

COPY . .

EXPOSE 3000

ENV HOSTNAME="0.0.0.0"
ENV PORT=3000

CMD ["npm", "run", "dev"]
