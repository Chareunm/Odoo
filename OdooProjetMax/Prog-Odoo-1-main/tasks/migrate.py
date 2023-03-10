# -*- coding: utf-8 -*-
# Copyright 2019 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from pprint import pprint

from invoke import task

from .database import get_db_list, get_db_request_result


@task(name='check-modules')
def check_modules(ctx, migrated_db, full_db, sample_db):
    """Print modules comparison between given databases"""
    can_continue = True
    db_list = get_db_list(ctx)
    if migrated_db not in db_list:
        print("Migrated database `%s` not found" % migrated_db)
        can_continue = False
    if full_db not in db_list:
        print("Full database `%s` not found" % full_db)
        can_continue = False
    if sample_db and sample_db not in db_list:
        print("Sample database `%s` not found" % sample_db)
        can_continue = False

    if can_continue:
        sql = """
            SELECT
                name,
                state
            FROM
                ir_module_module
            WHERE
                state IN ('to install', 'to upgrade', 'installed')
            ORDER BY
                name;
        """
        migrated_modules = get_db_request_result(ctx, migrated_db, sql) or []
        full_modules = get_db_request_result(ctx, full_db, sql) or []
        sample_modules = get_db_request_result(ctx, sample_db, sql) or []

        print('')
        print('Modules in migrated database:')
        pprint(set(migrated_modules))

        print('')
        print('Modules in full database:')
        pprint(set(full_modules))

        print('')
        print('Modules in migrated database, but not in full database:')
        # In migrated database,
        # we get "to install", "to update" and  "installed" modules
        #
        # In full database, we only get "installed" modules
        #
        # So we just compare modules name without their state
        pprint({x[0] for x in migrated_modules} - {x[0] for x in full_modules})

        print('')
        print('Modules in full database, but not in sample database:')
        pprint(set(full_modules) - set(sample_modules))

        print('')
        print('Modules in sample database, but not in full database:')
        pprint(set(sample_modules) - set(full_modules))
