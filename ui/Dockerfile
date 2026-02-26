FROM node:20.18-alpine3.20

WORKDIR /app

# Copy both package.json and lockfile for reproducible installs.
# Generate the lockfile locally with: npm install --package-lock-only
COPY package.json package-lock.json* /app/
RUN if [ -f package-lock.json ]; then npm ci --no-audit --no-fund; else npm install --no-audit --no-fund; fi

COPY . /app/

RUN npm run build

ENV HOST=0.0.0.0
ENV PORT=3000
ENV API_BASE_URL=http://spicetrader-api:8000

EXPOSE 3000
CMD ["node", "build"]
