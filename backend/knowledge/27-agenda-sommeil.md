---
id: agenda-sommeil
title: "Noter son sommeil : pourquoi au réveil et pas le soir"
category: hygiene
evidence_level: B
targets: [sommeil, auto-monitoring]
up_module: 1
duration_min: 1
sources:
  - label: "Comment les patients insomniaques interprètent et remplissent le Consensus Sleep Diary — étude par entretiens cognitifs : difficultés de rappel quand l'agenda n'est pas rempli directement au réveil"
    url: "https://pmc.ncbi.nlm.nih.gov/articles/PMC10879077/"
  - label: "Scientific Reports 2024 — biais non constant entre deux méthodes d'auto-déclaration de la durée habituelle de sommeil"
    url: "https://www.nature.com/articles/s41598-024-53174-1"
updated: 2026-08-18
---

## Le problème

Un chiffre de sommeil demandé le soir n'est pas le même chiffre que demandé au réveil.
Les travaux sur le Consensus Sleep Diary — l'instrument de référence — sont nets : les
patients ont des difficultés de rappel dès que l'agenda n'est pas rempli
**immédiatement au réveil**, et c'est le défaut connu de l'outil.

Pire, le biais n'est pas constant. Les estimations rétrospectives surestiment les
petites valeurs et sous-estiment les grandes : une nuit courte est déclarée plus longue
qu'elle ne l'a été, une nuit longue plus courte. Un biais constant se corrigerait ; un
biais qui dépend de la valeur déforme la relation elle-même.

## La conséquence pour ce suivi

La corrélation sommeil → anxiété du lendemain est l'une des plus utiles à connaître,
parce que le sommeil est le levier le plus concret à modifier. Elle est aussi celle qui
souffre le plus d'un chiffre approximatif : si les nuits courtes sont déclarées trop
longues, l'association s'aplatit et disparaît.

D'où le découpage du check-in : **le sommeil se note le matin**, la journée se raconte
le soir.

## Déclaré ou mesuré

Quand un bracelet fournit la durée, elle est affichée en lecture seule et corrigeable —
un capteur se trompe aussi (sieste comptée comme nuit, bracelet retiré), et une donnée
de santé fausse est pire qu'une donnée absente.

Les deux valeurs coexistent dans deux tables distinctes, et la provenance est
enregistrée (`declare`, `capteur`, `corrige`). Sans cette trace, une corrélation
mélangerait deux instruments de mesure et son coefficient ne voudrait rien dire.
