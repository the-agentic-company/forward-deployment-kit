---
description: Lance Phase 2 du pipeline HeyBap (route un bug ou une feature via le gate de classification) via le wrapper script blinde
---

Adapter Claude pour le skill canonique `phase-2`. Lance Phase 2 du pipeline HeyBap forward-deployment : route un bug ou une feature observe sur HeyBap a travers le gate de classification. Le gate peut d'abord retourner `needs-clarification` quand une petite ambiguite localisee peut etre resolue par une question operateur, puis dispatche vers SIMPLE / COMPLEX-SCOPED / COMPLEX-FUZZY quand la finding est assez claire. Dans Claude / Claude Code, l'adapter officiel est le wrapper FDK ci-dessous ; dans Codex, le skill `phase-2` execute le meme contrat directement avec le runtime Codex.

Args (a parser depuis $ARGUMENTS) :
- 1er : `bug` ou `feature`
- 2e : description en une ligne (probleme observe)

Marche a suivre Claude :

1. cd dans /Users/lubin.danilo/bap/forward-deployment-kit
2. Lance le wrapper qui pre-approuve les tools et force le passage par le gate :

```bash
./scripts/submit-finding.sh "$KIND" "$DESCRIPTION"
```

3. Le wrapper invoque `claude -p` qui execute : dedup Linear (60 jours, plusieurs tokens distinctifs), 5 minutes d'investigation dans un clone de `the-agentic-company/bap` pour localiser la surface, clarification gate pour les petites ambiguites d'intention operateur, classification sur la grille a 12 criteres (SIMPLE vs COMPLEX, puis SCOPED vs FUZZY si COMPLEX), dispatch vers `bap-bug-report` (SIMPLE), `bap-feature-brainstorm` (COMPLEX-SCOPED) ou `bap-direction-shaping` (COMPLEX-FUZZY).

4. Au retour : affiche le verdict (`dispatched | needs-clarification | already-reported | low-confidence | config-missing`), la question exacte si `needs-clarification`, l'URL du ticket Linear cree (BAP-<n>) si un ticket a ete cree, et l'URL de la PR si SIMPLE.

5. Si le verdict est `needs-clarification`, relaie la question telle quelle a Lubin et arrete-toi. Ne cree pas de ticket local, ne lance pas `bap-feature-brainstorm`, et ne contourne pas le wrapper.

**Ne jamais court-circuiter le wrapper depuis Claude.** Appeler `bap-bug-report` ou `bap-feature-brainstorm` en direct saute le dedup (doublons de tickets), la clarification gate et la classification (mauvais routing). Le wrapper est la facon de garantir A a Z dans le runtime Claude ; les autres runtimes doivent suivre le skill canonique `phase-2`.

Rappel : Lubin n'a plus les droits merge sur `the-agentic-company/bap`. Quel que soit le verdict, le contrat s'arrete a "PR ouverte + CI verte + ping Baptiste". Pas de `gh pr merge`.

Args recus : $ARGUMENTS
