---
id: prediction-limites
title: "Prévoir son anxiété : ce qui est possible, et le plafond"
category: mesure
evidence_level: B
targets: [auto-monitoring]
up_module: 1
duration_min: 3
sources:
  - label: "Digital Biomarkers of Anxiety Disorder Symptom Changes — modèles personnalisés sur capteurs et évaluations répétées : R² robuste ≈ 0,75 au niveau du groupe, ≈ 0,39 au niveau individuel"
    url: "https://pmc.ncbi.nlm.nih.gov/articles/PMC8858490/"
updated: 2026-08-18
---

## Ce qui est mesuré

À partir de mesures répétées et de capteurs, les modèles au niveau du **groupe**
expliquent une grande part de la variance de l'anxiété — R² robuste d'environ 0,75 dans
l'étude de référence. Les modèles **individuels**, eux, tombent à environ 0,39 en
moyenne, avec une prédiction non nulle chez 97 % des participants.

## La conséquence qui structure toute la fonction

L'essentiel de cette variance vient de l'**autocorrélation** : demain ressemble à
aujourd'hui. Un modèle qui prédit « demain = aujourd'hui » explique déjà beaucoup, sans
rien apprendre de personne.

La référence à battre n'est donc **pas le hasard, c'est la persistance**. Un modèle qui
n'améliore pas la persistance n'apporte rien, et l'afficher serait une mise en scène.
L'application le vérifie en validation par avance glissante : à chaque jour testé, le
modèle n'est ajusté que sur les jours antérieurs. S'il ne gagne pas, la persistance est
utilisée, et c'est dit.

Cas particulier, nommé pour ne pas s'attribuer un mérite qu'il n'a pas : un modèle peut
battre la persistance simplement en tirant la valeur du jour vers la moyenne. C'est un
résultat réel — il signifie que les écarts d'un jour sur l'autre sont surtout du bruit
autour d'un niveau — mais ce n'est pas un modèle personnalisé, et il est étiqueté
« retour à la moyenne ».

## Une fourchette, jamais un point

« Entre 4 et 7 » est une prévision. « 5,4 » est une promesse, et une promesse ratée
coûte la confiance dans tout le reste. L'intervalle est calibré sur les variations
quotidiennes de la personne, pas sur un écart-type théorique : une personne stable
reçoit une fourchette étroite, une personne instable une fourchette large — ce qui est
l'information utile.

## Ce qui n'est jamais prédit

Aucune attaque de panique. La fiabilité serait très faible, et surtout : une prédiction
anxiogène est auto-réalisatrice. « Journée à surveiller » avec la raison, jamais « tu
vas faire une crise ».
