FROM node:24-bookworm-slim
WORKDIR /app
COPY --chown=node:node bridge.cjs package.json ./
RUN mkdir /app/vendor && chown node:node /app/vendor
USER node
ENV NODE_ENV=production
ENV PORT=8080
EXPOSE 8080
CMD ["node", "bridge.cjs"]
