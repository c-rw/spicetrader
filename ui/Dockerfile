FROM node:20-alpine

WORKDIR /app

COPY package.json /app/package.json
RUN npm install --no-audit --no-fund

COPY . /app/

RUN npm run build

ENV HOST=0.0.0.0
ENV PORT=3000
ENV API_BASE_URL=http://spicetrader-api:8000

EXPOSE 3000
CMD ["node", "build"]
