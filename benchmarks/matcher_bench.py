from time import perf_counter
from pmw import Entity, Event, Relation, WorldState, parse_law
from pmw.matching import MatchStats, match_law

def run(label, size, law, world):
    stats=MatchStats(); start=perf_counter(); matches=match_law(law,world,Event("go","go"),stats=stats)
    print(f"{label} N={size} matches={len(matches)} time={perf_counter()-start:.6f} rows={stats.candidate_rows_examined} partial={stats.partial_bindings_created} complete={stats.complete_bindings} early_eval={stats.early_predicate_evaluations} early_prune={stats.early_predicate_prunes} exact_lookups={stats.exact_constraint_lookups} pushdowns={stats.constraint_pushdowns} exact_prunes={stats.exact_constraint_prunes} index_builds={stats.index_builds}")

def main():
    for n in (100,1000):
        entities={f"e{i}":Entity(f"e{i}",components={"rare":{}} if i<10 else {}) for i in range(n)}; relations={f"r{i}":Relation(f"r{i}","link",f"e{i}",f"e{(i+1)%n}",components={"rare":{}} if i<10 else {}) for i in range(n)}; world=WorldState(entities=entities,relations=relations)
        edge=parse_law({"id":"edge","bindings":{"a":{"kind":"entity"},"b":{"kind":"entity"},"r":{"kind":"relation","type":"link","source":"$a","target":"$b"}},"effects":[]})
        chain=parse_law({"id":"chain","bindings":{"a":{"kind":"entity"},"b":{"kind":"entity"},"c":{"kind":"entity"},"r1":{"kind":"relation","source":"$a","target":"$b"},"r2":{"kind":"relation","source":"$b","target":"$c"}},"effects":[]})
        run("EDGE",n,edge,world); run("CHAIN",n,chain,world); run("STAR",n,edge,world); run("SELECTIVE_COMPONENT",n,parse_law({"id":"se","bindings":{"x":{"kind":"entity","requires":["rare"]}},"effects":[]}),world); run("SELECTIVE_RELATION_COMPONENT",n,parse_law({"id":"sr","bindings":{"r":{"kind":"relation","requires":["rare"]}},"effects":[]}),world); run("SELECTIVE_CONDITION",n,parse_law({"id":"sc","bindings":{"a":{"kind":"entity"},"b":{"kind":"entity"}},"when":{"all":[{"has_component":["$a","rare"]}]},"effects":[]}),world); run("IRRELEVANT_EVENT",n,parse_law({"id":"ie","bindings":{"x":{"kind":"entity"}},"when":{"all":[{"event.type":{"eq":"nope"}}]},"effects":[]}),world)
    for n in (1000, 10000, 50000, 100000):
        world=WorldState(entities={f"e{i}":Entity(f"e{i}") for i in range(n)})
        exact=parse_law({"id":"exact-id","bindings":{"x":{"kind":"entity"}},"when":{"all":[{"ref":"$x.id","eq":"e0"}]},"effects":[]})
        run("EXACT_ID",n,exact,world)
if __name__ == "__main__": main()
