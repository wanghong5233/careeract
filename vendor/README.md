# Vendored Forks

`agno/` and `browser-use/` are project-owned GitHub Forks imported with `git subtree`.

Sync a Fork from upstream, then update this repository:

```powershell
gh repo sync wanghong5233/agno --branch main
git subtree pull --prefix=vendor/agno https://github.com/wanghong5233/agno.git main --squash

gh repo sync wanghong5233/browser-use --branch main
git subtree pull --prefix=vendor/browser-use https://github.com/wanghong5233/browser-use.git main --squash
```

Keep CareerAct business changes outside `vendor/`. When an upstream defect must be patched, commit that vendor change separately. To prepare a branch in the corresponding Fork:

```powershell
git subtree push --prefix=vendor/agno https://github.com/wanghong5233/agno.git careeract-fix
git subtree push --prefix=vendor/browser-use https://github.com/wanghong5233/browser-use.git careeract-fix
```
