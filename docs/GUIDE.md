# Guide d’utilisation

## Préparer le fichier de sessions

Une ligne représente le résultat global d’un couple `session_id` et `level`. Regrouper les tentatives successives de ce couple dans `attempts`. Une même session peut apparaître sur plusieurs niveaux.

| Colonne | Type attendu |
| --- | --- |
| `session_id` | Obligatoire. Identifiant pseudonyme stable dans le fichier. |
| `level` | Obligatoire. Nom ou identifiant stable du passage. Garder le même libellé entre deux analyses à comparer. |
| `success` | Obligatoire. `1` ou `0`, `oui` ou `non`, `réussite` ou `échec`. |
| `attempts` | Obligatoire. Nombre entier de tentatives, au moins 1. |
| `reaction_ms` | Facultative. Temps de réaction en millisecondes. |
| `timing_accuracy_pct` | Facultative. Précision du timing sur une échelle de 0 à 100. |
| `duration_s` | Facultative. Durée en secondes. |
| `progress_pct` | Facultative. Progression sur une échelle de 0 à 100. |
| `played_at` | Facultative. Date `AAAA-MM-JJ` ou date-heure ISO 8601. Les dates sont ramenées en UTC pour l’agrégation quotidienne. |

```csv
session_id;level;success;attempts;reaction_ms;timing_accuracy_pct;duration_s;progress_pct;played_at
S-001;Orbite;1;2;340;82,5;38;100;2026-11-12
S-001;Périgée;0;4;415;62;55;72;2026-11-12
S-002;Orbite;1;1;278;91;31;100;2026-11-13
```

L’import accepte les fichiers UTF-8, avec ou sans marqueur BOM, et Windows-1252. Les champs peuvent être séparés par des virgules ou des points-virgules. Pour une valeur comme `82,5`, employer le point-virgule comme séparateur ou placer la valeur entre guillemets. Les colonnes hors schéma sont ignorées. Les cellules facultatives vides sont exclues de leur indicateur. Les limites sont 20 Mio, 100 000 lignes de données et 250 niveaux distincts.

Un message indique la colonne et un exemple de ligne pour les valeurs hors format. Corriger la source, puis réimporter. Les identifiants doivent comporter de 1 à 128 caractères et éviter les sauts de ligne. Utiliser des identifiants pseudonymes et des libellés de niveaux sans données personnelles.

## Lire les statistiques

- **Réussite et échec**. Chaque taux rapporte les réussites ou les échecs au nombre de couples session-niveau analysés. Le nombre de sessions distinctes est affiché séparément. Les tentatives moyennes utilisent la colonne `attempts`.
- **Difficulté**. L’intervalle de Wilson à 95 % accompagne le taux par niveau. Il exprime l’incertitude associée à un taux binomial. Lorsque plusieurs observations dépendent des mêmes joueurs ou sessions, sa lecture reste descriptive.
- **Passages à examiner**. L’alerte compare le niveau au reste des observations. Il faut au moins 20 lignes dans le niveau, au moins 20 ailleurs, et un taux du niveau inférieur d’au moins 15 points. Ce seuil sert à prioriser une vérification. Il ne tient pas compte du mélange de populations ou de la difficulté prévue.
- **Timing**. L’écart entre les précisions moyennes des réussites et des échecs utilise uniquement les valeurs disponibles dans chaque groupe. Une association donne une piste de test. Elle peut aussi refléter la sélection des joueurs ou la conception du niveau.
- **Progression**. Le champ `progress_pct` mesure l’avancement enregistré. La courbe temporelle regroupe par jour les lignes dotées de `played_at`. Si les dates manquent, l’ordre des lignes ne permet pas de reconstruire une évolution. Comparer des données de même version et des populations semblables pour évaluer un changement.

## Lancer et lire l’investigation

Dans **Agent local**, sélectionner un modèle téléchargé. La connexion est affichée avant le lancement. Pendant le traitement, Qwen3 sélectionne des outils accessibles à l’agent. Le programme calcule leurs résultats, valide les entrées et renvoie les agrégats au modèle. Qwen3 sélectionne ensuite des actions du catalogue et les mesures qui les étayent. L’application contrôle ces références et affiche le libellé, la justification et les limites du catalogue. La trace permet de remonter aux outils qui ont produit les mesures citées.

Une proposition documente un problème, les indicateurs associés, l’essai proposé et sa justification. Vérifier les preuves et les limites affichées. Une variation chiffrée comme un élargissement de la fenêtre de timing de 10 % est un réglage d’essai défini dans le catalogue. L’effet de ce réglage doit être mesuré en jeu. Les recommandations commencent **En attente**. Sélectionner **Acceptée** ou **Rejetée**, puis cliquer sur **Enregistrer la décision** pour conserver le choix.

Sélectionner un résultat dans **Analyse active**. Dans **Historique**, choisir **Comparer l’analyse active avec** dès que deux imports sont disponibles. La comparaison indique l’écart en points de pourcentage sur les niveaux communs. Le rapport HTML est consultable dans un navigateur. Le JSON conserve la structure des recommandations pour réutilisation et le CSV facilite la lecture tabulaire. Les données de travail restent dans le dossier `.runtime/`, avec la base `analyses.sqlite3` et les journaux. Pour garder l’historique, faire une copie de la base une fois l’application arrêtée.

L’historique conserve les agrégats, le nom du fichier et les rapports. Pour conserver la possibilité de recalculer une analyse à partir de ses lignes, garder le fichier CSV source de son côté.

## Dépannage Windows

| Symptôme | Vérification |
| --- | --- |
| Le navigateur n’ouvre pas l’application | Garder la fenêtre de lancement ouverte et vérifier l’adresse [127.0.0.1:8765](http://127.0.0.1:8765). En cas de dépendances absentes, relancer `Installer.cmd`. |
| Ollama est inaccessible | Ouvrir Ollama pour Windows. Avec l’archive portable, vérifier la présence de `.runtime/ollama/ollama.exe` et relancer `Lancer.cmd`. |
| Le modèle sélectionné manque | Exécuter `ollama pull qwen3:8b` avec Ollama lancé. Pour le profil léger, exécuter `ollama pull qwen3:4b` ou `ollama pull qwen3:1.7b`, puis sélectionner le profil correspondant. |
| La réponse est trop lente ou échoue | Essayer sur une machine moins chargée, puis avec une variante plus légère. Pendant que le modèle est chargé, consulter `ollama ps` pour voir l’exécution GPU, CPU ou mixte. |
| L’interface rejette le CSV | Lire le message d’import, puis comparer le fichier au schéma ci-dessus et vérifier l’unicité des couples `session_id` et `level`. |

### Installer Ollama à partir de son archive portable

1. Télécharger l’archive Windows amd64 officielle d’Ollama et l’extraire dans `.runtime/ollama/`. Conserver les bibliothèques de l’archive à côté de `ollama.exe`.
2. Exécuter `Installer.cmd`, puis `Lancer.cmd`. Le lanceur réutilise un serveur déjà actif sur `127.0.0.1:11434` ou démarre l’exécutable portable. Dans ce second cas, les poids téléchargés sont stockés dans `.runtime/models/`.
3. Ouvrir un terminal PowerShell à la racine du projet pendant que l’application est ouverte. Télécharger le modèle via le serveur actif, puis cliquer sur **Vérifier la disponibilité** dans **Agent local**.

```powershell
& .\.runtime\ollama\ollama.exe pull qwen3:8b
```

Les variantes `qwen3:4b` et `qwen3:1.7b` occupent environ 2,5 Go et 1,4 Go sur disque. Prévoir de l’espace supplémentaire pour les binaires et la mémoire de travail. [Archives officielles d’Ollama](https://github.com/ollama/ollama/releases) · [Ollama pour Windows](https://docs.ollama.com/windows) · [Matériel compatible](https://docs.ollama.com/gpu) · [Fiche 4B](https://ollama.com/library/qwen3:4b) · [Fiche 1.7B](https://ollama.com/library/qwen3:1.7b)
