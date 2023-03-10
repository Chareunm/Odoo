FROM ghcr.io/camptocamp/odoo-project:14.0-latest
LABEL maintainer="Kal-It"
ARG UID=999
# Steps are grouped by dependency
# and ordered by compromizing cost and frequency

## Base requirements (Libs and packages)
# frequency: rarely
# cost:      high
COPY ./*requirements.txt /odoo/
COPY ./before-migrate-entrypoint.d/* /before-migrate-entrypoint.d/
COPY ./start-entrypoint.d/* /start-entrypoint.d/

# CSV Loader
# `parallel` + `importer.sh` are needed to load heavy files
COPY ./bin/importer.sh /odoo-bin/

## Prepare pip install
# frequency: never
# cost     : very light
COPY ./setup.py /odoo/

## Main activity
# frequency: always
# costs:     very high to very light
COPY ./src /odoo/src
COPY ./external-src /odoo/external-src
COPY ./local-src /odoo/local-src
COPY ./data /odoo/data/project
COPY ./songs /odoo/songs
COPY ./VERSION /odoo/
COPY ./migration.yml /odoo/
COPY ./history.yml /odoo/

USER root
# Install additional debian and python packages if needed
RUN set -x; \
        apt-get update \
        && pip install --upgrade pip \
        && apt-get install -y --no-install-recommends \
        parallel libmagic1 \
        cups libcups2-dev python3-dev\
        # if you need some dev packages for python packages, you need to clean them afterwards
        build-essential \
        git \
        # cleaning of dev packages
        && apt-get remove -y build-essential \
        # && apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false -o APT::AutoRemove::SuggestsImportant=false \
        && apt-get clean \
        && rm -rf /var/lib/apt/lists/*

# Entrypoints
RUN chmod +x /before-migrate-entrypoint.d/* \
    && chmod +x /start-entrypoint.d/

RUN usermod -u $UID -o odoo
RUN groupmod -g $UID odoo

RUN chown -R odoo:odoo /odoo
USER odoo
RUN pip install -e /odoo
RUN pip install -e /odoo/src

## Tools of odoo-template
# frequency: seldom
# cost:      light

# depends on ./setup.py ./src, ./songs and ./VERSION
RUN cd /odoo && pip install -r requirements.txt

## PLATFORM: Add this line to ADDONS_PATH if hosting is on cloud platform
# /odoo/external-src/odoo-cloud-platform, \

## Environment
# frequency: sometimes
# cost:      very light
ENV ADDONS_PATH="/odoo/src/addons, \
  /odoo/external-src/web, \
  /odoo/local-src" \
  LIMIT_TIME_CPU=86400 \
  LIMIT_TIME_REAL=86400 \
  LIMIT_MEMORY_SOFT=1342177280 \
  LIMIT_MEMORY_HARD=1610612736 \
  ODOO_DATA_PATH=/odoo/data/project