#!/usr/bin/env bash
# ============================================================================
# LRASGen — Run all 53 RESTful APIs through the full pipeline (Linux / macOS)
#
# Prerequisites:
#   1. Set LRASGEN_DATASETS to the absolute path of the datasets directory:
#        export LRASGEN_DATASETS="/home/user/LRASGen/datasets"
#   2. Set LLM API keys:
#        export DEEPSEEK_API_KEY="sk-..."
#        export OPENROUTER_API_KEY="sk-or-v1-..."
#   3. Install dependencies:
#        pip install -r requirements.txt
#
# Usage:
#   ./run_all_apis.sh
#
# Output lands in output/<api-name>/
# ============================================================================

set -e

if [ -z "$LRASGEN_DATASETS" ]; then
    echo "ERROR: LRASGEN_DATASETS environment variable is not set."
    echo "Set it to the absolute path of the datasets directory, e.g.:"
    echo "  export LRASGEN_DATASETS=\"/home/user/LRASGen/datasets\""
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/src"

echo "LRASGEN_DATASETS = $LRASGEN_DATASETS"
echo "Output directory = $SCRIPT_DIR/output/"
echo ""

# ===== Spring Boot（Java） =====

echo "[1/53] Actuator"
python main.py --root-path "$LRASGEN_DATASETS" --api-path spring-actuator-demo --output-name spring-actuator-demo

echo "[2/53] Batch"
python main.py --root-path "$LRASGEN_DATASETS" --api-path spring-batch-rest --output-name spring-batch-rest

echo "[3/53] Bibliothek"
python main.py --root-path "$LRASGEN_DATASETS" --api-path bibliothek --output-name bibliothek

echo "[4/53] Blog"
python main.py --root-path "$LRASGEN_DATASETS" --api-path blogapi --output-name blogapi

echo "[5/53] CatWatch"
python main.py --root-path "$LRASGEN_DATASETS" --api-path catwatch --output-name catwatch

echo "[6/53] CWA"
python main.py --root-path "$LRASGEN_DATASETS" --api-path cwa-verification-server --output-name cwa-verification-server

echo "[7/53] ERC20"
python main.py --root-path "$LRASGEN_DATASETS" --api-path erc20-rest-service --output-name erc20-rest-service

echo "[8/53] Faults"
python main.py --root-path "$LRASGEN_DATASETS" --api-path rest-faults-master --output-name rest-faults-master

echo "[9/53] Gestao"
python main.py --root-path "$LRASGEN_DATASETS" --api-path gestaohospital --output-name gestaohospital

echo "[10/53] HTTPPatch"
python main.py --root-path "$LRASGEN_DATASETS" --api-path http-patch-spring --output-name http-patch-spring

echo "[11/53] Market"
python main.py --root-path "$LRASGEN_DATASETS" --api-path market --output-name market

echo "[12/53] Microcks"
python main.py --root-path "$LRASGEN_DATASETS" --api-path microcks --output-name microcks

echo "[13/53] NCS"
python main.py --root-path "$LRASGEN_DATASETS" --api-path ncs --output-name ncs

echo "[14/53] OCVN"
python main.py --root-path "$LRASGEN_DATASETS" --api-path ocvn --output-name ocvn

echo "[15/53] Ohsome"
python main.py --root-path "$LRASGEN_DATASETS" --api-path ohsome-api --output-name ohsome-api

echo "[16/53] Person"
python main.py --root-path "$LRASGEN_DATASETS" --api-path person-controller --output-name person-controller

echo "[17/53] PetClinic"
python main.py --root-path "$LRASGEN_DATASETS" --api-path spring-petclinic-rest-master --output-name spring-petclinic-rest-master

echo "[18/53] Piggy"
python main.py --root-path "$LRASGEN_DATASETS" --api-path piggymetrics-master --output-name piggymetrics-master

echo "[19/53] ProxyPrint"
python main.py --root-path "$LRASGEN_DATASETS" --api-path proxyprint-kitchen --output-name proxyprint-kitchen

echo "[20/53] Quartz"
python main.py --root-path "$LRASGEN_DATASETS" --api-path quartz-manager --output-name quartz-manager

echo "[21/53] Reservations"
python main.py --root-path "$LRASGEN_DATASETS" --api-path reservations-api --output-name reservations-api

echo "[22/53] SBRAE"
python main.py --root-path "$LRASGEN_DATASETS" --api-path spring-rest-example --output-name spring-rest-example

echo "[23/53] SCS"
python main.py --root-path "$LRASGEN_DATASETS" --api-path scs --output-name scs

echo "[24/53] Session"
python main.py --root-path "$LRASGEN_DATASETS" --api-path session-service --output-name session-service

echo "[25/53] Tiltak"
python main.py --root-path "$LRASGEN_DATASETS" --api-path tiltaksgjennomforing --output-name tiltaksgjennomforing

echo "[26/53] UM"
python main.py --root-path "$LRASGEN_DATASETS" --api-path user-management --output-name user-management

echo "[27/53] Ur-Codebin"
python main.py --root-path "$LRASGEN_DATASETS" --api-path Ur-Codebin-API --output-name ur-codebin-api

echo "[28/53] WebGoat"
python main.py --root-path "$LRASGEN_DATASETS" --api-path webgoat --output-name webgoat

echo "[29/53] YTM（Kotlin / Spring Boot）"
python main.py --root-path "$LRASGEN_DATASETS" --api-path youtube-mock --output-name youtube-mock

# ===== Jersey（Java） =====

echo "[30/53] Digdag"
python main.py --root-path "$LRASGEN_DATASETS" --api-path digdag/digdag-server --output-name digdag-server

echo "[31/53] Cassandra"
python main.py --root-path "$LRASGEN_DATASETS" --api-path management-api-for-apache-cassandra --output-name management-api-for-apache-cassandra

echo "[32/53] Features-Service"
python main.py --root-path "$LRASGEN_DATASETS" --api-path features-service --output-name features-service

echo "[33/53] Gravitee"
python main.py --root-path "$LRASGEN_DATASETS" --api-path gravitee-api-management --output-name gravitee-api-management

echo "[34/53] Kafka"
python main.py --root-path "$LRASGEN_DATASETS" --api-path kafka-rest --output-name kafka-rest

echo "[35/53] Payments"
python main.py --root-path "$LRASGEN_DATASETS" --api-path pay-publicapi --output-name pay-publicapi

echo "[36/53] Petstore"
python main.py --root-path "$LRASGEN_DATASETS" --api-path swagger-petstore --output-name swagger-petstore

echo "[37/53] RESTCountries"
python main.py --root-path "$LRASGEN_DATASETS" --api-path restcountries --output-name restcountries

echo "[38/53] Scout"
python main.py --root-path "$LRASGEN_DATASETS" --api-path scout-api --output-name scout-api

echo "[39/53] Senzing"
python main.py --root-path "$LRASGEN_DATASETS" --api-path senzing-api-server --output-name senzing-api-server

# ===== JDK（Java） =====

echo "[40/53] Languagetool"
python main.py --root-path "$LRASGEN_DATASETS" --api-path languagetool --output-name languagetool --framework jdk

# ===== Spring Boot（Kotlin） =====

echo "[41/53] Familie"
python main.py --root-path "$LRASGEN_DATASETS" --api-path familie-ba-sak --output-name familie-ba-sak

echo "[42/53] News"
python main.py --root-path "$LRASGEN_DATASETS" --api-path news --output-name news

# ===== ASP.NET Core（C#） =====

echo "[43/53] enviroCar"
python main.py --root-path "$LRASGEN_DATASETS" --api-path enviroCar-server --output-name envirocar-server

echo "[44/53] Genome"
python main.py --root-path "$LRASGEN_DATASETS" --api-path genome-nexus --output-name genome-nexus

echo "[45/53] PTS"
python main.py --root-path "$LRASGEN_DATASETS" --api-path tracking-system --output-name tracking-system

# ===== Bitwarden =====

echo "[46/53] bitwarden-api（Public API）"
python main.py --root-path "$LRASGEN_DATASETS" --api-path bitwarden-server-main/src/Api/Public --output-name bitwarden-api

echo "[47/53] bitwarden-vault（Vault Management API）"
python main.py --root-path "$LRASGEN_DATASETS" --api-path bitwarden_clients-main/apps/cli/src --output-name bitwarden-vault

# ===== Express / NestJS =====

echo "[48/53] Cyclotron"
python main.py --root-path "$LRASGEN_DATASETS" --api-path cyclotron-master --output-name cyclotron-master

echo "[49/53] Realworld"
python main.py --root-path "$LRASGEN_DATASETS" --api-path nestjs-realworld-example-app-master --output-name nestjs-realworld-example-app-master

# ===== Python =====

echo "[50/53] Gramps（Flask）"
python main.py --root-path "$LRASGEN_DATASETS" --api-path gramps-web-api-master --framework flask --config-file gramps-web-api-master/gramps_webapi/api/__init__.py --output-name gramps-web-api-master

echo "[51/53] Jupyter（Tornado）"
python main.py --root-path "$LRASGEN_DATASETS" --api-path jupyter_server-main --framework tornado --keyword 'default_handlers = [' --output-name jupyter-server

echo "[52/53] Mlmmj（Web.py）"
python main.py --root-path "$LRASGEN_DATASETS" --api-path mlmmjadmin-master --framework webpy --config-file mlmmjadmin-master/controllers/urls.py --urls "/api/(%s)$,controllers.profile.Profile,/api/(%s)/owners,controllers.profile.Owners,/api/(%s)/moderators,controllers.profile.Moderators,/api/(%s)/subscribers,controllers.subscriber.Subscribers,/api/(%s)/has_subscriber/(%s),controllers.subscriber.HasSubscriber,/subscriber/(%s)/subscribed,controllers.subscriber.SubscribedLists,/subscriber/(%s)/subscribe,controllers.subscriber.Subscribe" --output-name mlmmjadmin-master

echo "[53/53] Poke（Django）"
python main.py --root-path "$LRASGEN_DATASETS" --api-path pokeapi-master --framework django --config-file pokeapi-master/pokemon_v2/urls.py --output-name pokeapi-master

echo ""
echo "============================================"
echo "All 53 APIs processed. Output in src/output/"
echo "============================================"
