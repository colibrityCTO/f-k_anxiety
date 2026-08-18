# Front : build en une étape, image finale sans outillage de build.
#
# Pourquoi un Dockerfile plutôt que Nixpacks : Railway monte un cache sur
# /app/node_modules/.cache, et `npm ci` commence par supprimer node_modules en
# entier. On ne peut pas supprimer un point de montage — d'où l'échec
# « EBUSY: resource busy or locked, rmdir '/app/node_modules/.cache' ».
# Avec un Dockerfile, aucun cache n'est monté à cet endroit et le build est
# reproductible.

FROM node:22-alpine AS build
WORKDIR /app

# Les dépendances d'abord : cette couche n'est reconstruite que si les
# manifestes changent.
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY . .

# Le front appelle toujours /api ; c'est le serveur qui relaie vers le backend
# (voir server.mjs). L'URL du backend est donc un réglage d'exécution, pas une
# valeur figée dans le bundle.
ENV VITE_API_URL=/api
RUN npm run build

# ---------------------------------------------------------------------------

FROM node:22-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production

# Rien d'autre que les fichiers compilés et le serveur : pas de Vite, pas de
# TypeScript, pas d'esbuild dans l'image qui tourne.
COPY --from=build /app/dist ./dist
COPY server.mjs ./

# Utilisateur non privilégié, déjà présent dans l'image officielle.
USER node

EXPOSE 4173
CMD ["node", "server.mjs"]
