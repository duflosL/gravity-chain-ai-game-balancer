# Validation locale

Machine de référence vérifiée le 14 novembre 2026. Windows 11, Core i5-14600K, RTX 5080 16 Go, pilote NVIDIA 621.14, Python 3.12.3.

## Tests exécutés

| Vérification | Résultat |
| --- | --- |
| Installation Windows | `Installer.cmd` a terminé et `pip check` a confirmé la cohérence des dépendances. |
| Démarrage Windows | `Lancer.cmd` a servi l’application sur la boucle locale. La page de vérification a répondu `ok`. |
| Suite Python | 20 tests réussis sur 20. Elle couvre les règles d’import, les agrégats, les seuils, SQLite, les décisions concurrentes, les exports et le protocole de l’agent avec réponses simulées. |
| Parcours dans Chrome | Huit groupes de vérifications réussis. Navigation, historique vide, Ollama indisponible, fichier manquant, CSV invalide, import valide avec évolution datée, simulations détectées par les deux parcours, persistance, comparaison et téléchargement du rapport HTML. |
| Simulation | 150 sessions, 458 observations, cinq étapes. À Périgée, 33 réussites sur 107, soit 30,84 %, contre 321 sur 351, soit 91,45 %, pour le reste. |

## Limites de la validation

L’essai a utilisé les données synthétiques fournies. L’intégration à un export du jeu et les essais auprès de joueurs restent à réaliser. Windows 11 et la configuration matérielle ci-dessus constituent le périmètre testé. La distribution Windows fournit les sources et le lanceur, avec Python, Ollama et les poids installés séparément.
