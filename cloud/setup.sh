#!/bin/bash
# Script de setup des environnements cloud Claude Code (claude.ai/code).
# Chaque environnement cloud l'appelle avec une seule ligne dans son Setup script :
#   curl -fsSL https://raw.githubusercontent.com/GabinSMD/shared-workflows/main/cloud/setup.sh | bash
# Exécuté en root sur la VM Ubuntu avant le lancement de Claude Code.

# 1. Identité git : les commits sont à ton nom, pas « Claude »
git config --global user.name "Gabin SIMOND"
git config --global user.email "59763102+GabinSMD@users.noreply.github.com"

# 2. Pas de ligne « Co-Authored-By: Claude » dans les commits et PR, et droit
#    de livrer sans demander : committer, pousser une branche de travail,
#    ouvrir une PR. Sans ces règles, une session lancée par une tâche planifiée
#    ou par une autre session s'arrête, correctif prêt, avant le commit
#    (constaté le 19/11/2026 sur ecole-saas #450).
#    Interdits quoi qu'il arrive : forcer un push, pousser sur une branche
#    longue, fusionner une PR. La vraie barrière reste la protection de
#    branche du dépôt : ces refus ne sont qu'un garde-fou de plus.
mkdir -p ~/.claude
cat > ~/.claude/settings.json <<'EOF'
{
  "attribution": { "commit": "", "pr": "" },
  "permissions": {
    "allow": [
      "Bash(git add:*)",
      "Bash(git commit:*)",
      "Bash(git switch:*)",
      "Bash(git push:*)",
      "Bash(gh pr create:*)",
      "Bash(gh pr edit:*)",
      "Bash(gh pr comment:*)"
    ],
    "deny": [
      "Bash(git push --force:*)",
      "Bash(git push -f:*)",
      "Bash(git push --force-with-lease:*)",
      "Bash(git push origin main:*)",
      "Bash(git push origin master:*)",
      "Bash(git push origin develop:*)",
      "Bash(git push origin staging:*)",
      "Bash(git push -u origin main:*)",
      "Bash(git push -u origin develop:*)",
      "Bash(gh pr merge:*)"
    ]
  }
}
EOF

# 3. Instructions personnelles chargées dans toutes les sessions cloud
cat > ~/.claude/CLAUDE.md <<'EOF'
# Règles personnelles (sessions cloud)

## Branches et PR (convention commune à tous les projets)
- Branche : `<type>/<n°-issue>-<quelques-mots>`, en minuscules avec des tirets, ex. `feat/982-player-act-warnings`. Le numéro d'issue est omis s'il n'y en a pas.
- Types : feat, fix, refactor, perf, test, docs, chore, ci, build, security, hotfix, revert.
- Titre de PR et commits : Conventional Commits **en anglais**, `type(scope): imperative sentence`, sans point final.
- Jamais de branche `claude/…`. Si la session démarre sur une branche `claude/…`, créer la bonne branche (`git switch -c <nom>`) avant le premier commit, et pousser celle-là.
- Partir de la branche cible du repo (`develop` pour FFD-Connect, sinon la branche par défaut). La CI « PR conventions » de chaque repo vérifie le nom de branche et le titre.
- Pas de ligne `Co-Authored-By: Claude`, de « Generated with Claude Code » ni de lien de session dans les commits et les PR.

## Identité des commits
- Les commits sont au nom de Gabin SIMOND. Avant le premier commit, vérifier `git config user.email` : si c'est `noreply@anthropic.com`, lancer `git config user.name "Gabin SIMOND"` et `git config user.email "59763102+GabinSMD@users.noreply.github.com"` dans le repo.

## Une session, une tâche
- Une session traite **une seule tâche** (une issue, un bug, une PR). Une autre tâche repérée en chemin est notée pour la passation, pas enchaînée.
- La session se termine toujours par un bloc **Passation** :
  - **Fait** : résumé et lien de la PR ;
  - **Reste à faire** : prochaines étapes, pièges et décisions en attente ;
  - **Prompt suivant** : le prompt prêt à coller pour la session suivante, autonome (repo, branche, contexte utile).
- **Créer la session suivante** (proposer, puis faire si l'utilisateur accepte) :
  - depuis une session locale : `claude --cloud "<prompt suivant>"` lancé depuis le repo ;
  - depuis une session cloud : ouvrir une issue GitHub qui contient le prompt suivant, et donner son lien.

## Sessions locales
- Tout se fait ici, dans le cloud. Si une étape a besoin du Mac (simulateur iOS / Xcode / appareil USB, Docker local et ses volumes de données, modifs non poussées, secrets du trousseau, réseau local / homelab), s'arrêter et demander d'ouvrir une session locale (Remote Control « Macbook »), en disant précisément ce qu'il faut y faire.
EOF
