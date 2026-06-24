---
description: Lance Phase 1 du pipeline HeyBap (build coworker from transcript or brief) via le wrapper script blinde
---

Adapter Claude pour le skill canonique `phase-1`. Lance Phase 1 du pipeline HeyBap forward-deployment : construit un ou plusieurs coworkers Bap depuis un transcript de call ou un brief operateur, de bout en bout. Dans Claude / Claude Code, l'adapter officiel est le wrapper FDK ci-dessous ; dans Codex, le skill `phase-1` execute le meme contrat directement avec le runtime Codex.

Args (forme libre, a parser depuis $ARGUMENTS) :
- 1er : chemin vers fichier transcript, URL Grain, ou "-" pour stdin
- 2e (optionnel) : nom du prospect / client (ameliore la spec et resout le canal Slack client)
- 3e (optionnel) : callType (`discovery` / `kickoff` / `follow-up` / `technical` / `demo` / `brief`)
- 4e (optionnel) : maxAgents (cap nombre de coworkers built, defaut 3)

Marche a suivre Claude :

1. cd dans /Users/lubin.danilo/bap/forward-deployment-kit
2. Lance le wrapper qui pre-approuve les tools et force le chainage complet :

```bash
./scripts/build-from-transcript.sh "$INPUT" "$PROSPECT" "$CALL_TYPE" "$MAX_AGENTS"
```

3. Le wrapper invoque `claude -p` qui enchaine : parse -> prior-art-scout -> platform-feasibility-check -> orchestrator (resolve tools -> scaffold skill folders -> skill_add -> coworker_create/update) -> bap-client-notify (planned) -> bap-coworker-test-loop -> bap-client-notify (validated) -> consolidated report.

4. Au retour : affiche le chemin du report final, la liste des @coworkers live, les tickets Linear ouverts (si findings HeyBap ont ete observes), et les permalinks des 2 posts Slack client.

**Ne jamais court-circuiter le wrapper depuis Claude.** Lancer `parse-transcript-to-agent-spec` ou un autre sous-skill en direct saute prior-art / feasibility / test loop / client-notify. Le wrapper est la facon de garantir A a Z dans le runtime Claude ; les autres runtimes doivent suivre le skill canonique `phase-1`.

Si Lubin n'a fourni qu'un seul argument et qu'il ressemble a du texte inline (pas un chemin ni une URL), passe-le via stdin en utilisant `-` comme premier argument :
```bash
echo "$INPUT" | ./scripts/build-from-transcript.sh - "$PROSPECT" brief
```

Args recus : $ARGUMENTS
