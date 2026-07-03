# ─── Stage 1: Builder ───────────────────────────────────────────────────────
FROM node:24-slim AS builder

ARG VITE_BACKEND_URL=
ARG VITE_INSFORGE_PROJECT_URL
ARG VITE_INSFORGE_ANON_KEY

WORKDIR /app

# Copy package files with correct ownership
COPY package*.json ./
RUN npm ci

# Copy source code
COPY . .

# Inject build arguments as environment variables for Vite compiler
ENV VITE_BACKEND_URL=${VITE_BACKEND_URL}
ENV VITE_INSFORGE_PROJECT_URL=${VITE_INSFORGE_PROJECT_URL}
ENV VITE_INSFORGE_ANON_KEY=${VITE_INSFORGE_ANON_KEY}
RUN npm run build


# ─── Stage 2: Final (Nginx unprivileged) ────────────────────────────────────
FROM nginxinc/nginx-unprivileged:1.27-alpine

# Remove default nginx config before switching to nginx user
RUN rm /etc/nginx/conf.d/default.conf

# Copy custom Nginx configuration and static React assets
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -q -O- http://localhost:8080/ || exit 1

CMD ["nginx", "-g", "daemon off;"]