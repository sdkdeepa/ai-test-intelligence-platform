FROM node:22-slim AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM node:22-slim

WORKDIR /app
RUN npm install -g serve

COPY --from=build /app/dist ./dist

# Sprint 14 hardening: node:*-slim ships an unprivileged `node` user
# (uid 1000) out of the box — no need to create one, just switch to it.
# `dist/` is plain static output, so `node` needs no special ownership grant
# beyond what COPY already gives it as the image's build-time root.
USER node

EXPOSE 4173

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD node -e "require('http').get('http://localhost:4173', r => process.exit(r.statusCode === 200 ? 0 : 1)).on('error', () => process.exit(1))"

CMD ["serve", "-s", "dist", "-l", "4173"]
