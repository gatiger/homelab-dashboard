FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .

# Bundle dashboard-oriented service logos into the production image. Existing
# checked-in icons are kept; additional catalog icons are fetched at build time.
RUN mkdir -p public/icons && \
    if [ -f icon-slugs.txt ]; then \
      while IFS= read -r icon; do \
        [ -z "$icon" ] && continue; \
        svg="public/icons/${icon}.svg"; \
        png="public/icons/${icon}.png"; \
        if [ ! -s "$svg" ] && [ ! -s "$png" ]; then \
          wget -q -O "$svg" "https://raw.githubusercontent.com/homarr-labs/dashboard-icons/refs/heads/main/svg/${icon}.svg" || { \
            rm -f "$svg"; \
            wget -q -O "$png" "https://raw.githubusercontent.com/homarr-labs/dashboard-icons/refs/heads/main/png/${icon}.png" || { rm -f "$png"; echo "Icon unavailable: $icon"; }; \
          }; \
        fi; \
      done < icon-slugs.txt; \
    fi
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
