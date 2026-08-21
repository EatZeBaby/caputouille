# Déploiement & previews de branches

Notes pour se souvenir de comment le site est publié et comment prévisualiser
une branche en ligne sans casser le site principal.

## Comment le site est publié

- **Hébergement** : GitHub Pages, dépôt `EatZeBaby/caputouille`.
- **Source Pages** : *Deploy from a branch* → branche **`gh-pages`**, dossier **`/ (root)`**
  (réglage dans Settings → Pages ; nécessite un accès admin au dépôt).
- **Workflow** : `.github/workflows/deploy.yml` — à chaque push sur `main`,
  [`peaceiris/actions-gh-pages`](https://github.com/peaceiris/actions-gh-pages)
  publie le dossier `app/` à la **racine** de la branche `gh-pages`.
  L'option `keep_files: true` **préserve** tout ce qui est sous `preview/`.

URL de prod : https://eatzebaby.github.io/caputouille/

> GitHub Pages ne sert **qu'un seul site par dépôt**. On ne peut donc pas avoir
> deux sites Pages « natifs » sur deux branches. L'astuce ci-dessous contourne
> ça en publiant chaque branche dans un **sous-dossier** de la même branche
> `gh-pages`.

## Prévisualiser une branche en ligne (sous-chemin)

Pour donner une URL live à une branche `ma-branche`, sans toucher au site
principal, ajouter sur cette branche un workflow qui publie dans un
sous-dossier `preview/<nom>/` avec `keep_files: true` :

```yaml
# .github/workflows/preview.yml  (sur la branche à prévisualiser)
name: Deploy preview (ma-branche)
on:
  push:
    branches: [ma-branche]
  workflow_dispatch:
permissions:
  contents: write
concurrency:
  group: gh-pages          # évite les écritures concurrentes sur gh-pages
  cancel-in-progress: false
jobs:
  deploy-preview:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: peaceiris/actions-gh-pages@v4
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: ./app
          destination_dir: preview/ma-branche
          keep_files: true
```

La preview est alors servie à
`https://eatzebaby.github.io/caputouille/preview/ma-branche/`, à côté du site
principal qui reste à la racine. Les chemins de l'app sont relatifs, donc ça
marche sans configuration de `base`.

### Nettoyer une preview
1. Supprimer le workflow `preview.yml` (sinon il la reconstruit).
2. Retirer le dossier de la branche `gh-pages` :
   ```bash
   git fetch origin gh-pages
   git worktree add /tmp/ghp gh-pages
   git -C /tmp/ghp rm -r preview/ma-branche
   git -C /tmp/ghp commit -m "Remove preview/ma-branche"
   git -C /tmp/ghp push origin gh-pages
   git worktree remove /tmp/ghp
   ```
3. Supprimer la branche : `git push origin --delete ma-branche`.

## Rafraîchir le contenu depuis Hamstouille Bambin

Le contenu vient de `bambin.hamstouille.fr` (derrière login + reCAPTCHA). Pour
un nouveau scrape :

1. Se connecter dans un navigateur, récupérer le cookie `PHPSESSID`, puis
   `export BAMBIN_PHPSESSID=<valeur>`.
2. `python3 scraper_bambin.py recipes --all` (et `blog`, `batch`, `assiette`,
   `qcnmp`).
3. `python3 merge_bambin.py` — fusionne dans `app/` en dédupliquant par titre,
   sans rien supprimer (base bébé pristine lue depuis `data/`, ids bambin
   décalés de +100000).
4. `python3 build_standalone.py` — reconstruit la version iPad hors-ligne.
