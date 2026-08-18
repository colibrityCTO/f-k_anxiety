---
id: capteurs-et-panique
title: "Bracelets et détection de panique : ce qui est possible aujourd'hui"
category: mesure
evidence_level: B
targets: [panique, somatique]
up_module: 1
duration_min: 3
sources:
  - label: "Meuret et al., Biological Psychiatry 2011 — enregistrement ambulatoire 24 h : instabilité autonome et respiratoire détectable jusqu'à 47 minutes avant des attaques dites imprévisibles"
    url: "https://www.ncbi.nlm.nih.gov/pubmed/21783179"
  - label: "JMIR 2025 — prédiction d'attaques de panique par apprentissage automatique sur ECG (500 Hz), sans validation externe"
    url: "https://pmc.ncbi.nlm.nih.gov/articles/PMC12526660/"
  - label: "Revue de portée 2025 — utilité des objets connectés pour prédire les attaques de panique"
    url: "https://doi.org/10.1177/20552076251390475"
updated: 2026-08-18
---

## L'argument physiologique est solide

Dans une étude d'enregistrement ambulatoire sur 24 heures portant sur 43 patients et
13 attaques naturelles, une instabilité autonome et respiratoire significative est
détectable **jusqu'à 47 minutes avant** le début — y compris pour des attaques que les
patients décrivaient comme soudaines et imprévisibles. Les dernières minutes sont
dominées par une baisse du volume courant suivie d'une hausse brusque de la PCO₂.

Autrement dit : il se passe quelque chose de mesurable avant. La question n'est pas là.

## Ce qui bloque, concrètement

Les travaux qui atteignent de bonnes performances utilisent de l'**ECG à 500 Hz** ou
des capteurs de recherche (conductance cutanée, température, fréquence cardiaque
continue). Ils souffrent de deux limites que les revues récentes soulignent : absence
de validation externe, et fort déséquilibre de classes — les crises sont rares, donc
les fausses alertes sont nombreuses.

Et surtout, du côté de l'objet grand public : **l'API de Whoop n'expose aucune série
temporelle de fréquence cardiaque.** Uniquement des agrégats — variabilité et fréquence
de repos par nuit, fréquence moyenne et maximale par cycle ou par séance, temps par
zone. Repérer un pic autonome de dix à vingt minutes demande la fréquence à la minute.

## Ce que l'application fait donc

Ce qui est calculable l'est : croiser une séance à fréquence maximale élevée avec une
crise du lendemain, et utiliser une variabilité nocturne dégradée par rapport à la base
personnelle comme signal de risque **journalier**, disponible avant que la journée
commence.

Ce qui ne l'est pas n'est pas simulé. Et même si ça le devenait : une fausse alerte de
panique est un déclencheur de panique. Une détection automatique devrait être formulée
comme une observation — « ton corps est plus activé que d'habitude » — et jamais comme
une prédiction d'attaque.

## À la place

Une question. Le lendemain d'une séance intense : « ton cœur est monté à 172 hier,
comment ça a été aujourd'hui ? ». Une question ne peut rien annoncer, donc elle ne peut
pas se retourner contre la personne.
