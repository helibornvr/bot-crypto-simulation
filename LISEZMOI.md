# Bot crypto en simulation

Ce bot surveille les vrais prix de Coinbase toutes les 10 minutes, jour et nuit, et applique les règles du Carnet de cycles crypto avec **220 € fictifs**. Quand une action est à faire, il t'envoie une notification sur ton téléphone, par exemple :

> **ACHETER SOL · tranche 1**
> Achète 5,00 € de SOL au prix limite de 62,29 € (prix actuel 61,80 €).
> Puis pose un stop à 50,09 €.
> Objectifs : 77,06 € (vendre la moitié), puis 89,91 €.

Il ne passe aucun ordre et ne se connecte à aucun compte. C'est toi qui décides et qui passes l'ordre sur Coinbase, si tu le veux.

## Ce qu'il fait

| Situation | Notification |
|---|---|
| Le prix passe sous le seuil de la tranche 1 ou 2 | ACHETER, avec le montant, le prix limite et le stop à poser |
| Le prix atteint l'objectif 1 | VENDRE 50 %, puis remonter le stop au prix d'achat moyen |
| Le prix atteint l'objectif 2 | VENDRE le reste |
| Le prix passe sous le stop | VENDRE tout sur cette crypto |
| Le bitcoin perd plus de 5 % en 24 h | PAUSE des achats (puis fin de pause quand ça se calme) |
| Le cycle perd 10 % | Achats BLOQUÉS |
| Le cycle perd 20 % | VENDRE TOUT, le bot s'arrête |
| Chaque soir vers 20 h | Bilan du jour, ce qui prouve aussi que le bot tourne |

Les seuils sont ceux du carnet du 24 novembre 2026, convertis en euros. Ils sont dans `config.json`.

## Les fichiers

- `bot.py` : le programme.
- `config.json` : les seuils et le budget du cycle.
- `.github/workflows/bot.yml` : la consigne qui fait tourner le bot toutes les 10 minutes sur GitHub.
- `etat.json` et `journal.csv` : créés par le bot. Le journal liste toutes les opérations simulées.

## Installation (environ 15 minutes, gratuit)

### 1. Les notifications sur ton téléphone

1. Installe l'application gratuite **ntfy** (App Store ou Google Play). Pas de compte à créer.
2. Dans l'application, touche **+** et abonne-toi au sujet : le nom secret que Claude t'a donné (ne l'écris jamais dans ce dépôt public)
3. Garde ce nom pour toi : quiconque le connaît peut lire tes notifications.

### 2. L'hébergement sur GitHub

GitHub fait tourner le bot gratuitement à ta place, même quand ton ordinateur est éteint.

1. Crée un compte gratuit sur github.com.
2. Crée un nouveau dépôt nommé `bot-crypto-simulation`, en **Public**. Un dépôt public permet de faire tourner le bot sans limite de temps gratuite. On y voit le code et les opérations fictives, mais pas ton sujet de notification.
3. Dépose dedans les fichiers `bot.py`, `config.json` et `LISEZMOI.md` (bouton **Add file**, puis **Upload files**).
4. Pour la consigne : **Add file**, puis **Create new file**. Tape le nom `.github/workflows/bot.yml`, colle le contenu du fichier `bot.yml`, puis **Commit changes**.
5. Dans **Settings**, puis **Secrets and variables**, puis **Actions**, clique **New repository secret**. Nom : `NTFY_TOPIC`. Valeur : le nom secret que Claude t'a donné (ne l'écris jamais dans ce dépôt public).
6. Dans l'onglet **Actions**, ouvre « Bot crypto (simulation) » et clique **Run workflow**. Tu dois recevoir « Bot démarré · cycle 1 » sur ton téléphone.

Ensuite il n'y a plus rien à faire : le bot tourne seul.

## Bon à savoir

- **Rythme :** GitHub lance le bot toutes les 10 minutes environ, parfois avec quelques minutes de retard. Une chute très brève peut passer entre deux passages. C'est pour ça que les ordres limites et les stops posés à l'avance sur Coinbase restent la vraie protection.
- **Frais :** la simulation compte 0,6 % de frais par opération, comme Coinbase Advanced avec des ordres simples.
- **Prix d'exécution :** un achat simulé se fait au prix constaté par le bot, qui peut être un peu sous le seuil. En vrai, ton ordre limite s'exécuterait au seuil ou mieux.
- **Fin de cycle :** quand tout est clos, ou après 42 jours sans position ouverte, le bot te propose de boucler le cycle. Demande alors à Claude des niveaux à jour : il suffira de remplacer `config.json` et d'y augmenter le numéro de `cycle`.
- **Arrêter le bot :** onglet **Actions**, « Bot crypto (simulation) », menu **…**, **Disable workflow**.

Ce bot est un outil de simulation, pas un conseil financier. Ses résultats sur quelques semaines ne disent pas ce qui se passera ensuite.
