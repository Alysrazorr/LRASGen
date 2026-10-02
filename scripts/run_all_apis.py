
import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN = os.path.join(REPO, "src", "main.py")
DEFAULT_DATASETS = os.path.join(REPO, "api-sources")

BITWARDEN = "Bitwarden"

APIS = [
    ("Actuator", "Actuator/spring-actuator-demo", "spring-boot", []),
    ("Batch", "Batch/spring-batch-rest", "spring-boot", []),
    ("Bibliothek", "Bibliothek/bibliothek", "spring-boot", []),
    ("Blog", "Blog/blogapi", "spring-boot", []),
    ("CatWatch", "CatWatch/catwatch", "spring-boot", []),
    ("CWA", "CWA/cwa-verification-server", "spring-boot",
     ["--exclude-dirs", "src/main/java/app/coronawarn/verification/client"]),
    ("ECommerce", "ECommerce/spring-ecommerce", "spring-boot", []),
    ("ERC20", "ERC20/erc20-rest-service", "spring-boot", []),
    ("Faults", "Faults/rest-faults-master", "spring-boot", []),
    ("Genome", "Genome/genome-nexus", "spring-boot", []),
    ("Gestao", "Gestao/gestaohospital", "spring-boot", []),
    ("HTTPPatch", "HTTPPatch/http-patch-spring", "spring-boot", []),
    ("Market", "Market/market", "spring-boot", []),
    ("Microcks", "Microcks/microcks", "spring-boot", []),
    ("NCS", "NCS/ncs", "spring-boot", []),
    ("OCVN", "OCVN/ocvn", "spring-boot", []),
    ("Ohsome", "Ohsome/ohsome-api", "spring-boot", []),
    ("Person", "Person/person-controller", "spring-boot", []),
    ("PetClinic", "PetClinic/spring-petclinic-rest-master", "spring-boot", []),
    ("Piggy", "Piggy/piggymetrics-master", "spring-boot", []),
    ("ProxyPrint", "ProxyPrint/proxyprint-kitchen", "spring-boot", []),
    ("PTS", "PTS/tracking-system", "spring-boot", []),
    ("Quartz", "Quartz/quartz-manager", "spring-boot", []),
    ("Reservations", "Reservations/reservations-api", "spring-boot", []),
    ("SBRAE", "SBRAE/spring-rest-example", "spring-boot", []),
    ("SCS", "SCS/scs", "spring-boot", []),
    ("Session", "Session/session-service", "spring-boot", []),
    ("Tiltak", "Tiltak/tiltaksgjennomforing", "spring-boot", []),
    ("UM", "UM/user-management", "spring-boot", []),
    ("Ur-Codebin", "Ur-Codebin/Ur-Codebin-API", "spring-boot", []),
    ("WebGoat", "WebGoat/webgoat", "spring-boot", []),
    ("YTM", "YTM/youtube-mock", "spring-boot", []),

    ("Digdag", "Digdag/digdag/digdag-server", "jersey", []),
    ("Cassandra", "Cassandra/management-api-for-apache-cassandra", "jersey", []),
    ("Features-Service", "Features-Service/features-service", "jersey", []),
    ("Gravitee", "Gravitee/gravitee-api-management", "jersey", []),
    ("Kafka", "Kafka/kafka-rest", "jersey", []),
    ("Payments", "Payments/pay-publicapi", "jersey", []),
    ("Petstore", "Petstore/swagger-petstore", "jersey", []),
    ("RESTcountries", "RESTcountries/restcountries", "jersey", []),
    ("Scout", "Scout/scout-api", "jersey", []),
    ("Senzing", "Senzing/senzing-api-server", "jersey", []),
    ("enviroCar", "enviroCar/enviroCar-server", "jersey", []),

    ("Languagetool", "Languagetool/languagetool", "jdk", []),

    ("Familie", "Familie/familie-ba-sak", "spring-boot-kotlin", []),
    ("News", "News/news", "spring-boot-kotlin", []),

    # Bitwarden is documented as one API but its code is split four ways. The
    # public API has six controllers, and only the collections one sits in the
    # tree named "Public"; the other five are under AdminConsole. The CLI that
    # serves the vault routes and the CLI that serves device approval are
    # likewise separate apps. Each is a run of its own, merged afterwards.
    ("Bitwarden", "Bitwarden/bitwarden-server-main/src/Api/Public", "aspnetcore", []),
    ("Bitwarden", "Bitwarden/bitwarden-server-main/src/Api/AdminConsole/Public", "aspnetcore", []),
    ("Bitwarden", "Bitwarden/bitwarden_clients-main/apps/cli/src", "koa", []),
    ("Bitwarden", "Bitwarden/bitwarden_clients-main/bitwarden_license/bit-cli/src", "koa", []),

    ("Cyclotron", "Cyclotron/cyclotron-master", "express", []),
    ("Realworld", "Realworld/nestjs-realworld-example-app-master", "nestjs", []),

    ("Gramps", "Gramps/gramps-web-api-master", "flask",
     ["--config-file", "{root}/Gramps/gramps-web-api-master/gramps_webapi/api/__init__.py"]),
    ("Jupyter", "Jupyter/jupyter_server-main", "tornado",
     ["--keyword", "default_handlers = ["]),
    ("Mlmmj", "Mlmmj/mlmmjadmin-master", "webpy",
     ["--config-file", "{root}/Mlmmj/mlmmjadmin-master/controllers/urls.py",
      "--urls", "/api/(%s)$,controllers.profile.Profile,"
                "/api/(%s)/owners,controllers.profile.Owners,"
                "/api/(%s)/moderators,controllers.profile.Moderators,"
                "/api/(%s)/subscribers,controllers.subscriber.Subscribers,"
                "/api/(%s)/has_subscriber/(%s),controllers.subscriber.HasSubscriber,"
                "/subscriber/(%s)/subscribed,controllers.subscriber.SubscribedLists,"
                "/subscriber/(%s)/subscribe,controllers.subscriber.Subscribe",
      # Web.py declares routes in a standalone list, so the handler source alone
      # carries no URL. The mapping is handed over ready to inject: --urls gives
      # step 1 the controller names it needs, this gives step 3 the paths.
      "--url-context", "# Web.py URL mapping (pattern -> handler class): "
                       "/api/{} -> controllers.profile.Profile; "
                       "/api/{}/owners -> controllers.profile.Owners; "
                       "/api/{}/moderators -> controllers.profile.Moderators; "
                       "/api/{}/subscribers -> controllers.subscriber.Subscribers; "
                       "/api/{}/has_subscriber/{} -> controllers.subscriber.HasSubscriber; "
                       "/api/subscriber/{}/subscribed -> controllers.subscriber.SubscribedLists; "
                       "/api/subscriber/{}/subscribe -> controllers.subscriber.Subscribe",
      # A vendored copy of web.py. Following it as a local package buries the
      # project's own code: it is 220 KB of the 234 KB that would reach the prompt.
      "--exclude-deps", "web"]),
    ("Poke", "Poke/pokeapi-master", "django",
     ["--config-file", "{root}/Poke/pokeapi-master/pokemon_v2/urls.py"]),
]


ORDER_FILE = os.path.join(REPO, "scripts", "api_order.txt")

# The order runs are dispatched in. The list is ascending by the size hint the
# subject APIs were supplied with, so a defect surfaces on the cheap APIs first.
GROUP_SIZE = 7


def load_order(path=ORDER_FILE):
    names = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.split("#", 1)[0].strip()
            if line:
                names.append(line)
    return names


def group_names(group, size=GROUP_SIZE, path=ORDER_FILE):
    names = load_order(path)
    start = (group - 1) * size
    return names[start:start + size]


# One output subdirectory per Bitwarden source, kept in step with subdir_for.
# Each source needs its own: two runs sharing a directory would overwrite each
# other's step files, and whatever survived would be merged as if it were whole.
BITWARDEN_PARTS = ("api-public", "api-adminconsole-public", "cli-oss", "cli-licensed")

# Token and cost counters, which add up when two runs are merged into one.
_SUM_FIELDS = ("prompt_tokens", "completion_tokens", "total_tokens", "calls",
               "elapsed_s", "prompt_cost_usd", "completion_cost_usd", "total_cost_usd")


def subdir_for(name, source):
    if name != BITWARDEN:
        return None
    if "bitwarden-server" in source:
        return "api-adminconsole-public" if "AdminConsole" in source else "api-public"
    return "cli-licensed" if "bitwarden_license" in source else "cli-oss"


def _merge_by_model(first, second):
    """Add two runs' per-model records, keeping the order of the first run."""
    out, at = [], {}
    for entry in list(first or []) + list(second or []):
        name = entry.get("name")
        if name not in at:
            at[name] = len(out)
            out.append(dict(entry))
            continue
        acc = out[at[name]]
        for f in _SUM_FIELDS:
            acc[f] = acc.get(f, 0) + entry.get(f, 0)
    return out


def _sum_tokens(a, b):
    out = {f: a.get(f, 0) + b.get(f, 0) for f in _SUM_FIELDS}
    out["by_model"] = _merge_by_model(a.get("by_model"), b.get("by_model"))
    return out


def build_command(short_name, source, framework, extra, datasets, out_root, sub=None):
    out_dir = os.path.join(out_root, short_name)
    if sub:
        out_dir = os.path.join(out_dir, sub)
    cmd = [sys.executable, MAIN,
           "--api-path", os.path.join(datasets, source.replace("/", os.sep)),
           "--framework", framework,
           "--output-dir", out_dir]
    for i, arg in enumerate(extra):
        if i % 2 == 0 and arg.startswith("--"):
            cmd.append(arg)
        else:
            cmd.append(arg.replace("{root}", datasets))
    return cmd, out_dir


def merge_bitwarden(out_root):
    base = os.path.join(out_root, BITWARDEN)
    parts = [os.path.join(base, p) for p in BITWARDEN_PARTS]
    missing = [p for p in BITWARDEN_PARTS if not os.path.isdir(os.path.join(base, p))]
    if missing:
        return f"Bitwarden: source run(s) missing, not merged: {', '.join(missing)}"

    for step in ("step3_endpoints.json", "step4_details.json", "step5_constraints.json"):
        merged, frameworks = None, []
        for p in parts:
            path = os.path.join(p, step)
            if not os.path.isfile(path):
                continue
            with open(path, encoding="utf-8") as fh:
                d = json.load(fh)
            frameworks.append(d.get("framework"))
            if merged is None:
                merged = d
                continue
            merged["endpoints"] = merged.get("endpoints", []) + d.get("endpoints", [])
            merged["errors"] = merged.get("errors", []) + d.get("errors", [])
            merged["duration_ms"] = merged.get("duration_ms", 0) + d.get("duration_ms", 0)
            # The merged file is the run's only record of what it cost, so the
            # counters have to cover every source, not just the first one.
            merged["tokens"] = _sum_tokens(merged.get("tokens") or {}, d.get("tokens") or {})
        if merged is not None:
            merged["api_name"] = BITWARDEN
            merged["framework"] = "+".join(sorted({f for f in frameworks if f}))
            with open(os.path.join(base, step), "w", encoding="utf-8") as fh:
                json.dump(merged, fh, ensure_ascii=False, indent=2)

    for step, key in (("step1_entry_files.json", "files"),
                      ("step2_code_files.json", "entry_to_deps")):
        merged = None
        for p in parts:
            path = os.path.join(p, step)
            if not os.path.isfile(path):
                continue
            with open(path, encoding="utf-8") as fh:
                d = json.load(fh)
            if merged is None:
                merged = d
            elif isinstance(d.get(key), list):
                merged[key] = merged.get(key, []) + d.get(key, [])
            elif isinstance(d.get(key), dict):
                merged.setdefault(key, {}).update(d.get(key, {}))
        if merged is not None:
            with open(os.path.join(base, step), "w", encoding="utf-8") as fh:
                json.dump(merged, fh, ensure_ascii=False, indent=2)

    return f"Bitwarden: merged {len(parts)} sources"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Run the pipeline over the 53 subject APIs")
    ap.add_argument("--datasets", default=DEFAULT_DATASETS,
                    help="dataset root holding one folder per API (default: %(default)s)")
    ap.add_argument("--out-root", default=os.path.join(REPO, "output", "lrasgen_generated"),
                    help="where each API's output directory is written (default: %(default)s)")
    ap.add_argument("--only", default=None,
                    help="comma-separated short names to run, e.g. CatWatch,Faults")
    ap.add_argument("--group", type=int, default=None,
                    help=f"run one {GROUP_SIZE}-API batch of the order in "
                         f"{os.path.relpath(ORDER_FILE, REPO)}, 1-based")
    ap.add_argument("--parallel", type=int, default=0,
                    help="how many APIs to run at once (default: the whole batch, "
                         "so a group of 7 runs 7 at a time)")
    ap.add_argument("--log-dir", default=os.path.join(REPO, "output", "logs"),
                    help="where each API's run log is written (default: %(default)s)")
    ap.add_argument("--list", action="store_true", help="list the APIs and exit")
    ap.add_argument("--list-order", action="store_true",
                    help="print the run order in batches and exit")
    args = ap.parse_args(argv)

    if args.list:
        for name, src, fw, _ in APIS:
            print(f"{name:<18} {fw:<20} {src}")
        return 0

    if args.list_order:
        order = load_order()
        known = {n for n, _, _, _ in APIS}
        unknown = [n for n in order if n not in known]
        for i in range(0, len(order), GROUP_SIZE):
            batch = order[i:i + GROUP_SIZE]
            print(f"group {i // GROUP_SIZE + 1:>2}  " + ", ".join(batch))
        print(f"\n{len(order)} entries, {len(set(order))} distinct")
        if unknown:
            print(f"error: not in APIS: {unknown}")
            return 1
        return 0

    if args.only and args.group:
        print("error: --only and --group are mutually exclusive")
        return 1

    if not os.path.isdir(args.datasets):
        print(f"error: dataset root not found: {args.datasets}")
        return 1

    wanted = None
    if args.only:
        wanted = {n.strip().lower() for n in args.only.split(",") if n.strip()}
    elif args.group:
        batch = group_names(args.group)
        if not batch:
            total = (len(load_order()) + GROUP_SIZE - 1) // GROUP_SIZE
            print(f"error: group {args.group} is empty; there are {total} groups")
            return 1
        wanted = {n.lower() for n in batch}

    if wanted is not None:
        unknown = wanted - {n.lower() for n, _, _, _ in APIS}
        if unknown:
            print(f"error: unknown API name(s): {sorted(unknown)}")
            return 1

    selected = [a for a in APIS if wanted is None or a[0].lower() in wanted]
    print(f"dataset root : {args.datasets}")
    print(f"output root  : {args.out_root}")
    print(f"APIs to run  : {len(selected)}")
    print()

    SRC = os.path.join(REPO, "src")
    os.makedirs(args.log_dir, exist_ok=True)

    def run_one(item):
        name, source, framework, extra = item
        cmd, out_dir = build_command(name, source, framework, extra, args.datasets,
                                     args.out_root, subdir_for(name, source))
        sub = subdir_for(name, source)
        log_path = os.path.join(args.log_dir,
                                f"{name}_{sub}_run.log" if sub else f"{name}_run.log")
        t0 = time.time()
        with open(log_path, "w", encoding="utf-8", errors="replace") as lf:
            proc = subprocess.run(cmd, cwd=SRC, stdout=lf, stderr=subprocess.STDOUT)
        took = time.time() - t0
        done = os.path.isfile(os.path.join(out_dir, "step3_endpoints.json"))
        return {"name": name, "ok": proc.returncode == 0 and done,
                "rc": proc.returncode, "took": took, "log": log_path}

    began = time.time()
    for i, (name, source, framework, _) in enumerate(selected, 1):
        print(f"[{i}/{len(selected)}] {name} ({framework})")

    # Every API in the batch runs at once: the batch is the unit of work, and the
    # APIs are independent, so running them one after another only adds wall time.
    workers = args.parallel or len(selected)
    workers = min(workers, len(selected))
    print(f"\nlaunching {len(selected)} runs, {workers} at a time\n")

    results = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(run_one, item): item[0] for item in selected}
        for fut in as_completed(futures):
            r = fut.result()
            results.append(r)
            state = "ok" if r["ok"] else f"FAILED (exit {r['rc']})"
            print(f"  {r['name']:<18} {state}  {r['took']:>5.0f}s  -> {os.path.relpath(r['log'], REPO)}")

    if any(a[0] == BITWARDEN for a in selected):
        print(merge_bitwarden(args.out_root))

    ok = [r["name"] for r in results if r["ok"]]
    failed = [r["name"] for r in results if not r["ok"]]
    print()
    print(f"finished in {time.time() - began:.0f}s: {len(ok)} ok, {len(failed)} failed")
    if failed:
        print("failed: " + ", ".join(failed))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
