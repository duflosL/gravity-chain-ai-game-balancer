# Gravity Chain AI Game Balancer

Gravity Chain est un jeu spatial de timing. Pour se propulser d’une planète à l’autre, le joueur doit libérer la comète au bon moment. Le Game Balancer aide à repérer les passages où les échecs se concentrent et à préparer un test d’équilibrage à partir de sessions de jeu.

Le tableau de bord calcule les statistiques sur le PC avec Pandas et NumPy. Un agent Qwen3, exécuté par Ollama, choisit des outils de comparaison, sélectionne des pistes dans un catalogue et indique les mesures qui les étayent. Les décisions sont conservées dans SQLite. Accepter une proposition enregistre un avis humain. Le jeu reste indépendant de l’application.

## Démarrer sur Windows 11

1. Copier ou extraire le projet dans un dossier où l’utilisateur peut écrire.
2. Installer Python 3.12 x64 avec son lanceur `py`, puis Ollama pour Windows. Démarrer Ollama depuis le menu Démarrer. [Télécharger Python](https://www.python.org/downloads/windows/) · [Télécharger Ollama](https://ollama.com/download/windows)
3. Exécuter `Installer.cmd` depuis le dossier du projet pour préparer les dépendances Python.
4. Dans un terminal Windows, télécharger le modèle une fois avec `ollama pull qwen3:8b`.
5. Exécuter `Lancer.cmd`. L’interface s’ouvre sur [127.0.0.1:8765](http://127.0.0.1:8765).

L’installation initiale et le téléchargement du modèle nécessitent Internet. L’application et le modèle local peuvent ensuite fonctionner hors connexion. L’import et les statistiques sont disponibles même sans Ollama. Une variante d’installation utilisant l’archive portable officielle d’Ollama est décrite dans le guide. [Guide d’utilisation et dépannage](docs/GUIDE.md) · [Documentation Windows d’Ollama](https://docs.ollama.com/windows)

## Essai pour le jury

1. Dans **Analyse**, cliquer sur **Charger la simulation**. Pour tester le parcours d’import, utiliser **Ajouter des données**, puis **Analyser le CSV** avec [le fichier de démonstration fourni](data/demo.csv). L’application reconnaît le fichier de démonstration d’origine et l’identifie comme simulation dans les deux parcours.
2. Examiner les taux par niveau, les effectifs et l’évolution lorsque les sessions sont datées. Le fichier fourni représente 150 sessions et 458 observations sur cinq niveaux. Le tableau relève 30,84 % de réussite au Périgée, sur 107 observations, contre 91,45 % dans les autres niveaux regroupés.
3. Dans **Agent local**, choisir le modèle téléchargé puis cliquer sur **Lancer l’agent**. Ouvrir **Consulter les appels d’outils** pour lire la trace. La simulation fournit les données. Les calculs et les appels à Ollama s’exécutent réellement.
4. Dans **Recommandations**, changer le **Statut de la recommandation** et cliquer sur **Enregistrer la décision**. Dans **Historique**, récupérer le rapport HTML puis vérifier la décision dans l’export JSON ou CSV.

Le [dossier de présentation ASUS](docs/ASUS.md) contient les critères du concours, la contribution de Codex et une trame de démonstration de deux minutes.

## Architecture

| Partie | Responsabilité |
| --- | --- |
| Streamlit et Plotly | Navigation, graphiques, import, revue et téléchargements |
| Pandas et NumPy | Validation du CSV et calcul déterministe des indicateurs |
| Qwen3 via Ollama | Sélection d’outils locaux, d’actions du catalogue et de références aux mesures |
| SQLite | Historique, rapports d’analyse et décisions |

Le flux part d’un CSV où chaque ligne décrit le résultat d’une session sur un niveau. L’analyse produit des agrégats et des références pour les outils. L’agent demande des calculs à l’application, qui valide les appels et renvoie leurs résultats. Il sélectionne ensuite des actions et des références aux mesures. L’application valide ces choix et affiche les hypothèses, les justifications et le texte français des propositions définis dans le catalogue. Les chiffres affichés proviennent des outils ou correspondent au réglage d’un essai décrit dans le catalogue. Le client Ollama utilise une adresse de boucle locale et reçoit des agrégats avec des identifiants internes de niveau.

Une alerte descriptive compare un niveau aux autres niveaux regroupés. Elle demande au moins 20 observations de chaque côté et un écart d’au moins 15 points de pourcentage. L’intervalle de Wilson à 95 % aide à lire l’incertitude liée à l’effectif par niveau. La documentation précise comment interpréter ces indicateurs quand des sessions ou des populations se recoupent. [Méthode et schéma CSV](docs/GUIDE.md)

## Matériel et limites

- `qwen3:8b` est le choix de référence. Ses poids quantifiés occupent environ 5,2 Go sur disque. La mémoire utilisée pendant l’exécution dépend aussi du contexte et de la mémoire libre. [Fiche du modèle 8B](https://ollama.com/library/qwen3:8b)
- Pour une machine plus contrainte, essayer `qwen3:4b` puis `qwen3:1.7b`, à télécharger séparément. Les modèles plus petits peuvent proposer une analyse moins précise ou nécessiter une nouvelle exécution. [Fiche 4B](https://ollama.com/library/qwen3:4b) · [Fiche 1.7B](https://ollama.com/library/qwen3:1.7b)
- Ollama choisit l’exécution GPU, CPU ou mixte selon le matériel. `ollama ps` permet de vérifier le placement du modèle pendant son chargement. [GPU pris en charge](https://docs.ollama.com/gpu) · [Vérifier le placement du modèle](https://docs.ollama.com/faq#how-can-i-tell-if-my-model-was-loaded-onto-the-gpu)
- Les propositions restent des hypothèses à tester. Les données observées peuvent refléter des différences de joueurs, de builds ou de composition des niveaux. Un écart de timing ne suffit pas pour identifier sa cause.

## Tests et feuille de route

Depuis la racine, après installation des dépendances, exécuter les tests Python locaux.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Les prochaines étapes envisagées sont le raccordement à un export de télémétrie de Gravity Chain, l’ajout de paramètres de niveau dans les rapports et le suivi d’essais comparables avant et après un changement d’équilibrage.

[Notice de licences et de contributions](docs/LICENCES.md)
