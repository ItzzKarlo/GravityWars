FROM node:22-alpine AS dependencies
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-alpine AS builder
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=dependencies /app/node_modules ./node_modules
COPY . .
# Next.js projects without static assets have no public/ directory.
# Keep the runtime COPY valid while preserving any future public assets.
RUN mkdir -p public && npm run build

FROM node:22-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000
RUN addgroup --system --gid 10001 gravitywars \
    && adduser --system --uid 10001 --ingroup gravitywars gravitywars
COPY --from=builder --chown=gravitywars:gravitywars /app/public ./public
COPY --from=builder --chown=gravitywars:gravitywars /app/.next/standalone ./
COPY --from=builder --chown=gravitywars:gravitywars /app/.next/static ./.next/static
USER gravitywars
EXPOSE 3000
CMD ["node", "server.js"]
