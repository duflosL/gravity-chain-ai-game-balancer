# Validation locale

Machine de référence vérifiée le 14 novembre 2026. Windows 11, Core i5-14600K, RTX 5080 16 Go, pilote NVIDIA 621.14, Python 3.12.3.

## Tests exécutés

| Vérification | Résultat |
| --- | --- |
| Installation Windows | `Installer.cmd` a terminé et `pip check` a confirmé la cohérence des dépendances. |
| Démarrage Windows | `Lancer.cmd` a servi l’application sur la boucle locale. La page de vérification a répondu `ok`. |
| Suite Python | 21 tests réussis sur 21. Elle couvre les règles d’import, les agrégats, les seuils, SQLite, les décisions concurrentes, les exports et le protocole de l’agent avec réponses simulées. |
| Parcours dans Chrome | Huit groupes de vérifications réussis. Navigation, historique vide, Ollama indisponible, fichier manquant, CSV invalide, import valide avec évolution datée, simulations détectées par les deux parcours, persistance, comparaison et téléchargement du rapport HTML. |
| Simulation | 150 sessions, 458 observations, cinq étapes. À Périgée, 33 réussites sur 107, soit 30,84 %, contre 321 sur 351, soit 91,45 %, pour le reste. |
| Inférence réelle, modèle chaud | Qwen3 8B Q4_K_M, Ollama 0.40.16, contexte de 8 192 jetons. Durée observée de 3,44 s. Cinq échanges avec le modèle et trois outils natifs sur Périgée. |
| Placement GPU | Les journaux CUDA indiquent 37 couches sur 37. Ollama a rapporté 6 312 228 290 octets en VRAM pendant l’analyse, soit 5,88 Gio. |
| Parcours avec le modèle dans Chrome | Nouvelle inférence réelle en 11,61 s, trace affichée, statut accepté puis rejeté, confirmé dans les deux exports JSON. Téléchargements HTML et CSV confirmés. Aucune requête externe observée dans la page pendant cet essai. |
| Rapport IA | Le modèle a retenu un repère visuel, une collecte des motifs d’échec et un essai A/B élargissant la fenêtre de timing de 10 %. La différence de précision de timing de 11,92 points est calculée sur 32 réussites et 70 échecs mesurés. |
| Démonstration vidéo | Capture réelle du parcours dans Chrome avec une nouvelle inférence Qwen3, la validation humaine et la vue des exports. Vidéo H.264 de 37,20 s, sous-titres français et décodage complet vérifié. |

L’essai initial avec le vrai modèle a révélé qu’une combinaison niveau-action pouvait franchir la grammaire de sortie et être rejetée par l’application. La grammaire contient désormais les paires autorisées et l’application vérifie également les références aux mesures. La revue a ensuite produit un rapport valide sur le même CSV. Le premier chargement du modèle a pris environ une minute dans les conditions de cette machine et la durée de 3,44 s a été relevée une fois le modèle en mémoire.

## Limites de la validation

L’essai a utilisé les données synthétiques fournies. L’intégration à un export du jeu et les essais auprès de joueurs restent à réaliser. Windows 11 et la configuration matérielle ci-dessus constituent le périmètre testé. La distribution Windows fournit les sources et le lanceur, avec Python, Ollama et les poids installés séparément.
